"""
M300 Controller Class with MIDI I/O using rtmidi.
"""

import time
import logging
import asyncio
import json
from collections import deque
from typing import List, Tuple, Dict, Any, Optional, Callable, Set, Union

# Attempt to import websockets for type hinting, but don't fail if not installed
try:
    from websockets.legacy.server import WebSocketServerProtocol
except ImportError:
    WebSocketServerProtocol = Any # type: ignore

try:
    import rtmidi
except ImportError:
    rtmidi = None
    logging.getLogger("M300Controller").warning("python-rtmidi not found. MIDI I/O will be disabled.")

from .models import (
    EffectPresetV3, SetupPresetV3,
    ALGORITHM_ID_TO_NAME_V3, ALGORITHM_NAME_TO_ID_V3,
    PRESET_CLASS_MAP
)
from .utils import (
    SYSEX_START, SYSEX_END, LEXICON_ID, M300_ID,
    CLASS_ACTIVE_BULK, CLASS_STORED_BULK, CLASS_PARAMETER, CLASS_EVENT, CLASS_REQUEST, CLASS_RESPONSE, CLASS_DISPLAY,
    DOMAIN_UTILITY, DOMAIN_RUN, DOMAIN_SETUP, DOMAIN_EFFECT_A, DOMAIN_EFFECT_B, DOMAIN_MODULATION_A, DOMAIN_MODULATION_B,
    TYPE_ACTIVE_SETUP_V3, TYPE_ACTIVE_EFFECT_A_V3, TYPE_ACTIVE_EFFECT_B_V3, TYPE_STORED_SETUP_V3, TYPE_STORED_EFFECT_V3, TYPE_PRESET_SETUP_V3, TYPE_PRESET_EFFECT_V3,
    REQ_ACTIVE_SETUP, REQ_ACTIVE_EFFECT_A, REQ_ACTIVE_EFFECT_B, REQ_STORED_SETUP, REQ_STORED_EFFECT, REQ_PARAM_VALUE, REQ_ALL_STORED_SETUPS, REQ_ALL_STORED_EFFECTS,
    NRPN_MSB_CC, NRPN_LSB_CC, DATA_ENTRY_MSB_CC, DATA_ENTRY_LSB_CC,
    EXPECTED_FLAG_BYTES, FLAG_BYTES_LEN, CHECKSUM_LEN,
    is_m300_sysex, unnibblize_data, nibblize_data, calculate_checksum, parse_string, format_string, generate_bulk_sysex, generate_request,
    parse_m300_sysex_detailed
)
from .error_tracking import ErrorTracker
from .diagnostics import Diagnostics
from .connection import ConnectionManager, ConnectionConfig
from .validation import MessageValidator

logger = logging.getLogger(__name__)

PRESETS_FILE = "presets.json"
FACTORY_PRESETS_FILE = "data/factory_presets.json"

MIDI_TIMEOUT = 5.0
MIDI_RETRY_DELAY = 0.1

class MIDIError(Exception):
    """Custom exception for MIDI operations."""
    pass

class MIDITimeoutError(Exception):
    """Exception raised when MIDI operation times out."""
    pass

class NRPNParserState:
    """Keeps track of NRPN message state."""
    def __init__(self):
        self.nrpn_msb: Optional[int] = None
        self.nrpn_lsb: Optional[int] = None
        self.data_msb: Optional[int] = None

    def process_cc(self, cc_number: int, cc_value: int) -> Optional[Dict[str, int]]:
        """Process a CC message, return NRPN data if complete."""
        if cc_number == NRPN_MSB_CC:
            self.nrpn_msb = cc_value; self.nrpn_lsb = None; self.data_msb = None
        elif cc_number == NRPN_LSB_CC and self.nrpn_msb is not None: self.nrpn_lsb = cc_value
        elif cc_number == DATA_ENTRY_MSB_CC: self.data_msb = cc_value
        elif cc_number == DATA_ENTRY_LSB_CC and self.data_msb is not None:
            if self.nrpn_msb is not None and self.nrpn_lsb is not None:
                value = (self.data_msb << 7) | cc_value
                return {"nrpn_domain": self.nrpn_msb, "nrpn_param_number": self.nrpn_lsb, "nrpn_value": value}
        return None

