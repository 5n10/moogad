"""Message validation for MIDI operations."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

class MessageType(Enum):
    PARAMETER_CHANGE = "parameter_change"
    REQUEST_ACTIVE_STATE = "request_active_state"
    SAVE_PRESET = "save_preset"
    LOAD_PRESET = "load_preset"
    GET_MIDI_PORTS = "get_midi_ports"
    CONNECT_MIDI = "connect_midi"
    MIDI_STATUS = "midi_status"
    ERROR = "error"

@dataclass
class ValidationError:
    """Validation error details."""
    field: str
    message: str

class MessageValidator:
    """Validates incoming WebSocket messages."""

    @staticmethod
    def validate_message(data: Dict[str, Any]) -> List[ValidationError]:
        """Validate a message based on its type.
        
        Returns:
            List of validation errors. Empty list means validation passed.
        """
        errors: List[ValidationError] = []
        
        if not isinstance(data, dict):
            return [ValidationError("message", "Message must be a JSON object")]
            
        if "type" not in data:
            return [ValidationError("type", "Message type is required")]
            
        try:
            msg_type = MessageType(data["type"])
        except ValueError:
            return [ValidationError("type", f"Invalid message type: {data['type']}")]
            
        # Validate based on message type
        if msg_type == MessageType.PARAMETER_CHANGE:
            errors.extend(MessageValidator._validate_parameter_change(data))
        elif msg_type == MessageType.SAVE_PRESET:
            errors.extend(MessageValidator._validate_save_preset(data))
        elif msg_type == MessageType.LOAD_PRESET:
            errors.extend(MessageValidator._validate_load_preset(data))
        elif msg_type == MessageType.CONNECT_MIDI:
            errors.extend(MessageValidator._validate_connect_midi(data))
            
        return errors
        
    @staticmethod
    def _validate_parameter_change(data: Dict[str, Any]) -> List[ValidationError]:
        """Validate parameter change message."""
        errors = []
        
        if "domain" not in data:
            errors.append(ValidationError("domain", "Domain is required"))
        elif not isinstance(data["domain"], int):
            errors.append(ValidationError("domain", "Domain must be an integer"))
            
        if "param" not in data:
            errors.append(ValidationError("param", "Parameter number is required"))
        elif not isinstance(data["param"], int):
            errors.append(ValidationError("param", "Parameter number must be an integer"))
            
        if "value" not in data:
            errors.append(ValidationError("value", "Value is required"))
        elif not isinstance(data["value"], int):
            errors.append(ValidationError("value", "Value must be an integer"))
            
        return errors
        
    @staticmethod
    def _validate_save_preset(data: Dict[str, Any]) -> List[ValidationError]:
        """Validate save preset message."""
        errors = []
        
        if "preset" not in data:
            errors.append(ValidationError("preset", "Preset data is required"))
        elif not isinstance(data["preset"], dict):
            errors.append(ValidationError("preset", "Preset must be an object"))
            
        if "register" not in data:
            errors.append(ValidationError("register", "Register number is required"))
        elif not isinstance(data["register"], int):
            errors.append(ValidationError("register", "Register must be an integer"))
        elif not (0 <= data["register"] <= 99):
            errors.append(ValidationError("register", "Register must be between 0 and 99"))
            
        return errors
        
    @staticmethod
    def _validate_load_preset(data: Dict[str, Any]) -> List[ValidationError]:
        """Validate load preset message."""
        errors = []
        
        if "preset" not in data:
            errors.append(ValidationError("preset", "Preset data is required"))
        elif not isinstance(data["preset"], dict):
            errors.append(ValidationError("preset", "Preset must be an object"))
            
        if "slot" in data and data["slot"] not in ["A", "B"]:
            errors.append(ValidationError("slot", "Slot must be 'A' or 'B'"))
            
        return errors
        
    @staticmethod
    def _validate_connect_midi(data: Dict[str, Any]) -> List[ValidationError]:
        """Validate connect MIDI message."""
        errors = []
        
        if "input_port" not in data:
            errors.append(ValidationError("input_port", "Input port is required"))
        elif not isinstance(data["input_port"], str):
            errors.append(ValidationError("input_port", "Input port must be a string"))
            
        if "output_port" not in data:
            errors.append(ValidationError("output_port", "Output port is required"))
        elif not isinstance(data["output_port"], str):
            errors.append(ValidationError("output_port", "Output port must be a string"))
            
        return errors

    @staticmethod
    def format_errors(errors: List[ValidationError]) -> str:
        """Format validation errors into a human-readable message."""
        if not errors:
            return ""
            
        messages = [f"{error.field}: {error.message}" for error in errors]
        return "Validation failed: " + "; ".join(messages)