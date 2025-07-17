#!/usr/bin/env python3
"""
종합 테스트 실행기
프로덕션 레벨 통합 테스트 + 성능 테스트 + 보고서 생성

think ultra: 모든 테스트를 순차적으로 실행하고 최종 프로덕션 준비도 평가
"""

import asyncio
import sys
import os
import time
import json
import subprocess
from datetime import datetime
from pathlib import Path

# 테스트 모듈 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests', 'integration'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests', 'performance'))

from test_comprehensive_production_integration import ProductionIntegrationTestSuite
from test_production_performance_suite import ProductionPerformanceTestSuite


class ComprehensiveTestRunner:
    """종합 테스트 실행기"""
    
    def __init__(self):
        self.test_start_time = datetime.now()
        self.test_results = {
            "integration_tests": {},
            "performance_tests": {},
            "overall_status": "running",
            "start_time": self.test_start_time.isoformat(),
            "end_time": None,
            "total_duration": 0,
            "production_readiness_score": 0
        }
        self.services_status = {
            "oms": False,
            "bff": False,
            "terminusdb": False
        }
    
    async def check_service_prerequisites(self):
        """서비스 전제 조건 확인"""
        print("🔍 서비스 전제 조건 확인")
        
        # Python 패키지 확인
        required_packages = ["httpx", "psutil", "asyncio", "statistics"]
        missing_packages = []
        
        for package in required_packages:
            try:
                __import__(package)
                print(f"  ✅ {package} 패키지 사용 가능")
            except ImportError:
                missing_packages.append(package)
                print(f"  ❌ {package} 패키지 누락")
        
        if missing_packages:
            print(f"\n🚨 누락된 패키지: {missing_packages}")
            print("설치 명령: pip install " + " ".join(missing_packages))
            return False
        
        # 서비스 포트 확인
        import socket
        
        services_to_check = [
            ("OMS", "localhost", 8000),
            ("BFF", "localhost", 8002),
            ("TerminusDB", "localhost", 6363)
        ]
        
        for service_name, host, port in services_to_check:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    print(f"  ✅ {service_name} 서비스 ({host}:{port}) 실행 중")
                    if service_name.lower() == "oms":
                        self.services_status["oms"] = True
                    elif service_name.lower() == "bff":
                        self.services_status["bff"] = True
                    elif service_name.lower() == "terminusdb":
                        self.services_status["terminusdb"] = True
                else:
                    print(f"  ⚠️ {service_name} 서비스 ({host}:{port}) 연결 불가")
                    
            except Exception as e:
                print(f"  ❌ {service_name} 서비스 확인 실패: {e}")
        
        return True
    
    async def run_integration_tests(self):
        """통합 테스트 실행"""
        print("\n" + "="*80)
        print("🔗 프로덕션 레벨 통합 테스트 시작")
        print("="*80)
        
        integration_start_time = time.time()
        
        try:
            integration_suite = ProductionIntegrationTestSuite()
            await integration_suite.run_comprehensive_tests()
            
            # 결과 수집
            self.test_results["integration_tests"] = {
                "status": "completed",
                "test_results": integration_suite.test_results,
                "security_violations": integration_suite.security_violations,
                "duration": time.time() - integration_start_time,
                "success_rate": len([t for t in integration_suite.test_results if t["status"] == "passed"]) / len(integration_suite.test_results) if integration_suite.test_results else 0
            }
            
            print(f"✅ 통합 테스트 완료 ({time.time() - integration_start_time:.1f}초)")
            
        except Exception as e:
            print(f"❌ 통합 테스트 실패: {e}")
            self.test_results["integration_tests"] = {
                "status": "failed",
                "error": str(e),
                "duration": time.time() - integration_start_time
            }
    
    async def run_performance_tests(self):
        """성능 테스트 실행"""
        print("\n" + "="*80)
        print("⚡ 프로덕션 레벨 성능 테스트 시작")
        print("="*80)
        
        performance_start_time = time.time()
        
        try:
            performance_suite = ProductionPerformanceTestSuite()
            await performance_suite.run_comprehensive_performance_tests()
            
            # 결과 수집
            self.test_results["performance_tests"] = {
                "status": "completed",
                "performance_results": performance_suite.performance_results,
                "resource_metrics": performance_suite.resource_metrics,
                "duration": time.time() - performance_start_time,
                "thresholds": performance_suite.thresholds
            }
            
            print(f"✅ 성능 테스트 완료 ({time.time() - performance_start_time:.1f}초)")
            
        except Exception as e:
            print(f"❌ 성능 테스트 실패: {e}")
            self.test_results["performance_tests"] = {
                "status": "failed",
                "error": str(e),
                "duration": time.time() - performance_start_time
            }
    
    def calculate_production_readiness_score(self):
        """프로덕션 준비도 점수 계산"""
        score = 0
        max_score = 100
        
        # 서비스 가용성 (20점)
        service_score = sum(self.services_status.values()) / len(self.services_status) * 20
        score += service_score
        
        # 통합 테스트 결과 (40점)
        integration_tests = self.test_results.get("integration_tests", {})
        if integration_tests.get("status") == "completed":
            success_rate = integration_tests.get("success_rate", 0)
            integration_score = success_rate * 40
            score += integration_score
            
            # 보안 위반 차감
            security_violations = len(integration_tests.get("security_violations", []))
            score -= security_violations * 5  # 위반당 5점 차감
        
        # 성능 테스트 결과 (40점)
        performance_tests = self.test_results.get("performance_tests", {})
        if performance_tests.get("status") == "completed":
            # 성능 임계값 위반 확인
            performance_violations = 0
            thresholds = performance_tests.get("thresholds", {})
            performance_results = performance_tests.get("performance_results", {})
            
            for test_name, results in performance_results.items():
                if isinstance(results, dict) and "error" not in results:
                    # 응답 시간, 처리량, 에러율 확인
                    if "response_time" in results and results["response_time"] > thresholds.get("max_response_time", 5):
                        performance_violations += 1
                    if "throughput" in results and results["throughput"] < thresholds.get("min_throughput", 10):
                        performance_violations += 1
                    if "error_rate" in results and results["error_rate"] > thresholds.get("max_error_rate", 0.05):
                        performance_violations += 1
            
            performance_score = max(0, 40 - performance_violations * 5)
            score += performance_score
        
        return min(max_score, max(0, score))
    
    def generate_final_report(self):
        """최종 종합 보고서 생성"""
        end_time = datetime.now()
        total_duration = (end_time - self.test_start_time).total_seconds()
        
        self.test_results["end_time"] = end_time.isoformat()
        self.test_results["total_duration"] = total_duration
        self.test_results["production_readiness_score"] = self.calculate_production_readiness_score()
        self.test_results["overall_status"] = "completed"
        
        print("\n" + "="*80)
        print("📋 최종 종합 테스트 보고서")
        print("="*80)
        
        print(f"🕒 테스트 시작: {self.test_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🕒 테스트 종료: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️ 총 소요 시간: {total_duration:.1f}초")
        
        print(f"\n🔧 서비스 상태:")
        for service, status in self.services_status.items():
            status_icon = "✅" if status else "❌"
            print(f"  {status_icon} {service.upper()}: {'실행 중' if status else '연결 불가'}")
        
        # 통합 테스트 결과
        integration_tests = self.test_results.get("integration_tests", {})
        if integration_tests.get("status") == "completed":
            test_results = integration_tests.get("test_results", [])
            passed_tests = [t for t in test_results if t["status"] == "passed"]
            failed_tests = [t for t in test_results if t["status"] == "failed"]
            security_violations = integration_tests.get("security_violations", [])
            
            print(f"\n🔗 통합 테스트 결과:")
            print(f"  ✅ 성공: {len(passed_tests)}")
            print(f"  ❌ 실패: {len(failed_tests)}")
            print(f"  🛡️ 보안 위반: {len(security_violations)}")
            print(f"  📊 성공률: {integration_tests.get('success_rate', 0):.1%}")
            
            if failed_tests:
                print(f"  실패한 테스트:")
                for test in failed_tests:
                    print(f"    - {test['test']}: {test.get('error', 'Unknown error')}")
        
        # 성능 테스트 결과
        performance_tests = self.test_results.get("performance_tests", {})
        if performance_tests.get("status") == "completed":
            performance_results = performance_tests.get("performance_results", {})
            resource_metrics = performance_tests.get("resource_metrics", {})
            
            print(f"\n⚡ 성능 테스트 결과:")
            print(f"  📊 테스트 항목: {len(performance_results)}")
            print(f"  💻 리소스 모니터링: {len(resource_metrics)}")
            
            # 주요 성능 지표
            if "response_time_analysis" in performance_results:
                response_analysis = performance_results["response_time_analysis"]
                print(f"  ⏱️ 평균 응답 시간: {response_analysis.get('avg_time', 0):.3f}s")
                print(f"  📈 95%ile 응답 시간: {response_analysis.get('p95_time', 0):.3f}s")
            
            # 동시 사용자 테스트
            concurrent_tests = [k for k in performance_results.keys() if k.startswith("concurrent_")]
            if concurrent_tests:
                max_concurrent = max([performance_results[k].get("concurrent_users", 0) for k in concurrent_tests])
                print(f"  👥 최대 동시 사용자: {max_concurrent}")
        
        # 프로덕션 준비도 점수
        readiness_score = self.test_results["production_readiness_score"]
        print(f"\n🎯 프로덕션 준비도 점수: {readiness_score:.1f}/100")
        
        if readiness_score >= 80:
            print("🚀 프로덕션 배포 준비 완료!")
            recommendation = "시스템이 프로덕션 환경에 배포할 준비가 되었습니다."
        elif readiness_score >= 60:
            print("⚠️ 프로덕션 배포 전 개선 권장")
            recommendation = "일부 성능 및 안정성 개선 후 배포를 권장합니다."
        else:
            print("🚨 프로덕션 배포 부적합")
            recommendation = "심각한 문제들을 해결한 후 재테스트가 필요합니다."
        
        print(f"\n💡 권장 사항: {recommendation}")
        
        # JSON 보고서 저장
        report_filename = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_filename, 'w', encoding='utf-8') as f:
            json.dump(self.test_results, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 상세 보고서 저장: {report_filename}")
        
        return readiness_score >= 80
    
    async def run_all_tests(self):
        """모든 테스트 실행"""
        print("🚀 SPICE HARVESTER 프로덕션 레벨 종합 테스트 시작")
        print("think ultra: 실제 프로덕션 환경 준비도 검증")
        
        # 1. 전제 조건 확인
        if not await self.check_service_prerequisites():
            print("❌ 전제 조건 확인 실패")
            return False
        
        # 2. 통합 테스트 실행
        await self.run_integration_tests()
        
        # 3. 성능 테스트 실행
        await self.run_performance_tests()
        
        # 4. 최종 보고서 생성
        production_ready = self.generate_final_report()
        
        return production_ready


async def main():
    """메인 실행 함수"""
    print("="*80)
    print("🎯 SPICE HARVESTER 프로덕션 준비도 검증")
    print("="*80)
    
    test_runner = ComprehensiveTestRunner()
    
    try:
        production_ready = await test_runner.run_all_tests()
        
        if production_ready:
            print("\n🎉 모든 테스트 통과! 프로덕션 배포 준비 완료!")
            sys.exit(0)
        else:
            print("\n⚠️ 일부 테스트 실패. 문제 해결 후 재테스트 필요.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⏹️ 사용자에 의해 테스트 중단됨")
        sys.exit(2)
    except Exception as e:
        print(f"\n💥 예상치 못한 오류 발생: {e}")
        sys.exit(3)


if __name__ == "__main__":
    asyncio.run(main())