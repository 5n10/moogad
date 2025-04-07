import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

# Modules to test
from midi.m300_controller import M300Controller, MIDIError
from midi.models import EffectPresetV3, SetupPresetV3

# Mock rtmidi if not available
try:
    import rtmidi
except ImportError:
    rtmidi = MagicMock()

# Removed custom event_loop fixture - rely on pytest-asyncio default

@pytest.fixture
def controller(): # Remove event_loop argument
    """Fixture for creating an M300Controller instance with mocked dependencies."""
    # Patch dependencies that would interact with hardware or external systems
    with patch('midi.m300_controller.rtmidi', rtmidi), \
         patch('midi.m300_controller.generate_request', return_value=(0xF0, 0x01, 0xF7)) as mock_gen_req, \
         patch('midi.m300_controller.generate_bulk_sysex', return_value=(0xF0, 0x02, 0xF7)) as mock_gen_bulk, \
         patch.object(M300Controller, '_send_hw_message', return_value=None) as mock_send_hw, \
         patch.object(M300Controller, '_broadcast_error', new_callable=AsyncMock) as mock_bcast_err, \
         patch.object(M300Controller, '_broadcast_status', new_callable=AsyncMock) as mock_bcast_stat, \
         patch.object(M300Controller, '_broadcast_feedback', new_callable=AsyncMock) as mock_bcast_feed, \
         patch.object(M300Controller, '_broadcast_update', new_callable=AsyncMock) as mock_bcast_upd, \
         patch.object(M300Controller, '_load_presets_from_file', return_value=None), \
         patch.object(M300Controller, '_save_presets_to_file', return_value=None), \
         patch.object(M300Controller, '_load_factory_presets', return_value=None):

        # Get the loop provided by pytest-asyncio
        event_loop = asyncio.get_running_loop()
        # Create controller instance
        instance = M300Controller(loop=event_loop, midi_in_port_name="MockIn", midi_out_port_name="MockOut")
        # Manually set midi_out mock for _send_hw_message check
        instance.midi_out = MagicMock()
        instance._midi_connected = True # Assume connected for most tests

        # Store mocks for potential assertion in tests
        instance._mocks = {
            "gen_req": mock_gen_req, "gen_bulk": mock_gen_bulk, "send_hw": mock_send_hw,
            "bcast_err": mock_bcast_err, "bcast_stat": mock_bcast_stat,
            "bcast_feed": mock_bcast_feed, "bcast_upd": mock_bcast_upd
        }
        yield instance

# --- Tests ---

@pytest.mark.asyncio
async def test_send_parameter_change_success(controller: M300Controller):
    """Test successful parameter change sending."""
    domain, param, value = 3, 5, 1000
    expected_sysex = (0xF0, 0x06, 0x03, 0x20, 0x03, 0x05, 0x68, 0x07, 0xF7) # Example expected SysEx

    # Mock the sysex creation to check its output
    with patch.object(controller, '_create_parameter_sysex', return_value=expected_sysex) as mock_create:
        success = await controller.send_parameter_change(domain, param, value, source='test')

        assert success is True
        mock_create.assert_called_once_with(domain, param, value)
        controller._mocks["send_hw"].assert_called_once_with(expected_sysex)
        # Check if state was updated (since source != 'websocket')
        assert controller.get_parameter_value(domain, param) == value
        controller._mocks["bcast_upd"].assert_called_once()

@pytest.mark.asyncio
async def test_send_parameter_change_midi_error(controller: M300Controller):
    """Test parameter change sending when _send_hw_message fails."""
    controller._mocks["send_hw"].side_effect = MIDIError("Test MIDI Send Fail")
    success = await controller.send_parameter_change(3, 5, 1000)
    assert success is False
    controller._mocks["bcast_err"].assert_not_called() # Error broadcast happens in _send_hw_message mock

@pytest.mark.asyncio
async def test_send_parameter_change_value_error(controller: M300Controller):
    """Test parameter change sending with invalid value."""
    success = await controller.send_parameter_change(3, 5, 99999) # Value out of range
    assert success is False
    controller._mocks["send_hw"].assert_not_called()
    controller._mocks["bcast_err"].assert_called_once() # Should broadcast internal error

# TODO: Add tests for send_preset_to_active
# TODO: Add tests for save_preset_to_register
# TODO: Add tests for _handle_cc / NRPN parsing
# TODO: Add tests for request methods verifying _send_request calls
# TODO: Add tests for connect_midi and close_midi (mocking rtmidi more deeply)
# TODO: Add tests for _handle_cc / NRPN parsing
# TODO: Add tests for request methods verifying _send_request calls
# TODO: Add tests for connect_midi and close_midi (mocking rtmidi more deeply)
# TODO: Add tests for loading/saving presets to file

