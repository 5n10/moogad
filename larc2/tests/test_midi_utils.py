import pytest
from midi.utils import (
    generate_sysex_header, generate_request, generate_bulk_sysex,
    calculate_checksum, nibblize_data, unnibblize_data,
    SYSEX_START, SYSEX_END, LEXICON_ID, M300_ID, CLASS_REQUEST, CLASS_PARAMETER,
    REQ_ACTIVE_SETUP, REQ_PARAM_VALUE, DOMAIN_EFFECT_A, EXPECTED_FLAG_BYTES,
    TYPE_ACTIVE_SETUP_V3, CLASS_ACTIVE_BULK,
    parse_m300_sysex_detailed # Add parser function
)
from midi.models import SetupPresetV3 # Import for type checking if needed

# --- Test Data (Moved from test_models) ---

# Example V3 Setup Data (36 bytes, unnibblized)
SETUP_V3_BYTES = (
    b'Test Setup\x00\x00\x00' + # Name (12 bytes)
    bytes([101 & 0x7F]) +      # Effect A Num (7-bit)
    bytes([0 & 0x7F]) +        # Effect B Num (7-bit)
    bytes([((0 & 0x03) << 6) | ((0 & 0x03) << 4) | ((0 & 0x03) << 2) | (0 & 0x03)]) + # Config byte
    bytes([64 & 0x7F]) +       # Softknob
    bytes([0 & 0xFF]) +        # LFO Rate
    bytes([0 & 0x7F]) + bytes([64 & 0x7F]) + bytes([0 & 0x7F]) + bytes([64 & 0x7F]) + bytes([127 & 0x7F]) + bytes([0 & 0x7F]) + # IO Levels 1-6
    # Patch 1 (src=65, dest=2, scale=1000, thresh=0)
    bytes([65 & 0x7F, 2 & 0x7F, (1000 >> 7) & 0x7F, 0 & 0x7F, 1000 & 0x7F, 0]) +
    # Patch 2 (src=66, dest=0, scale=500, thresh=64)
    bytes([66 & 0x7F, 0 & 0x7F, (500 >> 7) & 0x7F, 64 & 0x7F, 500 & 0x7F, 0])
)
assert len(SETUP_V3_BYTES) == 36

# Example V3 Effect Data (102 bytes, unnibblized)
param_bytes_effect = bytearray(68)
# Param 0 (size): Value 50 (0x0032)
param_bytes_effect[0*2] = 0x00
param_bytes_effect[0*2+1] = 0x32
# Param 2 (rtim): Value 80 (0x0050)
param_bytes_effect[2*2] = 0x00
param_bytes_effect[2*2+1] = 0x50
# Param 8 (pdly): Value 100 (0x0064)
param_bytes_effect[8*2] = 0x00
param_bytes_effect[8*2+1] = 0x64

EFFECT_V3_BYTES = (
    b'Test Effect\x00' + # Name (12 bytes)
    bytes([0]) +        # Algorithm ID (0 = Random Hall) (1 byte)
    bytes([0]) +        # Reserved byte (1 byte)
    bytes(param_bytes_effect) + # Parameters (68 bytes)
    bytes([0] * 20)     # Patches (placeholder 0s) (20 bytes)
)
assert len(EFFECT_V3_BYTES) == 102

from unittest.mock import MagicMock

# --- Test Data ---
SAMPLE_PRESET_BYTES = b'TestName\x00\x00\x00\x00\x01' + bytes([i % 256 for i in range(36 - 13)]) # Example byte data

# --- Tests ---

def test_generate_sysex_header():
    header = generate_sysex_header(CLASS_REQUEST, midi_channel=1)
    assert header == [SYSEX_START, LEXICON_ID, M300_ID, (CLASS_REQUEST << 4) | 0]
    header_ch5 = generate_sysex_header(CLASS_PARAMETER, midi_channel=5)
    assert header_ch5 == [SYSEX_START, LEXICON_ID, M300_ID, (CLASS_PARAMETER << 4) | 4]

def test_generate_request_no_value():
    msg = generate_request(REQ_ACTIVE_SETUP, midi_channel=1)
    expected = (
        SYSEX_START, LEXICON_ID, M300_ID, (CLASS_REQUEST << 4) | 0,
        REQ_ACTIVE_SETUP[0], REQ_ACTIVE_SETUP[1],
        SYSEX_END
    )
    assert msg == expected

