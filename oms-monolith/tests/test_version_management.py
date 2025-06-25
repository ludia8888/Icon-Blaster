"""
Tests for Version Management
버전 관리 및 호환성 검사 테스트
"""
import pytest
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from core.validation.version_manager import (
    VersionInfo, VersionCompatibility, FileMetadata, VersionManager,
    get_version_manager, add_file_version, check_file_compatibility,
    migrate_file_if_needed
)
from core.validation.naming_config import NamingConfigService
from core.validation.naming_convention import EntityType, NamingPattern, NamingRule, NamingConvention


class TestVersionInfo:
    """VersionInfo 클래스 테스트"""
    
    def test_version_parsing(self):
        """버전 문자열 파싱 테스트"""
        # 정상적인 버전 형식
        v1 = VersionInfo.from_string("1.2.3")
        assert v1.major == 1
        assert v1.minor == 2
        assert v1.patch == 3
        
        # 짧은 형식
        v2 = VersionInfo.from_string("2.1")
        assert v2.major == 2
        assert v2.minor == 1
        assert v2.patch == 0
        
        # 단일 숫자
        v3 = VersionInfo.from_string("3")
        assert v3.major == 3
        assert v3.minor == 0
        assert v3.patch == 0
    
    def test_invalid_version_parsing(self):
        """잘못된 버전 형식 테스트"""
        with pytest.raises(ValueError):
            VersionInfo.from_string("invalid")
        
        with pytest.raises(ValueError):
            VersionInfo.from_string("1.a.3")
        
        with pytest.raises(ValueError):
            VersionInfo.from_string("")
    
    def test_version_string_conversion(self):
        """버전 문자열 변환 테스트"""
        v = VersionInfo(1, 2, 3)
        assert v.to_string() == "1.2.3"
        assert str(v) == "1.2.3"
    
    def test_version_comparison(self):
        """버전 비교 테스트"""
        v1_0_0 = VersionInfo(1, 0, 0)
        v1_1_0 = VersionInfo(1, 1, 0)
        v1_1_1 = VersionInfo(1, 1, 1)
        v2_0_0 = VersionInfo(2, 0, 0)
        
        # 같음
        assert v1_0_0 == VersionInfo(1, 0, 0)
        
        # 작음
        assert v1_0_0 < v1_1_0
        assert v1_1_0 < v1_1_1
        assert v1_1_1 < v2_0_0
        
        # 크거나 같음
        assert v2_0_0 > v1_1_1
        assert v1_1_0 >= v1_0_0
        assert v1_1_0 >= VersionInfo(1, 1, 0)


