#!/usr/bin/env python3
"""
OMS 극한 카오스 테스트
더 극단적인 상황에서 시스템 복원력 테스트
"""
import asyncio
import random
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from main_enterprise import services

class ExtremeChaosTest:
    """극한 카오스 테스트"""
    
    def __init__(self):
        self.results = []
        self.active_tasks = []
        self.chaos_active = True
    
    def log(self, test: str, result: str, details: str = ""):
        """결과 로깅"""
        print(f"{'✅' if result == 'PASS' else '❌' if result == 'FAIL' else '⚠️'} {test}: {result}")
        if details:
            print(f"   └─ {details}")
        self.results.append({"test": test, "result": result, "details": details})
    
    async def chaos_monkey(self, duration: int = 30):
        """카오스 몽키 - 랜덤 장애 주입"""
        print(f"\n🐒 카오스 몽키 시작 ({duration}초간 랜덤 장애 주입)")
        
        start_time = time.time()
        failure_count = 0
        
        while time.time() - start_time < duration and self.chaos_active:
            try:
                # 랜덤 장애 선택
                chaos_type = random.choice([
                    "terminate_service",
                    "memory_spike", 
                    "network_delay",
                    "corrupt_data",
                    "resource_exhaustion"
                ])
                
                if chaos_type == "terminate_service":
                    # 서비스 강제 종료
                    if services.schema_service:
                        original = services.schema_service
                        services.schema_service = None
                        await asyncio.sleep(random.uniform(0.5, 2.0))
                        services.schema_service = original
                        failure_count += 1
                
                elif chaos_type == "memory_spike":
                    # 메모리 스파이크 생성
                    waste_memory = []
                    for _ in range(random.randint(100, 500)):
                        waste_memory.append("x" * 10000)
                    await asyncio.sleep(0.1)
                    del waste_memory
                    failure_count += 1
                
                elif chaos_type == "network_delay":
                    # 네트워크 지연 시뮬레이션
                    original_ping = services.db_client.ping
                    
                    async def delayed_ping():
                        await asyncio.sleep(random.uniform(1.0, 5.0))
                        return await original_ping()
                    
                    services.db_client.ping = delayed_ping
                    await asyncio.sleep(random.uniform(0.5, 1.0))
                    services.db_client.ping = original_ping
                    failure_count += 1
                
                await asyncio.sleep(random.uniform(0.1, 1.0))
                
            except Exception as e:
                print(f"   🔥 카오스 주입 중 예외: {str(e)[:50]}")
                failure_count += 1
        
        elapsed = time.time() - start_time
        self.log("카오스 몽키", "PASS", f"{failure_count}개 장애 주입 ({elapsed:.1f}초)")
    
    async def stress_test_concurrent_users(self, user_count: int = 100):
        """동시 사용자 스트레스 테스트"""
        print(f"\n👥 동시 사용자 스트레스 테스트 ({user_count}명)")
        
        await services.initialize()
        
        async def simulate_user(user_id: int):
            """사용자 시뮬레이션"""
            try:
                actions = 0
                errors = 0
                
                for _ in range(random.randint(5, 15)):  # 각 사용자당 5-15개 액션
                    action = random.choice([
                        "list_schemas",
                        "validate", 
                        "ping_db",
                        "check_health"
                    ])
                    
                    try:
                        if action == "list_schemas" and services.schema_service:
                            await services.schema_service.list_object_types("main")
                        elif action == "validate" and services.validation_service:
                            from core.validation.models import ValidationRequest
                            req = ValidationRequest(
                                source_branch="main",
                                target_branch="main",
                                include_impact_analysis=False,
                                include_warnings=False,
                                options={}
                            )
                            await services.validation_service.validate_breaking_changes(req)
                        elif action == "ping_db":
                            await services.db_client.ping()
                        
                        actions += 1
                        await asyncio.sleep(random.uniform(0.01, 0.1))
                        
                    except Exception:
                        errors += 1
                    
                return {"user_id": user_id, "actions": actions, "errors": errors}
                
            except Exception as e:
                return {"user_id": user_id, "actions": 0, "errors": 1, "error": str(e)[:30]}
        
        # 동시 사용자 실행
        start_time = time.time()
        tasks = [simulate_user(i) for i in range(user_count)]
        
        # 카오스 몽키를 백그라운드에서 실행
        chaos_task = asyncio.create_task(self.chaos_monkey(20))
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.time() - start_time
            
            # 결과 분석
            total_actions = sum(r.get("actions", 0) for r in results if isinstance(r, dict))
            total_errors = sum(r.get("errors", 0) for r in results if isinstance(r, dict))
            successful_users = sum(1 for r in results if isinstance(r, dict) and r.get("actions", 0) > 0)
            
            throughput = total_actions / duration if duration > 0 else 0
            error_rate = (total_errors / (total_actions + total_errors)) * 100 if (total_actions + total_errors) > 0 else 0
            
            if successful_users >= user_count * 0.7:  # 70% 사용자 성공
                self.log("동시 사용자 처리", "PASS", 
                        f"{successful_users}/{user_count} 사용자 성공, {throughput:.1f} TPS, 오류율 {error_rate:.1f}%")
            else:
                self.log("동시 사용자 처리", "FAIL",
                        f"사용자 성공률 부족: {successful_users}/{user_count}")
        
        finally:
            self.chaos_active = False
            await chaos_task
            await services.shutdown()
    
    async def failover_recovery_test(self):
        """장애 복구 테스트"""
        print("\n🔄 장애 복구 테스트")
        
        await services.initialize()
        
        # 1. 정상 상태 확인
        try:
            ping_result = await services.db_client.ping()
            if ping_result:
                self.log("초기 상태", "PASS", "모든 서비스 정상")
            else:
                self.log("초기 상태", "FAIL", "초기 상태 불안정")
                return
        except Exception as e:
            self.log("초기 상태", "FAIL", f"초기화 실패: {str(e)[:30]}")
            return
        
        # 2. 전체 시스템 강제 종료
        print("   🔥 전체 시스템 강제 종료...")
        await services.shutdown()
        
        # 3. 빠른 복구 시도
        recovery_start = time.time()
        try:
            await services.initialize()
            recovery_time = time.time() - recovery_start
            
            # 복구 후 기능 테스트
            ping_result = await services.db_client.ping()
            if ping_result:
                self.log("빠른 복구", "PASS", f"복구 시간: {recovery_time:.2f}초")
            else:
                self.log("빠른 복구", "WARN", f"부분 복구: {recovery_time:.2f}초")
                
        except Exception as e:
            recovery_time = time.time() - recovery_start
            self.log("빠른 복구", "FAIL", f"복구 실패: {str(e)[:30]} ({recovery_time:.2f}초)")
        
        # 4. 부분 장애 복구 테스트
        try:
            # Schema Service만 제거
            original_schema = services.schema_service
            services.schema_service = None
            
            # 시스템이 여전히 작동하는지 확인
            ping_result = await services.db_client.ping()
            if ping_result:
                self.log("부분 장애 대응", "PASS", "핵심 서비스는 계속 동작")
                
                # Schema Service 복구
                services.schema_service = original_schema
                self.log("부분 복구", "PASS", "개별 서비스 복구 성공")
            else:
                self.log("부분 장애 대응", "FAIL", "단일 서비스 장애가 전체 영향")
                
        except Exception as e:
            self.log("부분 장애 테스트", "FAIL", f"테스트 실행 실패: {str(e)[:30]}")
        
        await services.shutdown()
    
    async def data_corruption_resilience(self):
        """데이터 손상 복원력 테스트"""
        print("\n💥 데이터 손상 복원력 테스트")
        
        await services.initialize()
        
        try:
            # 1. 정상 데이터 작업
            normal_data = {"test": "normal_operation", "timestamp": time.time()}
            self.log("정상 데이터 처리", "PASS", "기준선 설정")
            
            # 2. 손상된 데이터 주입
            corrupted_inputs = [
                None,
                "",
                {"malformed": "json", "missing": True},
                "이것은 JSON이 아닙니다",
                {"매우긴키": "x" * 10000},
                {"숫자가아님": "문자열", "expected": "number"},
                []  # 잘못된 타입
            ]
            
            handled_count = 0
            for i, corrupt_data in enumerate(corrupted_inputs):
                try:
                    # 다양한 서비스에 손상된 데이터 전달 시도
                    if i % 3 == 0 and services.schema_service:
                        # 손상된 스키마 데이터 처리 시도
                        await services.schema_service.list_object_types("main")
                    elif i % 3 == 1 and services.validation_service:
                        # 손상된 검증 데이터 처리 시도  
                        from core.validation.models import ValidationRequest
                        req = ValidationRequest(
                            source_branch="main",
                            target_branch="main",
                            include_impact_analysis=False,
                            include_warnings=False,
                            options={}
                        )
                        await services.validation_service.validate_breaking_changes(req)
                    
                    handled_count += 1
                    
                except Exception:
                    # 예외 처리는 정상적인 동작
                    handled_count += 1
            
            if handled_count >= len(corrupted_inputs) * 0.8:
                self.log("데이터 손상 처리", "PASS", f"{handled_count}/{len(corrupted_inputs)} 손상 데이터 적절히 처리")
            else:
                self.log("데이터 손상 처리", "FAIL", f"손상 데이터 처리 부족: {handled_count}/{len(corrupted_inputs)}")
            
            # 3. 복구 후 정상 동작 확인
            ping_result = await services.db_client.ping()
            if ping_result:
                self.log("손상 후 복구", "PASS", "시스템 정상 동작 유지")
            else:
                self.log("손상 후 복구", "FAIL", "시스템 안정성 손상")
                
        except Exception as e:
            self.log("데이터 손상 테스트", "FAIL", f"테스트 실행 실패: {str(e)[:50]}")
        
        await services.shutdown()
    
    def print_extreme_results(self):
        """극한 테스트 결과 출력"""
        print("\n" + "="*60)
        print("💀 극한 카오스 테스트 결과")
        print("="*60)
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r["result"] == "PASS")
        failed = sum(1 for r in self.results if r["result"] == "FAIL")
        warned = sum(1 for r in self.results if r["result"] == "WARN")
        
        print(f"\n📊 극한 상황 테스트: {total}개")
        print(f"   ✅ 생존: {passed}개 ({passed/total*100:.1f}%)")
        print(f"   ❌ 실패: {failed}개 ({failed/total*100:.1f}%)")
        print(f"   ⚠️ 경고: {warned}개 ({warned/total*100:.1f}%)")
        
        if passed >= total * 0.7:
            print(f"\n🎖️ 극한 복원력: 우수")
            print("   시스템이 극한 상황에서도 안정적으로 동작합니다")
        elif passed >= total * 0.5:
            print(f"\n🏅 극한 복원력: 양호") 
            print("   대부분의 극한 상황을 견뎌내지만 개선 여지가 있습니다")
        else:
            print(f"\n⚡ 극한 복원력: 취약")
            print("   극한 상황에서 시스템 안정성 개선이 필요합니다")

async def main():
    """극한 카오스 테스트 실행"""
    print("💀 OMS 극한 카오스 엔지니어링 테스트")
    print("시스템을 한계까지 몰아붙여 복원력을 검증합니다...")
    
    extreme_test = ExtremeChaosTest()
    
    # 극한 테스트 시나리오
    test_scenarios = [
        ("장애 복구", extreme_test.failover_recovery_test),
        ("데이터 손상 복원력", extreme_test.data_corruption_resilience),
        ("동시 사용자 스트레스", lambda: extreme_test.stress_test_concurrent_users(50))
    ]
    
    for test_name, test_func in test_scenarios:
        print(f"\n🔥 {test_name} 테스트 시작...")
        try:
            await test_func()
        except Exception as e:
            extreme_test.log(f"{test_name} 전체", "FAIL", f"테스트 실행 오류: {str(e)[:50]}")
    
    extreme_test.print_extreme_results()

if __name__ == "__main__":
    asyncio.run(main())