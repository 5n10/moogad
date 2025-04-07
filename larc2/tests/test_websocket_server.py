import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock # Import AsyncMock
import json # Import json
from websockets.legacy.server import WebSocketServerProtocol # Import for mocking client
from server.websocket_server import WebSocketServer, ConnectionState, list_midi_ports
from midi.m300_controller import M300Controller, EffectPresetV3 # Import for mocking controller and preset class

@pytest.fixture
async def server(event_loop): # Use the event_loop fixture provided by pytest-asyncio
    """Pytest fixture providing a mocked WebSocketServer instance."""
    # Patch M300Controller for isolated testing
    with patch('server.websocket_server.M300Controller', new_callable=MagicMock) as MockController:
        mock_controller_inst = MockController.return_value
        # Set up default mock behaviors needed by the server
        mock_controller_inst._midi_connected = False # Start disconnected
        mock_controller_inst.get_full_state.return_value = {"midi_connected": False, "param_values": {}}
        mock_controller_inst.get_all_presets.return_value = []
        mock_controller_inst.connect_midi = MagicMock() # Mock connect method
        mock_controller_inst.stop = AsyncMock() # Mock async stop method

        server_inst = WebSocketServer(host="localhost", port=8766) # Provide host as well
        server_inst.m300 = mock_controller_inst # Manually assign mocked controller

        # Mock the background tasks if they interfere
        server_inst._health_check_task = MagicMock()
        server_inst._state_update_task = MagicMock() # Assuming this exists or might be added

        yield server_inst # Provide the instance to the test

        # Teardown: Explicitly call mocked stop if needed, though usually not necessary for unit tests
        # await server_inst.stop() # Call the mocked stop
    # Removed incorrect await server.stop() - teardown handled by context manager

@pytest.mark.asyncio
async def test_server_initialization():
    """Test basic server initialization."""
    server = WebSocketServer(port=8766)
    assert server.port == 8766
    assert isinstance(server, WebSocketServer)

@pytest.mark.asyncio
async def test_connection_state_transitions(server: WebSocketServer):
    """Test connection state transitions."""
    # Fixture now yields the server instance directly
    assert isinstance(server, WebSocketServer)
    # Test state transitions using the actual set_state method
    # Initial state should be DISCONNECTED (set in __init__)
    assert server.connection_state == ConnectionState.DISCONNECTED

    await server.set_state(ConnectionState.CONNECTING)
    assert server.connection_state == ConnectionState.CONNECTING

    await server.set_state(ConnectionState.CONNECTED)
    assert server.connection_state == ConnectionState.CONNECTED

    await server.set_state(ConnectionState.ERROR)
    assert server.connection_state == ConnectionState.ERROR

    await server.set_state(ConnectionState.DISCONNECTED)
    assert server.connection_state == ConnectionState.DISCONNECTED

# --- process_message Tests ---

@pytest.mark.asyncio
async def test_process_message_parameter_change(server: WebSocketServer):
    """Test handling of 'parameter_change' message."""
    mock_websocket = AsyncMock(spec=WebSocketServerProtocol) # Use AsyncMock for awaitable methods like send
    mock_controller = server.m300 # Get the mocked controller from the fixture
    assert mock_controller is not None

    test_payload = {"domain": 3, "param": 5, "value": 100}
    message_data = {"type": "parameter_change", "payload": test_payload}

    # Patch asyncio.create_task to check if it's called correctly
    with patch('asyncio.create_task') as mock_create_task:
        await server.process_message(mock_websocket, message_data)
        # Assert that create_task was called, indicating the controller method was scheduled
        mock_create_task.assert_called_once()
        # More specific check: Ensure the correct controller method was scheduled
        # This requires inspecting the coroutine passed to create_task, which can be complex.
        # For now, checking if create_task was called is a basic verification.
        # Alternatively, make send_parameter_change synchronous for easier mocking/testing if feasible.