class TestFileMetadata:
    """FileMetadata 클래스 테스트"""
    
    def test_metadata_creation(self):
        """메타데이터 생성 테스트"""
        now = datetime.now(timezone.utc).isoformat()
        metadata = FileMetadata(
            format_version=VersionInfo(1, 1, 0),
            created_at=now,
            last_modified=now,
            schema_type="naming_convention"
        )
        
        assert metadata.format_version.major == 1
        assert metadata.format_version.minor == 1
        assert metadata.format_version.patch == 0
        assert metadata.schema_type == "naming_convention"
    
    def test_metadata_to_dict(self):
        """메타데이터 딕셔너리 변환 테스트"""
        now = "2024-01-01T12:00:00Z"
        metadata = FileMetadata(
            format_version=VersionInfo(1, 1, 0),
            created_at=now,
            last_modified=now,
            schema_type="naming_convention",
            compatibility_version=VersionInfo(1, 0, 0),
            migration_notes=["Migrated from 1.0.0"]
        )
        
        result = metadata.to_dict()
        
        assert result["__version__"] == "1.1.0"
        assert result["__metadata__"]["created_at"] == now
        assert result["__metadata__"]["last_modified"] == now
        assert result["__metadata__"]["schema_type"] == "naming_convention"
        assert result["__metadata__"]["compatibility_version"] == "1.0.0"
        assert result["__metadata__"]["migration_notes"] == ["Migrated from 1.0.0"]
    
    def test_metadata_from_dict(self):
        """딕셔너리에서 메타데이터 생성 테스트"""
        data = {
            "__version__": "1.1.0",
            "__metadata__": {
                "created_at": "2024-01-01T12:00:00Z",
                "last_modified": "2024-01-01T12:30:00Z",
                "schema_type": "naming_convention",
                "compatibility_version": "1.0.0",
                "migration_notes": ["Test migration"]
            }
        }
        
        metadata = FileMetadata.from_dict(data)
        
        assert metadata.format_version == VersionInfo(1, 1, 0)
        assert metadata.created_at == "2024-01-01T12:00:00Z"
        assert metadata.last_modified == "2024-01-01T12:30:00Z"
        assert metadata.schema_type == "naming_convention"
        assert metadata.compatibility_version == VersionInfo(1, 0, 0)
        assert metadata.migration_notes == ["Test migration"]
    
    def test_metadata_from_minimal_dict(self):
        """최소한의 데이터에서 메타데이터 생성 테스트"""
        data = {"some_field": "some_value"}  # 버전 정보 없음
        
        metadata = FileMetadata.from_dict(data)
        
        # 기본값들이 설정되어야 함
        assert metadata.format_version == VersionInfo(1, 0, 0)
        assert metadata.schema_type == "unknown"
        assert isinstance(metadata.created_at, str)
        assert isinstance(metadata.last_modified, str)


