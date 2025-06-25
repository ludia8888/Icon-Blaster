"""
성능 벤치마크 테스트
대량 엔티티 검증, 메모리 사용량, 동시성 테스트
"""
import time
import psutil
import os
import gc
import concurrent.futures
from typing import List, Dict, Tuple
import statistics
import json
from dataclasses import dataclass

from core.validation.naming_convention import (
    NamingConventionEngine, EntityType, get_naming_engine
)
from core.validation.naming_config import get_naming_config_service


@dataclass
class BenchmarkResult:
    """벤치마크 결과"""
    name: str
    total_operations: int
    total_time: float
    avg_time: float
    min_time: float
    max_time: float
    std_dev: float
    ops_per_second: float
    memory_used_mb: float
    
    def __str__(self):
        return f"""
=== {self.name} ===
Total Operations: {self.total_operations:,}
Total Time: {self.total_time:.3f}s
Average Time: {self.avg_time * 1000:.3f}ms
Min Time: {self.min_time * 1000:.3f}ms
Max Time: {self.max_time * 1000:.3f}ms
Std Dev: {self.std_dev * 1000:.3f}ms
Operations/Second: {self.ops_per_second:,.0f}
Memory Used: {self.memory_used_mb:.2f} MB
"""


class NamingBenchmark:
    """명명 규칙 검증 벤치마크"""
    
    def __init__(self):
        self.engine = get_naming_engine()
        self.process = psutil.Process(os.getpid())
    
    def generate_test_names(self, count: int) -> List[Tuple[EntityType, str]]:
        """테스트용 이름 생성"""
        names = []
        
        # 다양한 패턴의 이름 생성
        patterns = [
            # 유효한 이름들
            ("Product", "ProductManager", "ProductType"),
            ("User", "UserAccount", "UserProfile"),
            ("Order", "OrderItem", "OrderStatus"),
            # 무효한 이름들
            ("product", "_Product", "Product_Type"),
            ("123Product", "Product!", "Pro duct"),
            # 복잡한 이름들
            ("HTTPServerManager", "OAuth2Provider", "XMLHttpRequest"),
            ("APIv3Client", "DB2Connection", "HTTP2ServerError"),
        ]
        
        entity_types = [
            EntityType.OBJECT_TYPE,
            EntityType.PROPERTY,
            EntityType.LINK_TYPE,
            EntityType.FUNCTION_TYPE,
        ]
        
        # 지정된 수만큼 이름 생성
        for i in range(count):
            pattern_group = patterns[i % len(patterns)]
            name = pattern_group[i % len(pattern_group)]
            entity_type = entity_types[i % len(entity_types)]
            
            # 변형 추가
            if i % 5 == 0:
                name = name.lower()
            elif i % 7 == 0:
                name = name + str(i)
            elif i % 11 == 0:
                name = "_" + name
            
            names.append((entity_type, name))
        
        return names
    
    def benchmark_single_validation(self, iterations: int = 1000) -> BenchmarkResult:
        """단일 검증 성능 측정"""
        test_names = self.generate_test_names(iterations)
        times = []
        
        # 워밍업
        for _ in range(100):
            self.engine.validate(EntityType.OBJECT_TYPE, "TestObject")
        
        # 메모리 측정 시작
        gc.collect()
        start_memory = self.process.memory_info().rss / 1024 / 1024
        
        # 벤치마크 실행
        total_start = time.perf_counter()
        
        for entity_type, name in test_names:
            start = time.perf_counter()
            self.engine.validate(entity_type, name)
            elapsed = time.perf_counter() - start
            times.append(elapsed)
        
        total_time = time.perf_counter() - total_start
        
        # 메모리 측정 종료
        end_memory = self.process.memory_info().rss / 1024 / 1024
        memory_used = end_memory - start_memory
        
        return BenchmarkResult(
            name="Single Validation Benchmark",
            total_operations=iterations,
            total_time=total_time,
            avg_time=statistics.mean(times),
            min_time=min(times),
            max_time=max(times),
            std_dev=statistics.stdev(times) if len(times) > 1 else 0,
            ops_per_second=iterations / total_time,
            memory_used_mb=memory_used
        )
    
    def benchmark_10k_entities(self) -> BenchmarkResult:
        """10,000개 엔티티 검증 성능 측정"""
        test_names = self.generate_test_names(10000)
        
        gc.collect()
        start_memory = self.process.memory_info().rss / 1024 / 1024
        
        start_time = time.perf_counter()
        
        for entity_type, name in test_names:
            self.engine.validate(entity_type, name)
        
        total_time = time.perf_counter() - start_time
        
        end_memory = self.process.memory_info().rss / 1024 / 1024
        memory_used = end_memory - start_memory
        
        return BenchmarkResult(
            name="10K Entities Benchmark",
            total_operations=10000,
            total_time=total_time,
            avg_time=total_time / 10000,
            min_time=total_time / 10000,  # 평균값 사용
            max_time=total_time / 10000,
            std_dev=0,
            ops_per_second=10000 / total_time,
            memory_used_mb=memory_used
        )
    
    def benchmark_memory_usage(self) -> Dict[str, float]:
        """메모리 사용량 프로파일링"""
        results = {}
        
        # 초기 메모리
        gc.collect()
        initial_memory = self.process.memory_info().rss / 1024 / 1024
        results['initial_mb'] = initial_memory
        
        # 엔진 생성 후
        engine = get_naming_engine()
        after_engine = self.process.memory_info().rss / 1024 / 1024
        results['after_engine_mb'] = after_engine
        results['engine_overhead_mb'] = after_engine - initial_memory
        
        # 1000번 검증 후
        for i in range(1000):
            engine.validate(EntityType.OBJECT_TYPE, f"TestObject{i}")
        
        after_1k = self.process.memory_info().rss / 1024 / 1024
        results['after_1k_validations_mb'] = after_1k
        results['validation_overhead_mb'] = after_1k - after_engine
        
        # 캐시 효과 측정 (같은 이름 반복)
        for _ in range(1000):
            engine.validate(EntityType.OBJECT_TYPE, "CachedObject")
        
        after_cache = self.process.memory_info().rss / 1024 / 1024
        results['after_cache_test_mb'] = after_cache
        results['cache_overhead_mb'] = after_cache - after_1k
        
        # GC 후
        gc.collect()
        after_gc = self.process.memory_info().rss / 1024 / 1024
        results['after_gc_mb'] = after_gc
        results['gc_freed_mb'] = after_cache - after_gc
        
        return results
    
    def benchmark_concurrent_validation(self, workers: int = 4, total_ops: int = 10000) -> BenchmarkResult:
        """동시 검증 성능 측정"""
        test_names = self.generate_test_names(total_ops)
        ops_per_worker = total_ops // workers
        
        def worker_task(names_chunk):
            """워커 태스크"""
            engine = get_naming_engine()
            times = []
            
            for entity_type, name in names_chunk:
                start = time.perf_counter()
                engine.validate(entity_type, name)
                elapsed = time.perf_counter() - start
                times.append(elapsed)
            
            return times
        
        # 작업 분할
        chunks = []
        for i in range(workers):
            start_idx = i * ops_per_worker
            end_idx = start_idx + ops_per_worker if i < workers - 1 else total_ops
            chunks.append(test_names[start_idx:end_idx])
        
        gc.collect()
        start_memory = self.process.memory_info().rss / 1024 / 1024
        
        # 동시 실행
        start_time = time.perf_counter()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(worker_task, chunk) for chunk in chunks]
            all_times = []
            
            for future in concurrent.futures.as_completed(futures):
                all_times.extend(future.result())
        
        total_time = time.perf_counter() - start_time
        
        end_memory = self.process.memory_info().rss / 1024 / 1024
        memory_used = end_memory - start_memory
        
        return BenchmarkResult(
            name=f"Concurrent Validation ({workers} workers)",
            total_operations=total_ops,
            total_time=total_time,
            avg_time=statistics.mean(all_times),
            min_time=min(all_times),
            max_time=max(all_times),
            std_dev=statistics.stdev(all_times),
            ops_per_second=total_ops / total_time,
            memory_used_mb=memory_used
        )
    
    def benchmark_pattern_complexity(self) -> Dict[str, BenchmarkResult]:
        """패턴 복잡도별 성능 측정"""
        results = {}
        
        # 간단한 패턴
        simple_names = ["Product", "User", "Order"] * 100
        
        # 복잡한 패턴 (약어, 숫자 포함)
        complex_names = ["HTTPServer", "OAuth2Token", "APIv3Client"] * 100
        
        # 매우 복잡한 패턴
        very_complex_names = ["HTTP2ServerErrorHandler", "OAuth2TokenProviderFactory", "XMLHttpRequestManagerV2"] * 100
        
        test_sets = [
            ("Simple Patterns", simple_names),
            ("Complex Patterns", complex_names),
            ("Very Complex Patterns", very_complex_names),
        ]
        
        for name, test_names in test_sets:
            times = []
            
            gc.collect()
            start_memory = self.process.memory_info().rss / 1024 / 1024
            
            total_start = time.perf_counter()
            
            for test_name in test_names:
                start = time.perf_counter()
                self.engine.validate(EntityType.OBJECT_TYPE, test_name)
                elapsed = time.perf_counter() - start
                times.append(elapsed)
            
            total_time = time.perf_counter() - total_start
            
            end_memory = self.process.memory_info().rss / 1024 / 1024
            memory_used = end_memory - start_memory
            
            results[name] = BenchmarkResult(
                name=name,
                total_operations=len(test_names),
                total_time=total_time,
                avg_time=statistics.mean(times),
                min_time=min(times),
                max_time=max(times),
                std_dev=statistics.stdev(times),
                ops_per_second=len(test_names) / total_time,
                memory_used_mb=memory_used
            )
        
        return results
    
    def benchmark_auto_fix_performance(self, iterations: int = 1000) -> BenchmarkResult:
        """자동 수정 성능 측정"""
        # 수정이 필요한 이름들
        invalid_names = [
            ("product_manager", EntityType.OBJECT_TYPE),
            ("FirstName", EntityType.PROPERTY),
            ("product", EntityType.LINK_TYPE),
            ("HTTPClient", EntityType.ACTION_TYPE),
        ] * (iterations // 4)
        
        times = []
        
        gc.collect()
        start_memory = self.process.memory_info().rss / 1024 / 1024
        
        total_start = time.perf_counter()
        
        for name, entity_type in invalid_names:
            start = time.perf_counter()
            self.engine.auto_fix(entity_type, name)
            elapsed = time.perf_counter() - start
            times.append(elapsed)
        
        total_time = time.perf_counter() - total_start
        
        end_memory = self.process.memory_info().rss / 1024 / 1024
        memory_used = end_memory - start_memory
        
        return BenchmarkResult(
            name="Auto-fix Performance",
            total_operations=len(invalid_names),
            total_time=total_time,
            avg_time=statistics.mean(times),
            min_time=min(times),
            max_time=max(times),
            std_dev=statistics.stdev(times),
            ops_per_second=len(invalid_names) / total_time,
            memory_used_mb=memory_used
        )


def run_all_benchmarks():
    """모든 벤치마크 실행"""
    print("🚀 Starting Naming Convention Benchmarks...")
    print("=" * 60)
    
    benchmark = NamingBenchmark()
    results = {}
    
    # 1. 단일 검증 벤치마크
    print("\n📊 Running single validation benchmark...")
    results['single'] = benchmark.benchmark_single_validation(1000)
    print(results['single'])
    
    # 2. 10K 엔티티 벤치마크
    print("\n📊 Running 10K entities benchmark...")
    results['10k'] = benchmark.benchmark_10k_entities()
    print(results['10k'])
    
    # 3. 메모리 사용량 프로파일링
    print("\n📊 Profiling memory usage...")
    memory_profile = benchmark.benchmark_memory_usage()
    print("\n=== Memory Usage Profile ===")
    for key, value in memory_profile.items():
        print(f"{key}: {value:.2f} MB")
    
    # 4. 동시성 벤치마크
    print("\n📊 Running concurrent validation benchmarks...")
    for workers in [1, 2, 4, 8]:
        results[f'concurrent_{workers}'] = benchmark.benchmark_concurrent_validation(workers, 8000)
        print(results[f'concurrent_{workers}'])
    
    # 5. 패턴 복잡도 벤치마크
    print("\n📊 Running pattern complexity benchmarks...")
    pattern_results = benchmark.benchmark_pattern_complexity()
    for name, result in pattern_results.items():
        print(result)
    
    # 6. 자동 수정 성능
    print("\n📊 Running auto-fix performance benchmark...")
    results['autofix'] = benchmark.benchmark_auto_fix_performance(1000)
    print(results['autofix'])
    
    # 결과 저장
    summary = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'results': {
            name: {
                'total_operations': r.total_operations,
                'total_time': r.total_time,
                'avg_time_ms': r.avg_time * 1000,
                'ops_per_second': r.ops_per_second,
                'memory_used_mb': r.memory_used_mb
            }
            for name, r in results.items()
        },
        'memory_profile': memory_profile
    }
    
    with open('benchmark_results.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print("\n✅ Benchmark completed. Results saved to benchmark_results.json")


if __name__ == "__main__":
    run_all_benchmarks()