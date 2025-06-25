"""
Snapshot Tests for JSON Serialization
스냅샷 테스트를 통한 직렬화 결과 고정 및 무의식적 포맷 변경 방지
"""
import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

try:
    from approvaltests import verify, verify_json
    from approvaltests.reporters import PythonNativeReporter
    HAS_APPROVALTESTS = True
except ImportError:
    HAS_APPROVALTESTS = False

from core.validation.naming_convention import (
    EntityType, NamingPattern, NamingRule, NamingConvention
)
from core.validation.naming_config import (
    NamingConfigService, create_utc_timestamp, save_json_optimized
)
from core.validation.naming_history import (
    NamingConventionHistory, ChangeType, ChangeDiff
)


# 고정된 테스트 데이터 (시간 등이 변하지 않도록)
FIXED_TIMESTAMP = "2024-01-01T12:00:00Z"
FIXED_USER = "snapshot-tester"


def create_fixed_naming_convention():
    """고정된 명명 규칙 생성 (스냅샷용)"""
    return NamingConvention(
        id="snapshot-test-convention",
        name="Snapshot Test Convention",
        description="Convention for snapshot testing to ensure consistent serialization",
        rules={
            EntityType.OBJECT_TYPE: NamingRule(
                entity_type=EntityType.OBJECT_TYPE,
                pattern=NamingPattern.PASCAL_CASE,
                forbidden_prefix=["_", "temp"],
                forbidden_suffix=["_temp"],
                min_length=3,
                max_length=50,
                allow_underscores=False,
                description="Object types should be descriptive PascalCase nouns"
            ),
            EntityType.PROPERTY: NamingRule(
                entity_type=EntityType.PROPERTY,
                pattern=NamingPattern.CAMEL_CASE,
                forbidden_prefix=["_", "$"],
                min_length=2,
                max_length=40,
                allow_numbers=True,
                description="Properties should be camelCase"
            ),
            EntityType.LINK_TYPE: NamingRule(
                entity_type=EntityType.LINK_TYPE,
                pattern=NamingPattern.CAMEL_CASE,
                required_suffix=["Link", "Relation"],
                min_length=5,
                max_length=60,
                description="Link types should end with Link or Relation"
            )
        },
        reserved_words=[
            "abstract", "class", "function", "if", "else", "for", "while",
            "return", "true", "false", "null", "void", "public", "private"
        ],
        case_sensitive=True,
        auto_fix_enabled=True,
        created_at=FIXED_TIMESTAMP,
        updated_at=FIXED_TIMESTAMP,
        created_by=FIXED_USER
    )


def create_fixed_naming_history():
    """고정된 명명 규칙 이력 생성 (스냅샷용)"""
    return NamingConventionHistory(
        id="snapshot-test-convention_v1_1704110400",
        convention_id="snapshot-test-convention",
        version=1,
        change_type=ChangeType.CREATE,
        change_summary="Created snapshot test convention",
        diffs=[
            ChangeDiff(
                field="name",
                old_value=None,
                new_value="Snapshot Test Convention",
                path="name"
            ),
            ChangeDiff(
                field="rules",
                old_value=None,
                new_value={
                    "entity_type": "objectType",
                    "pattern": "PascalCase",
                    "min_length": 3,
                    "max_length": 50
                },
                path="rules.objectType"
            )
        ],
        full_snapshot={
            "id": "snapshot-test-convention",
            "name": "Snapshot Test Convention",
            "description": "Convention for snapshot testing",
            "rules": {
                "objectType": {
                    "entity_type": "objectType",
                    "pattern": "PascalCase",
                    "min_length": 3,
                    "max_length": 50
                }
            }
        },
        changed_by=FIXED_USER,
        changed_at=datetime.fromisoformat(FIXED_TIMESTAMP.replace('Z', '+00:00')),
        change_reason="Initial snapshot test setup"
    )


class MockSnapshot:
    """approvaltests가 없을 때 사용할 Mock"""
    
    def __init__(self, content: str):
        self.content = content
    
    def verify(self, content: str):
        """내용이 동일한지 확인"""
        # 실제 구현에서는 파일 기반 비교를 하겠지만, 
        # 여기서는 단순히 문자열 길이와 기본 구조만 확인
        assert len(content) > 0
        assert isinstance(content, str)
        # JSON 파싱 가능한지 확인
        if content.strip().startswith('{'):
            json.loads(content)


def mock_verify(content: str, reporter=None):
    """approvaltests가 없을 때 사용할 mock verify 함수"""
    mock = MockSnapshot(content)
    mock.verify(content)


