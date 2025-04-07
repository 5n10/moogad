import asyncio
import logging
from typing import Callable, Any
from functools import wraps

from typing import List, Tuple, Dict, Any, Optional, Callable, Set, Union
from .models import PRESET_CLASS_MAP # Import maps needed by parser (Removed BULK_TYPE_MAP)


logger = logging.getLogger(__name__)

class MIDIOperationError(Exception):
    """Base exception for MIDI operations."""
    pass

def with_midi_retry(retries: int = 3, delay: float = 0.1):
    """Decorator for MIDI operations with retry logic."""

# --- M300 Constants ---
SYSEX_START = 0xF0
SYSEX_END = 0xF7
LEXICON_ID = 0x06
M300_ID = 0x03

# Message Classes
CLASS_ACTIVE_BULK = 0
CLASS_STORED_BULK = 1
CLASS_PARAMETER = 2
CLASS_EVENT = 3
CLASS_REQUEST = 4
CLASS_RESPONSE = 5
CLASS_DISPLAY = 6

# Domains
DOMAIN_UTILITY = 0
DOMAIN_RUN = 1
DOMAIN_SETUP = 2
DOMAIN_EFFECT_A = 3
DOMAIN_EFFECT_B = 4
DOMAIN_MODULATION_A = 5
DOMAIN_MODULATION_B = 6

# Bulk Data Types (V3.00)
TYPE_ACTIVE_SETUP_V3 = 0x32
TYPE_ACTIVE_EFFECT_A_V3 = 0x33
TYPE_ACTIVE_EFFECT_B_V3 = 0x34
TYPE_STORED_SETUP_V3 = 0x20
TYPE_STORED_EFFECT_V3 = 0x30
TYPE_PRESET_SETUP_V3 = 0x40
TYPE_PRESET_EFFECT_V3 = 0x50

# Map (message_class, type_byte) to (preset_type_str, preset_class_name)
# Used by the parser to identify incoming bulk data
BULK_TYPE_MAP: Dict[Tuple[int, int], Tuple[str, str]] = {
    (CLASS_ACTIVE_BULK, TYPE_ACTIVE_SETUP_V3): ("Active Setup", "SetupPresetV3"),
    (CLASS_ACTIVE_BULK, TYPE_ACTIVE_EFFECT_A_V3): ("Active Effect A", "EffectPresetV3"),
    (CLASS_ACTIVE_BULK, TYPE_ACTIVE_EFFECT_B_V3): ("Active Effect B", "EffectPresetV3"),
    (CLASS_STORED_BULK, TYPE_STORED_SETUP_V3): ("Stored Setup", "SetupPresetV3"),
    (CLASS_STORED_BULK, TYPE_STORED_EFFECT_V3): ("Stored Effect", "EffectPresetV3"),
    # Add Preset types if needed, assuming they also use CLASS_STORED_BULK
    (CLASS_STORED_BULK, TYPE_PRESET_SETUP_V3): ("Preset Setup", "SetupPresetV3"),
    (CLASS_STORED_BULK, TYPE_PRESET_EFFECT_V3): ("Preset Effect", "EffectPresetV3"),
}


# Request Data Opcodes (Subclass/Domain + Opcode Byte + Requires Value Flag)
REQ_ALL_PRESET_SETUPS = (0x00, 0x00, False)
REQ_ALL_PRESET_EFFECTS = (0x00, 0x01, False)
REQ_ALL_STORED_SETUPS = (0x00, 0x02, False)
REQ_ALL_STORED_EFFECTS = (0x00, 0x03, False)
REQ_PRESET_SETUP = (0x00, 0x04, True)
REQ_PRESET_EFFECT = (0x00, 0x05, True)
REQ_STORED_SETUP = (0x00, 0x06, True)
REQ_STORED_EFFECT = (0x00, 0x07, True)
REQ_ACTIVE_SETUP = (0x02, 0x08, False)
REQ_ACTIVE_EFFECT_A = (0x03, 0x09, False)
REQ_ACTIVE_EFFECT_B = (0x04, 0x09, False)
REQ_PARAM_VALUE = (0x00, 0x0E, True) # Domain specified separately

# NRPN CC Numbers
NRPN_MSB_CC = 99
NRPN_LSB_CC = 98
DATA_ENTRY_MSB_CC = 6
DATA_ENTRY_LSB_CC = 38

# Bulk Data Constants
EXPECTED_FLAG_BYTES = (0x0B, 0x09, 0x06, 0x0D)
FLAG_BYTES_LEN = 4
CHECKSUM_LEN = 1

