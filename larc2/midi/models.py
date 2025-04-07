"""
Models for M300 Effect and Setup presets.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Raised when preset validation fails."""
    pass

@dataclass
class BasePreset:
    """Base class for M300 presets."""
    name: str = "Untitled"

    def to_dict(self) -> Dict[str, Any]:
        """Convert preset to dictionary format."""
        return {"name": self.name}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BasePreset':
        """Create preset from dictionary data."""
        instance = cls()
        instance.name = data.get("name", "Untitled")
        return instance

# Algorithm mapping constants
ALGORITHM_ID_TO_NAME_V3 = {
    0: "Random Hall",
    1: "Ambience",
    2: "Plate",
    3: "Stereo Adjust",
    4: "Stereo Pitch Shift",
    5: "Twin Echo",
    6: "Small Reverb",
    7: "Mono Pitch Shift",
    8: "Mono Compressor",
    9: "PONS",
    10: "Small Stereo Adjust"
}
ALGORITHM_NAME_TO_ID_V3 = {v: k for k, v in ALGORITHM_ID_TO_NAME_V3.items()}

# Parameter mapping constants
RANDOM_HALL_PARAM_MAP: Dict[int, Optional[str]] = {
    0: "size", 1: None,  # Algorithm select is param 1
    2: "rtim", 3: "xovr", 4: "bass", 5: "roll", 6: "tdcy", 7: "diff",
    8: "pdly", 9: "link", 10: "sprd", 11: "shap", 12: "dly1", 13: "lvl1",
    14: "dly2", 15: "lvl2", 16: "dly3", 17: "lvl3", 18: "dly4", 19: "lvl4",
    20: "spin", 21: "wand", 22: "fbk3", 23: "fbk4", 24: "rlvl", 25: "shlf"
}

AMBIENCE_PARAM_MAP: Dict[int, Optional[str]] = {
    0: "size", 1: None,
    2: "rtim", 3: "rlvl",
    4: "roll", 5: "spin", 6: "wand", 7: "diff",
    8: "pdly", 9: "ddly"
}

RICH_PLATE_PARAM_MAP: Dict[int, Optional[str]] = {
    0: "size", 1: None,
    2: "rtim", 3: "xovr", 4: "bass", 5: "roll", 6: "tdcy", 7: "diff",
    8: "pdly", 9: "link", 10: "sprd", 11: "shap",
    12: "dly1", 13: "fbk1",
    14: "dly2", 15: "fbk2",
    16: "dly3", 17: "lvl3",
    18: "dly4", 19: "lvl4",
    20: "dly5", 21: "lvl5", 22: "fbk5",
    23: "dly6", 24: "lvl6", 25: "fbk6",
    26: "spin", 27: "wand", 28: "rlvl", 29: "rand"
}

# Parameter value ranges
PARAM_RANGES = {
    "size": (0, 127),    # Room Size
    "rtim": (0, 127),    # Mid RT
    "pdly": (0, 500),    # Pre Delay
    "link": (0, 1),      # Link
    "roll": (0, 127),    # High Roll
    "tdcy": (0, 127),    # Treble Decay
    "bass": (0, 127),    # Bass Multiply
    "xovr": (0, 127),    # Bass Crossover
    "shlf": (0, 127),    # Shelf
    "diff": (0, 127),    # Diffusion
    "shap": (0, 127),    # Shape
    "spin": (0, 127),    # Spin Rate
    "wand": (0, 127),    # Wander
    "sprd": (0, 255),    # Spread
    "rlvl": (0, 127),    # Reverb Level
    "ddly": (0, 500)     # Dry Delay
}

