"""
Tests for Naming Convention History functionality
명명 규칙 이력 관리 기능 테스트
"""
import pytest
from datetime import datetime
from pathlib import Path
import tempfile
import json

from core.validation.naming_convention import (
    NamingConvention, NamingRule, NamingPattern, EntityType
)
from core.validation.naming_config import NamingConfigService
from core.validation.naming_history import (
    NamingConventionHistoryService, NamingConventionHistory,
    ChangeType, ChangeDiff
)


@pytest.fixture
def temp_paths():
    """임시 파일 경로 생성"""
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "naming_rules.json"
        history_path = Path(temp_dir) / "naming_history.json"
        yield config_path, history_path


@pytest.fixture
def config_service(temp_paths):
    """테스트용 설정 서비스"""
    config_path, history_path = temp_paths
    return NamingConfigService(str(config_path), str(history_path))


@pytest.fixture
def history_service(temp_paths):
    """테스트용 이력 서비스"""
    _, history_path = temp_paths
    return NamingConventionHistoryService(str(history_path))


@pytest.fixture
def sample_convention():
    """테스트용 명명 규칙"""
    return NamingConvention(
        id="test-convention",
        name="Test Convention",
        description="Test naming convention",
        rules={
            EntityType.OBJECT_TYPE: NamingRule(
                entity_type=EntityType.OBJECT_TYPE,
                pattern=NamingPattern.PASCAL_CASE,
                min_length=3,
                max_length=50
            ),
            EntityType.PROPERTY: NamingRule(
                entity_type=EntityType.PROPERTY,
                pattern=NamingPattern.CAMEL_CASE,
                min_length=2,
                max_length=40
            )
        },
        reserved_words=["test", "example"],
        case_sensitive=True,
        auto_fix_enabled=True,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        created_by="test-user"
    )


class TestNamingConventionHistory:
    """명명 규칙 이력 테스트"""
    
    def test_change_diff_creation(self):
        """ChangeDiff 생성 테스트"""
        diff = ChangeDiff(
            field="pattern",
            old_value=NamingPattern.CAMEL_CASE,
            new_value=NamingPattern.PASCAL_CASE,
            path="rules.ObjectType.pattern"
        )
        
        assert diff.field == "pattern"
        assert diff.old_value == NamingPattern.CAMEL_CASE
        assert diff.new_value == NamingPattern.PASCAL_CASE
        assert diff.path == "rules.ObjectType.pattern"
        
        # 딕셔너리 변환 테스트
        diff_dict = diff.to_dict()
        assert diff_dict["field"] == "pattern"
        assert diff_dict["old_value"] == "camelCase"
        assert diff_dict["new_value"] == "PascalCase"
    
    def test_history_entry_creation(self):
        """이력 엔트리 생성 테스트"""
        diffs = [
            ChangeDiff("name", "Old Name", "New Name"),
            ChangeDiff("description", "Old Desc", "New Desc")
        ]
        
        history = NamingConventionHistory(
            id="test_v1_123456",
            convention_id="test",
            version=1,
            change_type=ChangeType.UPDATE,
            change_summary="Updated name and description",
            diffs=diffs,
            changed_by="test-user",
            change_reason="Test update"
        )
        
        assert history.convention_id == "test"
        assert history.version == 1
        assert history.change_type == ChangeType.UPDATE
        assert len(history.diffs) == 2
        assert history.changed_by == "test-user"
        
        # 딕셔너리 변환 테스트
        history_dict = history.to_dict()
        assert history_dict["convention_id"] == "test"
        assert history_dict["version"] == 1
        assert history_dict["change_type"] == "update"
        assert len(history_dict["diffs"]) == 2
    
    def test_record_creation(self, history_service, sample_convention):
        """생성 이력 기록 테스트"""
        history_entry = history_service.record_creation(
            sample_convention,
            "test-user",
            "Initial creation"
        )
        
        assert history_entry.convention_id == "test-convention"
        assert history_entry.version == 1
        assert history_entry.change_type == ChangeType.CREATE
        assert history_entry.changed_by == "test-user"
        assert history_entry.change_reason == "Initial creation"
        assert history_entry.full_snapshot is not None
        
        # 이력 조회 테스트
        history = history_service.get_history("test-convention")
        assert len(history) == 1
        assert history[0].version == 1
    
    def test_record_update(self, history_service, sample_convention):
        """업데이트 이력 기록 테스트"""
        # 먼저 생성 기록
        history_service.record_creation(sample_convention, "test-user")
        
        # 업데이트할 규칙 생성
        updated_convention = sample_convention.model_copy()
        updated_convention.name = "Updated Test Convention"
        updated_convention.reserved_words = ["test", "example", "sample"]
        
        # 업데이트 기록
        history_entry = history_service.record_update(
            sample_convention,
            updated_convention,
            "test-user",
            "Updated name and reserved words"
        )
        
        assert history_entry.version == 2
        assert history_entry.change_type == ChangeType.UPDATE
        assert len(history_entry.diffs) > 0
        
        # 변경 사항 확인
        name_diff = next(d for d in history_entry.diffs if d.field == "name")
        assert name_diff.old_value == "Test Convention"
        assert name_diff.new_value == "Updated Test Convention"
        
        # 이력 조회 테스트
        history = history_service.get_history("test-convention")
        assert len(history) == 2
        assert history[1].version == 2
    
    def test_record_deletion(self, history_service, sample_convention):
        """삭제 이력 기록 테스트"""
        # 먼저 생성 기록
        history_service.record_creation(sample_convention, "test-user")
        
        # 삭제 기록
        history_entry = history_service.record_deletion(
            sample_convention,
            "test-user",
            "No longer needed"
        )
        
        assert history_entry.version == 2
        assert history_entry.change_type == ChangeType.DELETE
        assert history_entry.change_reason == "No longer needed"
        assert history_entry.full_snapshot is not None
    
    def test_get_convention_at_version(self, history_service, sample_convention):
        """특정 버전의 규칙 조회 테스트"""
        # 버전 1 생성
        history_service.record_creation(sample_convention, "test-user")
        
        # 버전 2 업데이트
        updated_convention = sample_convention.model_copy()
        updated_convention.name = "Version 2 Convention"
        history_service.record_update(
            sample_convention, updated_convention, "test-user"
        )
        
        # 버전 1 조회
        v1_snapshot = history_service.get_convention_at_version("test-convention", 1)
        assert v1_snapshot["name"] == "Test Convention"
        
        # 버전 2 조회
        v2_snapshot = history_service.get_convention_at_version("test-convention", 2)
        assert v2_snapshot["name"] == "Version 2 Convention"
    
    def test_diff_between_versions(self, history_service, sample_convention):
        """버전 간 차이점 조회 테스트"""
        # 버전 1 생성
        history_service.record_creation(sample_convention, "test-user")
        
        # 버전 2 업데이트
        v2_convention = sample_convention.model_copy()
        v2_convention.name = "Version 2"
        v2_convention.description = "Updated description"
        history_service.record_update(sample_convention, v2_convention, "test-user")
        
        # 버전 3 업데이트
        v3_convention = v2_convention.model_copy()
        v3_convention.auto_fix_enabled = False
        history_service.record_update(v2_convention, v3_convention, "test-user")
        
        # 버전 1과 3 사이의 차이점 조회
        diffs = history_service.get_diff_between_versions("test-convention", 1, 3)
        assert len(diffs) > 0
        
        # 변경된 필드 확인
        changed_fields = {diff.field for diff in diffs}
        assert "name" in changed_fields or any("name" in str(diff.path) for diff in diffs)
    
    def test_generate_diff_report(self, history_service, sample_convention):
        """변경 이력 리포트 생성 테스트"""
        # 여러 버전 생성
        history_service.record_creation(sample_convention, "user1", "Initial version")
        
        v2 = sample_convention.model_copy()
        v2.name = "Updated Convention"
        history_service.record_update(sample_convention, v2, "user2", "Name update")
        
        # 리포트 생성
        report = history_service.generate_diff_report("test-convention")
        
        assert "Naming Convention History Report" in report
        assert "test-convention" in report
        assert "Version 1" in report
        assert "Version 2" in report
        assert "user1" in report
        assert "user2" in report
        assert "Initial version" in report
        assert "Name update" in report


