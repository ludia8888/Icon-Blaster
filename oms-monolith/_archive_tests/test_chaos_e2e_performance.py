#!/usr/bin/env python3
"""
OMS 카오스 E2E 성능 검증 테스트
극한 상황에서의 시스템 안정성과 성능 검증
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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ChaosE2EPerformanceTest:
    """카오스 E2E 성능 테스트"""
    
    def __init__(self):
        self.base_url = "http://localhost:8002"
        self.nats_url = "nats://localhost:4222"
        self.metrics = {
            "api_latencies": [],
            "event_latencies": [],
            "db_latencies": [],
            "memory_usage": [],
            "cpu_usage": [],
            "errors": [],
            "successful_operations": 0,
            "failed_operations": 0
        }
        self.start_time = None
        self.event_counter = 0
        self.event_timestamps = {}  # 이벤트 발행 시간 추적
        
    async def setup(self):
        """환경 설정"""
        logger.info("🚀 카오스 E2E 성능 테스트 환경 설정")
        
        # NATS 연결
        self.nc = await nats.connect(self.nats_url)
        
        # 이벤트 수신 핸들러 (지연 시간 측정용)
        async def event_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                event_id = data.get('id')
                if event_id and event_id in self.event_timestamps:
                    # 이벤트 지연 시간 계산
                    latency = (datetime.now().timestamp() - self.event_timestamps[event_id]) * 1000
                    self.metrics["event_latencies"].append(latency)
                    del self.event_timestamps[event_id]  # 메모리 정리
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
        
        # HTTP 클라이언트 풀
        self.http_clients = [httpx.AsyncClient(timeout=30.0) for _ in range(10)]
        
        # 시스템 모니터링 시작
        self.monitoring_task = asyncio.create_task(self.monitor_system_resources())
        
        self.start_time = datetime.now()
        logger.info("✅ 테스트 환경 설정 완료")
        
    async def monitor_system_resources(self):
        """시스템 리소스 모니터링"""
        while True:
            try:
                # CPU 사용률
                cpu_percent = psutil.cpu_percent(interval=1)
                self.metrics["cpu_usage"].append(cpu_percent)
                
                # 메모리 사용률
                memory = psutil.virtual_memory()
                self.metrics["memory_usage"].append(memory.percent)
                
                await asyncio.sleep(5)  # 5초마다 측정
            except:
                break
                
    async def chaos_test_1_extreme_load(self):
        """Chaos Test 1: 극한 부하 테스트"""
        logger.info("\n" + "="*80)
        logger.info("💥 Chaos Test 1: 극한 부하 테스트")
        logger.info("="*80)
        
        results = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "avg_latency": 0,
            "max_latency": 0,
            "min_latency": float('inf'),
            "p95_latency": 0,
            "p99_latency": 0
        }
        
        # 1000개의 동시 요청
        logger.info("\n🔥 1000개 동시 API 요청 시작...")
        
        async def make_request(client_idx, req_idx):
            client = self.http_clients[client_idx % len(self.http_clients)]
            start = time.time()
            
            try:
                # 랜덤 작업 선택
                operation = random.choice(['create', 'read', 'update'])
                
                if operation == 'create':
                    response = await client.post(
                        f"{self.base_url}/api/v1/schemas/main/object-types",
                        json={
                            "name": f"ChaosType_{req_idx}_{random.randint(1000,9999)}",
                            "displayName": f"카오스 타입 {req_idx}",
                            "description": "극한 부하 테스트"
                        },
                        headers={"Authorization": f"Bearer chaos-user-{req_idx}"}
                    )
                elif operation == 'read':
                    response = await client.get(
                        f"{self.base_url}/api/v1/schemas/main/object-types",
                        headers={"Authorization": f"Bearer chaos-user-{req_idx}"}
                    )
                else:  # update
                    response = await client.get(
                        f"{self.base_url}/health"
                    )
                    
                latency = (time.time() - start) * 1000  # ms
                
                if response.status_code in [200, 201]:
                    self.metrics["api_latencies"].append(latency)
                    return True, latency
                else:
                    self.metrics["errors"].append({
                        "type": "http_error",
                        "status": response.status_code,
                        "operation": operation
                    })
                    return False, latency
                    
            except Exception as e:
                latency = (time.time() - start) * 1000
                self.metrics["errors"].append({
                    "type": "exception",
                    "error": str(e),
                    "operation": operation
                })
                return False, latency
                
        # 1000개 요청을 100개씩 배치로 실행
        batch_size = 100
        total_requests = 1000
        
        for batch in range(0, total_requests, batch_size):
            tasks = []
            for i in range(batch_size):
                if batch + i < total_requests:
                    tasks.append(make_request(i, batch + i))
                    
            batch_results = await asyncio.gather(*tasks)
            
            for success, latency in batch_results:
                results["total_requests"] += 1
                if success:
                    results["successful"] += 1
                else:
                    results["failed"] += 1
                    
                if latency < results["min_latency"]:
                    results["min_latency"] = latency
                if latency > results["max_latency"]:
                    results["max_latency"] = latency
                    
            # 배치 간 짧은 대기
            await asyncio.sleep(0.1)
            
        # 통계 계산
        if self.metrics["api_latencies"]:
            results["avg_latency"] = statistics.mean(self.metrics["api_latencies"])
            results["p95_latency"] = statistics.quantiles(self.metrics["api_latencies"], n=20)[18]  # 95th percentile
            results["p99_latency"] = statistics.quantiles(self.metrics["api_latencies"], n=100)[98]  # 99th percentile
            
        logger.info(f"\n📊 극한 부하 테스트 결과:")
        logger.info(f"   총 요청: {results['total_requests']}")
        logger.info(f"   성공: {results['successful']} ({results['successful']/results['total_requests']*100:.1f}%)")
        logger.info(f"   실패: {results['failed']}")
        logger.info(f"   평균 지연: {results['avg_latency']:.2f}ms")
        logger.info(f"   최소 지연: {results['min_latency']:.2f}ms")
        logger.info(f"   최대 지연: {results['max_latency']:.2f}ms")
        logger.info(f"   P95 지연: {results['p95_latency']:.2f}ms")
        logger.info(f"   P99 지연: {results['p99_latency']:.2f}ms")
        
        return results
        
    async def chaos_test_2_event_storm(self):
        """Chaos Test 2: 이벤트 폭풍"""
        logger.info("\n" + "="*80)
        logger.info("🌪️ Chaos Test 2: 이벤트 폭풍 (10,000 이벤트)")
        logger.info("="*80)
        
        results = {
            "total_events": 10000,
            "published": 0,
            "received": 0,
            "avg_event_latency": 0,
            "max_event_latency": 0,
            "events_per_second": 0
        }
        
        initial_received = len(self.metrics["event_latencies"])
        start_time = time.time()
        
        # 10,000개 이벤트 연속 발행
        logger.info("\n📤 10,000개 이벤트 발행 시작...")
        
        for i in range(results["total_events"]):
            event_id = f"chaos-event-{i}-{random.randint(1000,9999)}"
            self.event_timestamps[event_id] = datetime.now().timestamp()
            
            event = {
                "specversion": "1.0",
                "type": "com.oms.chaos.storm",
                "source": "/oms/chaos",
                "id": event_id,
                "time": datetime.now().isoformat(),
                "datacontenttype": "application/json",
                "data": {
                    "index": i,
                    "test": "event_storm",
                    "payload": "x" * random.randint(100, 1000)  # 가변 크기 페이로드
                }
            }
            
            subject = f"oms.chaos.storm.{i % 100}"  # 100개의 다른 주제로 분산
            
            try:
                await self.nc.publish(subject, json.dumps(event).encode())
                results["published"] += 1
                
                # 100개마다 짧은 대기
                if i % 100 == 0:
                    await asyncio.sleep(0.01)
                    
            except Exception as e:
                self.metrics["errors"].append({
                    "type": "event_publish_error",
                    "error": str(e)
                })
                
        publish_time = time.time() - start_time
        results["events_per_second"] = results["published"] / publish_time
        
        logger.info(f"✅ 발행 완료: {results['published']}개 ({publish_time:.2f}초)")
        logger.info(f"📊 발행 속도: {results['events_per_second']:.2f} events/sec")
        
        # 수신 대기
        logger.info("\n⏳ 이벤트 수신 대기 (5초)...")
        await asyncio.sleep(5)
        
        results["received"] = len(self.metrics["event_latencies"]) - initial_received
        
        # 이벤트 지연 통계
        if self.metrics["event_latencies"]:
            recent_latencies = self.metrics["event_latencies"][initial_received:]
            if recent_latencies:
                results["avg_event_latency"] = statistics.mean(recent_latencies)
                results["max_event_latency"] = max(recent_latencies)
                
        logger.info(f"\n📊 이벤트 폭풍 결과:")
        logger.info(f"   발행: {results['published']}")
        logger.info(f"   수신: {results['received']} ({results['received']/results['published']*100:.1f}%)")
        logger.info(f"   평균 지연: {results['avg_event_latency']:.2f}ms")
        logger.info(f"   최대 지연: {results['max_event_latency']:.2f}ms")
        
        return results
        
    async def chaos_test_3_memory_pressure(self):
        """Chaos Test 3: 메모리 압박 테스트"""
        logger.info("\n" + "="*80)
        logger.info("💾 Chaos Test 3: 메모리 압박 테스트")
        logger.info("="*80)
        
        results = {
            "large_objects_created": 0,
            "memory_before": 0,
            "memory_peak": 0,
            "memory_after": 0,
            "gc_collections": 0
        }
        
        # 초기 메모리 사용량
        memory_before = psutil.virtual_memory().percent
        results["memory_before"] = memory_before
        
        logger.info(f"\n💾 초기 메모리 사용률: {memory_before:.1f}%")
        
        # 대용량 객체 생성
        logger.info("\n🔥 대용량 메타데이터 객체 생성...")
        
        large_objects = []
        for i in range(100):
            # 큰 설명과 많은 속성을 가진 객체
            large_object = {
                "name": f"LargeObject_{i}_{random.randint(1000,9999)}",
                "displayName": f"대용량 객체 {i}",
                "description": "x" * 10000,  # 10KB 설명
                "metadata": {
                    f"field_{j}": f"value_{j}" * 100 
                    for j in range(50)  # 50개 필드
                },
                "tags": [f"tag_{k}" for k in range(100)]  # 100개 태그
            }
            
            try:
                response = await self.http_clients[0].post(
                    f"{self.base_url}/api/v1/schemas/main/object-types",
                    json=large_object,
                    headers={"Authorization": "Bearer memory-test"}
                )
                
                if response.status_code in [200, 201]:
                    results["large_objects_created"] += 1
                    large_objects.append(large_object)
                    
                # 메모리 사용량 추적
                current_memory = psutil.virtual_memory().percent
                if current_memory > results["memory_peak"]:
                    results["memory_peak"] = current_memory
                    
            except Exception as e:
                self.metrics["errors"].append({
                    "type": "memory_test_error",
                    "error": str(e)
                })
                
        # 동시에 많은 조회 요청
        logger.info("\n🔥 대량 동시 조회 요청...")
        
        async def bulk_read():
            tasks = []
            for i in range(50):
                task = self.http_clients[i % len(self.http_clients)].get(
                    f"{self.base_url}/api/v1/schemas/main/object-types",
                    headers={"Authorization": f"Bearer reader-{i}"}
                )
                tasks.append(task)
                
            await asyncio.gather(*tasks, return_exceptions=True)
            
        await bulk_read()
        
        # 최종 메모리 사용량
        await asyncio.sleep(2)
        results["memory_after"] = psutil.virtual_memory().percent
        
        logger.info(f"\n📊 메모리 압박 테스트 결과:")
        logger.info(f"   대용량 객체 생성: {results['large_objects_created']}")
        logger.info(f"   초기 메모리: {results['memory_before']:.1f}%")
        logger.info(f"   최대 메모리: {results['memory_peak']:.1f}%")
        logger.info(f"   최종 메모리: {results['memory_after']:.1f}%")
        logger.info(f"   메모리 증가: {results['memory_peak'] - results['memory_before']:.1f}%")
        
        return results
        
    async def chaos_test_4_connection_chaos(self):
        """Chaos Test 4: 연결 카오스"""
        logger.info("\n" + "="*80)
        logger.info("🔌 Chaos Test 4: 연결 카오스 (연결/해제 반복)")
        logger.info("="*80)
        
        results = {
            "connection_attempts": 0,
            "successful_connections": 0,
            "failed_connections": 0,
            "reconnection_time": [],
            "operations_during_chaos": 0
        }
        
        # 연결 생성/해제 반복
        logger.info("\n🔥 500개 연결 생성/해제 반복...")
        
        async def connection_chaos():
            for i in range(500):
                try:
                    # 새 클라이언트 생성
                    client = httpx.AsyncClient(timeout=5.0)
                    results["connection_attempts"] += 1
                    
                    # 즉시 요청
                    response = await client.get(f"{self.base_url}/health")
                    
                    if response.status_code == 200:
                        results["successful_connections"] += 1
                        
                    # 랜덤하게 연결 유지 또는 즉시 종료
                    if random.random() > 0.5:
                        await asyncio.sleep(random.uniform(0.01, 0.1))
                        
                    await client.aclose()
                    
                except Exception as e:
                    results["failed_connections"] += 1
                    self.metrics["errors"].append({
                        "type": "connection_error",
                        "error": str(e)
                    })
                    
                # 10개마다 짧은 대기
                if i % 10 == 0:
                    await asyncio.sleep(0.01)
                    
        # 연결 카오스와 동시에 정상 작업 수행
        async def normal_operations():
            while results["connection_attempts"] < 500:
                try:
                    response = await self.http_clients[0].get(
                        f"{self.base_url}/api/v1/schemas/main/object-types",
                        headers={"Authorization": "Bearer normal-user"}
                    )
                    
                    if response.status_code == 200:
                        results["operations_during_chaos"] += 1
                        
                except:
                    pass
                    
                await asyncio.sleep(0.1)
                
        # 동시 실행
        await asyncio.gather(
            connection_chaos(),
            normal_operations()
        )
        
        logger.info(f"\n📊 연결 카오스 결과:")
        logger.info(f"   연결 시도: {results['connection_attempts']}")
        logger.info(f"   성공: {results['successful_connections']} ({results['successful_connections']/results['connection_attempts']*100:.1f}%)")
        logger.info(f"   실패: {results['failed_connections']}")
        logger.info(f"   카오스 중 정상 작업: {results['operations_during_chaos']}")
        
        return results
        
    async def chaos_test_5_cascade_failure(self):
        """Chaos Test 5: 연쇄 장애 시뮬레이션"""
        logger.info("\n" + "="*80)
        logger.info("⛓️ Chaos Test 5: 연쇄 장애 시뮬레이션")
        logger.info("="*80)
        
        results = {
            "db_operations": {"success": 0, "failed": 0},
            "api_operations": {"success": 0, "failed": 0},
            "event_operations": {"success": 0, "failed": 0},
            "recovery_time": 0,
            "degraded_performance": False
        }
        
        # Phase 1: 정상 작동 확인
        logger.info("\n1️⃣ Phase 1: 정상 작동 기준선 측정...")
        
        baseline_start = time.time()
        
        # 정상 작동 테스트
        for i in range(10):
            try:
                # API 호출
                response = await self.http_clients[0].get(f"{self.base_url}/health")
                if response.status_code == 200:
                    results["api_operations"]["success"] += 1
                    
                # 이벤트 발행
                await self.nc.publish("oms.test", b"test")
                results["event_operations"]["success"] += 1
                
            except:
                pass
                
        baseline_time = time.time() - baseline_start
        
        # Phase 2: 부하 증가로 성능 저하 유도
        logger.info("\n2️⃣ Phase 2: 극심한 부하로 성능 저하 유도...")
        
        async def heavy_load():
            tasks = []
            for i in range(200):
                task = self.http_clients[i % len(self.http_clients)].post(
                    f"{self.base_url}/api/v1/schemas/main/object-types",
                    json={
                        "name": f"LoadTest_{i}_{random.randint(1000,9999)}",
                        "displayName": f"부하 테스트 {i}",
                        "description": "x" * 5000
                    },
                    headers={"Authorization": f"Bearer load-{i}"},
                    timeout=2.0
                )
                tasks.append(task)
                
            results_heavy = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results_heavy:
                if isinstance(result, Exception):
                    results["api_operations"]["failed"] += 1
                else:
                    results["api_operations"]["success"] += 1
                    
        await heavy_load()
        
        # Phase 3: 복구 시간 측정
        logger.info("\n3️⃣ Phase 3: 시스템 복구 시간 측정...")
        
        recovery_start = time.time()
        recovered = False
        
        while not recovered and (time.time() - recovery_start) < 30:  # 최대 30초 대기
            try:
                response = await self.http_clients[0].get(
                    f"{self.base_url}/health",
                    timeout=1.0
                )
                
                if response.status_code == 200:
                    # 응답 시간이 정상 수준으로 돌아왔는지 확인
                    test_start = time.time()
                    await self.http_clients[0].get(f"{self.base_url}/health")
                    test_time = time.time() - test_start
                    
                    if test_time < baseline_time * 2:  # 기준선의 2배 이내
                        recovered = True
                        results["recovery_time"] = time.time() - recovery_start
                        
            except:
                pass
                
            await asyncio.sleep(0.5)
            
        logger.info(f"\n📊 연쇄 장애 시뮬레이션 결과:")
        logger.info(f"   API 성공/실패: {results['api_operations']['success']}/{results['api_operations']['failed']}")
        logger.info(f"   이벤트 작업: {results['event_operations']['success']}")
        logger.info(f"   복구 시간: {results['recovery_time']:.2f}초")
        logger.info(f"   시스템 복구: {'✅ 성공' if recovered else '❌ 실패'}")
        
        return results
        
    async def generate_performance_report(self, test_results):
        """성능 보고서 생성"""
        logger.info("\n" + "="*80)
        logger.info("📊 카오스 E2E 성능 테스트 최종 보고서")
        logger.info("="*80)
        
        total_time = (datetime.now() - self.start_time).total_seconds()
        
        # 1. 전체 성능 지표
        logger.info("\n### 1. 전체 성능 지표")
        logger.info(f"⏱️ 총 테스트 시간: {total_time:.2f}초")
        logger.info(f"✅ 성공한 작업: {self.metrics['successful_operations']}")
        logger.info(f"❌ 실패한 작업: {self.metrics['failed_operations']}")
        logger.info(f"📍 총 오류 수: {len(self.metrics['errors'])}")
        
        # 2. API 성능
        logger.info("\n### 2. API 성능 분석")
        if self.metrics["api_latencies"]:
            logger.info(f"📊 API 요청 수: {len(self.metrics['api_latencies'])}")
            logger.info(f"⏱️ 평균 응답 시간: {statistics.mean(self.metrics['api_latencies']):.2f}ms")
            logger.info(f"⏱️ 중간값: {statistics.median(self.metrics['api_latencies']):.2f}ms")
            logger.info(f"⏱️ P95: {statistics.quantiles(self.metrics['api_latencies'], n=20)[18]:.2f}ms")
            logger.info(f"⏱️ P99: {statistics.quantiles(self.metrics['api_latencies'], n=100)[98]:.2f}ms")
            
        # 3. 이벤트 성능
        logger.info("\n### 3. 이벤트 처리 성능")
        if self.metrics["event_latencies"]:
            logger.info(f"📊 처리된 이벤트: {len(self.metrics['event_latencies'])}")
            logger.info(f"⏱️ 평균 이벤트 지연: {statistics.mean(self.metrics['event_latencies']):.2f}ms")
            logger.info(f"⏱️ 최대 지연: {max(self.metrics['event_latencies']):.2f}ms")
            
        # 4. 시스템 리소스
        logger.info("\n### 4. 시스템 리소스 사용")
        if self.metrics["cpu_usage"]:
            logger.info(f"🖥️ 평균 CPU 사용률: {statistics.mean(self.metrics['cpu_usage']):.1f}%")
            logger.info(f"🖥️ 최대 CPU 사용률: {max(self.metrics['cpu_usage']):.1f}%")
            
        if self.metrics["memory_usage"]:
            logger.info(f"💾 평균 메모리 사용률: {statistics.mean(self.metrics['memory_usage']):.1f}%")
            logger.info(f"💾 최대 메모리 사용률: {max(self.metrics['memory_usage']):.1f}%")
            
        # 5. 오류 분석
        logger.info("\n### 5. 오류 분석")
        error_types = {}
        for error in self.metrics["errors"]:
            error_type = error.get("type", "unknown")
            error_types[error_type] = error_types.get(error_type, 0) + 1
            
        for error_type, count in error_types.items():
            logger.info(f"   {error_type}: {count}개")
            
        # 6. 극한 상황 평가
        logger.info("\n### 6. 극한 상황 처리 능력")
        
        # 점수 계산
        score = 0
        total_score = 5
        
        # 극한 부하 테스트
        if test_results["extreme_load"]["successful"] > 800:  # 80% 이상
            score += 1
            logger.info("✅ 극한 부하: 1000개 동시 요청 중 80% 이상 성공")
        else:
            logger.info("❌ 극한 부하: 성능 개선 필요")
            
        # 이벤트 폭풍
        if test_results["event_storm"]["received"] > 8000:  # 80% 이상
            score += 1
            logger.info("✅ 이벤트 폭풍: 10,000개 이벤트 중 80% 이상 처리")
        else:
            logger.info("❌ 이벤트 폭풍: 이벤트 처리 개선 필요")
            
        # 메모리 압박
        memory_increase = test_results["memory_pressure"]["memory_peak"] - test_results["memory_pressure"]["memory_before"]
        if memory_increase < 20:  # 20% 미만 증가
            score += 1
            logger.info("✅ 메모리 관리: 안정적")
        else:
            logger.info("⚠️ 메모리 관리: 주의 필요")
            
        # 연결 카오스
        if test_results["connection_chaos"]["successful_connections"] > 450:  # 90% 이상
            score += 1
            logger.info("✅ 연결 안정성: 우수")
        else:
            logger.info("❌ 연결 안정성: 개선 필요")
            
        # 복구 능력
        if test_results["cascade_failure"]["recovery_time"] < 5:  # 5초 이내
            score += 1
            logger.info("✅ 복구 능력: 빠른 복구")
        else:
            logger.info("⚠️ 복구 능력: 개선 여지 있음")
            
        logger.info(f"\n🏆 극한 상황 점수: {score}/{total_score} ({score/total_score*100:.0f}%)")
        
        # 7. 프로덕션 준비도
        logger.info("\n### 7. 프로덕션 준비도 평가")
        
        production_ready = score >= 3  # 60% 이상
        
        if production_ready:
            logger.info("✅ 프로덕션 준비 완료")
            logger.info("   - 극한 부하 처리 가능")
            logger.info("   - 안정적인 이벤트 처리")
            logger.info("   - 적절한 리소스 관리")
        else:
            logger.info("⚠️ 프로덕션 배포 전 개선 필요")
            logger.info("   권장 사항:")
            logger.info("   - API 응답 시간 최적화")
            logger.info("   - 이벤트 처리 용량 증대")
            logger.info("   - 연결 풀 관리 개선")
            
        # 8. 권장 사항
        logger.info("\n### 8. 성능 개선 권장 사항")
        
        if statistics.mean(self.metrics["api_latencies"]) > 500:
            logger.info("1. API 캐싱 도입 검토")
            
        if len(self.metrics["errors"]) > 100:
            logger.info("2. 오류 처리 및 재시도 로직 강화")
            
        if max(self.metrics["memory_usage"]) > 80:
            logger.info("3. 메모리 사용 최적화 필요")
            
        logger.info("4. 로드 밸런서 도입 검토")
        logger.info("5. 데이터베이스 인덱싱 최적화")
        
        # 결과 저장
        report_data = {
            "test_time": datetime.now().isoformat(),
            "duration_seconds": total_time,
            "metrics": {
                "api_requests": len(self.metrics["api_latencies"]),
                "events_processed": len(self.metrics["event_latencies"]),
                "errors": len(self.metrics["errors"]),
                "avg_api_latency": statistics.mean(self.metrics["api_latencies"]) if self.metrics["api_latencies"] else 0,
                "avg_event_latency": statistics.mean(self.metrics["event_latencies"]) if self.metrics["event_latencies"] else 0,
            },
            "test_results": test_results,
            "production_ready": production_ready,
            "score": f"{score}/{total_score}"
        }
        
        # JSON 파일로 저장
        async with aiofiles.open("chaos_e2e_performance_report.json", "w") as f:
            await f.write(json.dumps(report_data, indent=2))
            
        logger.info("\n💾 상세 보고서가 chaos_e2e_performance_report.json에 저장되었습니다.")
        
    async def cleanup(self):
        """정리 작업"""
        self.monitoring_task.cancel()
        await self.nc.close()
        for client in self.http_clients:
            await client.aclose()
        await self.db.disconnect()
        
    async def run_all_tests(self):
        """모든 카오스 테스트 실행"""
        await self.setup()
        
        test_results = {}
        
        # 각 카오스 테스트 실행
        test_results["extreme_load"] = await self.chaos_test_1_extreme_load()
        await asyncio.sleep(2)  # 테스트 간 휴식
        
        test_results["event_storm"] = await self.chaos_test_2_event_storm()
        await asyncio.sleep(2)
        
        test_results["memory_pressure"] = await self.chaos_test_3_memory_pressure()
        await asyncio.sleep(2)
        
        test_results["connection_chaos"] = await self.chaos_test_4_connection_chaos()
        await asyncio.sleep(2)
        
        test_results["cascade_failure"] = await self.chaos_test_5_cascade_failure()
        
        # 최종 보고서 생성
        await self.generate_performance_report(test_results)
        
        await self.cleanup()


async def main():
    """메인 실행"""
    test = ChaosE2EPerformanceTest()
    await test.run_all_tests()


if __name__ == "__main__":
    logger.info("🚀 OMS 카오스 E2E 성능 검증 시작")
    logger.info("극한 상황에서의 시스템 안정성과 성능을 검증합니다...")
    asyncio.run(main())