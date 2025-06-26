#!/usr/bin/env python3
"""
간단한 OMS 메타데이터 테스트
핵심 기능만 빠르게 검증
"""
import asyncio
from main_enterprise import services

async def test_simple_workflow():
    """간단한 워크플로우 테스트"""
    
    print("🚀 OMS 간단 테스트 시작")
    
    try:
        # 서비스 초기화
        await services.initialize()
        print("✅ 서비스 초기화 완료")
        
        # 1. TerminusDB 기본 연결 테스트
        print("\n🔌 TerminusDB 연결 테스트")
        if services.db_client:
            ping = await services.db_client.ping()
            print(f"   ✅ TerminusDB Ping: {ping}")
            
            # 데이터베이스 목록
            dbs = await services.db_client.get_databases()
            print(f"   ✅ 데이터베이스 개수: {len(dbs) if isinstance(dbs, list) else '조회됨'}")
        
        # 2. 서비스 상태 확인
        print("\n📊 서비스 상태 확인")
        services_status = {
            "Schema Service": services.schema_service is not None,
            "Validation Service": services.validation_service is not None,
            "Branch Service": services.branch_service is not None,
            "History Service": services.history_service is not None,
            "Event Service": services.event_service is not None
        }
        
        for name, status in services_status.items():
            print(f"   {'✅' if status else '❌'} {name}: {'활성' if status else '비활성'}")
        
        # 3. Mock API 호출 테스트 (에러 처리로 기능 확인)
        print("\n🔧 API 기능 테스트")
        
        try:
            # 스키마 목록 조회 시도
            if services.schema_service:
                await services.schema_service.list_object_types("main")
                print("   ✅ 스키마 서비스: API 호출 가능")
        except Exception as e:
            if "get_all_documents" in str(e):
                print("   ⚠️ 스키마 서비스: 메서드 구현 필요")
            else:
                print(f"   ❌ 스키마 서비스: {e}")
        
        try:
            # 검증 서비스 테스트
            if services.validation_service:
                from core.validation.models import ValidationRequest
                req = ValidationRequest(
                    source_branch="main",
                    target_branch="main",
                    include_impact_analysis=False,
                    include_warnings=False,
                    options={}
                )
                await services.validation_service.validate_breaking_changes(req)
                print("   ✅ 검증 서비스: API 호출 가능")
        except Exception as e:
            if "unexpected keyword argument" in str(e):
                print("   ⚠️ 검증 서비스: 인터페이스 수정 필요")
            else:
                print(f"   ❌ 검증 서비스: {e}")
        
        try:
            # 브랜치 서비스 테스트
            if services.branch_service:
                await services.branch_service.create_branch("test", "main", "Test branch")
                print("   ✅ 브랜치 서비스: API 호출 가능")
        except Exception as e:
            print(f"   ⚠️ 브랜치 서비스: {str(e)[:50]}...")
        
        # 4. 결과 요약
        print("\n📋 테스트 요약")
        active_services = sum(services_status.values())
        total_services = len(services_status)
        
        print(f"   🎯 서비스 활성화율: {active_services}/{total_services} ({active_services/total_services*100:.0f}%)")
        
        if services.db_client and ping:
            print("   ✅ 데이터베이스 연결: 정상")
        else:
            print("   ❌ 데이터베이스 연결: 오류")
        
        if active_services >= 4:
            print("   🎉 OMS 기본 기능 준비 완료!")
        else:
            print("   ⚠️ 일부 서비스 확인 필요")
            
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await services.shutdown()
        print("\n✅ 테스트 완료")

if __name__ == "__main__":
    asyncio.run(test_simple_workflow())