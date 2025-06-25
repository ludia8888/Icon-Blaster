"""
SIEM Integration Module
중앙 SIEM 연동을 위한 감사 로그 전송 시스템
"""
import json
import time
import socket
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union, Callable
from pathlib import Path
from enum import Enum
from queue import Queue, Empty
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import requests
import uuid

from pydantic import BaseModel, Field
from core.validation.validation_logging import ValidationLogEntry
from core.validation.tampering_detection import TamperingEvent
from core.validation.naming_convention import EntityType, ValidationIssue
from utils.logger import get_logger

logger = get_logger(__name__)


class SIEMPlatform(str, Enum):
    """지원하는 SIEM 플랫폼"""
    SPLUNK = "splunk"
    ELK_STACK = "elasticsearch" 
    QRADAR = "qradar"
    ARCSIGHT = "arcsight"
    SENTINEL = "azure_sentinel"
    CHRONICLE = "google_chronicle"
    SUMO_LOGIC = "sumo_logic"
    DATADOG = "datadog"
    GENERIC_SYSLOG = "syslog"
    WEBHOOK = "webhook"


class SIEMFormat(str, Enum):
    """SIEM 로그 포맷"""
    CEF = "cef"  # Common Event Format
    LEEF = "leef"  # Log Event Extended Format
    JSON = "json"
    SYSLOG_RFC3164 = "syslog_rfc3164"
    SYSLOG_RFC5424 = "syslog_rfc5424"
    STIX = "stix"  # Structured Threat Information eXpression


class SeverityLevel(str, Enum):
    """SIEM 심각도 레벨"""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


@dataclass
class SIEMEvent:
    """SIEM 이벤트 구조"""
    timestamp: str
    event_id: str
    source: str
    event_type: str
    severity: SeverityLevel
    user_id: Optional[str]
    source_ip: Optional[str]
    entity_type: Optional[str]
    entity_name: Optional[str]
    action: str
    outcome: str
    details: Dict[str, Any]
    raw_data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return asdict(self)


