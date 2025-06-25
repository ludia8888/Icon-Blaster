#!/usr/bin/env python3
"""
OMS API 엔드포인트 테스트
실제 FastAPI 서버를 통한 HTTP API 테스트
"""
import asyncio
import httpx
import json
from datetime import datetime

async def test_api_endpoints():
    """API 엔드포인트 테스트"""
    
    print("🌐 OMS API 엔드포인트 테스트 시작")
    print("=" * 50)
    
    base_url = "http://localhost:8001"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        
        # 1. Health Check
        print("\n📊 1. Health Check 테스트")
        try:
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                health_data = response.json()
                print(f"   ✅ Health Check: {health_data['status']}")
                print(f"   📋 서비스 상태:")
                for service, status in health_data.get('services', {}).items():
                    print(f"      {'✅' if status else '❌'} {service}: {'활성' if status else '비활성'}")
            else:
                print(f"   ❌ Health Check 실패: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Health Check 연결 실패: {e}")
        
        # 2. 루트 엔드포인트
        print("\n🏠 2. 루트 엔드포인트 테스트")
        try:
            response = await client.get(f"{base_url}/")
            if response.status_code == 200:
                root_data = response.json()
                print(f"   ✅ API 정보: {root_data.get('name', 'N/A')} v{root_data.get('version', 'N/A')}")
            else:
                print(f"   ❌ 루트 엔드포인트 실패: {response.status_code}")
        except Exception as e:
            print(f"   ❌ 루트 엔드포인트 연결 실패: {e}")
        
        # 3. 스키마 목록 조회
        print("\n📋 3. 스키마 목록 조회 테스트")
        try:
            response = await client.get(f"{base_url}/api/v1/schemas/main/object-types")
            if response.status_code == 200:
                schema_data = response.json()
                object_types = schema_data.get('objectTypes', [])
                print(f"   ✅ 스키마 목록 조회 성공: {len(object_types)}개 스키마")
                if object_types:
                    for obj_type in object_types[:3]:  # 처음 3개만 표시
                        print(f"      - {obj_type.get('name', 'N/A')}: {obj_type.get('displayName', 'N/A')}")
            else:
                print(f"   ❌ 스키마 목록 조회 실패: {response.status_code}")
        except Exception as e:
            print(f"   ❌ 스키마 목록 조회 연결 실패: {e}")
        
        # 4. 검증 API 테스트
        print("\n🔍 4. 검증 API 테스트")
        try:
            validation_request = {
                "branch": "main",
                "target_branch": "main",
                "include_impact_analysis": False,
                "include_warnings": True
            }
            
            response = await client.post(
                f"{base_url}/api/v1/validation/check",
                json=validation_request
            )
            
            if response.status_code == 200:
                validation_data = response.json()
                print(f"   ✅ 검증 API 성공: 유효성 {validation_data.get('is_valid', 'N/A')}")
                if validation_data.get('status') == 'mock_data':
                    print("   ℹ️ Mock 데이터 응답 (정상 동작)")
            else:
                print(f"   ❌ 검증 API 실패: {response.status_code}")
        except Exception as e:
            print(f"   ❌ 검증 API 연결 실패: {e}")
        
        # 5. 브랜치 생성 API 테스트
        print("\n🌿 5. 브랜치 생성 API 테스트")
        try:
            branch_request = {
                "name": f"test-branch-{datetime.now().strftime('%H%M%S')}",
                "parent": "main",
                "description": "API 테스트용 브랜치"
            }
            
            response = await client.post(
                f"{base_url}/api/v1/branches",
                json=branch_request
            )
            
            if response.status_code == 200:
                branch_data = response.json()
                print(f"   ✅ 브랜치 생성 성공: {branch_data.get('name', 'N/A')}")
                if branch_data.get('status') == 'mock_data':
                    print("   ℹ️ Mock 데이터 응답 (정상 동작)")
            else:
                print(f"   ❌ 브랜치 생성 실패: {response.status_code}")
        except Exception as e:
            print(f"   ❌ 브랜치 생성 연결 실패: {e}")
        
        # 6. 메트릭스 엔드포인트
        print("\n📈 6. 메트릭스 엔드포인트 테스트")
        try:
            response = await client.get(f"{base_url}/metrics")
            if response.status_code == 200:
                metrics_text = response.text
                metric_lines = [line for line in metrics_text.split('\n') if line and not line.startswith('#')]
                print(f"   ✅ 메트릭스 조회 성공: {len(metric_lines)}개 메트릭")
            else:
                print(f"   ❌ 메트릭스 조회 실패: {response.status_code}")
        except Exception as e:
            print(f"   ❌ 메트릭스 조회 연결 실패: {e}")
    
    print("\n" + "=" * 50)
    print("📊 API 테스트 완료")

async def main():
    """메인 실행 함수"""
    
    print("⚠️ 이 테스트를 실행하려면 별도 터미널에서 다음 명령을 실행하세요:")
    print("   python main_enterprise.py")
    print("   (또는 uvicorn main_enterprise:app --host 0.0.0.0 --port 8001)")
    print()
    
    input("OMS 서버가 실행 중이면 Enter를 눌러 계속하세요...")
    
    await test_api_endpoints()

if __name__ == "__main__":
    asyncio.run(main())