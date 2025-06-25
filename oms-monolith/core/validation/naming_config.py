"""
Naming Convention Configuration Service
조직별 명명 규칙 설정 관리
"""
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path
from enum import Enum

try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

from core.validation.naming_convention import (
    EntityType, NamingConvention, NamingPattern, NamingRule
)
from core.validation.naming_history import get_naming_history_service
from core.validation.schema_validator import (
    get_schema_validator, validate_external_naming_convention, SchemaValidationError
)
from core.validation.version_manager import (
    get_version_manager, add_file_version, check_file_compatibility, 
    migrate_file_if_needed, VersionCompatibility
)
from utils.logger import get_logger

logger = get_logger(__name__)


def create_utc_timestamp() -> str:
    """UTC 시간대가 포함된 현재 시간 반환"""
    return datetime.now(timezone.utc).isoformat()


def parse_enum_with_backward_compatibility(value: str, enum_cls: type) -> Any:
    """
    백워드 호환성을 지원하는 Enum 파싱
    
    기존 'EntityType.OBJECT_TYPE' 형식과 새로운 'objectType' 형식 모두 지원
    
    Args:
        value: 파싱할 문자열
        enum_cls: Enum 클래스
        
    Returns:
        Enum 인스턴스
    """
    if '.' in value:
        # 구 형식: "EntityType.OBJECT_TYPE" → "OBJECT_TYPE"
        logger.info(f"Converting legacy enum format: {value}")
        value = value.split('.')[-1]
        
        # name으로 먼저 시도
        try:
            return enum_cls[value]
        except KeyError:
            pass
    
    # 새로운 safe_enum_parse 사용
    return safe_enum_parse(enum_cls, value)


def json_serializer(obj: Any) -> Any:
    """
    커스텀 JSON 직렬화 함수
    
    Enum과 기타 객체들을 명시적으로 처리하여 일관된 직렬화 보장
    
    Args:
        obj: 직렬화할 객체
        
    Returns:
        직렬화 가능한 값
        
    Raises:
        TypeError: 직렬화할 수 없는 타입인 경우
    """
    if isinstance(obj, Enum):
        # Enum은 항상 .value를 사용하여 일관성 보장
        return obj.value
    elif hasattr(obj, 'isoformat'):
        # datetime 객체 - UTC 시간대 포함
        if hasattr(obj, 'tzinfo') and obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat()
    elif hasattr(obj, 'model_dump'):
        # Pydantic 모델
        return obj.model_dump()
    elif hasattr(obj, '__dict__'):
        # 일반 객체의 경우 딕셔너리로 변환
        return obj.__dict__
    else:
        # 최후의 수단으로 str() 사용
        return str(obj)


