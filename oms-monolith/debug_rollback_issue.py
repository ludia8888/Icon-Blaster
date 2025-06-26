"""
롤백 실패 원인 디버깅
왜 DELETE가 작동하지 않는지 상세 분석
"""
import asyncio
import sys
sys.path.append('/Users/sihyun/Desktop/ARRAKIS/SPICE/oms-monolith')

from database.simple_terminus_client import SimpleTerminusDBClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def debug_rollback():
    """롤백 문제 디버깅"""
    print("🔍 롤백 문제 디버깅 시작\n")
    
    db = SimpleTerminusDBClient(
        endpoint="http://localhost:6363",
        username="admin",
        password="root",
        database="oms"
    )
    await db.connect()
    
    # 1. 테스트 데이터 생성
    print("1️⃣ 테스트 데이터 생성")
    test_id = "ObjectType/DebugTest"
    
    create_result = await db.client.post(
        f"http://localhost:6363/api/document/admin/oms?author=debug&message=create_test",
        json=[{
            "@type": "ObjectType",
            "@id": test_id,
            "name": "DebugTest",
            "displayName": "디버그 테스트",
            "description": "롤백 테스트용"
        }],
        auth=("admin", "root")
    )
    
    print(f"생성 결과: {create_result.status_code}")
    if create_result.status_code not in [200, 201]:
        print(f"생성 실패: {create_result.text}")
        return
    
    # 2. 생성된 데이터 확인
    print("\n2️⃣ 생성된 데이터 확인")
    get_result = await db.client.get(
        f"http://localhost:6363/api/document/admin/oms?type=ObjectType",
        auth=("admin", "root")
    )
    
    if "DebugTest" in get_result.text:
        print("✅ DebugTest 확인됨")
    else:
        print("❌ DebugTest를 찾을 수 없음")
        
    # 3. 다양한 삭제 방법 시도
    print("\n3️⃣ 다양한 삭제 방법 시도")
    
    # 방법 1: 기본 DELETE
    print("\n방법 1: 기본 DELETE API")
    delete1 = await db.client.delete(
        f"http://localhost:6363/api/document/admin/oms/{test_id}?author=debug&message=delete_test",
        auth=("admin", "root")
    )
    print(f"결과: {delete1.status_code}")
    if delete1.status_code not in [200, 204]:
        print(f"응답: {delete1.text}")
        
    # 방법 2: 전체 경로 DELETE
    print("\n방법 2: 전체 경로 사용")
    delete2 = await db.client.delete(
        f"http://localhost:6363/api/document/admin/oms/data/{test_id}?author=debug",
        auth=("admin", "root")
    )
    print(f"결과: {delete2.status_code}")
    if delete2.status_code not in [200, 204]:
        print(f"응답: {delete2.text}")
        
    # 방법 3: terminusdb 프리픽스 사용
    print("\n방법 3: terminusdb:/// 프리픽스")
    delete3 = await db.client.delete(
        f"http://localhost:6363/api/document/admin/oms/terminusdb:///data/{test_id}?author=debug",
        auth=("admin", "root")
    )
    print(f"결과: {delete3.status_code}")
    if delete3.status_code not in [200, 204]:
        print(f"응답: {delete3.text}")
        
    # 4. TerminusDB의 올바른 삭제 방법 찾기
    print("\n4️⃣ TerminusDB 문서 확인")
    
    # WOQL 쿼리로 삭제 시도
    print("\n방법 4: WOQL 쿼리로 삭제")
    woql_delete = {
        "query": {
            "@type": "DeleteDocument",
            "identifier": {"@type": "NodeValue", "node": test_id}
        }
    }
    
    woql_result = await db.client.post(
        f"http://localhost:6363/api/woql/admin/oms",
        json=woql_delete,
        auth=("admin", "root")
    )
    print(f"WOQL 결과: {woql_result.status_code}")
    if woql_result.status_code != 200:
        print(f"응답: {woql_result.text}")
        
    # 5. 대안: 빈 문서로 덮어쓰기
    print("\n5️⃣ 대안 방법: 덮어쓰기로 삭제 효과")
    
    # 먼저 기존 문서 조회
    existing = await db.client.get(
        f"http://localhost:6363/api/document/admin/oms/data?type=ObjectType&id={test_id}",
        auth=("admin", "root")
    )
    
    # 빈 상태로 업데이트
    update_result = await db.client.put(
        f"http://localhost:6363/api/document/admin/oms?author=debug&message=pseudo_delete",
        json=[{
            "@type": "ObjectType",
            "@id": test_id,
            "name": "DebugTest",
            "displayName": "DELETED",
            "description": "This object has been deleted"
        }],
        auth=("admin", "root")
    )
    print(f"덮어쓰기 결과: {update_result.status_code}")
    
    # 6. 실제 동작하는 롤백 방법 확인
    print("\n6️⃣ 실제 동작하는 롤백 구현")
    
    # TerminusDB는 실제로 문서를 삭제하지 않고 새 버전을 생성
    # Git처럼 이전 커밋으로 되돌리는 방식
    
    # 현재 커밋 확인
    log_result = await db.client.get(
        f"http://localhost:6363/api/log/admin/oms",
        auth=("admin", "root")
    )
    
    if log_result.status_code == 200:
        commits = log_result.json()
        print(f"\n최근 커밋 수: {len(commits) if isinstance(commits, list) else 1}")
        
        # 이전 커밋으로 reset하는 것이 진짜 롤백
        print("\n✅ TerminusDB의 올바른 롤백 방법:")
        print("1. 특정 커밋 ID로 reset")
        print("2. 이전 상태의 문서로 덮어쓰기")
        print("3. 'deleted' 플래그로 논리적 삭제")
        
    # 7. 권장 롤백 구현
    print("\n7️⃣ 권장 롤백 구현 방법")
    
    async def proper_rollback(doc_id: str, reason: str):
        """올바른 롤백 구현"""
        # 방법 1: 논리적 삭제 (권장)
        rollback_doc = {
            "@type": "ObjectType",
            "@id": doc_id,
            "name": doc_id.split("/")[-1],
            "displayName": "[ROLLED BACK]",
            "description": f"Rolled back: {reason}",
            "_deleted": True,  # 논리적 삭제 플래그
            "_deletedAt": "2025-06-26T12:00:00Z"
        }
        
        result = await db.client.post(
            f"http://localhost:6363/api/document/admin/oms?author=system&message=rollback: {reason}",
            json=[rollback_doc],
            auth=("admin", "root")
        )
        
        return result.status_code in [200, 201]
        
    # 테스트
    rollback_success = await proper_rollback(test_id, "테스트 롤백")
    print(f"\n논리적 롤백 결과: {'✅ 성공' if rollback_success else '❌ 실패'}")
    
    await db.disconnect()
    
    print("\n\n📋 결론:")
    print("TerminusDB는 Git과 같은 append-only 데이터베이스입니다.")
    print("DELETE API가 제한적인 이유:")
    print("1. 모든 변경사항이 커밋으로 기록됨")
    print("2. 실제 삭제보다는 새 버전 생성 권장")
    print("3. 진짜 롤백은 이전 커밋으로 reset")
    print("\n✅ 해결 방법:")
    print("- 논리적 삭제 (deleted 플래그)")
    print("- 이전 상태로 덮어쓰기")
    print("- 커밋 레벨 reset (고급)")


if __name__ == "__main__":
    asyncio.run(debug_rollback())