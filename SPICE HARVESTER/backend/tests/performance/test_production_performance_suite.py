"""
프로덕션 레벨 성능 테스트 스위트
대용량 페이로드, 동시 요청, 리소스 사용량 등 모든 성능 시나리오 검증

think ultra: 실제 프로덕션 환경에서 발생할 수 있는 모든 성능 병목 지점 테스트
NO SIMULATION - 실제 대용량 데이터와 실제 동시 요청으로 테스트
"""

import asyncio
import httpx
import json
import time
import psutil
import threading
import statistics
from typing import Dict, List, Any, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import random
import string
import gc
import sys
import tracemalloc
from test_config import TestConfig

# 성능 테스트 설정
OMS_BASE_URL = TestConfig.get_oms_base_url()
BFF_BASE_URL = TestConfig.get_bff_base_url()
PERFORMANCE_TEST_TIMEOUT = 60
MAX_PAYLOAD_SIZE = 10 * 1024 * 1024  # 10MB
MAX_CONCURRENT_USERS = 100

logger = logging.getLogger(__name__)


class ProductionPerformanceTestSuite:
    """프로덕션 레벨 성능 테스트 스위트"""
    
    def __init__(self):
        self.test_db_name = f"perf_test_{int(time.time())}"
        self.performance_results = {}
        self.resource_metrics = {}
        self.error_counts = {}
        self.response_times = []
        
        # 성능 임계값 설정 (프로덕션 기준)
        self.thresholds = {
            "max_response_time": 5.0,  # 5초
            "min_throughput": 10,      # 초당 10 요청
            "max_error_rate": 0.05,    # 5% 이하
            "max_memory_mb": 512,      # 512MB 이하
            "max_cpu_percent": 80      # 80% 이하
        }
    
    async def setup_performance_test_environment(self):
        """성능 테스트 환경 설정"""
        print("🚀 프로덕션 성능 테스트 환경 설정")
        
        # 메모리 추적 시작
        tracemalloc.start()
        
        # 테스트 데이터베이스 생성
        async with httpx.AsyncClient(timeout=PERFORMANCE_TEST_TIMEOUT) as client:
            response = await client.post(
                f"{OMS_BASE_URL}/api/v1/database/create",
                json={"name": self.test_db_name, "description": "Performance test database"}
            )
            if response.status_code not in [200, 409]:
                raise Exception(f"성능 테스트 DB 생성 실패: {response.status_code}")
        
        print(f"✅ 성능 테스트 환경 준비 완료: {self.test_db_name}")
    
    async def cleanup_performance_test_environment(self):
        """성능 테스트 환경 정리"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                await client.delete(f"{OMS_BASE_URL}/api/v1/database/{self.test_db_name}")
            print("✅ 성능 테스트 환경 정리 완료")
        except Exception as e:
            print(f"⚠️ 성능 테스트 정리 중 오류: {e}")
    
    def monitor_system_resources(self, duration: int = 60):
        """시스템 리소스 모니터링"""
        start_time = time.time()
        cpu_samples = []
        memory_samples = []
        
        def collect_metrics():
            while time.time() - start_time < duration:
                cpu_samples.append(psutil.cpu_percent(interval=1))
                memory_samples.append(psutil.virtual_memory().used / 1024 / 1024)  # MB
                time.sleep(1)
        
        monitor_thread = threading.Thread(target=collect_metrics)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        return monitor_thread, cpu_samples, memory_samples

    # =============================================================================
    # 1. 대용량 페이로드 성능 테스트
    # =============================================================================
    
    async def test_large_payload_performance(self):
        """대용량 페이로드 처리 성능 테스트"""
        print("\n📦 대용량 페이로드 성능 테스트")
        
        # 대용량 온톨로지 데이터 생성 (점진적으로 크기 증가)
        payload_sizes = [1, 10, 100, 500, 1000]  # 속성 개수
        
        async with httpx.AsyncClient(timeout=PERFORMANCE_TEST_TIMEOUT) as client:
            for size in payload_sizes:
                # 대용량 온톨로지 생성
                large_ontology = {
                    "id": f"LargeOntology{size}",
                    "label": f"Large Ontology with {size} properties",
                    "description": "Performance test ontology with many properties",
                    "properties": {}
                }
                
                # 많은 속성 추가
                for i in range(size):
                    large_ontology["properties"][f"property_{i}"] = "string"
                
                # 페이로드 크기 계산
                payload_json = json.dumps(large_ontology)
                payload_size_mb = len(payload_json.encode('utf-8')) / 1024 / 1024
                
                if payload_size_mb > 10:  # 10MB 초과 시 중단
                    print(f"⚠️ 페이로드 크기 한계 도달: {payload_size_mb:.2f}MB")
                    break
                
                # 성능 측정
                start_time = time.time()
                response = await client.post(
                    f"{OMS_BASE_URL}/api/v1/ontology/{self.test_db_name}/create",
                    json=large_ontology
                )
                end_time = time.time()
                
                response_time = end_time - start_time
                
                self.performance_results[f"large_payload_{size}"] = {
                    "payload_size_mb": payload_size_mb,
                    "properties_count": size,
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "success": response.status_code == 200
                }
                
                print(f"  📊 {size} 속성: {payload_size_mb:.2f}MB, {response_time:.2f}s, {response.status_code}")
                
                # 임계값 확인
                if response_time > self.thresholds["max_response_time"]:
                    print(f"⚠️ 응답 시간 임계값 초과: {response_time:.2f}s > {self.thresholds['max_response_time']}s")
        
        print("✅ 대용량 페이로드 성능 테스트 완료")

    # =============================================================================
    # 2. 동시 사용자 부하 테스트
    # =============================================================================
    
    async def test_concurrent_user_load(self):
        """동시 사용자 부하 테스트"""
        print("\n👥 동시 사용자 부하 테스트")
        
        # 리소스 모니터링 시작
        monitor_thread, cpu_samples, memory_samples = self.monitor_system_resources(60)
        
        concurrent_levels = [10, 25, 50, 75, 100]
        
        for concurrent_users in concurrent_levels:
            print(f"  🔄 동시 사용자 {concurrent_users}명 테스트")
            
            # 동시 요청 생성
            tasks = []
            start_time = time.time()
            
            async with httpx.AsyncClient(timeout=PERFORMANCE_TEST_TIMEOUT) as client:
                for user_id in range(concurrent_users):
                    ontology_data = {
                        "id": f"ConcurrentUser{concurrent_users}_{user_id}",
                        "label": f"Concurrent Test User {user_id}",
                        "properties": {
                            "user_id": "string",
                            "timestamp": "string",
                            "test_data": "string"
                        }
                    }
                    
                    task = client.post(
                        f"{OMS_BASE_URL}/api/v1/ontology/{self.test_db_name}/create",
                        json=ontology_data
                    )
                    tasks.append(task)
                
                # 모든 요청 동시 실행
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                end_time = time.time()
                
                # 결과 분석
                total_time = end_time - start_time
                successful_responses = sum(1 for r in responses if hasattr(r, 'status_code') and r.status_code == 200)
                duplicate_responses = sum(1 for r in responses if hasattr(r, 'status_code') and r.status_code == 409)
                error_responses = sum(1 for r in responses if not hasattr(r, 'status_code') or r.status_code >= 500)
                
                throughput = len(responses) / total_time
                error_rate = error_responses / len(responses)
                
                self.performance_results[f"concurrent_{concurrent_users}"] = {
                    "concurrent_users": concurrent_users,
                    "total_requests": len(responses),
                    "successful": successful_responses,
                    "duplicates": duplicate_responses,
                    "errors": error_responses,
                    "total_time": total_time,
                    "throughput": throughput,
                    "error_rate": error_rate
                }
                
                print(f"    📈 처리량: {throughput:.2f} req/s, 에러율: {error_rate:.2%}")
                
                # 임계값 확인
                if throughput < self.thresholds["min_throughput"]:
                    print(f"⚠️ 처리량 임계값 미달: {throughput:.2f} < {self.thresholds['min_throughput']}")
                
                if error_rate > self.thresholds["max_error_rate"]:
                    print(f"⚠️ 에러율 임계값 초과: {error_rate:.2%} > {self.thresholds['max_error_rate']:.2%}")
                
                # 시스템 부하 조절을 위한 대기
                await asyncio.sleep(2)
        
        # 리소스 사용량 분석
        monitor_thread.join(timeout=5)
        if cpu_samples and memory_samples:
            avg_cpu = statistics.mean(cpu_samples)
            max_cpu = max(cpu_samples)
            avg_memory = statistics.mean(memory_samples)
            max_memory = max(memory_samples)
            
            self.resource_metrics["load_test"] = {
                "avg_cpu_percent": avg_cpu,
                "max_cpu_percent": max_cpu,
                "avg_memory_mb": avg_memory,
                "max_memory_mb": max_memory
            }
            
            print(f"  💻 CPU 사용률: 평균 {avg_cpu:.1f}%, 최대 {max_cpu:.1f}%")
            print(f"  🧠 메모리 사용량: 평균 {avg_memory:.1f}MB, 최대 {max_memory:.1f}MB")
        
        print("✅ 동시 사용자 부하 테스트 완료")

    # =============================================================================
    # 3. 스트레스 테스트 (한계점 찾기)
    # =============================================================================
    
    async def test_stress_breaking_point(self):
        """스트레스 테스트 - 시스템 한계점 찾기"""
        print("\n💥 스트레스 테스트 (한계점 찾기)")
        
        max_concurrent = 200
        increment = 20
        
        for concurrent_level in range(20, max_concurrent + 1, increment):
            print(f"  🔥 스트레스 레벨 {concurrent_level}")
            
            tasks = []
            error_count = 0
            timeout_count = 0
            
            start_time = time.time()
            
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    for i in range(concurrent_level):
                        ontology_data = {
                            "id": f"StressTest{concurrent_level}_{i}",
                            "label": f"Stress Test {i}",
                            "properties": {"stress_prop": "string"}
                        }
                        
                        task = client.post(
                            f"{OMS_BASE_URL}/api/v1/ontology/{self.test_db_name}/create",
                            json=ontology_data
                        )
                        tasks.append(task)
                    
                    # 모든 요청 실행
                    responses = await asyncio.gather(*tasks, return_exceptions=True)
                    end_time = time.time()
                    
                    # 결과 분석
                    for response in responses:
                        if isinstance(response, Exception):
                            if "timeout" in str(response).lower():
                                timeout_count += 1
                            else:
                                error_count += 1
                        elif hasattr(response, 'status_code') and response.status_code >= 500:
                            error_count += 1
                    
                    total_time = end_time - start_time
                    success_count = len(responses) - error_count - timeout_count
                    throughput = len(responses) / total_time
                    error_rate = (error_count + timeout_count) / len(responses)
                    
                    self.performance_results[f"stress_{concurrent_level}"] = {
                        "stress_level": concurrent_level,
                        "success_count": success_count,
                        "error_count": error_count,
                        "timeout_count": timeout_count,
                        "throughput": throughput,
                        "error_rate": error_rate,
                        "total_time": total_time
                    }
                    
                    print(f"    📊 성공: {success_count}, 에러: {error_count}, 타임아웃: {timeout_count}")
                    print(f"    ⚡ 처리량: {throughput:.2f} req/s, 에러율: {error_rate:.2%}")
                    
                    # 시스템 한계점 판단 (에러율 50% 이상)
                    if error_rate > 0.5:
                        print(f"🚨 시스템 한계점 도달: 동시 요청 {concurrent_level}, 에러율 {error_rate:.2%}")
                        break
                    
                    # 회복 시간
                    await asyncio.sleep(3)
                    
            except Exception as e:
                print(f"💥 스트레스 테스트 중 예외 발생: {e}")
                break
        
        print("✅ 스트레스 테스트 완료")

    # =============================================================================
    # 4. 메모리 누수 테스트
    # =============================================================================
    
    async def test_memory_leak_detection(self):
        """메모리 누수 탐지 테스트"""
        print("\n🧠 메모리 누수 탐지 테스트")
        
        initial_memory = psutil.virtual_memory().used / 1024 / 1024
        memory_snapshots = [initial_memory]
        
        # 1000개의 요청을 10회 반복 (총 10,000 요청)
        iterations = 10
        requests_per_iteration = 100
        
        for iteration in range(iterations):
            print(f"  🔄 반복 {iteration + 1}/{iterations}")
            
            tasks = []
            async with httpx.AsyncClient(timeout=30) as client:
                for i in range(requests_per_iteration):
                    ontology_data = {
                        "id": f"MemoryTest{iteration}_{i}",
                        "label": f"Memory Test {iteration}_{i}",
                        "properties": {"test_prop": "string"}
                    }
                    
                    task = client.post(
                        f"{OMS_BASE_URL}/api/v1/ontology/{self.test_db_name}/create",
                        json=ontology_data
                    )
                    tasks.append(task)
                
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # 메모리 사용량 측정
            current_memory = psutil.virtual_memory().used / 1024 / 1024
            memory_snapshots.append(current_memory)
            
            print(f"    💾 메모리 사용량: {current_memory:.1f}MB (+{current_memory - initial_memory:.1f}MB)")
            
            # 가비지 컬렉션 강제 실행
            gc.collect()
            
            # 잠시 대기
            await asyncio.sleep(2)
        
        # 메모리 증가 추세 분석
        memory_increase = memory_snapshots[-1] - memory_snapshots[0]
        memory_growth_rate = memory_increase / iterations
        
        self.resource_metrics["memory_leak_test"] = {
            "initial_memory_mb": initial_memory,
            "final_memory_mb": memory_snapshots[-1],
            "total_increase_mb": memory_increase,
            "growth_rate_mb_per_iteration": memory_growth_rate,
            "memory_snapshots": memory_snapshots
        }
        
        print(f"  📈 총 메모리 증가: {memory_increase:.1f}MB")
        print(f"  📊 반복당 증가율: {memory_growth_rate:.2f}MB/iteration")
        
        # 메모리 누수 임계값 확인
        if memory_growth_rate > 5:  # 반복당 5MB 이상 증가 시 경고
            print(f"⚠️ 메모리 누수 의심: 반복당 {memory_growth_rate:.2f}MB 증가")
        else:
            print("✅ 메모리 사용량 안정적")
        
        print("✅ 메모리 누수 탐지 테스트 완료")

    # =============================================================================
    # 5. 응답 시간 분포 분석
    # =============================================================================
    
    async def test_response_time_distribution(self):
        """응답 시간 분포 분석"""
        print("\n⏱️ 응답 시간 분포 분석")
        
        response_times = []
        sample_size = 500
        
        async with httpx.AsyncClient(timeout=30) as client:
            for i in range(sample_size):
                ontology_data = {
                    "id": f"ResponseTimeTest{i}",
                    "label": f"Response Time Test {i}",
                    "properties": {"test_prop": "string"}
                }
                
                start_time = time.time()
                try:
                    response = await client.post(
                        f"{OMS_BASE_URL}/api/v1/ontology/{self.test_db_name}/create",
                        json=ontology_data
                    )
                    end_time = time.time()
                    
                    if response.status_code in [200, 409]:  # 성공 또는 중복
                        response_times.append(end_time - start_time)
                
                except Exception as e:
                    end_time = time.time()
                    response_times.append(end_time - start_time)  # 타임아웃도 포함
                
                # 진행 상황 표시 (100개마다)
                if (i + 1) % 100 == 0:
                    print(f"    진행: {i + 1}/{sample_size}")
        
        # 통계 분석
        if response_times:
            min_time = min(response_times)
            max_time = max(response_times)
            avg_time = statistics.mean(response_times)
            median_time = statistics.median(response_times)
            p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
            p99_time = sorted(response_times)[int(len(response_times) * 0.99)]
            
            self.performance_results["response_time_analysis"] = {
                "sample_size": len(response_times),
                "min_time": min_time,
                "max_time": max_time,
                "avg_time": avg_time,
                "median_time": median_time,
                "p95_time": p95_time,
                "p99_time": p99_time,
                "times_over_threshold": sum(1 for t in response_times if t > self.thresholds["max_response_time"])
            }
            
            print(f"  📊 응답 시간 통계:")
            print(f"    최소: {min_time:.3f}s")
            print(f"    최대: {max_time:.3f}s")
            print(f"    평균: {avg_time:.3f}s")
            print(f"    중간값: {median_time:.3f}s")
            print(f"    95%ile: {p95_time:.3f}s")
            print(f"    99%ile: {p99_time:.3f}s")
            
            slow_requests = sum(1 for t in response_times if t > self.thresholds["max_response_time"])
            slow_percentage = slow_requests / len(response_times) * 100
            print(f"    임계값({self.thresholds['max_response_time']}s) 초과: {slow_requests}건 ({slow_percentage:.1f}%)")
        
        print("✅ 응답 시간 분포 분석 완료")

    # =============================================================================
    # 6. 장시간 안정성 테스트
    # =============================================================================
    
    async def test_long_running_stability(self):
        """장시간 안정성 테스트"""
        print("\n🕒 장시간 안정성 테스트 (5분간)")
        
        duration_seconds = 300  # 5분
        request_interval = 1    # 1초마다 요청
        
        start_time = time.time()
        request_count = 0
        error_count = 0
        
        # 리소스 모니터링 시작
        monitor_thread, cpu_samples, memory_samples = self.monitor_system_resources(duration_seconds)
        
        async with httpx.AsyncClient(timeout=30) as client:
            while time.time() - start_time < duration_seconds:
                try:
                    ontology_data = {
                        "id": f"LongRunTest{request_count}",
                        "label": f"Long Running Test {request_count}",
                        "properties": {"test_prop": "string"}
                    }
                    
                    response = await client.post(
                        f"{OMS_BASE_URL}/api/v1/ontology/{self.test_db_name}/create",
                        json=ontology_data
                    )
                    
                    if response.status_code not in [200, 409]:
                        error_count += 1
                    
                    request_count += 1
                    
                    # 진행 상황 표시 (30초마다)
                    elapsed = time.time() - start_time
                    if request_count % 30 == 0:
                        print(f"    진행: {elapsed:.0f}s/{duration_seconds}s, 요청: {request_count}, 에러: {error_count}")
                    
                    await asyncio.sleep(request_interval)
                    
                except Exception as e:
                    error_count += 1
                    await asyncio.sleep(request_interval)
        
        total_time = time.time() - start_time
        avg_throughput = request_count / total_time
        error_rate = error_count / request_count if request_count > 0 else 1
        
        # 리소스 사용량 분석
        monitor_thread.join(timeout=5)
        resource_stability = {
            "cpu_stability": statistics.stdev(cpu_samples) if len(cpu_samples) > 1 else 0,
            "memory_stability": statistics.stdev(memory_samples) if len(memory_samples) > 1 else 0
        }
        
        self.performance_results["long_running_stability"] = {
            "duration_seconds": total_time,
            "total_requests": request_count,
            "error_count": error_count,
            "error_rate": error_rate,
            "avg_throughput": avg_throughput,
            "resource_stability": resource_stability
        }
        
        print(f"  📊 안정성 테스트 결과:")
        print(f"    총 요청: {request_count}")
        print(f"    에러: {error_count} ({error_rate:.2%})")
        print(f"    평균 처리량: {avg_throughput:.2f} req/s")
        print(f"    CPU 안정성: {resource_stability['cpu_stability']:.2f}% 표준편차")
        print(f"    메모리 안정성: {resource_stability['memory_stability']:.2f}MB 표준편차")
        
        print("✅ 장시간 안정성 테스트 완료")

    # =============================================================================
    # 메인 성능 테스트 실행기
    # =============================================================================
    
    async def run_comprehensive_performance_tests(self):
        """모든 성능 테스트 실행"""
        try:
            await self.setup_performance_test_environment()
            
            # 순차적으로 모든 성능 테스트 실행
            performance_test_methods = [
                self.test_large_payload_performance,
                self.test_concurrent_user_load,
                self.test_stress_breaking_point,
                self.test_memory_leak_detection,
                self.test_response_time_distribution,
                self.test_long_running_stability
            ]
            
            for test_method in performance_test_methods:
                try:
                    await test_method()
                    # 테스트 간 회복 시간
                    await asyncio.sleep(5)
                except Exception as e:
                    print(f"❌ {test_method.__name__} 실패: {e}")
                    self.performance_results[test_method.__name__] = {"error": str(e)}
            
            # 성능 리포트 생성
            self.generate_performance_report()
            
        finally:
            await self.cleanup_performance_test_environment()
    
    def generate_performance_report(self):
        """성능 테스트 결과 리포트 생성"""
        print("\n" + "="*80)
        print("🏁 프로덕션 성능 테스트 결과 리포트")
        print("="*80)
        
        # 성능 임계값 위반 사항 확인
        violations = []
        
        for test_name, results in self.performance_results.items():
            if isinstance(results, dict) and "error" not in results:
                # 응답 시간 확인
                if "response_time" in results and results["response_time"] > self.thresholds["max_response_time"]:
                    violations.append(f"{test_name}: 응답 시간 초과 ({results['response_time']:.2f}s)")
                
                # 처리량 확인
                if "throughput" in results and results["throughput"] < self.thresholds["min_throughput"]:
                    violations.append(f"{test_name}: 처리량 부족 ({results['throughput']:.2f} req/s)")
                
                # 에러율 확인
                if "error_rate" in results and results["error_rate"] > self.thresholds["max_error_rate"]:
                    violations.append(f"{test_name}: 에러율 초과 ({results['error_rate']:.2%})")
        
        # 리소스 사용량 확인
        for metric_name, metric_data in self.resource_metrics.items():
            if "max_cpu_percent" in metric_data and metric_data["max_cpu_percent"] > self.thresholds["max_cpu_percent"]:
                violations.append(f"{metric_name}: CPU 사용률 초과 ({metric_data['max_cpu_percent']:.1f}%)")
            
            if "max_memory_mb" in metric_data and metric_data["max_memory_mb"] > self.thresholds["max_memory_mb"]:
                violations.append(f"{metric_name}: 메모리 사용량 초과 ({metric_data['max_memory_mb']:.1f}MB)")
        
        # 결과 출력
        print(f"📊 성능 테스트 항목: {len(self.performance_results)}")
        print(f"💻 리소스 모니터링: {len(self.resource_metrics)}")
        
        if violations:
            print(f"\n⚠️ 성능 임계값 위반 사항: {len(violations)}")
            for violation in violations:
                print(f"  - {violation}")
        else:
            print("\n✅ 모든 성능 임계값 통과")
        
        # 상세 결과
        print("\n📈 상세 성능 결과:")
        for test_name, results in self.performance_results.items():
            print(f"\n  {test_name}:")
            if isinstance(results, dict):
                for key, value in results.items():
                    if isinstance(value, (int, float)):
                        if key.endswith("_time"):
                            print(f"    {key}: {value:.3f}s")
                        elif key.endswith("_rate"):
                            print(f"    {key}: {value:.2%}")
                        elif key.endswith("_mb"):
                            print(f"    {key}: {value:.1f}MB")
                        else:
                            print(f"    {key}: {value}")
                    else:
                        print(f"    {key}: {value}")
        
        # 전체 성능 점수 계산
        performance_score = max(0, 100 - len(violations) * 10)
        print(f"\n🎯 전체 성능 점수: {performance_score}/100")
        
        if performance_score >= 80:
            print("🚀 프로덕션 성능 기준 만족!")
        elif performance_score >= 60:
            print("⚠️ 성능 최적화 권장")
        else:
            print("🚨 성능 개선 필수")


# 성능 테스트 실행 함수
async def run_production_performance_tests():
    """프로덕션 성능 테스트 실행"""
    test_suite = ProductionPerformanceTestSuite()
    await test_suite.run_comprehensive_performance_tests()


if __name__ == "__main__":
    # 실제 성능 테스트 실행
    asyncio.run(run_production_performance_tests())