# --- Helper Functions ---
def is_m300_sysex(message: Tuple[int, ...]) -> bool:
    """Checks if a MIDI message is a Lexicon M300 SysEx message."""
    return (
        len(message) > 4 and
        message[0] == SYSEX_START and
        message[1] == LEXICON_ID and
        message[2] == M300_ID and
        message[-1] == SYSEX_END
    )

def unnibblize_data(nibble_pairs: List[int]) -> Optional[bytes]:
    """Converts nibblized 7-bit MIDI byte pairs back to 8-bit bytes."""
    if len(nibble_pairs) % 2 != 0:
        logger.warning("Odd number of nibbles received for unnibblizing.")
        return None
    byte_data = bytearray()
    for i in range(0, len(nibble_pairs), 2):
        lsn = nibble_pairs[i] & 0x7F
        msn = nibble_pairs[i+1] & 0x7F
        byte = (msn << 4) | lsn
        byte_data.append(byte)
    return bytes(byte_data)

def nibblize_data(byte_data: bytes) -> List[int]:
    """Converts a bytes object of 8-bit bytes into nibblized 7-bit MIDI byte pairs."""
    nibblized = []
    for byte in byte_data:
        msn = (byte >> 4) & 0x0F
        lsn = byte & 0x0F
        nibblized.append(lsn & 0x7F) # LSB first
        nibblized.append(msn & 0x7F)
    return nibblized

def calculate_checksum(data_bytes_for_checksum: List[int]) -> int:
    """
    Calculates the checksum (7-bit XOR sum).
    Assumes checksum is calculated over the nibblized data bytes PLUS the flag bytes.
    """
    checksum = 0
    for byte in data_bytes_for_checksum:
        checksum ^= (byte & 0x7F)
    return checksum & 0x7F

def parse_string(byte_array: bytes, max_len: int) -> str:
    """Parses a null-terminated ASCII string from a byte array."""
    try:
        end_index = byte_array.index(0)
        actual_end = min(end_index, max_len)
        return byte_array[:actual_end].decode('ascii', errors='ignore')
    except ValueError:
        return byte_array[:max_len].decode('ascii', errors='ignore')

def format_string(text: str, max_len: int) -> bytes:
    """Formats a string to a fixed length with null termination."""
    truncated_text = text[:max_len]
    encoded = truncated_text.encode('ascii', errors='ignore')

def generate_sysex_header(message_class: int, midi_channel: int = 1) -> List[int]:
    """Generates the standard M300 SysEx header."""
    if not (1 <= midi_channel <= 16):
        # Default to channel 1 if invalid
        logger.warning(f"Invalid MIDI channel {midi_channel} specified, defaulting to 1.")
        midi_channel = 1
    # Class is upper 3 bits, Channel (0-15) is lower 4 bits
    class_channel_byte = ((message_class & 0x07) << 4) | ((midi_channel - 1) & 0x0F)
    return [SYSEX_START, LEXICON_ID, M300_ID, class_channel_byte]

def generate_request(request_tuple: Tuple[int, int, bool], value: Optional[int] = None, domain_for_param_req: Optional[int] = None, midi_channel: int = 1) -> Tuple[int, ...]:
    """Generates a SysEx request message."""
    header = generate_sysex_header(CLASS_REQUEST, midi_channel)
    subclass_domain_byte, opcode_byte, requires_value = request_tuple
    message_list = header + [subclass_domain_byte, opcode_byte]

    # Special handling for Parameter Value Request (Opcode 0x0E)
    # It uses the subclass_domain_byte for the parameter's domain, not 0x00
    if request_tuple == REQ_PARAM_VALUE:
        if domain_for_param_req is None:
            raise ValueError("Domain required for Parameter Value Request (0x0E)")
        message_list[4] = (0 << 4) | (domain_for_param_req & 0x0F) # Use provided domain

    if requires_value:
        if value is None:
            raise ValueError(f"Value required for request opcode {opcode_byte:#04x}")
        # Assuming value is up to 14-bit for indices/param numbers
        value_lsb = value & 0x7F
        value_msb = (value >> 7) & 0x7F
        message_list.extend([value_lsb, value_msb]) # Moved inside the if block

    message_list.append(SYSEX_END)
    return tuple(message_list)


