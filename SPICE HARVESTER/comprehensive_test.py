#!/usr/bin/env python3
"""
전체 시스템 검증 스크립트
모든 기능이 실제로 작동하는지 철저하게 검증
"""

import sys
import os
import asyncio
import traceback
from pathlib import Path

# 경로 설정
base_dir = Path('/Users/isihyeon/Desktop/SPICE HARVESTER/backend')
sys.path.insert(0, str(base_dir / 'ontology-management-service'))
sys.path.insert(0, str(base_dir / 'backend-for-frontend'))
sys.path.insert(0, str(base_dir / 'shared'))

class ComprehensiveTest:
    def __init__(self):
        self.test_results = []
        self.failed_tests = []
        
    def log_test(self, test_name, status, message=""):
        """테스트 결과 로깅"""
        status_symbol = "✓" if status else "✗"
        print(f"{status_symbol} {test_name}: {message}")
        self.test_results.append({
            'test': test_name,
            'status': status,
            'message': message
        })
        if not status:
            self.failed_tests.append(test_name)
    
    def test_imports(self):
        """모든 import 경로 테스트"""
        print("\n=== 1. IMPORT 경로 검증 ===")
        
        # Shared models 테스트
        try:
            from models.ontology import (
                OntologyCreateRequest, 
                OntologyUpdateRequest, 
                OntologyResponse,
                QueryRequest,
                QueryResponse,
                MultiLingualText
            )
            from models.common import BaseResponse
            self.log_test("Shared models import", True)
        except Exception as e:
            self.log_test("Shared models import", False, str(e))
        
        # Shared utils 테스트
        try:
            from utils.jsonld import JSONToJSONLDConverter
            from utils.retry import retry, CircuitBreaker
            self.log_test("Shared utils import", True)
        except Exception as e:
            self.log_test("Shared utils import", False, str(e))
        
        # OMS services 테스트
        try:
            from services.async_terminus import AsyncTerminusService, AsyncConnectionInfo
            self.log_test("OMS async_terminus import", True)
        except Exception as e:
            self.log_test("OMS async_terminus import", False, str(e))
        
        # BFF services 테스트
        try:
            from services.oms_client import OMSClient
            self.log_test("BFF oms_client import", True)
        except Exception as e:
            self.log_test("BFF oms_client import", False, str(e))
        
        # BFF utils 테스트
        try:
            # BFF utils 경로 추가
            bff_utils_path = str(base_dir / 'backend-for-frontend' / 'utils')
            if bff_utils_path not in sys.path:
                sys.path.insert(0, bff_utils_path)
            from label_mapper import LabelMapper
            self.log_test("BFF label_mapper import", True)
        except Exception as e:
            self.log_test("BFF label_mapper import", False, str(e))
    
    def test_model_creation(self):
        """모델 생성 테스트"""
        print("\n=== 2. 모델 생성 검증 ===")
        
        try:
            from models.ontology import OntologyCreateRequest, MultiLingualText
            
            # 다국어 텍스트 생성
            multilingual_label = MultiLingualText(
                ko="사람",
                en="Person"
            )
            
            # 온톨로지 생성 요청 모델 생성
            ontology_request = OntologyCreateRequest(
                id="Person",
                label=multilingual_label,
                description=MultiLingualText(ko="사람을 나타내는 클래스"),
                properties=[],
                relationships=[]
            )
            
            self.log_test("OntologyCreateRequest model creation", True)
            
            # 모델 직렬화 테스트
            request_dict = ontology_request.model_dump()
            self.log_test("Model serialization", True, f"ID: {request_dict['id']}")
            
        except Exception as e:
            self.log_test("Model creation", False, str(e))
    
    def test_jsonld_converter(self):
        """JSON-LD 변환기 테스트"""
        print("\n=== 3. JSON-LD 변환기 검증 ===")
        
        try:
            from utils.jsonld import JSONToJSONLDConverter
            
            converter = JSONToJSONLDConverter()
            
            # 테스트 데이터
            test_data = {
                "id": "Person",
                "label": {"ko": "사람", "en": "Person"},
                "description": {"ko": "사람을 나타내는 클래스"},
                "properties": [
                    {
                        "name": "name",
                        "type": "string",
                        "label": {"ko": "이름", "en": "Name"}
                    }
                ]
            }
            
            # JSON-LD 변환
            jsonld_result = converter.convert_with_labels(test_data)
            self.log_test("JSON to JSON-LD conversion", True, f"@type: {jsonld_result.get('@type')}")
            
            # 역변환 테스트
            extracted = converter.extract_from_jsonld(jsonld_result)
            self.log_test("JSON-LD to JSON extraction", True, f"ID: {extracted.get('id')}")
            
        except Exception as e:
            self.log_test("JSON-LD converter", False, str(e))
    
    async def test_oms_client(self):
        """OMS 클라이언트 테스트"""
        print("\n=== 4. OMS 클라이언트 검증 ===")
        
        try:
            from services.oms_client import OMSClient
            
            # 클라이언트 생성
            client = OMSClient("http://localhost:8001")
            self.log_test("OMS client creation", True)
            
            # 헬스 체크 (서버가 실행되지 않을 것이므로 실패 예상)
            try:
                is_healthy = await client.check_health()
                self.log_test("OMS client health check", is_healthy, "Server running" if is_healthy else "Server not running")
            except Exception as e:
                self.log_test("OMS client health check", False, "Expected: Server not running")
            
            await client.close()
            self.log_test("OMS client cleanup", True)
            
        except Exception as e:
            self.log_test("OMS client test", False, str(e))
    
    async def test_async_terminus_service(self):
        """AsyncTerminusService 테스트"""
        print("\n=== 5. AsyncTerminusService 검증 ===")
        
        try:
            from services.async_terminus import AsyncTerminusService, AsyncConnectionInfo
            
            # 연결 정보 생성
            connection_info = AsyncConnectionInfo(
                server_url="http://localhost:6363",
                user="admin",
                account="admin",
                key="admin123"
            )
            
            service = AsyncTerminusService(connection_info)
            self.log_test("AsyncTerminusService creation", True)
            
            # 연결 시도 (TerminusDB가 실행되지 않을 것이므로 실패 예상)
            try:
                await service.connect()
                self.log_test("TerminusDB connection", True, "Connected successfully")
            except Exception as e:
                self.log_test("TerminusDB connection", False, "Expected: TerminusDB not running")
            
            await service.disconnect()
            self.log_test("AsyncTerminusService cleanup", True)
            
        except Exception as e:
            self.log_test("AsyncTerminusService test", False, str(e))
    
    async def test_label_mapper(self):
        """LabelMapper 테스트"""
        print("\n=== 6. LabelMapper 검증 ===")
        
        try:
            # BFF utils 경로 추가
            bff_utils_path = str(base_dir / 'backend-for-frontend' / 'utils')
            if bff_utils_path not in sys.path:
                sys.path.insert(0, bff_utils_path)
            from label_mapper import LabelMapper
            
            # LabelMapper 생성
            mapper = LabelMapper()
            self.log_test("LabelMapper creation", True)
            
            # 테스트 데이터베이스에 클래스 등록
            test_db = "test_db"
            await mapper.register_class(
                db_name=test_db,
                class_id="Person",
                label={"ko": "사람", "en": "Person"},
                description={"ko": "사람을 나타내는 클래스"}
            )
            self.log_test("LabelMapper class registration", True)
            
            # 클래스 ID 조회
            class_id = await mapper.get_class_id(test_db, "사람", "ko")
            self.log_test("LabelMapper class ID lookup", class_id == "Person", f"Found ID: {class_id}")
            
        except Exception as e:
            self.log_test("LabelMapper test", False, str(e))
    
    def test_fastapi_app_creation(self):
        """FastAPI 앱 생성 테스트"""
        print("\n=== 7. FastAPI 앱 생성 검증 ===")
        
        try:
            # OMS 앱 생성 테스트
            sys.path.insert(0, str(base_dir / 'ontology-management-service'))
            from main import app as oms_app
            self.log_test("OMS FastAPI app creation", True, f"App title: {oms_app.title}")
            
        except Exception as e:
            self.log_test("OMS FastAPI app creation", False, str(e))
        
        try:
            # BFF 앱 생성 테스트
            sys.path.insert(0, str(base_dir / 'backend-for-frontend'))
            from main import app as bff_app
            self.log_test("BFF FastAPI app creation", True, f"App title: {bff_app.title}")
            
        except Exception as e:
            self.log_test("BFF FastAPI app creation", False, str(e))
    
    def test_router_imports(self):
        """라우터 import 테스트"""
        print("\n=== 8. 라우터 Import 검증 ===")
        
        try:
            sys.path.insert(0, str(base_dir / 'ontology-management-service'))
            from routers import database, ontology
            self.log_test("OMS routers import", True)
        except Exception as e:
            self.log_test("OMS routers import", False, str(e))
    
    def check_file_structure(self):
        """파일 구조 검증"""
        print("\n=== 9. 파일 구조 검증 ===")
        
        required_files = [
            'shared/models/ontology.py',
            'shared/models/common.py',
            'shared/utils/jsonld.py',
            'shared/utils/retry.py',
            'ontology-management-service/main.py',
            'ontology-management-service/services/async_terminus.py',
            'ontology-management-service/routers/database.py',
            'ontology-management-service/routers/ontology.py',
            'backend-for-frontend/main.py',
            'backend-for-frontend/services/oms_client.py',
            'backend-for-frontend/utils/label_mapper.py'
        ]
        
        for file_path in required_files:
            full_path = base_dir / file_path
            exists = full_path.exists()
            self.log_test(f"File exists: {file_path}", exists)
    
    def check_duplicate_removal(self):
        """중복 제거 검증"""
        print("\n=== 10. 중복 제거 검증 ===")
        
        # JSONToJSONLDConverter 중복 확인
        jsonld_files = list(base_dir.rglob("**/jsonld.py"))
        shared_jsonld_exists = any("shared/utils/jsonld.py" in str(f) for f in jsonld_files)
        
        duplicate_jsonld = [f for f in jsonld_files if "shared/utils/jsonld.py" not in str(f)]
        
        self.log_test("Shared JSONToJSONLDConverter exists", shared_jsonld_exists)
        self.log_test("No duplicate JSONToJSONLDConverter", len(duplicate_jsonld) == 0, 
                     f"Duplicates found: {[str(f) for f in duplicate_jsonld]}")
    
    async def run_all_tests(self):
        """모든 테스트 실행"""
        print("🔥 ULTRA CRITICAL 전체 시스템 검증 시작 🔥")
        print("=" * 60)
        
        # 동기 테스트
        self.test_imports()
        self.test_model_creation()
        self.test_jsonld_converter()
        self.test_fastapi_app_creation()
        self.test_router_imports()
        self.check_file_structure()
        self.check_duplicate_removal()
        
        # 비동기 테스트
        await self.test_oms_client()
        await self.test_async_terminus_service()
        await self.test_label_mapper()
        
        # 결과 요약
        print("\n" + "=" * 60)
        print("📊 테스트 결과 요약")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r['status']])
        failed_tests = len(self.failed_tests)
        
        print(f"총 테스트: {total_tests}")
        print(f"성공: {passed_tests}")
        print(f"실패: {failed_tests}")
        
        if failed_tests > 0:
            print(f"\n❌ 실패한 테스트:")
            for test in self.failed_tests:
                print(f"  - {test}")
        
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        print(f"\n성공률: {success_rate:.1f}%")
        
        if success_rate >= 90:
            print("🎉 대부분의 기능이 정상적으로 작동합니다!")
        elif success_rate >= 70:
            print("⚠️ 일부 기능에 문제가 있습니다.")
        else:
            print("🚨 많은 기능에 문제가 있습니다.")

async def main():
    """메인 함수"""
    test = ComprehensiveTest()
    await test.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())