class SIEMConfig(BaseModel):
    """SIEM 연동 설정"""
    platform: SIEMPlatform
    format: SIEMFormat
    endpoint: str
    port: Optional[int] = None
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    index: Optional[str] = None  # Splunk/ELK index
    facility: int = 16  # Syslog facility (local0)
    severity_mapping: Dict[str, SeverityLevel] = Field(default_factory=lambda: {
        "info": SeverityLevel.LOW,
        "warning": SeverityLevel.MEDIUM,
        "error": SeverityLevel.HIGH,
        "critical": SeverityLevel.CRITICAL
    })
    batch_size: int = 100
    batch_timeout: int = 30  # seconds
    retry_attempts: int = 3
    retry_delay: int = 5
    enable_tls: bool = True
    verify_ssl: bool = True
    custom_headers: Dict[str, str] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class SIEMFormatter:
    """SIEM 포맷터"""
    
    def __init__(self, format_type: SIEMFormat):
        self.format_type = format_type
    
    def format_event(self, event: SIEMEvent) -> str:
        """이벤트를 SIEM 포맷으로 변환"""
        if self.format_type == SIEMFormat.CEF:
            return self._format_cef(event)
        elif self.format_type == SIEMFormat.LEEF:
            return self._format_leef(event)
        elif self.format_type == SIEMFormat.JSON:
            return self._format_json(event)
        elif self.format_type == SIEMFormat.SYSLOG_RFC3164:
            return self._format_syslog_rfc3164(event)
        elif self.format_type == SIEMFormat.SYSLOG_RFC5424:
            return self._format_syslog_rfc5424(event)
        elif self.format_type == SIEMFormat.STIX:
            return self._format_stix(event)
        else:
            return self._format_json(event)  # 기본값
    
    def _format_cef(self, event: SIEMEvent) -> str:
        """CEF (Common Event Format) 포맷"""
        # CEF:Version|Device Vendor|Device Product|Device Version|Device Event Class ID|Name|Severity|Extension
        extension_fields = []
        for key, value in event.details.items():
            if isinstance(value, (str, int, float, bool)):
                extension_fields.append(f"{key}={value}")
        
        extension = " ".join(extension_fields)
        
        return (f"CEF:0|OMS|Naming Convention Validator|1.0|{event.event_type}|"
                f"{event.action}|{self._severity_to_cef(event.severity)}|"
                f"rt={event.timestamp} src={event.source_ip or 'unknown'} "
                f"suser={event.user_id or 'system'} act={event.action} "
                f"outcome={event.outcome} {extension}")
    
    def _format_leef(self, event: SIEMEvent) -> str:
        """LEEF (Log Event Extended Format) 포맷"""
        # LEEF:Version|Vendor|Product|Version|EventID|Delimiter|Key-Value pairs
        kv_pairs = [
            f"devTime={event.timestamp}",
            f"src={event.source_ip or 'unknown'}",
            f"usrName={event.user_id or 'system'}",
            f"cat={event.event_type}",
            f"sev={self._severity_to_leef(event.severity)}",
            f"srcName={event.source}"
        ]
        
        for key, value in event.details.items():
            if isinstance(value, (str, int, float, bool)):
                kv_pairs.append(f"{key}={value}")
        
        return f"LEEF:2.0|OMS|Naming Validator|1.0|{event.event_type}|^|" + "^".join(kv_pairs)
    
    def _format_json(self, event: SIEMEvent) -> str:
        """JSON 포맷"""
        return json.dumps(event.to_dict(), default=str, ensure_ascii=False)
    
    def _format_syslog_rfc3164(self, event: SIEMEvent) -> str:
        """Syslog RFC3164 포맷"""
        # <priority>timestamp hostname tag: message
        priority = 16 * 8 + self._severity_to_syslog(event.severity)  # facility * 8 + severity
        timestamp = datetime.fromisoformat(event.timestamp).strftime("%b %d %H:%M:%S")
        hostname = socket.gethostname()
        
        message = json.dumps({
            'event_id': event.event_id,
            'event_type': event.event_type,
            'action': event.action,
            'outcome': event.outcome,
            'user_id': event.user_id,
            'entity_type': event.entity_type,
            'entity_name': event.entity_name,
            'details': event.details
        })
        
        return f"<{priority}>{timestamp} {hostname} OMS-Naming: {message}"
    
    def _format_syslog_rfc5424(self, event: SIEMEvent) -> str:
        """Syslog RFC5424 포맷"""
        # <priority>version timestamp hostname app-name proc-id msg-id structured-data msg
        priority = 16 * 8 + self._severity_to_syslog(event.severity)
        hostname = socket.gethostname()
        
        structured_data = f'[oms@32473 eventId="{event.event_id}" eventType="{event.event_type}" userId="{event.user_id or "-"}"]'
        
        message = json.dumps({
            'action': event.action,
            'outcome': event.outcome,
            'entity_type': event.entity_type,
            'entity_name': event.entity_name,
            'details': event.details
        })
        
        return (f"<{priority}>1 {event.timestamp} {hostname} OMS-Naming "
                f"{event.event_id} {event.event_type} {structured_data} {message}")
    
    def _format_stix(self, event: SIEMEvent) -> str:
        """STIX (Structured Threat Information eXpression) 포맷"""
        stix_object = {
            "type": "observed-data",
            "id": f"observed-data--{event.event_id}",
            "created": event.timestamp,
            "modified": event.timestamp,
            "first_observed": event.timestamp,
            "last_observed": event.timestamp,
            "number_observed": 1,
            "objects": {
                "0": {
                    "type": "software",
                    "name": "OMS Naming Convention Validator",
                    "vendor": "OMS"
                },
                "1": {
                    "type": "x-oms-validation-event",
                    "event_type": event.event_type,
                    "action": event.action,
                    "outcome": event.outcome,
                    "severity": event.severity.value,
                    "entity_type": event.entity_type,
                    "entity_name": event.entity_name,
                    "user_id": event.user_id,
                    "details": event.details
                }
            }
        }
        return json.dumps(stix_object, default=str)
    
    def _severity_to_cef(self, severity: SeverityLevel) -> int:
        """CEF 심각도 변환 (0-10)"""
        mapping = {
            SeverityLevel.LOW: 3,
            SeverityLevel.MEDIUM: 6,
            SeverityLevel.HIGH: 8,
            SeverityLevel.CRITICAL: 10
        }
        return mapping.get(severity, 5)
    
    def _severity_to_leef(self, severity: SeverityLevel) -> int:
        """LEEF 심각도 변환 (1-10)"""
        mapping = {
            SeverityLevel.LOW: 2,
            SeverityLevel.MEDIUM: 5,
            SeverityLevel.HIGH: 8,
            SeverityLevel.CRITICAL: 10
        }
        return mapping.get(severity, 5)
    
    def _severity_to_syslog(self, severity: SeverityLevel) -> int:
        """Syslog 심각도 변환 (0-7)"""
        mapping = {
            SeverityLevel.LOW: 6,      # info
            SeverityLevel.MEDIUM: 4,   # warning
            SeverityLevel.HIGH: 3,     # error
            SeverityLevel.CRITICAL: 2  # critical
        }
        return mapping.get(severity, 6)


