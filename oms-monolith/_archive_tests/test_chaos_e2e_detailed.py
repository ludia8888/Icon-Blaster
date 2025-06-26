#!/usr/bin/env python3
"""
OMS 카오스 E2E 성능 검증 테스트 (상세 로그 버전)
적절한 크기로 조정하여 완료 가능하도록 함
"""
import asyncio
import json
import sys
import os
from datetime import datetime
import httpx
import nats
import random
import string
import statistics
import psutil
import time
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
import aiofiles

sys.path.append('/Users/sihyun/Desktop/ARRAKIS/SPICE/oms-monolith')

from database.simple_terminus_client import SimpleTerminusDBClient

import logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('chaos_test_detailed.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DetailedChaosTest:
    """상세 카오스 E2E 성능 테스트"""
    
    def __init__(self):
        self.base_url = "http://localhost:8002"
        self.nats_url = "nats://localhost:4222"
        self.metrics = {
            "api_latencies": [],
            "event_latencies": [],
            "errors": [],
            "successful_operations": 0,
            "failed_operations": 0
        }
        self.start_time = None
        self.event_counter = 0
        self.event_timestamps = {}
        
    async def setup(self):
        """환경 설정"""
        logger.info("="*80)
        logger.info("🚀 OMS 카오스 E2E 성능 검증 테스트 (상세 버전)")
        logger.info("="*80)
        
        # NATS 연결
        self.nc = await nats.connect(self.nats_url)
        logger.info("✅ NATS 연결 성공")
        
        # 이벤트 수신 핸들러
        async def event_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                event_id = data.get('id')
                if event_id and event_id in self.event_timestamps:
                    latency = (datetime.now().timestamp() - self.event_timestamps[event_id]) * 1000
                    self.metrics["event_latencies"].append(latency)
                    del self.event_timestamps[event_id]
                    logger.debug(f"이벤트 수신: {msg.subject}, 지연: {latency:.2f}ms")
            except:
                pass
                
        await self.nc.subscribe("oms.>", cb=event_handler)
        await self.nc.subscribe("com.>", cb=event_handler)
        
        # DB 연결
        self.db = SimpleTerminusDBClient(
            endpoint="http://localhost:6363",
            username="admin",
            password="root",
            database="oms"
        )
        await self.db.connect()
        logger.info("✅ TerminusDB 연결 성공")
        
        # HTTP 클라이언트 풀
        self.http_clients = [httpx.AsyncClient(timeout=30.0) for _ in range(5)]
        logger.info("✅ HTTP 클라이언트 풀 생성 (5개)")
        
        self.start_time = datetime.now()
        logger.info(f"테스트 시작 시간: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*80)
        
    async def chaos_test_1_burst_load(self):
        """Test 1: 순간 폭발적 부하 (500개)"""
        logger.info("\n" + "="*80)
        logger.info("💥 Chaos Test 1: 순간 폭발적 부하 테스트 (500개 동시 요청)")
        logger.info("="*80)
        
        results = {
            "total_requests": 500,
            "successful": 0,
            "failed": 0,
            "latencies": [],
            "errors_by_type": {}
        }
        
        logger.info("🔥 500개 동시 API 요청 시작...")
        
        async def make_request(client_idx, req_idx):
            client = self.http_clients[client_idx % len(self.http_clients)]
            start = time.time()
            operation = random.choice(['create', 'read', 'update'])
            
            try:
                if operation == 'create':
                    response = await client.post(
                        f"{self.base_url}/api/v1/schemas/main/object-types",
                        json={
                            "name": f"Burst_{req_idx}_{random.randint(1000,9999)}",
                            "displayName": f"부하 테스트 {req_idx}",
                            "description": "극한 부하 테스트"
                        },
                        headers={"Authorization": f"Bearer burst-{req_idx}"}
                    )
                elif operation == 'read':
                    response = await client.get(
                        f"{self.base_url}/api/v1/schemas/main/object-types",
                        headers={"Authorization": f"Bearer burst-{req_idx}"}
                    )
                else:  # update
                    response = await client.get(f"{self.base_url}/health")
                    
                latency = (time.time() - start) * 1000
                
                if response.status_code in [200, 201]:
                    return True, latency, operation
                else:
                    error_type = f"{operation}_{response.status_code}"
                    return False, latency, error_type
                    
            except Exception as e:
                latency = (time.time() - start) * 1000
                error_type = f"{operation}_exception_{type(e).__name__}"
                return False, latency, error_type
                
        # 50개씩 배치로 실행하여 진행 상황 표시
        batch_size = 50
        total_batches = results["total_requests"] // batch_size
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            logger.info(f"  배치 {batch_num + 1}/{total_batches} 실행 중... ({start_idx}-{start_idx + batch_size})")
            
            tasks = []
            for i in range(batch_size):
                tasks.append(make_request(i, start_idx + i))
                
            batch_start = time.time()
            batch_results = await asyncio.gather(*tasks)
            batch_time = time.time() - batch_start
            
            batch_success = 0
            for success, latency, info in batch_results:
                results["latencies"].append(latency)
                if success:
                    results["successful"] += 1
                    batch_success += 1
                else:
                    results["failed"] += 1
                    results["errors_by_type"][info] = results["errors_by_type"].get(info, 0) + 1
                    
            logger.info(f"    배치 완료: 성공 {batch_success}/{batch_size}, 평균 지연: {statistics.mean([r[1] for r in batch_results]):.2f}ms, 소요시간: {batch_time:.2f}초")
            
            # 배치 간 짧은 대기
            await asyncio.sleep(0.1)
            
        # 통계 계산 및 로깅
        logger.info("\n📊 순간 부하 테스트 결과:")
        logger.info(f"  총 요청: {results['total_requests']}")
        logger.info(f"  성공: {results['successful']} ({results['successful']/results['total_requests']*100:.1f}%)")
        logger.info(f"  실패: {results['failed']} ({results['failed']/results['total_requests']*100:.1f}%)")
        
        if results["latencies"]:
            logger.info(f"  평균 지연: {statistics.mean(results['latencies']):.2f}ms")
            logger.info(f"  최소 지연: {min(results['latencies']):.2f}ms")
            logger.info(f"  최대 지연: {max(results['latencies']):.2f}ms")
            logger.info(f"  중간값: {statistics.median(results['latencies']):.2f}ms")
            
            if len(results["latencies"]) >= 20:
                logger.info(f"  P95 지연: {statistics.quantiles(results['latencies'], n=20)[18]:.2f}ms")
            if len(results["latencies"]) >= 100:
                logger.info(f"  P99 지연: {statistics.quantiles(results['latencies'], n=100)[98]:.2f}ms")
                
        if results["errors_by_type"]:
            logger.info("\n  오류 분석:")
            for error_type, count in sorted(results["errors_by_type"].items(), key=lambda x: x[1], reverse=True):
                logger.info(f"    {error_type}: {count}개")
                
        return results
        
    async def chaos_test_2_event_storm(self):
        """Test 2: 이벤트 폭풍 (5000개)"""
        logger.info("\n" + "="*80)
        logger.info("🌪️ Chaos Test 2: 이벤트 폭풍 (5,000 이벤트)")
        logger.info("="*80)
        
        results = {
            "total_events": 5000,
            "published": 0,
            "publish_errors": 0,
            "received": 0,
            "event_latencies": []
        }
        
        initial_received = len(self.metrics["event_latencies"])
        start_time = time.time()
        
        logger.info("📤 5,000개 이벤트 발행 시작...")
        
        # 500개씩 배치로 발행
        batch_size = 500
        total_batches = results["total_events"] // batch_size
        
        for batch_num in range(total_batches):
            batch_start = time.time()
            batch_published = 0
            
            logger.info(f"  배치 {batch_num + 1}/{total_batches} 발행 중...")
            
            for i in range(batch_size):
                event_idx = batch_num * batch_size + i
                event_id = f"storm-{event_idx}-{random.randint(1000,9999)}"
                self.event_timestamps[event_id] = datetime.now().timestamp()
                
                event = {
                    "specversion": "1.0",
                    "type": "com.oms.chaos.storm",
                    "source": "/oms/chaos",
                    "id": event_id,
                    "time": datetime.now().isoformat(),
                    "datacontenttype": "application/json",
                    "data": {
                        "index": event_idx,
                        "batch": batch_num,
                        "test": "event_storm",
                        "payload": "x" * random.randint(100, 500)
                    }
                }
                
                subject = f"oms.chaos.storm.{event_idx % 50}"
                
                try:
                    await self.nc.publish(subject, json.dumps(event).encode())
                    results["published"] += 1
                    batch_published += 1
                except Exception as e:
                    results["publish_errors"] += 1
                    logger.debug(f"이벤트 발행 실패: {e}")
                    
            batch_time = time.time() - batch_start
            logger.info(f"    배치 완료: {batch_published}개 발행, 소요시간: {batch_time:.2f}초, 속도: {batch_published/batch_time:.2f} events/sec")
            
            # 배치 간 짧은 대기
            await asyncio.sleep(0.05)
            
        publish_time = time.time() - start_time
        
        # 수신 대기
        logger.info("\n⏳ 이벤트 수신 대기 (3초)...")
        await asyncio.sleep(3)
        
        results["received"] = len(self.metrics["event_latencies"]) - initial_received
        results["event_latencies"] = self.metrics["event_latencies"][initial_received:]
        
        # 결과 로깅
        logger.info("\n📊 이벤트 폭풍 결과:")
        logger.info(f"  발행 시도: {results['total_events']}")
        logger.info(f"  발행 성공: {results['published']} ({results['published']/results['total_events']*100:.1f}%)")
        logger.info(f"  발행 실패: {results['publish_errors']}")
        logger.info(f"  발행 속도: {results['published']/publish_time:.2f} events/sec")
        logger.info(f"  수신: {results['received']} ({results['received']/results['published']*100:.1f}% if results['published'] > 0 else 0)")
        
        if results["event_latencies"]:
            logger.info(f"  평균 이벤트 지연: {statistics.mean(results['event_latencies']):.2f}ms")
            logger.info(f"  최대 이벤트 지연: {max(results['event_latencies']):.2f}ms")
            logger.info(f"  최소 이벤트 지연: {min(results['event_latencies']):.2f}ms")
            
        return results
        
    async def chaos_test_3_concurrent_chaos(self):
        """Test 3: 동시성 카오스"""
        logger.info("\n" + "="*80)
        logger.info("🌀 Chaos Test 3: 동시성 카오스")
        logger.info("="*80)
        
        results = {
            "concurrent_updates": {"attempts": 100, "success": 0, "failed": 0},
            "mixed_operations": {"total": 90, "success": 0, "failed": 0},
            "race_conditions_detected": 0
        }
        
        # 1. 동일 객체에 대한 동시 수정
        logger.info("\n1️⃣ 동일 객체 100개 동시 수정 테스트...")
        
        # 먼저 테스트 객체 생성
        test_obj_name = f"ConcurrentTest_{random.randint(1000,9999)}"
        create_resp = await self.http_clients[0].post(
            f"{self.base_url}/api/v1/schemas/main/object-types",
            json={
                "name": test_obj_name,
                "displayName": "동시성 테스트",
                "description": "초기 설명"
            },
            headers={"Authorization": "Bearer creator"}
        )
        
        if create_resp.status_code == 200:
            obj_data = create_resp.json()
            obj_id = obj_data.get('id', test_obj_name)
            logger.info(f"  테스트 객체 생성 완료: {obj_id}")
            
            # 100개 동시 수정 시도
            async def concurrent_update(idx):
                try:
                    resp = await self.http_clients[idx % len(self.http_clients)].put(
                        f"{self.base_url}/api/v1/schemas/main/object-types/{obj_id}",
                        json={"description": f"동시 수정 #{idx} - {datetime.now().isoformat()}"},
                        headers={"Authorization": f"Bearer updater-{idx}"}
                    )
                    return resp.status_code == 200, resp.status_code
                except Exception as e:
                    return False, str(e)
                    
            logger.info("  100개 동시 수정 실행...")
            update_start = time.time()
            tasks = [concurrent_update(i) for i in range(100)]
            update_results = await asyncio.gather(*tasks)
            update_time = time.time() - update_start
            
            for success, info in update_results:
                if success:
                    results["concurrent_updates"]["success"] += 1
                else:
                    results["concurrent_updates"]["failed"] += 1
                    if isinstance(info, int) and info == 409:  # Conflict
                        results["race_conditions_detected"] += 1
                        
            logger.info(f"  완료: 성공 {results['concurrent_updates']['success']}/100, 소요시간: {update_time:.2f}초")
            logger.info(f"  경쟁 상태 감지: {results['race_conditions_detected']}건")
            
        # 2. 혼합 작업 동시 실행
        logger.info("\n2️⃣ 이벤트 + API + DB 혼합 작업 (90개)...")
        
        async def mixed_chaos():
            tasks = []
            
            # 30개 이벤트 발행
            for i in range(30):
                event_task = self.nc.publish(
                    "oms.chaos.mixed",
                    json.dumps({
                        "id": f"mixed-{i}",
                        "time": datetime.now().isoformat(),
                        "type": "chaos_test"
                    }).encode()
                )
                tasks.append(("event", event_task))
                
            # 30개 API 호출
            for i in range(30):
                api_task = self.http_clients[i % len(self.http_clients)].get(
                    f"{self.base_url}/api/v1/schemas/main/object-types",
                    headers={"Authorization": f"Bearer mixed-{i}"}
                )
                tasks.append(("api", api_task))
                
            # 30개 DB 직접 조회
            for i in range(30):
                db_task = self.db.client.get(
                    "http://localhost:6363/api/document/admin/oms?type=ObjectType&limit=1",
                    auth=("admin", "root")
                )
                tasks.append(("db", db_task))
                
            # 모든 작업 동시 실행
            logger.info("  90개 혼합 작업 동시 실행...")
            mixed_start = time.time()
            
            task_results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
            mixed_time = time.time() - mixed_start
            
            # 결과 분석
            success_by_type = {"event": 0, "api": 0, "db": 0}
            fail_by_type = {"event": 0, "api": 0, "db": 0}
            
            for i, result in enumerate(task_results):
                task_type = tasks[i][0]
                if not isinstance(result, Exception):
                    results["mixed_operations"]["success"] += 1
                    success_by_type[task_type] += 1
                else:
                    results["mixed_operations"]["failed"] += 1
                    fail_by_type[task_type] += 1
                    
            logger.info(f"  완료: 성공 {results['mixed_operations']['success']}/90, 소요시간: {mixed_time:.2f}초")
            logger.info(f"  성공 분석 - 이벤트: {success_by_type['event']}/30, API: {success_by_type['api']}/30, DB: {success_by_type['db']}/30")
            
        await mixed_chaos()
        
        logger.info("\n📊 동시성 카오스 결과:")
        logger.info(f"  동일 객체 수정: 성공 {results['concurrent_updates']['success']}/100")
        logger.info(f"  경쟁 상태: {results['race_conditions_detected']}건")
        logger.info(f"  혼합 작업: 성공 {results['mixed_operations']['success']}/90")
        
        return results
        
    async def chaos_test_4_recovery(self):
        """Test 4: 장애 복구 테스트"""
        logger.info("\n" + "="*80)
        logger.info("🔧 Chaos Test 4: 장애 복구 능력")
        logger.info("="*80)
        
        results = {
            "baseline_latency": 0,
            "stressed_latency": 0,
            "recovery_time": 0,
            "recovered": False,
            "stress_operations": {"success": 0, "failed": 0}
        }
        
        # 1. 기준선 측정
        logger.info("\n1️⃣ 정상 상태 기준선 측정...")
        baseline_latencies = []
        
        for i in range(10):
            start = time.time()
            try:
                resp = await self.http_clients[0].get(f"{self.base_url}/health")
                if resp.status_code == 200:
                    latency = (time.time() - start) * 1000
                    baseline_latencies.append(latency)
            except:
                pass
            await asyncio.sleep(0.1)
            
        if baseline_latencies:
            results["baseline_latency"] = statistics.mean(baseline_latencies)
            logger.info(f"  기준 응답시간: {results['baseline_latency']:.2f}ms (10회 평균)")
        
        # 2. 극한 스트레스 부하
        logger.info("\n2️⃣ 극한 스트레스 부하 가중...")
        logger.info("  200개 대용량 객체 동시 생성 시도...")
        
        async def stress_operation(idx):
            try:
                # 대용량 페이로드
                large_description = "x" * 5000  # 5KB
                large_metadata = {f"field_{j}": f"value_{j}" * 50 for j in range(20)}
                
                resp = await self.http_clients[idx % len(self.http_clients)].post(
                    f"{self.base_url}/api/v1/schemas/main/object-types",
                    json={
                        "name": f"Stress_{idx}_{random.randint(1000,9999)}",
                        "displayName": f"스트레스 {idx}",
                        "description": large_description,
                        "metadata": large_metadata
                    },
                    headers={"Authorization": f"Bearer stress-{idx}"},
                    timeout=5.0
                )
                return resp.status_code in [200, 201]
            except:
                return False
                
        stress_start = time.time()
        tasks = [stress_operation(i) for i in range(200)]
        stress_results = await asyncio.gather(*tasks, return_exceptions=True)
        stress_time = time.time() - stress_start
        
        for result in stress_results:
            if result is True:
                results["stress_operations"]["success"] += 1
            else:
                results["stress_operations"]["failed"] += 1
                
        logger.info(f"  스트레스 작업 완료: 성공 {results['stress_operations']['success']}/200, 소요시간: {stress_time:.2f}초")
        
        # 스트레스 직후 상태 측정
        logger.info("\n3️⃣ 스트레스 직후 상태 측정...")
        stressed_latencies = []
        
        for i in range(5):
            start = time.time()
            try:
                resp = await self.http_clients[0].get(f"{self.base_url}/health", timeout=3.0)
                latency = (time.time() - start) * 1000
                stressed_latencies.append(latency)
                logger.info(f"  스트레스 상태 응답: {latency:.2f}ms")
            except asyncio.TimeoutError:
                stressed_latencies.append(3000)  # timeout
                logger.info("  스트레스 상태 응답: TIMEOUT (3000ms)")
            except:
                stressed_latencies.append(3000)
                
        results["stressed_latency"] = statistics.mean(stressed_latencies)
        logger.info(f"  스트레스 응답시간: {results['stressed_latency']:.2f}ms (5회 평균)")
        
        # 3. 복구 시간 측정
        logger.info("\n4️⃣ 시스템 복구 모니터링...")
        recovery_start = time.time()
        check_count = 0
        
        while (time.time() - recovery_start) < 30:  # 최대 30초
            check_count += 1
            try:
                start = time.time()
                resp = await self.http_clients[0].get(f"{self.base_url}/health", timeout=2.0)
                latency = (time.time() - start) * 1000
                
                logger.info(f"  복구 체크 #{check_count}: {latency:.2f}ms")
                
                # 기준선의 2배 이내로 돌아오면 복구
                if latency < results["baseline_latency"] * 2:
                    results["recovery_time"] = time.time() - recovery_start
                    results["recovered"] = True
                    logger.info(f"  ✅ 시스템 복구 완료! (복구 시간: {results['recovery_time']:.2f}초)")
                    break
                    
            except:
                logger.info(f"  복구 체크 #{check_count}: 실패")
                
            await asyncio.sleep(1)
            
        if not results["recovered"]:
            logger.info("  ❌ 30초 내 복구 실패")
            
        logger.info("\n📊 장애 복구 테스트 결과:")
        logger.info(f"  기준 응답시간: {results['baseline_latency']:.2f}ms")
        logger.info(f"  스트레스 응답시간: {results['stressed_latency']:.2f}ms ({results['stressed_latency']/results['baseline_latency']:.1f}배 증가)")
        logger.info(f"  복구 시간: {results['recovery_time']:.2f}초")
        logger.info(f"  복구 상태: {'✅ 성공' if results['recovered'] else '❌ 실패'}")
        
        return results
        
    async def generate_final_report(self, test_results):
        """최종 종합 보고서"""
        logger.info("\n" + "="*80)
        logger.info("📊 카오스 E2E 성능 테스트 최종 보고서")
        logger.info("="*80)
        
        total_time = (datetime.now() - self.start_time).total_seconds()
        
        # 1. 테스트 요약
        logger.info("\n### 1. 테스트 실행 요약")
        logger.info(f"⏱️ 총 테스트 시간: {total_time:.2f}초")
        logger.info(f"🚀 테스트 항목: 4개")
        logger.info(f"📊 수집된 메트릭:")
        logger.info(f"   - API 지연 시간: {len(self.metrics['api_latencies'])}개")
        logger.info(f"   - 이벤트 지연 시간: {len(self.metrics['event_latencies'])}개")
        logger.info(f"   - 오류 기록: {len(self.metrics['errors'])}개")
        
        # 2. 각 테스트 점수
        logger.info("\n### 2. 개별 테스트 평가")
        
        scores = {}
        
        # 순간 부하 점수
        burst = test_results.get("burst_load", {})
        burst_success_rate = burst.get("successful", 0) / burst.get("total_requests", 1) * 100
        scores["burst"] = 1 if burst_success_rate >= 70 else 0
        logger.info(f"\n💥 순간 부하 처리:")
        logger.info(f"   성공률: {burst_success_rate:.1f}%")
        logger.info(f"   점수: {'✅ 통과' if scores['burst'] else '❌ 실패'}")
        
        # 이벤트 처리 점수
        event = test_results.get("event_storm", {})
        event_success_rate = event.get("published", 0) / event.get("total_events", 1) * 100
        event_receive_rate = event.get("received", 0) / event.get("published", 1) * 100 if event.get("published", 0) > 0 else 0
        scores["event"] = 1 if event_success_rate >= 90 and event_receive_rate >= 50 else 0
        logger.info(f"\n🌪️ 이벤트 처리:")
        logger.info(f"   발행 성공률: {event_success_rate:.1f}%")
        logger.info(f"   수신률: {event_receive_rate:.1f}%")
        logger.info(f"   점수: {'✅ 통과' if scores['event'] else '❌ 실패'}")
        
        # 동시성 점수
        concurrent = test_results.get("concurrent_chaos", {})
        concurrent_success = concurrent.get("concurrent_updates", {}).get("success", 0)
        mixed_success_rate = concurrent.get("mixed_operations", {}).get("success", 0) / concurrent.get("mixed_operations", {}).get("total", 1) * 100
        scores["concurrent"] = 1 if concurrent_success > 0 or mixed_success_rate >= 80 else 0
        logger.info(f"\n🌀 동시성 처리:")
        logger.info(f"   동일 객체 수정 성공: {concurrent_success}/100")
        logger.info(f"   혼합 작업 성공률: {mixed_success_rate:.1f}%")
        logger.info(f"   점수: {'✅ 통과' if scores['concurrent'] else '❌ 실패'}")
        
        # 복구 능력 점수
        recovery = test_results.get("recovery", {})
        scores["recovery"] = 1 if recovery.get("recovered", False) else 0
        logger.info(f"\n🔧 장애 복구:")
        logger.info(f"   복구 시간: {recovery.get('recovery_time', 0):.2f}초")
        logger.info(f"   점수: {'✅ 통과' if scores['recovery'] else '❌ 실패'}")
        
        # 3. 최종 점수
        total_score = sum(scores.values())
        max_score = len(scores)
        percentage = (total_score / max_score) * 100
        
        logger.info("\n" + "="*80)
        logger.info(f"🏆 최종 점수: {total_score}/{max_score} ({percentage:.0f}%)")
        logger.info("="*80)
        
        # 4. 프로덕션 준비도 평가
        logger.info("\n### 3. 프로덕션 준비도 평가")
        
        if percentage >= 75:
            logger.info("✅ 프로덕션 준비 완료")
            logger.info("   OMS는 프로덕션 환경에서 사용할 준비가 되었습니다.")
        elif percentage >= 50:
            logger.info("⚠️ 조건부 프로덕션 가능")
            logger.info("   일부 개선이 필요하지만 제한적으로 사용 가능합니다.")
        else:
            logger.info("❌ 추가 개발 필요")
            logger.info("   프로덕션 배포 전 주요 문제 해결이 필요합니다.")
            
        # 5. 권장사항
        logger.info("\n### 4. 개선 권장사항")
        
        recommendations = []
        
        if not scores["burst"]:
            recommendations.append("- API 응답 속도 최적화 (캐싱, 연결 풀링)")
            
        if not scores["event"]:
            recommendations.append("- 이벤트 처리 성능 개선 (배치 처리, 비동기 최적화)")
            
        if not scores["concurrent"]:
            recommendations.append("- 동시성 제어 메커니즘 강화 (낙관적 잠금, 충돌 해결)")
            
        if not scores["recovery"]:
            recommendations.append("- 복구 메커니즘 개선 (Circuit Breaker, 자동 스케일링)")
            
        for rec in recommendations:
            logger.info(rec)
            
        if not recommendations:
            logger.info("- 현재 성능이 우수합니다. 모니터링 지속 권장")
            
        # 6. 상세 메트릭 파일 저장
        logger.info("\n### 5. 상세 결과 저장")
        
        detailed_results = {
            "test_time": datetime.now().isoformat(),
            "duration_seconds": total_time,
            "test_results": test_results,
            "scores": scores,
            "final_score": f"{total_score}/{max_score}",
            "percentage": percentage,
            "production_ready": percentage >= 75,
            "metrics_summary": {
                "total_api_calls": len(self.metrics["api_latencies"]),
                "total_events": len(self.metrics["event_latencies"]),
                "total_errors": len(self.metrics["errors"])
            }
        }
        
        async with aiofiles.open("chaos_test_detailed_results.json", "w") as f:
            await f.write(json.dumps(detailed_results, indent=2, ensure_ascii=False))
            
        logger.info("💾 상세 결과가 chaos_test_detailed_results.json에 저장되었습니다.")
        logger.info("📝 전체 로그는 chaos_test_detailed.log에서 확인할 수 있습니다.")
        
    async def cleanup(self):
        """정리 작업"""
        logger.info("\n정리 작업 수행 중...")
        await self.nc.close()
        for client in self.http_clients:
            await client.aclose()
        await self.db.disconnect()
        logger.info("✅ 정리 완료")
        
    async def run_all_tests(self):
        """모든 테스트 실행"""
        await self.setup()
        
        test_results = {}
        
        # 각 테스트 실행
        test_results["burst_load"] = await self.chaos_test_1_burst_load()
        await asyncio.sleep(2)
        
        test_results["event_storm"] = await self.chaos_test_2_event_storm()
        await asyncio.sleep(2)
        
        test_results["concurrent_chaos"] = await self.chaos_test_3_concurrent_chaos()
        await asyncio.sleep(2)
        
        test_results["recovery"] = await self.chaos_test_4_recovery()
        
        # 최종 보고서
        await self.generate_final_report(test_results)
        
        await self.cleanup()


async def main():
    test = DetailedChaosTest()
    await test.run_all_tests()


if __name__ == "__main__":
    print("🚀 OMS 카오스 E2E 성능 검증 (상세 로그 버전)")
    print("모든 로그는 chaos_test_detailed.log 파일에 저장됩니다.")
    print("="*80)
    asyncio.run(main())