@pytest.mark.asyncio
async def test_send_preset_to_active_effect(controller: M300Controller):
    """Test sending an Effect preset to active slot A."""
    mock_preset = EffectPresetV3(name="Test Active Effect")
    slot = 'A'
    expected_bulk_type = 0x33 # TYPE_ACTIVE_EFFECT_A_V3
    expected_index = 0
    expected_sysex = (0xF0, 0x02, 0xF7) # From mock_gen_bulk

    controller.send_preset_to_active(mock_preset, slot=slot) # Call synchronously

    controller._mocks["gen_bulk"].assert_called_once_with(mock_preset, expected_bulk_type, expected_index, controller.midi_channel)
    controller._mocks["send_hw"].assert_called_once_with(expected_sysex)
    assert controller.active_effect_a == mock_preset
    controller._mocks["bcast_feed"].assert_called_once()
    controller._mocks["bcast_upd"].assert_called_once()
    # Check if save to file was called (added in controller logic)
    controller._mocks["_save_presets_to_file"].assert_called_once()


@pytest.mark.asyncio
async def test_send_preset_to_active_setup(controller: M300Controller):
    """Test sending a Setup preset to active."""
    mock_preset = SetupPresetV3(name="Test Active Setup")
    expected_bulk_type = 0x32 # TYPE_ACTIVE_SETUP_V3
    expected_index = 0
    expected_sysex = (0xF0, 0x02, 0xF7) # From mock_gen_bulk

    controller.send_preset_to_active(mock_preset) # Call synchronously

    controller._mocks["gen_bulk"].assert_called_once_with(mock_preset, expected_bulk_type, expected_index, controller.midi_channel)
    controller._mocks["send_hw"].assert_called_once_with(expected_sysex)
    assert controller.active_setup == mock_preset
    controller._mocks["bcast_feed"].assert_called_once()
    controller._mocks["bcast_upd"].assert_called_once()
    controller._mocks["_save_presets_to_file"].assert_called_once()


@pytest.mark.asyncio
async def test_save_preset_to_register_effect(controller: M300Controller):
    """Test saving an Effect preset to a register."""
    mock_preset = EffectPresetV3(name="Test Stored Effect")
    index = 15
    expected_bulk_type = 0x30 # TYPE_STORED_EFFECT_V3
    expected_sysex = (0xF0, 0x02, 0xF7) # From mock_gen_bulk

    controller.save_preset_to_register(mock_preset, index) # Call synchronously

    controller._mocks["gen_bulk"].assert_called_once_with(mock_preset, expected_bulk_type, index, controller.midi_channel)
    controller._mocks["send_hw"].assert_called_once_with(expected_sysex)
    assert controller.stored_effects[index] == mock_preset
    controller._mocks["bcast_feed"].assert_called_once()
    controller._mocks["_save_presets_to_file"].assert_called_once()


@pytest.mark.asyncio
async def test_save_preset_to_register_setup(controller: M300Controller):
    """Test saving a Setup preset to a register."""
    mock_preset = SetupPresetV3(name="Test Stored Setup")
    index = 22
    expected_bulk_type = 0x20 # TYPE_STORED_SETUP_V3
    expected_sysex = (0xF0, 0x02, 0xF7) # From mock_gen_bulk

    controller.save_preset_to_register(mock_preset, index) # Call synchronously

    controller._mocks["gen_bulk"].assert_called_once_with(mock_preset, expected_bulk_type, index, controller.midi_channel)
    controller._mocks["send_hw"].assert_called_once_with(expected_sysex)
    assert controller.stored_setups[index] == mock_preset
    controller._mocks["bcast_feed"].assert_called_once()
    controller._mocks["_save_presets_to_file"].assert_called_once()


@pytest.mark.asyncio
async def test_save_preset_invalid_index(controller: M300Controller):
    """Test saving preset with an invalid index."""
    mock_preset = EffectPresetV3(name="Test Invalid Index")
    index = 100 # Invalid index

    controller.save_preset_to_register(mock_preset, index) # Call synchronously

    controller._mocks["gen_bulk"].assert_not_called()
    controller._mocks["send_hw"].assert_not_called()
    controller._mocks["bcast_err"].assert_called_once()
    controller._mocks["_save_presets_to_file"].assert_not_called()