def generate_bulk_sysex(preset_object: Any, bulk_data_type: int, index: int, midi_channel: int = 1) -> Optional[Tuple[int, ...]]:
    """Generates a SysEx bulk data dump message for a given preset object."""
    logger.info(f"Generating Bulk SysEx: Type={bulk_data_type:#04x}, Index={index}")

    # Determine message class based on type (simplified check)
    # Active types: 0x32, 0x33, 0x34 (V3)
    # Stored types: 0x20, 0x30 (V3)
    # Preset types: 0x40, 0x50 (V3)
    if bulk_data_type in [TYPE_ACTIVE_SETUP_V3, TYPE_ACTIVE_EFFECT_A_V3, TYPE_ACTIVE_EFFECT_B_V3]:
        message_class = CLASS_ACTIVE_BULK
    elif bulk_data_type in [TYPE_STORED_SETUP_V3, TYPE_STORED_EFFECT_V3, TYPE_PRESET_SETUP_V3, TYPE_PRESET_EFFECT_V3]:
        message_class = CLASS_STORED_BULK # Note: Presets use CLASS_STORED_BULK according to some interpretations
    else:
        logger.error(f"Unknown bulk_data_type {bulk_data_type:#04x} for determining message class.")
        return None

    try:
        # Get the raw bytes from the preset object
        unnibblized_bytes = preset_object.to_bytes()
        if unnibblized_bytes is None:
             logger.error(f"Preset object {type(preset_object).__name__} failed to serialize to bytes.")
             return None

        # Nibblize the data
        nibblized_data = nibblize_data(unnibblized_bytes)

        # Prepare payload for checksum (nibblized data + flag bytes)
        payload_for_checksum = nibblized_data + list(EXPECTED_FLAG_BYTES)
        checksum = calculate_checksum(payload_for_checksum)

        # Construct the variable payload part (data + flags + checksum)
        variable_payload = payload_for_checksum + [checksum]
        data_byte_count = len(variable_payload)

        # Check if data byte count exceeds 7-bit limit (127)
        if data_byte_count > 127:
            logger.error(f"SysEx data byte count {data_byte_count} exceeds 7-bit limit (127). Cannot generate message.")
            return None

        # Generate the header
        header = generate_sysex_header(message_class, midi_channel)

        # Construct the full message
        # Header + Type Byte + Index + Data Byte Count + Variable Payload + End
        message_list = header + [bulk_data_type & 0x7F, index & 0x7F, data_byte_count & 0x7F] + variable_payload + [SYSEX_END]

        logger.info(f"Generated SysEx message length: {len(message_list)} for {preset_object.name}")
        return tuple(message_list)

    except AttributeError as e:
        logger.error(f"Preset object of type {type(preset_object).__name__} missing 'to_bytes' method or name attribute: {e}")
        return None
    except Exception as e:
        logger.exception(f"Error generating bulk SysEx for type {bulk_data_type:#04x}, index {index}")
        return None

# Removed misplaced value extension lines from here


    padded = encoded.ljust(max_len, b'\x00')
    return padded

