"""
AWS EventBridge Infrastructure Setup
EventBridge 리소스 생성 및 IAM 권한 설정
"""
import json
import logging
from typing import Dict, Any, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class EventBridgeInfrastructureManager:
    """EventBridge 인프라 관리"""
    
    def __init__(
        self,
        aws_region: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None
    ):
        self.aws_region = aws_region
        
        # AWS 클라이언트 초기화
        session_kwargs = {'region_name': aws_region}
        if aws_access_key_id:
            session_kwargs['aws_access_key_id'] = aws_access_key_id
        if aws_secret_access_key:
            session_kwargs['aws_secret_access_key'] = aws_secret_access_key
        if aws_session_token:
            session_kwargs['aws_session_token'] = aws_session_token
            
        self.session = boto3.Session(**session_kwargs)
        self.events_client = self.session.client('events')
        self.iam_client = self.session.client('iam')
        self.sts_client = self.session.client('sts')
    
    def create_event_bus(
        self,
        event_bus_name: str,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        EventBridge 커스텀 이벤트 버스 생성
        
        Args:
            event_bus_name: 이벤트 버스 이름
            description: 버스 설명
            tags: 리소스 태그
            
        Returns:
            생성 결과 딕셔너리
        """
        try:
            # 이벤트 버스가 이미 존재하는지 확인
            try:
                existing_bus = self.events_client.describe_event_bus(Name=event_bus_name)
                logger.info(f"Event bus '{event_bus_name}' already exists")
                return {
                    'status': 'exists',
                    'event_bus_arn': existing_bus['Arn'],
                    'event_bus_name': event_bus_name
                }
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceNotFoundException':
                    raise
            
            # 이벤트 버스 생성
            create_params = {'Name': event_bus_name}
            if description:
                create_params['Description'] = description
            
            response = self.events_client.create_event_bus(**create_params)
            
            # 태그 추가
            if tags:
                resource_arn = response['EventBusArn']
                tag_list = [{'Key': k, 'Value': v} for k, v in tags.items()]
                self.events_client.tag_resource(
                    ResourceARN=resource_arn,
                    Tags=tag_list
                )
            
            logger.info(f"Successfully created event bus '{event_bus_name}'")
            return {
                'status': 'created',
                'event_bus_arn': response['EventBusArn'],
                'event_bus_name': event_bus_name
            }
            
        except Exception as e:
            logger.error(f"Failed to create event bus '{event_bus_name}': {e}")
            return {
                'status': 'error',
                'error': str(e),
                'event_bus_name': event_bus_name
            }
    
    def create_oms_event_rules(
        self,
        event_bus_name: str,
        target_configs: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        OMS 이벤트용 EventBridge Rule들 생성
        
        Args:
            event_bus_name: 이벤트 버스 이름
            target_configs: 타겟 설정 목록
            
        Returns:
            생성된 Rule들의 정보
        """
        from core.event_publisher.eventbridge_adapter import EventBridgeRuleGenerator
        
        results = []
        
        # OMS 이벤트 타입별 Rule 생성
        rule_definitions = EventBridgeRuleGenerator.generate_rules_for_oms_events()
        
        for rule_def in rule_definitions:
            try:
                rule_def['EventBusName'] = event_bus_name
                
                # Rule 생성
                self.events_client.put_rule(**rule_def)
                
                # 타겟이 지정된 경우 추가
                if target_configs:
                    for target_config in target_configs:
                        if self._should_add_target_to_rule(rule_def['Name'], target_config):
                            self._add_target_to_rule(
                                rule_def['Name'],
                                target_config,
                                event_bus_name
                            )
                
                results.append({
                    'status': 'created',
                    'rule_name': rule_def['Name'],
                    'event_pattern': rule_def['EventPattern']
                })
                
            except Exception as e:
                logger.error(f"Failed to create rule {rule_def['Name']}: {e}")
                results.append({
                    'status': 'error',
                    'rule_name': rule_def['Name'],
                    'error': str(e)
                })
        
        return results
    
    def create_iam_role_for_eventbridge(
        self,
        role_name: str = "OMSEventBridgeRole",
        event_bus_arn: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        EventBridge 발행용 IAM Role 생성
        
        Args:
            role_name: IAM Role 이름
            event_bus_arn: 특정 이벤트 버스 ARN (권한 제한용)
            
        Returns:
            생성된 Role 정보
        """
        try:
            # Trust Policy (어플리케이션이 Role을 assume할 수 있도록)
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": ["ec2.amazonaws.com", "ecs-tasks.amazonaws.com"]
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
            
            # 현재 계정 ID 가져오기
            account_id = self.sts_client.get_caller_identity()['Account']
            
            # Permissions Policy
            if event_bus_arn:
                resource_arn = event_bus_arn
            else:
                resource_arn = f"arn:aws:events:{self.aws_region}:{account_id}:event-bus/*"
            
            permissions_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "events:PutEvents"
                        ],
                        "Resource": resource_arn
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "events:DescribeEventBus"
                        ],
                        "Resource": "*"
                    }
                ]
            }
            
            # Role 생성
            try:
                create_role_response = self.iam_client.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(trust_policy),
                    Description="IAM role for OMS EventBridge publishing",
                    Tags=[
                        {'Key': 'Service', 'Value': 'OMS'},
                        {'Key': 'Component', 'Value': 'EventBridge'},
                        {'Key': 'Environment', 'Value': 'production'}
                    ]
                )
                role_arn = create_role_response['Role']['Arn']
                logger.info(f"Created IAM role '{role_name}'")
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'EntityAlreadyExists':
                    # Role이 이미 존재하는 경우
                    get_role_response = self.iam_client.get_role(RoleName=role_name)
                    role_arn = get_role_response['Role']['Arn']
                    logger.info(f"IAM role '{role_name}' already exists")
                else:
                    raise
            
            # Policy 추가
            policy_name = f"{role_name}Policy"
            try:
                self.iam_client.put_role_policy(
                    RoleName=role_name,
                    PolicyName=policy_name,
                    PolicyDocument=json.dumps(permissions_policy)
                )
                logger.info(f"Added policy '{policy_name}' to role '{role_name}'")
                
            except Exception as e:
                logger.error(f"Failed to add policy to role: {e}")
                # Policy 추가 실패해도 Role은 생성됨
            
            return {
                'status': 'success',
                'role_name': role_name,
                'role_arn': role_arn,
                'policy_name': policy_name
            }
            
        except Exception as e:
            logger.error(f"Failed to create IAM role '{role_name}': {e}")
            return {
                'status': 'error',
                'error': str(e),
                'role_name': role_name
            }
    
    def setup_cloudwatch_dashboard(
        self,
        dashboard_name: str = "OMS-EventBridge-Dashboard",
        event_bus_name: str = "oms-events"
    ) -> Dict[str, Any]:
        """
        EventBridge 모니터링용 CloudWatch Dashboard 생성
        
        Args:
            dashboard_name: 대시보드 이름
            event_bus_name: 모니터링할 이벤트 버스
            
        Returns:
            대시보드 생성 결과
        """
        try:
            cloudwatch = self.session.client('cloudwatch')
            
            # Dashboard 설정
            dashboard_body = {
                "widgets": [
                    {
                        "type": "metric",
                        "x": 0, "y": 0, "width": 12, "height": 6,
                        "properties": {
                            "metrics": [
                                ["AWS/Events", "SuccessfulInvocations", "EventBusName", event_bus_name],
                                [".", "FailedInvocations", ".", "."]
                            ],
                            "period": 300,
                            "stat": "Sum",
                            "region": self.aws_region,
                            "title": "EventBridge Invocations"
                        }
                    },
                    {
                        "type": "metric",
                        "x": 12, "y": 0, "width": 12, "height": 6,
                        "properties": {
                            "metrics": [
                                ["AWS/Events", "MatchedEvents", "EventBusName", event_bus_name]
                            ],
                            "period": 300,
                            "stat": "Sum",
                            "region": self.aws_region,
                            "title": "Matched Events"
                        }
                    }
                ]
            }
            
            cloudwatch.put_dashboard(
                DashboardName=dashboard_name,
                DashboardBody=json.dumps(dashboard_body)
            )
            
            logger.info(f"Created CloudWatch dashboard '{dashboard_name}'")
            return {
                'status': 'success',
                'dashboard_name': dashboard_name,
                'dashboard_url': f"https://console.aws.amazon.com/cloudwatch/home?region={self.aws_region}#dashboards:name={dashboard_name}"
            }
            
        except Exception as e:
            logger.error(f"Failed to create CloudWatch dashboard: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'dashboard_name': dashboard_name
            }
    
    def _should_add_target_to_rule(self, rule_name: str, target_config: Dict[str, Any]) -> bool:
        """Rule에 타겟을 추가할지 결정"""
        # 특정 이벤트 타입에만 타겟을 추가하는 로직
        return target_config.get('apply_to_all', False) or \
               rule_name in target_config.get('specific_rules', [])
    
    def _add_target_to_rule(
        self,
        rule_name: str,
        target_config: Dict[str, Any],
        event_bus_name: str
    ):
        """Rule에 타겟 추가"""
        try:
            targets = [
                {
                    'Id': target_config.get('id', '1'),
                    'Arn': target_config['arn']
                }
            ]
            
            # 추가 타겟 설정
            if 'input_transformer' in target_config:
                targets[0]['InputTransformer'] = target_config['input_transformer']
            
            self.events_client.put_targets(
                Rule=rule_name,
                EventBusName=event_bus_name,
                Targets=targets
            )
            
            logger.info(f"Added target to rule '{rule_name}'")
            
        except Exception as e:
            logger.error(f"Failed to add target to rule '{rule_name}': {e}")


def setup_oms_eventbridge_infrastructure(
    event_bus_name: str = "oms-events",
    aws_region: str = "us-east-1",
    create_iam_role: bool = True,
    create_dashboard: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    OMS EventBridge 인프라 전체 설정
    
    Args:
        event_bus_name: 생성할 이벤트 버스 이름
        aws_region: AWS 리전
        create_iam_role: IAM Role 생성 여부
        create_dashboard: CloudWatch Dashboard 생성 여부
        **kwargs: 추가 설정
        
    Returns:
        설정 결과 요약
    """
    manager = EventBridgeInfrastructureManager(aws_region=aws_region, **kwargs)
    
    results = {
        'event_bus': None,
        'iam_role': None,
        'rules': [],
        'dashboard': None,
        'overall_status': 'pending'
    }
    
    try:
        # 1. Event Bus 생성
        bus_result = manager.create_event_bus(
            event_bus_name,
            description="OMS CloudEvents Event Bus",
            tags={
                'Service': 'OMS',
                'Component': 'EventBridge',
                'Environment': 'production'
            }
        )
        results['event_bus'] = bus_result
        
        if bus_result['status'] in ['created', 'exists']:
            event_bus_arn = bus_result['event_bus_arn']
            
            # 2. IAM Role 생성
            if create_iam_role:
                iam_result = manager.create_iam_role_for_eventbridge(
                    event_bus_arn=event_bus_arn
                )
                results['iam_role'] = iam_result
            
            # 3. EventBridge Rules 생성
            rules_result = manager.create_oms_event_rules(event_bus_name)
            results['rules'] = rules_result
            
            # 4. CloudWatch Dashboard 생성
            if create_dashboard:
                dashboard_result = manager.setup_cloudwatch_dashboard(
                    event_bus_name=event_bus_name
                )
                results['dashboard'] = dashboard_result
            
            results['overall_status'] = 'success'
        else:
            results['overall_status'] = 'failed'
        
    except Exception as e:
        logger.error(f"Failed to setup OMS EventBridge infrastructure: {e}")
        results['overall_status'] = 'error'
        results['error'] = str(e)
    
    return results


# CLI 스크립트용 메인 함수
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Setup OMS EventBridge Infrastructure')
    parser.add_argument('--event-bus-name', default='oms-events', help='Event bus name')
    parser.add_argument('--aws-region', default='us-east-1', help='AWS region')
    parser.add_argument('--no-iam-role', action='store_true', help='Skip IAM role creation')
    parser.add_argument('--no-dashboard', action='store_true', help='Skip dashboard creation')
    
    args = parser.parse_args()
    
    result = setup_oms_eventbridge_infrastructure(
        event_bus_name=args.event_bus_name,
        aws_region=args.aws_region,
        create_iam_role=not args.no_iam_role,
        create_dashboard=not args.no_dashboard
    )
    
    print(json.dumps(result, indent=2, default=str))