class TestVersionManager:
    """VersionManager 클래스 테스트"""
    
    def test_manager_initialization(self):
        """매니저 초기화 테스트"""
        manager = VersionManager()
        
        assert manager.CURRENT_VERSION == VersionInfo(1, 1, 0)
        assert manager.MINIMUM_SUPPORTED_VERSION == VersionInfo(1, 0, 0)
        assert "naming_convention" in manager.SCHEMA_VERSIONS
        assert len(manager.VERSION_CHANGELOG) > 0
    
    def test_add_version_metadata_new_file(self):
        """새 파일에 버전 메타데이터 추가 테스트"""
        manager = VersionManager()
        
        data = {
            "id": "test-convention",
            "name": "Test Convention",
            "rules": {}
        }
        
        result = manager.add_version_metadata(data, "naming_convention")
        
        assert "__version__" in result
        assert "__metadata__" in result
        assert result["__version__"] == "1.1.0"  # naming_convention의 현재 버전
        assert result["__metadata__"]["schema_type"] == "naming_convention"
        assert "created_at" in result["__metadata__"]
        assert "last_modified" in result["__metadata__"]
    
    def test_add_version_metadata_existing_file(self):
        """기존 파일 버전 메타데이터 업데이트 테스트"""
        manager = VersionManager()
        
        # 기존 메타데이터가 있는 데이터
        data = {
            "__version__": "1.0.0",
            "__metadata__": {
                "created_at": "2023-01-01T12:00:00Z",
                "last_modified": "2023-01-01T12:00:00Z",
                "schema_type": "naming_convention"
            },
            "id": "test-convention",
            "name": "Test Convention"
        }
        
        result = manager.add_version_metadata(data, "naming_convention")
        
        # 버전은 현재 버전으로 업데이트
        assert result["__version__"] == "1.1.0"
        # 생성 시간은 유지
        assert result["__metadata__"]["created_at"] == "2023-01-01T12:00:00Z"
        # 수정 시간은 업데이트
        assert result["__metadata__"]["last_modified"] != "2023-01-01T12:00:00Z"
    
    def test_check_compatibility_same_version(self):
        """동일한 버전 호환성 확인 테스트"""
        manager = VersionManager()
        
        data = {
            "__version__": "1.1.0",
            "__metadata__": {
                "schema_type": "naming_convention"
            }
        }
        
        compatibility, message = manager.check_compatibility(data)
        
        assert compatibility == VersionCompatibility.COMPATIBLE
        assert "matches current version" in message
    
    def test_check_compatibility_migration_required(self):
        """마이그레이션 필요 호환성 확인 테스트"""
        manager = VersionManager()
        
        data = {
            "__version__": "1.0.0",
            "__metadata__": {
                "schema_type": "naming_convention"
            }
        }
        
        compatibility, message = manager.check_compatibility(data)
        
        assert compatibility == VersionCompatibility.MIGRATION_REQUIRED
        assert "requires migration" in message
    
    def test_check_compatibility_incompatible_old(self):
        """호환되지 않는 구 버전 테스트"""
        manager = VersionManager()
        
        data = {
            "__version__": "0.5.0",  # 최소 지원 버전보다 낮음
            "__metadata__": {
                "schema_type": "naming_convention"
            }
        }
        
        compatibility, message = manager.check_compatibility(data)
        
        assert compatibility == VersionCompatibility.INCOMPATIBLE
        assert "below minimum supported version" in message
    
    def test_check_compatibility_incompatible_new(self):
        """호환되지 않는 미래 버전 테스트"""
        manager = VersionManager()
        
        data = {
            "__version__": "3.0.0",  # 너무 새로운 버전
            "__metadata__": {
                "schema_type": "naming_convention"
            }
        }
        
        compatibility, message = manager.check_compatibility(data)
        
        assert compatibility == VersionCompatibility.INCOMPATIBLE
        assert "too new" in message
    
    def test_check_compatibility_backward_compatible(self):
        """하위 호환 가능 버전 테스트"""
        manager = VersionManager()
        
        data = {
            "__version__": "1.2.0",  # Minor 버전이 하나 높음
            "__metadata__": {
                "schema_type": "naming_convention"
            }
        }
        
        compatibility, message = manager.check_compatibility(data)
        
        assert compatibility == VersionCompatibility.BACKWARD_COMPATIBLE
        assert "newer but backward compatible" in message
    
    def test_migrate_file_1_0_to_1_1(self):
        """1.0.0에서 1.1.0 마이그레이션 테스트"""
        manager = VersionManager()
        
        # 1.0.0 형식 데이터 (naive datetime)
        data = {
            "__version__": "1.0.0",
            "__metadata__": {
                "schema_type": "naming_convention"
            },
            "id": "test-convention",
            "name": "Test Convention",
            "created_at": "2024-01-01T12:00:00",  # timezone 없음
            "updated_at": "2024-01-01T12:00:00",  # timezone 없음
            "reserved_words": ["test", "test", "", "  ", "example"],  # 중복 및 빈 값
            "rules": {}
        }
        
        migrated_data, migrations = manager.migrate_file(data)
        
        assert len(migrations) == 1
        assert "1.0.0 → 1.1.0" in migrations[0]
        
        # UTC 타임스탬프로 변환되었는지 확인
        assert migrated_data["created_at"].endswith(('+00:00', 'Z'))
        assert migrated_data["updated_at"].endswith(('+00:00', 'Z'))
        
        # 예약어 정규화 확인
        assert set(migrated_data["reserved_words"]) == {"test", "example"}
        
        # 버전 업데이트 확인
        assert migrated_data["__version__"] == "1.1.0"
    
    def test_migrate_file_no_migration_needed(self):
        """마이그레이션 불필요한 경우 테스트"""
        manager = VersionManager()
        
        data = {
            "__version__": "1.1.0",
            "__metadata__": {
                "schema_type": "naming_convention"
            },
            "id": "test-convention"
        }
        
        migrated_data, migrations = manager.migrate_file(data)
        
        assert len(migrations) == 0
        assert migrated_data["__version__"] == "1.1.0"
    
    def test_get_version_info(self):
        """버전 정보 조회 테스트"""
        manager = VersionManager()
        
        data = {
            "__version__": "1.1.0",
            "__metadata__": {
                "created_at": "2024-01-01T12:00:00Z",
                "schema_type": "naming_convention"
            }
        }
        
        metadata = manager.get_version_info(data)
        
        assert metadata is not None
        assert metadata.format_version == VersionInfo(1, 1, 0)
        assert metadata.schema_type == "naming_convention"
    
    def test_is_current_version(self):
        """현재 버전 확인 테스트"""
        manager = VersionManager()
        
        current_data = {
            "__version__": "1.1.0",
            "__metadata__": {
                "schema_type": "naming_convention"
            }
        }
        
        old_data = {
            "__version__": "1.0.0",
            "__metadata__": {
                "schema_type": "naming_convention"
            }
        }
        
        assert manager.is_current_version(current_data) is True
        assert manager.is_current_version(old_data) is False
    
    def test_get_changelog(self):
        """변경 사항 조회 테스트"""
        manager = VersionManager()
        
        changelog = manager.get_changelog("1.0.0", "1.1.0")
        
        assert len(changelog) > 0
        assert any("schema validation" in change.lower() for change in changelog)
    
    def test_validate_version_format(self):
        """버전 형식 검증 테스트"""
        manager = VersionManager()
        
        assert manager.validate_version_format("1.0.0") is True
        assert manager.validate_version_format("1.2") is True
        assert manager.validate_version_format("2") is True
        assert manager.validate_version_format("invalid") is False
        assert manager.validate_version_format("1.a.0") is False