# Additional algorithm parameter maps
STEREO_ADJUST_PARAM_MAP: Dict[int, Optional[str]] = {
    0: "mstr", 1: "bal", 2: "rot", 3: "dlay", 4: "dem", 5: "half_sample", 6: "rfns",
    7: "bass", 8: "treb", 9: "ltrb", 10: "rtrb", 11: "bxov", 12: "txov", 13: "txlr",
    14: "speq", 15: "ldly", 16: "lfin", 17: "rdly", 18: "rfin", 19: "lfbk",
    20: "lfbk_fine", 21: "rfbk", 22: "rfbk_fine", 23: "dcsw", 24: "ldc", 25: "rdc", 26: "shuf"
}
PITCH_SHIFT_PARAM_MAP: Dict[int, Optional[str]] = { # Renamed from STEREO_PITCH_SHIFT_PARAM_MAP for consistency
    0: "mode", 1: "gldl", 2: "gldr", 3: "pchl", 4: "finl", 5: "pchr", 6: "finr",
    7: "ldly", 8: "lfbk", 9: "rdly", 10: "rfbk", 11: "bnps", 12: "sync"
}
DUAL_DELAYS_PARAM_MAP: Dict[int, Optional[str]] = {
    0: "fdly", 1: "lfbd", 2: "rfbd", 3: "lflg", 4: "rflg", 5: "dly1", 6: "fbk1",
    7: "dly2", 8: "fbk2", 9: "apd1", 10: "apg1", 11: "apd2", 12: "apg2", 13: "dly3",
    14: "fbk3", 15: "dly4", 16: "fbk4", 17: "ldly_out", 18: "lpan", 19: "rdly_out", 20: "rpan"
}
SPLIT_CHAMBER_PARAM_MAP: Dict[int, Optional[str]] = {
    0: "rtim", 1: "size", 2: "pdly", 3: "tdcy", 4: "shap", 5: "sprd", 6: "bass",
    7: "diff", 8: "rand", 9: "xovr", 10: "link"
}
MONO_PITCH_SHIFT_PARAM_MAP: Dict[int, Optional[str]] = {
    0: "pch", 1: "dly", 2: "fbk", 3: "gld", 4: "fin", 5: "bnps"
}
COMPRESSOR_PARAM_MAP: Dict[int, Optional[str]] = {
    0: "pdly_comp", 1: "atc", 2: "rtc", 3: "thrs", 4: "gain", 5: "slp", 6: "exth",
    7: "exg", 8: "exsl"
}
PONS_PARAM_MAP: Dict[int, Optional[str]] = {
    0: "dith", 1: "pons_gain"
}
SMALL_STEREO_ADJUST_PARAM_MAP: Dict[int, Optional[str]] = {
    0: "mstr", 1: "bal", 2: "rot", 3: "speq", 4: "rfns", 5: "basl", 6: "ltrb",
    7: "bxov", 8: "basr", 9: "rtrb", 10: "txlr"
}

# Define ALL_PARAM_MAPS *after* all individual maps are defined
ALL_PARAM_MAPS: Dict[str, Dict[int, Optional[str]]] = {
    "Random Hall": RANDOM_HALL_PARAM_MAP,
    "Ambience": AMBIENCE_PARAM_MAP,
    "Plate": RICH_PLATE_PARAM_MAP,
    "Stereo Adjust": STEREO_ADJUST_PARAM_MAP,
    "Stereo Pitch Shift": PITCH_SHIFT_PARAM_MAP,
    "Twin Echo": DUAL_DELAYS_PARAM_MAP,
    "Small Reverb": SPLIT_CHAMBER_PARAM_MAP,
    "Mono Pitch Shift": MONO_PITCH_SHIFT_PARAM_MAP,
    "Mono Compressor": COMPRESSOR_PARAM_MAP,
    "PONS": PONS_PARAM_MAP,
    "Small Stereo Adjust": SMALL_STEREO_ADJUST_PARAM_MAP,
    "Unknown": {} # Default empty map
}


