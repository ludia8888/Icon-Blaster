#!/usr/bin/env python3
"""
OMS 카오스 E2E 성능 검증 (Quick Version)
핵심 극한 상황 테스트
"""
import asyncio
import json
import sys
import os
from datetime import datetime
import httpx
import nats
import random
import statistics
import time
from typing import Dict, Any, List

sys.path.append('/Users/sihyun/Desktop/ARRAKIS/SPICE/oms-monolith')

from database.simple_terminus_client import SimpleTerminusDBClient

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class QuickChaosTest:
    """빠른 카오스 테스트"""
    
    def __init__(self):
        self.base_url = "http://localhost:8002"
        self.nats_url = "nats://localhost:4222"
        self.results = {
            "burst_test": {},
            "concurrent_chaos": {},
            "event_flood": {},
            "recovery_test": {}
        }
        
    async def setup(self):
        """환경 설정"""
        logger.info("🚀 카오스 E2E 성능 테스트 시작")
        
        # NATS 연결
        self.nc = await nats.connect(self.nats_url)
        
        # DB 연결
        self.db = SimpleTerminusDBClient(
            endpoint="http://localhost:6363",
            username="admin",
            password="root",
            database="oms"
        )
        await self.db.connect()
        
        # HTTP 클라이언트
        self.http = httpx.AsyncClient(timeout=10.0)
        
    async def test_1_burst_load(self):
        """Test 1: 순간 폭발적 부하"""
        logger.info("\n" + "="*60)
        logger.info("💥 Test 1: 순간 폭발적 부하 (200 동시 요청)")
        logger.info("="*60)
        
        results = {
            "total": 200,
            "success": 0,
            "failed": 0,
            "latencies": []
        }
        
        async def burst_request(i):
            start = time.time()
            try:
                if i % 3 == 0:  # CREATE
                    resp = await self.http.post(
                        f"{self.base_url}/api/v1/schemas/main/object-types",
                        json={
                            "name": f"Burst_{i}_{random.randint(1000,9999)}",
                            "displayName": f"폭발 {i}",
                            "description": "Burst test"
                        },
                        headers={"Authorization": f"Bearer burst-{i}"}
                    )
                elif i % 3 == 1:  # READ
                    resp = await self.http.get(
                        f"{self.base_url}/api/v1/schemas/main/object-types",
                        headers={"Authorization": f"Bearer burst-{i}"}
                    )
                else:  # HEALTH CHECK
                    resp = await self.http.get(f"{self.base_url}/health")
                    
                latency = (time.time() - start) * 1000
                
                if resp.status_code in [200, 201]:
                    return True, latency
                else:
                    return False, latency
                    
            except Exception as e:
                latency = (time.time() - start) * 1000
                return False, latency
                
        # 200개 동시 실행
        start_time = time.time()
        tasks = [burst_request(i) for i in range(200)]
        burst_results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        for success, latency in burst_results:
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1
            results["latencies"].append(latency)
            
        # 통계
        avg_latency = statistics.mean(results["latencies"])
        p95_latency = statistics.quantiles(results["latencies"], n=20)[18]
        
        logger.info(f"\n📊 결과:")
        logger.info(f"   성공: {results['success']}/{results['total']} ({results['success']/results['total']*100:.1f}%)")
        logger.info(f"   평균 지연: {avg_latency:.2f}ms")
        logger.info(f"   P95 지연: {p95_latency:.2f}ms")
        logger.info(f"   처리 속도: {results['total']/total_time:.2f} req/sec")
        
        self.results["burst_test"] = results
        return results
        
    async def test_2_concurrent_chaos(self):
        """Test 2: 동시 다발적 카오스"""
        logger.info("\n" + "="*60)
        logger.info("🌪️ Test 2: 동시 다발적 카오스")
        logger.info("="*60)
        
        results = {
            "concurrent_updates": 0,
            "race_conditions": 0,
            "conflicts_handled": 0
        }
        
        # 동일 객체에 대한 50개 동시 수정
        test_object_id = f"ChaosTest_{random.randint(1000,9999)}"
        
        # 먼저 객체 생성
        create_resp = await self.http.post(
            f"{self.base_url}/api/v1/schemas/main/object-types",
            json={
                "name": test_object_id,
                "displayName": "카오스 테스트 객체",
                "description": "동시 수정 테스트"
            },
            headers={"Authorization": "Bearer chaos-creator"}
        )
        
        if create_resp.status_code == 200:
            obj_data = create_resp.json()
            obj_id = obj_data.get('id', test_object_id)
            
            logger.info(f"\n🎯 {obj_id}에 50개 동시 수정 시도...")
            
            async def concurrent_update(i):
                try:
                    resp = await self.http.put(
                        f"{self.base_url}/api/v1/schemas/main/object-types/{obj_id}",
                        json={"description": f"동시 수정 #{i} at {datetime.now().isoformat()}"},
                        headers={"Authorization": f"Bearer user-{i}"}
                    )
                    return resp.status_code == 200
                except:
                    return False
                    
            tasks = [concurrent_update(i) for i in range(50)]
            update_results = await asyncio.gather(*tasks)
            
            results["concurrent_updates"] = sum(1 for r in update_results if r)
            results["race_conditions"] = 50 - results["concurrent_updates"]
            
        # 이벤트 + API + DB 동시 작업
        logger.info("\n🎯 이벤트 + API + DB 동시 작업...")
        
        async def multi_chaos():
            tasks = []
            
            # 10개 이벤트 발행
            for i in range(10):
                event = self.nc.publish(
                    f"oms.chaos.test",
                    json.dumps({"id": f"chaos-{i}", "time": datetime.now().isoformat()}).encode()
                )
                tasks.append(event)
                
            # 10개 API 호출
            for i in range(10):
                api_call = self.http.get(
                    f"{self.base_url}/api/v1/schemas/main/object-types",
                    headers={"Authorization": f"Bearer chaos-{i}"}
                )
                tasks.append(api_call)
                
            # 10개 DB 직접 조회
            for i in range(10):
                db_query = self.db.client.get(
                    "http://localhost:6363/api/document/admin/oms?type=ObjectType&limit=1",
                    auth=("admin", "root")
                )
                tasks.append(db_query)
                
            results_multi = await asyncio.gather(*tasks, return_exceptions=True)
            
            success_count = sum(1 for r in results_multi if not isinstance(r, Exception))
            results["conflicts_handled"] = success_count
            
        await multi_chaos()
        
        logger.info(f"\n📊 결과:")
        logger.info(f"   동시 수정 성공: {results['concurrent_updates']}/50")
        logger.info(f"   경쟁 상태 발생: {results['race_conditions']}")
        logger.info(f"   동시 작업 처리: {results['conflicts_handled']}/30")
        
        self.results["concurrent_chaos"] = results
        return results
        
    async def test_3_event_flood(self):
        """Test 3: 이벤트 홍수"""
        logger.info("\n" + "="*60)
        logger.info("🌊 Test 3: 이벤트 홍수 (1000 이벤트/초)")
        logger.info("="*60)
        
        results = {
            "events_sent": 0,
            "duration": 0,
            "events_per_second": 0
        }
        
        # 1000개 이벤트를 최대한 빠르게 발행
        start_time = time.time()
        
        for i in range(1000):
            event = {
                "specversion": "1.0",
                "type": "com.oms.flood.test",
                "source": "/oms/chaos",
                "id": f"flood-{i}",
                "time": datetime.now().isoformat(),
                "data": {"index": i, "random": random.random()}
            }
            
            try:
                await self.nc.publish(
                    f"oms.flood.{i%10}",
                    json.dumps(event).encode()
                )
                results["events_sent"] += 1
            except:
                pass
                
            # 10개마다 아주 짧은 대기
            if i % 10 == 0:
                await asyncio.sleep(0.001)
                
        results["duration"] = time.time() - start_time
        results["events_per_second"] = results["events_sent"] / results["duration"]
        
        logger.info(f"\n📊 결과:")
        logger.info(f"   발행된 이벤트: {results['events_sent']}")
        logger.info(f"   소요 시간: {results['duration']:.2f}초")
        logger.info(f"   처리 속도: {results['events_per_second']:.2f} events/sec")
        
        self.results["event_flood"] = results
        return results
        
    async def test_4_recovery(self):
        """Test 4: 장애 복구 테스트"""
        logger.info("\n" + "="*60)
        logger.info("🔧 Test 4: 장애 복구 능력")
        logger.info("="*60)
        
        results = {
            "baseline_latency": 0,
            "stressed_latency": 0,
            "recovery_time": 0,
            "recovered": False
        }
        
        # 1. 기준선 측정
        logger.info("\n📏 기준선 측정...")
        baseline_latencies = []
        
        for i in range(5):
            start = time.time()
            resp = await self.http.get(f"{self.base_url}/health")
            latency = (time.time() - start) * 1000
            baseline_latencies.append(latency)
            await asyncio.sleep(0.1)
            
        results["baseline_latency"] = statistics.mean(baseline_latencies)
        logger.info(f"   기준 응답시간: {results['baseline_latency']:.2f}ms")
        
        # 2. 스트레스 부하
        logger.info("\n💥 극심한 부하 가중...")
        
        async def stress_load():
            tasks = []
            for i in range(100):
                task = self.http.post(
                    f"{self.base_url}/api/v1/schemas/main/object-types",
                    json={
                        "name": f"Stress_{i}_{random.randint(1000,9999)}",
                        "displayName": f"스트레스 {i}",
                        "description": "x" * 1000
                    },
                    headers={"Authorization": f"Bearer stress-{i}"},
                    timeout=2.0
                )
                tasks.append(task)
                
            await asyncio.gather(*tasks, return_exceptions=True)
            
        await stress_load()
        
        # 스트레스 상태 측정
        stressed_latencies = []
        for i in range(3):
            start = time.time()
            try:
                resp = await self.http.get(f"{self.base_url}/health", timeout=2.0)
                latency = (time.time() - start) * 1000
                stressed_latencies.append(latency)
            except:
                stressed_latencies.append(2000)  # timeout
                
        results["stressed_latency"] = statistics.mean(stressed_latencies)
        logger.info(f"   스트레스 응답시간: {results['stressed_latency']:.2f}ms")
        
        # 3. 복구 시간 측정
        logger.info("\n⏱️ 복구 시간 측정...")
        recovery_start = time.time()
        
        while (time.time() - recovery_start) < 10:  # 최대 10초
            try:
                start = time.time()
                resp = await self.http.get(f"{self.base_url}/health", timeout=1.0)
                latency = (time.time() - start) * 1000
                
                # 기준선의 2배 이내로 돌아오면 복구
                if latency < results["baseline_latency"] * 2:
                    results["recovery_time"] = time.time() - recovery_start
                    results["recovered"] = True
                    break
                    
            except:
                pass
                
            await asyncio.sleep(0.5)
            
        logger.info(f"\n📊 결과:")
        logger.info(f"   기준 응답시간: {results['baseline_latency']:.2f}ms")
        logger.info(f"   스트레스 응답시간: {results['stressed_latency']:.2f}ms")
        logger.info(f"   복구 시간: {results['recovery_time']:.2f}초")
        logger.info(f"   복구 상태: {'✅ 성공' if results['recovered'] else '❌ 실패'}")
        
        self.results["recovery_test"] = results
        return results
        
    async def generate_report(self):
        """최종 보고서"""
        logger.info("\n" + "="*60)
        logger.info("📊 카오스 E2E 성능 테스트 결과")
        logger.info("="*60)
        
        # 1. 순간 부하 처리
        burst = self.results["burst_test"]
        burst_score = 1 if burst.get("success", 0) > 160 else 0  # 80% 이상
        
        logger.info("\n### 1. 순간 부하 처리 능력")
        logger.info(f"✅ 성공률: {burst.get('success', 0)/200*100:.1f}%")
        logger.info(f"⏱️ 평균 지연: {statistics.mean(burst.get('latencies', [0])):.2f}ms")
        logger.info(f"점수: {'✅' if burst_score else '❌'}")
        
        # 2. 동시성 처리
        chaos = self.results["concurrent_chaos"]
        chaos_score = 1 if chaos.get("concurrent_updates", 0) > 0 else 0
        
        logger.info("\n### 2. 동시성 및 경쟁 상태 처리")
        logger.info(f"✅ 동시 수정 처리: {chaos.get('concurrent_updates', 0)}/50")
        logger.info(f"✅ 멀티 작업 처리: {chaos.get('conflicts_handled', 0)}/30")
        logger.info(f"점수: {'✅' if chaos_score else '❌'}")
        
        # 3. 이벤트 처리
        flood = self.results["event_flood"]
        flood_score = 1 if flood.get("events_per_second", 0) > 500 else 0
        
        logger.info("\n### 3. 이벤트 처리 성능")
        logger.info(f"✅ 처리 속도: {flood.get('events_per_second', 0):.2f} events/sec")
        logger.info(f"점수: {'✅' if flood_score else '❌'}")
        
        # 4. 복구 능력
        recovery = self.results["recovery_test"]
        recovery_score = 1 if recovery.get("recovered", False) else 0
        
        logger.info("\n### 4. 장애 복구 능력")
        logger.info(f"✅ 복구 시간: {recovery.get('recovery_time', 0):.2f}초")
        logger.info(f"✅ 복구 상태: {'성공' if recovery.get('recovered', False) else '실패'}")
        logger.info(f"점수: {'✅' if recovery_score else '❌'}")
        
        # 총점
        total_score = burst_score + chaos_score + flood_score + recovery_score
        
        logger.info("\n" + "="*60)
        logger.info(f"🏆 최종 점수: {total_score}/4 ({total_score/4*100:.0f}%)")
        logger.info("="*60)
        
        if total_score >= 3:
            logger.info("\n✅ 프로덕션 준비 완료")
            logger.info("   - 순간 부하 처리 가능")
            logger.info("   - 동시성 문제 처리")
            logger.info("   - 높은 이벤트 처리량")
            logger.info("   - 빠른 복구 능력")
        else:
            logger.info("\n⚠️ 개선 필요 사항:")
            if not burst_score:
                logger.info("   - API 응답 속도 최적화")
            if not chaos_score:
                logger.info("   - 동시성 제어 강화")
            if not flood_score:
                logger.info("   - 이벤트 처리 성능 개선")
            if not recovery_score:
                logger.info("   - 장애 복구 메커니즘 강화")
                
        # 권장사항
        logger.info("\n💡 권장 사항:")
        logger.info("1. 연결 풀링 최적화")
        logger.info("2. 캐싱 전략 도입")
        logger.info("3. 비동기 처리 강화")
        logger.info("4. 로드 밸런싱 고려")
        
    async def cleanup(self):
        """정리"""
        await self.nc.close()
        await self.http.aclose()
        await self.db.disconnect()
        
    async def run(self):
        """전체 실행"""
        await self.setup()
        
        await self.test_1_burst_load()
        await asyncio.sleep(1)
        
        await self.test_2_concurrent_chaos()
        await asyncio.sleep(1)
        
        await self.test_3_event_flood()
        await asyncio.sleep(1)
        
        await self.test_4_recovery()
        
        await self.generate_report()
        
        await self.cleanup()


async def main():
    test = QuickChaosTest()
    await test.run()


if __name__ == "__main__":
    logger.info("🚀 OMS 카오스 E2E 성능 검증 (Quick Version)")
    asyncio.run(main())