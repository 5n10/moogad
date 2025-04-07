"""
WebSocket server for M300 AI LARC application.
"""

import asyncio
import json
import logging
from typing import Dict, Set, Any, Optional, Callable, List
# Removed duplicate import line
from typing import Dict, Set, Any, Optional, Callable
from enum import Enum

import websockets
from websockets.legacy.server import WebSocketServerProtocol

try:
    import rtmidi
except ImportError:
    rtmidi = None
    logging.getLogger("WebSocketServer").warning("python-rtmidi not found. MIDI port listing/connection will be disabled.")


from midi.m300_controller import M300Controller, SetupPresetV3, EffectPresetV3 # Import preset classes
from midi.connection import ConnectionManager
from midi.error_tracking import ErrorTracker
from midi.validation import MessageValidator
# Assuming PRESET_CLASS_MAP might be useful here too, or handled within controller
# from midi.models import PRESET_CLASS_MAP

logger = logging.getLogger(__name__)

class ConnectionState(Enum):
    """Connection states for the WebSocket server."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

class WebSocketServer:
    """WebSocket server managing M300 controller and client connections."""

    def __init__(self, host: str = "localhost", port: int = 8765,
                 midi_in: Optional[str] = None, midi_out: Optional[str] = None):
        """Initialize the WebSocket server."""
        self.host = host
        self.port = port
        self.midi_in = midi_in
        self.midi_out = midi_out
        self.m300: Optional[M300Controller] = None # Add type hint
        self.server = None
        self.port_aliases = self._load_config()
        self.connection_state = ConnectionState.DISCONNECTED # Initialize state


        self._clients: Set[WebSocketServerProtocol] = set()

    def _load_config(self) -> Dict[str, str]:
        """Loads MIDI port aliases from config.json."""
        config_path = 'config.json'
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
                aliases = config_data.get('midi_port_aliases', {})
                logger.info(f"Loaded MIDI port aliases from {config_path}: {aliases}")
                return aliases
        except FileNotFoundError:
            logger.warning(f"{config_path} not found. No MIDI port aliases loaded.")
            return {}
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {config_path}. No aliases loaded.")
            return {}
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {e}")
            return {}

        self.connection_manager = ConnectionManager() # This seems unused here, maybe belongs in controller?
        self._health_check_task = None
        self._state_update_task = None
        self.connection_state = ConnectionState.DISCONNECTED
        self.error_tracker = ErrorTracker()
        self.validator = MessageValidator()

    async def start(self):
        """Start the WebSocket server."""
        try:
            await self.set_state(ConnectionState.CONNECTING)
            # Bind the handle_client method with self.m300 available
            handler = lambda ws, path: self.handle_client(ws, path)
            self.server = await websockets.serve(handler, self.host, self.port)
            logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")
            await self.set_state(ConnectionState.CONNECTED)

            # Create controller
            loop = asyncio.get_running_loop()
            self.m300 = M300Controller(
                loop=loop,
                midi_in_port_name=self.midi_in,
                midi_out_port_name=self.midi_out
            )
            # Pass connected clients set to controller for broadcasting
            self.m300.connected_clients = self._clients

            # Start health check task
            self._health_check_task = asyncio.create_task(self._monitor_connection())

            # Request initial state after controller is ready and potentially connected
            # Delay slightly to allow MIDI connection attempt
            await asyncio.sleep(0.5)
            # Use the correct attribute name with underscore
            if self.m300 and self.m300._midi_connected:
                 self.m300.request_active_setup()
                 await asyncio.sleep(0.05) # Small delay between requests
                 self.m300.request_active_effect_a()
                 await asyncio.sleep(0.05)
                 self.m300.request_active_effect_b()
            else:
                 logger.warning("MIDI not connected, skipping initial state request.")


        except Exception as e:
            logger.exception("Failed to start WebSocket server")
            await self.set_state(ConnectionState.ERROR)
            raise

    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """Handle WebSocket client connection."""
        logger.info(f"Client connected: {websocket.remote_address}")
        self._clients.add(websocket)
        if self.m300: # Ensure controller exists before assigning clients
             self.m300.connected_clients = self._clients # Update controller's client list
        try:
            # Send initial state
            await self.send_initial_state(websocket)

            # Handle messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    logger.debug(f"Received message: {data}")

                    # Validate message (optional, basic check here)
                    if "type" not in data:
                        raise ValueError("Message missing 'type' field")

                    # Process valid message
                    await self.process_message(websocket, data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from {websocket.remote_address}: {message}")
                    await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": "Invalid JSON format"}}))
                except ValueError as e:
                     logger.error(f"Invalid message format from {websocket.remote_address}: {e}")
                     await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": f"Invalid message: {e}"}}))
                except Exception as e:
                    logger.exception(f"Error handling message from {websocket.remote_address}")
                    await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": f"Error processing message: {str(e)}"}}))

        except websockets.exceptions.ConnectionClosedOK:
             logger.info(f"Client disconnected normally: {websocket.remote_address}")
        except websockets.exceptions.ConnectionClosedError as e:
             logger.warning(f"Client connection closed with error: {websocket.remote_address} - {e}")
        except Exception as e:
            logger.exception(f"WebSocket handler error for {websocket.remote_address}")
        finally:
            logger.info(f"Removing client: {websocket.remote_address}")
            self._clients.remove(websocket)
            if self.m300: # Update controller's client list
                 self.m300.connected_clients = self._clients

    async def send_initial_state(self, websocket: WebSocketServerProtocol):
        """Send initial state to newly connected client."""
        if not self.m300:
            logger.warning("Cannot send initial state, controller not initialized.")
            return

        logger.debug(f"Sending initial state to {websocket.remote_address}")
        try:
            # Send connection status first
            await websocket.send(json.dumps({
                "type": "midi_status",
                "payload": {
                    "connected": self.m300._midi_connected, # Use correct attribute
                    "in_port": self.m300.midi_in_port_name,
                    "out_port": self.m300.midi_out_port_name
                 }
            }))

            # Send full state from controller
            full_state = self.m300.get_full_state()
            await websocket.send(json.dumps({
                 "type": "full_state",
                 "payload": full_state
            }))
            logger.debug("Initial state sent.")

            # Also send the combined preset list on initial connect
            if self.m300: # Ensure controller exists
                all_presets = self.m300.get_all_presets()
                await websocket.send(json.dumps({
                     "type": "all_presets",
                     "payload": all_presets
                }))
                logger.debug(f"Initial preset list sent ({len(all_presets)} presets).")

            # Also send the combined preset list on initial connect
            if self.m300: # Ensure controller exists
                all_presets = self.m300.get_all_presets()
                await websocket.send(json.dumps({
                     "type": "all_presets",
                     "payload": all_presets
                }))
                logger.debug(f"Initial preset list sent ({len(all_presets)} presets).")

            # Also send the combined preset list on initial connect
            all_presets = self.m300.get_all_presets()
            await websocket.send(json.dumps({
                 "type": "all_presets",
                 "payload": all_presets
            }))
            logger.debug("Initial preset list sent.")

        except Exception as e:
            logger.error(f"Error sending initial state to {websocket.remote_address}: {e}")


    async def process_message(self, websocket: WebSocketServerProtocol, data: Dict[str, Any]):
        """Process validated message from client."""
        if not self.m300:
            await websocket.send(json.dumps({
                "type": "error",
                "payload": {"source": "ws_server", "message": "MIDI controller not initialized"}
            }))
            return

        payload = data.get("payload", {}) # Get payload safely
        msg_type = data.get("type")
        logger.debug(f"Processing message type: {msg_type} with payload: {payload}")

        try:
            if msg_type == "parameter_change":
                # Assuming payload structure: { domain: number, param: number, value: number }
                if "domain" in payload and "param" in payload and "value" in payload:
                    # Use the controller's method which now handles SysEx/NRPN generation
                    # Run in background task to avoid blocking websocket handler
                    asyncio.create_task(self.m300.send_parameter_change(
                        int(payload["domain"]),
                        int(payload["param"]),
                        int(payload["value"]),
                        source='websocket' # Indicate source
                    ))
                else:
                    logger.warning(f"Invalid parameter_change payload: {payload}")
                    await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": "Invalid parameter_change payload"}}))

            elif msg_type == "request_active_state":
                 # Run requests in background
                 asyncio.create_task(self.m300.request_active_setup())
                 # No need for sleep here, controller handles delays if necessary
                 asyncio.create_task(self.m300.request_active_effect_a())
                 asyncio.create_task(self.m300.request_active_effect_b())

            elif msg_type == "save_preset":
                 # Assuming payload structure: { preset_data: Dict, index: int, preset_type: 'setup' | 'effect' }
                preset_data = payload.get("preset_data")
                index = payload.get("index")
                preset_type = payload.get("preset_type") # Helps determine which class to use

                if preset_data and isinstance(index, int) and preset_type in ['setup', 'effect']:
                    logger.info(f"Received save_preset request for index {index}, type {preset_type}")
                    PresetClass = SetupPresetV3 if preset_type == 'setup' else EffectPresetV3
                    try:
                        preset_obj = PresetClass.from_dict(preset_data)
                        # Call controller method to handle SysEx generation and sending (run in background)
                        asyncio.create_task(self.m300.save_preset_to_register(preset_obj, index))
                    except Exception as e:
                         logger.error(f"Error reconstructing/saving preset: {e}", exc_info=True)
                         await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": f"Error saving preset: {e}"}}))
                else:
                    logger.warning(f"Invalid save_preset payload: {payload}")
                    await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": "Invalid save_preset payload"}}))

            elif msg_type == "load_preset":
                 # Assuming payload structure: { id: number, slot?: 'A' | 'B', kind: 'setup' | 'effect' }
                 preset_id = payload.get("id")
                 slot = payload.get("slot", "A") # Default to slot A for effects
                 preset_kind = payload.get("kind") # Frontend needs to specify 'setup' or 'effect'

                 if isinstance(preset_id, int) and preset_kind in ['setup', 'effect']:
                     logger.info(f"Received load_preset request for ID {preset_id}, Kind: {preset_kind}, Slot: {slot}")
                     # TODO: Determine if ID is factory/stored
                     preset_to_load = None
                     # Example: Check stored first
                     if preset_kind == "effect" and preset_id in self.m300.stored_effects:
                         preset_to_load = self.m300.stored_effects[preset_id]
                     elif preset_kind == "setup" and preset_id in self.m300.stored_setups:
                          preset_to_load = self.m300.stored_setups[preset_id]
                     # TODO: Add logic to check factory presets (Requires knowing how to load factory via MIDI)
                     logger.info(f"Preset ID {preset_id} (Kind: {preset_kind}) is likely a factory preset. Loading via MIDI not implemented yet.")

                     if preset_to_load:
                          # Run in background task
                          asyncio.create_task(self.m300.send_preset_to_active(preset_to_load, slot if preset_kind == 'effect' else 'A'))
                     else:
                         logger.warning(f"Preset ID {preset_id} (Kind: {preset_kind}) not found in controller state.")
                         await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": f"Preset ID {preset_id} not found"}}))
                 else:
                     logger.warning(f"Invalid load_preset payload: {payload}")
                     await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": "Invalid load_preset payload"}}))

            elif msg_type == "get_midi_ports":
                # Correctly indented block
                inputs = []
                # Call the standalone list_midi_ports function, passing aliases
                try:
                    ports_dict = list_midi_ports(self.port_aliases)
                    inputs = ports_dict.get('in', [])
                    outputs = ports_dict.get('out', [])
                except Exception as e:
                    logger.error(f"Error calling list_midi_ports: {e}")
                    inputs = [f"Error: {e}"]
                    outputs = [f"Error: {e}"]
                await websocket.send(json.dumps({
                    "type": "midi_ports",
                    "payload": { # Send data under payload key
                        "ports": { "inputs": inputs, "outputs": outputs }
                    }
                }))

            elif msg_type == "connect_midi":
                 # Assuming payload structure: { input_port: string, output_port: string, channel: int }
                 input_port = payload.get("input_port")
                 output_port = payload.get("output_port")
                 channel = payload.get("channel", 1) # Default to channel 1 if not provided
                 # Validate channel
                 if not isinstance(channel, int) or not (1 <= channel <= 16):
                     logger.warning(f"Invalid channel received: {channel}. Using default 1.")
                     channel = 1

                 if input_port and output_port and self.m300:
                     self.m300.midi_in_port_name = input_port
                     self.m300.midi_out_port_name = output_port
                     self.m300.midi_channel = channel # Set the channel on the controller
                     # connect_midi is synchronous and updates internal state
                     self.m300.connect_midi()
                     # Status is broadcast from within connect_midi now
                 elif not self.m300:
                      logger.error("Cannot connect MIDI: Controller not initialized.")
                      await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": "MIDI controller not initialized"}}))
                 else: # Missing input or output port
                     logger.warning(f"Invalid connect_midi payload (missing ports?): {payload}")
                     await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": "Invalid connect_midi payload"}}))

            # --- Add other message type handlers ---
            elif msg_type == "request_stored_setup":
                 index = payload.get("index")
                 if isinstance(index, int):
                      asyncio.create_task(self.m300.request_stored_setup(index))
            elif msg_type == "request_stored_effect":
                 index = payload.get("index")
                 if isinstance(index, int):
                      asyncio.create_task(self.m300.request_stored_effect(index))
            # Add more request handlers...
            elif msg_type == "request_mod_matrix":
                 if self.m300: asyncio.create_task(self.m300.request_mod_matrix())
            elif msg_type == "add_mod_route":
                 # Payload: { source: int, destination: int, amount: int, enabled: bool } (IDs/Indices, not names)
                 # TODO: Map names from frontend to IDs/Indices before sending to controller
                 logger.info(f"Received add_mod_route (Placeholder): {payload}")
                 # if self.m300: asyncio.create_task(self.m300.send_mod_route_update(...)) # Needs mapping and route ID/index
            elif msg_type == "update_mod_route":
                 # Payload: { id: any, updates: { source?: int, destination?: int, amount?: int, enabled?: bool } }
                 # TODO: Map names from frontend to IDs/Indices before sending to controller
                 logger.info(f"Received update_mod_route (Placeholder): {payload}")
                 # if self.m300: asyncio.create_task(self.m300.send_mod_route_update(...)) # Needs mapping and route ID/index
            elif msg_type == "request_all_presets":
                 logger.info(f"Client {websocket.remote_address} requested all presets.")
                 if self.m300:
                     all_presets = self.m300.get_all_presets()
                     await websocket.send(json.dumps({
                         "type": "all_presets",
                         "payload": all_presets
                     }))
                     logger.debug(f"Sent {len(all_presets)} presets to client.")
                 else:
                      await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": "MIDI controller not initialized"}}))
            elif msg_type == "disconnect_midi":
                 logger.info(f"Client {websocket.remote_address} requested MIDI disconnect.")
                 if self.m300:
                     self.m300.close_midi() # Call the controller's close method
                     # Status update will be broadcast automatically by close_midi/connect_midi logic
                 else:
                      await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": "MIDI controller not initialized"}}))
            elif msg_type == "add_mod_route":
                 # Payload: { source: string, destination: string, amount: int, enabled: bool }
                 logger.info(f"Received add_mod_route request: {payload}")
                 if self.m300:
                     # TODO: Implement M300Controller.add_mod_route(payload)
                     # This would parse source/dest strings to IDs, generate MIDI, etc.
                     logger.warning("Backend logic for add_mod_route not implemented yet.")
                     # Optionally send feedback
                     # await self._broadcast_feedback("info", "Add route received (not implemented)")
                     pass # Placeholder
                 else:
                      await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": "MIDI controller not initialized"}}))

            elif msg_type == "update_mod_route":
                 # Payload: { id: string, updates: { source?: string, destination?: string, amount?: int, enabled?: bool } }
                 logger.info(f"Received update_mod_route request: {payload}")
                 if self.m300:
                      # TODO: Implement M300Controller.update_mod_route(payload['id'], payload['updates'])
                      logger.warning("Backend logic for update_mod_route not implemented yet.")
                      pass # Placeholder
                 else:
                      await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": "MIDI controller not initialized"}}))

            elif msg_type == "delete_mod_route":
                 # Payload: { id: string }
                 logger.info(f"Received delete_mod_route request: {payload}")
                 if self.m300:
                      # TODO: Implement M300Controller.delete_mod_route(payload['id'])
                      # Or potentially map to disabling the route via update
                      logger.warning("Backend logic for delete_mod_route not implemented yet.")
                      pass # Placeholder
                 else:
                      await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": "MIDI controller not initialized"}}))

            elif msg_type == "request_all_presets":
                 logger.info(f"Client {websocket.remote_address} requested all presets.")
                 if self.m300:
                     all_presets = self.m300.get_all_presets()
                     await websocket.send(json.dumps({
                         "type": "all_presets",
                         "payload": all_presets
                     }))
                     logger.debug(f"Sent {len(all_presets)} presets to client.")
                 else:
                      await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": "MIDI controller not initialized"}}))
            elif msg_type == "request_all_presets":
                 logger.info(f"Client {websocket.remote_address} requested all presets.")
                 if self.m300:
                     all_presets = self.m300.get_all_presets()
                     await websocket.send(json.dumps({
                         "type": "all_presets",
                         "payload": all_presets
                     }))
            elif msg_type == "delete_mod_route":
                 # Payload: { id: any }
                 # TODO: Determine if deletion is possible or just disabling
                 logger.info(f"Received delete_mod_route (Placeholder): {payload}")
                 # if self.m300: asyncio.create_task(self.m300.send_mod_route_update(payload.get('id'), ..., enabled=False)) # Example: Disable instead of delete
            else:
                 logger.warning(f"Received unknown message type: {msg_type}")
                 await websocket.send(json.dumps({"type": "error", "payload": {"source": "ws_server", "message": f"Unknown command type: {msg_type}"}}))

        except Exception as e:
            logger.exception(f"Error processing message type {msg_type}") # Log full traceback
            self.error_tracker.add_error("message_processing", str(e), str(data))
            await websocket.send(json.dumps({
                "type": "error",
                "payload": {"source": "ws_server", "message": f"Internal server error processing '{msg_type}': {str(e)}"}
            }))

    async def _monitor_connection(self):
        """Monitor connection health."""
        while True:
            try:
                await asyncio.sleep(5) # Check less frequently
                if self.m300:
                    # Check MIDI connection status (assuming controller updates _midi_connected)
                    # Only attempt reconnect if ports have been selected previously
                    if not self.m300._midi_connected and self.m300.midi_in_port_name and self.m300.midi_out_port_name:
                         logger.warning("MIDI connection lost. Attempting to reconnect using selected ports...")
                         self.m300.connect_midi() # connect_midi handles broadcast
                    elif not self.m300._midi_connected:
                         # Log that we are waiting for initial port selection if ports are None
                         logger.debug("MIDI not connected. Waiting for port selection via client.")

                    # Check error rate (optional)
                    # if self.error_tracker.should_reconnect("message_processing"):
                    #     logger.warning("High error rate detected, attempting to reconnect MIDI...")
                    #     self.m300.close_midi()
                    #     await asyncio.sleep(1) # Give time to close
                    #     self.m300.connect_midi()

            except asyncio.CancelledError:
                logger.info("Connection monitor task cancelled.")
                break
            except Exception:
                 logger.exception("Error in connection monitor task")
                 await asyncio.sleep(15) # Wait longer after an error

    async def set_state(self, new_state: ConnectionState):
        """Set connection state and broadcast."""
        if new_state != self.connection_state:
            logger.info(f"WebSocket Server state changed: {self.connection_state.value} -> {new_state.value}")
            self.connection_state = new_state
            # Broadcast state change to clients
            message = json.dumps({
                "type": "connection_state",
                "payload": {"state": new_state.value}
            })
            # Use gather for concurrent sending
            results = await asyncio.gather(
                 *[client.send(message) for client in self._clients],
                 return_exceptions=True
            )
            for res, client in zip(results, list(self._clients)):
                 if isinstance(res, Exception):
                      logger.error(f"Failed to send state update to client {client.remote_address}: {res}")


    async def stop(self):
        """Stop the server."""
        logger.info("Stopping WebSocket server...")
        # Cancel background tasks
        if self._health_check_task:
            self._health_check_task.cancel()
            try: await self._health_check_task
            except asyncio.CancelledError: pass

        # Close MIDI controller
        if self.m300:
            await self.m300.stop() # Assuming stop is async

        # Close all client connections
        logger.info(f"Closing {len(self._clients)} client connections...")
        if self._clients:
             results = await asyncio.gather(
                  *[client.close(code=1001, reason='Server shutdown') for client in self._clients],
                  return_exceptions=True
             )
             for res, client in zip(results, list(self._clients)):
                  if isinstance(res, Exception):
                       logger.error(f"Error closing client {client.remote_address}: {res}")
        self._clients.clear()

        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("WebSocket server closed.")

        await self.set_state(ConnectionState.DISCONNECTED)

# --- Helper to list MIDI ports ---
def list_midi_ports(aliases: Dict[str, str]) -> Dict[str, List[Dict[str, str]]]:
    ports = {'in': [], 'out': []} # Type: Dict[str, List[Dict[str, str]]]
    # Helper to create port object with alias
    def create_port_object(system_name: str) -> Dict[str, str]:
        return {
            "system_name": system_name,
            "display_name": aliases.get(system_name, system_name) # Use alias or default to system name
        }

    if rtmidi is None:
        ports['in'].append(create_port_object("No rtmidi library"))
        ports['out'].append(create_port_object("No rtmidi library"))
        return ports
    try:
        midi_in = rtmidi.MidiIn()
        ports['in'] = [create_port_object(name) for name in midi_in.get_ports()]
        del midi_in
        midi_out = rtmidi.MidiOut()
        ports['out'] = [create_port_object(name) for name in midi_out.get_ports()]
        del midi_out
    except Exception as e:
        logger.error(f"Error listing MIDI ports: {e}")
        ports['in'].append(create_port_object(f"Error: {e}"))
        ports['out'].append(create_port_object(f"Error: {e}"))
    return ports


async def main(host: str = "localhost", port: int = 8765,
              midi_in: Optional[str] = None, midi_out: Optional[str] = None):
    """Run the WebSocket server."""
    # --- List Ports ---
    # Load aliases directly here for logging before server instance exists
    temp_aliases = {}
    config_path = 'config.json'
    try:
        with open(config_path, 'r') as f:
            config_data = json.load(f)
            temp_aliases = config_data.get('midi_port_aliases', {})
    except Exception: # Catch broad exception for initial logging
        pass # Ignore errors here, server init will handle proper loading/logging
    available_ports = list_midi_ports(temp_aliases)
    logger.info(f"Available MIDI Inputs: {available_ports['in']}")
    logger.info(f"Available MIDI Outputs: {available_ports['out']}")

    # --- Port Selection Deferred ---
    # Ports will be selected via the frontend UI and set via 'connect_midi' message.
    # Initialize server with None for ports.
    logger.info("Initializing WebSocket server without pre-selected MIDI ports.")
    logger.info("Please connect and select MIDI ports via the frontend UI.")

    server = WebSocketServer(host, port, midi_in, midi_out) # Pass initial midi_in/midi_out (likely None)
    await server.start()

    try:
        # Keep server running until interrupted
        await asyncio.Future()
    except (asyncio.CancelledError, KeyboardInterrupt):
         logger.info("Shutdown signal received.")
    finally:
        await server.stop()

if __name__ == "__main__":
    # Setup logging
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format)
    # Optionally set websockets logger level higher if too noisy
    logging.getLogger('websockets').setLevel(logging.WARNING)

    # --- Optional: Get port names from command line ---
    # import argparse
    # parser = argparse.ArgumentParser(description="LARC2 WebSocket Server")
    # parser.add_argument("--midi-in", help="Name of the MIDI input port")
    # parser.add_argument("--midi-out", help="Name of the MIDI output port")
    # args = parser.parse_args()
    # input_name = args.midi_in
    # output_name = args.midi_out
    input_name = None # Replace with actual name or selection logic/args
    output_name = None # Replace with actual name or selection logic/args


    try:
        asyncio.run(main(midi_in=input_name, midi_out=output_name))
    except ImportError as e:
        logger.error(f"Import Error: {e}. Please ensure required libraries are installed.")
        logger.error("Try: pip install websockets python-rtmidi")
    except Exception as e:
         logger.exception("Unhandled error during application startup or runtime.")
