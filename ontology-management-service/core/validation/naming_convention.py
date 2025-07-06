"""
Naming Convention Engine
엔티티 명명 규칙 검증 및 자동 교정 기능
"""
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator
import logging

logger = logging.getLogger(__name__)


def enum_encoder(v):
    """Pydantic용 Enum 인코더 - 항상 .value 사용"""
    if isinstance(v, Enum):
        return v.value
    return v


def utc_datetime_encoder(v):
    """UTC 시간대 포함 datetime 인코더"""
    if isinstance(v, datetime):
        if v.tzinfo is None:
            # naive datetime을 UTC로 가정
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    return v


class NamingPattern(str, Enum):
    """명명 패턴 타입"""
    CAMEL_CASE = "camelCase"           # objectType, propertyName
    PASCAL_CASE = "PascalCase"         # ObjectType, ClassName
    SNAKE_CASE = "snake_case"          # property_name, field_name
    KEBAB_CASE = "kebab-case"          # branch-name, file-name
    UPPER_SNAKE_CASE = "UPPER_SNAKE_CASE"  # CONSTANT_NAME
    LOWER_CASE = "lowercase"           # id, key
    UPPER_CASE = "UPPERCASE"           # TYPE, ENUM


class EntityType(str, Enum):
    """검증 가능한 엔티티 타입"""
    OBJECT_TYPE = "objectType"
    PROPERTY = "property"
    LINK_TYPE = "linkType"
    ACTION_TYPE = "actionType"
    FUNCTION_TYPE = "functionType"
    INTERFACE = "interface"
    BRANCH = "branch"
    SHARED_PROPERTY = "sharedProperty"
    DATA_TYPE = "dataType"
    METRIC_TYPE = "metricType"


class NamingRule(BaseModel):
    """명명 규칙 정의"""
    entity_type: EntityType
    pattern: NamingPattern
    required_prefix: Optional[List[str]] = Field(default_factory=list)
    required_suffix: Optional[List[str]] = Field(default_factory=list)
    forbidden_prefix: Optional[List[str]] = Field(default_factory=list)
    forbidden_suffix: Optional[List[str]] = Field(default_factory=list)
    forbidden_words: Optional[List[str]] = Field(default_factory=list)
    min_length: int = Field(1, ge=1)
    max_length: int = Field(255, le=255)
    allow_numbers: bool = True
    allow_underscores: bool = True
    custom_regex: Optional[str] = None
    description: Optional[str] = None
    
    @field_validator('custom_regex')
    def validate_regex(cls, v):
        if v:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")
        return v
    
    class Config:
        json_encoders = {
            Enum: enum_encoder,
            datetime: utc_datetime_encoder
        }


class NamingConvention(BaseModel):
    """조직/프로젝트별 명명 규칙 세트"""
    id: str
    name: str
    description: Optional[str] = None
    rules: Dict[EntityType, NamingRule]
    reserved_words: List[str] = Field(default_factory=list)
    case_sensitive: bool = True
    auto_fix_enabled: bool = True
    created_at: str
    updated_at: str
    created_by: str
    
    class Config:
        json_encoders = {
            Enum: enum_encoder,
            datetime: utc_datetime_encoder
        }
        json_schema_extra = {
            "example": {
                "id": "default_convention",
                "name": "Default Naming Convention",
                "rules": {
                    "objectType": {
                        "entity_type": "objectType",
                        "pattern": "PascalCase",
                        "required_suffix": ["Type"],
                        "forbidden_prefix": ["_", "temp"],
                        "min_length": 3,
                        "max_length": 50
                    }
                }
            }
        }


class ValidationIssue(BaseModel):
    """명명 규칙 위반 사항"""
    entity_type: EntityType
    entity_name: str
    rule_violated: str
    severity: str = "warning"  # warning, error
    message: str
    suggestion: Optional[str] = None
    auto_fixable: bool = False


class NamingValidationResult(BaseModel):
    """명명 규칙 검증 결과"""
    is_valid: bool
    issues: List[ValidationIssue] = Field(default_factory=list)
    suggestions: Dict[str, str] = Field(default_factory=dict)
    applied_convention: str


