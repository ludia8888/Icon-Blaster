"""실제 TerminusDB 연결 및 데이터 작업 테스트"""
import asyncio
import sys
sys.path.append('/Users/sihyun/Desktop/ARRAKIS/SPICE/oms-monolith')

from database.simple_terminus_client import SimpleTerminusDBClient

async def test_real_terminus():
    print("🔍 Real TerminusDB Connection Test")
    
    # SimpleTerminusDBClient 사용 - admin으로 인증
    client = SimpleTerminusDBClient(
        endpoint="http://localhost:6363",
        username="admin",
        password="root",  # Docker에서 설정한 비밀번호
        database="oms"
    )
    
    # 1. 연결 테스트
    connected = await client.connect()
    print(f"✅ Connection: {'SUCCESS' if connected else 'FAILED'}")
    
    if not connected:
        return
    
    # 2. 실제 데이터 삽입 테스트
    test_object = {
        "@type": "ObjectType",
        "@id": "TestObject",
        "name": "TestObject",
        "displayName": "Test Object",
        "description": "Real test object in TerminusDB",
        "properties": [
            {
                "@type": "Property",
                "@id": "TestObject_name",
                "name": "name",
                "dataType": "string",
                "required": True
            }
        ]
    }
    
    insert_result = await client.insert_document(test_object, doc_id="TestObject")
    print(f"✅ Insert Document: {'SUCCESS' if insert_result else 'FAILED'}")
    
    # 3. 데이터 조회 테스트
    retrieved = await client.get_document("TestObject")
    print(f"✅ Retrieve Document: {'SUCCESS' if retrieved else 'FAILED'}")
    if retrieved:
        print(f"   Retrieved data: {retrieved.get('name', 'No name')}")
    
    # 4. 모든 문서 목록 조회
    all_docs = await client.list_all_documents()
    print(f"✅ List All Documents: Found {len(all_docs)} documents")
    
    await client.disconnect()
    print("\n🎉 Real TerminusDB test completed!")

if __name__ == "__main__":
    asyncio.run(test_real_terminus())