import pytest
from midi.models import SetupPresetV3, EffectPresetV3, ALGORITHM_ID_TO_NAME_V3
from tests.test_midi_utils import SETUP_V3_BYTES, EFFECT_V3_BYTES # Import test data


# --- Test Data ---

# Test data moved to tests/test_midi_utils.py
# Remnants removed


# --- Tests ---

def test_setup_v3_parse_bytes():
    preset = SetupPresetV3()
    preset.parse_bytes(SETUP_V3_BYTES)

    assert preset.name == "Test Setup"
    assert preset.effect_a_num == 101
    assert preset.effect_b_num == 0
    assert preset.machine_config == 0
    assert preset.lfo_shape == 0
    assert preset.left_meter_assign == 0
    assert preset.right_meter_assign == 0
    assert preset.softknob == 64
    assert preset.lfo_rate == 0 # Based on current parse logic
    assert preset.io_level1 == 0
    assert preset.io_level2 == 64
    assert preset.io_level3 == 0
    assert preset.io_level4 == 64
    assert preset.io_level5 == 127
    assert preset.io_level6 == 0
    assert preset.patch1_src == 65
    assert preset.patch1_dest == 2
    assert preset.patch1_scale == 1000
    assert preset.patch1_thresh == 0
    assert preset.patch2_src == 66
    assert preset.patch2_dest == 0
    assert preset.patch2_scale == 500
    assert preset.patch2_thresh == 64

def test_effect_v3_parse_bytes():
    preset = EffectPresetV3()
    preset.parse_bytes(EFFECT_V3_BYTES)

    assert preset.name == "Test Effect"
    assert preset.algorithm == ALGORITHM_ID_TO_NAME_V3[0] # Random Hall
    # Check specific parameters based on updated EFFECT_V3_BYTES
    assert preset.size == 50
    assert preset.rtim == 80
    assert preset.pdly == 100
    assert preset.link == 0 # Check the value parsed from the test data (param_bytes[9*2] is 0)
    # e.g., assert preset.rtim == expected_value_from_test_data

def test_effect_v3_parse_bytes_short_data():
     preset = EffectPresetV3()
     short_data = EFFECT_V3_BYTES[:50] # Less than minimum required
     # Should log a warning but not raise an error ideally
     preset.parse_bytes(short_data)
     # Assert that the preset remains mostly default
     assert preset.name == "Untitled" # Name parsing might fail or be partial
     assert preset.algorithm == "Random Hall" # Default algo

def test_setup_v3_parse_bytes_short_data():
     preset = SetupPresetV3()
     short_data = SETUP_V3_BYTES[:20] # Less than minimum required
     preset.parse_bytes(short_data)
     assert preset.name == "Untitled"
     assert preset.effect_a_num == 101 # Default

# --- Serialization Tests ---

def test_setup_v3_to_bytes():
    preset = SetupPresetV3(name="Test Setup")
    # Modify some defaults if needed for a more robust test
    preset.softknob = 100
    preset.effect_b_num = 5

    byte_data = preset.to_bytes()
    assert isinstance(byte_data, bytes)
    assert len(byte_data) == 36

    # Check key fields
    assert byte_data[0:10] == b'Test Setup'
    assert byte_data[12] == 0 # Null terminator
    assert byte_data[13] == 101 # Default Effect A
    assert byte_data[14] == 5   # Modified Effect B
    assert byte_data[16] == 100 # Modified Softknob

def test_effect_v3_to_bytes():
    preset = EffectPresetV3(name="Test Effect")
    preset.algorithm = "Plate" # Change algorithm
    preset.size = 60
    preset.rtim = 90

    byte_data = preset.to_bytes()
    assert isinstance(byte_data, bytes)
    assert len(byte_data) == 102

    # Check key fields
    assert byte_data[0:11] == b'Test Effect'
    assert byte_data[12] == 0 # Null terminator
    assert byte_data[13] == 2 # Algorithm ID for Plate

    # Check parameter bytes (using param map for Plate)
    # Param 0 (size): Value 60 (0x003C)
    assert byte_data[14] == 0x00
    assert byte_data[15] == 0x3C
    # Param 2 (rtim): Value 90 (0x005A)
    assert byte_data[14 + 2*2] == 0x00
    assert byte_data[14 + 2*2 + 1] == 0x5A