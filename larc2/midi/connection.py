"""Connection management for MIDI operations."""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Callable, Dict, List
import logging

logger = logging.getLogger(__name__)

@dataclass
class ConnectionConfig:
    """Connection configuration."""
    retry_delay: float = 5.0
    max_retries: int = 3
    timeout: float = 10.0
    keepalive_interval: float = 30.0

class ConnectionManager:
    """Manages connection state and reconnection logic."""
    
    def __init__(self, config: Optional[ConnectionConfig] = None):
        """Initialize connection manager."""
        self.config = config or ConnectionConfig()
        self._connected = False
        self._retry_count = 0
        self._last_keepalive = 0.0
        self._handlers: Dict[str, List[Callable]] = {
            'connect': [],
            'disconnect': [],
            'error': [],
            'timeout': []
        }
        self._reconnect_task: Optional[asyncio.Task] = None
        
    @property
    def connected(self) -> bool:
        """Get connection state."""
        return self._connected
        
    @property
    def can_retry(self) -> bool:
        """Check if retry is possible."""
        return self._retry_count < self.config.max_retries
        
    def add_handler(self, event: str, handler: Callable) -> None:
        """Add event handler."""
        if event in self._handlers:
            self._handlers[event].append(handler)
            
    def remove_handler(self, event: str, handler: Callable) -> None:
        """Remove event handler."""
        if event in self._handlers and handler in self._handlers[event]:
            self._handlers[event].remove(handler)
            
    async def _notify(self, event: str, *args, **kwargs) -> None:
        """Notify event handlers."""
        for handler in self._handlers.get(event, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args, **kwargs)
                else:
                    handler(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {event} handler: {e}")
                
    async def connect(self) -> bool:
        """Initiate connection."""
        if self._connected:
            return True
            
        try:
            self._retry_count += 1
            await self._notify('connect')
            self._connected = True
            self._retry_count = 0
            self._last_keepalive = time.time()
            return True
            
        except Exception as e:
            await self._notify('error', str(e))
            if self.can_retry:
                self._schedule_reconnect()
            return False
            
    def disconnect(self) -> None:
        """Disconnect and cleanup."""
        if self._reconnect_task:
            self._reconnect_task.cancel()
            
        self._connected = False
        asyncio.create_task(self._notify('disconnect'))
        
    def _schedule_reconnect(self) -> None:
        """Schedule reconnection attempt."""
        if self._reconnect_task and not self._reconnect_task.done():
            return
            
        async def reconnect():
            await asyncio.sleep(self.config.retry_delay)
            if not self._connected and self.can_retry:
                await self.connect()
                
        self._reconnect_task = asyncio.create_task(reconnect())
        
    async def check_keepalive(self) -> None:
        """Check connection keepalive."""
        if self._connected:
            elapsed = time.time() - self._last_keepalive
            if elapsed > self.config.keepalive_interval:
                await self._notify('timeout')
                self.disconnect()
                if self.can_retry:
                    self._schedule_reconnect()
                    
    def update_keepalive(self) -> None:
        """Update last keepalive timestamp."""
        self._last_keepalive = time.time()
        
    async def wait_until_connected(self, timeout: Optional[float] = None) -> bool:
        """Wait until connection is established."""
        if self._connected:
            return True
            
        timeout = timeout or self.config.timeout
        try:
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self._connected:
                    return True
                await asyncio.sleep(0.1)
            return False
        except asyncio.CancelledError:
            return self._connected