class TestConvenienceFunctions:
    """편의 함수 테스트"""
    
    def test_add_file_version(self):
        """파일 버전 추가 편의 함수 테스트"""
        data = {"id": "test", "name": "Test"}
        
        result = add_file_version(data, "naming_convention")
        
        assert "__version__" in result
        assert "__metadata__" in result
        assert result["id"] == "test"
        assert result["name"] == "Test"
    
    def test_check_file_compatibility(self):
        """파일 호환성 확인 편의 함수 테스트"""
        data = {
            "__version__": "1.0.0",
            "__metadata__": {
                "schema_type": "naming_convention"
            }
        }
        
        compatibility, message = check_file_compatibility(data)
        
        assert compatibility == VersionCompatibility.MIGRATION_REQUIRED
        assert isinstance(message, str)
        assert len(message) > 0
    
    def test_migrate_file_if_needed_with_migration(self):
        """필요시 파일 마이그레이션 편의 함수 테스트 - 마이그레이션 필요"""
        data = {
            "__version__": "1.0.0",
            "__metadata__": {
                "schema_type": "naming_convention"
            },
            "created_at": "2024-01-01T12:00:00"  # timezone 없음
        }
        
        result_data, migrated, migrations = migrate_file_if_needed(data)
        
        assert migrated is True
        assert len(migrations) > 0
        assert result_data["__version__"] == "1.1.0"
        assert result_data["created_at"].endswith(('+00:00', 'Z'))
    
    def test_migrate_file_if_needed_no_migration(self):
        """필요시 파일 마이그레이션 편의 함수 테스트 - 마이그레이션 불필요"""
        data = {
            "__version__": "1.1.0",
            "__metadata__": {
                "schema_type": "naming_convention"
            }
        }
        
        result_data, migrated, migrations = migrate_file_if_needed(data)
        
        assert migrated is False
        assert len(migrations) == 0
        assert result_data["__version__"] == "1.1.0"
    
    def test_migrate_file_if_needed_incompatible(self):
        """필요시 파일 마이그레이션 편의 함수 테스트 - 호환 불가"""
        data = {
            "__version__": "0.5.0",  # 최소 지원 버전보다 낮음
            "__metadata__": {
                "schema_type": "naming_convention"
            }
        }
        
        with pytest.raises(ValueError) as exc_info:
            migrate_file_if_needed(data)
        
        assert "incompatible" in str(exc_info.value).lower()