def save_json_optimized(data: Dict, file_path: Path, use_orjson: bool = True) -> None:
    """
    고성능 JSON 저장 (orjson 활용)
    
    Args:
        data: 저장할 데이터
        file_path: 저장할 파일 경로
        use_orjson: orjson 사용 여부 (기본값: True)
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    if HAS_ORJSON and use_orjson:
        # orjson 사용 - 고성능
        try:
            json_bytes = orjson.dumps(
                data,
                option=orjson.OPT_INDENT_2 | orjson.OPT_UTC_Z,  # UTC 시간을 Z 표기로
                default=json_serializer
            )
            with open(file_path, 'wb') as f:
                f.write(json_bytes)
            logger.debug(f"Saved JSON using orjson to {file_path}")
            return
        except Exception as e:
            logger.warning(f"orjson failed, falling back to standard json: {e}")
    
    # 표준 json 사용 - fallback
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2, default=json_serializer)
    logger.debug(f"Saved JSON using standard json to {file_path}")


def load_json_optimized(file_path: Path, use_orjson: bool = True) -> Dict:
    """
    고성능 JSON 로드 (orjson 활용)
    
    Args:
        file_path: 로드할 파일 경로
        use_orjson: orjson 사용 여부 (기본값: True)
        
    Returns:
        로드된 데이터
    """
    if not file_path.exists():
        return {}
    
    if HAS_ORJSON and use_orjson:
        # orjson 사용 - 고성능
        try:
            with open(file_path, 'rb') as f:
                data = orjson.loads(f.read())
            logger.debug(f"Loaded JSON using orjson from {file_path}")
            return data
        except Exception as e:
            logger.warning(f"orjson failed, falling back to standard json: {e}")
    
    # 표준 json 사용 - fallback
    with open(file_path, 'r') as f:
        data = json.load(f)
    logger.debug(f"Loaded JSON using standard json from {file_path}")
    return data


def safe_enum_parse(enum_class: type, value: Any, default: Optional[Any] = None) -> Any:
    """
    안전한 Enum 파싱 함수
    
    문자열 값을 Enum으로 안전하게 변환. 실패 시 기본값 반환 또는 예외 발생
    
    Args:
        enum_class: Enum 클래스 타입
        value: 변환할 값 (문자열 또는 이미 Enum인 경우)
        default: 변환 실패 시 기본값 (None이면 예외 발생)
        
    Returns:
        Enum 인스턴스 또는 기본값
        
    Raises:
        ValueError: 변환 실패하고 default가 None인 경우
    """
    # 이미 올바른 Enum 타입인 경우
    if isinstance(value, enum_class):
        return value
    
    # None이나 빈 값 처리
    if value is None or value == "":
        if default is not None:
            return default
        raise ValueError(f"Cannot convert None/empty value to {enum_class.__name__}")
    
    # 문자열을 Enum으로 변환 시도
    if isinstance(value, str):
        # 1. 직접 value로 찾기 (권장)
        for enum_item in enum_class:
            if enum_item.value == value:
                return enum_item
        
        # 2. name으로 찾기 (호환성)
        try:
            return enum_class[value]
        except KeyError:
            pass
        
        # 3. 대소문자 무시하고 value로 찾기
        value_lower = value.lower()
        for enum_item in enum_class:
            if enum_item.value.lower() == value_lower:
                return enum_item
        
        # 4. 대소문자 무시하고 name으로 찾기
        for enum_item in enum_class:
            if enum_item.name.lower() == value_lower:
                return enum_item
    
    # 변환 실패
    if default is not None:
        logger.warning(f"Failed to convert '{value}' to {enum_class.__name__}, using default: {default}")
        return default
    
    valid_values = [item.value for item in enum_class]
    raise ValueError(f"Cannot convert '{value}' to {enum_class.__name__}. Valid values: {valid_values}")


class NamingConfigService:
    """명명 규칙 설정 관리 서비스"""
    
    def __init__(self, config_path: Optional[str] = None, history_path: Optional[str] = None):
        """
        초기화
        
        Args:
            config_path: 명명 규칙 설정 파일 경로
            history_path: 이력 저장 파일 경로
        """
        self.config_path = config_path or "/etc/oms/naming_rules.json"
        self.conventions: Dict[str, NamingConvention] = {}
        
        # history_path가 주어지면 사용, 아니면 config_path와 같은 디렉토리에 생성
        if history_path:
            self.history_service = get_naming_history_service(history_path)
        else:
            config_dir = Path(self.config_path).parent
            history_file = config_dir / "naming_history.json"
            self.history_service = get_naming_history_service(str(history_file))
        
        self._load_conventions()
    
    def _load_conventions(self):
        """설정 파일에서 명명 규칙 로드"""
        config_file = Path(self.config_path)
        
        if config_file.exists():
            try:
                # 고성능 JSON 로드 사용
                data = load_json_optimized(config_file)
                
                # 버전 호환성 확인 및 마이그레이션
                try:
                    data, migrated, migrations = migrate_file_if_needed(data)
                    if migrated:
                        logger.info(f"Applied migrations: {', '.join(migrations)}")
                        # 마이그레이션된 데이터를 파일에 다시 저장
                        save_json_optimized(data, config_file)
                except ValueError as e:
                    logger.error(f"Version compatibility error: {e}")
                    # 호환되지 않는 경우 백업 생성 후 기본값 사용
                    backup_path = config_file.with_suffix('.backup.json')
                    config_file.rename(backup_path)
                    logger.warning(f"Incompatible file backed up to {backup_path}")
                    data = {"conventions": []}
                
                for conv_data in data.get("conventions", []):
                    convention = self._parse_convention(conv_data)
                    self.conventions[convention.id] = convention
                logger.info(f"Loaded {len(self.conventions)} naming conventions")
            except Exception as e:
                logger.error(f"Failed to load naming conventions: {e}")
        
        # 기본 규칙이 없으면 생성
        if "default" not in self.conventions:
            self.conventions["default"] = self._create_default_convention()
    
    def _create_default_convention(self) -> NamingConvention:
        """Foundry 스타일 기본 명명 규칙 생성"""
        return NamingConvention(
            id="default",
            name="Foundry Default Naming Convention",
            description="Default naming rules based on Palantir Foundry best practices",
            rules={
                EntityType.OBJECT_TYPE: NamingRule(
                    entity_type=EntityType.OBJECT_TYPE,
                    pattern=NamingPattern.PASCAL_CASE,
                    forbidden_prefix=["_", "temp", "test", "tmp"],
                    forbidden_suffix=["_temp", "_test", "_tmp"],
                    min_length=3,
                    max_length=50,
                    allow_underscores=False,
                    description="Object types should be PascalCase nouns"
                ),
                EntityType.PROPERTY: NamingRule(
                    entity_type=EntityType.PROPERTY,
                    pattern=NamingPattern.CAMEL_CASE,
                    forbidden_prefix=["_", "$", "@"],
                    min_length=2,
                    max_length=50,
                    allow_numbers=True,
                    description="Properties should be camelCase"
                ),
                EntityType.LINK_TYPE: NamingRule(
                    entity_type=EntityType.LINK_TYPE,
                    pattern=NamingPattern.CAMEL_CASE,
                    required_suffix=["Link", "Relation", "Reference", "Association"],
                    min_length=5,
                    max_length=60,
                    description="Link types should describe the relationship"
                ),
                EntityType.ACTION_TYPE: NamingRule(
                    entity_type=EntityType.ACTION_TYPE,
                    pattern=NamingPattern.CAMEL_CASE,
                    required_prefix=["create", "update", "delete", "get", "list", "execute", "process", "validate"],
                    min_length=5,
                    max_length=80,
                    description="Actions should start with a verb"
                ),
                EntityType.FUNCTION_TYPE: NamingRule(
                    entity_type=EntityType.FUNCTION_TYPE,
                    pattern=NamingPattern.CAMEL_CASE,
                    forbidden_prefix=["_", "temp"],
                    min_length=3,
                    max_length=60,
                    description="Functions should be descriptive camelCase"
                ),
                EntityType.INTERFACE: NamingRule(
                    entity_type=EntityType.INTERFACE,
                    pattern=NamingPattern.PASCAL_CASE,
                    required_prefix=["I"],
                    forbidden_suffix=["Interface", "Contract"],
                    min_length=3,
                    max_length=50,
                    description="Interfaces should start with 'I'"
                ),
                EntityType.BRANCH: NamingRule(
                    entity_type=EntityType.BRANCH,
                    pattern=NamingPattern.KEBAB_CASE,
                    custom_regex=r'^[a-z][a-z0-9\-/]*$',
                    forbidden_words=["master"],  # Use 'main' instead
                    forbidden_prefix=["_", "-"],
                    min_length=3,
                    max_length=100,
                    description="Branches should use kebab-case"
                ),
                EntityType.SHARED_PROPERTY: NamingRule(
                    entity_type=EntityType.SHARED_PROPERTY,
                    pattern=NamingPattern.CAMEL_CASE,
                    required_prefix=["shared"],
                    min_length=8,
                    max_length=60,
                    description="Shared properties should be prefixed with 'shared'"
                ),
                EntityType.DATA_TYPE: NamingRule(
                    entity_type=EntityType.DATA_TYPE,
                    pattern=NamingPattern.PASCAL_CASE,
                    forbidden_suffix=["Type", "DataType"],
                    min_length=3,
                    max_length=40,
                    description="Data types should be PascalCase"
                ),
                EntityType.METRIC_TYPE: NamingRule(
                    entity_type=EntityType.METRIC_TYPE,
                    pattern=NamingPattern.CAMEL_CASE,
                    required_suffix=["Metric", "Counter", "Gauge", "Histogram"],
                    min_length=5,
                    max_length=60,
                    description="Metrics should have descriptive suffixes"
                )
            },
            reserved_words=[
                # JavaScript/TypeScript keywords
                "abstract", "arguments", "await", "boolean", "break", "byte", "case",
                "catch", "char", "class", "const", "continue", "debugger", "default",
                "delete", "do", "double", "else", "enum", "eval", "export", "extends",
                "false", "final", "finally", "float", "for", "function", "goto", "if",
                "implements", "import", "in", "instanceof", "int", "interface", "let",
                "long", "native", "new", "null", "package", "private", "protected",
                "public", "return", "short", "static", "super", "switch", "synchronized",
                "this", "throw", "throws", "transient", "true", "try", "typeof", "var",
                "void", "volatile", "while", "with", "yield",
                
                # Python keywords
                "and", "as", "assert", "async", "await", "class", "def", "del",
                "elif", "except", "exec", "from", "global", "import", "is", "lambda",
                "nonlocal", "not", "or", "pass", "print", "raise", "with",
                
                # Common system fields
                "id", "uuid", "rid", "_id", "type", "_type", "__type__",
                
                # SQL keywords
                "select", "from", "where", "join", "union", "insert", "update",
                "delete", "create", "drop", "alter", "table", "index", "view"
            ],
            case_sensitive=True,
            auto_fix_enabled=True,
            created_at=create_utc_timestamp(),
            updated_at=create_utc_timestamp(),
            created_by="system"
        )
    
    def get_convention(self, convention_id: str) -> Optional[NamingConvention]:
        """명명 규칙 조회"""
        return self.conventions.get(convention_id)
    
    def create_convention(
        self,
        convention: NamingConvention,
        user_id: str,
        reason: Optional[str] = None
    ) -> NamingConvention:
        """새 명명 규칙 생성"""
        if convention.id in self.conventions:
            raise ValueError(f"Convention '{convention.id}' already exists")
        
        convention.created_by = user_id
        convention.created_at = create_utc_timestamp()
        convention.updated_at = convention.created_at
        
        self.conventions[convention.id] = convention
        self._save_conventions()
        
        # 이력 기록
        self.history_service.record_creation(convention, user_id, reason)
        
        logger.info(f"Created naming convention: {convention.id}")
        return convention
    
    def update_convention(
        self,
        convention_id: str,
        updates: Dict,
        user_id: str,
        reason: Optional[str] = None
    ) -> NamingConvention:
        """명명 규칙 업데이트"""
        convention = self.conventions.get(convention_id)
        if not convention:
            raise ValueError(f"Convention '{convention_id}' not found")
        
        # 기본 규칙은 수정 불가
        if convention_id == "default":
            raise ValueError("Default convention cannot be modified")
        
        # 업데이트 전 상태 보존
        old_convention = self._parse_convention(convention.model_dump())
        
        # 업데이트 적용
        for key, value in updates.items():
            if hasattr(convention, key) and key not in ["id", "created_at", "created_by"]:
                setattr(convention, key, value)
        
        convention.updated_at = create_utc_timestamp()
        self._save_conventions()
        
        # 이력 기록
        self.history_service.record_update(old_convention, convention, user_id, reason)
        
        logger.info(f"Updated naming convention: {convention_id}")
        return convention
    
    def delete_convention(
        self, 
        convention_id: str,
        user_id: str,
        reason: Optional[str] = None
    ) -> None:
        """명명 규칙 삭제"""
        if convention_id == "default":
            raise ValueError("Default convention cannot be deleted")
        
        if convention_id in self.conventions:
            # 삭제 전 상태 보존
            convention = self.conventions[convention_id]
            
            # 이력 기록
            self.history_service.record_deletion(convention, user_id, reason)
            
            del self.conventions[convention_id]
            self._save_conventions()
            logger.info(f"Deleted naming convention: {convention_id}")
        else:
            raise ValueError(f"Convention '{convention_id}' not found")
    
    def list_conventions(self) -> List[NamingConvention]:
        """모든 명명 규칙 목록"""
        return list(self.conventions.values())
    
    def export_convention(self, convention_id: str) -> Dict:
        """명명 규칙을 JSON으로 내보내기"""
        convention = self.conventions.get(convention_id)
        if not convention:
            raise ValueError(f"Convention '{convention_id}' not found")
        
        return convention.model_dump()
    
    def import_convention(self, data: Dict, user_id: str, reason: Optional[str] = None, validate_schema: bool = True) -> NamingConvention:
        """
        JSON에서 명명 규칙 가져오기
        
        Args:
            data: 가져올 딕셔너리 데이터
            user_id: 가져오는 사용자 ID
            reason: 가져오기 이유
            validate_schema: 스키마 검증 수행 여부
            
        Returns:
            생성된 NamingConvention 인스턴스
            
        Raises:
            SchemaValidationError: 스키마 검증 실패 시
            ValueError: 기타 검증 실패 시
        """
        # 스키마 검증 (옵션)
        if validate_schema:
            try:
                validated_data = validate_external_naming_convention(data)
                logger.info("External naming convention passed schema validation")
                data = validated_data
            except SchemaValidationError as e:
                logger.error(f"Schema validation failed for imported convention: {e}")
                raise ValueError(f"Import failed due to schema validation errors: {e}")
        
        convention = self._parse_convention(data)
        
        # ID 중복 체크
        if convention.id in self.conventions:
            # 새 ID 생성
            base_id = convention.id
            counter = 1
            while f"{base_id}_{counter}" in self.conventions:
                counter += 1
            convention.id = f"{base_id}_{counter}"
        
        return self.create_convention(convention, user_id, reason or f"Imported from {data.get('name', 'external source')}")
    
    def validate_convention_data(self, data: Dict) -> Dict:
        """
        명명 규칙 데이터 검증
        
        Args:
            data: 검증할 딕셔너리 데이터
            
        Returns:
            검증된 딕셔너리 데이터
            
        Raises:
            SchemaValidationError: 스키마 검증 실패 시
        """
        return validate_external_naming_convention(data)
    
    def export_schema(self, schema_type: str = "naming_convention", file_path: Optional[str] = None) -> str:
        """
        JSON 스키마 내보내기
        
        Args:
            schema_type: 스키마 타입 ("naming_convention" 또는 "naming_rule")
            file_path: 저장할 파일 경로 (None이면 JSON 문자열만 반환)
            
        Returns:
            JSON 스키마 문자열
        """
        validator = get_schema_validator()
        return validator.export_schema(schema_type, file_path)
    
    def check_file_version(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        파일 버전 정보 확인
        
        Args:
            file_path: 확인할 파일 경로 (None이면 현재 설정 파일)
            
        Returns:
            버전 정보 딕셔너리
        """
        path = file_path or self.config_path
        file = Path(path)
        
        if not file.exists():
            return {"error": "File not found", "path": str(path)}
        
        try:
            data = load_json_optimized(file)
            manager = get_version_manager()
            metadata = manager.get_version_info(data)
            compatibility, message = manager.check_compatibility(data)
            
            return {
                "file_path": str(path),
                "version_info": metadata.to_dict() if metadata else None,
                "compatibility": compatibility.value,
                "compatibility_message": message,
                "is_current": manager.is_current_version(data),
                "needs_migration": compatibility == VersionCompatibility.MIGRATION_REQUIRED
            }
        except Exception as e:
            return {"error": str(e), "path": str(path)}
    
    def migrate_config_file(self, backup: bool = True) -> Dict[str, Any]:
        """
        설정 파일 마이그레이션
        
        Args:
            backup: 백업 생성 여부
            
        Returns:
            마이그레이션 결과
        """
        config_file = Path(self.config_path)
        
        if not config_file.exists():
            return {"error": "Config file not found", "path": str(config_file)}
        
        try:
            # 원본 데이터 로드
            original_data = load_json_optimized(config_file)
            
            # 백업 생성
            if backup:
                backup_path = config_file.with_suffix(f'.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
                with open(backup_path, 'w') as f:
                    json.dump(original_data, f, indent=2)
                logger.info(f"Created backup: {backup_path}")
            else:
                backup_path = None
            
            # 마이그레이션 수행
            migrated_data, migrated, migrations = migrate_file_if_needed(original_data)
            
            if migrated:
                # 마이그레이션된 데이터 저장
                save_json_optimized(migrated_data, config_file)
                logger.info(f"Migration completed: {', '.join(migrations)}")
                
                # 설정 다시 로드
                self._load_conventions()
                
                return {
                    "success": True,
                    "migrated": True,
                    "migrations_applied": migrations,
                    "backup_path": str(backup_path) if backup else None
                }
            else:
                # 마이그레이션 불필요
                return {
                    "success": True,
                    "migrated": False,
                    "message": "No migration required",
                    "backup_path": str(backup_path) if backup_path else None
                }
                
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return {"error": str(e), "success": False}
    
    def get_version_changelog(self, from_version: str = None, to_version: str = None) -> List[str]:
        """
        버전 간 변경 사항 조회
        
        Args:
            from_version: 시작 버전 (None이면 최소 지원 버전)
            to_version: 종료 버전 (None이면 현재 버전)
            
        Returns:
            변경 사항 목록
        """
        manager = get_version_manager()
        
        if not from_version:
            from_version = manager.MINIMUM_SUPPORTED_VERSION.to_string()
        if not to_version:
            to_version = manager.CURRENT_VERSION.to_string()
        
        return manager.get_changelog(from_version, to_version)
    
    def _parse_convention(self, data: Dict) -> NamingConvention:
        """
        딕셔너리에서 NamingConvention 파싱
        
        안전한 Enum 변환을 통해 역직렬화 수행
        
        Args:
            data: 파싱할 딕셔너리 데이터
            
        Returns:
            NamingConvention 인스턴스
            
        Raises:
            ValueError: 필수 필드 누락 또는 잘못된 Enum 값
        """
        rules = {}
        
        # rules 파싱 - 백워드 호환성 지원
        for entity_type_str, rule_data in data.get("rules", {}).items():
            try:
                # EntityType 백워드 호환 변환
                entity_type = parse_enum_with_backward_compatibility(entity_type_str, EntityType)
                
                # rule_data 복사본 생성 (원본 수정 방지)
                rule_data_copy = rule_data.copy()
                
                # NamingPattern 백워드 호환 변환
                if "pattern" in rule_data_copy:
                    rule_data_copy["pattern"] = parse_enum_with_backward_compatibility(
                        rule_data_copy["pattern"], NamingPattern
                    )
                
                # EntityType도 entity_type 필드에 설정
                if "entity_type" in rule_data_copy:
                    rule_data_copy["entity_type"] = parse_enum_with_backward_compatibility(
                        rule_data_copy["entity_type"], EntityType
                    )
                else:
                    rule_data_copy["entity_type"] = entity_type
                
                # NamingRule 생성
                rules[entity_type] = NamingRule(**rule_data_copy)
                
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to parse rule for entity type '{entity_type_str}': {e}")
                # 개별 규칙 파싱 실패는 건너뛰고 계속 진행
                continue
        
        # 필수 필드 검증
        if not data.get("id"):
            raise ValueError("Convention ID is required")
        if not data.get("name"):
            raise ValueError("Convention name is required")
        
        return NamingConvention(
            id=data["id"],
            name=data["name"],
            description=data.get("description"),
            rules=rules,
            reserved_words=data.get("reserved_words", []),
            case_sensitive=data.get("case_sensitive", True),
            auto_fix_enabled=data.get("auto_fix_enabled", True),
            created_at=data.get("created_at", create_utc_timestamp()),
            updated_at=data.get("updated_at", create_utc_timestamp()),
            created_by=data.get("created_by", "system")
        )
    
    def get_convention_history(
        self,
        convention_id: str,
        version: Optional[int] = None
    ) -> List[Dict]:
        """명명 규칙의 변경 이력 조회"""
        history = self.history_service.get_history(convention_id, version)
        return [h.to_dict() for h in history]
    
    def get_convention_at_version(
        self,
        convention_id: str,
        version: int
    ) -> Optional[Dict]:
        """특정 버전의 명명 규칙 조회"""
        return self.history_service.get_convention_at_version(convention_id, version)
    
    def get_convention_diff(
        self,
        convention_id: str,
        from_version: int,
        to_version: int
    ) -> List[Dict]:
        """두 버전 간의 차이점 조회"""
        diffs = self.history_service.get_diff_between_versions(
            convention_id, from_version, to_version
        )
        return [diff.to_dict() for diff in diffs]
    
    def generate_history_report(
        self,
        convention_id: str,
        from_version: Optional[int] = None,
        to_version: Optional[int] = None
    ) -> str:
        """명명 규칙 변경 이력 리포트 생성"""
        return self.history_service.generate_diff_report(
            convention_id, from_version, to_version
        )
    
    def _save_conventions(self):
        """명명 규칙을 파일에 저장"""
        try:
            config_file = Path(self.config_path)
            
            data = {
                "conventions": [
                    conv.model_dump() for conv in self.conventions.values()
                    if conv.id != "default"  # 기본 규칙은 저장하지 않음
                ]
            }
            
            # 버전 메타데이터 추가
            data = add_file_version(data, "naming_convention")
            
            # 고성능 JSON 저장 사용
            save_json_optimized(data, config_file)
                
            logger.info(f"Saved {len(data['conventions'])} conventions to {config_file}")
        except Exception as e:
            logger.error(f"Failed to save naming conventions: {e}")


# 싱글톤 인스턴스 딕셔너리 (경로별로 관리)
_config_services: Dict[str, NamingConfigService] = {}

def get_naming_config_service(config_path: Optional[str] = None, history_path: Optional[str] = None) -> NamingConfigService:
    """명명 규칙 설정 서비스 인스턴스 반환"""
    global _config_services
    path_key = config_path or "/etc/oms/naming_rules.json"
    
    if path_key not in _config_services:
        _config_services[path_key] = NamingConfigService(config_path, history_path)
    
    return _config_services[path_key]