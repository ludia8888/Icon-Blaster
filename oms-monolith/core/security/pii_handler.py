"""
PII Detection and Handling
민감 정보 감지 및 처리를 위한 모듈
"""
import re
import logging
from typing import List, Dict, Any, Tuple, Optional, Union
from dataclasses import dataclass
from enum import Enum
from cryptography.fernet import Fernet
import hashlib
import copy

logger = logging.getLogger(__name__)


class PIIType(Enum):
    """PII 타입 정의"""
    EMAIL = "email"
    SSN = "ssn"
    PHONE = "phone"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"
    AWS_KEY = "aws_key"
    API_KEY = "api_key"
    PASSWORD = "password"
    DATE_OF_BIRTH = "date_of_birth"
    KOREAN_RRN = "korean_rrn"  # 주민등록번호


@dataclass
class PIIMatch:
    """PII 매치 결과"""
    field_path: str
    pii_type: PIIType
    value: str
    confidence: float = 1.0


class PIIHandlingStrategy(Enum):
    """PII 처리 전략"""
    BLOCK = "block"          # 차단
    ANONYMIZE = "anonymize"  # 익명화
    ENCRYPT = "encrypt"      # 암호화
    LOG = "log"             # 로깅만
    REDACT = "redact"       # 삭제


class PIIHandler:
    """PII 감지 및 처리"""
    
    # PII 패턴 정의
    PII_PATTERNS = {
        PIIType.EMAIL: r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        PIIType.SSN: r'\b\d{3}-\d{2}-\d{4}\b',
        PIIType.PHONE: r'\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
        PIIType.CREDIT_CARD: r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
        PIIType.IP_ADDRESS: r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
        PIIType.AWS_KEY: r'\b(AKIA[0-9A-Z]{16})\b',
        PIIType.API_KEY: r'\b[A-Za-z0-9]{32,}\b',  # 일반적인 API 키 패턴
        PIIType.PASSWORD: r'(password|passwd|pwd)[\s:=]+[\S]+',
        PIIType.DATE_OF_BIRTH: r'\b(0[1-9]|1[0-2])[-/](0[1-9]|[12][0-9]|3[01])[-/](19|20)\d{2}\b',
        PIIType.KOREAN_RRN: r'\b\d{6}[-]?[1-4]\d{6}\b',  # 주민등록번호
    }
    
    # 필드명 기반 PII 감지
    SENSITIVE_FIELD_NAMES = {
        'password', 'passwd', 'pwd', 'secret', 'token', 'api_key', 'apikey',
        'access_token', 'refresh_token', 'private_key', 'ssn', 'social_security',
        'credit_card', 'cc_number', 'cvv', 'email', 'phone', 'phone_number',
        'date_of_birth', 'dob', 'birthdate', 'rrn', 'jumin'
    }
    
    def __init__(
        self, 
        encryption_key: Optional[bytes] = None,
        strategy: PIIHandlingStrategy = PIIHandlingStrategy.ANONYMIZE
    ):
        """
        Args:
            encryption_key: 암호화 키 (없으면 자동 생성)
            strategy: 기본 PII 처리 전략
        """
        if encryption_key:
            self.cipher = Fernet(encryption_key)
        else:
            self.cipher = Fernet(Fernet.generate_key())
        
        self.strategy = strategy
        self._compiled_patterns = {
            pii_type: re.compile(pattern, re.IGNORECASE)
            for pii_type, pattern in self.PII_PATTERNS.items()
        }
    
    def detect_pii(self, data: Dict[str, Any]) -> List[PIIMatch]:
        """
        데이터에서 PII 감지
        
        Args:
            data: 검사할 데이터
            
        Returns:
            감지된 PII 목록
        """
        pii_matches = []
        
        def check_value(key: str, value: Any, path: str = ""):
            current_path = f"{path}.{key}" if path else key
            
            # 필드명 기반 감지
            if key.lower() in self.SENSITIVE_FIELD_NAMES:
                pii_matches.append(PIIMatch(
                    field_path=current_path,
                    pii_type=self._infer_pii_type_from_field_name(key),
                    value=str(value) if not isinstance(value, dict) else "<object>",
                    confidence=0.9
                ))
            
            # 패턴 기반 감지 (문자열만)
            if isinstance(value, str):
                for pii_type, pattern in self._compiled_patterns.items():
                    matches = pattern.findall(value)
                    for match in matches:
                        pii_matches.append(PIIMatch(
                            field_path=current_path,
                            pii_type=pii_type,
                            value=match,
                            confidence=1.0
                        ))
            
            # 재귀적 검사
            elif isinstance(value, dict):
                for k, v in value.items():
                    check_value(k, v, current_path)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    check_value(f"[{i}]", item, current_path)
        
        # 최상위 레벨부터 검사
        for key, value in data.items():
            check_value(key, value)
        
        return pii_matches
    
    def handle_pii(
        self, 
        data: Dict[str, Any], 
        strategy: Optional[PIIHandlingStrategy] = None
    ) -> Dict[str, Any]:
        """
        PII 처리
        
        Args:
            data: 처리할 데이터
            strategy: 처리 전략 (없으면 기본 전략 사용)
            
        Returns:
            처리된 데이터
        """
        strategy = strategy or self.strategy
        pii_matches = self.detect_pii(data)
        
        if not pii_matches:
            return data
        
        # 전략별 처리
        if strategy == PIIHandlingStrategy.BLOCK:
            raise ValueError(f"PII detected: {len(pii_matches)} sensitive fields found")
        
        elif strategy == PIIHandlingStrategy.LOG:
            logger.warning(f"PII detected: {[m.field_path for m in pii_matches]}")
            return data
        
        elif strategy == PIIHandlingStrategy.ANONYMIZE:
            return self.anonymize_pii(data, pii_matches)
        
        elif strategy == PIIHandlingStrategy.ENCRYPT:
            return self.encrypt_pii(data, pii_matches)
        
        elif strategy == PIIHandlingStrategy.REDACT:
            return self.redact_pii(data, pii_matches)
        
        return data
    
    def anonymize_pii(self, data: Dict[str, Any], pii_matches: List[PIIMatch]) -> Dict[str, Any]:
        """PII 익명화"""
        anonymized = copy.deepcopy(data)
        
        for match in pii_matches:
            value = self._get_anonymized_value(match)
            self._set_value_by_path(anonymized, match.field_path, value)
        
        return anonymized
    
    def encrypt_pii(self, data: Dict[str, Any], pii_matches: List[PIIMatch]) -> Dict[str, Any]:
        """PII 암호화"""
        encrypted = copy.deepcopy(data)
        
        for match in pii_matches:
            if match.value and match.value != "<object>":
                encrypted_value = self.cipher.encrypt(match.value.encode()).decode()
                # 암호화된 값임을 표시
                encrypted_value = f"ENCRYPTED:{encrypted_value}"
                self._set_value_by_path(encrypted, match.field_path, encrypted_value)
        
        return encrypted
    
    def redact_pii(self, data: Dict[str, Any], pii_matches: List[PIIMatch]) -> Dict[str, Any]:
        """PII 제거"""
        redacted = copy.deepcopy(data)
        
        for match in pii_matches:
            self._set_value_by_path(redacted, match.field_path, "[REDACTED]")
        
        return redacted
    
    def decrypt_value(self, encrypted_value: str) -> str:
        """암호화된 값 복호화"""
        if encrypted_value.startswith("ENCRYPTED:"):
            encrypted_data = encrypted_value[10:]  # "ENCRYPTED:" 제거
            return self.cipher.decrypt(encrypted_data.encode()).decode()
        return encrypted_value
    
    def _get_anonymized_value(self, match: PIIMatch) -> str:
        """PII 타입별 익명화 값 생성"""
        if match.pii_type == PIIType.EMAIL:
            # 도메인은 유지하고 사용자명만 익명화
            if '@' in match.value:
                domain = match.value.split('@')[1]
                hash_value = hashlib.md5(match.value.encode()).hexdigest()[:8]
                return f"user_{hash_value}@{domain}"
        
        elif match.pii_type == PIIType.PHONE:
            # 마지막 4자리만 표시
            return f"***-***-{match.value[-4:]}" if len(match.value) >= 4 else "***"
        
        elif match.pii_type == PIIType.CREDIT_CARD:
            # 마지막 4자리만 표시
            return f"****-****-****-{match.value[-4:]}" if len(match.value) >= 4 else "****"
        
        elif match.pii_type == PIIType.IP_ADDRESS:
            # 클래스 C까지만 표시
            parts = match.value.split('.')
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.XXX"
        
        elif match.pii_type == PIIType.KOREAN_RRN:
            # 생년월일만 표시
            return f"{match.value[:6]}-*******" if len(match.value) >= 6 else "*******"
        
        # 기본: 해시 기반 익명화
        hash_value = hashlib.md5(match.value.encode()).hexdigest()[:8]
        return f"{match.pii_type.value}_{hash_value}"
    
    def _infer_pii_type_from_field_name(self, field_name: str) -> PIIType:
        """필드명에서 PII 타입 추론"""
        field_lower = field_name.lower()
        
        if 'email' in field_lower:
            return PIIType.EMAIL
        elif 'phone' in field_lower:
            return PIIType.PHONE
        elif 'ssn' in field_lower or 'social' in field_lower:
            return PIIType.SSN
        elif 'credit' in field_lower or 'card' in field_lower or 'cc' in field_lower:
            return PIIType.CREDIT_CARD
        elif 'password' in field_lower or 'passwd' in field_lower or 'pwd' in field_lower:
            return PIIType.PASSWORD
        elif 'api' in field_lower and 'key' in field_lower:
            return PIIType.API_KEY
        elif 'birth' in field_lower or 'dob' in field_lower:
            return PIIType.DATE_OF_BIRTH
        elif 'rrn' in field_lower or 'jumin' in field_lower:
            return PIIType.KOREAN_RRN
        
        return PIIType.API_KEY  # 기본값
    
    def _set_value_by_path(self, data: Dict[str, Any], path: str, value: Any):
        """경로를 따라 값 설정"""
        parts = path.split('.')
        current = data
        
        for i, part in enumerate(parts[:-1]):
            # 배열 인덱스 처리
            if part.startswith('[') and part.endswith(']'):
                index = int(part[1:-1])
                current = current[index]
            else:
                if part not in current:
                    return
                current = current[part]
        
        # 마지막 부분 설정
        last_part = parts[-1]
        if last_part.startswith('[') and last_part.endswith(']'):
            index = int(last_part[1:-1])
            current[index] = value
        else:
            current[last_part] = value


# 환경별 PII 핸들러 팩토리
def create_pii_handler(environment: str = "development") -> PIIHandler:
    """환경별 PII 핸들러 생성"""
    import os
    
    if environment == "production":
        # 프로덕션: 암호화 사용
        encryption_key = os.getenv("PII_ENCRYPTION_KEY")
        if encryption_key:
            encryption_key = encryption_key.encode()
        
        return PIIHandler(
            encryption_key=encryption_key,
            strategy=PIIHandlingStrategy.ENCRYPT
        )
    
    elif environment == "staging":
        # 스테이징: 익명화 사용
        return PIIHandler(strategy=PIIHandlingStrategy.ANONYMIZE)
    
    else:
        # 개발: 로깅만
        return PIIHandler(strategy=PIIHandlingStrategy.LOG)