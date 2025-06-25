"""
Version Management for JSON Files
JSON 파일 버전 관리 및 호환성 검사
"""
import json
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timezone

from utils.logger import get_logger

logger = get_logger(__name__)


class VersionCompatibility(str, Enum):
    """버전 호환성 레벨"""
    COMPATIBLE = "compatible"              # 완전 호환
    BACKWARD_COMPATIBLE = "backward_compatible"  # 하위 호환
    MIGRATION_REQUIRED = "migration_required"    # 마이그레이션 필요
    INCOMPATIBLE = "incompatible"          # 비호환


@dataclass
class VersionInfo:
    """버전 정보"""
    major: int
    minor: int
    patch: int
    
    @classmethod
    def from_string(cls, version_str: str) -> 'VersionInfo':
        """문자열에서 버전 정보 파싱"""
        try:
            parts = version_str.split('.')
            return cls(
                major=int(parts[0]),
                minor=int(parts[1]) if len(parts) > 1 else 0,
                patch=int(parts[2]) if len(parts) > 2 else 0
            )
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid version format: {version_str}") from e
    
    def to_string(self) -> str:
        """문자열로 변환"""
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def __str__(self) -> str:
        return self.to_string()
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, VersionInfo):
            return False
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
    
    def __lt__(self, other) -> bool:
        if not isinstance(other, VersionInfo):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
    
    def __le__(self, other) -> bool:
        return self == other or self < other
    
    def __gt__(self, other) -> bool:
        return not self <= other
    
    def __ge__(self, other) -> bool:
        return self == other or self > other


@dataclass
class FileMetadata:
    """JSON 파일 메타데이터"""
    format_version: VersionInfo
    created_at: str
    last_modified: str
    schema_type: str
    compatibility_version: Optional[VersionInfo] = None
    migration_notes: Optional[List[str]] = None
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        result = {
            "__version__": self.format_version.to_string(),
            "__metadata__": {
                "created_at": self.created_at,
                "last_modified": self.last_modified,
                "schema_type": self.schema_type
            }
        }
        
        if self.compatibility_version:
            result["__metadata__"]["compatibility_version"] = self.compatibility_version.to_string()
        
        if self.migration_notes:
            result["__metadata__"]["migration_notes"] = self.migration_notes
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'FileMetadata':
        """딕셔너리에서 생성"""
        format_version = VersionInfo.from_string(data.get("__version__", "1.0.0"))
        metadata = data.get("__metadata__", {})
        
        compatibility_version = None
        if "compatibility_version" in metadata:
            compatibility_version = VersionInfo.from_string(metadata["compatibility_version"])
        
        return cls(
            format_version=format_version,
            created_at=metadata.get("created_at", datetime.now(timezone.utc).isoformat()),
            last_modified=metadata.get("last_modified", datetime.now(timezone.utc).isoformat()),
            schema_type=metadata.get("schema_type", "unknown"),
            compatibility_version=compatibility_version,
            migration_notes=metadata.get("migration_notes")
        )


