"""
CloudWatch Alarms Configuration for OMS EventBridge
OMS EventBridge 모니터링을 위한 CloudWatch 알람 설정
"""
import json
import logging
from typing import Dict, Any, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class CloudWatchAlarmsManager:
    """CloudWatch 알람 관리자"""
    
    def __init__(
        self,
        aws_region: str = "us-east-1",
        sns_topic_arn: Optional[str] = None
    ):
        self.aws_region = aws_region
        self.sns_topic_arn = sns_topic_arn
        self.cloudwatch = boto3.client('cloudwatch', region_name=aws_region)
    
    def create_eventbridge_alarms(
        self,
        event_bus_name: str = "oms-events",
        alarm_prefix: str = "oms"
    ) -> List[Dict[str, Any]]:
        """
        EventBridge 관련 CloudWatch 알람 생성
        
        Args:
            event_bus_name: 모니터링할 이벤트 버스
            alarm_prefix: 알람 이름 접두사
            
        Returns:
            생성된 알람 목록
        """
        alarms = []
        
        # 1. Failed Invocations 알람
        failed_invocation_alarm = self.create_alarm(
            alarm_name=f"{alarm_prefix}-eventbridge-failed-invocations",
            alarm_description="Alert when EventBridge rule invocations fail",
            metric_name="FailedInvocations",
            namespace="AWS/Events",
            statistic="Sum",
            dimensions=[
                {"Name": "EventBusName", "Value": event_bus_name}
            ],
            period=300,  # 5 minutes
            evaluation_periods=1,
            threshold=5,
            comparison_operator="GreaterThanThreshold",
            treat_missing_data="notBreaching"
        )
        alarms.append(failed_invocation_alarm)
        
        # 2. Low Successful Invocations 알람 (이벤트가 없을 때)
        low_success_alarm = self.create_alarm(
            alarm_name=f"{alarm_prefix}-eventbridge-low-invocations",
            alarm_description="Alert when EventBridge invocations are too low",
            metric_name="SuccessfulInvocations",
            namespace="AWS/Events",
            statistic="Sum",
            dimensions=[
                {"Name": "EventBusName", "Value": event_bus_name}
            ],
            period=900,  # 15 minutes
            evaluation_periods=2,
            threshold=1,
            comparison_operator="LessThanThreshold",
            treat_missing_data="breaching"
        )
        alarms.append(low_success_alarm)
        
        # 3. High Error Rate 알람
        error_rate_alarm = self.create_metric_math_alarm(
            alarm_name=f"{alarm_prefix}-eventbridge-error-rate",
            alarm_description="Alert when EventBridge error rate is too high",
            metrics=[
                {
                    "Id": "e1",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/Events",
                            "MetricName": "FailedInvocations",
                            "Dimensions": [
                                {"Name": "EventBusName", "Value": event_bus_name}
                            ]
                        },
                        "Period": 300,
                        "Stat": "Sum"
                    },
                    "ReturnData": False
                },
                {
                    "Id": "e2",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/Events",
                            "MetricName": "SuccessfulInvocations",
                            "Dimensions": [
                                {"Name": "EventBusName", "Value": event_bus_name}
                            ]
                        },
                        "Period": 300,
                        "Stat": "Sum"
                    },
                    "ReturnData": False
                },
                {
                    "Id": "m1",
                    "Expression": "e1/(e1+e2)*100",
                    "Label": "Error Rate %",
                    "ReturnData": True
                }
            ],
            threshold=10,  # 10% error rate
            comparison_operator="GreaterThanThreshold",
            evaluation_periods=2
        )
        alarms.append(error_rate_alarm)
        
        return alarms
    
    def create_nats_consumer_lag_alarms(
        self,
        stream_name: str = "OMS_EVENTS",
        alarm_prefix: str = "oms"
    ) -> List[Dict[str, Any]]:
        """
        NATS Consumer Lag 알람 생성
        
        Args:
            stream_name: NATS Stream 이름
            alarm_prefix: 알람 이름 접두사
            
        Returns:
            생성된 알람 목록
        """
        alarms = []
        
        # Consumer Lag 알람
        consumer_lag_alarm = self.create_alarm(
            alarm_name=f"{alarm_prefix}-nats-consumer-lag",
            alarm_description="Alert when NATS consumer lag is too high",
            metric_name="ConsumerLag",
            namespace="OMS/NATS",
            statistic="Average",
            dimensions=[
                {"Name": "StreamName", "Value": stream_name}
            ],
            period=300,  # 5 minutes
            evaluation_periods=2,
            threshold=1000,  # 1000 messages behind
            comparison_operator="GreaterThanThreshold",
            treat_missing_data="notBreaching"
        )
        alarms.append(consumer_lag_alarm)
        
        return alarms
    
    def create_alarm(
        self,
        alarm_name: str,
        alarm_description: str,
        metric_name: str,
        namespace: str,
        statistic: str,
        dimensions: List[Dict[str, str]],
        period: int,
        evaluation_periods: int,
        threshold: float,
        comparison_operator: str,
        treat_missing_data: str = "notBreaching"
    ) -> Dict[str, Any]:
        """
        CloudWatch 알람 생성
        
        Args:
            alarm_name: 알람 이름
            alarm_description: 알람 설명
            metric_name: 메트릭 이름
            namespace: 네임스페이스
            statistic: 통계 (Sum, Average, etc.)
            dimensions: 디멘션 목록
            period: 기간 (초)
            evaluation_periods: 평가 기간 수
            threshold: 임계값
            comparison_operator: 비교 연산자
            treat_missing_data: 누락된 데이터 처리 방법
            
        Returns:
            생성 결과
        """
        try:
            alarm_kwargs = {
                "AlarmName": alarm_name,
                "AlarmDescription": alarm_description,
                "MetricName": metric_name,
                "Namespace": namespace,
                "Statistic": statistic,
                "Dimensions": dimensions,
                "Period": period,
                "EvaluationPeriods": evaluation_periods,
                "Threshold": threshold,
                "ComparisonOperator": comparison_operator,
                "TreatMissingData": treat_missing_data
            }
            
            # SNS 토픽이 설정된 경우 알람 액션 추가
            if self.sns_topic_arn:
                alarm_kwargs["AlarmActions"] = [self.sns_topic_arn]
                alarm_kwargs["OKActions"] = [self.sns_topic_arn]
            
            self.cloudwatch.put_metric_alarm(**alarm_kwargs)
            
            logger.info(f"Created alarm '{alarm_name}'")
            return {
                "status": "success",
                "alarm_name": alarm_name,
                "threshold": threshold
            }
            
        except ClientError as e:
            logger.error(f"Failed to create alarm '{alarm_name}': {e}")
            return {
                "status": "error",
                "alarm_name": alarm_name,
                "error": str(e)
            }
    
    def create_metric_math_alarm(
        self,
        alarm_name: str,
        alarm_description: str,
        metrics: List[Dict[str, Any]],
        threshold: float,
        comparison_operator: str,
        evaluation_periods: int
    ) -> Dict[str, Any]:
        """
        수식 기반 CloudWatch 알람 생성
        
        Args:
            alarm_name: 알람 이름
            alarm_description: 알람 설명
            metrics: 메트릭 정의 목록
            threshold: 임계값
            comparison_operator: 비교 연산자
            evaluation_periods: 평가 기간 수
            
        Returns:
            생성 결과
        """
        try:
            alarm_kwargs = {
                "AlarmName": alarm_name,
                "AlarmDescription": alarm_description,
                "Metrics": metrics,
                "Threshold": threshold,
                "ComparisonOperator": comparison_operator,
                "EvaluationPeriods": evaluation_periods,
                "TreatMissingData": "notBreaching"
            }
            
            if self.sns_topic_arn:
                alarm_kwargs["AlarmActions"] = [self.sns_topic_arn]
                alarm_kwargs["OKActions"] = [self.sns_topic_arn]
            
            self.cloudwatch.put_metric_alarm(**alarm_kwargs)
            
            logger.info(f"Created metric math alarm '{alarm_name}'")
            return {
                "status": "success",
                "alarm_name": alarm_name,
                "threshold": threshold
            }
            
        except ClientError as e:
            logger.error(f"Failed to create metric math alarm '{alarm_name}': {e}")
            return {
                "status": "error",
                "alarm_name": alarm_name,
                "error": str(e)
            }