class TestNamingConfigServiceWithHistory:
    """이력 기능이 통합된 NamingConfigService 테스트"""
    
    def test_create_convention_with_history(self, config_service, sample_convention):
        """이력 기록과 함께 규칙 생성 테스트"""
        created = config_service.create_convention(
            sample_convention,
            "test-user",
            "Test creation"
        )
        
        assert created.id == "test-convention"
        
        # 이력 확인
        history = config_service.get_convention_history("test-convention")
        assert len(history) == 1
        assert history[0]["version"] == 1
        assert history[0]["change_type"] == "create"
        assert history[0]["change_reason"] == "Test creation"
    
    def test_update_convention_with_history(self, config_service, sample_convention):
        """이력 기록과 함께 규칙 업데이트 테스트"""
        # 먼저 생성
        config_service.create_convention(sample_convention, "test-user")
        
        # 업데이트
        updates = {
            "name": "Updated Convention",
            "description": "New description"
        }
        
        updated = config_service.update_convention(
            "test-convention",
            updates,
            "test-user",
            "Test update"
        )
        
        assert updated.name == "Updated Convention"
        
        # 이력 확인
        history = config_service.get_convention_history("test-convention")
        assert len(history) == 2
        assert history[1]["version"] == 2
        assert history[1]["change_type"] == "update"
        assert history[1]["change_summary"].startswith("Updated:")
    
    def test_delete_convention_with_history(self, config_service, sample_convention):
        """이력 기록과 함께 규칙 삭제 테스트"""
        # 먼저 생성
        config_service.create_convention(sample_convention, "test-user")
        
        # 삭제
        config_service.delete_convention(
            "test-convention",
            "test-user",
            "No longer needed"
        )
        
        # 이력 확인 (삭제되어도 이력은 남음)
        history = config_service.get_convention_history("test-convention")
        assert len(history) == 2
        assert history[1]["version"] == 2
        assert history[1]["change_type"] == "delete"
        assert history[1]["change_reason"] == "No longer needed"
    
    def test_import_convention_with_history(self, config_service):
        """이력 기록과 함께 규칙 가져오기 테스트"""
        import_data = {
            "id": "imported-convention",
            "name": "Imported Convention",
            "description": "Imported from external source",
            "rules": {
                "objectType": {
                    "entity_type": "objectType",
                    "pattern": "PascalCase",
                    "min_length": 3,
                    "max_length": 50
                }
            },
            "reserved_words": ["import", "export"],
            "case_sensitive": True,
            "auto_fix_enabled": True
        }
        
        imported = config_service.import_convention(
            import_data,
            "test-user",
            "Imported from backup"
        )
        
        assert imported.id == "imported-convention"
        
        # 이력 확인
        history = config_service.get_convention_history("imported-convention")
        assert len(history) == 1
        assert history[0]["change_reason"] == "Imported from backup"
    
    def test_get_convention_at_version_via_config(self, config_service, sample_convention):
        """ConfigService를 통한 특정 버전 조회 테스트"""
        # 버전 1 생성
        config_service.create_convention(sample_convention, "test-user")
        
        # 버전 2 업데이트
        config_service.update_convention(
            "test-convention",
            {"name": "Version 2"},
            "test-user"
        )
        
        # 버전 1 조회
        v1 = config_service.get_convention_at_version("test-convention", 1)
        assert v1["name"] == "Test Convention"
        
        # 버전 2 조회
        v2 = config_service.get_convention_at_version("test-convention", 2)
        assert v2["name"] == "Version 2"
    
    def test_generate_history_report_via_config(self, config_service, sample_convention):
        """ConfigService를 통한 이력 리포트 생성 테스트"""
        # 여러 버전 생성
        config_service.create_convention(sample_convention, "user1", "Initial")
        
        config_service.update_convention(
            "test-convention",
            {"description": "Updated"},
            "user2",
            "Description update"
        )
        
        # 리포트 생성
        report = config_service.generate_history_report("test-convention")
        
        assert "Naming Convention History Report" in report
        assert "Version 1" in report
        assert "Version 2" in report
        assert "Description update" in report