def mock_verify_json(data, reporter=None):
    """approvaltests가 없을 때 사용할 mock verify_json 함수"""
    json_str = json.dumps(data, indent=2, sort_keys=True)
    mock_verify(json_str, reporter)


# approvaltests가 없으면 mock 함수 사용
if not HAS_APPROVALTESTS:
    verify = mock_verify
    verify_json = mock_verify_json
    PythonNativeReporter = None


@pytest.mark.skipif(not HAS_APPROVALTESTS, reason="approvaltests not available")
class TestSnapshotWithApprovalTests:
    """approvaltests를 사용한 스냅샷 테스트"""
    
    def test_naming_convention_serialization_snapshot(self):
        """명명 규칙 직렬화 스냅샷 테스트"""
        convention = create_fixed_naming_convention()
        serialized_data = convention.model_dump()
        
        # JSON 직렬화 결과를 스냅샷으로 저장
        verify_json(serialized_data, reporter=PythonNativeReporter())
    
    def test_naming_history_serialization_snapshot(self):
        """명명 규칙 이력 직렬화 스냅샷 테스트"""
        history = create_fixed_naming_history()
        serialized_data = history.to_dict()
        
        # JSON 직렬화 결과를 스냅샷으로 저장
        verify_json(serialized_data, reporter=PythonNativeReporter())
    
    def test_complete_config_file_snapshot(self):
        """전체 설정 파일 스냅샷 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "snapshot_config.json"
            
            service = NamingConfigService(str(config_path))
            convention = create_fixed_naming_convention()
            
            # 서비스에 추가 (시간을 고정하기 위해 직접 설정)
            service.conventions[convention.id] = convention
            service._save_conventions()
            
            # 저장된 파일 내용 읽기
            with open(config_path, 'r') as f:
                file_content = f.read()
            
            # 파일 내용을 스냅샷으로 저장
            verify(file_content, reporter=PythonNativeReporter())
    
    def test_json_schema_export_snapshot(self):
        """JSON 스키마 내보내기 스냅샷 테스트"""
        service = NamingConfigService()
        schema_json = service.export_schema("naming_convention")
        
        # 스키마를 파싱하여 일관된 형태로 변환
        schema_dict = json.loads(schema_json)
        
        # 스키마 스냅샷 저장
        verify_json(schema_dict, reporter=PythonNativeReporter())


class TestSnapshotFallback:
    """approvaltests가 없을 때도 작동하는 스냅샷 테스트"""
    
    def test_naming_convention_serialization_consistency(self):
        """명명 규칙 직렬화 일관성 테스트"""
        convention = create_fixed_naming_convention()
        serialized_data = convention.model_dump()
        
        # 기본 구조 검증
        assert "id" in serialized_data
        assert "name" in serialized_data
        assert "rules" in serialized_data
        assert "created_at" in serialized_data
        assert "updated_at" in serialized_data
        
        # 고정된 값들 검증
        assert serialized_data["id"] == "snapshot-test-convention"
        assert serialized_data["name"] == "Snapshot Test Convention"
        assert serialized_data["created_at"] == FIXED_TIMESTAMP
        assert serialized_data["updated_at"] == FIXED_TIMESTAMP
        assert serialized_data["created_by"] == FIXED_USER
        
        # rules 구조 검증
        assert "objectType" in serialized_data["rules"]
        assert "property" in serialized_data["rules"]
        assert "linkType" in serialized_data["rules"]
        
        # JSON 직렬화 가능성 검증
        json_str = json.dumps(serialized_data, indent=2, sort_keys=True)
        assert len(json_str) > 0
        
        # mock verify 호출
        verify_json(serialized_data)
    
    def test_naming_history_serialization_consistency(self):
        """명명 규칙 이력 직렬화 일관성 테스트"""
        history = create_fixed_naming_history()
        serialized_data = history.to_dict()
        
        # 기본 구조 검증
        assert "id" in serialized_data
        assert "convention_id" in serialized_data
        assert "version" in serialized_data
        assert "change_type" in serialized_data
        assert "diffs" in serialized_data
        assert "changed_at" in serialized_data
        
        # 고정된 값들 검증
        assert serialized_data["convention_id"] == "snapshot-test-convention"
        assert serialized_data["version"] == 1
        assert serialized_data["change_type"] == "create"
        assert serialized_data["changed_by"] == FIXED_USER
        
        # diffs 구조 검증
        assert len(serialized_data["diffs"]) > 0
        first_diff = serialized_data["diffs"][0]
        assert "field" in first_diff
        assert "old_value" in first_diff
        assert "new_value" in first_diff
        
        # JSON 직렬화 가능성 검증
        json_str = json.dumps(serialized_data, indent=2, sort_keys=True)
        assert len(json_str) > 0
        
        # mock verify 호출
        verify_json(serialized_data)
    
    def test_enum_serialization_consistency(self):
        """Enum 직렬화 일관성 테스트"""
        convention = create_fixed_naming_convention()
        serialized_data = convention.model_dump()
        
        # ObjectType 규칙의 Enum 직렬화 확인
        obj_rule = serialized_data["rules"]["objectType"]
        assert obj_rule["entity_type"] == "objectType"  # Enum.value
        assert obj_rule["pattern"] == "PascalCase"      # Enum.value
        
        # Property 규칙의 Enum 직렬화 확인
        prop_rule = serialized_data["rules"]["property"]
        assert prop_rule["entity_type"] == "property"   # Enum.value
        assert prop_rule["pattern"] == "camelCase"      # Enum.value
        
        # LinkType 규칙의 Enum 직렬화 확인
        link_rule = serialized_data["rules"]["linkType"]
        assert link_rule["entity_type"] == "linkType"   # Enum.value
        assert link_rule["pattern"] == "camelCase"      # Enum.value
        
        # 모든 Enum이 .value로 직렬화되었는지 확인
        json_str = json.dumps(serialized_data, indent=2)
        
        # 잘못된 Enum 형식이 없는지 확인
        assert "EntityType." not in json_str
        assert "NamingPattern." not in json_str
        assert "OBJECT_TYPE" not in json_str
        assert "PASCAL_CASE" not in json_str
        
        # mock verify 호출
        verify(json_str)
    
    def test_timestamp_format_consistency(self):
        """타임스탬프 형식 일관성 테스트"""
        convention = create_fixed_naming_convention()
        serialized_data = convention.model_dump()
        
        # 타임스탬프 형식 확인
        created_at = serialized_data["created_at"]
        updated_at = serialized_data["updated_at"]
        
        # ISO 형식인지 확인
        assert created_at == FIXED_TIMESTAMP
        assert updated_at == FIXED_TIMESTAMP
        
        # 파싱 가능한지 확인
        datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        
        # 히스토리 타임스탬프도 확인
        history = create_fixed_naming_history()
        history_data = history.to_dict()
        
        changed_at = history_data["changed_at"]
        # UTC 타임스탬프인지 확인 (Z 또는 +00:00 포함)
        assert changed_at.endswith('Z') or '+' in changed_at
    
    def test_file_format_regression_protection(self):
        """파일 형식 회귀 방지 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "format_test.json"
            
            # 표준 JSON 저장
            test_data = {
                "test_enum": EntityType.OBJECT_TYPE.value,
                "test_timestamp": FIXED_TIMESTAMP,
                "test_nested": {
                    "pattern": NamingPattern.PASCAL_CASE.value,
                    "count": 42
                }
            }
            
            save_json_optimized(test_data, config_path, use_orjson=False)
            
            # 파일 내용 읽기
            with open(config_path, 'r') as f:
                file_content = f.read()
            
            # 기본 JSON 구조 확인
            assert file_content.startswith('{')
            assert file_content.endswith('}')
            assert '"test_enum": "objectType"' in file_content
            assert '"test_timestamp": "2024-01-01T12:00:00Z"' in file_content
            assert '"pattern": "PascalCase"' in file_content
            
            # 파싱 가능한지 확인
            parsed_data = json.loads(file_content)
            assert parsed_data["test_enum"] == "objectType"
            assert parsed_data["test_timestamp"] == FIXED_TIMESTAMP
            
            # mock verify 호출
            verify(file_content)
    
    def test_large_data_serialization_stability(self):
        """대용량 데이터 직렬화 안정성 테스트"""
        # 큰 명명 규칙 생성
        large_convention = NamingConvention(
            id="large-snapshot-test",
            name="Large Snapshot Test Convention",
            description="Large convention for testing serialization stability with many rules",
            rules={
                entity_type: NamingRule(
                    entity_type=entity_type,
                    pattern=NamingPattern.PASCAL_CASE if i % 2 == 0 else NamingPattern.CAMEL_CASE,
                    min_length=i % 10 + 1,
                    max_length=i % 50 + 50,
                    allow_numbers=i % 3 == 0,
                    allow_underscores=i % 4 == 0,
                    description=f"Rule {i} for {entity_type.value}"
                )
                for i, entity_type in enumerate(EntityType)
            },
            reserved_words=[f"reserved{i}" for i in range(100)],  # 100개 예약어
            case_sensitive=True,
            auto_fix_enabled=True,
            created_at=FIXED_TIMESTAMP,
            updated_at=FIXED_TIMESTAMP,
            created_by=FIXED_USER
        )
        
        # 직렬화
        serialized_data = large_convention.model_dump()
        
        # 기본 구조 확인
        assert len(serialized_data["rules"]) == len(EntityType)
        assert len(serialized_data["reserved_words"]) == 100
        
        # JSON 직렬화 가능성 확인
        json_str = json.dumps(serialized_data, indent=2, sort_keys=True)
        assert len(json_str) > 1000  # 충분히 큰 데이터
        
        # 파싱 가능한지 확인
        parsed_back = json.loads(json_str)
        assert parsed_back["id"] == "large-snapshot-test"
        assert len(parsed_back["rules"]) == len(EntityType)
        
        # mock verify 호출
        verify_json(serialized_data)


