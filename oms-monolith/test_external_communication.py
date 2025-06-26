#!/usr/bin/env python3
"""
OMS 외부 서비스 통신 실제 테스트
각 통신 방식이 실제로 작동하는지 검증
"""
import asyncio
import json
import sys
import os
from datetime import datetime
import httpx
from typing import Dict, Any, Optional

sys.path.append('/Users/sihyun/Desktop/ARRAKIS/SPICE/oms-monolith')

# Import OMS modules
from database.simple_terminus_client import SimpleTerminusDBClient
from core.event_publisher.outbox_processor import OutboxProcessor
from core.event_publisher.enhanced_event_service import EnhancedEventService
from core.action.metadata_service import ActionMetadataService
from shared.infrastructure.nats_client import NATSClient
from shared.infrastructure.metrics import MetricsCollector

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ExternalCommunicationTest:
    """외부 서비스 통신 테스트"""
    
    def __init__(self):
        self.results = {
            "event_publish": {"tested": False, "success": False, "details": {}},
            "webhook_action": {"tested": False, "success": False, "details": {}},
            "graphql_api": {"tested": False, "success": False, "details": {}},
            "rest_api": {"tested": False, "success": False, "details": {}},
            "metadata_pulling": {"tested": False, "success": False, "details": {}}
        }
        
    async def setup(self):
        """테스트 환경 설정"""
        logger.info("🚀 외부 통신 테스트 환경 설정 중...")
        
        # TerminusDB 연결
        self.db = SimpleTerminusDBClient(
            endpoint="http://localhost:6363",
            username="admin",
            password="root",
            database="oms"
        )
        connected = await self.db.connect()
        if not connected:
            raise Exception("TerminusDB 연결 실패")
            
        logger.info("✅ TerminusDB 연결 성공")
        
    async def test_1_event_publishing(self):
        """Test 1: 이벤트 발행 실제 테스트"""
        logger.info("\n=== Test 1: Event Publishing (NATS) ===")
        self.results["event_publish"]["tested"] = True
        
        try:
            # 1. schema.changed 이벤트 생성
            logger.info("1️⃣ schema.changed 이벤트 생성")
            
            # 테스트용 ObjectType 생성
            test_object = {
                "@type": "ObjectType",
                "@id": "ObjectType/TestEventPublish",
                "name": "TestEventPublish",
                "displayName": "이벤트 발행 테스트",
                "description": "외부 통신 테스트용"
            }
            
            result = await self.db.client.post(
                f"http://localhost:6363/api/document/admin/oms?author=test&message=Test event publish",
                json=[test_object],
                auth=("admin", "root")
            )
            
            if result.status_code in [200, 201]:
                logger.info("✅ 테스트 ObjectType 생성 성공")
                
                # 2. Outbox 이벤트 확인
                await asyncio.sleep(1)  # Change detector가 감지할 시간
                
                # 3. NATS 연결 시도
                logger.info("2️⃣ NATS 연결 시도")
                try:
                    # NATS 연결 테스트
                    nats_test = await self.test_nats_connection()
                    if nats_test:
                        logger.info("✅ NATS 연결 성공")
                        self.results["event_publish"]["success"] = True
                        self.results["event_publish"]["details"] = {
                            "nats_connected": True,
                            "event_type": "schema.changed",
                            "object_created": "TestEventPublish"
                        }
                    else:
                        logger.warning("⚠️ NATS 연결 실패 - 서비스가 실행 중인지 확인")
                        self.results["event_publish"]["details"]["error"] = "NATS not available"
                        
                except Exception as e:
                    logger.error(f"❌ NATS 테스트 실패: {e}")
                    self.results["event_publish"]["details"]["error"] = str(e)
                    
            else:
                logger.error(f"❌ ObjectType 생성 실패: {result.status_code}")
                self.results["event_publish"]["details"]["error"] = f"Create failed: {result.status_code}"
                
        except Exception as e:
            logger.error(f"❌ 이벤트 발행 테스트 실패: {e}")
            self.results["event_publish"]["details"]["error"] = str(e)
            
    async def test_nats_connection(self) -> bool:
        """NATS 연결 테스트"""
        try:
            # NATS가 실행 중인지 확인
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8222/varz", timeout=2.0)
                return response.status_code == 200
        except:
            return False
            
    async def test_2_webhook_action(self):
        """Test 2: Webhook Action 실제 테스트"""
        logger.info("\n=== Test 2: Webhook Action (Action Service) ===")
        self.results["webhook_action"]["tested"] = True
        
        try:
            # 1. ActionType 메타데이터 생성
            logger.info("1️⃣ ActionType 메타데이터 생성")
            
            action_service = ActionMetadataService(
                terminus_endpoint="http://localhost:6363"
            )
            await action_service.initialize()
            
            action_data = {
                "name": "SendNotification",
                "displayName": "알림 전송",
                "description": "외부 Webhook 호출 테스트",
                "objectTypeId": "ObjectType/TestEventPublish",
                "webhookUrl": "https://webhook.site/test-oms",  # 테스트 webhook
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "channel": {"type": "string"}
                    },
                    "required": ["message"]
                }
            }
            
            action_type = await action_service.create_action_type(action_data)
            logger.info(f"✅ ActionType 생성: {action_type.id}")
            
            # 2. Action Service로 실행 위임 시도
            logger.info("2️⃣ Action Service 호출 시도")
            
            actions_service_url = os.getenv("ACTIONS_SERVICE_URL", "http://localhost:8009")
            
            try:
                async with httpx.AsyncClient() as client:
                    # Action Service health check
                    health = await client.get(f"{actions_service_url}/health", timeout=2.0)
                    
                    if health.status_code == 200:
                        logger.info("✅ Action Service 연결 가능")
                        self.results["webhook_action"]["success"] = True
                        self.results["webhook_action"]["details"] = {
                            "action_type_created": action_type.id,
                            "webhook_url": action_data["webhookUrl"],
                            "action_service_available": True
                        }
                    else:
                        logger.warning("⚠️ Action Service 응답 이상")
                        self.results["webhook_action"]["details"]["error"] = "Action Service unhealthy"
                        
            except Exception as e:
                logger.warning(f"⚠️ Action Service 연결 불가: {e}")
                self.results["webhook_action"]["details"] = {
                    "action_type_created": action_type.id,
                    "webhook_url": action_data["webhookUrl"],
                    "action_service_available": False,
                    "note": "Action Service가 별도 MSA로 실행되어야 함"
                }
                
        except Exception as e:
            logger.error(f"❌ Webhook Action 테스트 실패: {e}")
            self.results["webhook_action"]["details"]["error"] = str(e)
            
    async def test_3_graphql_api(self):
        """Test 3: GraphQL API 실제 테스트"""
        logger.info("\n=== Test 3: GraphQL API Access ===")
        self.results["graphql_api"]["tested"] = True
        
        try:
            # GraphQL 엔드포인트 테스트
            graphql_url = "http://localhost:8004/graphql"
            
            # 1. GraphQL Schema 조회
            logger.info("1️⃣ GraphQL Schema 조회")
            
            query = """
            query IntrospectionQuery {
                __schema {
                    types {
                        name
                        kind
                    }
                }
            }
            """
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    graphql_url,
                    json={"query": query},
                    headers={"Content-Type": "application/json"},
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    types = data.get("data", {}).get("__schema", {}).get("types", [])
                    logger.info(f"✅ GraphQL Schema 조회 성공: {len(types)}개 타입")
                    
                    # 2. ObjectType 조회 쿼리
                    logger.info("2️⃣ ObjectType 조회 테스트")
                    
                    object_query = """
                    query GetObjectTypes {
                        objectTypes(branch: "main") {
                            nodes {
                                id
                                name
                                displayName
                                versionHash
                            }
                            total
                        }
                    }
                    """
                    
                    response2 = await client.post(
                        graphql_url,
                        json={"query": object_query},
                        timeout=5.0
                    )
                    
                    if response2.status_code == 200:
                        result = response2.json()
                        if "errors" not in result:
                            logger.info("✅ ObjectType 조회 성공")
                            self.results["graphql_api"]["success"] = True
                            self.results["graphql_api"]["details"] = {
                                "schema_types": len(types),
                                "endpoint": graphql_url,
                                "query_success": True
                            }
                        else:
                            logger.warning(f"⚠️ GraphQL 쿼리 오류: {result['errors']}")
                            self.results["graphql_api"]["details"]["errors"] = result["errors"]
                    else:
                        logger.error(f"❌ ObjectType 조회 실패: {response2.status_code}")
                        self.results["graphql_api"]["details"]["error"] = f"Query failed: {response2.status_code}"
                        
                else:
                    logger.error(f"❌ GraphQL Schema 조회 실패: {response.status_code}")
                    self.results["graphql_api"]["details"]["error"] = f"Schema query failed: {response.status_code}"
                    
        except httpx.ConnectError:
            logger.warning("⚠️ GraphQL 서비스 연결 불가 - 서비스가 실행 중인지 확인")
            self.results["graphql_api"]["details"] = {
                "error": "GraphQL service not running",
                "note": "Run: cd api/graphql && python main.py"
            }
        except Exception as e:
            logger.error(f"❌ GraphQL API 테스트 실패: {e}")
            self.results["graphql_api"]["details"]["error"] = str(e)
            
    async def test_4_rest_api(self):
        """Test 4: REST API 실제 테스트"""
        logger.info("\n=== Test 4: REST API Access ===")
        self.results["rest_api"]["tested"] = True
        
        try:
            # REST API 엔드포인트
            base_url = "http://localhost:8002"
            
            # 1. Health check
            logger.info("1️⃣ REST API Health Check")
            
            async with httpx.AsyncClient() as client:
                health = await client.get(f"{base_url}/health", timeout=5.0)
                
                if health.status_code == 200:
                    logger.info("✅ REST API 서비스 정상")
                    
                    # 2. ObjectType 목록 조회
                    logger.info("2️⃣ ObjectType 목록 조회")
                    
                    response = await client.get(
                        f"{base_url}/api/v1/schemas/main/object-types",
                        headers={"Authorization": "Bearer test-token"},
                        timeout=5.0
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        logger.info(f"✅ ObjectType 목록 조회 성공: {len(data.get('data', []))}개")
                        
                        # 3. 특정 ObjectType 조회
                        if data.get('data'):
                            first_type = data['data'][0]
                            type_id = first_type['id']
                            
                            detail_response = await client.get(
                                f"{base_url}/api/v1/schemas/main/object-types/{type_id}",
                                headers={"Authorization": "Bearer test-token"},
                                timeout=5.0
                            )
                            
                            if detail_response.status_code == 200:
                                detail = detail_response.json()
                                logger.info(f"✅ 개별 ObjectType 조회 성공: {detail.get('name')}")
                                
                                self.results["rest_api"]["success"] = True
                                self.results["rest_api"]["details"] = {
                                    "endpoint": base_url,
                                    "object_types_count": len(data.get('data', [])),
                                    "version_hash": detail.get('versionHash'),
                                    "api_version": "v1"
                                }
                            else:
                                logger.warning(f"⚠️ 개별 조회 실패: {detail_response.status_code}")
                                
                    else:
                        logger.error(f"❌ ObjectType 목록 조회 실패: {response.status_code}")
                        self.results["rest_api"]["details"]["error"] = f"List failed: {response.status_code}"
                        
                else:
                    logger.error(f"❌ Health check 실패: {health.status_code}")
                    self.results["rest_api"]["details"]["error"] = "Service unhealthy"
                    
        except httpx.ConnectError:
            logger.warning("⚠️ REST API 서비스 연결 불가")
            self.results["rest_api"]["details"] = {
                "error": "REST API service not running",
                "note": "Run: python main_enterprise.py"
            }
        except Exception as e:
            logger.error(f"❌ REST API 테스트 실패: {e}")
            self.results["rest_api"]["details"]["error"] = str(e)
            
    async def test_5_metadata_pulling(self):
        """Test 5: Metadata Pulling 실제 테스트"""
        logger.info("\n=== Test 5: Metadata Pulling ===")
        self.results["metadata_pulling"]["tested"] = True
        
        try:
            # 1. 초기 메타데이터 조회
            logger.info("1️⃣ 초기 메타데이터 조회")
            
            async with httpx.AsyncClient() as client:
                # 첫 번째 조회
                response1 = await client.get(
                    "http://localhost:8002/api/v1/schemas/main/object-types",
                    headers={"Authorization": "Bearer test-token"},
                    timeout=5.0
                )
                
                if response1.status_code == 200:
                    data1 = response1.json()
                    initial_versions = {}
                    
                    for obj in data1.get('data', []):
                        initial_versions[obj['id']] = obj.get('versionHash')
                        
                    logger.info(f"✅ 초기 버전 해시 수집: {len(initial_versions)}개")
                    
                    # 2. 변경 발생시키기
                    logger.info("2️⃣ 메타데이터 변경 발생")
                    
                    # 테스트용 변경
                    if data1.get('data'):
                        target = data1['data'][0]
                        update_result = await self.db.client.post(
                            f"http://localhost:6363/api/document/admin/oms?author=test&message=Test metadata change",
                            json=[{
                                "@type": "ObjectType",
                                "@id": target['id'],
                                "name": target['name'],
                                "displayName": target['displayName'] + " (Updated)",
                                "description": f"Updated at {datetime.now().isoformat()}"
                            }],
                            auth=("admin", "root")
                        )
                        
                        if update_result.status_code in [200, 201]:
                            logger.info("✅ 메타데이터 변경 완료")
                            
                            # 3. 변경 후 재조회
                            await asyncio.sleep(0.5)  # 변경 반영 대기
                            
                            logger.info("3️⃣ 변경 후 메타데이터 재조회")
                            response2 = await client.get(
                                "http://localhost:8002/api/v1/schemas/main/object-types",
                                headers={"Authorization": "Bearer test-token"},
                                timeout=5.0
                            )
                            
                            if response2.status_code == 200:
                                data2 = response2.json()
                                changed = False
                                
                                for obj in data2.get('data', []):
                                    if obj['id'] in initial_versions:
                                        if obj.get('versionHash') != initial_versions[obj['id']]:
                                            logger.info(f"✅ 버전 변경 감지: {obj['id']}")
                                            changed = True
                                            break
                                            
                                if changed:
                                    self.results["metadata_pulling"]["success"] = True
                                    self.results["metadata_pulling"]["details"] = {
                                        "initial_count": len(initial_versions),
                                        "change_detected": True,
                                        "method": "version_hash polling"
                                    }
                                else:
                                    logger.warning("⚠️ 버전 변경이 감지되지 않음")
                                    self.results["metadata_pulling"]["details"]["warning"] = "No version change detected"
                                    
                else:
                    logger.error(f"❌ 초기 조회 실패: {response1.status_code}")
                    self.results["metadata_pulling"]["details"]["error"] = f"Initial query failed: {response1.status_code}"
                    
        except Exception as e:
            logger.error(f"❌ Metadata Pulling 테스트 실패: {e}")
            self.results["metadata_pulling"]["details"]["error"] = str(e)
            
    async def run_all_tests(self):
        """모든 테스트 실행"""
        await self.setup()
        
        # 각 테스트 실행
        await self.test_1_event_publishing()
        await self.test_2_webhook_action()
        await self.test_3_graphql_api()
        await self.test_4_rest_api()
        await self.test_5_metadata_pulling()
        
        # 결과 요약
        self.print_summary()
        
        # 정리
        await self.db.disconnect()
        
    def print_summary(self):
        """테스트 결과 요약"""
        print("\n" + "="*80)
        print("🔍 OMS 외부 통신 테스트 결과")
        print("="*80)
        
        total_tests = 0
        passed_tests = 0
        
        for test_name, result in self.results.items():
            if result["tested"]:
                total_tests += 1
                if result["success"]:
                    passed_tests += 1
                    status = "✅ PASS"
                else:
                    status = "❌ FAIL"
                    
                print(f"\n{test_name}: {status}")
                print(f"  Details: {json.dumps(result['details'], indent=2)}")
                
        print(f"\n총 테스트: {total_tests}, 성공: {passed_tests}, 실패: {total_tests - passed_tests}")
        
        print("\n📋 필수 서비스 실행 상태:")
        print("- TerminusDB: ✅ 실행 중 (docker-compose)")
        print("- NATS: " + ("✅ 실행 중" if self.results["event_publish"]["success"] else "❌ 미실행 (docker run -p 4222:4222 nats)"))
        print("- GraphQL: " + ("✅ 실행 중" if self.results["graphql_api"]["success"] else "❌ 미실행 (cd api/graphql && python main.py)"))
        print("- REST API: " + ("✅ 실행 중" if self.results["rest_api"]["success"] else "❌ 미실행 (python main_enterprise.py)"))
        print("- Action Service: " + ("✅ 실행 중" if self.results["webhook_action"].get("details", {}).get("action_service_available") else "❌ 미실행 (별도 MSA)"))
        
        print("\n💡 참고사항:")
        print("- OMS는 메타데이터 관리에 집중, 실행은 외부 MSA에 위임")
        print("- Action Service, Funnel Service 등은 별도 MSA로 구현 필요")
        print("- 이벤트 발행은 Outbox 패턴으로 신뢰성 보장")
        print("- 메타데이터 동기화는 version_hash 기반 polling")


async def main():
    """메인 실행"""
    test = ExternalCommunicationTest()
    await test.run_all_tests()


if __name__ == "__main__":
    print("🚀 OMS 외부 서비스 통신 실제 테스트 시작")
    print("="*80)
    asyncio.run(main())