class VersionManager:
    """JSON 파일 버전 관리자"""
    
    # 현재 지원하는 버전들
    CURRENT_VERSION = VersionInfo(1, 1, 0)
    MINIMUM_SUPPORTED_VERSION = VersionInfo(1, 0, 0)
    
    # 스키마별 버전 정보
    SCHEMA_VERSIONS = {
        "naming_convention": VersionInfo(1, 1, 0),
        "naming_history": VersionInfo(1, 0, 0),
        "naming_rule": VersionInfo(1, 0, 0)
    }
    
    # 버전별 변경 사항
    VERSION_CHANGELOG = {
        "1.1.0": [
            "Added schema validation support",
            "Enhanced JSON serialization with UTC timestamps",
            "Added orjson optimization support"
        ],
        "1.0.0": [
            "Initial version",
            "Basic naming convention support",
            "History tracking functionality"
        ]
    }
    
    def __init__(self):
        self.migration_handlers = {
            ("1.0.0", "1.1.0"): self._migrate_1_0_to_1_1
        }
    
    def add_version_metadata(self, data: Dict, schema_type: str = "naming_convention") -> Dict:
        """
        JSON 데이터에 버전 메타데이터 추가
        
        Args:
            data: JSON 데이터
            schema_type: 스키마 타입
            
        Returns:
            버전 메타데이터가 추가된 데이터
        """
        now = datetime.now(timezone.utc).isoformat()
        
        # 기존 메타데이터 확인
        existing_metadata = FileMetadata.from_dict(data) if "__version__" in data else None
        
        if existing_metadata:
            # 기존 파일 업데이트
            metadata = FileMetadata(
                format_version=self.SCHEMA_VERSIONS.get(schema_type, self.CURRENT_VERSION),
                created_at=existing_metadata.created_at,
                last_modified=now,
                schema_type=schema_type,
                compatibility_version=existing_metadata.compatibility_version,
                migration_notes=existing_metadata.migration_notes
            )
        else:
            # 새 파일 생성
            metadata = FileMetadata(
                format_version=self.SCHEMA_VERSIONS.get(schema_type, self.CURRENT_VERSION),
                created_at=now,
                last_modified=now,
                schema_type=schema_type
            )
        
        # 기존 데이터에 메타데이터 추가
        result = data.copy()
        result.update(metadata.to_dict())
        
        return result
    
    def check_compatibility(self, file_data: Dict) -> Tuple[VersionCompatibility, Optional[str]]:
        """
        파일 버전 호환성 확인
        
        Args:
            file_data: JSON 파일 데이터
            
        Returns:
            (호환성 레벨, 메시지)
        """
        try:
            metadata = FileMetadata.from_dict(file_data)
            file_version = metadata.format_version
            schema_type = metadata.schema_type
            
            current_version = self.SCHEMA_VERSIONS.get(schema_type, self.CURRENT_VERSION)
            
            # 동일한 버전
            if file_version == current_version:
                return VersionCompatibility.COMPATIBLE, "File version matches current version"
            
            # 최소 지원 버전보다 낮음
            if file_version < self.MINIMUM_SUPPORTED_VERSION:
                return VersionCompatibility.INCOMPATIBLE, f"File version {file_version} is below minimum supported version {self.MINIMUM_SUPPORTED_VERSION}"
            
            # 현재 버전보다 높음 (미래 버전)
            if file_version > current_version:
                # Minor 버전 차이는 하위 호환 가능
                if file_version.major == current_version.major and file_version.minor - current_version.minor <= 1:
                    return VersionCompatibility.BACKWARD_COMPATIBLE, f"File version {file_version} is newer but backward compatible"
                else:
                    return VersionCompatibility.INCOMPATIBLE, f"File version {file_version} is too new (current: {current_version})"
            
            # 현재 버전보다 낮음 (구 버전)
            if file_version < current_version:
                # Major 버전이 같으면 마이그레이션 가능
                if file_version.major == current_version.major:
                    return VersionCompatibility.MIGRATION_REQUIRED, f"File version {file_version} requires migration to {current_version}"
                else:
                    return VersionCompatibility.INCOMPATIBLE, f"File version {file_version} has incompatible major version"
            
            return VersionCompatibility.COMPATIBLE, "Version check completed"
            
        except Exception as e:
            logger.error(f"Error checking version compatibility: {e}")
            return VersionCompatibility.INCOMPATIBLE, f"Error checking compatibility: {e}"
    
    def migrate_file(self, file_data: Dict) -> Tuple[Dict, List[str]]:
        """
        파일을 현재 버전으로 마이그레이션
        
        Args:
            file_data: 마이그레이션할 JSON 데이터
            
        Returns:
            (마이그레이션된 데이터, 적용된 마이그레이션 목록)
        """
        try:
            metadata = FileMetadata.from_dict(file_data)
            current_version = metadata.format_version
            target_version = self.SCHEMA_VERSIONS.get(metadata.schema_type, self.CURRENT_VERSION)
            
            applied_migrations = []
            migrated_data = file_data.copy()
            
            # 버전별 순차 마이그레이션
            while current_version < target_version:
                migration_path = None
                
                # 적용 가능한 마이그레이션 찾기
                for (from_ver, to_ver), handler in self.migration_handlers.items():
                    from_version = VersionInfo.from_string(from_ver)
                    to_version = VersionInfo.from_string(to_ver)
                    
                    if current_version == from_version and to_version <= target_version:
                        migration_path = (from_ver, to_ver)
                        break
                
                if not migration_path:
                    logger.warning(f"No migration path found from {current_version} to {target_version}")
                    break
                
                # 마이그레이션 적용
                from_ver, to_ver = migration_path
                handler = self.migration_handlers[migration_path]
                migrated_data = handler(migrated_data)
                
                current_version = VersionInfo.from_string(to_ver)
                applied_migrations.append(f"{from_ver} → {to_ver}")
                
                logger.info(f"Applied migration: {from_ver} → {to_ver}")
            
            # 메타데이터 업데이트
            migrated_data = self.add_version_metadata(migrated_data, metadata.schema_type)
            
            # 마이그레이션 노트 추가
            if applied_migrations:
                migrated_metadata = FileMetadata.from_dict(migrated_data)
                migrated_metadata.migration_notes = migrated_metadata.migration_notes or []
                migrated_metadata.migration_notes.extend(applied_migrations)
                
                # 메타데이터 재적용
                metadata_dict = migrated_metadata.to_dict()
                migrated_data.update(metadata_dict)
            
            return migrated_data, applied_migrations
            
        except Exception as e:
            logger.error(f"Error during migration: {e}")
            raise ValueError(f"Migration failed: {e}")
    
    def _migrate_1_0_to_1_1(self, data: Dict) -> Dict:
        """1.0.0에서 1.1.0으로 마이그레이션"""
        migrated = data.copy()
        
        # 1.1.0에서 추가된 기능들
        # 1. UTC 타임스탬프 정규화
        if "created_at" in migrated:
            try:
                dt = datetime.fromisoformat(migrated["created_at"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                migrated["created_at"] = dt.isoformat()
            except ValueError:
                # 파싱 실패 시 현재 시간으로 대체
                migrated["created_at"] = datetime.now(timezone.utc).isoformat()
        
        if "updated_at" in migrated:
            try:
                dt = datetime.fromisoformat(migrated["updated_at"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                migrated["updated_at"] = dt.isoformat()
            except ValueError:
                migrated["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # conventions 배열의 각 항목도 처리
        if "conventions" in migrated:
            for conv in migrated["conventions"]:
                if "created_at" in conv:
                    try:
                        dt = datetime.fromisoformat(conv["created_at"])
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        conv["created_at"] = dt.isoformat()
                    except ValueError:
                        conv["created_at"] = datetime.now(timezone.utc).isoformat()
                
                if "updated_at" in conv:
                    try:
                        dt = datetime.fromisoformat(conv["updated_at"])
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        conv["updated_at"] = dt.isoformat()
                    except ValueError:
                        conv["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # 2. 스키마 검증을 위한 기본값 추가
        if "rules" in migrated and migrated["rules"]:
            # 빈 규칙이 있으면 제거
            migrated["rules"] = {k: v for k, v in migrated["rules"].items() if v}
        
        # 3. 예약어 정규화
        if "reserved_words" in migrated:
            # 중복 제거 및 빈 값 제거
            words = migrated["reserved_words"]
            if isinstance(words, list):
                migrated["reserved_words"] = list(set(word for word in words if word and word.strip()))
        
        # conventions 배열의 각 항목에서도 예약어 정리
        if "conventions" in migrated:
            for conv in migrated["conventions"]:
                if "reserved_words" in conv:
                    words = conv["reserved_words"]
                    if isinstance(words, list):
                        conv["reserved_words"] = list(set(word for word in words if word and word.strip()))
        
        logger.info("Applied migration 1.0.0 → 1.1.0")
        return migrated
    
    def get_version_info(self, file_data: Dict) -> Optional[FileMetadata]:
        """파일의 버전 정보 반환"""
        try:
            return FileMetadata.from_dict(file_data)
        except Exception as e:
            logger.error(f"Error getting version info: {e}")
            return None
    
    def is_current_version(self, file_data: Dict) -> bool:
        """파일이 현재 버전인지 확인"""
        metadata = self.get_version_info(file_data)
        if not metadata:
            return False
        
        current_version = self.SCHEMA_VERSIONS.get(metadata.schema_type, self.CURRENT_VERSION)
        return metadata.format_version == current_version
    
    def get_changelog(self, from_version: str, to_version: str) -> List[str]:
        """버전 간 변경 사항 조회"""
        changes = []
        
        try:
            from_ver = VersionInfo.from_string(from_version)
            to_ver = VersionInfo.from_string(to_version)
            
            for version_str, changelog in self.VERSION_CHANGELOG.items():
                version = VersionInfo.from_string(version_str)
                if from_ver < version <= to_ver:
                    changes.extend(changelog)
            
        except ValueError as e:
            logger.error(f"Error getting changelog: {e}")
        
        return changes
    
    def validate_version_format(self, version_str: str) -> bool:
        """버전 형식 검증"""
        try:
            VersionInfo.from_string(version_str)
            return True
        except ValueError:
            return False


# 싱글톤 인스턴스
_version_manager = None

def get_version_manager() -> VersionManager:
    """버전 관리자 인스턴스 반환"""
    global _version_manager
    if not _version_manager:
        _version_manager = VersionManager()
    return _version_manager


def add_file_version(data: Dict, schema_type: str = "naming_convention") -> Dict:
    """
    JSON 데이터에 버전 정보 추가 (편의 함수)
    
    Args:
        data: JSON 데이터
        schema_type: 스키마 타입
        
    Returns:
        버전 정보가 추가된 데이터
    """
    manager = get_version_manager()
    return manager.add_version_metadata(data, schema_type)


def check_file_compatibility(data: Dict) -> Tuple[VersionCompatibility, str]:
    """
    파일 호환성 확인 (편의 함수)
    
    Args:
        data: JSON 데이터
        
    Returns:
        (호환성 레벨, 메시지)
    """
    manager = get_version_manager()
    compatibility, message = manager.check_compatibility(data)
    return compatibility, message or ""


def migrate_file_if_needed(data: Dict) -> Tuple[Dict, bool, List[str]]:
    """
    필요시 파일 마이그레이션 (편의 함수)
    
    Args:
        data: JSON 데이터
        
    Returns:
        (처리된 데이터, 마이그레이션 여부, 적용된 마이그레이션 목록)
    """
    manager = get_version_manager()
    compatibility, message = manager.check_compatibility(data)
    
    if compatibility == VersionCompatibility.MIGRATION_REQUIRED:
        migrated_data, migrations = manager.migrate_file(data)
        return migrated_data, True, migrations
    elif compatibility in [VersionCompatibility.COMPATIBLE, VersionCompatibility.BACKWARD_COMPATIBLE]:
        # 호환 가능하지만 메타데이터 업데이트
        metadata = manager.get_version_info(data)
        if metadata:
            updated_data = manager.add_version_metadata(data, metadata.schema_type)
            return updated_data, False, []
        return data, False, []
    else:
        raise ValueError(f"File is incompatible: {message}")