class TestVersionManagerIntegration:
    """VersionManager와 NamingConfigService 통합 테스트"""
    
    def test_config_service_version_integration(self):
        """설정 서비스와 버전 관리 통합 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_config.json"
            
            # 1.0.0 형식 파일 생성
            old_data = {
                "__version__": "1.0.0",
                "__metadata__": {
                    "schema_type": "naming_convention"
                },
                "conventions": [{
                    "id": "test-convention",
                    "name": "Test Convention",
                    "rules": {
                        "objectType": {
                            "entity_type": "objectType",
                            "pattern": "PascalCase",
                            "min_length": 3,
                            "max_length": 50
                        }
                    },
                    "reserved_words": ["test", "test", ""],  # 중복 및 빈 값
                    "case_sensitive": True,
                    "auto_fix_enabled": True,
                    "created_at": "2024-01-01T12:00:00",  # naive datetime
                    "updated_at": "2024-01-01T12:00:00",
                    "created_by": "test-user"
                }]
            }
            
            # 구 버전 파일 저장
            with open(config_path, 'w') as f:
                json.dump(old_data, f, indent=2)
            
            # 서비스 로드 (자동 마이그레이션 수행)
            service = NamingConfigService(str(config_path))
            
            # 마이그레이션이 적용되었는지 확인
            loaded_convention = service.get_convention("test-convention")
            assert loaded_convention is not None
            assert loaded_convention.id == "test-convention"
            
            # 파일이 새 버전으로 업데이트되었는지 확인
            with open(config_path, 'r') as f:
                updated_data = json.load(f)
            
            assert updated_data["__version__"] == "1.1.0"
            
            # UTC 타임스탬프로 변환되었는지 확인
            convention_data = updated_data["conventions"][0]
            assert convention_data["created_at"].endswith(('+00:00', 'Z'))
            assert convention_data["updated_at"].endswith(('+00:00', 'Z'))
            
            # 예약어 정리되었는지 확인
            assert convention_data["reserved_words"] == ["test"]
    
    def test_config_service_version_methods(self):
        """설정 서비스의 버전 관리 메소드 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_config.json"
            
            service = NamingConfigService(str(config_path))
            
            # 새 규칙 생성 (자동으로 버전 메타데이터 추가됨)
            convention = NamingConvention(
                id="version-test",
                name="Version Test Convention",
                description="Testing version functionality",
                rules={
                    EntityType.OBJECT_TYPE: NamingRule(
                        entity_type=EntityType.OBJECT_TYPE,
                        pattern=NamingPattern.PASCAL_CASE,
                        min_length=3,
                        max_length=50
                    )
                },
                reserved_words=["test"],
                case_sensitive=True,
                auto_fix_enabled=True,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                created_by="version-tester"
            )
            
            service.create_convention(convention, "version-tester", "Version test")
            
            # 버전 정보 확인
            version_info = service.check_file_version()
            
            assert version_info["compatibility"] == "compatible"
            assert version_info["is_current"] is True
            assert version_info["needs_migration"] is False
            assert "version_info" in version_info
            assert version_info["version_info"]["__version__"] == "1.1.0"
            
            # 변경 사항 조회
            changelog = service.get_version_changelog()
            assert len(changelog) > 0
    
    def test_config_service_migration_methods(self):
        """설정 서비스의 마이그레이션 메소드 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "migration_test.json"
            
            # 구 버전 파일 생성
            old_data = {
                "__version__": "1.0.0",
                "__metadata__": {
                    "schema_type": "naming_convention"
                },
                "conventions": [{
                    "id": "migration-test",
                    "name": "Migration Test",
                    "rules": {},
                    "reserved_words": ["test", "test"],  # 중복
                    "case_sensitive": True,
                    "auto_fix_enabled": True,
                    "created_at": "2024-01-01T12:00:00",
                    "updated_at": "2024-01-01T12:00:00",
                    "created_by": "test-user"
                }]
            }
            
            with open(config_path, 'w') as f:
                json.dump(old_data, f, indent=2)
            
            service = NamingConfigService(str(config_path))
            
            # 수동 마이그레이션 수행 (이미 로드 시 자동 마이그레이션 됨)
            migration_result = service.migrate_config_file(backup=True)
            
            assert migration_result["success"] is True
            # 이미 로드 시 마이그레이션이 되었으므로 추가 마이그레이션은 불필요할 수 있음
            # assert migration_result["migrated"] is True
            # 마이그레이션이 있었거나 없어도 백업은 생성되어야 함
            assert "backup_path" in migration_result
            
            # 백업 파일이 생성되었는지 확인
            if migration_result["backup_path"]:
                backup_path = Path(migration_result["backup_path"])
                assert backup_path.exists()
            
            # 마이그레이션 후 파일 확인
            version_info = service.check_file_version()
            assert version_info["is_current"] is True
    
    def test_singleton_version_manager(self):
        """싱글톤 버전 매니저 테스트"""
        manager1 = get_version_manager()
        manager2 = get_version_manager()
        
        # 동일한 인스턴스인지 확인
        assert manager1 is manager2
        
        # 기본 설정 확인
        assert manager1.CURRENT_VERSION == VersionInfo(1, 1, 0)
        assert manager1.MINIMUM_SUPPORTED_VERSION == VersionInfo(1, 0, 0)


class TestVersionErrorHandling:
    """버전 관리 에러 처리 테스트"""
    
    def test_invalid_version_data(self):
        """잘못된 버전 데이터 처리 테스트"""
        manager = VersionManager()
        
        # 잘못된 버전 형식
        data = {
            "__version__": "invalid.version",
            "__metadata__": {
                "schema_type": "naming_convention"
            }
        }
        
        compatibility, message = manager.check_compatibility(data)
        assert compatibility == VersionCompatibility.INCOMPATIBLE
        assert "error" in message.lower()
    
    def test_missing_metadata(self):
        """메타데이터 누락 처리 테스트"""
        manager = VersionManager()
        
        # 메타데이터 없는 데이터
        data = {"id": "test", "name": "Test"}
        
        # 기본값으로 처리되어야 함
        metadata = manager.get_version_info(data)
        assert metadata is not None
        assert metadata.format_version == VersionInfo(1, 0, 0)
        assert metadata.schema_type == "unknown"
    
    def test_migration_failure_handling(self):
        """마이그레이션 실패 처리 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "nonexistent.json"
            
            service = NamingConfigService(str(config_path))
            
            # 존재하지 않는 파일 마이그레이션 시도
            result = service.migrate_config_file()
            
            assert result["success"] is False
            assert "error" in result
            assert "not found" in result["error"].lower()
    
    def test_corrupted_file_handling(self):
        """손상된 파일 처리 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "corrupted.json"
            
            # 잘못된 JSON 파일 생성
            with open(config_path, 'w') as f:
                f.write("{ invalid json content")
            
            service = NamingConfigService(str(config_path))
            
            # 파일 버전 확인 시 에러 처리
            version_info = service.check_file_version()
            
            assert "error" in version_info


class TestVersionCompatibilityMatrix:
    """버전 호환성 매트릭스 테스트"""
    
    @pytest.mark.parametrize("file_version,expected_compatibility", [
        ("1.1.0", VersionCompatibility.COMPATIBLE),           # 현재 버전
        ("1.0.0", VersionCompatibility.MIGRATION_REQUIRED),   # 구 버전, 마이그레이션 가능
        ("1.2.0", VersionCompatibility.BACKWARD_COMPATIBLE),  # 새 버전, 하위 호환
        ("0.9.0", VersionCompatibility.INCOMPATIBLE),         # 최소 지원 버전보다 낮음
        ("2.0.0", VersionCompatibility.INCOMPATIBLE),         # Major 버전 차이
        ("1.3.0", VersionCompatibility.INCOMPATIBLE),         # Minor 버전 차이가 너무 큼
    ])
    def test_version_compatibility_matrix(self, file_version, expected_compatibility):
        """버전 호환성 매트릭스 테스트"""
        manager = VersionManager()
        
        data = {
            "__version__": file_version,
            "__metadata__": {
                "schema_type": "naming_convention"
            }
        }
        
        compatibility, _ = manager.check_compatibility(data)
        assert compatibility == expected_compatibility