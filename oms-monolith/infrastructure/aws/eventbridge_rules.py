"""
AWS EventBridge Rules Configuration with Retry and DLQ
EventBridge 규칙 설정 및 재시도/DLQ 구성
"""
import json
import logging
from typing import Dict, Any, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class EventBridgeRuleManager:
    """EventBridge Rule 관리자"""
    
    def __init__(self, client: boto3.client):
        self.client = client
    
    def create_rule_with_retry_and_dlq(
        self,
        rule_name: str,
        event_pattern: Dict[str, Any],
        event_bus_name: str,
        target_arn: str,
        role_arn: Optional[str] = None,
        dlq_arn: Optional[str] = None,
        max_retry_attempts: int = 3,
        max_event_age: int = 3600,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        재시도 정책과 DLQ가 설정된 Rule 생성
        
        Args:
            rule_name: Rule 이름
            event_pattern: 이벤트 패턴
            event_bus_name: 이벤트 버스 이름
            target_arn: 타겟 ARN (Lambda, SNS, SQS 등)
            role_arn: 실행 역할 ARN
            dlq_arn: Dead Letter Queue ARN
            max_retry_attempts: 최대 재시도 횟수
            max_event_age: 최대 이벤트 나이 (초)
            description: Rule 설명
            
        Returns:
            생성 결과
        """
        try:
            # 1. Rule 생성
            rule_response = self.client.put_rule(
                Name=rule_name,
                EventPattern=json.dumps(event_pattern),
                State='ENABLED',
                EventBusName=event_bus_name,
                Description=description or f'OMS event rule: {rule_name}'
            )
            
            logger.info(f"Created rule '{rule_name}' on bus '{event_bus_name}'")
            
            # 2. Target 설정 (재시도 정책 포함)
            target_config = {
                'Id': '1',
                'Arn': target_arn,
                'RetryPolicy': {
                    'MaximumRetryAttempts': max_retry_attempts,
                    'MaximumEventAge': max_event_age
                }
            }
            
            # Role ARN 추가 (필요한 경우)
            if role_arn:
                target_config['RoleArn'] = role_arn
            
            # DLQ 설정 추가
            if dlq_arn:
                target_config['DeadLetterConfig'] = {
                    'Arn': dlq_arn
                }
                logger.info(f"Added DLQ to rule '{rule_name}': {dlq_arn}")
            
            # Target 추가
            target_response = self.client.put_targets(
                Rule=rule_name,
                EventBusName=event_bus_name,
                Targets=[target_config]
            )
            
            if target_response['FailedEntryCount'] > 0:
                logger.error(f"Failed to add targets to rule '{rule_name}': {target_response['FailedEntries']}")
                return {
                    'status': 'partial_success',
                    'rule_arn': rule_response['RuleArn'],
                    'failed_targets': target_response['FailedEntries']
                }
            
            logger.info(f"Successfully configured rule '{rule_name}' with retry policy and DLQ")
            
            return {
                'status': 'success',
                'rule_arn': rule_response['RuleArn'],
                'rule_name': rule_name,
                'retry_policy': {
                    'max_attempts': max_retry_attempts,
                    'max_age': max_event_age
                },
                'dlq_configured': dlq_arn is not None
            }
            
        except ClientError as e:
            logger.error(f"Failed to create rule '{rule_name}': {e}")
            return {
                'status': 'error',
                'error': str(e),
                'rule_name': rule_name
            }
    
    def create_oms_event_rules(
        self,
        event_bus_name: str,
        target_config: Dict[str, Any],
        dlq_arn: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        모든 OMS 이벤트 타입에 대한 Rule 생성
        
        Args:
            event_bus_name: 이벤트 버스 이름
            target_config: 타겟 설정
            dlq_arn: DLQ ARN
            
        Returns:
            생성된 Rule들의 정보
        """
        from core.event_publisher.cloudevents_enhanced import EventType
        
        results = []
        
        # 모든 이벤트 타입에 대해 Rule 생성
        for event_type in EventType:
            rule_name = f"oms_{event_type.name.lower()}_rule"
            
            # 이벤트 패턴 생성
            event_pattern = {
                "source": ["oms"],
                "detail": {
                    "cloudEvents": {
                        "type": [event_type.value]
                    }
                }
            }
            
            # Rule 생성
            result = self.create_rule_with_retry_and_dlq(
                rule_name=rule_name,
                event_pattern=event_pattern,
                event_bus_name=event_bus_name,
                target_arn=target_config['target_arn'],
                role_arn=target_config.get('role_arn'),
                dlq_arn=dlq_arn,
                max_retry_attempts=3,
                max_event_age=3600,
                description=f"Route {event_type.value} events to target"
            )
            
            results.append(result)
        
        # 요약 통계
        success_count = sum(1 for r in results if r['status'] == 'success')
        logger.info(f"Created {success_count}/{len(results)} EventBridge rules successfully")
        
        return results


def ensure_dlq_exists(
    sqs_client: boto3.client,
    dlq_name: str = "oms-events-dlq",
    message_retention_seconds: int = 1209600  # 14 days
) -> str:
    """
    DLQ가 존재하는지 확인하고 없으면 생성
    
    Args:
        sqs_client: SQS 클라이언트
        dlq_name: DLQ 이름
        message_retention_seconds: 메시지 보관 기간
        
    Returns:
        DLQ ARN
    """
    try:
        # DLQ가 이미 존재하는지 확인
        try:
            response = sqs_client.get_queue_url(QueueName=dlq_name)
            queue_url = response['QueueUrl']
            
            # Queue 속성 가져오기
            attrs = sqs_client.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=['QueueArn']
            )
            
            logger.info(f"DLQ '{dlq_name}' already exists")
            return attrs['Attributes']['QueueArn']
            
        except ClientError as e:
            if e.response['Error']['Code'] != 'AWS.SimpleQueueService.NonExistentQueue':
                raise
        
        # DLQ 생성
        response = sqs_client.create_queue(
            QueueName=dlq_name,
            Attributes={
                'MessageRetentionPeriod': str(message_retention_seconds),
                'VisibilityTimeout': '300',  # 5 minutes
                'DelaySeconds': '0'
            },
            tags={
                'Service': 'OMS',
                'Type': 'DLQ',
                'Purpose': 'EventBridge-Failed-Events'
            }
        )
        
        queue_url = response['QueueUrl']
        
        # Queue ARN 가져오기
        attrs = sqs_client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['QueueArn']
        )
        
        dlq_arn = attrs['Attributes']['QueueArn']
        logger.info(f"Created DLQ '{dlq_name}' with ARN: {dlq_arn}")
        
        return dlq_arn
        
    except Exception as e:
        logger.error(f"Failed to ensure DLQ exists: {e}")
        raise