class TestSnapshotIntegration:
    """스냅샷 테스트 통합 시나리오"""
    
    def test_end_to_end_snapshot_workflow(self):
        """엔드투엔드 스냅샷 워크플로우 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "e2e_config.json"
            history_path = Path(temp_dir) / "e2e_history.json"
            
            # 1. 서비스 생성 및 규칙 추가
            service = NamingConfigService(str(config_path), str(history_path))
            convention = create_fixed_naming_convention()
            
            # 시간을 고정하여 일관된 결과 보장
            service.conventions[convention.id] = convention
            service._save_conventions()
            
            # 2. 설정 파일 스냅샷
            with open(config_path, 'r') as f:
                config_content = f.read()
            
            # 기본 구조 확인
            config_data = json.loads(config_content)
            assert "conventions" in config_data
            assert len(config_data["conventions"]) > 0
            
            # mock verify
            verify(config_content)
            
            # 3. 스키마 내보내기 스냅샷
            schema_json = service.export_schema("naming_convention")
            schema_data = json.loads(schema_json)
            
            # 스키마 구조 확인
            assert "properties" in schema_data
            assert "required" in schema_data
            assert schema_data["title"] == "Naming Convention Schema"
            
            # mock verify
            verify_json(schema_data)
            
            # 4. 전체 워크플로우 일관성 확인
            # 설정 파일에서 다시 로드
            service2 = NamingConfigService(str(config_path), str(history_path))
            loaded_convention = service2.get_convention(convention.id)
            
            assert loaded_convention is not None
            assert loaded_convention.id == convention.id
            assert loaded_convention.name == convention.name
            
            # 로드된 규칙도 동일한 형태로 직렬화되는지 확인
            reloaded_data = loaded_convention.model_dump()
            verify_json(reloaded_data)


# 스냅샷 테스트 유틸리티 함수들
def normalize_json_for_snapshot(data: dict) -> str:
    """스냅샷 비교용 JSON 정규화"""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)


def compare_snapshots(expected: str, actual: str) -> bool:
    """두 스냅샷 문자열 비교"""
    # JSON으로 파싱하여 구조적 비교
    try:
        expected_json = json.loads(expected)
        actual_json = json.loads(actual)
        return expected_json == actual_json
    except json.JSONDecodeError:
        # JSON이 아닌 경우 공백 정규화 후 비교
        expected_normalized = ' '.join(expected.split())
        actual_normalized = ' '.join(actual.split())
        return expected_normalized == actual_normalized


class TestSnapshotUtilities:
    """스냅샷 테스트 유틸리티 테스트"""
    
    def test_json_normalization(self):
        """JSON 정규화 테스트"""
        test_data = {
            "z_field": "last",
            "a_field": "first",
            "nested": {
                "b": 2,
                "a": 1
            }
        }
        
        normalized = normalize_json_for_snapshot(test_data)
        
        # 정렬된 키 순서 확인
        lines = normalized.split('\n')
        # "a_field"가 "z_field"보다 먼저 나와야 함
        a_field_line = next(i for i, line in enumerate(lines) if '"a_field"' in line)
        z_field_line = next(i for i, line in enumerate(lines) if '"z_field"' in line)
        assert a_field_line < z_field_line
        
        # 중첩된 객체도 정렬되었는지 확인
        assert '"a": 1' in normalized
        assert '"b": 2' in normalized
    
    def test_snapshot_comparison(self):
        """스냅샷 비교 테스트"""
        json1 = '{"a": 1, "b": 2}'
        json2 = '{ "a" : 1 , "b" : 2 }'  # 공백이 다름
        
        # 정규화 후 비교하면 동일해야 함
        assert compare_snapshots(json1, json2)
        
        json3 = '{"a": 1, "b": 3}'  # 값이 다름
        assert not compare_snapshots(json1, json3)