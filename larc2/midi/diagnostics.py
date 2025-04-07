"""System diagnostics for MIDI operations."""

import os
import sys
import time
import platform
import psutil
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import asyncio

logger = logging.getLogger(__name__)

@dataclass
class SystemMetrics:
    """System resource metrics."""
    cpu_percent: float
    memory_percent: float
    disk_usage_percent: float
    network_connections: int
    timestamp: float

@dataclass
class MIDIMetrics:
    """MIDI performance metrics."""
    message_rate: float  # messages/second
    error_rate: float   # errors/minute
    latency_ms: float   # average message latency
    queue_size: int     # current message queue size
    timestamp: float

class Diagnostics:
    """System and MIDI diagnostics."""
    
    def __init__(self, history_size: int = 100):
        """Initialize diagnostics.
        
        Args:
            history_size: Number of historical metrics to keep
        """
        self._history_size = history_size
        self._system_metrics: List[SystemMetrics] = []
        self._midi_metrics: List[MIDIMetrics] = []
        self._message_times: List[float] = []
        self._error_times: List[float] = []
        self._start_time = time.time()
        
    def collect_system_metrics(self) -> SystemMetrics:
        """Collect current system metrics."""
        try:
            metrics = SystemMetrics(
                cpu_percent=psutil.cpu_percent(),
                memory_percent=psutil.virtual_memory().percent,
                disk_usage_percent=psutil.disk_usage('/').percent,
                network_connections=len(psutil.net_connections()),
                timestamp=time.time()
            )
            
            self._system_metrics.append(metrics)
            if len(self._system_metrics) > self._history_size:
                self._system_metrics.pop(0)
                
            return metrics
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return None
            
    def collect_midi_metrics(self, queue_size: int) -> MIDIMetrics:
        """Collect current MIDI metrics."""
        now = time.time()
        window = 60.0  # 1 minute window
        
        # Clean old message times
        self._message_times = [t for t in self._message_times if now - t <= window]
        self._error_times = [t for t in self._error_times if now - t <= window]
        
        # Calculate metrics
        message_rate = len(self._message_times) / window if self._message_times else 0
        error_rate = len(self._error_times) / window * 60 if self._error_times else 0
        
        # Calculate latency if we have message timestamps
        latencies = []
        for i in range(1, len(self._message_times)):
            latencies.append(self._message_times[i] - self._message_times[i-1])
        avg_latency = sum(latencies) / len(latencies) * 1000 if latencies else 0
        
        metrics = MIDIMetrics(
            message_rate=message_rate,
            error_rate=error_rate,
            latency_ms=avg_latency,
            queue_size=queue_size,
            timestamp=now
        )
        
        self._midi_metrics.append(metrics)
        if len(self._midi_metrics) > self._history_size:
            self._midi_metrics.pop(0)
            
        return metrics
        
    def record_message(self):
        """Record a MIDI message timestamp."""
        self._message_times.append(time.time())
        
    def record_error(self):
        """Record a MIDI error timestamp."""
        self._error_times.append(time.time())
        
    def get_system_info(self) -> Dict[str, Any]:
        """Get system information."""
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "python_version": sys.version,
            "cpu_count": psutil.cpu_count(),
            "total_memory": psutil.virtual_memory().total,
            "total_disk": psutil.disk_usage('/').total
        }
        
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate performance report."""
        if not self._midi_metrics:
            return {}
            
        latest_system = self._system_metrics[-1] if self._system_metrics else None
        latest_midi = self._midi_metrics[-1]
        uptime = time.time() - self._start_time
        
        return {
            "uptime_seconds": uptime,
            "message_throughput": latest_midi.message_rate,
            "average_latency_ms": latest_midi.latency_ms,
            "error_rate": latest_midi.error_rate,
            "queue_backlog": latest_midi.queue_size,
            "system_load": {
                "cpu": latest_system.cpu_percent if latest_system else None,
                "memory": latest_system.memory_percent if latest_system else None,
                "disk": latest_system.disk_usage_percent if latest_system else None
            }
        }
        
    def should_throttle(self) -> bool:
        """Check if system is under heavy load and should throttle."""
        if not self._system_metrics:
            return False
            
        latest = self._system_metrics[-1]
        return (latest.cpu_percent > 80 or
                latest.memory_percent > 90 or
                latest.disk_usage_percent > 95)
                
    async def monitor_system(self, interval: float = 1.0):
        """Background task to monitor system metrics."""
        while True:
            try:
                self.collect_system_metrics()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in system monitor: {e}")
                await asyncio.sleep(interval)
                
    def get_historical_metrics(self, 
                             metric_type: str = "system",
                             minutes: float = 5) -> List[Dict[str, Any]]:
        """Get historical metrics for specified time window.
        
        Args:
            metric_type: "system" or "midi"
            minutes: Time window in minutes
        """
        now = time.time()
        cutoff = now - (minutes * 60)
        
        if metric_type == "system":
            metrics = [m for m in self._system_metrics if m.timestamp >= cutoff]
            return [{
                "timestamp": m.timestamp,
                "cpu_percent": m.cpu_percent,
                "memory_percent": m.memory_percent,
                "disk_usage_percent": m.disk_usage_percent,
                "network_connections": m.network_connections
            } for m in metrics]
        else:
            metrics = [m for m in self._midi_metrics if m.timestamp >= cutoff]
            return [{
                "timestamp": m.timestamp,
                "message_rate": m.message_rate,
                "error_rate": m.error_rate,
                "latency_ms": m.latency_ms,
                "queue_size": m.queue_size
            } for m in metrics]
