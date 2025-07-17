"""
Comprehensive Input Sanitization Module
모든 사용자 입력에 대한 보안 검증 및 정화 처리
"""

import re
import html
import json
import urllib.parse
from typing import Any, Dict, List, Optional, Union
import logging

logger = logging.getLogger(__name__)


class SecurityViolationError(Exception):
    """보안 위반 시 발생하는 예외"""
    pass


class InputSanitizer:
    """포괄적인 입력 데이터 보안 검증 및 정화 클래스"""
    
    # SQL Injection 패턴들
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|OR|AND)\b)",
        r"(--|#|/\*|\*/)",
        r"(\b(CHAR|NCHAR|VARCHAR|NVARCHAR|CAST|CONVERT|SUBSTRING)\s*\()",
        r"(\b(INFORMATION_SCHEMA|SYS|MASTER|MSDB|TEMPDB)\b)",
        r"(\b(XP_|SP_)\w+)",
        r"(\b(LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)\b)",
        r"(\b(WAITFOR\s+DELAY|BENCHMARK\s*\()\b)",
        r"(\b(SLEEP\s*\(|PG_SLEEP\s*\()\b)"
    ]
    
    # XSS 패턴들
    XSS_PATTERNS = [
        r"<\s*script[^>]*>.*?</\s*script\s*>",
        r"<\s*iframe[^>]*>.*?</\s*iframe\s*>",
        r"<\s*object[^>]*>.*?</\s*object\s*>",
        r"<\s*embed[^>]*>",
        r"<\s*link[^>]*>",
        r"<\s*meta[^>]*>",
        r"<\s*style[^>]*>.*?</\s*style\s*>",
        r"javascript\s*:",
        r"vbscript\s*:",
        r"data\s*:",
        r"on\w+\s*=",
        r"expression\s*\(",
        r"@import",
        r"alert\s*\(",
        r"eval\s*\(",
        r"document\.",
        r"window\.",
        r"location\.",
        r"cookie"
    ]
    
    # Path Traversal 패턴들
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\./",
        r"\.\.\\",
        r"%2e%2e%2f",
        r"%2e%2e%5c",
        r"\.\.%2f",
        r"\.\.%5c",
        r"%2e%2e/",
        r"%2e%2e\\",
        r"..%c0%af",
        r"..%c1%9c"
    ]
    
    # Command Injection 패턴들 - 실제 명령어 실행 컨텍스트에서만 사용
    COMMAND_INJECTION_PATTERNS = [
        r"[;&|`$]",
        # 명령어 패턴은 shell command 필드에서만 체크해야 함
        # 일반 텍스트에서 'id', 'name' 같은 단어는 정상적인 사용
        r"\\x[0-9a-fA-F]{2}",
        r"%[0-9a-fA-F]{2}",
        r"\$\{.*\}",
        r"\$\(.*\)",
        r"`.*`"
    ]
    
    # Shell 명령어 전용 패턴 (shell command 필드에서만 사용)
    SHELL_COMMAND_PATTERNS = [
        r"\b(cat|ls|pwd|whoami|uname|ps|netstat|ifconfig|ping|wget|curl|nc|telnet|ssh|ftp)\b",
        r"\b(rm|mv|cp|chmod|chown|mkdir|rmdir|touch|find|grep|awk|sed|sort|uniq|head|tail)\b",
        r"\b(python|perl|ruby|php|node|java|gcc|make|sudo|su)\b"
    ]
    
    # NoSQL Injection 패턴들
    NOSQL_INJECTION_PATTERNS = [
        r"\$where",
        r"\$ne",
        r"\$gt",
        r"\$lt",
        r"\$gte",
        r"\$lte",
        r"\$in",
        r"\$nin",
        r"\$or",
        r"\$and",
        r"\$not",
        r"\$nor",
        r"\$exists",
        r"\$type",
        r"\$mod",
        r"\$regex",
        r"\$text",
        r"\$expr",
        r"\$jsonSchema",
        r"\$elemMatch"
    ]
    
    # LDAP Injection 패턴들 - 다국어 입력을 고려하여 개선
    LDAP_INJECTION_PATTERNS = [
        # 단순 괄호는 제외하고 LDAP 필터 패턴만 검사
        r"\(\s*[&|!]\s*\(",  # LDAP 논리 연산자 패턴
        r"\\[0-9a-fA-F]{2}",
        r"(cn=|uid=|ou=|dc=|objectClass=).*[)(*&|!]",  # LDAP 속성과 특수문자 조합
        r"\*\)|\(\*"  # 와일드카드와 괄호 조합
    ]
    
    def __init__(self):
        # 컴파일된 정규식 패턴들
        self.sql_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.SQL_INJECTION_PATTERNS]
        self.xss_regex = [re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in self.XSS_PATTERNS]
        self.path_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.PATH_TRAVERSAL_PATTERNS]
        self.cmd_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.COMMAND_INJECTION_PATTERNS]
        self.shell_cmd_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.SHELL_COMMAND_PATTERNS]
        self.nosql_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.NOSQL_INJECTION_PATTERNS]
        self.ldap_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.LDAP_INJECTION_PATTERNS]
    
    def detect_sql_injection(self, value: str) -> bool:
        """SQL Injection 패턴 탐지"""
        for pattern in self.sql_regex:
            if pattern.search(value):
                return True
        return False
    
    def detect_xss(self, value: str) -> bool:
        """XSS 패턴 탐지"""
        for pattern in self.xss_regex:
            if pattern.search(value):
                return True
        return False
    
    def detect_path_traversal(self, value: str) -> bool:
        """Path Traversal 패턴 탐지"""
        for pattern in self.path_regex:
            if pattern.search(value):
                return True
        return False
    
    def detect_command_injection(self, value: str, is_shell_context: bool = False) -> bool:
        """Command Injection 패턴 탐지
        
        Args:
            value: 검사할 문자열
            is_shell_context: shell 명령어 실행 컨텍스트인지 여부
        """
        # 기본 command injection 패턴 체크
        for pattern in self.cmd_regex:
            if pattern.search(value):
                return True
        
        # shell context에서만 명령어 패턴 체크
        if is_shell_context:
            for pattern in self.shell_cmd_regex:
                if pattern.search(value):
                    return True
        
        return False
    
    def detect_nosql_injection(self, value: str) -> bool:
        """NoSQL Injection 패턴 탐지"""
        for pattern in self.nosql_regex:
            if pattern.search(value):
                return True
        return False
    
    def detect_ldap_injection(self, value: str) -> bool:
        """LDAP Injection 패턴 탐지"""
        for pattern in self.ldap_regex:
            if pattern.search(value):
                return True
        return False
    
    def sanitize_string(self, value: str, max_length: int = 1000) -> str:
        """문자열 정화 처리"""
        if not isinstance(value, str):
            raise SecurityViolationError(f"Expected string, got {type(value)}")
        
        # 길이 제한
        if len(value) > max_length:
            raise SecurityViolationError(f"String too long: {len(value)} > {max_length}")
        
        # 악성 패턴 탐지
        if self.detect_sql_injection(value):
            raise SecurityViolationError("SQL injection pattern detected")
        
        if self.detect_xss(value):
            raise SecurityViolationError("XSS pattern detected")
        
        if self.detect_path_traversal(value):
            raise SecurityViolationError("Path traversal pattern detected")
        
        # Command injection은 특정 컨텍스트에서만 체크
        # 일반 텍스트 필드에서는 체크하지 않음
        
        if self.detect_nosql_injection(value):
            raise SecurityViolationError("NoSQL injection pattern detected")
        
        if self.detect_ldap_injection(value):
            raise SecurityViolationError("LDAP injection pattern detected")
        
        # HTML 인코딩 제거 - 다국어 입력을 손상시킴
        # TerminusDB는 자체적으로 안전한 저장을 보장
        sanitized = value
        
        # 제어 문자만 제거 (다국어 문자는 보존)
        sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', sanitized)
        
        # URL 디코딩 후 재검증
        try:
            decoded = urllib.parse.unquote(sanitized)
            if decoded != sanitized:
                # 디코딩된 값도 검증
                self.sanitize_string(decoded, max_length)
        except (UnicodeDecodeError, ValueError) as e:
            # URL 디코딩 실패는 보안 위반으로 처리
            logger.error(f"URL decoding failed for potentially malicious input: {e}")
            raise SecurityViolationError(f"Invalid URL encoding detected: {str(e)}")
        
        return sanitized
    
    def sanitize_field_name(self, value: str) -> str:
        """필드명 정화 (id, name 등 일반적인 필드명 허용)"""
        if not isinstance(value, str):
            raise SecurityViolationError(f"Expected string, got {type(value)}")
        
        # 필드명은 영문자, 숫자, 언더스코어만 허용
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', value):
            raise SecurityViolationError("Field name contains invalid characters")
        
        if len(value) > 100:
            raise SecurityViolationError(f"Field name too long: {len(value)} > 100")
        
        return value
    
    def sanitize_description(self, value: str) -> str:
        """설명 텍스트 정화 (command injection 체크 안함)"""
        if not isinstance(value, str):
            raise SecurityViolationError(f"Expected string, got {type(value)}")
        
        if len(value) > 5000:  # 설명은 더 길게 허용
            raise SecurityViolationError(f"Description too long: {len(value)} > 5000")
        
        # SQL injection, XSS, Path traversal만 체크
        if self.detect_sql_injection(value):
            raise SecurityViolationError("SQL injection pattern detected")
        
        if self.detect_xss(value):
            raise SecurityViolationError("XSS pattern detected")
        
        if self.detect_path_traversal(value):
            raise SecurityViolationError("Path traversal pattern detected")
        
        # Command injection 체크 안함 - 설명에서 'id'와 같은 단어는 정상적
        
        # 제어 문자만 제거
        sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', value)
        return sanitized
    
    def sanitize_shell_command(self, value: str) -> str:
        """Shell 명령어 컨텍스트의 문자열 정화 (모든 보안 체크 적용)"""
        if not isinstance(value, str):
            raise SecurityViolationError(f"Expected string, got {type(value)}")
        
        # 모든 보안 체크 적용
        sanitized = self.sanitize_string(value)
        
        # Shell 명령어 패턴도 추가로 체크
        if self.detect_command_injection(value, is_shell_context=True):
            raise SecurityViolationError("Shell command injection pattern detected")
        
        return sanitized
    
    def sanitize_dict(self, data: Dict[str, Any], max_depth: int = 10, current_depth: int = 0) -> Dict[str, Any]:
        """딕셔너리 재귀적 정화 처리"""
        if current_depth > max_depth:
            raise SecurityViolationError(f"Dictionary nesting too deep: {current_depth} > {max_depth}")
        
        if not isinstance(data, dict):
            raise SecurityViolationError(f"Expected dict, got {type(data)}")
        
        if len(data) > 100:  # 너무 많은 키 방지
            raise SecurityViolationError(f"Too many keys in dict: {len(data)} > 100")
        
        sanitized = {}
        for key, value in data.items():
            # 키는 필드명으로 처리 (id, name 등 허용)
            if isinstance(key, str):
                clean_key = self.sanitize_field_name(key)
            else:
                clean_key = self.sanitize_any(key, max_depth, current_depth + 1)
            
            # 값은 컨텍스트에 따라 처리
            if isinstance(value, str) and key in ['description', 'comment', 'note', 'label']:
                # 설명 필드는 description sanitizer 사용
                clean_value = self.sanitize_description(value)
            elif isinstance(value, str) and key in ['command', 'script', 'exec']:
                # 명령어 필드는 shell command sanitizer 사용
                clean_value = self.sanitize_shell_command(value)
            else:
                # 일반 값은 기본 sanitizer 사용
                clean_value = self.sanitize_any(value, max_depth, current_depth + 1)
            
            sanitized[clean_key] = clean_value
        
        return sanitized
    
    def sanitize_list(self, data: List[Any], max_depth: int = 10, current_depth: int = 0) -> List[Any]:
        """리스트 정화 처리"""
        if current_depth > max_depth:
            raise SecurityViolationError(f"List nesting too deep: {current_depth} > {max_depth}")
        
        if not isinstance(data, list):
            raise SecurityViolationError(f"Expected list, got {type(data)}")
        
        if len(data) > 1000:  # 너무 많은 요소 방지
            raise SecurityViolationError(f"Too many items in list: {len(data)} > 1000")
        
        sanitized = []
        for item in data:
            clean_item = self.sanitize_any(item, max_depth, current_depth + 1)
            sanitized.append(clean_item)
        
        return sanitized
    
    def sanitize_any(self, value: Any, max_depth: int = 10, current_depth: int = 0) -> Any:
        """모든 타입의 데이터 정화 처리"""
        if value is None:
            return None
        
        if isinstance(value, str):
            # 기본적으로 description sanitizer 사용 (command injection 체크 안함)
            # 이렇게 하면 'id', 'name' 등의 일반적인 단어가 차단되지 않음
            return self.sanitize_description(value)
        
        elif isinstance(value, (int, float, bool)):
            # 숫자와 불린값은 안전
            if isinstance(value, (int, float)):
                # 극단적인 값 방지
                if abs(value) > 10**15:
                    raise SecurityViolationError(f"Number too large: {value}")
            return value
        
        elif isinstance(value, dict):
            return self.sanitize_dict(value, max_depth, current_depth)
        
        elif isinstance(value, list):
            return self.sanitize_list(value, max_depth, current_depth)
        
        else:
            # 기타 타입은 문자열로 변환 후 정화
            return self.sanitize_string(str(value))
    
    def validate_database_name(self, db_name: str) -> str:
        """데이터베이스 이름 검증"""
        if not db_name or not isinstance(db_name, str):
            raise SecurityViolationError("Database name must be a non-empty string")
        
        # 데이터베이스 이름은 영숫자, 하이픈, 언더스코어만 허용
        if not re.match(r'^[a-zA-Z0-9_-]+$', db_name):
            raise SecurityViolationError("Database name contains invalid characters")
        
        if len(db_name) > 50:
            raise SecurityViolationError("Database name too long")
        
        if db_name.startswith(('_', '-')) or db_name.endswith(('_', '-')):
            raise SecurityViolationError("Database name cannot start or end with _ or -")
        
        return db_name
    
    def validate_class_id(self, class_id: str) -> str:
        """클래스 ID 검증"""
        if not class_id or not isinstance(class_id, str):
            raise SecurityViolationError("Class ID must be a non-empty string")
        
        # 클래스 ID는 영숫자, 하이픈, 언더스코어, 콜론만 허용 (네임스페이스 고려)
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_:-]*$', class_id):
            raise SecurityViolationError("Class ID contains invalid characters")
        
        if len(class_id) > 100:
            raise SecurityViolationError("Class ID too long")
        
        return class_id
    
    def validate_branch_name(self, branch_name: str) -> str:
        """브랜치 이름 검증"""
        if not branch_name or not isinstance(branch_name, str):
            raise SecurityViolationError("Branch name must be a non-empty string")
        
        # 브랜치 이름은 영숫자, 하이픈, 언더스코어, 슬래시만 허용
        if not re.match(r'^[a-zA-Z0-9_/-]+$', branch_name):
            raise SecurityViolationError("Branch name contains invalid characters")
        
        if len(branch_name) > 100:
            raise SecurityViolationError("Branch name too long")
        
        # 예약된 이름 확인
        reserved_names = {'HEAD', 'refs', 'objects', 'info', 'hooks'}
        if branch_name.lower() in reserved_names:
            raise SecurityViolationError(f"'{branch_name}' is a reserved branch name")
        
        return branch_name


# 전역 인스턴스
input_sanitizer = InputSanitizer()


def sanitize_input(data: Any) -> Any:
    """전역 입력 정화 함수"""
    try:
        return input_sanitizer.sanitize_any(data)
    except SecurityViolationError as e:
        logger.warning(f"Security violation detected: {e}")
        raise
    except (ValueError, TypeError, AttributeError) as e:
        logger.error(f"Input sanitization error: {e}")
        raise SecurityViolationError(f"Input sanitization failed: {e}")


def validate_db_name(db_name: str) -> str:
    """데이터베이스 이름 검증 함수"""
    return input_sanitizer.validate_database_name(db_name)


def validate_class_id(class_id: str) -> str:
    """클래스 ID 검증 함수"""
    return input_sanitizer.validate_class_id(class_id)


def validate_branch_name(branch_name: str) -> str:
    """브랜치 이름 검증 함수"""
    return input_sanitizer.validate_branch_name(branch_name)