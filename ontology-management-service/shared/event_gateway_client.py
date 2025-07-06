"""gRPC client for event gateway service."""

import logging
from typing import Dict, List, Optional, Any, AsyncIterator
import grpc
from google.protobuf import struct_pb2, timestamp_pb2
from datetime import datetime
from cloudevents.http import CloudEvent, to_dict, from_dict

logger = logging.getLogger(__name__)

# Try to import generated proto stubs
try:
    from shared.proto_stubs import event_gateway_pb2
    from shared.proto_stubs import event_gateway_pb2_grpc
    PROTO_AVAILABLE = True
except ImportError:
    logger.warning("Event gateway proto stubs not found. gRPC client will not be available.")
    PROTO_AVAILABLE = False


class EventGatewayClient:
    """gRPC client for event gateway microservice."""
    
    def __init__(self, endpoint: str = "localhost:50057"):
        self.endpoint = endpoint
        self.channel = None
        self.stub = None
        
        if PROTO_AVAILABLE:
            self._connect()
    
    def _connect(self):
        """Establish gRPC connection."""
        self.channel = grpc.aio.insecure_channel(self.endpoint)
        self.stub = event_gateway_pb2_grpc.EventGatewayServiceStub(self.channel)
    
    async def close(self):
        """Close gRPC connection."""
        if self.channel:
            await self.channel.close()
    
    async def publish_event(
        self,
        event: CloudEvent,
        stream: str = "events",
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Publish a CloudEvent."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Event gateway gRPC client not available")
        
        try:
            # Convert CloudEvent to proto
            cloud_event_proto = self._cloudevent_to_proto(event)
            
            request = event_gateway_pb2.PublishEventRequest(
                event=cloud_event_proto,
                stream=stream,
                headers=headers or {}
            )
            
            # Make gRPC call
            response = await self.stub.PublishEvent(request)
            
            return {
                "event_id": response.event_id,
                "sequence": response.sequence,
                "published_at": self._timestamp_to_datetime(response.published_at)
            }
            
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error publishing event: {e}")
            raise
    
    async def publish_events_batch(
        self,
        events: List[CloudEvent],
        stream: str = "events",
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Publish multiple events."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Event gateway gRPC client not available")
        
        try:
            # Convert CloudEvents to proto
            cloud_events_proto = [self._cloudevent_to_proto(e) for e in events]
            
            request = event_gateway_pb2.PublishEventsBatchRequest(
                events=cloud_events_proto,
                stream=stream,
                headers=headers or {}
            )
            
            # Make gRPC call
            response = await self.stub.PublishEventsBatch(request)
            
            return {
                "results": [
                    {
                        "event_id": r.event_id,
                        "sequence": r.sequence,
                        "published_at": self._timestamp_to_datetime(r.published_at)
                    }
                    for r in response.results
                ],
                "succeeded": response.succeeded,
                "failed": response.failed
            }
            
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error publishing events batch: {e}")
            raise
    
    async def subscribe(
        self,
        consumer_id: str,
        event_types: List[str] = None,
        stream: str = "events",
        durable_name: Optional[str] = None,
        start_sequence: Optional[int] = None,
        deliver_new: bool = True,
        max_in_flight: int = 100,
        ack_wait_seconds: int = 30
    ) -> str:
        """Create a subscription and return subscription ID."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Event gateway gRPC client not available")
        
        try:
            request = event_gateway_pb2.SubscribeRequest(
                consumer_id=consumer_id,
                event_types=event_types or [],
                stream=stream,
                durable_name=durable_name,
                max_in_flight=max_in_flight,
                ack_wait_seconds=ack_wait_seconds
            )
            
            # Set start position
            if start_sequence:
                request.start_sequence = start_sequence
            elif deliver_new:
                request.deliver_new = True
            else:
                request.deliver_all = True
            
            # Create subscription (returns stream)
            response_stream = self.stub.Subscribe(request)
            
            # For now, return a subscription ID
            # In a real implementation, we'd manage the stream
            return f"{consumer_id}_{stream}_grpc"
            
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error creating subscription: {e}")
            raise
    
    async def stream_events(
        self,
        subscription_id: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream events for a subscription."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Event gateway gRPC client not available")
        
        # In a real implementation, we'd retrieve the stream created in subscribe()
        # For now, create a new subscription request
        consumer_id = subscription_id.split("_")[0]
        stream = subscription_id.split("_")[1] if "_" in subscription_id else "events"
        
        request = event_gateway_pb2.SubscribeRequest(
            consumer_id=consumer_id,
            stream=stream,
            deliver_new=True
        )
        
        try:
            # Get event stream
            async for event_proto in self.stub.Subscribe(request):
                yield self._event_proto_to_dict(event_proto)
                
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error streaming events: {e}")
            raise
    
    async def unsubscribe(self, consumer_id: str, subscription_id: str) -> bool:
        """Unsubscribe from events."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Event gateway gRPC client not available")
        
        try:
            request = event_gateway_pb2.UnsubscribeRequest(
                consumer_id=consumer_id,
                subscription_id=subscription_id
            )
            
            response = await self.stub.Unsubscribe(request)
            return response.success
            
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error unsubscribing: {e}")
            raise
    
    async def register_webhook(self, webhook: Dict[str, Any]) -> Dict[str, Any]:
        """Register a new webhook."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Event gateway gRPC client not available")
        
        try:
            webhook_proto = self._dict_to_webhook_proto(webhook)
            request = event_gateway_pb2.RegisterWebhookRequest(webhook=webhook_proto)
            
            response = await self.stub.RegisterWebhook(request)
            return self._webhook_proto_to_dict(response.webhook)
            
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error registering webhook: {e}")
            raise
    
    async def list_webhooks(
        self,
        event_types: Optional[List[str]] = None,
        enabled_only: bool = False
    ) -> List[Dict[str, Any]]:
        """List webhooks."""
        if not PROTO_AVAILABLE or not self.stub:
            raise RuntimeError("Event gateway gRPC client not available")
        
        try:
            request = event_gateway_pb2.ListWebhooksRequest(
                event_types=event_types or [],
                enabled_only=enabled_only
            )
            
            response = await self.stub.ListWebhooks(request)
            return [self._webhook_proto_to_dict(w) for w in response.webhooks]
            
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error listing webhooks: {e}")
            raise
    
    def _cloudevent_to_proto(self, event: CloudEvent) -> Any:
        """Convert CloudEvent to proto message."""
        if not PROTO_AVAILABLE:
            return None
        
        proto = event_gateway_pb2.CloudEvent()
        
        # Required fields
        proto.id = event.get("id", "")
        proto.source = event.get("source", "")
        proto.spec_version = event.get("specversion", "1.0")
        proto.type = event.get("type", "")
        
        # Optional fields
        if "datacontenttype" in event:
            proto.data_content_type = event["datacontenttype"]
        if "dataschema" in event:
            proto.data_schema = event["dataschema"]
        if "subject" in event:
            proto.subject = event["subject"]
        if "time" in event:
            proto.time.CopyFrom(self._datetime_to_timestamp(
                datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
            ))
        
        # Data
        data = event.get("data")
        if isinstance(data, dict):
            struct = struct_pb2.Struct()
            struct.update(data)
            proto.data_json.CopyFrom(struct)
        elif isinstance(data, str):
            proto.data_text = data
        elif isinstance(data, bytes):
            proto.data_binary = data
        
        # Extensions
        for key, value in event.items():
            if key not in ["id", "source", "specversion", "type", "datacontenttype",
                          "dataschema", "subject", "time", "data"]:
                proto.extensions[key] = str(value)
        
        return proto
    
    def _event_proto_to_dict(self, event_proto: Any) -> Dict[str, Any]:
        """Convert Event proto to dict."""
        if not event_proto:
            return {}
        
        # Convert CloudEvent
        cloud_event = {}
        ce = event_proto.cloud_event
        
        cloud_event["id"] = ce.id
        cloud_event["source"] = ce.source
        cloud_event["specversion"] = ce.spec_version
        cloud_event["type"] = ce.type
        
        if ce.HasField("data_content_type"):
            cloud_event["datacontenttype"] = ce.data_content_type
        if ce.HasField("data_schema"):
            cloud_event["dataschema"] = ce.data_schema
        if ce.HasField("subject"):
            cloud_event["subject"] = ce.subject
        if ce.HasField("time"):
            cloud_event["time"] = self._timestamp_to_datetime(ce.time).isoformat()
        
        # Data
        if ce.HasField("data_json"):
            cloud_event["data"] = dict(ce.data_json)
        elif ce.HasField("data_text"):
            cloud_event["data"] = ce.data_text
        elif ce.HasField("data_binary"):
            cloud_event["data"] = ce.data_binary
        
        # Extensions
        cloud_event.update(ce.extensions)
        
        # Metadata
        metadata = {
            "stream_name": event_proto.metadata.stream_name,
            "sequence": event_proto.metadata.sequence,
            "received_at": self._timestamp_to_datetime(event_proto.metadata.received_at),
            "delivery_count": event_proto.metadata.delivery_count,
            "headers": dict(event_proto.metadata.headers)
        }
        
        return {
            "cloud_event": cloud_event,
            "metadata": metadata
        }
    
    def _dict_to_webhook_proto(self, webhook_dict: Dict[str, Any]) -> Any:
        """Convert dict to Webhook proto."""
        if not PROTO_AVAILABLE:
            return None
        
        proto = event_gateway_pb2.Webhook()
        
        if "id" in webhook_dict:
            proto.id = webhook_dict["id"]
        proto.name = webhook_dict["name"]
        proto.url = webhook_dict["url"]
        proto.event_types.extend(webhook_dict.get("event_types", []))
        proto.enabled = webhook_dict.get("enabled", True)
        
        # Config
        config = webhook_dict.get("config", {})
        proto.config.headers.update(config.get("headers", {}))
        if "secret" in config:
            proto.config.secret = config["secret"]
        proto.config.timeout_seconds = config.get("timeout_seconds", 30)
        proto.config.max_retries = config.get("max_retries", 3)
        proto.config.retry_delay_seconds = config.get("retry_delay_seconds", 60)
        proto.config.verify_ssl = config.get("verify_ssl", True)
        
        return proto
    
    def _webhook_proto_to_dict(self, webhook_proto: Any) -> Dict[str, Any]:
        """Convert Webhook proto to dict."""
        if not webhook_proto:
            return {}
        
        result = {
            "id": webhook_proto.id,
            "name": webhook_proto.name,
            "url": webhook_proto.url,
            "event_types": list(webhook_proto.event_types),
            "enabled": webhook_proto.enabled,
            "config": {
                "headers": dict(webhook_proto.config.headers),
                "timeout_seconds": webhook_proto.config.timeout_seconds,
                "max_retries": webhook_proto.config.max_retries,
                "retry_delay_seconds": webhook_proto.config.retry_delay_seconds,
                "verify_ssl": webhook_proto.config.verify_ssl
            }
        }
        
        if webhook_proto.config.secret:
            result["config"]["secret"] = webhook_proto.config.secret
        
        if webhook_proto.HasField("created_at"):
            result["created_at"] = self._timestamp_to_datetime(webhook_proto.created_at)
        if webhook_proto.HasField("updated_at"):
            result["updated_at"] = self._timestamp_to_datetime(webhook_proto.updated_at)
        
        # Stats
        if webhook_proto.HasField("stats"):
            result["stats"] = {
                "total_deliveries": webhook_proto.stats.total_deliveries,
                "successful_deliveries": webhook_proto.stats.successful_deliveries,
                "failed_deliveries": webhook_proto.stats.failed_deliveries,
                "average_response_time_ms": webhook_proto.stats.average_response_time_ms
            }
            if webhook_proto.stats.HasField("last_delivery_at"):
                result["stats"]["last_delivery_at"] = self._timestamp_to_datetime(
                    webhook_proto.stats.last_delivery_at
                )
            if webhook_proto.stats.last_delivery_status:
                result["stats"]["last_delivery_status"] = webhook_proto.stats.last_delivery_status
        
        return result
    
    def _datetime_to_timestamp(self, dt: datetime) -> timestamp_pb2.Timestamp:
        """Convert datetime to protobuf timestamp."""
        ts = timestamp_pb2.Timestamp()
        ts.FromDatetime(dt)
        return ts
    
    def _timestamp_to_datetime(self, ts: timestamp_pb2.Timestamp) -> datetime:
        """Convert protobuf timestamp to datetime."""
        return ts.ToDatetime()