def setup_oms_cloudwatch_alarms(
    event_bus_name: str = "oms-events",
    sns_topic_arn: Optional[str] = None,
    aws_region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    OMS용 CloudWatch 알람 전체 설정
    
    Args:
        event_bus_name: 이벤트 버스 이름
        sns_topic_arn: 알람 알림용 SNS 토픽 ARN
        aws_region: AWS 리전
        
    Returns:
        설정 결과
    """
    manager = CloudWatchAlarmsManager(
        aws_region=aws_region,
        sns_topic_arn=sns_topic_arn
    )
    
    results = {
        "eventbridge_alarms": [],
        "nats_alarms": [],
        "status": "pending"
    }
    
    try:
        # EventBridge 알람 생성
        eventbridge_alarms = manager.create_eventbridge_alarms(
            event_bus_name=event_bus_name
        )
        results["eventbridge_alarms"] = eventbridge_alarms
        
        # NATS Consumer Lag 알람 생성
        nats_alarms = manager.create_nats_consumer_lag_alarms()
        results["nats_alarms"] = nats_alarms
        
        # 성공 여부 확인
        all_alarms = eventbridge_alarms + nats_alarms
        success_count = sum(1 for alarm in all_alarms if alarm.get("status") == "success")
        
        results["status"] = "success" if success_count == len(all_alarms) else "partial"
        results["summary"] = {
            "total_alarms": len(all_alarms),
            "successful": success_count,
            "failed": len(all_alarms) - success_count
        }
        
        logger.info(f"Created {success_count}/{len(all_alarms)} CloudWatch alarms")
        
    except Exception as e:
        logger.error(f"Failed to setup CloudWatch alarms: {e}")
        results["status"] = "error"
        results["error"] = str(e)
    
    return results


# 알람 설정 정보
ALARM_CONFIGURATIONS = {
    "oms-eventbridge-failed-invocations": {
        "MetricName": "FailedInvocations",
        "Namespace": "AWS/Events",
        "Statistic": "Sum",
        "Period": 300,
        "EvaluationPeriods": 1,
        "Threshold": 5,
        "ComparisonOperator": "GreaterThanThreshold"
    },
    "oms-eventbridge-low-invocations": {
        "MetricName": "SuccessfulInvocations",
        "Namespace": "AWS/Events",
        "Statistic": "Sum",
        "Period": 900,
        "EvaluationPeriods": 2,
        "Threshold": 1,
        "ComparisonOperator": "LessThanThreshold"
    },
    "oms-nats-consumer-lag": {
        "MetricName": "ConsumerLag",
        "Namespace": "OMS/NATS",
        "Statistic": "Average",
        "Period": 300,
        "EvaluationPeriods": 2,
        "Threshold": 1000,
        "ComparisonOperator": "GreaterThanThreshold"
    }
}


# CLI 실행
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Setup CloudWatch Alarms for OMS')
    parser.add_argument('--event-bus-name', default='oms-events', help='Event bus name')
    parser.add_argument('--sns-topic-arn', help='SNS topic ARN for notifications')
    parser.add_argument('--aws-region', default='us-east-1', help='AWS region')
    
    args = parser.parse_args()
    
    result = setup_oms_cloudwatch_alarms(
        event_bus_name=args.event_bus_name,
        sns_topic_arn=args.sns_topic_arn,
        aws_region=args.aws_region
    )
    
    print(json.dumps(result, indent=2, default=str))