class NamingConventionEngine:
    """명명 규칙 검증 엔진"""
    
    # 일반적인 기술 약어 사전 (대소문자 보존)
    KNOWN_ACRONYMS = {
        # 프로토콜/통신
        'HTTP', 'HTTPS', 'FTP', 'SSH', 'TCP', 'UDP', 'IP', 'DNS', 'URL', 'URI',
        'REST', 'SOAP', 'RPC', 'GRPC', 'API', 'SDK', 'CDN', 'VPN',
        
        # 데이터 형식
        'JSON', 'XML', 'HTML', 'CSS', 'CSV', 'PDF', 'PNG', 'JPEG', 'GIF',
        'YAML', 'TOML', 'SQL', 'JWT', 'UUID', 'GUID', 'MD5', 'SHA',
        
        # 프로그래밍
        'IO', 'UI', 'UX', 'DB', 'ORM', 'MVC', 'MVP', 'MVVM', 'DOM', 'CLI',
        'GUI', 'IDE', 'CPU', 'GPU', 'RAM', 'ROM', 'SSD', 'HDD', 'OS',
        
        # 클라우드/서비스
        'AWS', 'GCP', 'S3', 'EC2', 'RDS', 'ECS', 'EKS', 'SQS', 'SNS',
        'K8S', 'CI', 'CD', 'ML', 'AI', 'NLP', 'OCR', 'ETL', 'ELT',
        
        # 비즈니스
        'B2B', 'B2C', 'SaaS', 'PaaS', 'IaaS', 'CRM', 'ERP', 'KPI', 'ROI',
        'CEO', 'CTO', 'CFO', 'HR', 'IT', 'QA', 'BA', 'PM', 'PO',
        
        # 버전/인증
        'OAuth', 'OAuth2', 'SAML', 'LDAP', 'SSO', 'MFA', '2FA',
        
        # 기타
        'ID', 'PK', 'FK', 'ACL', 'RBAC', 'CRUD', 'DTO', 'DAO', 'POC',
        'MVP', 'SKU', 'PII', 'GDPR', 'HIPAA', 'SOC', 'ISO',
    }
    
    # 패턴별 정규식 (클래스 레벨 상수로 한 번만 컴파일, ^$ 명시적 포함)
    PATTERN_REGEXES = {
        NamingPattern.CAMEL_CASE: re.compile(r'^[a-z][a-zA-Z0-9]*$'),
        NamingPattern.PASCAL_CASE: re.compile(r'^[A-Z][a-zA-Z0-9]*$'),
        NamingPattern.SNAKE_CASE: re.compile(r'^[a-z][a-z0-9_]*$'),
        NamingPattern.KEBAB_CASE: re.compile(r'^[a-z][a-z0-9\-]*$'),
        NamingPattern.UPPER_SNAKE_CASE: re.compile(r'^[A-Z][A-Z0-9_]*$'),
        NamingPattern.LOWER_CASE: re.compile(r'^[a-z][a-z0-9]*$'),
        NamingPattern.UPPER_CASE: re.compile(r'^[A-Z][A-Z0-9]*$')
    }
    
    # 단어 분리용 정규식 (숫자, 대문자 약어 처리)
    # 패턴: 연속 대문자 | 대문자+소문자 | 소문자 | 숫자
    WORD_SPLIT_REGEX = re.compile(
        r'[A-Z]+(?=[A-Z][a-z]|\b)|'         # 연속 대문자 (HTTP, XML)
        r'[A-Z][a-z]+|'                     # 대문자로 시작하는 단어 (Server)
        r'[a-z]+|'                          # 소문자 단어 (get)
        r'[0-9]+'                           # 숫자 (2, 123)
    )
    
    # 기본 명명 규칙 (Foundry 스타일)
    DEFAULT_RULES = {
        EntityType.OBJECT_TYPE: NamingRule(
            entity_type=EntityType.OBJECT_TYPE,
            pattern=NamingPattern.PASCAL_CASE,
            forbidden_prefix=["_", "temp", "test"],
            min_length=3,
            max_length=50,
            allow_underscores=False
        ),
        EntityType.PROPERTY: NamingRule(
            entity_type=EntityType.PROPERTY,
            pattern=NamingPattern.CAMEL_CASE,
            forbidden_prefix=["_", "$"],
            min_length=2,
            max_length=50
        ),
        EntityType.LINK_TYPE: NamingRule(
            entity_type=EntityType.LINK_TYPE,
            pattern=NamingPattern.CAMEL_CASE,
            required_suffix=["Link", "Relation", "Ref"],
            min_length=5,
            max_length=60
        ),
        EntityType.ACTION_TYPE: NamingRule(
            entity_type=EntityType.ACTION_TYPE,
            pattern=NamingPattern.CAMEL_CASE,
            required_prefix=["create", "update", "delete", "get", "list", "execute"],
            min_length=5,
            max_length=80
        ),
        EntityType.FUNCTION_TYPE: NamingRule(
            entity_type=EntityType.FUNCTION_TYPE,
            pattern=NamingPattern.CAMEL_CASE,
            min_length=3,
            max_length=60
        ),
        EntityType.INTERFACE: NamingRule(
            entity_type=EntityType.INTERFACE,
            pattern=NamingPattern.PASCAL_CASE,
            required_prefix=["I"],
            min_length=3,
            max_length=50
        ),
        EntityType.BRANCH: NamingRule(
            entity_type=EntityType.BRANCH,
            pattern=NamingPattern.KEBAB_CASE,
            custom_regex=r'^[a-z][a-z0-9\-/]*$',
            forbidden_words=["master"],  # Git 모범 사례
            min_length=3,
            max_length=100
        )
    }
    
    # 예약어 (프로그래밍 언어 키워드)
    DEFAULT_RESERVED_WORDS = {
        "class", "function", "if", "else", "for", "while", "return",
        "true", "false", "null", "undefined", "void", "var", "let", "const",
        "public", "private", "protected", "static", "abstract", "interface",
        "extends", "implements", "import", "export", "default", "new",
        "this", "super", "self", "id", "type", "name", "value"
    }
    
    def __init__(self, convention: Optional[NamingConvention] = None):
        """명명 규칙 엔진 초기화"""
        if convention:
            self.convention = convention
        else:
            # 기본 규칙 사용
            self.convention = NamingConvention(
                id="default",
                name="Default Convention",
                rules=self.DEFAULT_RULES,
                reserved_words=list(self.DEFAULT_RESERVED_WORDS),
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                created_by="system"
            )
        
        # 패턴 검증기 컴파일
        self._compile_patterns()
    
    def normalize(self, name: str) -> str:
        """
        이름을 정규화 - case_sensitive 옵션에 따라 처리
        
        Args:
            name: 정규화할 이름
            
        Returns:
            정규화된 이름
        """
        if not self.convention.case_sensitive:
            return name.lower()
        return name
    
    def validate(
        self,
        entity_type: EntityType,
        entity_name: str
    ) -> NamingValidationResult:
        """엔티티 이름 검증"""
        issues = []
        
        # 규칙 조회
        rule = self.convention.rules.get(entity_type)
        if not rule:
            return NamingValidationResult(
                is_valid=True,
                applied_convention=self.convention.id
            )
        
        # 1. 길이 검증
        if len(entity_name) < rule.min_length:
            issues.append(ValidationIssue(
                entity_type=entity_type,
                entity_name=entity_name,
                rule_violated="min_length",
                severity="error",
                message=f"Name too short. Minimum {rule.min_length} characters required."
            ))
        
        if len(entity_name) > rule.max_length:
            issues.append(ValidationIssue(
                entity_type=entity_type,
                entity_name=entity_name,
                rule_violated="max_length",
                severity="error",
                message=f"Name too long. Maximum {rule.max_length} characters allowed."
            ))
        
        # 2. 패턴 검증
        if not self._matches_pattern(entity_name, rule.pattern):
            issues.append(ValidationIssue(
                entity_type=entity_type,
                entity_name=entity_name,
                rule_violated="pattern",
                severity="error",
                message=f"Name must follow {rule.pattern.value} pattern.",
                suggestion=self._convert_to_pattern(entity_name, rule.pattern),
                auto_fixable=True
            ))
        
        # 3. 접두사/접미사 검증
        prefix_issue = self._check_affixes(
            entity_name, rule.required_prefix, rule.forbidden_prefix, "prefix"
        )
        if prefix_issue:
            issues.append(ValidationIssue(
                entity_type=entity_type,
                entity_name=entity_name,
                rule_violated=f"{prefix_issue[0]}_prefix",
                severity="error",
                message=prefix_issue[1],
                suggestion=prefix_issue[2],
                auto_fixable=bool(prefix_issue[2])
            ))
        
        suffix_issue = self._check_affixes(
            entity_name, rule.required_suffix, rule.forbidden_suffix, "suffix"
        )
        if suffix_issue:
            issues.append(ValidationIssue(
                entity_type=entity_type,
                entity_name=entity_name,
                rule_violated=f"{suffix_issue[0]}_suffix",
                severity="error",
                message=suffix_issue[1],
                suggestion=suffix_issue[2],
                auto_fixable=bool(suffix_issue[2])
            ))
        
        # 4. 금지어 검증
        forbidden_found = []
        name_lower = entity_name.lower()
        for word in (rule.forbidden_words or []):
            if word.lower() in name_lower:
                forbidden_found.append(word)
        
        if forbidden_found:
            issues.append(ValidationIssue(
                entity_type=entity_type,
                entity_name=entity_name,
                rule_violated="forbidden_words",
                severity="error",
                message=f"Name contains forbidden words: {', '.join(forbidden_found)}"
            ))
        
        # 5. 예약어 검증
        if self._is_reserved_word(entity_name):
            issues.append(ValidationIssue(
                entity_type=entity_type,
                entity_name=entity_name,
                rule_violated="reserved_word",
                severity="error",
                message=f"'{entity_name}' is a reserved word.",
                suggestion=f"{entity_name}_"
            ))
        
        # 6. 커스텀 정규식 검증
        if rule.custom_regex:
            # 컴파일된 패턴 사용 (fullmatch로 전체 문자열 검증)
            compiled_pattern = self._compiled_patterns.get(entity_type)
            if compiled_pattern and not compiled_pattern.fullmatch(entity_name):
                issues.append(ValidationIssue(
                    entity_type=entity_type,
                    entity_name=entity_name,
                    rule_violated="custom_regex",
                    severity="error",
                    message=f"Name does not match required pattern: {rule.custom_regex}"
                ))
        
        # 7. 숫자/언더스코어 검증
        if not rule.allow_numbers and any(c.isdigit() for c in entity_name):
            issues.append(ValidationIssue(
                entity_type=entity_type,
                entity_name=entity_name,
                rule_violated="no_numbers",
                severity="error",  # CI/CD 차단을 위해 error로 변경
                message="Numbers are not allowed in names.",
                suggestion=self._remove_numbers(entity_name),
                auto_fixable=True
            ))
        
        if not rule.allow_underscores and '_' in entity_name:
            issues.append(ValidationIssue(
                entity_type=entity_type,
                entity_name=entity_name,
                rule_violated="no_underscores",
                severity="error",  # CI/CD 차단을 위해 error로 변경
                message="Underscores are not allowed in names.",
                suggestion=entity_name.replace('_', ''),
                auto_fixable=True
            ))
        
        # 제안사항 생성
        suggestions = {}
        if issues and self.convention.auto_fix_enabled:
            fixed_name = self.auto_fix(entity_type, entity_name)
            if fixed_name != entity_name:
                suggestions[entity_name] = fixed_name
        
        return NamingValidationResult(
            is_valid=len(issues) == 0,
            issues=issues,
            suggestions=suggestions,
            applied_convention=self.convention.id
        )
    
    def auto_fix(self, entity_type: EntityType, entity_name: str) -> str:
        """자동 교정 시도"""
        rule = self.convention.rules.get(entity_type)
        if not rule:
            return entity_name
        
        # 1. 단어 분리
        words = self._split_words(entity_name)
        if not words:
            return entity_name
        
        # 2. 필수 접두사 처리 (단어 리스트에 추가)
        if rule.required_prefix:
            # 이미 있는 접두사 확인
            has_prefix = any(
                words[0].lower() == p.lower() for p in rule.required_prefix
            ) if words else False
            
            if not has_prefix:
                # 접두사를 단어로 분리하여 추가
                prefix_words = self._split_words(rule.required_prefix[0])
                words = prefix_words + words
        
        # 3. 필수 접미사 처리 (단어 리스트에 추가)
        if rule.required_suffix:
            # 이미 있는 접미사 확인
            has_suffix = any(
                words[-1].lower() == s.lower() for s in rule.required_suffix
            ) if words else False
            
            if not has_suffix:
                # 접미사를 단어로 분리하여 추가
                suffix_words = self._split_words(rule.required_suffix[0])
                words.extend(suffix_words)
        
        # 4. 예약어 처리 (전체 이름 검사)
        temp_name = self._convert_to_pattern(''.join(words), rule.pattern)
        if self._is_reserved_word(temp_name):
            # 마지막 단어에 _ 추가
            words[-1] = words[-1] + '_'
        
        # 5. 패턴 변환 (수정된 단어 리스트로)
        fixed_name = self._convert_words_to_pattern(words, rule.pattern)
        
        # 6. 길이 조정
        if len(fixed_name) > rule.max_length:
            # 접미사는 보존하고 중간 부분 자르기
            if rule.required_suffix and words:
                # 접미사 제외한 부분을 자름
                suffix_len = len(rule.required_suffix[0])
                if len(fixed_name) - suffix_len > 0:
                    fixed_name = fixed_name[:rule.max_length - suffix_len] + \
                                 fixed_name[-suffix_len:]
                else:
                    fixed_name = fixed_name[:rule.max_length]
            else:
                fixed_name = fixed_name[:rule.max_length]
        
        return fixed_name
    
    def _convert_words_to_pattern(self, words: List[str], pattern: NamingPattern) -> str:
        """단어 리스트를 특정 패턴으로 변환"""
        if not words:
            return ""
        
        if pattern == NamingPattern.CAMEL_CASE:
            # 첫 단어는 전체 소문자, 나머지는 적절히 처리
            result = words[0].lower()
            for word in words[1:]:
                if word.upper() in self.KNOWN_ACRONYMS:
                    # 알려진 약어는 첫 글자만 대문자로 (HTTP -> Http)
                    result += word[0].upper() + word[1:].lower()
                elif word.isupper() and len(word) > 1 and word not in self.KNOWN_ACRONYMS:
                    # 알려지지 않은 대문자 연속은 변환
                    result += word[0].upper() + word[1:].lower()
                else:
                    result += word.capitalize()
            return result
        elif pattern == NamingPattern.PASCAL_CASE:
            # 모든 단어 첫 글자 대문자
            result = ""
            for word in words:
                if word.upper() in self.KNOWN_ACRONYMS:
                    # 알려진 약어는 대문자로 유지 (HTTP, XML, API)
                    result += word.upper()
                elif any(c.isdigit() for c in word):
                    # 숫자가 포함된 경우 그대로
                    result += word
                else:
                    result += word.capitalize()
            return result
        elif pattern == NamingPattern.SNAKE_CASE:
            return '_'.join(w.lower() for w in words)
        elif pattern == NamingPattern.KEBAB_CASE:
            return '-'.join(w.lower() for w in words)
        elif pattern == NamingPattern.UPPER_SNAKE_CASE:
            return '_'.join(w.upper() for w in words)
        elif pattern == NamingPattern.LOWER_CASE:
            return ''.join(w.lower() for w in words)
        elif pattern == NamingPattern.UPPER_CASE:
            return ''.join(w.upper() for w in words)
        
        return ''.join(words)
    
    def _matches_pattern(self, name: str, pattern: NamingPattern) -> bool:
        """패턴 매칭 검증"""
        # 미리 컴파일된 정규식 사용 (fullmatch로 전체 문자열 검증)
        compiled_regex = self.PATTERN_REGEXES.get(pattern)
        if not compiled_regex:
            return True
        
        return bool(compiled_regex.fullmatch(name))
    
    def _convert_to_pattern(self, name: str, pattern: NamingPattern) -> str:
        """패턴 변환"""
        # 단어 분리
        words = self._split_words(name)
        if not words:
            return name
        
        # 단어 리스트를 패턴으로 변환
        return self._convert_words_to_pattern(words, pattern)
    
    def _split_words(self, name: str) -> List[str]:
        """이름을 단어로 분리"""
        # snake_case / kebab-case 먼저 처리
        if '_' in name:
            # snake_case 각 부분을 다시 분석
            parts = name.split('_')
            words = []
            for part in parts:
                if part:  # 빈 문자열 제외
                    words.extend(self._split_camel_case(part))
            return words
        
        if '-' in name:
            # kebab-case 각 부분을 다시 분석
            parts = name.split('-')
            words = []
            for part in parts:
                if part:  # 빈 문자열 제외
                    words.extend(self._split_camel_case(part))
            return words
        
        # camelCase/PascalCase 분리
        return self._split_camel_case(name)
    
    def _split_camel_case(self, name: str) -> List[str]:
        """CamelCase/PascalCase 분리 - 정규식 기반 단순 구현"""
        if not name:
            return []
        
        # 정규식을 사용한 간단한 단어 분리
        # 패턴: 연속 대문자 | 대문자+소문자 | 소문자 | 숫자
        words = re.findall(self.WORD_SPLIT_REGEX, name)
        
        # 빈 문자열 제거
        words = [w for w in words if w]
        
        # 특별한 패턴 후처리
        processed_words = []
        i = 0
        while i < len(words):
            word = words[i]
            
            # 알려진 약어인지 확인
            if word.upper() in self.KNOWN_ACRONYMS:
                # 다음에 숫자가 있으면 합치기 (OAuth + 2 -> OAuth2)
                if i + 1 < len(words) and words[i + 1].isdigit():
                    processed_words.append(word + words[i + 1])
                    i += 2
                else:
                    processed_words.append(word)
                    i += 1
            # v + 숫자 패턴 (v3, v2 등)
            elif (word.lower() == 'v' and 
                  i + 1 < len(words) and 
                  words[i + 1].isdigit()):
                processed_words.append(word + words[i + 1])
                i += 2
            else:
                processed_words.append(word)
                i += 1
        
        return processed_words if processed_words else [name]
    
    
    def _remove_numbers(self, name: str) -> str:
        """이름에서 숫자 제거"""
        # 단순히 숫자만 제거하면 의미가 깨질 수 있으므로
        # 단어 분리 후 숫자가 포함된 단어 제거
        words = self._split_words(name)
        filtered_words = [w for w in words if not w.isdigit()]
        
        if not filtered_words:
            # 모든 단어가 숫자면 원본 반환
            return name
        
        # 현재 엔티티의 패턴 유추
        if name[0].isupper():
            # PascalCase로 가정
            return ''.join(w.capitalize() for w in filtered_words)
        else:
            # camelCase로 가정
            return filtered_words[0].lower() + ''.join(w.capitalize() for w in filtered_words[1:])
    
    def _check_affixes(
        self,
        name: str,
        required: Optional[List[str]],
        forbidden: Optional[List[str]],
        affix_type: str
    ) -> Optional[Tuple[str, str, Optional[str]]]:
        """접두사/접미사 검증"""
        check_func = name.startswith if affix_type == "prefix" else name.endswith
        
        # 필수 검증
        if required:
            has_required = any(check_func(a) for a in required)
            if not has_required:
                suggestion = None
                if affix_type == "prefix":
                    suggestion = required[0] + name
                else:
                    suggestion = name + required[0]
                
                return (
                    "missing_required",
                    f"Name must {affix_type} with one of: {', '.join(required)}",
                    suggestion
                )
        
        # 금지 검증
        if forbidden:
            for f in forbidden:
                if check_func(f):
                    suggestion = None
                    if affix_type == "prefix":
                        suggestion = name[len(f):]
                    else:
                        suggestion = name[:-len(f)]
                    
                    return (
                        "forbidden",
                        f"Name cannot {affix_type} with: {f}",
                        suggestion
                    )
        
        return None
    
    def _compile_patterns(self):
        """정규식 패턴 컴파일 (성능 최적화)"""
        self._compiled_patterns = {}
        for entity_type, rule in self.convention.rules.items():
            if rule.custom_regex:
                try:
                    # 정규식에 ^, $가 없으면 자동 추가하여 전체 매칭 보장
                    regex = rule.custom_regex
                    if not regex.startswith('^'):
                        regex = '^' + regex
                    if not regex.endswith('$'):
                        regex = regex + '$'
                    self._compiled_patterns[entity_type] = re.compile(regex)
                except re.error:
                    logger.error(f"Failed to compile regex for {entity_type}: {rule.custom_regex}")
    
    def _is_reserved_word(self, word: str) -> bool:
        """예약어 확인 (case_sensitive 옵션 고려)"""
        if self.convention.case_sensitive:
            # 대소문자 구분
            return word in self.convention.reserved_words
        else:
            # 대소문자 무시
            word_lower = word.lower()
            return any(
                word_lower == reserved.lower() 
                for reserved in self.convention.reserved_words
            )


# 싱글톤 인스턴스
_default_engine = None

def get_naming_engine(convention: Optional[NamingConvention] = None) -> NamingConventionEngine:
    """명명 규칙 엔진 인스턴스 반환"""
    global _default_engine
    if convention:
        return NamingConventionEngine(convention)
    if not _default_engine:
        _default_engine = NamingConventionEngine()
    return _default_engine