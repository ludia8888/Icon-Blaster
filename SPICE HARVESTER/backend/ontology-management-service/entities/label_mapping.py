"""
레이블 매핑 엔티티 정의
레이블과 ID 간의 매핑을 저장하는 도메인 엔티티
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from value_objects.multilingual_text import MultiLingualText


@dataclass
class LabelMapping:
    """
    레이블 매핑 엔티티
    
    TerminusDB에 저장되는 레이블 매핑 정보를 나타내는 도메인 엔티티
    """
    
    # 기본 식별자
    id: str  # 고유 ID (예: "label_mapping_class_Person_ko")
    db_name: str  # 데이터베이스 이름
    
    # 매핑 정보
    mapping_type: str  # "class", "property", "relationship"
    target_id: str  # 매핑 대상 ID (class_id, property_id, predicate)
    label: str  # 레이블 텍스트
    language: str = "ko"  # 언어 코드
    
    # 추가 정보 (선택사항)
    description: Optional[str] = None  # 설명
    class_id: Optional[str] = None  # property 타입일 때 소속 클래스 ID
    
    # 메타데이터
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # TerminusDB 특정 필드
    terminus_type: str = "LabelMapping"  # TerminusDB 타입
    
    def to_terminusdb_document(self) -> Dict[str, Any]:
        """
        TerminusDB 문서 형식으로 변환
        
        Returns:
            TerminusDB 문서 딕셔너리
        """
        return {
            "@id": self.id,
            "@type": self.terminus_type,
            "db_name": self.db_name,
            "mapping_type": self.mapping_type,
            "target_id": self.target_id,
            "label": self.label,
            "language": self.language,
            "description": self.description,
            "class_id": self.class_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_terminusdb_document(cls, doc: Dict[str, Any]) -> 'LabelMapping':
        """
        TerminusDB 문서에서 LabelMapping 엔티티 생성
        
        Args:
            doc: TerminusDB 문서
            
        Returns:
            LabelMapping 인스턴스
        """
        return cls(
            id=doc["@id"],
            db_name=doc["db_name"],
            mapping_type=doc["mapping_type"],
            target_id=doc["target_id"],
            label=doc["label"],
            language=doc.get("language", "ko"),
            description=doc.get("description"),
            class_id=doc.get("class_id"),
            created_at=datetime.fromisoformat(doc["created_at"]) if doc.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(doc["updated_at"]) if doc.get("updated_at") else datetime.utcnow()
        )
    
    def update_timestamp(self) -> None:
        """업데이트 타임스탬프 갱신"""
        self.updated_at = datetime.utcnow()
    
    @staticmethod
    def generate_id(db_name: str, mapping_type: str, target_id: str, 
                   language: str = "ko", class_id: Optional[str] = None) -> str:
        """
        고유 ID 생성
        
        Args:
            db_name: 데이터베이스 이름
            mapping_type: 매핑 타입
            target_id: 대상 ID
            language: 언어 코드
            class_id: 클래스 ID (property 타입일 때만)
            
        Returns:
            고유 ID
        """
        if mapping_type == "property" and class_id:
            return f"label_mapping_{mapping_type}_{class_id}_{target_id}_{language}"
        else:
            return f"label_mapping_{mapping_type}_{target_id}_{language}"
    
    def __eq__(self, other: object) -> bool:
        """동등성 비교"""
        if not isinstance(other, LabelMapping):
            return False
        return (
            self.db_name == other.db_name and
            self.mapping_type == other.mapping_type and
            self.target_id == other.target_id and
            self.language == other.language and
            self.class_id == other.class_id
        )
    
    def __hash__(self) -> int:
        """해시 계산"""
        return hash((
            self.db_name,
            self.mapping_type,
            self.target_id,
            self.language,
            self.class_id
        ))