def setup_eventbridge_with_dlq(
    event_bus_name: str = "oms-events",
    target_arn: str = None,
    aws_region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    EventBridge Rule을 DLQ와 함께 설정
    
    Args:
        event_bus_name: 이벤트 버스 이름
        target_arn: 타겟 ARN
        aws_region: AWS 리전
        
    Returns:
        설정 결과
    """
    # 클라이언트 초기화
    events_client = boto3.client('events', region_name=aws_region)
    sqs_client = boto3.client('sqs', region_name=aws_region)
    
    results = {
        'dlq': None,
        'rules': [],
        'status': 'pending'
    }
    
    try:
        # 1. DLQ 확인/생성
        dlq_arn = ensure_dlq_exists(sqs_client)
        results['dlq'] = {
            'status': 'success',
            'arn': dlq_arn
        }
        
        # 2. Rule Manager 생성
        rule_manager = EventBridgeRuleManager(events_client)
        
        # 3. Target 설정
        if not target_arn:
            # 기본 타겟 설정 (예: Lambda ARN)
            logger.warning("No target ARN provided, rules will be created without targets")
            return results
        
        target_config = {
            'target_arn': target_arn
        }
        
        # 4. 모든 OMS 이벤트 Rule 생성
        rules_results = rule_manager.create_oms_event_rules(
            event_bus_name=event_bus_name,
            target_config=target_config,
            dlq_arn=dlq_arn
        )
        
        results['rules'] = rules_results
        results['status'] = 'success'
        
    except Exception as e:
        logger.error(f"Failed to setup EventBridge with DLQ: {e}")
        results['status'] = 'error'
        results['error'] = str(e)
    
    return results


# CLI 실행
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Setup EventBridge Rules with DLQ')
    parser.add_argument('--event-bus-name', default='oms-events', help='Event bus name')
    parser.add_argument('--target-arn', required=True, help='Target ARN for events')
    parser.add_argument('--aws-region', default='us-east-1', help='AWS region')
    
    args = parser.parse_args()
    
    result = setup_eventbridge_with_dlq(
        event_bus_name=args.event_bus_name,
        target_arn=args.target_arn,
        aws_region=args.aws_region
    )
    
    print(json.dumps(result, indent=2, default=str))