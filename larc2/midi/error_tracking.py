"""Error tracking for MIDI operations."""

import time
from typing import Dict, List, Optional, NamedTuple
from collections import deque
import logging

logger = logging.getLogger(__name__)

class ErrorEntry(NamedTuple):
    """Error entry with timestamp and context."""
    timestamp: float
    source: str
    message: str
    details: Optional[str] = None

class ErrorTracker:
    """Tracks errors and their frequency."""
    
    def __init__(self, max_history: int = 100, window_seconds: float = 300):
        """Initialize error tracker.
        
        Args:
            max_history: Maximum number of errors to keep in history
            window_seconds: Time window for error rate calculation (seconds)
        """
        self._history: deque[ErrorEntry] = deque(maxlen=max_history)
        self._error_counts: Dict[str, int] = {}
        self._window_seconds = window_seconds
        
    def add_error(self, source: str, message: str, details: Optional[str] = None) -> None:
        """Add an error to the tracker."""
        entry = ErrorEntry(time.time(), source, message, details)
        self._history.append(entry)
        
        # Update error counts
        key = f"{source}:{message}"
        self._error_counts[key] = self._error_counts.get(key, 0) + 1
        
        # Log the error
        if details:
            logger.error(f"{source}: {message} - {details}")
        else:
            logger.error(f"{source}: {message}")
            
    def get_recent_errors(self, seconds: Optional[float] = None) -> List[ErrorEntry]:
        """Get errors from the last N seconds."""
        if not seconds:
            seconds = self._window_seconds
            
        cutoff = time.time() - seconds
        return [e for e in self._history if e.timestamp >= cutoff]
        
    def get_error_rate(self, source: str) -> float:
        """Get error rate (errors/minute) for a source."""
        recent = self.get_recent_errors()
        source_errors = [e for e in recent if e.source == source]
        
        if not source_errors:
            return 0.0
            
        window = min(self._window_seconds, 
                    time.time() - source_errors[0].timestamp)
        return len(source_errors) * 60 / window if window > 0 else 0
        
    def clear_history(self) -> None:
        """Clear error history."""
        self._history.clear()
        self._error_counts.clear()
        
    def get_most_frequent(self, limit: int = 5) -> List[tuple[str, int]]:
        """Get most frequent errors."""
        return sorted(
            self._error_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]

    def should_reconnect(self, source: str) -> bool:
        """Determine if connection should be reset based on error rate."""
        error_rate = self.get_error_rate(source)
        return error_rate >= 10  # More than 10 errors per minute