class M300Controller:
    """Controller class for Lexicon M300 via MIDI."""

    def __init__(self, loop: asyncio.AbstractEventLoop,
                 midi_in_port_name: Optional[str] = None,
                 midi_out_port_name: Optional[str] = None,
                 midi_channel: int = 1):
        """Initialize controller."""
        self.loop = loop
        self.midi_channel = midi_channel
        self.midi_in_port_name = midi_in_port_name
        self.midi_out_port_name = midi_out_port_name
        self.midi_in = None
        self.midi_out = None
        self._midi_connected = False

        # State tracking
        self.param_values: Dict[int, Dict[int, int]] = {d: {} for d in range(7)}
        self.active_setup: Optional[SetupPresetV3] = None
        self.active_effect_a: Optional[EffectPresetV3] = None
        self.active_effect_b: Optional[EffectPresetV3] = None
        self.stored_setups: Dict[int, SetupPresetV3] = {}
        self.stored_effects: Dict[int, EffectPresetV3] = {}
        self.factory_preset_data: List[Dict[str, Any]] = [] # Store raw factory preset data

        # Message queues & Processing
        self.command_queue = asyncio.Queue()
        self._command_processor_task: Optional[asyncio.Task] = None
        self._message_queue = deque(maxlen=1000)
        self.nrpn_parser = NRPNParserState()

        # Connection management
        self.connection_manager = ConnectionManager(
            ConnectionConfig(retry_delay=5.0, max_retries=3, timeout=10.0, keepalive_interval=30.0)
        )

        # Error tracking & Diagnostics
        self.error_tracker = ErrorTracker()
        self.diagnostics = Diagnostics()
        self._monitor_task: Optional[asyncio.Task] = None
        self.connected_clients: Set[WebSocketServerProtocol] = set()

        # Start background tasks
        self._start_monitoring()
        self._start_command_processor()
        self._load_presets_from_file()
        self._load_factory_presets()

    # --- State Management Methods ---
    def _update_parameter_state(self, domain: int, param_number: int, value: int) -> bool:
        """Updates the internal parameter state and returns True if changed."""
        if not (0 <= domain <= 6): logger.warning(f"Invalid domain: {domain}"); return False
        if not (0 <= value <= 16383): logger.warning(f"Invalid value: {value}"); return False
        current_value = self.param_values.setdefault(domain, {}).get(param_number)
        if current_value != value:
            self.param_values[domain][param_number] = value
            logger.debug(f"State updated: Domain={domain}, Param={param_number}, Value={value}")
            return True
        return False

    def get_parameter_value(self, domain: int, param_number: int) -> Optional[int]:
        """Retrieves the current value for a parameter from the internal state."""
        if not (0 <= domain <= 6): logger.warning(f"Invalid domain: {domain}"); return None
        return self.param_values.get(domain, {}).get(param_number)

    def get_full_state(self) -> Dict[str, Any]:
        """Returns a dictionary representing the current known state (excluding presets)."""
        return {
            "midi_connected": self._midi_connected,
            "active_setup": self.active_setup.to_dict() if self.active_setup else None,
            "active_effect_a": self.active_effect_a.to_dict() if self.active_effect_a else None,
            "active_effect_b": self.active_effect_b.to_dict() if self.active_effect_b else None,
            "param_values": self.param_values,
        }

    # --- MIDI Message Generation ---
    def _create_parameter_sysex(self, domain: int, param_number: int, value: int) -> Tuple[int, ...]:
        """Creates a SysEx message for a parameter change."""
        if not (0 <= value <= 16383): raise ValueError(f"Value {value} out of 14-bit range")
        class_channel = (CLASS_PARAMETER << 4) | ((self.midi_channel - 1) & 0x0F)
        type_byte = (0 << 4) | (domain & 0x0F)
        param_byte = param_number & 0x7F
        val_lsb = value & 0x7F; val_msb = (value >> 7) & 0x7F
        return (SYSEX_START, LEXICON_ID, M300_ID, class_channel, type_byte, param_byte, val_lsb, val_msb, SYSEX_END)

    # --- MIDI Sending/Request Methods ---
    def _send_hw_message(self, message_to_send: Union[Tuple[int, ...], List[Tuple[int, ...]]]):
        """Internal helper to send MIDI message(s) to hardware."""
        if not self.midi_out or not self._midi_connected:
            msg = "MIDI Output Not Connected"; logger.error(msg)
            asyncio.run_coroutine_threadsafe(self._broadcast_error("midi", msg), self.loop); raise MIDIError(msg)
        try:
            if isinstance(message_to_send, list):
                for msg in message_to_send: self.midi_out.send_message(list(msg))
            elif isinstance(message_to_send, tuple): self.midi_out.send_message(list(message_to_send))
            else: raise TypeError(f"Invalid message type: {type(message_to_send)}")
            self.diagnostics.record_message()
        except rtmidi.SystemError as e:
            logger.exception("rtmidi SystemError"); self._midi_connected = False
            asyncio.run_coroutine_threadsafe(self._broadcast_error("midi", f"SysError: {e}", str(message_to_send)), self.loop)
            asyncio.run_coroutine_threadsafe(self._broadcast_status(), self.loop); raise MIDIError(f"SysError: {e}") from e
        except Exception as e:
            logger.exception("MIDI Send Error"); asyncio.run_coroutine_threadsafe(self._broadcast_error("midi", f"Send Error: {e}", str(message_to_send)), self.loop)
            raise MIDIError(f"Send Error: {e}") from e

    def _send_request(self, request_tuple: Tuple[int, int, bool], value: Optional[int] = None, domain_for_param: Optional[int] = None):
        """Constructs and sends a SysEx request message."""
        logger.info(f"Sending Request: {request_tuple}, Value: {value}, Domain: {domain_for_param}")
        try:
            message = generate_request(request_tuple, value, domain_for_param, self.midi_channel)
            self._send_hw_message(message); logger.debug(f"Request sent: {message}")
        except MIDIError as e: logger.error(f"MIDIError sending request {request_tuple}: {e}")
        except ValueError as e: logger.error(f"ValueError generating request {request_tuple}: {e}"); asyncio.run_coroutine_threadsafe(self._broadcast_error("internal", f"Req gen error: {e}"), self.loop)
        except Exception as e: logger.exception(f"Error sending request {request_tuple}"); asyncio.run_coroutine_threadsafe(self._broadcast_error("internal", f"Req error: {e}"), self.loop)

    # --- Public Request Methods ---
    def request_active_setup(self): self._send_request(REQ_ACTIVE_SETUP)
    def request_active_effect_a(self): self._send_request(REQ_ACTIVE_EFFECT_A)
    def request_active_effect_b(self): self._send_request(REQ_ACTIVE_EFFECT_B)
    def request_stored_setup(self, index: int):
        if not (0 <= index <= 49): logger.warning(f"Invalid setup index: {index}"); return
        self._send_request(REQ_STORED_SETUP, value=index)
    def request_stored_effect(self, index: int):
        if not (0 <= index <= 49): logger.warning(f"Invalid effect index: {index}"); return
        self._send_request(REQ_STORED_EFFECT, value=index)
    def request_all_stored_setups(self): logger.info("Requesting all stored setups..."); self._send_request(REQ_ALL_STORED_SETUPS)
    def request_all_stored_effects(self): logger.info("Requesting all stored effects..."); self._send_request(REQ_ALL_STORED_EFFECTS)
    def request_parameter_value(self, domain: int, param_number: int): self._send_request(REQ_PARAM_VALUE, value=param_number, domain_for_param=domain)
    def request_mod_matrix(self):
        """Requests the current modulation matrix state from the M300L."""
        logger.info("Received request for Modulation Matrix state (Placeholder - MIDI command unknown)")
        # TODO: Implement actual SysEx request when known
        asyncio.run_coroutine_threadsafe(self._broadcast_feedback("warning", "Mod matrix request not implemented"), self.loop)

    # --- Preset Sending/Saving Methods ---
    def send_preset_to_active(self, preset_object: Union[SetupPresetV3, EffectPresetV3], slot: str = 'A'):
        logger.info(f"Sending preset '{preset_object.name}' to active slot {slot}")
        bulk_type, index = None, 0
        if isinstance(preset_object, SetupPresetV3): bulk_type = TYPE_ACTIVE_SETUP_V3
        elif isinstance(preset_object, EffectPresetV3):
            if slot == 'A': bulk_type, index = TYPE_ACTIVE_EFFECT_A_V3, 0
            elif slot == 'B': bulk_type, index = TYPE_ACTIVE_EFFECT_B_V3, 1
            else: logger.error(f"Invalid slot: {slot}"); asyncio.run_coroutine_threadsafe(self._broadcast_error("internal", f"Invalid slot: {slot}"), self.loop); return
        else: logger.error(f"Unsupported type: {type(preset_object).__name__}"); asyncio.run_coroutine_threadsafe(self._broadcast_error("internal", "Unsupported type"), self.loop); return
        if bulk_type is not None:
            try:
                sysex = generate_bulk_sysex(preset_object, bulk_type, index, self.midi_channel)
                if sysex:
                    self._send_hw_message(sysex)
                    if bulk_type == TYPE_ACTIVE_SETUP_V3: self.active_setup = preset_object
                    elif bulk_type == TYPE_ACTIVE_EFFECT_A_V3: self.active_effect_a = preset_object
                    elif bulk_type == TYPE_ACTIVE_EFFECT_B_V3: self.active_effect_b = preset_object
                    logger.info(f"Sent '{preset_object.name}' to active {slot}.")
                    asyncio.run_coroutine_threadsafe(self._broadcast_feedback("info", f"Loaded '{preset_object.name}' to Active {slot}"), self.loop)
                    update_type = "active_setup" if isinstance(preset_object, SetupPresetV3) else f"active_effect_{slot.lower()}"
                    asyncio.run_coroutine_threadsafe(self._broadcast_update({"type": update_type, "payload": preset_object.to_dict()}), self.loop)
                    self._save_presets_to_file()
                else: logger.error(f"Failed SysEx generation for '{preset_object.name}'."); asyncio.run_coroutine_threadsafe(self._broadcast_error("internal", "SysEx gen failed"), self.loop)
            except MIDIError as e: logger.error(f"MIDIError sending '{preset_object.name}': {e}")
            except Exception as e: logger.exception(f"Error sending '{preset_object.name}'"); asyncio.run_coroutine_threadsafe(self._broadcast_error("internal", f"Error sending: {e}"), self.loop)

    def save_preset_to_register(self, preset_object: Union[SetupPresetV3, EffectPresetV3], index: int):
        logger.info(f"Saving '{preset_object.name}' to register {index}")
        bulk_type = None
        if isinstance(preset_object, SetupPresetV3):
            if not (0 <= index <= 49): logger.error(f"Invalid Setup index: {index}"); asyncio.run_coroutine_threadsafe(self._broadcast_error("internal", f"Invalid Setup index: {index}"), self.loop); return
            bulk_type = TYPE_STORED_SETUP_V3
        elif isinstance(preset_object, EffectPresetV3):
             if not (0 <= index <= 49): logger.error(f"Invalid Effect index: {index}"); asyncio.run_coroutine_threadsafe(self._broadcast_error("internal", f"Invalid Effect index: {index}"), self.loop); return
             bulk_type = TYPE_STORED_EFFECT_V3
        else: logger.error(f"Unsupported type: {type(preset_object).__name__}"); asyncio.run_coroutine_threadsafe(self._broadcast_error("internal", "Unsupported type"), self.loop); return
        if bulk_type is not None:
            try:
                sysex = generate_bulk_sysex(preset_object, bulk_type, index, self.midi_channel)
                if sysex:
                    self._send_hw_message(sysex)
                    if bulk_type == TYPE_STORED_SETUP_V3: self.stored_setups[index] = preset_object
                    elif bulk_type == TYPE_STORED_EFFECT_V3: self.stored_effects[index] = preset_object
                    logger.info(f"Sent '{preset_object.name}' to register {index}.")
                    asyncio.run_coroutine_threadsafe(self._broadcast_feedback("success", f"Saved '{preset_object.name}' to Register {index}"), self.loop)
                    self._save_presets_to_file()
                else: logger.error(f"Failed SysEx generation for saving '{preset_object.name}'."); asyncio.run_coroutine_threadsafe(self._broadcast_error("internal", "SysEx gen failed"), self.loop)
            except MIDIError as e: logger.error(f"MIDIError saving '{preset_object.name}': {e}")
            except Exception as e: logger.exception(f"Error saving '{preset_object.name}'"); asyncio.run_coroutine_threadsafe(self._broadcast_error("internal", f"Error saving: {e}"), self.loop)

    # --- Modulation Matrix Methods (Placeholders) ---
    def send_mod_route_update(self, route_id: Any, source: int, destination: int, amount: int, enabled: bool):
        """Sends an update for a specific modulation route."""
        # TODO: Map source/destination names/IDs to actual MIDI values
        # TODO: Implement actual SysEx/NRPN command when known
        logger.info(f"Received Mod Route Update: ID={route_id}, Src={source}, Dest={destination}, Amt={amount}, En={enabled} (Placeholder - MIDI command unknown)")
        asyncio.run_coroutine_threadsafe(self._broadcast_feedback("warning", "Mod matrix update not implemented"), self.loop)

    # --- Time Code Automation Methods (Placeholders) ---
    def request_time_code_events(self):
        """Requests the current Time Code Event List from the M300L."""
        logger.info("Requesting Time Code Events (Placeholder - MIDI command unknown)")
        # TODO: Implement SysEx request for Time Code Event List
        asyncio.run_coroutine_threadsafe(self._broadcast_feedback("warning", "Time Code event request not implemented"), self.loop)

    def add_time_code_event(self, event_data: Dict[str, Any]):
        """Adds a new Time Code event."""
        logger.info(f"Received Add Time Code Event request: {event_data} (Placeholder - MIDI command unknown)")
        # TODO: Implement SysEx/NRPN command to add event
        asyncio.run_coroutine_threadsafe(self._broadcast_feedback("warning", "Add Time Code event not implemented"), self.loop)

    def update_time_code_event(self, event_id: Any, updates: Dict[str, Any]):
        """Updates an existing Time Code event."""
        logger.info(f"Received Update Time Code Event request: ID={event_id}, Updates={updates} (Placeholder - MIDI command unknown)")
        # TODO: Implement SysEx/NRPN command to update event
        asyncio.run_coroutine_threadsafe(self._broadcast_feedback("warning", "Update Time Code event not implemented"), self.loop)

    def delete_time_code_event(self, event_id: Any):
        """Deletes a Time Code event."""
        logger.info(f"Received Delete Time Code Event request: ID={event_id} (Placeholder - MIDI command unknown)")
        # TODO: Implement SysEx/NRPN command to delete event
        asyncio.run_coroutine_threadsafe(self._broadcast_feedback("warning", "Delete Time Code event not implemented"), self.loop)

    # --- Parameter Handling ---
    async def send_parameter_change(self, domain: int, param: int, value: int, source: str = 'unknown') -> bool:
        """Sends a parameter change via SysEx or NRPN."""
        logger.info(f"Sending Param Change: Domain={domain}, Param={param}, Value={value}, Source={source}")
        try:
            sysex_msg = self._create_parameter_sysex(domain, param, value)
            self._send_hw_message(sysex_msg)
            if source != 'websocket': # Update state if change didn't come from UI
                 changed = self._update_parameter_state(domain, param, value)
                 if changed: await self._broadcast_update({"type": "parameter_change", "payload": {"domain": domain, "param": param, "value": value}})
            return True
        except (MIDIError, ValueError) as e:
            logger.error(f"Failed to send parameter change ({domain},{param},{value}): {e}")
            if isinstance(e, ValueError): await self._broadcast_error("internal", f"Param change error: {e}")
            return False
        except Exception as e:
             logger.exception(f"Unexpected error sending parameter change ({domain},{param},{value})")
             await self._broadcast_error("internal", f"Unexpected param change error: {e}")
             return False

    # --- MIDI Input Handling ---
    async def request_active_state(self):
        """Request the active setup and effects from the M300."""
        if not self._midi_connected or not self.midi_out: logger.warning("Cannot request active state: MIDI not connected."); return
        logger.info("Requesting active state from M300...")
        try:
            self._send_request(REQ_ACTIVE_SETUP); await asyncio.sleep(MIDI_RETRY_DELAY)
            self._send_request(REQ_ACTIVE_EFFECT_A); await asyncio.sleep(MIDI_RETRY_DELAY)
            self._send_request(REQ_ACTIVE_EFFECT_B); self.diagnostics.record_message(count=3)
            logger.debug("Active state request messages sent.")
        except Exception as e:
            self.diagnostics.record_error(); self.error_tracker.add_error("request_active_state", str(e))
            logger.error(f"Error requesting active state: {e}", exc_info=True)

    def _start_monitoring(self): self._monitor_task = self.loop.create_task(self._monitor_system())
    def _start_command_processor(self): self._command_processor_task = self.loop.create_task(self._process_command_queue())

    async def _monitor_system(self):
        """Monitor system and MIDI metrics."""
        try:
            while True:
                self.diagnostics.collect_system_metrics()
                self.diagnostics.collect_midi_metrics(self.command_queue.qsize())
                if self.diagnostics.should_throttle(): self._handle_throttling() # Call synchronous method
                await asyncio.sleep(1)
        except asyncio.CancelledError: logger.info("System monitor task cancelled.")
        except Exception: logger.exception("Error in system monitor task")

    def _handle_throttling(self): # Made synchronous
        """Handle system throttling."""
        logger.warning("System under heavy load, throttling MIDI messages")
        time.sleep(0.1) # Use time.sleep
        if self.command_queue.qsize() > 100:
            logger.warning(f"Cmd queue size ({self.command_queue.qsize()}) > 100, clearing non-critical.")
            new_queue = asyncio.Queue()
            while not self.command_queue.empty():
                try:
                    item = self.command_queue.get_nowait() # Use get_nowait
                    if isinstance(item, dict) and item.get("type") in ["parameter_change", "request_active_state"]:
                        new_queue.put_nowait(item) # Use put_nowait
                    self.command_queue.task_done()
                except asyncio.QueueEmpty: break # Exit if queue becomes empty
            self.command_queue = new_queue

    async def _process_command_queue(self):
        """Process incoming MIDI messages from the queue."""
        logger.info("Starting MIDI command processor task.")
        try:
            while True:
                item = await self.command_queue.get()
                try:
                    if isinstance(item, dict) and item.get("type") == "midi_in":
                        message = item.get("payload")
                        if message: await self.process_midi_message(message)
                    else: logger.warning(f"Unknown item type in command queue: {item}")
                except Exception as e: logger.exception(f"Error processing command queue item: {item}")
                finally: self.command_queue.task_done()
        except asyncio.CancelledError: logger.info("Command processor task cancelled.")
        except Exception: logger.exception("Command processor task failed unexpectedly.")

    async def process_midi_message(self, message: Tuple[int, ...]):
        """Process a MIDI message."""
        try:
            self.diagnostics.record_message()
            if message[0] == SYSEX_START: await self._handle_sysex(message)
            elif (message[0] & 0xF0) == 0xB0: await self._handle_cc(message[1], message[2])
        except Exception as e:
            self.diagnostics.record_error(); self.error_tracker.add_error("midi_processing", str(e))
            logger.exception("Error processing MIDI message"); await self._broadcast_error("midi_processing", f"Error processing MIDI: {e}", str(message))

    async def _handle_sysex(self, message: Tuple[int, ...]):
        """Handle incoming SysEx messages."""
        if not is_m300_sysex(message): logger.debug(f"Ignoring non-M300 SysEx: {message[:5]}..."); return
        parsed_data = parse_m300_sysex_detailed(message)
        if parsed_data.get("error"): logger.error(f"SysEx Parsing Error: {parsed_data['error']} - {message}"); await self._broadcast_error("midi_parse", parsed_data['error'], str(message)); return
        if parsed_data.get("warning"): logger.warning(f"SysEx Parsing Warning: {parsed_data['warning']} - {message}")
        msg_class = parsed_data.get("message_class_raw")
        if msg_class == CLASS_ACTIVE_BULK or msg_class == CLASS_STORED_BULK: await self._handle_bulk_data(parsed_data)
        elif msg_class == CLASS_PARAMETER: await self._handle_parameter_data(parsed_data)
        else: logger.debug(f"Received unhandled SysEx class: {msg_class}")

    async def _handle_bulk_data(self, parsed_data: Dict[str, Any]):
        logger.debug(f"Processing parsed bulk data: {parsed_data}") # Log incoming parsed data
        """Process parsed bulk data (Active or Stored Presets/Effects)."""
        logger.info(f"Handling Bulk Data: {parsed_data.get('preset_type_str', 'Unknown Type')}")
        preset_class_name = parsed_data.get("preset_class_name"); unnibblized_data = parsed_data.get("unnibblized_data")
        index = parsed_data.get("index"); checksum_ok = parsed_data.get("checksum_raw") == parsed_data.get("checksum_calculated")
        if not preset_class_name or unnibblized_data is None or index is None: logger.error("Incomplete bulk data."); await self._broadcast_error("bulk_data", "Incomplete bulk data", str(parsed_data)); return
        if not checksum_ok: logger.warning(f"Checksum mismatch! Raw: {parsed_data.get('checksum_raw')}, Calc: {parsed_data.get('checksum_calculated')}")
        PresetClass = PRESET_CLASS_MAP.get(preset_class_name)
        if not PresetClass: logger.error(f"Unknown preset class: {preset_class_name}"); await self._broadcast_error("bulk_data", f"Unknown preset class: {preset_class_name}"); return
        try:
            preset_obj = PresetClass(); preset_obj.parse_bytes(unnibblized_data)
            msg_class = parsed_data.get("message_class_raw"); type_byte = parsed_data.get("type_byte_raw"); update_type = "unknown_bulk"
            if msg_class == CLASS_ACTIVE_BULK:
                if type_byte == TYPE_ACTIVE_SETUP_V3: self.active_setup = preset_obj; update_type = "active_setup"
                elif type_byte == TYPE_ACTIVE_EFFECT_A_V3: self.active_effect_a = preset_obj; update_type = "active_effect_a"
                elif type_byte == TYPE_ACTIVE_EFFECT_B_V3: self.active_effect_b = preset_obj; update_type = "active_effect_b"
            elif msg_class == CLASS_STORED_BULK:
                if type_byte == TYPE_STORED_SETUP_V3: self.stored_setups[index] = preset_obj; update_type = "stored_setup"
                elif type_byte == TYPE_STORED_EFFECT_V3: self.stored_effects[index] = preset_obj; update_type = "stored_effect"
            logger.info(f"Processed: {preset_obj.name} ({update_type}, Index: {index if msg_class == CLASS_STORED_BULK else 'N/A'})")
            await self._broadcast_update({"type": update_type, "payload": preset_obj.to_dict(), "index": index if msg_class == CLASS_STORED_BULK else None})
        except Exception as e: logger.exception(f"Error processing bulk data object: {preset_class_name}"); await self._broadcast_error("bulk_data", f"Error processing preset: {e}")
        finally:
             if preset_class_name and unnibblized_data is not None and index is not None: self._save_presets_to_file()

    async def _handle_parameter_data(self, parsed_data: Dict[str, Any]):
        logger.debug(f"Processing parsed parameter data: {parsed_data}") # Log incoming parsed data
        """Process parsed parameter data."""
        domain = parsed_data.get("param_domain"); param_num = parsed_data.get("param_number"); value = parsed_data.get("param_value")
        if domain is None or param_num is None or value is None: logger.error("Incomplete parameter data."); await self._broadcast_error("param_data", "Incomplete parameter data", str(parsed_data)); return
        logger.debug(f"Received Parameter Update: Domain={domain}, Param={param_num}, Value={value}")
        changed = self._update_parameter_state(domain, param_num, value)
        if changed: await self._broadcast_update({"type": "parameter_change", "payload": {"domain": domain, "param": param_num, "value": value}})

    async def _handle_cc(self, cc_number: int, cc_value: int):
        """Handle incoming CC messages (potentially NRPN)."""
        logger.debug(f"Received CC: Num={cc_number}, Val={cc_value}")
        nrpn_data = self.nrpn_parser.process_cc(cc_number, cc_value)
        if nrpn_data:
             domain = nrpn_data["nrpn_domain"]; param = nrpn_data["nrpn_param_number"]; value = nrpn_data["nrpn_value"]
             logger.info(f"Received NRPN: Domain={domain}, Param={param}, Value={value}")
             changed = self._update_parameter_state(domain, param, value)
             if changed: await self._broadcast_update({"type": "parameter_change", "payload": {"domain": domain, "param": param, "value": value}})

    # --- Broadcasting Methods ---
    async def _broadcast_error(self, source: str, message: str, details: Optional[str] = None):
        logger.error(f"Broadcasting Error ({source}): {message} {details or ''}")
        error_payload = {"type": "error", "payload": {"source": source, "message": message, "details": details}}
        message_json = json.dumps(error_payload)
        if self.connected_clients: await asyncio.gather(*[client.send(message_json) for client in self.connected_clients], return_exceptions=True)

    async def _broadcast_status(self):
        logger.info(f"Broadcasting Status - MIDI Connected: {self._midi_connected}")
        status_payload = {"type": "midi_status", "payload": {"connected": self._midi_connected, "in_port": self.midi_in_port_name, "out_port": self.midi_out_port_name}}
        message_json = json.dumps(status_payload)
        if self.connected_clients: await asyncio.gather(*[client.send(message_json) for client in self.connected_clients], return_exceptions=True)

    async def _broadcast_feedback(self, level: str, message: str, duration: int = 3000):
        logger.info(f"Broadcasting Feedback ({level}): {message}")
        feedback_payload = {"type": "feedback", "payload": {"level": level, "message": message, "duration": duration}}
        message_json = json.dumps(feedback_payload)
        if self.connected_clients:
            results = await asyncio.gather(*[client.send(message_json) for client in self.connected_clients], return_exceptions=True)
            for res, client in zip(results, list(self.connected_clients)):
                 if isinstance(res, Exception): logger.error(f"Failed to send feedback to client {client.remote_address}: {res}")

    async def _broadcast_update(self, data: Dict[str, Any]):
        log_level = logging.DEBUG if data.get("type") == "parameter_change" else logging.INFO
        logger.log(log_level, f"Broadcasting Update: Type={data.get('type')}, Index={data.get('index', 'N/A')}, PayloadKeys={list(data.get('payload', {}).keys())}")
        message_json = json.dumps(data)
        if self.connected_clients:
            results = await asyncio.gather(*[client.send(message_json) for client in self.connected_clients], return_exceptions=True)
            for res, client in zip(results, list(self.connected_clients)):
                 if isinstance(res, Exception): logger.error(f"Failed to send update to client {client.remote_address}: {res}")

    # --- MIDI Connection Handling ---
    def connect_midi(self):
        """Connects to the specified MIDI ports."""
        if rtmidi is None: logger.error("Cannot connect MIDI: python-rtmidi not found."); self._midi_connected = False; asyncio.run_coroutine_threadsafe(self._broadcast_status(), self.loop); return
        logger.info(f"Attempting to connect MIDI ports: IN='{self.midi_in_port_name}', OUT='{self.midi_out_port_name}'")
        self.close_midi()
        if not self.midi_in_port_name or not self.midi_out_port_name: logger.warning("MIDI port names not specified."); self._midi_connected = False; asyncio.run_coroutine_threadsafe(self._broadcast_status(), self.loop); return
        try:
            self.midi_out = rtmidi.MidiOut(); available_outs = self.midi_out.get_ports()
            if self.midi_out_port_name in available_outs: self.midi_out.open_port(available_outs.index(self.midi_out_port_name)); logger.info(f"MIDI Output Port '{self.midi_out_port_name}' opened.")
            else: logger.error(f"MIDI Output Port '{self.midi_out_port_name}' not found. Available: {available_outs}"); self.close_midi(); asyncio.run_coroutine_threadsafe(self._broadcast_error("midi", f"Output port not found: {self.midi_out_port_name}"), self.loop); asyncio.run_coroutine_threadsafe(self._broadcast_status(), self.loop); return
            self.midi_in = rtmidi.MidiIn(); available_ins = self.midi_in.get_ports()
            if self.midi_in_port_name in available_ins:
                self.midi_in.open_port(available_ins.index(self.midi_in_port_name)); self.midi_in.set_callback(self._midi_callback)
                self.midi_in.ignore_types(sysex=False, timing=True, active_sense=True); logger.info(f"MIDI Input Port '{self.midi_in_port_name}' opened.")
            else: logger.error(f"MIDI Input Port '{self.midi_in_port_name}' not found. Available: {available_ins}"); self.close_midi(); asyncio.run_coroutine_threadsafe(self._broadcast_error("midi", f"Input port not found: {self.midi_in_port_name}"), self.loop); asyncio.run_coroutine_threadsafe(self._broadcast_status(), self.loop); return
            self._midi_connected = True; logger.info("MIDI Connection Successful.")
            asyncio.run_coroutine_threadsafe(self.request_active_state(), self.loop)
            # Request all stored presets after connection to populate state
            logger.info("Requesting all stored presets after connection...")
            asyncio.run_coroutine_threadsafe(self.request_all_stored_setups(), self.loop)
            # Add a small delay before requesting effects to avoid overwhelming the M300L
            self.loop.call_later(0.2, lambda: asyncio.run_coroutine_threadsafe(self.request_all_stored_effects(), self.loop))
        except rtmidi.SystemError as e: logger.exception("rtmidi SystemError"); self.close_midi(); self._midi_connected = False; asyncio.run_coroutine_threadsafe(self._broadcast_error("midi", f"MIDI SystemError: {e}"), self.loop)
        except Exception as e: logger.exception("Failed to connect MIDI"); self.close_midi(); self._midi_connected = False; asyncio.run_coroutine_threadsafe(self._broadcast_error("midi", f"MIDI Connection Error: {e}"), self.loop)
        finally: asyncio.run_coroutine_threadsafe(self._broadcast_status(), self.loop)

    def _midi_callback(self, event, data=None):
        """Callback function for incoming MIDI messages."""
        message, deltatime = event
        self.loop.call_soon_threadsafe(self.command_queue.put_nowait, {"type": "midi_in", "payload": tuple(message)})

    async def stop(self):
        """Stop controller and cleanup."""
        logger.info("Stopping M300 Controller...")
        if self._monitor_task: self._monitor_task.cancel(); await asyncio.gather(self._monitor_task, return_exceptions=True)
        if self._command_processor_task: self._command_processor_task.cancel(); await asyncio.gather(self._command_processor_task, return_exceptions=True)
        self.close_midi()
        self.command_queue = asyncio.Queue()
        self._message_queue.clear()
        self._midi_connected = False
        logger.info("M300 Controller stopped.")

    def close_midi(self):
        """Close MIDI ports."""
        if self.midi_in:
            try: self.midi_in.close_port(); logger.debug("MIDI Input closed.")
            except Exception as e: logger.error(f"Error closing MIDI Input: {e}")
            del self.midi_in; self.midi_in = None
        if self.midi_out:
            try: self.midi_out.close_port(); logger.debug("MIDI Output closed.")
            except Exception as e: logger.error(f"Error closing MIDI Output: {e}")
            del self.midi_out; self.midi_out = None
        if self._midi_connected: self._midi_connected = False

    # --- Preset Persistence ---
    def _load_presets_from_file(self):
        """Loads user preset state from the JSON file."""
        logger.info(f"Attempting to load user presets from {PRESETS_FILE}...")
        try:
            with open(PRESETS_FILE, 'r') as f: data = json.load(f)
            if data.get("active_setup"): self.active_setup = SetupPresetV3.from_dict(data["active_setup"]); logger.info(f"Loaded active setup: {self.active_setup.name}")
            if data.get("active_effect_a"): self.active_effect_a = EffectPresetV3.from_dict(data["active_effect_a"]); logger.info(f"Loaded active effect A: {self.active_effect_a.name}")
            if data.get("active_effect_b"): self.active_effect_b = EffectPresetV3.from_dict(data["active_effect_b"]); logger.info(f"Loaded active effect B: {self.active_effect_b.name}")
            loaded_setups = 0
            for index_str, setup_data in data.get("stored_setups", {}).items():
                try: index = int(index_str); self.stored_setups[index] = SetupPresetV3.from_dict(setup_data); loaded_setups += 1
                except (ValueError, TypeError) as e: logger.warning(f"Skipping invalid stored setup at index '{index_str}': {e}")
            if loaded_setups > 0: logger.info(f"Loaded {loaded_setups} stored setups.")
            loaded_effects = 0
            for index_str, effect_data in data.get("stored_effects", {}).items():
                 try: index = int(index_str); self.stored_effects[index] = EffectPresetV3.from_dict(effect_data); loaded_effects += 1
                 except (ValueError, TypeError) as e: logger.warning(f"Skipping invalid stored effect at index '{index_str}': {e}")
            if loaded_effects > 0: logger.info(f"Loaded {loaded_effects} stored effects.")
        except FileNotFoundError: logger.info(f"{PRESETS_FILE} not found.")
        except json.JSONDecodeError: logger.error(f"Error decoding JSON from {PRESETS_FILE}.")
        except Exception as e: logger.exception(f"Error loading presets from {PRESETS_FILE}")

    def _save_presets_to_file(self):
        """Saves the current user preset state to the JSON file."""
        logger.debug(f"Saving user presets to {PRESETS_FILE}...")
        state_to_save = {
            "active_setup": self.active_setup.to_dict() if self.active_setup else None,
            "active_effect_a": self.active_effect_a.to_dict() if self.active_effect_a else None,
            "active_effect_b": self.active_effect_b.to_dict() if self.active_effect_b else None,
            "stored_setups": {str(k): v.to_dict() for k, v in self.stored_setups.items()},
            "stored_effects": {str(k): v.to_dict() for k, v in self.stored_effects.items()},
        }
        try:
            with open(PRESETS_FILE, 'w') as f: json.dump(state_to_save, f, indent=4)
            logger.debug(f"Successfully saved user presets to {PRESETS_FILE}")
        except Exception as e: logger.exception(f"Error saving presets to {PRESETS_FILE}")

    def _load_factory_presets(self):
        """Loads factory presets definitions from the JSON file."""
        logger.info(f"Attempting to load factory presets from {FACTORY_PRESETS_FILE}...")
        try:
            with open(FACTORY_PRESETS_FILE, 'r') as f:
                self.factory_preset_data = json.load(f) # Store raw list of dicts
            if not isinstance(self.factory_preset_data, list):
                logger.error(f"Invalid format in {FACTORY_PRESETS_FILE}: Expected list."); self.factory_preset_data = []
                return
            logger.info(f"Loaded {len(self.factory_preset_data)} factory preset definitions.")
        except FileNotFoundError: logger.warning(f"{FACTORY_PRESETS_FILE} not found."); self.factory_preset_data = []
        except json.JSONDecodeError: logger.error(f"Error decoding JSON from {FACTORY_PRESETS_FILE}."); self.factory_preset_data = []
        except Exception as e: logger.exception(f"Error loading factory presets from {FACTORY_PRESETS_FILE}"); self.factory_preset_data = []

    def get_all_presets(self) -> List[Dict[str, Any]]:
        """Combines factory, stored setup, and stored effect presets into a single list for the frontend."""
        combined_presets = []
        # Add Factory Presets
        for preset_info in self.factory_preset_data:
            if isinstance(preset_info, dict) and 'id' in preset_info:
                 combined_presets.append({
                    "id": preset_info.get('id'), "name": preset_info.get('name', 'Unknown Factory'),
                    "type": preset_info.get('type', 'Unknown'), "tags": preset_info.get('tags', []),
                    "author": preset_info.get('author', 'Factory'), "description": preset_info.get('description', ''),
                    "source": "factory" })
            else: logger.warning(f"Skipping invalid factory preset data entry: {preset_info}")
        # Add Stored Setups
        for index, preset_obj in self.stored_setups.items():
            combined_presets.append({
                "id": index, "name": preset_obj.name, "type": "Setup",
                "tags": getattr(preset_obj, 'tags', []), "author": getattr(preset_obj, 'author', 'User'),
                "description": getattr(preset_obj, 'description', ''), "source": "user" })
        # Add Stored Effects
        for index, preset_obj in self.stored_effects.items():
             combined_presets.append({
                "id": index, "name": preset_obj.name, "type": "Effect",
                "tags": getattr(preset_obj, 'tags', []), "author": getattr(preset_obj, 'author', 'User'),
                "description": getattr(preset_obj, 'description', ''), "source": "user" })
        logger.info(f"Returning combined list of {len(combined_presets)} presets.")
        return combined_presets