def test_generate_request_with_value():
    # Example: Request Stored Setup index 10 (0x0A)
    msg = generate_request((0x00, 0x06, True), value=10, midi_channel=1)
    expected = (
        SYSEX_START, LEXICON_ID, M300_ID, (CLASS_REQUEST << 4) | 0,
        0x00, 0x06, # Subclass/Domain, Opcode
        10, 0,      # Value LSB, Value MSB (10 = 0x0A)
        SYSEX_END
    )
    assert msg == expected

def test_generate_request_param_value():
    # Example: Request Param 5 in Domain 3 (Effect A)
    msg = generate_request(REQ_PARAM_VALUE, value=5, domain_for_param_req=DOMAIN_EFFECT_A, midi_channel=1) # Corrected kwarg name
    expected = (
        SYSEX_START, LEXICON_ID, M300_ID, (CLASS_REQUEST << 4) | 0,
        DOMAIN_EFFECT_A, REQ_PARAM_VALUE[1], # Domain, Opcode
        5, 0,           # Param Num LSB, Param Num MSB (5 = 0x05)
        SYSEX_END
    )
    assert msg == expected

def test_nibblize_unnibblize():
    original = bytes([0x12, 0x34, 0xAB, 0xCD, 0xFF, 0x00])
    nibblized = nibblize_data(original)
    # Expected: [0x02, 0x01, 0x04, 0x03, 0x0B, 0x0A, 0x0D, 0x0C, 0x0F, 0x0F, 0x00, 0x00]
    assert len(nibblized) == len(original) * 2
    assert nibblized[0] == 0x02 and nibblized[1] == 0x01 # 0x12
    assert nibblized[8] == 0x0F and nibblized[9] == 0x0F # 0xFF
    unnibblized = unnibblize_data(nibblized)
    assert unnibblized == original

def test_calculate_checksum():
    # Checksum is XOR sum of nibblized data + flag bytes
    nibblized = [0x01, 0x02, 0x03, 0x04]
    flags = list(EXPECTED_FLAG_BYTES) # (0x0B, 0x09, 0x06, 0x0D)
    data_for_checksum = nibblized + flags
    # 1^2^3^4^11^9^6^13 = 3^3^4^11^9^6^13 = 0^4^11^9^6^13 = 4^11^9^6^13 = 15^9^6^13 = 6^6^13 = 0^13 = 13 (0x0D)
    checksum = calculate_checksum(data_for_checksum)
    assert checksum == 0x0D

# Mock preset object for bulk sysex generation test
class MockPreset:
    def __init__(self, name="MockPreset", byte_data=SAMPLE_PRESET_BYTES):
        self.name = name
        self._byte_data = byte_data

    def to_bytes(self):
        return self._byte_data

def test_generate_bulk_sysex():
    mock_preset = MockPreset()
    index = 5
    msg_type = TYPE_ACTIVE_SETUP_V3 # Example type
    msg_class = CLASS_ACTIVE_BULK

    sysex = generate_bulk_sysex(mock_preset, msg_type, index, midi_channel=1)
    assert sysex is not None
    assert sysex[0] == SYSEX_START
    assert sysex[1] == LEXICON_ID
    assert sysex[2] == M300_ID
    assert sysex[3] == (msg_class << 4) | 0 # Class and Channel
    assert sysex[4] == msg_type
    assert sysex[5] == index
    data_byte_count = sysex[6]
    variable_payload = list(sysex[7:-1])
    assert len(variable_payload) == data_byte_count
    assert sysex[-1] == SYSEX_END

    # Verify checksum calculation part
    nibblized = nibblize_data(mock_preset.to_bytes())
    payload_for_checksum = nibblized + list(EXPECTED_FLAG_BYTES)
    expected_checksum = calculate_checksum(payload_for_checksum)
    assert variable_payload[-1] == expected_checksum
    assert tuple(variable_payload[-5:-1]) == EXPECTED_FLAG_BYTES # Check flags

# --- SysEx Parsing Tests ---

