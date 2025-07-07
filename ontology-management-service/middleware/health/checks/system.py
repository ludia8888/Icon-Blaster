"""
System resource health check implementation
"""
import psutil
import asyncio
from typing import Dict, Any, Optional
from .base import HealthCheck
from ..models import HealthCheckResult, HealthStatus


class SystemHealthCheck(HealthCheck):
    """Health check for system resources (CPU, memory, disk)"""
    
    def __init__(
        self,
        name: str = "system",
        timeout: float = 2.0,
        cpu_threshold: float = 80.0,
        memory_threshold: float = 85.0,
        disk_threshold: float = 90.0
    ):
        super().__init__(name, timeout)
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.disk_threshold = disk_threshold
    
    async def check(self) -> HealthCheckResult:
        """Check system resource health"""
        try:
            # Gather system metrics
            metrics = await self._gather_metrics()
            
            # Evaluate health based on thresholds
            status, issues = self._evaluate_health(metrics)
            
            # Create appropriate message
            if status == HealthStatus.HEALTHY:
                message = "System resources are healthy"
            elif status == HealthStatus.DEGRADED:
                message = f"System resources degraded: {', '.join(issues)}"
            else:
                message = f"System resources critical: {', '.join(issues)}"
            
            return self.create_result(
                status=status,
                message=message,
                details=metrics
            )
            
        except Exception as e:
            return self.create_result(
                status=HealthStatus.UNKNOWN,
                message=f"Failed to check system resources: {str(e)}",
                details={"error": str(e)}
            )
    
    async def _gather_metrics(self) -> Dict[str, Any]:
        """Gather system metrics asynchronously"""
        loop = asyncio.get_event_loop()
        
        # CPU metrics
        cpu_percent = await loop.run_in_executor(None, psutil.cpu_percent, 1)
        cpu_count = psutil.cpu_count()
        
        # Memory metrics
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        # Disk metrics
        disk_partitions = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_partitions.append({
                    "mountpoint": partition.mountpoint,
                    "device": partition.device,
                    "fstype": partition.fstype,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent": usage.percent
                })
            except PermissionError:
                # Skip partitions we can't access
                continue
        
        # Network I/O
        net_io = psutil.net_io_counters()
        
        # Process info
        current_process = psutil.Process()
        process_info = {
            "pid": current_process.pid,
            "cpu_percent": current_process.cpu_percent(),
            "memory_mb": round(current_process.memory_info().rss / (1024**2), 2),
            "num_threads": current_process.num_threads(),
            "num_fds": current_process.num_fds() if hasattr(current_process, "num_fds") else None
        }
        
        return {
            "cpu": {
                "percent": cpu_percent,
                "count": cpu_count,
                "load_average": psutil.getloadavg() if hasattr(psutil, "getloadavg") else None
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "percent": memory.percent,
                "swap_percent": swap.percent
            },
            "disk": disk_partitions,
            "network": {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "errin": net_io.errin,
                "errout": net_io.errout,
                "dropin": net_io.dropin,
                "dropout": net_io.dropout
            },
            "process": process_info
        }
    
    def _evaluate_health(
        self, 
        metrics: Dict[str, Any]
    ) -> tuple[HealthStatus, list[str]]:
        """Evaluate system health based on metrics"""
        issues = []
        critical_issues = []
        
        # Check CPU
        cpu_percent = metrics["cpu"]["percent"]
        if cpu_percent > self.cpu_threshold:
            if cpu_percent > 95:
                critical_issues.append(f"CPU usage critical: {cpu_percent}%")
            else:
                issues.append(f"CPU usage high: {cpu_percent}%")
        
        # Check Memory
        memory_percent = metrics["memory"]["percent"]
        if memory_percent > self.memory_threshold:
            if memory_percent > 95:
                critical_issues.append(f"Memory usage critical: {memory_percent}%")
            else:
                issues.append(f"Memory usage high: {memory_percent}%")
        
        # Check Swap
        swap_percent = metrics["memory"]["swap_percent"]
        if swap_percent > 50:
            issues.append(f"Swap usage high: {swap_percent}%")
        
        # Check Disk
        for disk in metrics["disk"]:
            if disk["percent"] > self.disk_threshold:
                if disk["percent"] > 95:
                    critical_issues.append(
                        f"Disk {disk['mountpoint']} critical: {disk['percent']}%"
                    )
                else:
                    issues.append(
                        f"Disk {disk['mountpoint']} high: {disk['percent']}%"
                    )
        
        # Check network errors
        net = metrics["network"]
        total_errors = net["errin"] + net["errout"]
        total_drops = net["dropin"] + net["dropout"]
        if total_errors > 1000:
            issues.append(f"Network errors detected: {total_errors}")
        if total_drops > 1000:
            issues.append(f"Network packet drops: {total_drops}")
        
        # Determine overall status
        if critical_issues:
            return HealthStatus.UNHEALTHY, critical_issues + issues
        elif issues:
            return HealthStatus.DEGRADED, issues
        else:
            return HealthStatus.HEALTHY, []