@pytest.mark.asyncio
async def test_process_message_save_preset(server: WebSocketServer):
    """Test handling of 'save_preset' message."""
    mock_websocket = AsyncMock(spec=WebSocketServerProtocol)
    mock_controller = server.m300
    assert mock_controller is not None

    test_payload = {"preset_data": {"name": "My Preset"}, "index": 10, "preset_type": "effect"}
    message_data = {"type": "save_preset", "payload": test_payload}

    with patch('asyncio.create_task') as mock_create_task:
         # Mock from_dict on the class itself if needed
         with patch('server.websocket_server.EffectPresetV3.from_dict') as mock_from_dict:
              mock_preset_obj = MagicMock()
              mock_from_dict.return_value = mock_preset_obj
              await server.process_message(mock_websocket, message_data)
              mock_from_dict.assert_called_once_with(test_payload["preset_data"])
              mock_create_task.assert_called_once() # Check if save_preset_to_register was scheduled

@pytest.mark.asyncio
async def test_process_message_load_preset(server: WebSocketServer):
    """Test handling of 'load_preset' message."""
    mock_websocket = AsyncMock(spec=WebSocketServerProtocol)
    mock_controller = server.m300
    assert mock_controller is not None
    # Mock controller state for testing lookup
    mock_preset = MagicMock()
    mock_controller.stored_effects = {5: mock_preset} # Example stored effect

    test_payload = {"id": 5, "kind": "effect", "slot": "A"}
    message_data = {"type": "load_preset", "payload": test_payload}

    with patch('asyncio.create_task') as mock_create_task:
        await server.process_message(mock_websocket, message_data)
        mock_create_task.assert_called_once() # Check if send_preset_to_active was scheduled

@pytest.mark.asyncio
async def test_process_message_get_midi_ports(server: WebSocketServer):
    """Test handling of 'get_midi_ports' message."""
    mock_websocket = AsyncMock(spec=WebSocketServerProtocol)
    test_ports = {'in': [{'system_name': 'In1', 'display_name': 'Input 1'}], 'out': [{'system_name': 'Out1', 'display_name': 'Output 1'}]}

    # Patch the list_midi_ports function used by the handler
    with patch('server.websocket_server.list_midi_ports', return_value=test_ports) as mock_list_ports:
        message_data = {"type": "get_midi_ports"}
        await server.process_message(mock_websocket, message_data)
        mock_list_ports.assert_called_once_with(server.port_aliases)
        # Check if the correct message was sent back
        expected_response = {"type": "midi_ports", "payload": {"ports": {"inputs": test_ports['in'], "outputs": test_ports['out']}}} # Correct keys
        mock_websocket.send.assert_called_once_with(json.dumps(expected_response))

@pytest.mark.asyncio
async def test_process_message_connect_midi(server: WebSocketServer):
    """Test handling of 'connect_midi' message."""
    mock_websocket = AsyncMock(spec=WebSocketServerProtocol)
    mock_controller = server.m300
    assert mock_controller is not None

    test_payload = {"input_port": "In1", "output_port": "Out1"}
    message_data = {"type": "connect_midi", "payload": test_payload}

    await server.process_message(mock_websocket, message_data)
    # Check if controller attributes were set and connect_midi was called
    assert mock_controller.midi_in_port_name == "In1"
    assert mock_controller.midi_out_port_name == "Out1"
    mock_controller.connect_midi.assert_called_once()

@pytest.mark.asyncio
async def test_process_message_unknown_type(server: WebSocketServer):
    """Test handling of an unknown message type."""
    mock_websocket = AsyncMock(spec=WebSocketServerProtocol)
    message_data = {"type": "unknown_command", "payload": {}}
    await server.process_message(mock_websocket, message_data)
    # Check if an error message was sent back
    args, _ = mock_websocket.send.call_args
    response_data = json.loads(args[0])
    assert response_data["type"] == "error"
    assert "Unknown command type" in response_data["payload"]["message"]