def test_parse_sysex_parameter_change():
    # Example: Param 5 (0x05) in Domain 3 (Effect A) set to 1000 (0x03E8 -> LSB=0x68, MSB=0x07)
    sysex_msg = (
        SYSEX_START, LEXICON_ID, M300_ID, (CLASS_PARAMETER << 4) | 0, # Class=Param, Chan=1
        (0 << 4) | DOMAIN_EFFECT_A, # Subclass=0, Domain=Effect A
        0x05, # Param Number
        0x68, # Value LSB
        0x07, # Value MSB
        SYSEX_END
    )
    parsed = parse_m300_sysex_detailed(sysex_msg)
    assert parsed["error"] is None
    assert parsed["message_class_raw"] == CLASS_PARAMETER
    assert parsed["message_class"] == "Parameter Data"
    assert parsed["param_domain"] == DOMAIN_EFFECT_A
    assert parsed["param_number"] == 5
    assert parsed["param_value"] == 1000

def test_parse_sysex_active_setup_bulk():
    # Use the same bytes generated by generate_bulk_sysex test (or known good data)
    # For simplicity, reuse the mock preset and generate sample data
    mock_preset = MockPreset(byte_data=SETUP_V3_BYTES) # Use Setup bytes
    index = 0 # Active dumps often use index 0
    msg_type = TYPE_ACTIVE_SETUP_V3
    msg_class = CLASS_ACTIVE_BULK
    sysex_msg = generate_bulk_sysex(mock_preset, msg_type, index, midi_channel=1)
    assert sysex_msg is not None

    parsed = parse_m300_sysex_detailed(sysex_msg)
    assert parsed["error"] is None
    assert parsed["message_class_raw"] == msg_class
    assert parsed["message_class"] == "Active Bulk Data"
    assert parsed["type_byte_raw"] == msg_type
    assert parsed["index"] == index
    assert parsed["preset_type_str"] == "Active Setup"
    assert parsed["preset_class_name"] == "SetupPresetV3"
    assert parsed["unnibblized_data"] == SETUP_V3_BYTES
    # Verify checksum
    nibblized = nibblize_data(SETUP_V3_BYTES)
    payload_for_checksum = nibblized + list(EXPECTED_FLAG_BYTES)
    expected_checksum = calculate_checksum(payload_for_checksum)
    assert parsed["checksum_raw"] == expected_checksum
    assert parsed["checksum_calculated"] == expected_checksum

def test_parse_sysex_invalid_structure():
    # Too short
    msg = (SYSEX_START, LEXICON_ID, M300_ID, SYSEX_END)
    parsed = parse_m300_sysex_detailed(msg)
    assert "Not a valid M300 SysEx" in parsed["error"]
    # Incorrect end byte
    msg = (SYSEX_START, LEXICON_ID, M300_ID, 0, 0, 0, 0xF0)
    parsed = parse_m300_sysex_detailed(msg)
    assert "Not a valid M300 SysEx" in parsed["error"]
    # Incorrect manufacturer
    msg = (SYSEX_START, 0x7F, M300_ID, 0, 0, 0, SYSEX_END)
    parsed = parse_m300_sysex_detailed(msg)
    assert "Not a valid M300 SysEx" in parsed["error"]

def test_parse_sysex_bulk_bad_checksum():
     # Generate valid message first
    mock_preset = MockPreset(byte_data=SETUP_V3_BYTES)
    sysex_list = list(generate_bulk_sysex(mock_preset, TYPE_ACTIVE_SETUP_V3, 0, 1))
    # Corrupt the checksum byte
    sysex_list[-2] = (sysex_list[-2] + 1) & 0x7F # Flip a bit
    corrupted_sysex = tuple(sysex_list)

    parsed = parse_m300_sysex_detailed(corrupted_sysex)
    assert parsed["error"] is None # Parser should still parse
    assert parsed["warning"] is None # Checksum mismatch isn't currently a warning in parser
    assert parsed["checksum_raw"] != parsed["checksum_calculated"]

def test_parse_sysex_bulk_bad_flags():
     # Generate valid message first
    mock_preset = MockPreset(byte_data=SETUP_V3_BYTES)
    sysex_list = list(generate_bulk_sysex(mock_preset, TYPE_ACTIVE_SETUP_V3, 0, 1))
    # Corrupt a flag byte (e.g., the last one before checksum)
    sysex_list[-3] = (sysex_list[-3] + 1) & 0x7F
    corrupted_sysex = tuple(sysex_list)

    parsed = parse_m300_sysex_detailed(corrupted_sysex)
    assert parsed["error"] is None
    assert "Unexpected flag bytes" in parsed["warning"]
    # Checksum will likely mismatch now too
    assert parsed["checksum_raw"] != parsed["checksum_calculated"]