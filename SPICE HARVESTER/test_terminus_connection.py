#!/usr/bin/env python3
"""
TerminusDB 연결 테스트 스크립트
"""

import asyncio
import sys
import os

# 경로 설정
sys.path.insert(0, '/Users/isihyeon/Desktop/SPICE FOUNDRY/ontology-management-service')
sys.path.insert(0, '/Users/isihyeon/Desktop/SPICE FOUNDRY/shared')

from services.async_terminus import AsyncTerminusService, AsyncConnectionInfo

async def test_terminus_connection():
    """TerminusDB 연결 테스트"""
    print("=== TerminusDB 연결 테스트 시작 ===")
    
    # 연결 정보 설정
    connection_info = AsyncConnectionInfo(
        server_url="http://localhost:6363",
        user="admin",
        account="admin",
        key="root"
    )
    
    service = AsyncTerminusService(connection_info)
    
    try:
        print("1. TerminusDB 연결 시도...")
        await service.connect()
        print("✓ TerminusDB 연결 성공")
        
        print("\n2. 연결 상태 확인...")
        is_connected = await service.check_connection()
        print(f"✓ 연결 상태: {'연결됨' if is_connected else '연결 안됨'}")
        
        print("\n3. 데이터베이스 목록 조회...")
        databases = await service.list_databases()
        print(f"✓ 데이터베이스 목록: {databases}")
        
        print("\n4. 테스트 데이터베이스 생성...")
        test_db = "test_ontology_db"
        if await service.database_exists(test_db):
            print(f"✓ 테스트 데이터베이스 '{test_db}' 이미 존재")
        else:
            await service.create_database(test_db, "테스트용 온톨로지 데이터베이스")
            print(f"✓ 테스트 데이터베이스 '{test_db}' 생성 완료")
        
        print("\n5. 테스트 온톨로지 생성...")
        test_ontology = {
            "@id": "Person",
            "@type": "Class",
            "rdfs:label": {"@value": "사람", "@language": "ko"},
            "rdfs:comment": {"@value": "사람 클래스", "@language": "ko"}
        }
        
        result = await service.create_ontology(test_db, test_ontology)
        print(f"✓ 테스트 온톨로지 생성 완료: {result}")
        
        print("\n6. 온톨로지 조회...")
        retrieved = await service.get_ontology(test_db, "Person")
        print(f"✓ 온톨로지 조회 완료: {retrieved}")
        
        print("\n7. 온톨로지 목록 조회...")
        ontologies = await service.list_ontologies(test_db)
        print(f"✓ 온톨로지 목록: {len(ontologies)}개")
        
        print("\n=== 모든 테스트 성공! ===")
        
    except Exception as e:
        print(f"✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("\n8. 연결 종료...")
        await service.disconnect()
        print("✓ 연결 종료 완료")

if __name__ == "__main__":
    asyncio.run(test_terminus_connection())