"""
Input Sanitization Layer
입력 정제 및 보안 검증 전처리 계층
"""
import re
import unicodedata
import html
from typing import Any, Dict, List, Optional, Tuple, Union
from enum import Enum
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class SanitizationLevel(str, Enum):
    """정제 레벨"""
    BASIC = "basic"          # 기본 정제 (널 바이트, 제어 문자)
    STANDARD = "standard"    # 표준 정제 (기본 + 정규화)
    STRICT = "strict"        # 엄격 정제 (표준 + 인젝션 방지)
    PARANOID = "paranoid"    # 매우 엄격 (엄격 + 추가 보안)


class SanitizationResult(BaseModel):
    """정제 결과"""
    original_value: str
    sanitized_value: str
    was_modified: bool
    detected_threats: List[str] = []
    applied_rules: List[str] = []
    risk_score: int = 0  # 0-100


class InputSanitizer:
    """입력 정제기"""
    
    # 위험한 패턴들
    DANGEROUS_PATTERNS = {
        'null_bytes': re.compile(r'\x00'),
        'control_chars': re.compile(r'[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]'),
        'sql_injection': re.compile(r'(\b(union|select|insert|update|delete|drop|exec|script)\b|--|;|\'\s*or\s*\'|\/\*.*\*\/)', re.IGNORECASE),
        'xss_scripts': re.compile(r'<\s*script[^>]*>.*?<\s*/\s*script\s*>', re.IGNORECASE | re.DOTALL),
        'command_injection': re.compile(r'(\$\(|\`|&&|\|\||\;|\|)', re.IGNORECASE),
        'path_traversal': re.compile(r'(\.\./|\.\.\\|%2e%2e%2f|%2e%2e%5c)', re.IGNORECASE),
        'log4j_injection': re.compile(r'\$\{jndi:', re.IGNORECASE),
        'template_injection': re.compile(r'(\{\{.*\}\}|\{%.*%\})', re.IGNORECASE),
        'html_entities': re.compile(r'&[a-zA-Z]+;|&#\d+;|&#x[a-fA-F0-9]+;'),
        'unicode_exploitation': re.compile(r'[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]'),  # Zero-width, bidi override
        'suspicious_chars': re.compile(r'[<>&"\'\\\x00-\x1f\x7f-\x9f]'),
        'excessive_length': lambda x: len(x) > 10000,
        'repeated_chars': re.compile(r'(.)\1{100,}'),  # 같은 문자 100개 이상 반복
    }
    
    # 허용되는 문자 패턴 (엔티티 명명용)
    SAFE_PATTERNS = {
        'alphanumeric': re.compile(r'^[a-zA-Z0-9_-]*$'),
        'alphanumeric_unicode': re.compile(r'^[\w\-]*$', re.UNICODE),
        'ascii_printable': re.compile(r'^[ -~]*$'),
        'basic_naming': re.compile(r'^[a-zA-Z][a-zA-Z0-9_]*$'),
    }
    
    def __init__(self, default_level: SanitizationLevel = SanitizationLevel.STANDARD):
        """
        초기화
        
        Args:
            default_level: 기본 정제 레벨
        """
        self.default_level = default_level
        
        # 정제 규칙 함수 매핑
        self.sanitization_rules = {
            SanitizationLevel.BASIC: [
                self._remove_null_bytes,
                self._remove_control_chars,
            ],
            SanitizationLevel.STANDARD: [
                self._remove_null_bytes,
                self._remove_control_chars,
                self._normalize_unicode,
                self._trim_whitespace,
            ],
            SanitizationLevel.STRICT: [
                self._remove_null_bytes,
                self._remove_control_chars,
                self._normalize_unicode,
                self._trim_whitespace,
                self._prevent_injections,
                self._sanitize_html,
                self._limit_length,
            ],
            SanitizationLevel.PARANOID: [
                self._remove_null_bytes,
                self._remove_control_chars,
                self._normalize_unicode,
                self._trim_whitespace,
                self._prevent_injections,
                self._sanitize_html,
                self._limit_length,
                self._remove_suspicious_unicode,
                self._prevent_homograph_attacks,
                self._detect_excessive_repetition,
            ]
        }
    
    def sanitize(
        self,
        value: str,
        level: Optional[SanitizationLevel] = None,
        max_length: int = 1000,
        allow_unicode: bool = True
    ) -> SanitizationResult:
        """
        입력값 정제
        
        Args:
            value: 정제할 값
            level: 정제 레벨
            max_length: 최대 길이
            allow_unicode: 유니코드 허용 여부
            
        Returns:
            정제 결과
        """
        if not isinstance(value, str):
            value = str(value)
        
        original_value = value
        current_value = value
        detected_threats = []
        applied_rules = []
        risk_score = 0
        
        # 정제 레벨 결정
        sanitization_level = level or self.default_level
        
        # 위협 탐지 먼저 수행
        threats, threat_score = self._detect_threats(current_value)
        detected_threats.extend(threats)
        risk_score += threat_score
        
        # 정제 규칙 적용
        rules = self.sanitization_rules.get(sanitization_level, [])
        
        for rule_func in rules:
            try:
                rule_name = rule_func.__name__
                if rule_name == '_limit_length':
                    # 길이 제한 규칙에 max_length 전달
                    new_value = rule_func(current_value, max_length)
                elif rule_name in ['_normalize_unicode', '_remove_suspicious_unicode']:
                    # 유니코드 관련 규칙에 allow_unicode 전달
                    new_value = rule_func(current_value, allow_unicode)
                else:
                    new_value = rule_func(current_value)
                
                if new_value != current_value:
                    applied_rules.append(rule_name)
                    current_value = new_value
                    
            except Exception as e:
                logger.warning(f"Sanitization rule {rule_func.__name__} failed: {e}")
        
        # 최종 검증
        final_threats, final_score = self._detect_threats(current_value)
        if final_threats:
            # 정제 후에도 위협이 남아있으면 점수 추가
            risk_score += final_score // 2
        
        return SanitizationResult(
            original_value=original_value,
            sanitized_value=current_value,
            was_modified=(original_value != current_value),
            detected_threats=detected_threats,
            applied_rules=applied_rules,
            risk_score=min(risk_score, 100)
        )
    
    def _detect_threats(self, value: str) -> Tuple[List[str], int]:
        """위협 탐지"""
        threats = []
        score = 0
        
        for threat_name, pattern in self.DANGEROUS_PATTERNS.items():
            if threat_name == 'excessive_length':
                if pattern(value):
                    threats.append(threat_name)
                    score += 20
            elif hasattr(pattern, 'search') and pattern.search(value):
                threats.append(threat_name)
                # 위협별 위험도 점수
                threat_scores = {
                    'null_bytes': 30,
                    'sql_injection': 40,
                    'xss_scripts': 40,
                    'command_injection': 40,
                    'log4j_injection': 50,
                    'path_traversal': 30,
                    'template_injection': 35,
                    'control_chars': 15,
                    'html_entities': 10,
                    'unicode_exploitation': 25,
                    'suspicious_chars': 15,
                    'repeated_chars': 10,
                }
                score += threat_scores.get(threat_name, 10)
        
        return threats, score
    
    def _remove_null_bytes(self, value: str) -> str:
        """널 바이트 제거"""
        return value.replace('\x00', '')
    
    def _remove_control_chars(self, value: str) -> str:
        """제어 문자 제거"""
        return self.DANGEROUS_PATTERNS['control_chars'].sub('', value)
    
    def _normalize_unicode(self, value: str, allow_unicode: bool = True) -> str:
        """유니코드 정규화"""
        if not allow_unicode:
            # 유니코드 허용하지 않으면 ASCII만 허용
            value = ''.join(char for char in value if ord(char) < 128)
        
        # NFKC 정규화 (호환성 합성)
        normalized = unicodedata.normalize('NFKC', value)
        
        # 위험한 유니코드 카테고리 제거
        safe_categories = {'L', 'N', 'P', 'S', 'Z'}  # Letter, Number, Punctuation, Symbol, Separator
        filtered = ''.join(
            char for char in normalized 
            if unicodedata.category(char)[0] in safe_categories
        )
        
        return filtered
    
    def _trim_whitespace(self, value: str) -> str:
        """앞뒤 공백 제거 및 연속 공백 정리"""
        # 앞뒤 공백 제거
        value = value.strip()
        
        # 연속된 공백을 하나로 압축
        value = re.sub(r'\s+', ' ', value)
        
        return value
    
    def _prevent_injections(self, value: str) -> str:
        """인젝션 공격 방지"""
        # SQL 키워드 이스케이프
        sql_keywords = ['union', 'select', 'insert', 'update', 'delete', 'drop', 'exec', 'script']
        for keyword in sql_keywords:
            # 단어 경계에서만 매치되도록 개선
            pattern = re.compile(rf'\b{keyword}\b', re.IGNORECASE)
            value = pattern.sub(f'_{keyword}_', value)
        
        # 위험한 문자들 이스케이프
        dangerous_chars = {
            ';': '&#59;',
            '--': '&#45;&#45;',
            '/*': '&#47;&#42;',
            '*/': '&#42;&#47;',
            '${': '&#36;&#123;',
            '`': '&#96;',
        }
        
        for dangerous, safe in dangerous_chars.items():
            value = value.replace(dangerous, safe)
        
        return value
    
    def _sanitize_html(self, value: str) -> str:
        """HTML 정제"""
        # HTML 엔티티 디코딩 후 재인코딩
        value = html.unescape(value)
        value = html.escape(value, quote=True)
        
        # 스크립트 태그 완전 제거
        value = self.DANGEROUS_PATTERNS['xss_scripts'].sub('', value)
        
        # 기타 위험한 태그들 제거
        dangerous_tags = ['script', 'iframe', 'object', 'embed', 'form', 'input']
        for tag in dangerous_tags:
            pattern = re.compile(f'<\\s*{tag}[^>]*>.*?<\\s*/\\s*{tag}\\s*>', re.IGNORECASE | re.DOTALL)
            value = pattern.sub('', value)
            pattern = re.compile(f'<\\s*{tag}[^>]*/?>', re.IGNORECASE)
            value = pattern.sub('', value)
        
        return value
    
    def _limit_length(self, value: str, max_length: int = 1000) -> str:
        """길이 제한"""
        if len(value) > max_length:
            # 안전하게 자르기 (UTF-8 바이트 경계 고려)
            value = value[:max_length]
            
            # 마지막 문자가 불완전한 UTF-8 시퀀스일 수 있으므로 검증
            try:
                value.encode('utf-8')
            except UnicodeEncodeError:
                # 마지막 몇 문자를 제거해서 안전하게 만들기
                for i in range(1, min(5, len(value))):
                    try:
                        value[:-i].encode('utf-8')
                        value = value[:-i]
                        break
                    except UnicodeEncodeError:
                        continue
        
        return value
    
    def _remove_suspicious_unicode(self, value: str, allow_unicode: bool = True) -> str:
        """의심스러운 유니코드 문자 제거"""
        if not allow_unicode:
            return value
        
        # Zero-width 문자들과 방향 제어 문자들 제거
        value = self.DANGEROUS_PATTERNS['unicode_exploitation'].sub('', value)
        
        # 혼동을 일으킬 수 있는 유사 문자들 정리
        confusing_chars = {
            '\u2013': '-',  # en dash
            '\u2014': '-',  # em dash
            '\u2018': "'",  # left single quote
            '\u2019': "'",  # right single quote
            '\u201c': '"',  # left double quote
            '\u201d': '"',  # right double quote
            '\u00a0': ' ',  # non-breaking space
        }
        
        for confusing, replacement in confusing_chars.items():
            value = value.replace(confusing, replacement)
        
        return value
    
    def _prevent_homograph_attacks(self, value: str) -> str:
        """호모그래프 공격 방지"""
        # 라틴 문자와 유사한 키릴 문자들을 라틴으로 변환
        homograph_map = {
            'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y', 'х': 'x',
            'А': 'A', 'В': 'B', 'Е': 'E', 'К': 'K', 'М': 'M', 'Н': 'H', 'О': 'O',
            'Р': 'P', 'С': 'C', 'Т': 'T', 'У': 'Y', 'Х': 'X'
        }
        
        for cyrillic, latin in homograph_map.items():
            value = value.replace(cyrillic, latin)
        
        return value
    
    def _detect_excessive_repetition(self, value: str) -> str:
        """과도한 반복 문자 정리"""
        # 같은 문자가 10개 이상 반복되면 3개로 축소
        value = re.sub(r'(.)\1{9,}', r'\1\1\1', value)
        
        # 같은 단어가 5번 이상 반복되면 2번으로 축소
        value = re.sub(r'\b(\w+)(\s+\1){4,}\b', r'\1 \1', value)
        
        return value
    
    def validate_naming_input(self, value: str) -> Tuple[bool, List[str]]:
        """
        명명 규칙용 입력 검증
        
        Args:
            value: 검증할 값
            
        Returns:
            (유효성, 문제점_목록)
        """
        issues = []
        
        # 기본 안전성 검사
        result = self.sanitize(value, SanitizationLevel.STRICT)
        
        if result.detected_threats:
            issues.extend([f"Security threat detected: {threat}" for threat in result.detected_threats])
        
        if result.risk_score > 30:
            issues.append(f"High risk score: {result.risk_score}")
        
        # 명명 규칙 특화 검증
        if not value:
            issues.append("Empty value not allowed")
        
        if len(value) < 1:
            issues.append("Value too short")
        
        if len(value) > 255:
            issues.append("Value too long (max 255 characters)")
        
        # 시작/끝 문자 검증
        if value and not value[0].isalpha():
            issues.append("Must start with a letter")
        
        if value and value.endswith(('_', '-')):
            issues.append("Cannot end with underscore or hyphen")
        
        # 연속 특수문자 검증
        if re.search(r'[_-]{2,}', value):
            issues.append("Cannot contain consecutive underscores or hyphens")
        
        # 예약어/시스템 키워드 검사
        reserved_patterns = [
            r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])$',  # Windows reserved
            r'^\.+$',  # Only dots
            r'^\s+$',  # Only whitespace
        ]
        
        for pattern in reserved_patterns:
            if re.match(pattern, value, re.IGNORECASE):
                issues.append(f"Reserved word or pattern: {value}")
        
        return len(issues) == 0, issues
    
    def get_safe_subset(self, value: str, pattern_name: str = 'basic_naming') -> str:
        """
        안전한 문자만 추출
        
        Args:
            value: 원본 값
            pattern_name: 사용할 패턴 이름
            
        Returns:
            안전한 문자만으로 구성된 문자열
        """
        if pattern_name == 'basic_naming':
            # 영문자, 숫자, 언더스코어만 허용
            safe_chars = re.findall(r'[a-zA-Z0-9_]', value)
            result = ''.join(safe_chars)
            
            # 첫 문자가 숫자나 언더스코어면 제거
            while result and not result[0].isalpha():
                result = result[1:]
            
            return result
        
        elif pattern_name == 'alphanumeric':
            return re.sub(r'[^a-zA-Z0-9_-]', '', value)
        
        elif pattern_name == 'ascii_printable':
            return ''.join(char for char in value if 32 <= ord(char) <= 126)
        
        else:
            # 기본값: 영숫자만
            return re.sub(r'[^a-zA-Z0-9]', '', value)


