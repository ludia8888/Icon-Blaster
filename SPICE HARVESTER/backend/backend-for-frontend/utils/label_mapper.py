"""
Label Mapper 유틸리티
사용자 친화적인 레이블과 내부 ID 간의 매핑을 관리합니다.
영속성을 위해 SQLite를 사용합니다.
"""

import aiosqlite
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
import logging
from contextlib import asynccontextmanager
import asyncio
import sys
import os

# shared 모델 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from models.ontology import MultiLingualText, QueryInput, QueryFilter

logger = logging.getLogger(__name__)


class LabelMapper:
    """
    레이블과 ID 간의 매핑을 관리하는 클래스
    SQLite를 사용하여 매핑 정보를 영속적으로 저장합니다.
    """
    
    def __init__(self, db_path: str = "../data/label_mappings.db"):
        """
        초기화
        
        Args:
            db_path: SQLite 데이터베이스 파일 경로
        """
        self.db_path = db_path
        self._ensure_directory()
        self._init_flag = False
        self._init_lock = asyncio.Lock()
    
    def _ensure_directory(self):
        """데이터베이스 디렉토리 생성"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
    
    async def _init_database(self):
        """데이터베이스 초기화 및 테이블 생성 (thread-safe)"""
        if self._init_flag:
            return
            
        async with self._init_lock:
            # 락을 얻은 후 다시 확인 (double-checked locking)
            if self._init_flag:
                return
                
            async with self._get_connection() as conn:
                # 클래스 매핑 테이블
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS class_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    db_name TEXT NOT NULL,
                    class_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    label_lang TEXT DEFAULT 'ko',
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(db_name, class_id, label_lang)
                )
                """)
                
                # 속성 매핑 테이블
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS property_mappings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        db_name TEXT NOT NULL,
                        class_id TEXT NOT NULL,
                        property_id TEXT NOT NULL,
                        label TEXT NOT NULL,
                        label_lang TEXT DEFAULT 'ko',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(db_name, class_id, property_id, label_lang)
                    )
                """)
                
                # 관계 매핑 테이블
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS relationship_mappings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        db_name TEXT NOT NULL,
                        predicate TEXT NOT NULL,
                        label TEXT NOT NULL,
                        label_lang TEXT DEFAULT 'ko',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(db_name, predicate, label_lang)
                    )
                """)
                
                # 인덱스 생성 (쿼리 패턴에 최적화된 복합 인덱스)
                # 기존 인덱스 (레이블로 ID 찾기)
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_class_label ON class_mappings(db_name, label, label_lang)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_property_label ON property_mappings(db_name, class_id, label, label_lang)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_relationship_label ON relationship_mappings(db_name, label, label_lang)")
                
                # 배치 조회 최적화 인덱스 (ID로 레이블 찾기)
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_class_batch ON class_mappings(db_name, label_lang, class_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_property_batch ON property_mappings(db_name, class_id, label_lang, property_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_property_batch_all ON property_mappings(db_name, label_lang, class_id, property_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_relationship_batch ON relationship_mappings(db_name, label_lang, predicate)")
                
                await conn.commit()
                self._init_flag = True
    
    @asynccontextmanager
    async def _get_connection(self):
        """데이터베이스 연결 컨텍스트 매니저 (with connection pooling)"""
        conn = None
        try:
            conn = await aiosqlite.connect(self.db_path)
            conn.row_factory = aiosqlite.Row
            yield conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                await conn.close()
    
    async def register_class(self, db_name: str, class_id: str, 
                      label: Any, description: Optional[Any] = None) -> None:
        """
        클래스 레이블 매핑 등록
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            label: 클래스 레이블 (문자열 또는 MultiLingualText)
            description: 클래스 설명
        """
        # None 체크
        if not db_name or not class_id or not label:
            logger.warning(f"Invalid parameters: db_name={db_name}, class_id={class_id}, label={label}")
            return
            
        try:
            await self._init_database()
            async with self._get_connection() as conn:
                # 다국어 레이블 처리
                labels = self._extract_labels(label)
                descriptions = self._extract_labels(description) if description else {}
                
                # 트랜잭션 시작
                await conn.execute("BEGIN TRANSACTION")
                
                try:
                    for lang, label_text in labels.items():
                        desc_text = descriptions.get(lang, "")
                        
                        await conn.execute("""
                            INSERT OR REPLACE INTO class_mappings 
                            (db_name, class_id, label, label_lang, description, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (db_name, class_id, label_text, lang, desc_text, datetime.utcnow()))
                    
                    await conn.commit()
                    logger.info(f"Registered class mapping: {class_id} -> {labels}")
                    
                except Exception as e:
                    await conn.rollback()
                    raise
                    
        except Exception as e:
            logger.error(f"Failed to register class mapping: {e}")
            raise
    
    async def get_class_labels_in_batch(self, db_name: str, class_ids: List[str], 
                                        lang: str = 'ko') -> Dict[str, str]:
        """
        여러 클래스의 레이블을 한 번에 조회 (N+1 쿼리 문제 해결)
        
        Args:
            db_name: 데이터베이스 이름
            class_ids: 클래스 ID 목록
            lang: 언어 코드
            
        Returns:
            {class_id: label} 형태의 딕셔너리
        """
        if not class_ids:
            return {}
            
        await self._init_database()
        async with self._get_connection() as conn:
            # IN 절을 위한 placeholders 생성
            placeholders = ','.join(['?' for _ in class_ids])
            
            query = f"""
                SELECT class_id, label FROM class_mappings 
                WHERE db_name = ? AND label_lang = ? AND class_id IN ({placeholders})
            """
            
            params = [db_name, lang] + class_ids
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return {row['class_id']: row['label'] for row in rows}
    
    async def get_property_labels_in_batch(self, db_name: str, class_id: str, 
                                           property_ids: List[str], lang: str = 'ko') -> Dict[str, str]:
        """
        특정 클래스의 여러 속성 레이블을 한 번에 조회 (N+1 쿼리 문제 해결)
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            property_ids: 속성 ID 목록
            lang: 언어 코드
            
        Returns:
            {property_id: label} 형태의 딕셔너리
        """
        if not property_ids:
            return {}
            
        await self._init_database()
        async with self._get_connection() as conn:
            placeholders = ','.join(['?' for _ in property_ids])
            
            query = f"""
                SELECT property_id, label FROM property_mappings 
                WHERE db_name = ? AND class_id = ? AND label_lang = ? AND property_id IN ({placeholders})
            """
            
            params = [db_name, class_id, lang] + property_ids
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return {row['property_id']: row['label'] for row in rows}
    
    async def get_all_property_labels_in_batch(self, db_name: str, 
                                                class_property_pairs: List[Tuple[str, str]], 
                                                lang: str = 'ko') -> Dict[Tuple[str, str], str]:
        """
        여러 클래스의 여러 속성 레이블을 한 번의 쿼리로 조회 (N+1 쿼리 문제 완전 해결)
        
        Args:
            db_name: 데이터베이스 이름
            class_property_pairs: [(class_id, property_id)] 튜플 목록
            lang: 언어 코드
            
        Returns:
            {(class_id, property_id): label} 형태의 딕셔너리
        """
        if not class_property_pairs:
            return {}
            
        await self._init_database()
        async with self._get_connection() as conn:
            # WHERE 절을 위한 조건 생성
            conditions = []
            params = [db_name, lang]
            
            for class_id, property_id in class_property_pairs:
                conditions.append("(class_id = ? AND property_id = ?)")
                params.extend([class_id, property_id])
            
            query = f"""
                SELECT class_id, property_id, label FROM property_mappings 
                WHERE db_name = ? AND label_lang = ? AND ({' OR '.join(conditions)})
            """
            
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return {(row['class_id'], row['property_id']): row['label'] for row in rows}
    
    async def get_relationship_labels_in_batch(self, db_name: str, predicates: List[str], 
                                               lang: str = 'ko') -> Dict[str, str]:
        """
        여러 관계의 레이블을 한 번에 조회 (N+1 쿼리 문제 해결)
        
        Args:
            db_name: 데이터베이스 이름
            predicates: 관계 술어 목록
            lang: 언어 코드
            
        Returns:
            {predicate: label} 형태의 딕셔너리
        """
        if not predicates:
            return {}
            
        await self._init_database()
        async with self._get_connection() as conn:
            placeholders = ','.join(['?' for _ in predicates])
            
            query = f"""
                SELECT predicate, label FROM relationship_mappings 
                WHERE db_name = ? AND label_lang = ? AND predicate IN ({placeholders})
            """
            
            params = [db_name, lang] + predicates
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return {row['predicate']: row['label'] for row in rows}
    
    async def convert_to_display_batch(self, db_name: str, data_list: List[Dict[str, Any]], 
                                       lang: str = 'ko') -> List[Dict[str, Any]]:
        """
        여러 데이터를 한 번에 레이블 기반으로 변환 (N+1 쿼리 문제 해결)
        
        Args:
            db_name: 데이터베이스 이름
            data_list: 내부 ID 기반 데이터 목록
            lang: 언어 코드
            
        Returns:
            레이블 기반 데이터 목록
        """
        if not data_list:
            return []
        
        # 모든 클래스 ID 수집
        class_ids = []
        all_property_ids = set()
        all_predicates = set()
        
        for data in data_list:
            if 'id' in data:
                class_ids.append(data['id'])
            elif '@id' in data:
                class_ids.append(data['@id'])
            
            # 속성 ID 수집
            properties = data.get('properties', [])
            if isinstance(properties, dict):
                # OMS dict 형식 처리
                for prop_name, prop_type in properties.items():
                    if not prop_name.startswith('rdfs:') and prop_name not in ['@type', '@class']:
                        all_property_ids.add(prop_name)
            elif isinstance(properties, list):
                # 기존 list 형식 처리
                for prop in properties:
                    if isinstance(prop, dict) and 'name' in prop:
                        all_property_ids.add(prop['name'])
            
            # 관계 술어 수집
            for rel in data.get('relationships', []):
                if 'predicate' in rel:
                    all_predicates.add(rel['predicate'])
        
        # 배치 조회
        class_labels = await self.get_class_labels_in_batch(db_name, class_ids, lang)
        relationship_labels = await self.get_relationship_labels_in_batch(db_name, list(all_predicates), lang)
        
        # 모든 (class_id, property_id) 쌍 수집 (N+1 쿼리 문제 해결)
        all_class_property_pairs = []
        for data in data_list:
            class_id = data.get('id') or data.get('@id')
            if class_id:
                properties = data.get('properties', [])
                if isinstance(properties, dict):
                    # OMS dict 형식 처리
                    for prop_name, prop_type in properties.items():
                        if not prop_name.startswith('rdfs:') and prop_name not in ['@type', '@class']:
                            all_class_property_pairs.append((class_id, prop_name))
                elif isinstance(properties, list):
                    # 기존 list 형식 처리
                    for prop in properties:
                        if isinstance(prop, dict) and 'name' in prop:
                            all_class_property_pairs.append((class_id, prop['name']))
        
        # 한 번의 쿼리로 모든 속성 라벨 조회
        all_property_labels = await self.get_all_property_labels_in_batch(
            db_name, all_class_property_pairs, lang
        )
        
        # 데이터 변환
        labeled_data = []
        for data in data_list:
            display_data = data.copy()
            
            # 클래스 ID를 레이블로 변환
            class_id = data.get('id') or data.get('@id')
            if class_id and class_id in class_labels:
                if 'id' in data:
                    display_data['label'] = class_labels[class_id]
                elif '@id' in data:
                    display_data['@label'] = class_labels[class_id]
            
            # 속성들을 레이블로 변환
            if 'properties' in display_data and class_id:
                properties = display_data['properties']
                if isinstance(properties, dict):
                    # OMS dict 형식을 list로 변환하면서 레이블 추가
                    property_list = []
                    for prop_name, prop_type in properties.items():
                        if not prop_name.startswith('rdfs:') and prop_name not in ['@type', '@class']:
                            prop_info = {
                                'name': prop_name,
                                'type': prop_type if isinstance(prop_type, str) else prop_type.get('@class', 'xsd:string')
                            }
                            # 튜플 키로 속성 라벨 조회
                            label_key = (class_id, prop_name)
                            if label_key in all_property_labels:
                                prop_info['display_label'] = all_property_labels[label_key]
                            property_list.append(prop_info)
                    display_data['properties'] = property_list
                elif isinstance(properties, list):
                    # 기존 list 형식 처리
                    for prop in properties:
                        if isinstance(prop, dict) and 'name' in prop:
                            # 튜플 키로 속성 라벨 조회
                            label_key = (class_id, prop['name'])
                            if label_key in all_property_labels:
                                prop['display_label'] = all_property_labels[label_key]
            
            # 관계들을 레이블로 변환
            if 'relationships' in display_data:
                for rel in display_data['relationships']:
                    if 'predicate' in rel and rel['predicate'] in relationship_labels:
                        rel['display_label'] = relationship_labels[rel['predicate']]
            
            labeled_data.append(display_data)
        
        return labeled_data
    
    async def register_property(self, db_name: str, class_id: str, 
                         property_id: str, label: Any) -> None:
        """
        속성 레이블 매핑 등록
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            property_id: 속성 ID
            label: 속성 레이블
        """
        await self._init_database()
        async with self._get_connection() as conn:
            labels = self._extract_labels(label)
            
            for lang, label_text in labels.items():
                await conn.execute("""
                    INSERT OR REPLACE INTO property_mappings 
                    (db_name, class_id, property_id, label, label_lang, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (db_name, class_id, property_id, label_text, lang, datetime.utcnow()))
            
            await conn.commit()
            logger.info(f"Registered property mapping: {property_id} -> {labels}")
    
    async def register_relationship(self, db_name: str, predicate: str, label: Any) -> None:
        """
        관계 레이블 매핑 등록
        
        Args:
            db_name: 데이터베이스 이름
            predicate: 관계 술어
            label: 관계 레이블
        """
        await self._init_database()
        async with self._get_connection() as conn:
            labels = self._extract_labels(label)
            
            for lang, label_text in labels.items():
                await conn.execute("""
                    INSERT OR REPLACE INTO relationship_mappings 
                    (db_name, predicate, label, label_lang, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (db_name, predicate, label_text, lang, datetime.utcnow()))
            
            await conn.commit()
            logger.info(f"Registered relationship mapping: {predicate} -> {labels}")
    
    async def get_class_id(self, db_name: str, label: str, lang: str = 'ko') -> Optional[str]:
        """
        레이블로 클래스 ID 조회
        
        Args:
            db_name: 데이터베이스 이름
            label: 클래스 레이블
            lang: 언어 코드
            
        Returns:
            클래스 ID 또는 None
        """
        await self._init_database()
        async with self._get_connection() as conn:
            cursor = await conn.execute("""
                SELECT class_id FROM class_mappings 
                WHERE db_name = ? AND label = ? AND label_lang = ?
            """, (db_name, label, lang))
            
            row = await cursor.fetchone()
            return row['class_id'] if row else None
    
    async def get_class_label(self, db_name: str, class_id: str, lang: str = 'ko') -> Optional[str]:
        """
        클래스 ID로 레이블 조회
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            lang: 언어 코드
            
        Returns:
            클래스 레이블 또는 None
        """
        await self._init_database()
        async with self._get_connection() as conn:
            cursor = await conn.execute("""
                SELECT label FROM class_mappings 
                WHERE db_name = ? AND class_id = ? AND label_lang = ?
            """, (db_name, class_id, lang))
            
            row = await cursor.fetchone()
            return row['label'] if row else None
    
    async def get_property_id(self, db_name: str, class_id: str, 
                       label: str, lang: str = 'ko') -> Optional[str]:
        """
        레이블로 속성 ID 조회
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            label: 속성 레이블
            lang: 언어 코드
            
        Returns:
            속성 ID 또는 None
        """
        await self._init_database()
        async with self._get_connection() as conn:
            cursor = await conn.execute("""
                SELECT property_id FROM property_mappings 
                WHERE db_name = ? AND class_id = ? AND label = ? AND label_lang = ?
            """, (db_name, class_id, label, lang))
            
            row = await cursor.fetchone()
            return row['property_id'] if row else None
    
    async def get_predicate(self, db_name: str, label: str, lang: str = 'ko') -> Optional[str]:
        """
        레이블로 관계 술어 조회
        
        Args:
            db_name: 데이터베이스 이름
            label: 관계 레이블
            lang: 언어 코드
            
        Returns:
            관계 술어 또는 None
        """
        await self._init_database()
        async with self._get_connection() as conn:
            cursor = await conn.execute("""
                SELECT predicate FROM relationship_mappings 
                WHERE db_name = ? AND label = ? AND label_lang = ?
            """, (db_name, label, lang))
            
            row = await cursor.fetchone()
            return row['predicate'] if row else None
    
    async def convert_query_to_internal(self, db_name: str, query: Dict[str, Any], 
                                 lang: str = 'ko') -> Dict[str, Any]:
        """
        레이블 기반 쿼리를 내부 ID 기반으로 변환
        
        Args:
            db_name: 데이터베이스 이름
            query: 레이블 기반 쿼리
            lang: 언어 코드
            
        Returns:
            내부 ID 기반 쿼리
            
        Raises:
            ValueError: 레이블을 찾을 수 없는 경우
        """
        # 클래스 레이블을 ID로 변환
        class_label = query.get('class_label') or query.get('class')
        class_id = await self.get_class_id(db_name, class_label, lang)
        
        if not class_id:
            raise ValueError(f"클래스를 찾을 수 없습니다: {class_label}")
        
        internal_query = {
            'class_id': class_id,
            'filters': [],
            'select': query.get('select'),
            'limit': query.get('limit'),
            'offset': query.get('offset'),
            'order_by': query.get('order_by'),
            'order_direction': query.get('order_direction')
        }
        
        # 필터 변환
        for filter_item in query.get('filters', []):
            field_label = filter_item.get('field')
            
            # 속성 레이블을 ID로 변환
            property_id = await self.get_property_id(db_name, class_id, field_label, lang)
            if not property_id:
                # 관계일 수도 있으므로 확인
                predicate = await self.get_predicate(db_name, field_label, lang)
                if not predicate:
                    raise ValueError(f"필드를 찾을 수 없습니다: {field_label}")
                property_id = predicate
            
            internal_filter = {
                'field': property_id,
                'operator': filter_item.get('operator'),
                'value': filter_item.get('value')
            }
            internal_query['filters'].append(internal_filter)
        
        # SELECT 필드 변환
        if internal_query['select']:
            internal_select = []
            for field_label in internal_query['select']:
                property_id = await self.get_property_id(db_name, class_id, field_label, lang)
                if not property_id:
                    predicate = await self.get_predicate(db_name, field_label, lang)
                    if not predicate:
                        raise ValueError(f"SELECT 필드를 찾을 수 없습니다: {field_label}")
                    property_id = predicate
                internal_select.append(property_id)
            internal_query['select'] = internal_select
        
        # ORDER BY 필드 변환
        if internal_query['order_by']:
            order_field = internal_query['order_by']
            property_id = await self.get_property_id(db_name, class_id, order_field, lang)
            if not property_id:
                predicate = await self.get_predicate(db_name, order_field, lang)
                if not predicate:
                    raise ValueError(f"ORDER BY 필드를 찾을 수 없습니다: {order_field}")
                property_id = predicate
            internal_query['order_by'] = property_id
        
        return internal_query
    
    async def convert_to_display(self, db_name: str, data: Dict[str, Any], 
                          lang: str = 'ko') -> Dict[str, Any]:
        """
        내부 ID 기반 데이터를 레이블 기반으로 변환
        
        Args:
            db_name: 데이터베이스 이름
            data: 내부 ID 기반 데이터
            lang: 언어 코드
            
        Returns:
            레이블 기반 데이터
        """
        if not data:
            return data
        
        # 배치 처리를 사용하여 N+1 쿼리 문제 해결
        result = await self.convert_to_display_batch(db_name, [data], lang)
        return result[0] if result else data
    
    async def get_property_label(self, db_name: str, class_id: str, 
                           property_id: str, lang: str = 'ko') -> Optional[str]:
        """
        속성 ID로 레이블 조회 (공개 메서드)
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            property_id: 속성 ID
            lang: 언어 코드
            
        Returns:
            속성 레이블 또는 None
        """
        return await self._get_property_label(db_name, class_id, property_id, lang)
    
    async def _get_property_label(self, db_name: str, class_id: str, 
                           property_id: str, lang: str = 'ko') -> Optional[str]:
        """속성 ID로 레이블 조회 (내부 메서드)"""
        await self._init_database()
        async with self._get_connection() as conn:
            cursor = await conn.execute("""
                SELECT label FROM property_mappings 
                WHERE db_name = ? AND class_id = ? AND property_id = ? AND label_lang = ?
            """, (db_name, class_id, property_id, lang))
            
            row = await cursor.fetchone()
            return row['label'] if row else None
    
    async def _get_relationship_label(self, db_name: str, predicate: str, 
                               lang: str = 'ko') -> Optional[str]:
        """관계 술어로 레이블 조회"""
        await self._init_database()
        async with self._get_connection() as conn:
            cursor = await conn.execute("""
                SELECT label FROM relationship_mappings 
                WHERE db_name = ? AND predicate = ? AND label_lang = ?
            """, (db_name, predicate, lang))
            
            row = await cursor.fetchone()
            return row['label'] if row else None
    
    def _extract_labels(self, label: Any) -> Dict[str, str]:
        """
        레이블에서 언어별 텍스트 추출
        
        Args:
            label: 문자열 또는 MultiLingualText 또는 dict
            
        Returns:
            언어 코드를 키로 하는 딕셔너리
        """
        if label is None:
            return {}
            
        if isinstance(label, str):
            return {'ko': label} if label.strip() else {}  # 빈 문자열 체크
        
        if isinstance(label, dict):
            # MultiLingualText의 dict 형태
            return {k: str(v).strip() for k, v in label.items() if v and str(v).strip()}
        
        if hasattr(label, 'dict'):
            # Pydantic 모델
            try:
                return {k: str(v).strip() for k, v in label.dict().items() if v and str(v).strip()}
            except Exception as e:
                logger.warning(f"Failed to extract labels from Pydantic model: {e}")
                return {}
        
        # 기타 타입은 문자열로 변환
        try:
            label_str = str(label).strip()
            return {'ko': label_str} if label_str else {}
        except Exception as e:
            logger.warning(f"Failed to convert label to string: {e}")
            return {}
    
    async def update_mappings(self, db_name: str, ontology_data: Dict[str, Any]) -> None:
        """
        온톨로지 데이터로부터 모든 매핑 업데이트
        
        Args:
            db_name: 데이터베이스 이름
            ontology_data: 온톨로지 데이터
        """
        # 클래스 매핑 업데이트
        if 'id' in ontology_data and 'label' in ontology_data:
            await self.register_class(
                db_name,
                ontology_data['id'],
                ontology_data['label'],
                ontology_data.get('description')
            )
        
        # 속성 매핑 업데이트
        for prop in ontology_data.get('properties', []):
            if 'name' in prop and 'label' in prop:
                await self.register_property(
                    db_name,
                    ontology_data['id'],
                    prop['name'],
                    prop['label']
                )
        
        # 관계 매핑 업데이트
        for rel in ontology_data.get('relationships', []):
            if 'predicate' in rel and 'label' in rel:
                await self.register_relationship(
                    db_name,
                    rel['predicate'],
                    rel['label']
                )
    
    async def remove_class(self, db_name: str, class_id: str) -> None:
        """
        클래스 관련 모든 매핑 제거
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
        """
        await self._init_database()
        async with self._get_connection() as conn:
            # 클래스 매핑 삭제
            await conn.execute("""
                DELETE FROM class_mappings 
                WHERE db_name = ? AND class_id = ?
            """, (db_name, class_id))
            
            # 속성 매핑 삭제
            await conn.execute("""
                DELETE FROM property_mappings 
                WHERE db_name = ? AND class_id = ?
            """, (db_name, class_id))
            
            await conn.commit()
            logger.info(f"Removed all mappings for class: {class_id}")
    
    async def export_mappings(self, db_name: str) -> Dict[str, Any]:
        """
        특정 데이터베이스의 모든 매핑 내보내기
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            매핑 데이터
        """
        if not db_name:
            logger.warning("export_mappings called with empty db_name")
            return {
                'db_name': db_name,
                'classes': [],
                'properties': [],
                'relationships': [],
                'exported_at': datetime.utcnow().isoformat(),
                'error': 'Invalid database name'
            }
            
        try:
            await self._init_database()
            async with self._get_connection() as conn:
                # 클래스 매핑
                cursor = await conn.execute("""
                    SELECT * FROM class_mappings WHERE db_name = ?
                """, (db_name,))
                classes = [dict(row) for row in await cursor.fetchall()]
                
                # 속성 매핑
                cursor = await conn.execute("""
                    SELECT * FROM property_mappings WHERE db_name = ?
                """, (db_name,))
                properties = [dict(row) for row in await cursor.fetchall()]
                
                # 관계 매핑
                cursor = await conn.execute("""
                    SELECT * FROM relationship_mappings WHERE db_name = ?
                """, (db_name,))
                relationships = [dict(row) for row in await cursor.fetchall()]
                
                return {
                    'db_name': db_name,
                    'classes': classes,
                    'properties': properties,
                    'relationships': relationships,
                    'exported_at': datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to export mappings: {e}")
            return {
                'db_name': db_name,
                'classes': [],
                'properties': [],
                'relationships': [],
                'exported_at': datetime.utcnow().isoformat(),
                'error': str(e)
            }
    
    async def import_mappings(self, data: Dict[str, Any]) -> None:
        """
        매핑 데이터 가져오기
        
        Args:
            data: 매핑 데이터
        """
        if not data or not isinstance(data, dict):
            logger.error("Invalid mapping data provided")
            raise ValueError("Invalid mapping data")
            
        db_name = data.get('db_name')
        if not db_name:
            logger.error("No database name in import data")
            raise ValueError("Database name is required")
        
        imported_count = {'classes': 0, 'properties': 0, 'relationships': 0}
        errors = []
        
        # 클래스 매핑 가져오기
        for class_mapping in data.get('classes', []):
            try:
                if not class_mapping.get('class_id') or not class_mapping.get('label'):
                    logger.warning(f"Skipping invalid class mapping: {class_mapping}")
                    continue
                    
                await self.register_class(
                    db_name,
                    class_mapping['class_id'],
                    {class_mapping.get('label_lang', 'ko'): class_mapping['label']},
                    {class_mapping.get('label_lang', 'ko'): class_mapping.get('description', '')}
                )
                imported_count['classes'] += 1
            except Exception as e:
                error_msg = f"Failed to import class mapping {class_mapping.get('class_id', 'unknown')}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # 속성 매핑 가져오기
        for prop_mapping in data.get('properties', []):
            try:
                if not prop_mapping.get('property_id') or not prop_mapping.get('label'):
                    logger.warning(f"Skipping invalid property mapping: {prop_mapping}")
                    continue
                    
                await self.register_property(
                    db_name,
                    prop_mapping.get('class_id', ''),
                    prop_mapping['property_id'],
                    {prop_mapping.get('label_lang', 'ko'): prop_mapping['label']}
                )
                imported_count['properties'] += 1
            except Exception as e:
                error_msg = f"Failed to import property mapping {prop_mapping.get('property_id', 'unknown')}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # 관계 매핑 가져오기
        for rel_mapping in data.get('relationships', []):
            try:
                if not rel_mapping.get('predicate') or not rel_mapping.get('label'):
                    logger.warning(f"Skipping invalid relationship mapping: {rel_mapping}")
                    continue
                    
                await self.register_relationship(
                    db_name,
                    rel_mapping['predicate'],
                    {rel_mapping.get('label_lang', 'ko'): rel_mapping['label']}
                )
                imported_count['relationships'] += 1
            except Exception as e:
                error_msg = f"Failed to import relationship mapping {rel_mapping.get('predicate', 'unknown')}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        logger.info(f"Imported mappings for database: {db_name}. "
                   f"Classes: {imported_count['classes']}, "
                   f"Properties: {imported_count['properties']}, "
                   f"Relationships: {imported_count['relationships']}")
        
        if errors:
            logger.warning(f"Import completed with {len(errors)} errors")
            # 에러가 있어도 부분적 성공은 허용