@dataclass
class EffectPresetV3(BasePreset):
    """Represents an M300 Effect preset (V3 format)."""
    algorithm: str = "Random Hall"
    tags: List[str] = field(default_factory=list)
    description: str = ""
    author: str = "User"
    created_date: str = ""

    # Default parameter values (based on Random Hall)
    rtim: int = 20    # Mid RT
    size: int = 37    # Room Size
    pdly: int = 220   # Pre Delay
    link: int = 1     # Link
    roll: int = 29    # High Roll
    tdcy: int = 36    # Treble Decay
    bass: int = 12    # Bass Multiply
    xovr: int = 5     # Bass Crossover
    shlf: int = 0     # Shelf
    diff: int = 65    # Diffusion
    shap: int = 120   # Shape
    spin: int = 38    # Spin Rate
    wand: int = 10    # Wander
    sprd: int = 157   # Spread
    dly1: int = 140   # Delay 1
    lvl1: int = 0     # Level 1
    dly2: int = 200   # Delay 2
    lvl2: int = 0     # Level 2
    dly3: int = 400   # Delay 3
    lvl3: int = 0     # Level 3
    fbk3: int = 0     # Feedback 3
    dly4: int = 480   # Delay 4
    lvl4: int = 0     # Level 4
    fbk4: int = 0     # Feedback 4
    rlvl: int = 0     # Reverb Level
    ddly: int = 0     # Dry Delay (Ambience)
    fbk1: int = 0     # Feedback 1 (Plate)
    fbk2: int = 0     # Feedback 2 (Plate)
    dly5: int = 0     # Delay 5 (Plate)
    lvl5: int = 0     # Level 5 (Plate)
    fbk5: int = 0     # Feedback 5 (Plate)
    dly6: int = 0     # Delay 6 (Plate)
    lvl6: int = 0     # Level 6 (Plate)
    fbk6: int = 0     # Feedback 6 (Plate)
    rand: int = 0     # Randomization (Plate)

    def validate(self) -> None:
        """Validate preset data."""
        if not self.name:
            raise ValidationError("Preset name is required")
        if self.algorithm not in ALGORITHM_NAME_TO_ID_V3:
            raise ValidationError(f"Invalid algorithm: {self.algorithm}")

        param_map = self.get_param_map()
        if not param_map: # Check if map exists for the algorithm
             logger.warning(f"No parameter map found for algorithm '{self.algorithm}' during validation.")
             return # Or raise error?

        for param_name, value in self.__dict__.items():
            if param_name in PARAM_RANGES:
                min_val, max_val = PARAM_RANGES[param_name]
                # Ensure value is int before comparison
                if isinstance(value, int) and not min_val <= value <= max_val:
                    raise ValidationError(f"Parameter {param_name} value {value} out of range [{min_val}, {max_val}]")
            # Add checks for other types if necessary

    def get_param_map(self) -> Optional[Dict[int, Optional[str]]]:
        """Returns the correct parameter map based on the current algorithm."""
        return ALL_PARAM_MAPS.get(self.algorithm)

    def validate_param_value(self, param_name: str, value: int) -> int:
        """Clamps the value to the valid range for the parameter."""
        if param_name in PARAM_RANGES:
            min_val, max_val = PARAM_RANGES[param_name]
            if value < min_val:
                logger.debug(f"Clamping {param_name} value {value} to min {min_val}")
                return min_val
            if value > max_val:
                logger.debug(f"Clamping {param_name} value {value} to max {max_val}")
                return max_val
        # Assuming 16-bit values if not in specific ranges, M300 uses 14/16 bit? Check manual.
        # For now, let's assume parameters are generally 16-bit if not specified otherwise.
        # Clamp to 16-bit unsigned range if no specific range defined
        # return max(0, min(value, 65535))
        # Let's assume 14-bit (0-16383) as per SysEx param message structure for now
        return max(0, min(value, 16383))


    def parse_bytes(self, data: bytes) -> None:
        """Parse binary data from M300 SysEx dump into effect parameters."""
        # Expected size for V3 Effect Preset is 102 bytes according to manual page 15
        expected_len = 102
        if len(data) < expected_len:
            logger.warning(f"Data too short for V3 Effect preset. Expected {expected_len}, got {len(data)} bytes")
            # Attempt partial parse? For now, return.
            return

        try:
            # Parse name (12 bytes, null-terminated)
            self.name = data[0:12].split(b'\x00')[0].decode('ascii', errors='replace').strip()

            # Parse algorithm ID
            algo_id = data[13]
            self.algorithm = ALGORITHM_ID_TO_NAME_V3.get(algo_id, f"UnknownAlgoID_{algo_id}")

            # Get parameter map based on algorithm
            param_map = self.get_param_map()

            if param_map:
                # Parse parameters (68 bytes starting at offset 14)
                # Parameter values seem to be 16-bit MSB first in the dump
                param_data_block = data[14:14+68]
                if len(param_data_block) < 68:
                     logger.warning(f"Parameter data block is too short: {len(param_data_block)} bytes")
                     # Handle partial data?

                for param_num, attr_name in param_map.items():
                    if attr_name is None: # Skip algorithm ID slot or other reserved slots
                        continue

                    # Calculate offset within the 68-byte parameter block
                    offset = param_num * 2
                    if offset + 1 < len(param_data_block):
                        # Read 16-bit value (MSB first)
                        value = (param_data_block[offset] << 8) | param_data_block[offset + 1]
                        # Validate/clamp value before setting
                        validated_value = self.validate_param_value(attr_name, value)
                        if hasattr(self, attr_name):
                            setattr(self, attr_name, validated_value)
                        else:
                            logger.warning(f"Preset class {type(self).__name__} missing attribute for param '{attr_name}' (Num: {param_num})")
                    else:
                        logger.warning(f"Offset {offset} out of bounds for param {param_num} ('{attr_name}') in param block size {len(param_data_block)}")

            # TODO: Parse Patches (Bytes 82-101)
            # Assuming 4 patches, 5 bytes each? (Src, Dest, Scale MSB, Thresh, Scale LSB) - Needs verification
            # patch_data = data[82:102]
            # for i in range(4):
            #     patch_offset = i * 5
            #     if patch_offset + 4 < len(patch_data):
            #         src = patch_data[patch_offset]
            #         dest = patch_data[patch_offset + 1]
            #         scale_msb = patch_data[patch_offset + 2]
            #         thresh = patch_data[patch_offset + 3]
            #         scale_lsb = patch_data[patch_offset + 4]
            #         scale = ((scale_msb & 0x7F) << 7) | (scale_lsb & 0x7F) # Reconstruct 14-bit scale
            #         # Update self.patches[i] attributes
            #         logger.debug(f"Parsed Patch {i+1}: Src={src}, Dest={dest}, Scale={scale}, Thresh={thresh}")

            logger.info(f"Parsed V3 Effect Preset '{self.name}' ({self.algorithm})")

        except IndexError as e:
             logger.error(f"Error parsing V3 Effect preset (IndexError): {e}. Data length: {len(data)}")
        except Exception as e:
            logger.exception(f"Error parsing V3 Effect preset: {e}")

    def to_bytes(self) -> bytes:
        """Convert effect preset to binary data for M300 SysEx dump."""
        try:
            self.validate()
            # Initialize 102-byte buffer (spec page 15)
            result = bytearray(102)

            # Write name (12 bytes, null-terminated)
            name_bytes = self.name.encode('ascii', errors='replace')[:12]
            result[0:len(name_bytes)] = name_bytes
            result[12] = 0  # Null terminator

            # Write algorithm ID
            algo_id = ALGORITHM_NAME_TO_ID_V3.get(self.algorithm, 0)
            result[13] = algo_id

            # Get parameter map based on algorithm
            param_map = self.get_param_map()

            if param_map:
                # Write parameters (68 bytes starting at offset 14)
                for param_num, attr_name in param_map.items():
                    if attr_name is None:
                        continue

                    # Calculate offset in parameter data block
                    offset = 14 + (param_num * 2)
                    if offset + 1 < len(result):
                        if hasattr(self, attr_name):
                            value = getattr(self, attr_name)
                            value = self.validate_param_value(attr_name, value)
                            # Write 16-bit value (MSB first)
                            result[offset] = (value >> 8) & 0xFF
                            result[offset + 1] = value & 0xFF
                        else:
                             logger.warning(f"Attribute '{attr_name}' not found during serialization.")
                    else:
                         logger.warning(f"Offset {offset} out of bounds during serialization.")


            # TODO: Serialize Patches (Bytes 82-101)
            # Assuming self.patches is a list of 4 patch objects/dicts
            # for i, patch in enumerate(self.patches):
            #     patch_offset = 82 + (i * 5)
            #     if patch_offset + 4 < len(result):
            #         src = getattr(patch, 'source', 0) & 0x7F
            #         dest = getattr(patch, 'destination', 0) & 0x7F # Assuming 7-bit dest
            #         scale = getattr(patch, 'scale', 0)
            #         thresh = getattr(patch, 'threshold', 0) & 0x7F
            #         scale_msb = (scale >> 7) & 0x7F
            #         scale_lsb = scale & 0x7F
            #         result[patch_offset] = src
            #         result[patch_offset + 1] = dest
            #         result[patch_offset + 2] = scale_msb
            #         result[patch_offset + 3] = thresh
            #         result[patch_offset + 4] = scale_lsb


            logger.info(f"Serialized V3 Effect Preset '{self.name}'")

        except ValidationError as e:
            logger.error(f"Preset validation failed during serialization: {e}")
            raise
        except Exception as e:
            logger.exception(f"Error serializing V3 Effect preset: {e}")
            # Return empty bytes or raise? Returning empty for now.
            return b''

        return bytes(result)

    def to_dict(self) -> Dict[str, Any]:
        """Convert preset to dictionary format."""
        base_dict = super().to_dict()
        params_dict = {}
        param_map = self.get_param_map()
        if param_map:
            for param_num, attr_name in param_map.items():
                if attr_name and hasattr(self, attr_name):
                    params_dict[attr_name] = getattr(self, attr_name)

        base_dict.update({
            "algorithm": self.algorithm,
            "tags": self.tags,
            "description": self.description,
            "author": self.author,
            "created_date": self.created_date,
            "parameters": params_dict
            # TODO: Add patches to dict
        })
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EffectPresetV3':
        """Create preset from dictionary data."""
        preset = cls()
        preset.name = data.get("name", "Untitled")
        preset.algorithm = data.get("algorithm", "Random Hall")
        preset.tags = data.get("tags", [])
        preset.description = data.get("description", "")
        preset.author = data.get("author", "User")
        preset.created_date = data.get("created_date", "")

        params = data.get("parameters", {})
        for param, value in params.items():
            if hasattr(preset, param):
                # Add type checking/validation if necessary
                try:
                     setattr(preset, param, int(value))
                except (ValueError, TypeError):
                     logger.warning(f"Could not set param '{param}' from dict value '{value}'")
            else:
                 logger.warning(f"Attribute '{param}' from dict not found in EffectPresetV3")

        # TODO: Load patches from dict

        return preset