class SecureInputProcessor:
    """보안 입력 처리기 - 명명 규칙 전용"""
    
    def __init__(self):
        self.sanitizer = InputSanitizer(SanitizationLevel.STRICT)
    
    def process_entity_name(
        self,
        name: str,
        auto_fix: bool = True,
        max_length: int = 255
    ) -> Tuple[str, bool, List[str]]:
        """
        엔티티 이름 처리
        
        Args:
            name: 원본 이름
            auto_fix: 자동 수정 여부
            max_length: 최대 길이
            
        Returns:
            (처리된_이름, 수정됨, 문제점_목록)
        """
        # 1단계: 보안 정제
        sanitization_result = self.sanitizer.sanitize(
            name, 
            SanitizationLevel.STRICT,
            max_length=max_length
        )
        
        processed_name = sanitization_result.sanitized_value
        issues = []
        
        # 보안 위협 발견시 경고
        if sanitization_result.detected_threats:
            issues.extend([f"Security: {threat}" for threat in sanitization_result.detected_threats])
        
        # 2단계: 명명 규칙 검증
        is_valid, naming_issues = self.sanitizer.validate_naming_input(processed_name)
        issues.extend(naming_issues)
        
        # 3단계: 자동 수정 (요청된 경우)
        if auto_fix and (not is_valid or sanitization_result.was_modified):
            # 안전한 문자만 추출
            safe_name = self.sanitizer.get_safe_subset(processed_name, 'basic_naming')
            
            # 빈 문자열이면 기본값 설정
            if not safe_name:
                safe_name = "entity"
            
            # 길이 제한
            if len(safe_name) > max_length:
                safe_name = safe_name[:max_length]
            
            processed_name = safe_name
        
        was_modified = (name != processed_name)
        
        return processed_name, was_modified, issues
    
    def batch_process(
        self,
        names: List[str],
        auto_fix: bool = True
    ) -> List[Tuple[str, str, bool, List[str]]]:
        """
        배치 처리
        
        Args:
            names: 이름 목록
            auto_fix: 자동 수정 여부
            
        Returns:
            (원본_이름, 처리된_이름, 수정됨, 문제점_목록) 리스트
        """
        results = []
        
        for original_name in names:
            processed_name, was_modified, issues = self.process_entity_name(
                original_name, auto_fix
            )
            results.append((original_name, processed_name, was_modified, issues))
        
        return results


# 전역 인스턴스
_input_sanitizer = None
_secure_processor = None

def get_input_sanitizer(level: SanitizationLevel = SanitizationLevel.STANDARD) -> InputSanitizer:
    """입력 정제기 인스턴스 반환"""
    global _input_sanitizer
    if not _input_sanitizer:
        _input_sanitizer = InputSanitizer(level)
    return _input_sanitizer

def get_secure_processor() -> SecureInputProcessor:
    """보안 입력 처리기 인스턴스 반환"""
    global _secure_processor
    if not _secure_processor:
        _secure_processor = SecureInputProcessor()
    return _secure_processor

def sanitize_input(value: str, level: SanitizationLevel = SanitizationLevel.STANDARD) -> SanitizationResult:
    """편의 함수: 입력 정제"""
    sanitizer = get_input_sanitizer(level)
    return sanitizer.sanitize(value, level)

def secure_entity_name(name: str, auto_fix: bool = True) -> Tuple[str, bool, List[str]]:
    """편의 함수: 안전한 엔티티 이름 처리"""
    processor = get_secure_processor()
    return processor.process_entity_name(name, auto_fix)