#!/usr/bin/env python3
"""
Critical Functionality Test - 핵심 기능 실제 동작 검증
think ultra: 절대 mock/fake 없이 실제 API 호출로 모든 기능 검증

실제 프로덕션 시나리오:
1. 데이터베이스 생성/관리
2. 온톨로지 CRUD 작업
3. 보안 입력 검증
4. 에러 처리 및 상태 코드
5. 다국어 레이블 매핑
6. 버전 관리 (브랜치/커밋)
"""

import asyncio
import httpx
import json
import time
from datetime import datetime
from test_config import TestConfig


class CriticalFunctionalityTest:
    """핵심 기능 실제 동작 테스트"""
    
    def __init__(self):
        self.oms_url = TestConfig.get_oms_base_url()
        self.bff_url = TestConfig.get_bff_base_url()
        self.test_db = f"{TestConfig.get_test_db_prefix()}critical_{int(time.time())}"
        self.test_results = []
        self.security_test_results = []
        
    async def run_all_critical_tests(self):
        """모든 핵심 테스트 실행"""
        print("🚀 핵심 기능 실제 동작 검증 시작 (think ultra)")
        print("="*60)
        
        try:
            # 1. 서비스 연결 테스트
            await self._test_service_connectivity()
            
            # 2. 데이터베이스 관리 테스트
            await self._test_database_management()
            
            # 3. 온톨로지 CRUD 테스트
            await self._test_ontology_crud()
            
            # 4. 보안 입력 검증 테스트
            await self._test_security_validation()
            
            # 5. 에러 처리 테스트
            await self._test_error_handling()
            
            # 6. 다국어 지원 테스트
            await self._test_multilingual_support()
            
            # 7. URL 정렬 확인 테스트
            await self._test_url_alignment()
            
            # 결과 출력
            self._print_test_results()
            
        except Exception as e:
            print(f"💥 테스트 중 예외 발생: {e}")
        finally:
            # 정리
            await self._cleanup()
    
    async def _test_service_connectivity(self):
        """서비스 연결 테스트"""
        print("\n🔗 서비스 연결 테스트")
        
        async with httpx.AsyncClient(timeout=30) as client:
            # OMS 헬스체크
            try:
                response = await client.get(f"{self.oms_url}/health")
                if response.status_code == 200:
                    health_data = response.json()
                    print(f"  ✅ OMS: {health_data}")
                    self.test_results.append(("OMS Health", "PASS", health_data))
                else:
                    print(f"  ❌ OMS: {response.status_code}")
                    self.test_results.append(("OMS Health", "FAIL", f"Status: {response.status_code}"))
            except Exception as e:
                print(f"  💥 OMS 연결 실패: {e}")
                self.test_results.append(("OMS Health", "ERROR", str(e)))
            
            # BFF 헬스체크
            try:
                response = await client.get(f"{self.bff_url}/api/v1/health")
                if response.status_code == 200:
                    health_data = response.json()
                    print(f"  ✅ BFF: {health_data}")
                    self.test_results.append(("BFF Health", "PASS", health_data))
                else:
                    print(f"  ❌ BFF: {response.status_code}")
                    self.test_results.append(("BFF Health", "FAIL", f"Status: {response.status_code}"))
            except Exception as e:
                print(f"  💥 BFF 연결 실패: {e}")
                self.test_results.append(("BFF Health", "ERROR", str(e)))
    
    async def _test_database_management(self):
        """데이터베이스 관리 테스트"""
        print("\n💾 데이터베이스 관리 테스트")
        
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. 데이터베이스 생성
            try:
                response = await client.post(
                    f"{self.oms_url}/api/v1/database/create",
                    json={"name": self.test_db, "description": "Critical test database"}
                )
                if response.status_code == 200:
                    print(f"  ✅ DB 생성 성공: {self.test_db}")
                    self.test_results.append(("DB Creation", "PASS", self.test_db))
                else:
                    print(f"  ❌ DB 생성 실패: {response.status_code} - {response.text}")
                    self.test_results.append(("DB Creation", "FAIL", response.text))
            except Exception as e:
                print(f"  💥 DB 생성 예외: {e}")
                self.test_results.append(("DB Creation", "ERROR", str(e)))
            
            # 2. 중복 데이터베이스 생성 시도 (409 Conflict 확인)
            try:
                response = await client.post(
                    f"{self.oms_url}/api/v1/database/create",
                    json={"name": self.test_db}
                )
                if response.status_code == 409:
                    print(f"  ✅ 중복 DB 방지 동작: 409 Conflict")
                    self.test_results.append(("DB Duplicate Prevention", "PASS", "409 returned"))
                else:
                    print(f"  ❌ 중복 DB 방지 실패: {response.status_code}")
                    self.test_results.append(("DB Duplicate Prevention", "FAIL", f"Status: {response.status_code}"))
            except Exception as e:
                self.test_results.append(("DB Duplicate Prevention", "ERROR", str(e)))
            
            # 3. 데이터베이스 목록 조회
            try:
                response = await client.get(f"{self.oms_url}/api/v1/database/list")
                if response.status_code == 200:
                    db_list = response.json()
                    databases = db_list.get("data", {}).get("databases", [])
                    
                    # Check if test database exists in the list
                    # Handle both string and dict formats
                    found = False
                    for db in databases:
                        if isinstance(db, str) and db == self.test_db:
                            found = True
                            break
                        elif isinstance(db, dict) and db.get("name") == self.test_db:
                            found = True
                            break
                    
                    if found:
                        print(f"  ✅ DB 목록에서 확인됨: {self.test_db}")
                        self.test_results.append(("DB List", "PASS", "Found in list"))
                    else:
                        print(f"  ❌ DB 목록에서 누락: {self.test_db}")
                        self.test_results.append(("DB List", "FAIL", "Not found in list"))
                else:
                    print(f"  ❌ DB 목록 조회 실패: {response.status_code}")
                    self.test_results.append(("DB List", "FAIL", f"Status: {response.status_code}"))
            except Exception as e:
                self.test_results.append(("DB List", "ERROR", str(e)))
            
            # 4. 데이터베이스 존재 확인
            try:
                response = await client.get(f"{self.oms_url}/api/v1/database/exists/{self.test_db}")
                if response.status_code == 200:
                    print(f"  ✅ DB 존재 확인: {self.test_db}")
                    self.test_results.append(("DB Exists Check", "PASS", "Confirmed exists"))
                else:
                    print(f"  ❌ DB 존재 확인 실패: {response.status_code}")
                    self.test_results.append(("DB Exists Check", "FAIL", f"Status: {response.status_code}"))
            except Exception as e:
                self.test_results.append(("DB Exists Check", "ERROR", str(e)))
    
    async def _test_ontology_crud(self):
        """온톨로지 CRUD 테스트"""
        print("\n🧠 온톨로지 CRUD 테스트")
        
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. 온톨로지 생성 (correct schema format)
            test_ontology = {
                "id": "TestProduct",
                "label": "테스트 제품",
                "description": "Critical test ontology",
                "properties": [
                    {"name": "name", "type": "xsd:string", "label": "Name"},
                    {"name": "price", "type": "xsd:decimal", "label": "Price"},
                    {"name": "category", "type": "xsd:string", "label": "Category"}
                ]
            }
            
            try:
                response = await client.post(
                    f"{self.oms_url}/api/v1/ontology/{self.test_db}/create",
                    json=test_ontology
                )
                if response.status_code == 200:
                    print(f"  ✅ 온톨로지 생성 성공: TestProduct")
                    self.test_results.append(("Ontology Creation", "PASS", "TestProduct created"))
                else:
                    print(f"  ❌ 온톨로지 생성 실패: {response.status_code} - {response.text}")
                    self.test_results.append(("Ontology Creation", "FAIL", response.text))
            except Exception as e:
                print(f"  💥 온톨로지 생성 예외: {e}")
                self.test_results.append(("Ontology Creation", "ERROR", str(e)))
            
            # 2. 온톨로지 조회
            try:
                response = await client.get(f"{self.oms_url}/api/v1/ontology/{self.test_db}/TestProduct")
                if response.status_code == 200:
                    ontology_data = response.json()
                    print(f"  ✅ 온톨로지 조회 성공: {ontology_data.get('data', {}).get('id', 'Unknown')}")
                    self.test_results.append(("Ontology Read", "PASS", "TestProduct retrieved"))
                else:
                    print(f"  ❌ 온톨로지 조회 실패: {response.status_code}")
                    self.test_results.append(("Ontology Read", "FAIL", f"Status: {response.status_code}"))
            except Exception as e:
                self.test_results.append(("Ontology Read", "ERROR", str(e)))
            
            # 3. 온톨로지 목록 조회
            try:
                response = await client.get(f"{self.oms_url}/api/v1/ontology/{self.test_db}/list")
                if response.status_code == 200:
                    ontology_list = response.json()
                    count = ontology_list.get("data", {}).get("count", 0)
                    print(f"  ✅ 온톨로지 목록 조회: {count}개")
                    self.test_results.append(("Ontology List", "PASS", f"{count} ontologies"))
                else:
                    print(f"  ❌ 온톨로지 목록 조회 실패: {response.status_code}")
                    self.test_results.append(("Ontology List", "FAIL", f"Status: {response.status_code}"))
            except Exception as e:
                self.test_results.append(("Ontology List", "ERROR", str(e)))
            
            # 4. 잘못된 속성 타입으로 온톨로지 생성 시도 (400 확인)
            invalid_ontology = {
                "id": "InvalidOntology",
                "label": "Invalid Test",
                "properties": [
                    {"name": "bad_prop", "type": "invalid:type", "label": "Bad Property"}
                ]
            }
            
            try:
                response = await client.post(
                    f"{self.oms_url}/api/v1/ontology/{self.test_db}/create",
                    json=invalid_ontology
                )
                if response.status_code == 400:
                    print(f"  ✅ 잘못된 속성 타입 차단: 400 Bad Request")
                    self.test_results.append(("Invalid Property Type", "PASS", "400 returned"))
                else:
                    print(f"  ❌ 잘못된 속성 타입 허용됨: {response.status_code}")
                    self.test_results.append(("Invalid Property Type", "FAIL", f"Status: {response.status_code}"))
            except Exception as e:
                self.test_results.append(("Invalid Property Type", "ERROR", str(e)))
    
    async def _test_security_validation(self):
        """보안 입력 검증 테스트"""
        print("\n🛡️ 보안 입력 검증 테스트")
        
        # 악성 입력 패턴들
        malicious_inputs = [
            "test'; DROP TABLE users; --",  # SQL Injection
            "<script>alert('xss')</script>",  # XSS
            "../../../etc/passwd",  # Path Traversal
            "test && rm -rf /",  # Command Injection
            "test*)(|(password=*"  # LDAP Injection
        ]
        
        async with httpx.AsyncClient(timeout=30) as client:
            for i, malicious_input in enumerate(malicious_inputs):
                test_name = f"Security Test {i+1}"
                
                # 데이터베이스 이름에 악성 입력
                try:
                    response = await client.post(
                        f"{self.oms_url}/api/v1/database/create",
                        json={"name": malicious_input}
                    )
                    if response.status_code == 400:
                        print(f"  ✅ 악성 DB 이름 차단: {malicious_input[:20]}...")
                        self.security_test_results.append((test_name + " (DB)", "PASS", "400 returned"))
                    else:
                        print(f"  ❌ 악성 DB 이름 허용: {response.status_code}")
                        self.security_test_results.append((test_name + " (DB)", "FAIL", f"Status: {response.status_code}"))
                except Exception as e:
                    self.security_test_results.append((test_name + " (DB)", "ERROR", str(e)))
                
                # 온톨로지 ID에 악성 입력
                try:
                    response = await client.post(
                        f"{self.oms_url}/api/v1/ontology/{self.test_db}/create",
                        json={"id": malicious_input, "label": "test"}
                    )
                    if response.status_code == 400:
                        print(f"  ✅ 악성 클래스 ID 차단: {malicious_input[:20]}...")
                        self.security_test_results.append((test_name + " (Class)", "PASS", "400 returned"))
                    else:
                        print(f"  ❌ 악성 클래스 ID 허용: {response.status_code}")
                        self.security_test_results.append((test_name + " (Class)", "FAIL", f"Status: {response.status_code}"))
                except Exception as e:
                    self.security_test_results.append((test_name + " (Class)", "ERROR", str(e)))
    
    async def _test_error_handling(self):
        """에러 처리 테스트"""
        print("\n🚨 에러 처리 테스트")
        
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. 존재하지 않는 데이터베이스 접근 (404)
            try:
                fake_db = "nonexistent_database_12345"
                response = await client.get(f"{self.oms_url}/api/v1/database/exists/{fake_db}")
                if response.status_code == 404:
                    print(f"  ✅ 존재하지 않는 DB 처리: 404 Not Found")
                    self.test_results.append(("Non-existent DB", "PASS", "404 returned"))
                else:
                    print(f"  ❌ 존재하지 않는 DB 처리 실패: {response.status_code}")
                    self.test_results.append(("Non-existent DB", "FAIL", f"Status: {response.status_code}"))
            except Exception as e:
                self.test_results.append(("Non-existent DB", "ERROR", str(e)))
            
            # 2. 잘못된 JSON 형식 (400)
            try:
                response = await client.post(
                    f"{self.oms_url}/api/v1/ontology/{self.test_db}/create",
                    content="invalid json{",
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 400:
                    print(f"  ✅ 잘못된 JSON 처리: 400 Bad Request")
                    self.test_results.append(("Invalid JSON", "PASS", "400 returned"))
                else:
                    print(f"  ❌ 잘못된 JSON 처리 실패: {response.status_code}")
                    self.test_results.append(("Invalid JSON", "FAIL", f"Status: {response.status_code}"))
            except Exception as e:
                self.test_results.append(("Invalid JSON", "ERROR", str(e)))
            
            # 3. 존재하지 않는 온톨로지 조회 (404)
            try:
                response = await client.get(f"{self.oms_url}/api/v1/ontology/{self.test_db}/NonExistentClass")
                if response.status_code == 404:
                    print(f"  ✅ 존재하지 않는 온톨로지 처리: 404 Not Found")
                    self.test_results.append(("Non-existent Ontology", "PASS", "404 returned"))
                else:
                    print(f"  ❌ 존재하지 않는 온톨로지 처리 실패: {response.status_code}")
                    self.test_results.append(("Non-existent Ontology", "FAIL", f"Status: {response.status_code}"))
            except Exception as e:
                self.test_results.append(("Non-existent Ontology", "ERROR", str(e)))
    
    async def _test_multilingual_support(self):
        """다국어 지원 테스트"""
        print("\n🌍 다국어 지원 테스트")
        
        # 다국어 온톨로지 생성 (BFF 형식)
        multilingual_ontology = {
            "label": {
                "ko": "다국어 제품",
                "en": "Multilingual Product",
                "ja": "多言語製品",
                "zh": "多语言产品"
            },
            "description": {
                "ko": "다국어 지원 제품 설명",
                "en": "Multilingual support product description"
            },
            "properties": [
                {"name": "name", "type": "xsd:string", "label": {"ko": "이름", "en": "Name"}}
            ]
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            # BFF를 통한 다국어 온톨로지 생성
            try:
                response = await client.post(
                    f"{self.bff_url}/database/{self.test_db}/ontology",
                    json=multilingual_ontology,
                    headers={"Accept-Language": "ko"}
                )
                if response.status_code == 200:
                    print(f"  ✅ 다국어 온톨로지 생성 성공")
                    self.test_results.append(("Multilingual Creation", "PASS", "Created successfully"))
                else:
                    print(f"  ❌ 다국어 온톨로지 생성 실패: {response.status_code} - {response.text}")
                    self.test_results.append(("Multilingual Creation", "FAIL", response.text))
            except Exception as e:
                print(f"  💥 다국어 온톨로지 생성 예외: {e}")
                self.test_results.append(("Multilingual Creation", "ERROR", str(e)))
            
            # 각 언어별 조회 테스트
            languages = ["ko", "en", "ja", "zh"]
            for lang in languages:
                try:
                    response = await client.get(
                        f"{self.bff_url}/database/{self.test_db}/ontology/다국어 제품",
                        headers={"Accept-Language": lang}
                    )
                    if response.status_code == 200:
                        print(f"  ✅ {lang} 언어 조회 성공")
                        self.test_results.append((f"Language {lang}", "PASS", "Retrieved successfully"))
                    else:
                        print(f"  ⚠️ {lang} 언어 조회 실패: {response.status_code}")
                        self.test_results.append((f"Language {lang}", "FAIL", f"Status: {response.status_code}"))
                except Exception as e:
                    self.test_results.append((f"Language {lang}", "ERROR", str(e)))
    
    async def _test_url_alignment(self):
        """BFF-OMS URL 정렬 테스트"""
        print("\n🔗 BFF-OMS URL 정렬 테스트")
        
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. 온톨로지 엔드포인트 정렬 확인
            test_ontology = {
                "id": "URLAlignmentTest",
                "label": "URL Alignment Test",
                "properties": [
                    {"name": "test", "type": "xsd:string", "label": "Test Property"}
                ]
            }
            
            # OMS 직접 호출
            # Fix the format to match what OMS expects
            oms_test_ontology = {
                "id": "URLAlignmentTest",
                "label": "URL Alignment Test",
                "properties": [
                    {"name": "test", "type": "xsd:string"}
                ]
            }
            try:
                response = await client.post(
                    f"{self.oms_url}/api/v1/ontology/{self.test_db}/create",
                    json=oms_test_ontology
                )
                oms_success = response.status_code == 200
                print(f"  OMS 직접 호출: {'✅' if oms_success else '❌'} {response.status_code}")
            except Exception as e:
                oms_success = False
                print(f"  OMS 직접 호출 예외: {e}")
            
            # BFF를 통한 호출 (BFF 형식에 맞게 수정)
            bff_ontology = {
                # BFF는 ID를 자동 생성하므로 제거
                "label": {
                    "ko": "URL 정렬 테스트 BFF",
                    "en": "URL Alignment Test BFF"
                },
                "properties": [
                    {"name": "test", "type": "xsd:string", "label": {"en": "Test Property"}}
                ]
            }
            try:
                response = await client.post(
                    f"{self.bff_url}/database/{self.test_db}/ontology",
                    json=bff_ontology
                )
                bff_success = response.status_code == 200
                print(f"  BFF 경유 호출: {'✅' if bff_success else '❌'} {response.status_code}")
                if not bff_success and response.text:
                    print(f"  BFF 응답: {response.text}")
            except Exception as e:
                bff_success = False
                print(f"  BFF 경유 호출 예외: {e}")
            
            if oms_success and bff_success:
                self.test_results.append(("URL Alignment", "PASS", "Both endpoints working"))
            else:
                self.test_results.append(("URL Alignment", "FAIL", f"OMS: {oms_success}, BFF: {bff_success}"))
    
    async def _cleanup(self):
        """테스트 정리"""
        print(f"\n🧹 테스트 정리: {self.test_db}")
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                await client.delete(f"{self.oms_url}/api/v1/database/{self.test_db}")
                print(f"  ✅ 테스트 DB 삭제 완료")
            except Exception as e:
                print(f"  ⚠️ 테스트 DB 삭제 실패: {e}")
    
    def _print_test_results(self):
        """테스트 결과 출력"""
        print("\n" + "="*60)
        print("📋 핵심 기능 테스트 결과")
        print("="*60)
        
        # 일반 테스트 결과
        pass_count = sum(1 for _, status, _ in self.test_results if status == "PASS")
        fail_count = sum(1 for _, status, _ in self.test_results if status == "FAIL")
        error_count = sum(1 for _, status, _ in self.test_results if status == "ERROR")
        
        print(f"✅ 성공: {pass_count}")
        print(f"❌ 실패: {fail_count}")
        print(f"💥 오류: {error_count}")
        print(f"📊 성공률: {pass_count/(len(self.test_results)) if self.test_results else 0:.1%}")
        
        # 보안 테스트 결과
        security_pass = sum(1 for _, status, _ in self.security_test_results if status == "PASS")
        security_fail = sum(1 for _, status, _ in self.security_test_results if status == "FAIL")
        
        print(f"\n🛡️ 보안 테스트:")
        print(f"  차단됨: {security_pass}")
        print(f"  뚫림: {security_fail}")
        
        # 실패한 테스트 상세
        if fail_count > 0 or error_count > 0:
            print(f"\n❌ 실패/오류 상세:")
            for test_name, status, details in self.test_results:
                if status in ["FAIL", "ERROR"]:
                    print(f"  {status}: {test_name} - {details}")
        
        # 보안 위반 상세
        if security_fail > 0:
            print(f"\n🚨 보안 위반 상세:")
            for test_name, status, details in self.security_test_results:
                if status == "FAIL":
                    print(f"  SECURITY BREACH: {test_name} - {details}")
        
        # 전체 평가
        overall_success_rate = (pass_count + security_pass) / (len(self.test_results) + len(self.security_test_results)) if (self.test_results or self.security_test_results) else 0
        
        print(f"\n🎯 전체 평가:")
        if overall_success_rate >= 0.9:
            print("  🚀 프로덕션 준비 완료!")
        elif overall_success_rate >= 0.7:
            print("  ⚠️ 일부 개선 필요")
        else:
            print("  🚨 심각한 문제 발견 - 배포 불가")
        
        print(f"  종합 성공률: {overall_success_rate:.1%}")


async def main():
    """메인 실행 함수"""
    test = CriticalFunctionalityTest()
    await test.run_all_critical_tests()


if __name__ == "__main__":
    asyncio.run(main())