@dataclass
class SetupPresetV3(BasePreset):
    """Represents an M300 Setup preset (V3 format)."""
    machine_config: int = 0      # 0-3
    effect_a_num: int = 101      # Effect A preset number
    effect_b_num: int = 0        # Effect B preset number
    lfo_shape: int = 0          # 0-3
    lfo_rate: int = 0           # 0-250
    softknob: int = 64          # 0-127
    io_level1: int = 0          # 0-127
    io_level2: int = 64         # 0-127
    io_level3: int = 0          # 0-127
    io_level4: int = 64         # 0-127
    io_level5: int = 127        # 0-127
    io_level6: int = 0          # 0-127
    patch1_src: int = 65        # 0-72
    patch1_dest: int = 2        # 0-33
    patch1_scale: int = 1000    # 14-bit value
    patch1_thresh: int = 0      # 0-127
    patch2_src: int = 66        # 0-72
    patch2_dest: int = 0        # 0-33
    patch2_scale: int = 500     # 14-bit value
    patch2_thresh: int = 64     # 0-127
    left_meter_assign: int = 0   # 0-3
    right_meter_assign: int = 0  # 0-3

    def parse_bytes(self, data: bytes) -> None:
        """Parse binary unnibblized data from M300 SysEx dump into setup parameters."""
        # Expected size for V3 Setup Preset is 36 bytes according to manual page 15
        expected_len = 36
        if len(data) < expected_len:
            logger.warning(f"Data too short for V3 Setup preset. Expected {expected_len}, got {len(data)} bytes")
            return

        try:
            # Parse name (12 bytes, null-terminated)
            self.name = data[0:12].split(b'\x00')[0].decode('ascii', errors='replace').strip()

            # Parse effect numbers (assuming 7-bit values in dump)
            self.effect_a_num = data[13] & 0x7F
            self.effect_b_num = data[14] & 0x7F

            # Parse configuration byte
            config_byte = data[15]
            self.machine_config = (config_byte >> 6) & 0x03
            self.lfo_shape = (config_byte >> 4) & 0x03
            self.left_meter_assign = (config_byte >> 2) & 0x03
            self.right_meter_assign = config_byte & 0x03

            # Parse remaining parameters (assuming 7-bit values, except LFO rate?)
            self.softknob = data[16] & 0x7F
            self.lfo_rate = data[17] # LFO Rate seems to be 8-bit in to_bytes? Verify. Assuming 8-bit based on to_bytes.
            self.io_level1 = data[18] & 0x7F
            self.io_level2 = data[19] & 0x7F
            self.io_level3 = data[20] & 0x7F
            self.io_level4 = data[21] & 0x7F
            self.io_level5 = data[22] & 0x7F
            self.io_level6 = data[23] & 0x7F

            # Parse patch 1 (5 bytes: src, dest, scale_msb, thresh, scale_lsb)
            self.patch1_src = data[24] & 0x7F
            self.patch1_dest = data[25] & 0x7F # Assuming dest is 7-bit
            scale1_msb = data[26] & 0x7F
            self.patch1_thresh = data[27] & 0x7F
            scale1_lsb = data[28] & 0x7F
            self.patch1_scale = (scale1_msb << 7) | scale1_lsb # Reconstruct 14-bit scale

            # Byte 29 is reserved

            # Parse patch 2 (5 bytes: src, dest, scale_msb, thresh, scale_lsb)
            self.patch2_src = data[30] & 0x7F
            self.patch2_dest = data[31] & 0x7F # Assuming dest is 7-bit
            scale2_msb = data[32] & 0x7F
            self.patch2_thresh = data[33] & 0x7F
            scale2_lsb = data[34] & 0x7F
            self.patch2_scale = (scale2_msb << 7) | scale2_lsb # Reconstruct 14-bit scale

            # Byte 35 is reserved

            logger.info(f"Parsed V3 Setup Preset '{self.name}'")

        except IndexError as e:
             logger.error(f"Error parsing V3 Setup preset (IndexError): {e}. Data length: {len(data)}")
        except Exception as e:
            logger.exception(f"Error parsing V3 Setup preset: {e}")

    def to_bytes(self) -> bytes:
        """Convert setup preset to binary data for M300 SysEx dump."""
        result = bytearray(36)

        try:
            # Write name (12 bytes, null-terminated)
            name_bytes = self.name.encode('ascii', errors='replace')[:12]
            result[0:len(name_bytes)] = name_bytes
            result[12] = 0  # Null terminator

            # Write effect numbers
            result[13] = self.effect_a_num & 0x7F
            result[14] = self.effect_b_num & 0x7F

            # Write configuration byte
            config_byte = (
                ((self.machine_config & 0x03) << 6) |
                ((self.lfo_shape & 0x03) << 4) |
                ((self.left_meter_assign & 0x03) << 2) |
                (self.right_meter_assign & 0x03)
            )
            result[15] = config_byte

            # Write remaining parameters
            result[16] = self.softknob & 0x7F
            result[17] = self.lfo_rate & 0xFF # Assuming 8-bit LFO rate
            result[18] = self.io_level1 & 0x7F
            result[19] = self.io_level2 & 0x7F
            result[20] = self.io_level3 & 0x7F
            result[21] = self.io_level4 & 0x7F
            result[22] = self.io_level5 & 0x7F
            result[23] = self.io_level6 & 0x7F

            # Write patch 1
            result[24] = self.patch1_src & 0x7F
            result[25] = self.patch1_dest & 0x7F
            result[26] = (self.patch1_scale >> 7) & 0x7F
            result[27] = self.patch1_thresh & 0x7F
            result[28] = self.patch1_scale & 0x7F
            result[29] = 0  # Reserved

            # Write patch 2
            result[30] = self.patch2_src & 0x7F
            result[31] = self.patch2_dest & 0x7F
            result[32] = (self.patch2_scale >> 7) & 0x7F
            result[33] = self.patch2_thresh & 0x7F
            result[34] = self.patch2_scale & 0x7F
            result[35] = 0  # Reserved

            logger.info(f"Serialized V3 Setup Preset '{self.name}'")

        except Exception as e:
            logger.exception(f"Error serializing V3 Setup preset: {e}")
            return b'' # Return empty bytes on error

        return bytes(result)

    def to_dict(self) -> Dict[str, Any]:
        """Convert preset to dictionary format."""
        base_dict = super().to_dict()
        base_dict.update({
            "machine_config": self.machine_config,
            "effect_a_num": self.effect_a_num,
            "effect_b_num": self.effect_b_num,
            "lfo_shape": self.lfo_shape,
            "lfo_rate": self.lfo_rate,
            "softknob": self.softknob,
            "io_level1": self.io_level1,
            "io_level2": self.io_level2,
            "io_level3": self.io_level3,
            "io_level4": self.io_level4,
            "io_level5": self.io_level5,
            "io_level6": self.io_level6,
            "patch1_src": self.patch1_src,
            "patch1_dest": self.patch1_dest,
            "patch1_scale": self.patch1_scale,
            "patch1_thresh": self.patch1_thresh,
            "patch2_src": self.patch2_src,
            "patch2_dest": self.patch2_dest,
            "patch2_scale": self.patch2_scale,
            "patch2_thresh": self.patch2_thresh,
            "left_meter_assign": self.left_meter_assign,
            "right_meter_assign": self.right_meter_assign
        })
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SetupPresetV3':
        """Create preset from dictionary data."""
        preset = cls()
        preset.name = data.get("name", "Untitled Setup")
        for key, value in data.items():
            if hasattr(preset, key):
                 try:
                      setattr(preset, key, int(value)) # Attempt to cast to int
                 except (ValueError, TypeError):
                      logger.warning(f"Could not set setup param '{key}' from dict value '{value}'")
            # else: # Be less noisy about extra keys from frontend
            #      logger.warning(f"Attribute '{key}' from dict not found in SetupPresetV3")
        return preset

