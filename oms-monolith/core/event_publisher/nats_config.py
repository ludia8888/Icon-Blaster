"""
NATS JetStream Configuration
EventBridge와 동일한 재시도 정책 설정
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
import nats
from nats.js import api


@dataclass
class NATSStreamConfig:
    """NATS Stream 설정"""
    name: str = "OMS_EVENTS"
    subjects: list = None
    max_age: int = 3600  # EventBridge MaximumEventAge와 일치 (1 hour)
    max_deliver: int = 3  # EventBridge MaximumRetryAttempts와 일치
    ack_wait: int = 30  # 30초
    max_msg_size: int = 1048576  # 1MB
    storage: str = "file"
    replicas: int = 3
    retention: str = "workqueue"
    discard: str = "old"
    
    def __post_init__(self):
        if self.subjects is None:
            self.subjects = ["oms.>"]  # 모든 OMS 이벤트
    
    def to_stream_config(self) -> api.StreamConfig:
        """NATS StreamConfig 객체로 변환"""
        return api.StreamConfig(
            name=self.name,
            subjects=self.subjects,
            max_age=self.max_age,
            max_deliver=self.max_deliver,
            ack_wait=self.ack_wait,
            max_msg_size=self.max_msg_size,
            storage=api.StorageType[self.storage.upper()],
            replicas=self.replicas,
            retention=api.RetentionPolicy[self.retention.upper()],
            discard=api.DiscardPolicy[self.discard.upper()]
        )


@dataclass 
class NATSConsumerConfig:
    """NATS Consumer 설정"""
    durable_name: str
    ack_policy: str = "explicit"
    max_deliver: int = 3  # EventBridge와 동일
    ack_wait: int = 30
    max_ack_pending: int = 1000
    deliver_policy: str = "all"
    filter_subject: Optional[str] = None
    
    def to_consumer_config(self) -> api.ConsumerConfig:
        """NATS ConsumerConfig 객체로 변환"""
        config = api.ConsumerConfig(
            durable_name=self.durable_name,
            ack_policy=api.AckPolicy[self.ack_policy.upper()],
            max_deliver=self.max_deliver,
            ack_wait=self.ack_wait,
            max_ack_pending=self.max_ack_pending,
            deliver_policy=api.DeliverPolicy[self.deliver_policy.upper()]
        )
        
        if self.filter_subject:
            config.filter_subject = self.filter_subject
            
        return config


class NATSConfigManager:
    """NATS 설정 관리자"""
    
    @staticmethod
    def get_stream_config(environment: str = "production") -> NATSStreamConfig:
        """환경별 Stream 설정"""
        
        if environment == "production":
            return NATSStreamConfig(
                name="OMS_EVENTS",
                subjects=["oms.>"],
                max_age=3600,  # 1 hour (EventBridge와 동일)
                max_deliver=3,  # EventBridge와 동일
                ack_wait=30,
                replicas=3,
                retention="workqueue"
            )
        elif environment == "staging":
            return NATSStreamConfig(
                name="OMS_EVENTS_STAGING",
                subjects=["oms.staging.>"],
                max_age=3600,
                max_deliver=3,
                ack_wait=30,
                replicas=1,
                retention="workqueue"
            )
        else:  # development
            return NATSStreamConfig(
                name="OMS_EVENTS_DEV",
                subjects=["oms.dev.>"],
                max_age=300,  # 5 minutes
                max_deliver=1,
                ack_wait=10,
                replicas=1,
                retention="workqueue"
            )
    
    @staticmethod
    def get_consumer_config(
        consumer_name: str,
        environment: str = "production"
    ) -> NATSConsumerConfig:
        """환경별 Consumer 설정"""
        
        base_config = {
            "durable_name": consumer_name,
            "ack_policy": "explicit",
            "deliver_policy": "all"
        }
        
        if environment == "production":
            base_config.update({
                "max_deliver": 3,  # EventBridge와 동일
                "ack_wait": 30,
                "max_ack_pending": 1000
            })
        elif environment == "staging":
            base_config.update({
                "max_deliver": 3,
                "ack_wait": 20,
                "max_ack_pending": 500
            })
        else:  # development
            base_config.update({
                "max_deliver": 1,
                "ack_wait": 10,
                "max_ack_pending": 100
            })
        
        return NATSConsumerConfig(**base_config)
    
    @staticmethod
    async def ensure_stream_exists(
        js: nats.js.JetStreamContext,
        config: NATSStreamConfig
    ) -> api.StreamInfo:
        """Stream이 존재하는지 확인하고 없으면 생성"""
        try:
            # Stream 정보 가져오기
            stream_info = await js.stream_info(config.name)
            
            # 설정이 다르면 업데이트
            current_config = stream_info.config
            new_config = config.to_stream_config()
            
            if (current_config.max_age != new_config.max_age or
                current_config.max_deliver != new_config.max_deliver):
                
                # Stream 설정 업데이트
                stream_info = await js.update_stream(
                    name=config.name,
                    config=new_config
                )
                print(f"Updated stream '{config.name}' configuration")
            else:
                print(f"Stream '{config.name}' already exists with correct configuration")
                
        except nats.js.errors.NotFoundError:
            # Stream 생성
            stream_info = await js.add_stream(config.to_stream_config())
            print(f"Created stream '{config.name}'")
        
        return stream_info
    
    @staticmethod
    def validate_dlq_settings() -> Dict[str, Any]:
        """DLQ 설정이 EventBridge와 일치하는지 검증"""
        
        # EventBridge 설정
        eventbridge_config = {
            "max_retry": 3,
            "max_age": 3600
        }
        
        # NATS 설정
        nats_config = NATSConfigManager.get_stream_config("production")
        
        # 비교
        matches = {
            "max_retry_match": eventbridge_config["max_retry"] == nats_config.max_deliver,
            "max_age_match": eventbridge_config["max_age"] == nats_config.max_age
        }
        
        return {
            "eventbridge": eventbridge_config,
            "nats": {
                "max_deliver": nats_config.max_deliver,
                "max_age": nats_config.max_age
            },
            "matches": matches,
            "valid": all(matches.values())
        }


# 설정 검증 스크립트
if __name__ == "__main__":
    import asyncio
    
    async def main():
        # 설정 검증
        validation_result = NATSConfigManager.validate_dlq_settings()
        
        print("DLQ Settings Validation:")
        print(f"EventBridge: {validation_result['eventbridge']}")
        print(f"NATS: {validation_result['nats']}")
        print(f"Matches: {validation_result['matches']}")
        print(f"Valid: {validation_result['valid']}")
        
        if not validation_result['valid']:
            print("\n⚠️  WARNING: DLQ settings do not match between EventBridge and NATS!")
    
    asyncio.run(main())