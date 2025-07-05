"""gRPC client for scheduler service."""

import logging
from typing import Dict, List, Optional, Any
import grpc
from google.protobuf import struct_pb2, timestamp_pb2
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import generated proto stubs
try:
    from shared.proto_stubs import scheduler_service_pb2
    from shared.proto_stubs import scheduler_service_pb2_grpc
    PROTO_AVAILABLE = True
except ImportError:
    logger.warning("Scheduler proto stubs not found. gRPC client will not be available.")
    PROTO_AVAILABLE = False


class SchedulerClient:
    """gRPC client for scheduler microservice."""
    
    def __init__(self, endpoint: str = "localhost:50056"):
        self.endpoint = endpoint
        self.channel = None
        self.stub = None
        
        if PROTO_AVAILABLE:
            self._connect()
    
    def _connect(self):
        """Establish gRPC connection."""
        self.channel = grpc.aio.insecure_channel(self.endpoint)
        self.stub = scheduler_service_pb2_grpc.SchedulerServiceStub(self.channel)
    
    async def close(self):
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
    
    async def create_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new scheduled job."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Scheduler gRPC client not available")
        
        try:
            # Convert dict to proto message
            job_proto = self._dict_to_job_proto(job)
            request = scheduler_service_pb2.CreateJobRequest(job=job_proto)
            
            # Make gRPC call
            response = await self.stub.CreateJob(request)
            
            # Convert proto to dict
            return self._job_proto_to_dict(response.job)
            
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error creating job: {e}")
            raise
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a job by ID."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Scheduler gRPC client not available")
        
        try:
            request = scheduler_service_pb2.GetJobRequest(job_id=job_id)
            response = await self.stub.GetJob(request)
            return self._job_proto_to_dict(response.job)
            
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            logger.error(f"gRPC error getting job: {e}")
            raise
    
    async def update_job(self, job_id: str, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing job."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Scheduler gRPC client not available")
        
        try:
            job_proto = self._dict_to_job_proto(job)
            request = scheduler_service_pb2.UpdateJobRequest(
                job_id=job_id,
                job=job_proto
            )
            response = await self.stub.UpdateJob(request)
            return self._job_proto_to_dict(response.job)
            
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            logger.error(f"gRPC error updating job: {e}")
            raise
    
    async def delete_job(self, job_id: str) -> bool:
        """Delete a job."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Scheduler gRPC client not available")
        
        try:
            request = scheduler_service_pb2.DeleteJobRequest(job_id=job_id)
            response = await self.stub.DeleteJob(request)
            return response.success
            
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error deleting job: {e}")
            raise
    
    async def list_jobs(
        self,
        page: int = 1,
        page_size: int = 50,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
        enabled_only: bool = False
    ) -> tuple[List[Dict[str, Any]], int]:
        """List jobs with filtering and pagination."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Scheduler gRPC client not available")
        
        try:
            request = scheduler_service_pb2.ListJobsRequest(
                page=page,
                page_size=page_size,
                tags=tags or [],
                status=status,
                enabled_only=enabled_only
            )
            response = await self.stub.ListJobs(request)
            
            jobs = [self._job_proto_to_dict(job) for job in response.jobs]
            return jobs, response.total
            
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error listing jobs: {e}")
            raise
    
    async def run_job(self, job_id: str, override_parameters: Optional[Dict] = None) -> str:
        """Manually trigger a job execution."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Scheduler gRPC client not available")
        
        try:
            request = scheduler_service_pb2.RunJobRequest(job_id=job_id)
            
            if override_parameters:
                struct = struct_pb2.Struct()
                struct.update(override_parameters)
                request.override_parameters.CopyFrom(struct)
            
            response = await self.stub.RunJob(request)
            return response.execution_id
            
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error running job: {e}")
            raise
    
    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a job."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Scheduler gRPC client not available")
        
        try:
            request = scheduler_service_pb2.GetJobStatusRequest(job_id=job_id)
            response = await self.stub.GetJobStatus(request)
            
            return {
                "job_id": response.job_id,
                "status": response.status,
                "current_execution": self._execution_proto_to_dict(response.current_execution)
                    if response.HasField("current_execution") else None,
                "next_run_time": self._timestamp_to_datetime(response.next_run_time)
                    if response.HasField("next_run_time") else None
            }
            
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            logger.error(f"gRPC error getting job status: {e}")
            raise
    
    async def get_job_history(
        self,
        job_id: str,
        limit: int = 50,
        status_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get execution history for a job."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Scheduler gRPC client not available")
        
        try:
            request = scheduler_service_pb2.GetJobHistoryRequest(
                job_id=job_id,
                limit=limit,
                status_filter=status_filter
            )
            response = await self.stub.GetJobHistory(request)
            
            return [self._execution_proto_to_dict(e) for e in response.executions]
            
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error getting job history: {e}")
            raise
    
    def _dict_to_job_proto(self, job_dict: Dict[str, Any]) -> Any:
        """Convert dict to Job proto message."""
        if not PROTO_AVAILABLE:
            return None
        
        job = scheduler_service_pb2.Job()
        
        # Basic fields
        if "id" in job_dict:
            job.id = job_dict["id"]
        if "name" in job_dict:
            job.name = job_dict["name"]
        if "description" in job_dict:
            job.description = job_dict["description"]
        if "enabled" in job_dict:
            job.enabled = job_dict["enabled"]
        if "status" in job_dict:
            job.status = job_dict["status"]
        
        # Schedule
        schedule = job_dict.get("schedule", {})
        if "cron_expression" in schedule:
            job.cron.cron_expression = schedule["cron_expression"]
            job.cron.timezone = schedule.get("timezone", "UTC")
        elif "interval_seconds" in schedule:
            job.interval.interval_seconds = schedule["interval_seconds"]
            if "start_time" in schedule:
                job.interval.start_time.CopyFrom(
                    self._datetime_to_timestamp(schedule["start_time"])
                )
        elif "run_at" in schedule:
            job.one_time.run_at.CopyFrom(
                self._datetime_to_timestamp(schedule["run_at"])
            )
        
        # Config
        config = job_dict.get("config", {})
        if "job_type" in config:
            job.config.job_type = config["job_type"]
        if "parameters" in config:
            job.config.parameters.update(config["parameters"])
        if "max_retries" in config:
            job.config.max_retries = config["max_retries"]
        if "retry_delay_seconds" in config:
            job.config.retry_delay_seconds = config["retry_delay_seconds"]
        if "timeout_seconds" in config:
            job.config.timeout_seconds = config["timeout_seconds"]
        if "tags" in config:
            job.config.tags.extend(config["tags"])
        
        return job
    
    def _job_proto_to_dict(self, job_proto: Any) -> Dict[str, Any]:
        """Convert Job proto message to dict."""
        if not job_proto:
            return {}
        
        result = {
            "id": job_proto.id,
            "name": job_proto.name,
            "description": job_proto.description,
            "enabled": job_proto.enabled,
            "status": job_proto.status,
            "created_at": self._timestamp_to_datetime(job_proto.created_at),
            "updated_at": self._timestamp_to_datetime(job_proto.updated_at),
        }
        
        # Schedule
        if job_proto.HasField("cron"):
            result["schedule"] = {
                "cron_expression": job_proto.cron.cron_expression,
                "timezone": job_proto.cron.timezone
            }
        elif job_proto.HasField("interval"):
            result["schedule"] = {
                "interval_seconds": job_proto.interval.interval_seconds
            }
            if job_proto.interval.HasField("start_time"):
                result["schedule"]["start_time"] = self._timestamp_to_datetime(
                    job_proto.interval.start_time
                )
        elif job_proto.HasField("one_time"):
            result["schedule"] = {
                "run_at": self._timestamp_to_datetime(job_proto.one_time.run_at)
            }
        
        # Config
        result["config"] = {
            "job_type": job_proto.config.job_type,
            "parameters": dict(job_proto.config.parameters),
            "max_retries": job_proto.config.max_retries,
            "retry_delay_seconds": job_proto.config.retry_delay_seconds,
            "timeout_seconds": job_proto.config.timeout_seconds,
            "tags": list(job_proto.config.tags)
        }
        
        # Optional fields
        if job_proto.HasField("next_run_time"):
            result["next_run_time"] = self._timestamp_to_datetime(job_proto.next_run_time)
        if job_proto.HasField("last_run_time"):
            result["last_run_time"] = self._timestamp_to_datetime(job_proto.last_run_time)
        
        return result
    
    def _execution_proto_to_dict(self, exec_proto: Any) -> Dict[str, Any]:
        """Convert JobExecution proto message to dict."""
        if not exec_proto:
            return {}
        
        result = {
            "id": exec_proto.id,
            "job_id": exec_proto.job_id,
            "started_at": self._timestamp_to_datetime(exec_proto.started_at),
            "status": exec_proto.status,
            "retry_count": exec_proto.retry_count
        }
        
        if exec_proto.HasField("finished_at"):
            result["finished_at"] = self._timestamp_to_datetime(exec_proto.finished_at)
        if exec_proto.error_message:
            result["error_message"] = exec_proto.error_message
        if exec_proto.HasField("result"):
            result["result"] = dict(exec_proto.result)
        
        return result
    
    def _datetime_to_timestamp(self, dt: datetime) -> timestamp_pb2.Timestamp:
        """Convert datetime to protobuf timestamp."""
        ts = timestamp_pb2.Timestamp()
        ts.FromDatetime(dt)
        return ts
    
    def _timestamp_to_datetime(self, ts: timestamp_pb2.Timestamp) -> datetime:
        """Convert protobuf timestamp to datetime."""
        return ts.ToDatetime()