# --- Add V1 Preset Classes if needed ---
# @dataclass
# class M300EffectV1_02(BasePreset): ...
# @dataclass

# --- Map for Bulk Data Types --- 
# (Message Class, Type Byte) -> (Type String, Class Name)
# TODO: Add V1 types if needed
BULK_TYPE_MAP = {
    (0, 0x32): ("Active Setup V3.00", "SetupPresetV3"),
    (0, 0x33): ("Active Effect A V3.00", "EffectPresetV3"),
    (0, 0x34): ("Active Effect B V3.00", "EffectPresetV3"),
    (1, 0x20): ("Stored Setup V3.00", "SetupPresetV3"),
    (1, 0x30): ("Stored Effect V3.00", "EffectPresetV3"),
    (1, 0x40): ("Preset Setup V3.00", "SetupPresetV3"), # Class 1 according to manual examples
    (1, 0x50): ("Preset Effect V3.00", "EffectPresetV3"), # Class 1 according to manual examples
}

# class M300SetupV1_02(BasePreset): ...

# --- Update PRESET_CLASS_MAP if V1 classes are added ---
PRESET_CLASS_MAP = {
    "M300SetupV3_00": SetupPresetV3,
    "M300EffectV3_00": EffectPresetV3,
    # "M300SetupV1_02": M300SetupV1_02,
    # "M300EffectV1_02": M300EffectV1_02,
}

# --- Update BULK_TYPE_MAP if V1 types are added ---
# (Already defined in midi.utils, keep consistent)

# Map preset class names (as strings) back to the actual classes
# Used by the controller to instantiate the correct class after parsing SysEx
PRESET_CLASS_MAP = {
    "SetupPresetV3": SetupPresetV3,
    "EffectPresetV3": EffectPresetV3
}

# BULK_TYPE_MAP = { ... }
