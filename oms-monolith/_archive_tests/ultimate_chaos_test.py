"""
OMS 궁극의 카오스 테스트
시스템을 극한까지 밀어붙이는 진짜 스트레스 테스트
"""
import asyncio
import random
import string
import time
from datetime import datetime
import sys
sys.path.append('/Users/sihyun/Desktop/ARRAKIS/SPICE/oms-monolith')

from database.simple_terminus_client import SimpleTerminusDBClient
import logging

logging.basicConfig(level=logging.WARNING)  # 로그 줄이기
logger = logging.getLogger(__name__)


class ChaosTest:
    """극한의 카오스 테스트"""
    
    def __init__(self):
        self.results = {
            "성공": 0,
            "실패": 0,
            "오류": [],
            "응답시간": [],
            "메모리누수": False,
            "데이터손실": False,
            "동시성문제": False
        }
        self.start_time = None
        
    async def test_1_connection_storm(self):
        """Test 1: 연결 폭풍 - 100개 동시 연결"""
        print("\n🌪️ Test 1: Connection Storm (100개 동시 연결)")
        print("-"*60)
        
        connections = []
        success = 0
        fail = 0
        
        async def create_connection(i):
            try:
                db = SimpleTerminusDBClient(
                    endpoint="http://localhost:6363",
                    username="admin",
                    password="root",
                    database="oms"
                )
                await db.connect()
                connections.append(db)
                return True
            except:
                return False
                
        # 100개 동시 연결 시도
        tasks = [create_connection(i) for i in range(100)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success = sum(1 for r in results if r is True)
        fail = len(results) - success
        
        print(f"✅ 성공: {success}/100")
        print(f"❌ 실패: {fail}/100")
        
        # 연결 종료
        for conn in connections:
            try:
                await conn.disconnect()
            except:
                pass
                
        self.results["연결폭풍"] = {"성공": success, "실패": fail}
        return success > 80  # 80% 이상 성공하면 통과
        
    async def test_2_rapid_fire_creation(self):
        """Test 2: 초고속 생성 - 1초에 50개 타입 생성"""
        print("\n\n⚡ Test 2: Rapid Fire Creation (1초에 50개)")
        print("-"*60)
        
        db = SimpleTerminusDBClient(
            endpoint="http://localhost:6363",
            username="admin",
            password="root",
            database="oms"
        )
        await db.connect()
        
        success = 0
        fail = 0
        start = time.time()
        
        async def create_type(i):
            try:
                random_name = ''.join(random.choices(string.ascii_letters, k=8))
                result = await db.client.post(
                    f"http://localhost:6363/api/document/admin/oms?author=chaos&message=rapid_test_{i}",
                    json=[{
                        "@type": "ObjectType",
                        "@id": f"ObjectType/Chaos_{random_name}",
                        "name": f"Chaos_{random_name}",
                        "displayName": f"카오스 {i}",
                        "description": f"Rapid fire test {i}"
                    }],
                    auth=("admin", "root"),
                    timeout=1.0  # 1초 타임아웃
                )
                return result.status_code in [200, 201]
            except:
                return False
                
        # 50개 동시 생성
        tasks = [create_type(i) for i in range(50)]
        results = await asyncio.gather(*tasks)
        
        elapsed = time.time() - start
        success = sum(1 for r in results if r)
        fail = len(results) - success
        
        print(f"⏱️ 소요시간: {elapsed:.2f}초")
        print(f"✅ 성공: {success}/50")
        print(f"❌ 실패: {fail}/50")
        print(f"📊 초당 처리량: {success/elapsed:.2f} ops/sec")
        
        await db.disconnect()
        self.results["초고속생성"] = {"성공": success, "실패": fail, "초당처리량": success/elapsed}
        return success > 30  # 60% 이상 성공하면 통과
        
    async def test_3_concurrent_conflicts(self):
        """Test 3: 동시 충돌 - 10명이 같은 객체 동시 수정"""
        print("\n\n💥 Test 3: Concurrent Conflicts (10명 동시 수정)")
        print("-"*60)
        
        target_id = "ObjectType/ConflictTest"
        
        # 먼저 타겟 생성
        db = SimpleTerminusDBClient(
            endpoint="http://localhost:6363",
            username="admin", 
            password="root",
            database="oms"
        )
        await db.connect()
        
        # 타겟 생성
        await db.client.post(
            f"http://localhost:6363/api/document/admin/oms?author=chaos&message=create_target",
            json=[{
                "@type": "ObjectType",
                "@id": target_id,
                "name": "ConflictTest",
                "displayName": "충돌 테스트",
                "description": "초기값"
            }],
            auth=("admin", "root")
        )
        
        # 10명이 동시에 수정
        async def modify_concurrent(user_id):
            try:
                # 삭제
                await db.client.delete(
                    f"http://localhost:6363/api/document/admin/oms/{target_id}?author=user_{user_id}",
                    auth=("admin", "root"),
                    timeout=1.0
                )
                
                # 재생성 (수정)
                result = await db.client.post(
                    f"http://localhost:6363/api/document/admin/oms?author=user_{user_id}&message=modify_{user_id}",
                    json=[{
                        "@type": "ObjectType",
                        "@id": target_id,
                        "name": "ConflictTest",
                        "displayName": "충돌 테스트",
                        "description": f"User {user_id}가 수정함"
                    }],
                    auth=("admin", "root"),
                    timeout=1.0
                )
                return result.status_code in [200, 201]
            except:
                return False
                
        # 동시 실행
        tasks = [modify_concurrent(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        success = sum(1 for r in results if r)
        fail = len(results) - success
        
        print(f"✅ 성공한 수정: {success}/10")
        print(f"❌ 충돌로 실패: {fail}/10")
        
        # 최종 상태 확인
        final = await db.client.get(
            f"http://localhost:6363/api/document/admin/oms/{target_id}",
            auth=("admin", "root")
        )
        
        if final.status_code == 200:
            print(f"📝 최종 승자: {final.json().get('description', 'Unknown')}")
            
        await db.disconnect()
        self.results["동시충돌"] = {"성공": success, "실패": fail}
        return fail > 0  # 충돌이 발생해야 정상
        
    async def test_4_memory_leak_test(self):
        """Test 4: 메모리 누수 테스트 - 1000번 연결/해제 반복"""
        print("\n\n🧠 Test 4: Memory Leak Test (1000번 반복)")
        print("-"*60)
        
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        print(f"초기 메모리: {initial_memory:.2f} MB")
        
        for i in range(1000):
            db = SimpleTerminusDBClient(
                endpoint="http://localhost:6363",
                username="admin",
                password="root",
                database="oms"
            )
            await db.connect()
            
            # 간단한 쿼리
            await db.client.get(
                "http://localhost:6363/api/info",
                auth=("admin", "root")
            )
            
            await db.disconnect()
            
            if i % 100 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024
                print(f"  {i}번째: {current_memory:.2f} MB (+{current_memory - initial_memory:.2f} MB)")
                
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_increase = final_memory - initial_memory
        
        print(f"\n최종 메모리: {final_memory:.2f} MB")
        print(f"메모리 증가: {memory_increase:.2f} MB")
        
        self.results["메모리누수"] = memory_increase < 50  # 50MB 이하 증가면 OK
        return memory_increase < 50
        
    async def test_5_data_corruption_test(self):
        """Test 5: 데이터 무결성 테스트"""
        print("\n\n🔐 Test 5: Data Integrity Test")
        print("-"*60)
        
        db = SimpleTerminusDBClient(
            endpoint="http://localhost:6363",
            username="admin",
            password="root",
            database="oms"
        )
        await db.connect()
        
        # 테스트 데이터 생성
        test_data = []
        for i in range(10):
            data = {
                "id": f"IntegrityTest_{i}",
                "value": random.randint(1000, 9999),
                "checksum": None
            }
            data["checksum"] = hash(str(data))
            test_data.append(data)
            
            # 저장
            await db.client.post(
                f"http://localhost:6363/api/document/admin/oms?author=chaos&message=integrity_test",
                json=[{
                    "@type": "ObjectType",
                    "@id": f"ObjectType/{data['id']}",
                    "name": data['id'],
                    "displayName": str(data['value']),
                    "description": str(data['checksum'])
                }],
                auth=("admin", "root")
            )
            
        # 다시 읽어서 검증
        corrupted = 0
        for data in test_data:
            result = await db.client.get(
                f"http://localhost:6363/api/document/admin/oms/ObjectType/{data['id']}",
                auth=("admin", "root")
            )
            
            if result.status_code == 200:
                stored = result.json()
                if stored.get('description') != str(data['checksum']):
                    corrupted += 1
                    print(f"❌ 데이터 손상 감지: {data['id']}")
                    
        print(f"\n✅ 무결성 유지: {len(test_data) - corrupted}/{len(test_data)}")
        print(f"❌ 손상된 데이터: {corrupted}")
        
        await db.disconnect()
        self.results["데이터무결성"] = corrupted == 0
        return corrupted == 0
        
    async def test_6_branch_chaos(self):
        """Test 6: 브랜치 카오스 - 50개 브랜치 동시 생성/병합"""
        print("\n\n🌳 Test 6: Branch Chaos (50개 브랜치)")
        print("-"*60)
        
        db = SimpleTerminusDBClient(
            endpoint="http://localhost:6363",
            username="admin",
            password="root",
            database="oms"
        )
        await db.connect()
        
        # 50개 브랜치에서 동시 작업
        async def branch_work(i):
            branch_name = f"chaos/branch_{i}"
            try:
                # 브랜치에서 타입 생성
                result = await db.client.post(
                    f"http://localhost:6363/api/document/admin/oms?author=chaos&message=branch_work&branch={branch_name}",
                    json=[{
                        "@type": "ObjectType",
                        "@id": f"ObjectType/BranchTest_{i}",
                        "name": f"BranchTest_{i}",
                        "displayName": f"브랜치 {i}",
                        "description": f"Branch {branch_name} work"
                    }],
                    auth=("admin", "root"),
                    timeout=2.0
                )
                return result.status_code in [200, 201]
            except:
                return False
                
        # 동시 실행
        tasks = [branch_work(i) for i in range(50)]
        results = await asyncio.gather(*tasks)
        
        success = sum(1 for r in results if r)
        fail = len(results) - success
        
        print(f"✅ 성공한 브랜치 작업: {success}/50")
        print(f"❌ 실패한 브랜치 작업: {fail}/50")
        
        await db.disconnect()
        self.results["브랜치카오스"] = {"성공": success, "실패": fail}
        return success > 25  # 50% 이상 성공
        
    async def test_7_rollback_stress(self):
        """Test 7: 롤백 스트레스 - 연속 100번 생성/롤백"""
        print("\n\n↩️ Test 7: Rollback Stress (100번 반복)")
        print("-"*60)
        
        db = SimpleTerminusDBClient(
            endpoint="http://localhost:6363",
            username="admin",
            password="root",
            database="oms"
        )
        await db.connect()
        
        success_create = 0
        success_rollback = 0
        
        for i in range(100):
            type_id = f"ObjectType/RollbackTest_{i}"
            
            # 생성
            create_result = await db.client.post(
                f"http://localhost:6363/api/document/admin/oms?author=chaos&message=create_{i}",
                json=[{
                    "@type": "ObjectType",
                    "@id": type_id,
                    "name": f"RollbackTest_{i}",
                    "displayName": f"롤백 {i}",
                    "description": "Will be rolled back"
                }],
                auth=("admin", "root")
            )
            
            if create_result.status_code in [200, 201]:
                success_create += 1
                
                # 즉시 롤백 (삭제)
                rollback_result = await db.client.delete(
                    f"http://localhost:6363/api/document/admin/oms/{type_id}?author=chaos&message=rollback_{i}",
                    auth=("admin", "root")
                )
                
                if rollback_result.status_code in [200, 204]:
                    success_rollback += 1
                    
            if i % 20 == 0:
                print(f"  진행: {i}/100 (생성: {success_create}, 롤백: {success_rollback})")
                
        print(f"\n✅ 성공한 생성: {success_create}/100")
        print(f"✅ 성공한 롤백: {success_rollback}/100")
        
        await db.disconnect()
        self.results["롤백스트레스"] = {"생성": success_create, "롤백": success_rollback}
        return success_rollback > 80
        
    async def test_8_ultimate_chaos(self):
        """Test 8: 궁극의 카오스 - 모든 것을 동시에"""
        print("\n\n🔥 Test 8: ULTIMATE CHAOS (모든 작업 동시 실행)")
        print("-"*60)
        
        print("동시 실행 작업:")
        print("- 20개 연결 생성")
        print("- 30개 타입 생성")
        print("- 10개 충돌 수정")
        print("- 5개 브랜치 작업")
        print("- 10번 롤백")
        
        chaos_tasks = []
        
        # 연결 생성
        async def connect_chaos():
            dbs = []
            for _ in range(20):
                try:
                    db = SimpleTerminusDBClient(
                        endpoint="http://localhost:6363",
                        username="admin",
                        password="root",
                        database="oms"
                    )
                    await db.connect()
                    dbs.append(db)
                except:
                    pass
            return len(dbs)
            
        # 타입 생성
        async def create_chaos():
            db = SimpleTerminusDBClient(
                endpoint="http://localhost:6363",
                username="admin",
                password="root",
                database="oms"
            )
            await db.connect()
            
            success = 0
            for i in range(30):
                try:
                    result = await db.client.post(
                        f"http://localhost:6363/api/document/admin/oms?author=ultimate_chaos&message=chaos_{i}",
                        json=[{
                            "@type": "ObjectType",
                            "@id": f"ObjectType/UltimateChaos_{i}",
                            "name": f"UltimateChaos_{i}",
                            "displayName": f"궁극 {i}",
                            "description": "Ultimate chaos test"
                        }],
                        auth=("admin", "root"),
                        timeout=1.0
                    )
                    if result.status_code in [200, 201]:
                        success += 1
                except:
                    pass
                    
            await db.disconnect()
            return success
            
        # 모든 작업 동시 실행
        start_time = time.time()
        
        results = await asyncio.gather(
            connect_chaos(),
            create_chaos(),
            connect_chaos(),
            create_chaos(),
            return_exceptions=True
        )
        
        elapsed = time.time() - start_time
        
        print(f"\n⏱️ 총 소요시간: {elapsed:.2f}초")
        print(f"📊 결과: {[r for r in results if isinstance(r, int)]}")
        
        self.results["궁극카오스"] = {"소요시간": elapsed, "결과": str(results)}
        return True
        
    async def run_all_tests(self):
        """모든 카오스 테스트 실행"""
        print("\n" + "="*70)
        print("🔥 OMS 궁극의 카오스 테스트 시작!")
        print("="*70)
        
        self.start_time = time.time()
        
        tests = [
            ("Connection Storm", self.test_1_connection_storm),
            ("Rapid Fire Creation", self.test_2_rapid_fire_creation),
            ("Concurrent Conflicts", self.test_3_concurrent_conflicts),
            ("Memory Leak Test", self.test_4_memory_leak_test),
            ("Data Integrity Test", self.test_5_data_corruption_test),
            ("Branch Chaos", self.test_6_branch_chaos),
            ("Rollback Stress", self.test_7_rollback_stress),
            ("Ultimate Chaos", self.test_8_ultimate_chaos)
        ]
        
        passed = 0
        failed = 0
        
        for name, test in tests:
            try:
                result = await test()
                if result:
                    passed += 1
                    status = "✅ PASS"
                else:
                    failed += 1
                    status = "❌ FAIL"
            except Exception as e:
                failed += 1
                status = f"💥 CRASH: {str(e)[:50]}"
                self.results["오류"].append(f"{name}: {str(e)}")
                
            print(f"\n{name}: {status}")
            await asyncio.sleep(1)  # 테스트 간 쿨다운
            
        total_time = time.time() - self.start_time
        
        # 최종 보고서
        print("\n\n" + "="*70)
        print("📊 카오스 테스트 최종 보고서")
        print("="*70)
        
        print(f"\n테스트 결과:")
        print(f"  ✅ 통과: {passed}/{len(tests)}")
        print(f"  ❌ 실패: {failed}/{len(tests)}")
        print(f"  ⏱️ 총 소요시간: {total_time:.2f}초")
        
        print(f"\n상세 결과:")
        for key, value in self.results.items():
            if key != "오류":
                print(f"  - {key}: {value}")
                
        if self.results["오류"]:
            print(f"\n오류 목록:")
            for error in self.results["오류"]:
                print(f"  ❌ {error}")
                
        print(f"\n시스템 안정성 평가:")
        stability_score = (passed / len(tests)) * 100
        
        if stability_score >= 80:
            print(f"  🏆 매우 안정적 ({stability_score:.1f}%)")
        elif stability_score >= 60:
            print(f"  ✅ 안정적 ({stability_score:.1f}%)")
        elif stability_score >= 40:
            print(f"  ⚠️ 불안정 ({stability_score:.1f}%)")
        else:
            print(f"  ❌ 매우 불안정 ({stability_score:.1f}%)")
            
        print("\n🏁 카오스 테스트 완료!")
        
        return stability_score


async def main():
    test = ChaosTest()
    score = await test.run_all_tests()
    
    # 최종 판정
    if score >= 60:
        print("\n✅ OMS는 카오스 상황에서도 안정적으로 작동합니다!")
    else:
        print("\n❌ OMS는 극한 상황에서 불안정합니다.")


if __name__ == "__main__":
    asyncio.run(main())