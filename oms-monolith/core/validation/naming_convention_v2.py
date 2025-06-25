"""
Naming Convention Engine - 간단하고 효과적인 접근
복잡한 약어 처리를 단순화
"""
import re
from typing import List, Dict, Optional, Tuple, Set
from enum import Enum
from datetime import datetime
import logging
from pydantic import BaseModel, Field, field_validator

from core.validation.naming_convention import (
    EntityType, NamingPattern, NamingRule, NamingConvention,
    ValidationIssue, NamingValidationResult
)

logger = logging.getLogger(__name__)


class SimplifiedNamingEngine:
    """단순화된 명명 규칙 엔진"""
    
    # 일반적인 약어 (대문자 유지)
    COMMON_ACRONYMS = {
        'API', 'HTTP', 'HTTPS', 'URL', 'URI', 'JSON', 'XML', 'SQL',
        'HTML', 'CSS', 'JWT', 'UUID', 'TCP', 'UDP', 'FTP', 'SSH',
        'REST', 'SOAP', 'GRPC', 'OAuth', 'SAML', 'LDAP', 'SSO',
        'AWS', 'GCP', 'S3', 'DB', 'IO', 'UI', 'UX', 'AI', 'ML',
        'CPU', 'GPU', 'RAM', 'ROM', 'SSD', 'HDD', 'OS', 'VM',
        'CI', 'CD', 'CLI', 'GUI', 'IDE', 'SDK', 'CDN', 'DNS',
        'B2B', 'B2C', 'CRM', 'ERP', 'HR', 'IT', 'QA', 'PO',
        'ID', 'PK', 'FK', 'CRUD', 'DTO', 'DAO', 'MVC', 'MVP'
    }
    
    def __init__(self, convention: Optional[NamingConvention] = None):
        self.convention = convention or self._get_default_convention()
        self._is_reserved_word = self._create_reserved_checker()
    
    def validate(self, entity_type: EntityType, name: str) -> NamingValidationResult:
        """엔티티 이름 검증"""
        rule = self.convention.rules.get(entity_type)
        if not rule:
            return NamingValidationResult(
                is_valid=True,
                applied_convention=self.convention.id
            )
        
        issues = []
        
        # 기본 검증들...
        # (길이, 패턴, 예약어 등은 기존 로직 사용)
        
        return NamingValidationResult(
            is_valid=len(issues) == 0,
            issues=issues,
            suggestions={name: self.auto_fix(entity_type, name)} if issues else {},
            applied_convention=self.convention.id
        )
    
    def auto_fix(self, entity_type: EntityType, name: str) -> str:
        """자동 교정"""
        rule = self.convention.rules.get(entity_type)
        if not rule:
            return name
        
        # 1. 단어 분리
        words = self._split_into_words(name)
        
        # 2. 접두사/접미사 처리
        if rule.required_prefix:
            if not any(w.lower() == p.lower() for w in words[:1] for p in rule.required_prefix):
                prefix_words = self._split_into_words(rule.required_prefix[0])
                words = prefix_words + words
        
        if rule.required_suffix:
            if not any(w.lower() == s.lower() for w in words[-1:] for s in rule.required_suffix):
                suffix_words = self._split_into_words(rule.required_suffix[0])
                words = words + suffix_words
        
        # 3. 패턴 적용
        result = self._apply_pattern(words, rule.pattern)
        
        # 4. 예약어 처리
        if self._is_reserved_word(result):
            result += '_'
        
        return result
    
    def _split_into_words(self, text: str) -> List[str]:
        """텍스트를 단어로 분리"""
        # snake_case, kebab-case 처리
        if '_' in text:
            parts = text.split('_')
            words = []
            for part in parts:
                words.extend(self._split_camel_case(part))
            return words
        
        if '-' in text:
            parts = text.split('-')
            words = []
            for part in parts:
                words.extend(self._split_camel_case(part))
            return words
        
        return self._split_camel_case(text)
    
    def _split_camel_case(self, text: str) -> List[str]:
        """CamelCase 분리 - 단순하지만 효과적"""
        if not text:
            return []
        
        # 정규식으로 분리
        # 1. 소문자 다음의 대문자
        # 2. 연속된 대문자 (약어)
        # 3. 숫자
        pattern = r'(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[a-zA-Z])(?=[0-9])|(?<=[0-9])(?=[a-zA-Z])'
        
        parts = re.split(pattern, text)
        
        # 빈 문자열 제거하고 정리
        words = []
        for part in parts:
            if part:
                # OAuth2, APIv3 같은 패턴 처리
                if len(part) > 1 and part[-1].isdigit() and part[:-1].isalpha():
                    # 마지막이 숫자면 분리해서 확인
                    alpha_part = part[:-1]
                    digit_part = part[-1]
                    
                    if alpha_part.upper() in self.COMMON_ACRONYMS:
                        words.append(part)  # OAuth2로 유지
                    else:
                        words.append(alpha_part)
                        words.append(digit_part)
                else:
                    words.append(part)
        
        return words
    
    def _apply_pattern(self, words: List[str], pattern: NamingPattern) -> str:
        """단어 리스트에 패턴 적용"""
        if not words:
            return ""
        
        if pattern == NamingPattern.CAMEL_CASE:
            result = words[0].lower()
            for word in words[1:]:
                if word.upper() in self.COMMON_ACRONYMS:
                    # 약어는 첫 글자만 대문자
                    result += word[0].upper() + word[1:].lower()
                else:
                    result += word.capitalize()
            return result
            
        elif pattern == NamingPattern.PASCAL_CASE:
            result = ""
            for word in words:
                if word.upper() in self.COMMON_ACRONYMS:
                    # 약어는 그대로 유지
                    result += word.upper()
                else:
                    result += word.capitalize()
            return result
            
        elif pattern == NamingPattern.SNAKE_CASE:
            return '_'.join(w.lower() for w in words)
            
        elif pattern == NamingPattern.KEBAB_CASE:
            return '-'.join(w.lower() for w in words)
            
        else:
            return ''.join(words)
    
    def _create_reserved_checker(self):
        """예약어 체커 생성"""
        if self.convention.case_sensitive:
            reserved_set = set(self.convention.reserved_words)
            return lambda word: word in reserved_set
        else:
            reserved_lower = {w.lower() for w in self.convention.reserved_words}
            return lambda word: word.lower() in reserved_lower
    
    def _get_default_convention(self) -> NamingConvention:
        """기본 명명 규칙"""
        return NamingConvention(
            id="default",
            name="Default Convention",
            rules={
                EntityType.OBJECT_TYPE: NamingRule(
                    entity_type=EntityType.OBJECT_TYPE,
                    pattern=NamingPattern.PASCAL_CASE,
                    forbidden_prefix=["_", "temp"],
                    min_length=3,
                    max_length=50
                ),
                EntityType.PROPERTY: NamingRule(
                    entity_type=EntityType.PROPERTY,
                    pattern=NamingPattern.CAMEL_CASE,
                    forbidden_prefix=["_", "$"],
                    min_length=2,
                    max_length=50
                ),
                EntityType.ACTION_TYPE: NamingRule(
                    entity_type=EntityType.ACTION_TYPE,
                    pattern=NamingPattern.CAMEL_CASE,
                    required_prefix=["create", "update", "delete", "get", "list", "execute"],
                    min_length=5,
                    max_length=80
                ),
                EntityType.LINK_TYPE: NamingRule(
                    entity_type=EntityType.LINK_TYPE,
                    pattern=NamingPattern.CAMEL_CASE,
                    required_suffix=["Link", "Relation", "Reference", "Association"],
                    min_length=5,
                    max_length=60
                )
            },
            reserved_words=["class", "function", "if", "else", "return", "import", "export",
                           "type", "name", "id", "value", "true", "false", "null"],
            case_sensitive=True,
            auto_fix_enabled=True,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            created_by="system"
        )


# 테스트
if __name__ == "__main__":
    engine = SimplifiedNamingEngine()
    
    test_cases = [
        ("HTTPServerError", "objectType"),
        ("OAuth2Token", "objectType"),
        ("APIv3Client", "property"),
        ("getValue2", "property"),
        ("HTTPClient", "actionType"),
    ]
    
    print("=== Simplified Engine Test ===")
    for name, entity_type in test_cases:
        et = getattr(EntityType, entity_type.upper().replace("TYPE", "_TYPE"))
        words = engine._split_into_words(name)
        fixed = engine.auto_fix(et, name)
        print(f"{name} ({entity_type})")
        print(f"  Words: {words}")
        print(f"  Fixed: {fixed}")
        print()