class SIEMEventConverter:
    """검증 로그를 SIEM 이벤트로 변환"""
    
    def __init__(self, source_name: str = "OMS-Naming-Validator"):
        self.source_name = source_name
    
    def convert_validation_log(self, log_entry: ValidationLogEntry) -> SIEMEvent:
        """검증 로그를 SIEM 이벤트로 변환"""
        severity = self._determine_severity(log_entry)
        
        return SIEMEvent(
            timestamp=log_entry.timestamp,
            event_id=log_entry.log_id,
            source=self.source_name,
            event_type="naming_validation",
            severity=severity,
            user_id=log_entry.user_id,
            source_ip=log_entry.metadata.get("source_ip"),
            entity_type=log_entry.entity_type.value,
            entity_name=log_entry.entity_name,
            action="validate_naming",
            outcome=log_entry.outcome.value,
            details={
                "convention_id": log_entry.convention_id,
                "is_valid": log_entry.is_valid,
                "issues_count": len(log_entry.issues),
                "suggestions_count": len(log_entry.suggestions),
                "validation_time_ms": log_entry.validation_time_ms,
                "session_id": log_entry.session_id,
                "source_file": log_entry.source_file,
                "line_number": log_entry.line_number,
                "git_commit": log_entry.git_commit,
                "issues": [issue for issue in log_entry.issues]
            },
            raw_data=log_entry.model_dump()
        )
    
    def convert_tampering_event(self, tamper_event: TamperingEvent) -> SIEMEvent:
        """변조 이벤트를 SIEM 이벤트로 변환"""
        severity_mapping = {
            "info": SeverityLevel.LOW,
            "warning": SeverityLevel.MEDIUM,
            "critical": SeverityLevel.CRITICAL
        }
        
        return SIEMEvent(
            timestamp=tamper_event.timestamp,
            event_id=tamper_event.event_id,
            source=self.source_name,
            event_type="policy_tampering",
            severity=severity_mapping.get(tamper_event.alert_level.value, SeverityLevel.HIGH),
            user_id=None,  # 변조는 사용자 불명
            source_ip=None,
            entity_type="policy",
            entity_name=tamper_event.policy_id,
            action="tamper_detection",
            outcome="detected",
            details={
                "alert_level": tamper_event.alert_level.value,
                "event_type": tamper_event.event_type,
                "description": tamper_event.description,
                "details": tamper_event.details,
                "has_previous_snapshot": tamper_event.previous_snapshot is not None,
                "has_current_snapshot": tamper_event.current_snapshot is not None
            },
            raw_data=tamper_event.model_dump()
        )
    
    def convert_security_event(self, event_data: Dict[str, Any]) -> SIEMEvent:
        """보안 이벤트를 SIEM 이벤트로 변환"""
        return SIEMEvent(
            timestamp=event_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            event_id=str(uuid.uuid4()),
            source=self.source_name,
            event_type="security_event",
            severity=SeverityLevel.HIGH,
            user_id=event_data.get("user_id"),
            source_ip=event_data.get("source_ip"),
            entity_type=event_data.get("entity_type"),
            entity_name=event_data.get("entity_name"),
            action=event_data.get("action", "security_check"),
            outcome=event_data.get("outcome", "detected"),
            details=event_data.get("details", {}),
            raw_data=event_data
        )
    
    def _determine_severity(self, log_entry: ValidationLogEntry) -> SeverityLevel:
        """검증 로그의 심각도 결정"""
        if log_entry.outcome.value == "error":
            return SeverityLevel.HIGH
        elif log_entry.outcome.value == "failure":
            # 보안 관련 실패는 높은 심각도
            if any("security" in str(issue).lower() for issue in log_entry.issues):
                return SeverityLevel.HIGH
            return SeverityLevel.MEDIUM
        else:
            return SeverityLevel.LOW