class TestHistoryPersistence:
    """이력 영속성 테스트"""
    
    def test_history_persistence(self, temp_paths):
        """이력이 파일에 저장되고 다시 로드되는지 테스트"""
        config_path, history_path = temp_paths
        
        # 첫 번째 서비스 인스턴스
        service1 = NamingConventionHistoryService(str(history_path))
        convention = NamingConvention(
            id="persist-test",
            name="Persistence Test",
            description="Test",
            rules={},
            reserved_words=[],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            created_by="test-user"
        )
        
        service1.record_creation(convention, "test-user", "Test")
        
        # 파일이 생성되었는지 확인
        assert history_path.exists()
        
        # 두 번째 서비스 인스턴스 (파일에서 로드)
        service2 = NamingConventionHistoryService(str(history_path))
        history = service2.get_history("persist-test")
        
        assert len(history) == 1
        assert history[0].convention_id == "persist-test"
        assert history[0].change_reason == "Test"
    
    def test_complex_history_persistence(self, temp_paths):
        """복잡한 이력이 올바르게 저장/로드되는지 테스트"""
        _, history_path = temp_paths
        
        service = NamingConventionHistoryService(str(history_path))
        
        # 복잡한 규칙 생성
        convention = NamingConvention(
            id="complex-test",
            name="Complex Convention",
            description="Complex test",
            rules={
                EntityType.OBJECT_TYPE: NamingRule(
                    entity_type=EntityType.OBJECT_TYPE,
                    pattern=NamingPattern.PASCAL_CASE,
                    required_prefix=["I", "C"],
                    forbidden_suffix=["_temp", "_test"],
                    min_length=5,
                    max_length=50,
                    custom_regex=r'^[A-Z][a-zA-Z0-9]*$'
                )
            },
            reserved_words=["test", "sample", "example"],
            case_sensitive=True,
            auto_fix_enabled=True,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            created_by="test-user"
        )
        
        # 이력 생성
        service.record_creation(convention, "user1", "Initial")
        
        # 업데이트
        updated = convention.model_copy(deep=True)
        updated.name = "Complex Convention v2"
        updated.rules[EntityType.OBJECT_TYPE].min_length = 3  # 5에서 3으로 변경
        updated.reserved_words = updated.reserved_words + ["demo"]  # 리스트 복사본에 추가
        
        service.record_update(convention, updated, "user2", "Relaxed constraints")
        
        # 다시 로드
        service2 = NamingConventionHistoryService(str(history_path))
        history = service2.get_history("complex-test")
        
        assert len(history) == 2
        assert history[0].change_type == ChangeType.CREATE
        assert history[1].change_type == ChangeType.UPDATE
        
        # 차이점 확인
        assert len(history[1].diffs) > 0
        
        # 스냅샷 확인
        v2_snapshot = service2.get_convention_at_version("complex-test", 2)
        assert v2_snapshot["rules"]["objectType"]["min_length"] == 3
        assert "demo" in v2_snapshot["reserved_words"]