def parse_m300_sysex_detailed(message: Tuple[int, ...]) -> Dict[str, Any]:
    """ Parses validated M300 SysEx, including bulk data. """
    # logger.debug(f"Parsing SysEx (len={len(message)}): {message[:8]}...") # Keep this less verbose
    parsed = {
        "message_class_raw": None,
        "type_byte_raw": None,
        "payload_raw": [],
        "error": None,
        "warning": None,
        "message_class": "Unknown",
        "index": None,
        "preset_type_str": None,
        "preset_class_name": None,
        "unnibblized_data": None,
        "checksum_raw": None,
        "checksum_calculated": None,
        "param_domain": None,
        "param_number": None,
        "param_value": None,
        # Add fields for other message types (Response, Display, etc.) as needed
    }

    if not is_m300_sysex(message):
        parsed["error"] = "Not a valid M300 SysEx message structure."
        return parsed

    try:
        msg_class_channel_byte = message[3]
        msg_class = (msg_class_channel_byte >> 4) & 0x07
        # midi_channel = (msg_class_channel_byte & 0x0F) + 1 # Can parse channel if needed
        parsed["message_class_raw"] = msg_class
        logger.debug(f"  Parsed Class: {msg_class}")

        type_byte = message[4]
        parsed["type_byte_raw"] = type_byte
        logger.debug(f"  Parsed Type Byte: {type_byte:#04x}")

        payload = list(message[5:-1]) # Exclude header and SYSEX_END
        parsed["payload_raw"] = payload

        if msg_class == CLASS_PARAMETER:
            parsed["message_class"] = "Parameter Data"
            if len(payload) >= 3:
                # Parameter messages use type_byte for subclass/domain
                parsed["param_domain"] = type_byte & 0x0F
                parsed["param_number"] = payload[0]
                # Value is 14-bit, LSB first then MSB
                parsed["param_value"] = (payload[2] << 7) | payload[1]
                logger.debug(f"  Parsed Param: Domain={parsed['param_domain']}, Num={parsed['param_number']}, Val={parsed['param_value']}")
            else:
                parsed["error"] = "Parameter data payload too short."

        elif msg_class == CLASS_ACTIVE_BULK or msg_class == CLASS_STORED_BULK:
            parsed["message_class"] = "Active Bulk Data" if msg_class == CLASS_ACTIVE_BULK else "Stored Bulk Data"
            if len(payload) < 3: # Need at least index, data_byte_count, checksum
                parsed["error"] = "Bulk data payload too short for header info."
                return parsed

            parsed["index"] = payload[0]
            data_byte_count = payload[1]
            variable_payload = payload[2:]
            logger.debug(f"  Parsed Bulk Header: Index={parsed['index']}, DataByteCount={data_byte_count}")

            if len(variable_payload) != data_byte_count:
                parsed["error"] = f"Bulk data byte count mismatch. Expected {data_byte_count}, got {len(variable_payload)}."
                return parsed

            if data_byte_count < CHECKSUM_LEN + FLAG_BYTES_LEN:
                 parsed["error"] = f"Bulk data payload too short for checksum/flags. Min required: {CHECKSUM_LEN + FLAG_BYTES_LEN}, got: {data_byte_count}."
                 return parsed

            # Extract components from variable_payload
            nibblized_data_with_flags = variable_payload[:-CHECKSUM_LEN]
            parsed["checksum_raw"] = variable_payload[-CHECKSUM_LEN]

            # Validate flag bytes
            received_flags = tuple(nibblized_data_with_flags[-FLAG_BYTES_LEN:])
            if received_flags != EXPECTED_FLAG_BYTES:
                parsed["warning"] = f"Unexpected flag bytes. Expected {EXPECTED_FLAG_BYTES}, got {received_flags}."
                # Continue parsing despite warning

            # Calculate checksum (over nibblized data + flags)
            parsed["checksum_calculated"] = calculate_checksum(nibblized_data_with_flags)
            logger.debug(f"  Checksum: Raw={parsed['checksum_raw']}, Calc={parsed['checksum_calculated']}")
            # Extract nibblized preset data (excluding flags)
            nibblized_preset_data = nibblized_data_with_flags[:-FLAG_BYTES_LEN]
            parsed["unnibblized_data"] = unnibblize_data(nibblized_preset_data)

            # Determine preset type
            type_info = BULK_TYPE_MAP.get((msg_class, type_byte))
            if type_info:
                parsed["preset_type_str"], parsed["preset_class_name"] = type_info
                logger.debug(f"  Identified Preset Type: {parsed['preset_type_str']} ({parsed['preset_class_name']})")
            else:
                parsed["warning"] = f"Unknown bulk data type: Class={msg_class}, Type={type_byte:#04x}"

        # TODO: Add parsing logic for other message classes (Response, Display, etc.)
        # elif msg_class == CLASS_RESPONSE:
        #     parsed["message_class"] = "Response Data"
        #     # ... parse response payload ...

    except IndexError as e:
        parsed["error"] = f"SysEx message too short during parsing: {e}"
    except Exception as e:
        logger.exception("Unexpected error during SysEx parsing")
        parsed["error"] = f"Internal parsing error: {e}"

    return parsed



    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    logger.warning(f"Retry {attempt + 1}/{retries}: {str(e)}")
                    if attempt < retries - 1:
                        await asyncio.sleep(delay * (attempt + 1))
            raise MIDIOperationError(f"Operation failed after {retries} retries: {last_error}")
        return wrapper
    return decorator

class MIDIMessageQueue:
    """Queue for handling MIDI messages with rate limiting."""
    def __init__(self, rate_limit: float = 0.05):
        self.queue = asyncio.Queue()
        self.rate_limit = rate_limit
        self._task = None

    async def start(self):
        """Start processing queue."""
        self._task = asyncio.create_task(self._process_queue())

    async def stop(self):
        """Stop processing queue."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def put(self, message: Any):
        """Add message to queue."""
        await self.queue.put(message)

    async def _process_queue(self):
        """Process messages from queue with rate limiting."""
        while True:
            message = await self.queue.get()
            try:
                await message()
            finally:
                self.queue.task_done()
                await asyncio.sleep(self.rate_limit)