class SIEMTransmitter:
    """SIEM 전송자"""
    
    def __init__(self, config: SIEMConfig):
        self.config = config
        self.formatter = SIEMFormatter(config.format)
        self.event_queue = Queue()
        self.batch_buffer = []
        self.last_batch_time = time.time()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.running = False
        self.batch_thread = None
        
    def start(self):
        """전송자 시작"""
        if not self.running:
            self.running = True
            self.batch_thread = threading.Thread(target=self._batch_processor, daemon=True)
            self.batch_thread.start()
            logger.info(f"SIEM transmitter started for {self.config.platform}")
    
    def stop(self):
        """전송자 중지"""
        self.running = False
        if self.batch_thread:
            self.batch_thread.join(timeout=5)
        self.executor.shutdown(wait=True)
        logger.info("SIEM transmitter stopped")
    
    def send_event(self, event: SIEMEvent) -> bool:
        """단일 이벤트 전송"""
        try:
            self.event_queue.put(event, timeout=1)
            return True
        except Exception as e:
            logger.error(f"Failed to queue SIEM event: {e}")
            return False
    
    def send_events_batch(self, events: List[SIEMEvent]) -> bool:
        """배치 이벤트 전송"""
        try:
            for event in events:
                self.event_queue.put(event, timeout=1)
            return True
        except Exception as e:
            logger.error(f"Failed to queue SIEM events batch: {e}")
            return False
    
    def _batch_processor(self):
        """배치 처리 스레드"""
        while self.running:
            try:
                # 이벤트 수집
                try:
                    event = self.event_queue.get(timeout=1)
                    self.batch_buffer.append(event)
                except Empty:
                    pass
                
                # 배치 전송 조건 확인
                current_time = time.time()
                should_send = (
                    len(self.batch_buffer) >= self.config.batch_size or
                    (self.batch_buffer and 
                     current_time - self.last_batch_time >= self.config.batch_timeout)
                )
                
                if should_send and self.batch_buffer:
                    self._send_batch(self.batch_buffer.copy())
                    self.batch_buffer.clear()
                    self.last_batch_time = current_time
                    
            except Exception as e:
                logger.error(f"Error in SIEM batch processor: {e}")
                time.sleep(1)
    
    def _send_batch(self, events: List[SIEMEvent]):
        """실제 배치 전송"""
        formatted_events = []
        for event in events:
            try:
                formatted = self.formatter.format_event(event)
                formatted_events.append(formatted)
            except Exception as e:
                logger.error(f"Failed to format SIEM event {event.event_id}: {e}")
        
        if not formatted_events:
            return
        
        # 플랫폼별 전송
        self.executor.submit(self._transmit_to_platform, formatted_events)
    
    def _transmit_to_platform(self, formatted_events: List[str]):
        """플랫폼별 전송 로직"""
        for attempt in range(self.config.retry_attempts):
            try:
                if self.config.platform == SIEMPlatform.SPLUNK:
                    self._send_to_splunk(formatted_events)
                elif self.config.platform == SIEMPlatform.ELK_STACK:
                    self._send_to_elasticsearch(formatted_events)
                elif self.config.platform == SIEMPlatform.GENERIC_SYSLOG:
                    self._send_to_syslog(formatted_events)
                elif self.config.platform == SIEMPlatform.WEBHOOK:
                    self._send_to_webhook(formatted_events)
                else:
                    self._send_generic_http(formatted_events)
                
                logger.info(f"Successfully sent {len(formatted_events)} events to {self.config.platform}")
                break
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed to send to {self.config.platform}: {e}")
                if attempt < self.config.retry_attempts - 1:
                    time.sleep(self.config.retry_delay)
                else:
                    logger.error(f"Failed to send events after {self.config.retry_attempts} attempts")
    
    def _send_to_splunk(self, events: List[str]):
        """Splunk HEC 전송"""
        url = f"{self.config.endpoint}/services/collector/event"
        headers = {
            "Authorization": f"Splunk {self.config.api_key}",
            "Content-Type": "application/json",
            **self.config.custom_headers
        }
        
        # Splunk HEC 형식으로 변환
        splunk_events = []
        for event in events:
            splunk_event = {
                "time": int(time.time()),
                "index": self.config.index or "main",
                "source": "oms-naming-validator",
                "sourcetype": "_json",
                "event": json.loads(event) if self.config.format == SIEMFormat.JSON else event
            }
            splunk_events.append(splunk_event)
        
        response = requests.post(
            url, 
            json=splunk_events,
            headers=headers,
            verify=self.config.verify_ssl,
            timeout=30
        )
        response.raise_for_status()
    
    def _send_to_elasticsearch(self, events: List[str]):
        """Elasticsearch 전송"""
        url = f"{self.config.endpoint}/_bulk"
        headers = {
            "Content-Type": "application/x-ndjson",
            **self.config.custom_headers
        }
        
        if self.config.username and self.config.password:
            auth = (self.config.username, self.config.password)
        else:
            auth = None
        
        # Elasticsearch bulk 형식
        bulk_data = []
        for event in events:
            index_line = {"index": {"_index": self.config.index or "oms-naming-logs"}}
            bulk_data.append(json.dumps(index_line))
            
            if self.config.format == SIEMFormat.JSON:
                bulk_data.append(event)
            else:
                bulk_data.append(json.dumps({"message": event}))
        
        data = "\n".join(bulk_data) + "\n"
        
        response = requests.post(
            url,
            data=data,
            headers=headers,
            auth=auth,
            verify=self.config.verify_ssl,
            timeout=30
        )
        response.raise_for_status()
    
    def _send_to_syslog(self, events: List[str]):
        """Syslog 전송"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            for event in events:
                sock.sendto(event.encode('utf-8'), (self.config.endpoint, self.config.port or 514))
        finally:
            sock.close()
    
    def _send_to_webhook(self, events: List[str]):
        """Webhook 전송"""
        headers = {
            "Content-Type": "application/json",
            **self.config.custom_headers
        }
        
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        payload = {
            "events": [json.loads(event) if self.config.format == SIEMFormat.JSON else event for event in events],
            "source": "oms-naming-validator",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        response = requests.post(
            self.config.endpoint,
            json=payload,
            headers=headers,
            verify=self.config.verify_ssl,
            timeout=30
        )
        response.raise_for_status()
    
    def _send_generic_http(self, events: List[str]):
        """일반 HTTP 전송"""
        headers = {
            "Content-Type": "application/json",
            **self.config.custom_headers
        }
        
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        for event in events:
            response = requests.post(
                self.config.endpoint,
                data=event,
                headers=headers,
                verify=self.config.verify_ssl,
                timeout=30
            )
            response.raise_for_status()


class SIEMIntegrationManager:
    """SIEM 통합 관리자"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        초기화
        
        Args:
            config_file: SIEM 설정 파일 경로
        """
        self.config_file = config_file or "/etc/oms/siem_config.json"
        self.configs: Dict[str, SIEMConfig] = {}
        self.transmitters: Dict[str, SIEMTransmitter] = {}
        self.converter = SIEMEventConverter()
        
        self._load_configs()
        self._initialize_transmitters()
    
    def _load_configs(self):
        """SIEM 설정 로드"""
        config_path = Path(self.config_file)
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                
                for siem_id, config_data in data.get("siem_integrations", {}).items():
                    self.configs[siem_id] = SIEMConfig(**config_data)
                
                logger.info(f"Loaded {len(self.configs)} SIEM configurations")
            except Exception as e:
                logger.error(f"Failed to load SIEM configs: {e}")
        else:
            logger.warning(f"SIEM config file not found: {config_path}")
    
    def _initialize_transmitters(self):
        """전송자 초기화"""
        for siem_id, config in self.configs.items():
            try:
                transmitter = SIEMTransmitter(config)
                transmitter.start()
                self.transmitters[siem_id] = transmitter
                logger.info(f"Initialized SIEM transmitter: {siem_id}")
            except Exception as e:
                logger.error(f"Failed to initialize transmitter {siem_id}: {e}")
    
    def send_validation_log(self, log_entry: ValidationLogEntry, siem_ids: Optional[List[str]] = None):
        """검증 로그를 SIEM으로 전송"""
        event = self.converter.convert_validation_log(log_entry)
        self._send_to_siems(event, siem_ids)
    
    def send_tampering_event(self, tamper_event: TamperingEvent, siem_ids: Optional[List[str]] = None):
        """변조 이벤트를 SIEM으로 전송"""
        event = self.converter.convert_tampering_event(tamper_event)
        self._send_to_siems(event, siem_ids)
    
    def send_security_event(self, event_data: Dict[str, Any], siem_ids: Optional[List[str]] = None):
        """보안 이벤트를 SIEM으로 전송"""
        event = self.converter.convert_security_event(event_data)
        self._send_to_siems(event, siem_ids)
    
    def _send_to_siems(self, event: SIEMEvent, siem_ids: Optional[List[str]] = None):
        """지정된 SIEM들에 이벤트 전송"""
        target_siems = siem_ids or list(self.transmitters.keys())
        
        for siem_id in target_siems:
            transmitter = self.transmitters.get(siem_id)
            if transmitter:
                try:
                    transmitter.send_event(event)
                    logger.debug(f"Event {event.event_id} sent to SIEM {siem_id}")
                except Exception as e:
                    logger.error(f"Failed to send event to SIEM {siem_id}: {e}")
            else:
                logger.warning(f"SIEM transmitter not found: {siem_id}")
    
    def add_siem_config(self, siem_id: str, config: SIEMConfig):
        """SIEM 설정 추가"""
        self.configs[siem_id] = config
        
        try:
            transmitter = SIEMTransmitter(config)
            transmitter.start()
            self.transmitters[siem_id] = transmitter
            logger.info(f"Added SIEM configuration: {siem_id}")
        except Exception as e:
            logger.error(f"Failed to add SIEM {siem_id}: {e}")
    
    def remove_siem_config(self, siem_id: str):
        """SIEM 설정 제거"""
        if siem_id in self.transmitters:
            self.transmitters[siem_id].stop()
            del self.transmitters[siem_id]
        
        if siem_id in self.configs:
            del self.configs[siem_id]
        
        logger.info(f"Removed SIEM configuration: {siem_id}")
    
    def get_siem_status(self) -> Dict[str, Dict[str, Any]]:
        """SIEM 상태 조회"""
        status = {}
        for siem_id, transmitter in self.transmitters.items():
            config = self.configs[siem_id]
            status[siem_id] = {
                "platform": config.platform.value,
                "format": config.format.value,
                "endpoint": config.endpoint,
                "running": transmitter.running,
                "queue_size": transmitter.event_queue.qsize(),
                "batch_buffer_size": len(transmitter.batch_buffer)
            }
        return status
    
    def shutdown(self):
        """모든 SIEM 전송자 종료"""
        for transmitter in self.transmitters.values():
            transmitter.stop()
        logger.info("SIEM integration manager shutdown complete")


# 싱글톤 인스턴스
_siem_manager = None

def get_siem_manager(config_file: Optional[str] = None) -> SIEMIntegrationManager:
    """SIEM 통합 관리자 인스턴스 반환"""
    global _siem_manager
    if not _siem_manager or config_file:
        _siem_manager = SIEMIntegrationManager(config_file)
    return _siem_manager


def send_to_siem(event_data: Dict[str, Any], event_type: str = "security_event"):
    """편의 함수: SIEM 이벤트 전송"""
    manager = get_siem_manager()
    if event_type == "security_event":
        manager.send_security_event(event_data)
    else:
        # 다른 이벤트 타입도 추가 가능
        logger.warning(f"Unknown event type for SIEM: {event_type}")