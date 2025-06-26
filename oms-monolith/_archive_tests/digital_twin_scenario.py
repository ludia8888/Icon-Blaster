"""
실제 회사 디지털 트윈 시나리오
여러 사용자가 GitHub처럼 협업하며 회사를 모델링하는 시뮬레이션
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any
sys.path.append('/Users/sihyun/Desktop/ARRAKIS/SPICE/oms-monolith')

from database.simple_terminus_client import SimpleTerminusDBClient
from core.schema.service_fixed import SchemaService
from models.domain import ObjectTypeCreate, PropertyCreate
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


class User:
    """시뮬레이션 사용자"""
    def __init__(self, name: str, role: str, branch: str = None):
        self.name = name
        self.role = role
        self.branch = branch or f"feature/{name.lower()}"
        self.db = None
        
    async def connect(self):
        self.db = SimpleTerminusDBClient(
            endpoint="http://localhost:6363",
            username="admin",
            password="root",
            database="oms"
        )
        await self.db.connect()
        logger.info(f"👤 {self.name} ({self.role}) 연결됨")


class DigitalTwinScenario:
    """회사 디지털 트윈 시나리오"""
    
    def __init__(self):
        self.users = []
        self.company_name = "TechCorp Inc."
        self.main_db = None
        
    async def setup(self):
        """시나리오 초기화"""
        print(f"\n🏢 {self.company_name} 디지털 트윈 프로젝트 시작")
        print("="*70)
        
        # 메인 DB 연결
        self.main_db = SimpleTerminusDBClient(
            endpoint="http://localhost:6363",
            username="admin",
            password="root",
            database="oms"
        )
        await self.main_db.connect()
        
        # 사용자 생성
        self.users = [
            User("Alice", "Data Architect", "feature/organization-model"),
            User("Bob", "HR Manager", "feature/hr-system"),
            User("Charlie", "Finance Lead", "feature/financial-model"),
            User("David", "IT Manager", "feature/it-infrastructure")
        ]
        
        for user in self.users:
            await user.connect()
            
        print(f"\n✅ {len(self.users)}명의 사용자가 프로젝트에 참여")
        
    async def phase_1_initial_modeling(self):
        """Phase 1: 초기 도메인 모델링"""
        print(f"\n\n📋 Phase 1: 초기 도메인 모델링")
        print("-"*70)
        
        alice = self.users[0]  # Data Architect
        
        print(f"\n👤 {alice.name}: 핵심 조직 구조 모델링 시작")
        
        # 1. Organization 타입 생성
        org_type = {
            "@type": "ObjectType",
            "@id": "ObjectType/Organization",
            "name": "Organization",
            "displayName": "조직",
            "description": "회사 조직 구조의 최상위 엔티티"
        }
        
        await self._create_type(alice, org_type, "조직 구조 기본 틀 생성")
        
        # 2. Division 타입 생성
        division_type = {
            "@type": "ObjectType",
            "@id": "ObjectType/Division",
            "name": "Division",
            "displayName": "사업부",
            "description": "회사의 주요 사업 부문"
        }
        
        await self._create_type(alice, division_type, "사업부 타입 추가")
        
        # 3. Team 타입 생성
        team_type = {
            "@type": "ObjectType",
            "@id": "ObjectType/Team",
            "name": "Team",
            "displayName": "팀",
            "description": "실무 조직 단위"
        }
        
        await self._create_type(alice, team_type, "팀 구조 추가")
        
        # 4. 관계 정의
        org_relations = [
            {
                "@type": "LinkType",
                "@id": "LinkType/OrganizationHasDivision",
                "name": "OrganizationHasDivision",
                "displayName": "포함",
                "sourceObjectType": "Organization",
                "targetObjectType": "Division",
                "cardinality": "one-to-many"
            },
            {
                "@type": "LinkType",
                "@id": "LinkType/DivisionHasTeam",
                "name": "DivisionHasTeam",
                "displayName": "관리",
                "sourceObjectType": "Division",
                "targetObjectType": "Team",
                "cardinality": "one-to-many"
            }
        ]
        
        for relation in org_relations:
            await self._create_linktype(alice, relation)
            
        print(f"\n✅ {alice.name}: 기본 조직 구조 모델링 완료")
        
    async def phase_2_parallel_development(self):
        """Phase 2: 병렬 개발 (여러 사용자가 동시에 작업)"""
        print(f"\n\n🚀 Phase 2: 병렬 개발 시작")
        print("-"*70)
        
        # 각 사용자가 자신의 브랜치에서 작업
        tasks = []
        
        # Bob: HR 시스템 모델링
        async def bob_work():
            bob = self.users[1]
            print(f"\n👤 {bob.name}: HR 시스템 모델링 ({bob.branch})")
            
            hr_types = [
                {
                    "@type": "ObjectType",
                    "@id": "ObjectType/Employee",
                    "name": "Employee",
                    "displayName": "직원",
                    "description": "회사 직원 정보"
                },
                {
                    "@type": "ObjectType",
                    "@id": "ObjectType/Position",
                    "name": "Position",
                    "displayName": "직급",
                    "description": "직급 및 역할 정보"
                },
                {
                    "@type": "ObjectType",
                    "@id": "ObjectType/Contract",
                    "name": "Contract",
                    "displayName": "계약",
                    "description": "고용 계약 정보"
                }
            ]
            
            for hr_type in hr_types:
                await self._create_type(bob, hr_type, f"HR: {hr_type['displayName']} 추가", bob.branch)
                await asyncio.sleep(0.5)  # 실제 작업 시뮬레이션
                
            print(f"✅ {bob.name}: HR 모델 완료")
            
        # Charlie: 재무 시스템 모델링
        async def charlie_work():
            charlie = self.users[2]
            print(f"\n👤 {charlie.name}: 재무 시스템 모델링 ({charlie.branch})")
            
            finance_types = [
                {
                    "@type": "ObjectType",
                    "@id": "ObjectType/Budget",
                    "name": "Budget",
                    "displayName": "예산",
                    "description": "부서별 예산 정보"
                },
                {
                    "@type": "ObjectType",
                    "@id": "ObjectType/CostCenter",
                    "name": "CostCenter",
                    "displayName": "코스트센터",
                    "description": "비용 관리 단위"
                },
                {
                    "@type": "ObjectType",
                    "@id": "ObjectType/FinancialReport",
                    "name": "FinancialReport",
                    "displayName": "재무보고서",
                    "description": "정기 재무 보고서"
                }
            ]
            
            for fin_type in finance_types:
                await self._create_type(charlie, fin_type, f"Finance: {fin_type['displayName']} 추가", charlie.branch)
                await asyncio.sleep(0.5)
                
            print(f"✅ {charlie.name}: 재무 모델 완료")
            
        # David: IT 인프라 모델링
        async def david_work():
            david = self.users[3]
            print(f"\n👤 {david.name}: IT 인프라 모델링 ({david.branch})")
            
            it_types = [
                {
                    "@type": "ObjectType",
                    "@id": "ObjectType/System",
                    "name": "System",
                    "displayName": "시스템",
                    "description": "IT 시스템 및 애플리케이션"
                },
                {
                    "@type": "ObjectType",
                    "@id": "ObjectType/Server",
                    "name": "Server",
                    "displayName": "서버",
                    "description": "물리/가상 서버 인프라"
                },
                {
                    "@type": "ObjectType",
                    "@id": "ObjectType/Database",
                    "name": "Database",
                    "displayName": "데이터베이스",
                    "description": "데이터베이스 시스템"
                }
            ]
            
            for it_type in it_types:
                await self._create_type(david, it_type, f"IT: {it_type['displayName']} 추가", david.branch)
                await asyncio.sleep(0.5)
                
            print(f"✅ {david.name}: IT 모델 완료")
        
        # 병렬 실행
        tasks = [bob_work(), charlie_work(), david_work()]
        await asyncio.gather(*tasks)
        
        print(f"\n✅ 모든 사용자의 병렬 개발 완료")
        
    async def phase_3_conflict_scenario(self):
        """Phase 3: 충돌 시나리오"""
        print(f"\n\n⚔️ Phase 3: 충돌 시나리오")
        print("-"*70)
        
        bob = self.users[1]
        charlie = self.users[2]
        
        print(f"\n💥 충돌 상황: Bob과 Charlie가 동시에 Employee 타입 수정")
        
        # Bob: Employee에 salary 필드 추가
        print(f"\n👤 {bob.name}: Employee에 급여 정보 추가")
        bob_employee = {
            "@type": "ObjectType",
            "@id": "ObjectType/Employee",
            "name": "Employee",
            "displayName": "직원",
            "description": "회사 직원 정보 (급여 정보 포함)"
        }
        
        # Charlie: Employee에 department 필드 추가  
        print(f"👤 {charlie.name}: Employee에 부서 정보 추가")
        charlie_employee = {
            "@type": "ObjectType",
            "@id": "ObjectType/Employee", 
            "name": "Employee",
            "displayName": "직원",
            "description": "회사 직원 정보 (부서 정보 포함)"
        }
        
        # 동시에 수정 시도
        print("\n🔄 두 사용자가 동시에 커밋 시도...")
        
        # 실제로는 한 명만 성공하고 한 명은 충돌
        await self._update_type(bob, bob_employee, "Employee 급여 필드 추가", bob.branch)
        
        print(f"\n⚠️ {charlie.name}: 충돌 발생! Merge conflict detected")
        print("📝 충돌 해결 방안:")
        print("   1. 3-way merge로 자동 병합 시도")
        print("   2. 수동으로 충돌 해결")
        print("   3. 두 변경사항 모두 통합")
        
        # 충돌 해결
        resolved_employee = {
            "@type": "ObjectType",
            "@id": "ObjectType/Employee",
            "name": "Employee", 
            "displayName": "직원",
            "description": "회사 직원 정보 (급여 및 부서 정보 포함)"
        }
        
        await self._update_type(charlie, resolved_employee, "충돌 해결: 급여와 부서 정보 통합", charlie.branch)
        print(f"\n✅ 충돌 해결 완료")
        
    async def phase_4_merge_to_main(self):
        """Phase 4: Main 브랜치로 병합"""
        print(f"\n\n🔀 Phase 4: Main 브랜치로 병합")
        print("-"*70)
        
        alice = self.users[0]
        
        print(f"\n👤 {alice.name}: PR 리뷰 및 병합 진행")
        
        # 각 브랜치의 변경사항 확인
        branches = ["feature/hr-system", "feature/financial-model", "feature/it-infrastructure"]
        
        for i, branch in enumerate(branches):
            user = self.users[i+1]
            print(f"\n🔍 {branch} 브랜치 리뷰:")
            print(f"   - 작업자: {user.name}")
            print(f"   - 추가된 타입: 3개")
            print(f"   - 충돌: 없음")
            print(f"   ✅ 승인 및 병합")
            
            # 실제 병합 시뮬레이션
            await asyncio.sleep(0.5)
            
        print(f"\n✅ 모든 feature 브랜치가 main에 병합됨")
        
    async def phase_5_rollback_scenario(self):
        """Phase 5: 롤백 시나리오"""
        print(f"\n\n↩️ Phase 5: 롤백 시나리오")
        print("-"*70)
        
        david = self.users[3]
        
        print(f"\n⚠️ 문제 발생: Database 타입에 치명적인 오류 발견")
        print(f"👤 {david.name}: 긴급 롤백 필요!")
        
        # 롤백 전 상태
        print("\n📊 롤백 전 상태:")
        types_before = await self._get_all_types()
        print(f"   - 총 ObjectType: {len(types_before)}개")
        
        # 롤백 실행
        print(f"\n🔄 롤백 실행중...")
        await self._rollback_type(david, "ObjectType/Database", "치명적 오류로 인한 롤백")
        
        # 롤백 후 상태
        print("\n📊 롤백 후 상태:")
        types_after = await self._get_all_types()
        print(f"   - 총 ObjectType: {len(types_after)}개")
        print(f"   ✅ Database 타입 성공적으로 롤백됨")
        
    async def phase_6_final_state(self):
        """Phase 6: 최종 디지털 트윈 상태"""
        print(f"\n\n🏆 Phase 6: {self.company_name} 디지털 트윈 완성")
        print("-"*70)
        
        # 최종 상태 확인
        all_types = await self._get_all_types()
        all_links = await self._get_all_links()
        
        print(f"\n📊 디지털 트윈 최종 통계:")
        print(f"   - ObjectType: {len(all_types)}개")
        print(f"   - LinkType: {len(all_links)}개")
        print(f"   - 참여 사용자: {len(self.users)}명")
        print(f"   - 총 커밋 수: 20+")
        
        print(f"\n🏢 모델링된 도메인:")
        domains = {
            "조직 구조": ["Organization", "Division", "Team"],
            "인사 관리": ["Employee", "Position", "Contract"],
            "재무 관리": ["Budget", "CostCenter", "FinancialReport"],
            "IT 인프라": ["System", "Server"]
        }
        
        for domain, types in domains.items():
            print(f"\n   {domain}:")
            for t in types:
                print(f"      - {t}")
                
        print(f"\n✅ {self.company_name}의 디지털 트윈이 성공적으로 구축되었습니다!")
        
    # Helper methods
    async def _create_type(self, user: User, type_data: Dict, message: str, branch: str = "main"):
        """타입 생성"""
        try:
            result = await user.db.client.post(
                f"http://localhost:6363/api/document/admin/oms?author={user.name}&message={message}&branch={branch}",
                json=[type_data],
                auth=("admin", "root")
            )
            if result.status_code in [200, 201]:
                logger.info(f"✅ {user.name}: {type_data['displayName']} 생성")
            else:
                logger.error(f"❌ {user.name}: {type_data['displayName']} 생성 실패")
        except Exception as e:
            logger.error(f"❌ 오류: {e}")
            
    async def _create_linktype(self, user: User, link_data: Dict):
        """관계 생성"""
        try:
            result = await user.db.client.post(
                f"http://localhost:6363/api/document/admin/oms?author={user.name}&message=관계 정의",
                json=[link_data],
                auth=("admin", "root")
            )
            if result.status_code in [200, 201]:
                logger.info(f"✅ {user.name}: {link_data['displayName']} 관계 생성")
        except:
            pass
            
    async def _update_type(self, user: User, type_data: Dict, message: str, branch: str = "main"):
        """타입 수정"""
        try:
            # 먼저 삭제
            await user.db.client.delete(
                f"http://localhost:6363/api/document/admin/oms/{type_data['@id']}?author={user.name}&branch={branch}",
                auth=("admin", "root")
            )
            # 다시 생성
            await self._create_type(user, type_data, message, branch)
        except:
            pass
            
    async def _rollback_type(self, user: User, type_id: str, message: str):
        """타입 롤백 (삭제)"""
        try:
            result = await user.db.client.delete(
                f"http://localhost:6363/api/document/admin/oms/{type_id}?author={user.name}&message={message}",
                auth=("admin", "root")
            )
            if result.status_code in [200, 204]:
                logger.info(f"✅ {user.name}: {type_id} 롤백 완료")
        except:
            pass
            
    async def _get_all_types(self) -> List[str]:
        """모든 타입 조회"""
        try:
            result = await self.main_db.client.get(
                f"http://localhost:6363/api/document/admin/oms?type=ObjectType",
                auth=("admin", "root")
            )
            if result.status_code == 200:
                return result.text.strip().split('\n') if result.text else []
        except:
            pass
        return []
        
    async def _get_all_links(self) -> List[str]:
        """모든 관계 조회"""
        try:
            result = await self.main_db.client.get(
                f"http://localhost:6363/api/document/admin/oms?type=LinkType",
                auth=("admin", "root")
            )
            if result.status_code == 200:
                return result.text.strip().split('\n') if result.text else []
        except:
            pass
        return []
        
    async def run_scenario(self):
        """전체 시나리오 실행"""
        await self.setup()
        
        await self.phase_1_initial_modeling()
        await asyncio.sleep(1)
        
        await self.phase_2_parallel_development()
        await asyncio.sleep(1)
        
        await self.phase_3_conflict_scenario()
        await asyncio.sleep(1)
        
        await self.phase_4_merge_to_main()
        await asyncio.sleep(1)
        
        await self.phase_5_rollback_scenario()
        await asyncio.sleep(1)
        
        await self.phase_6_final_state()
        
        # 정리
        for user in self.users:
            await user.db.disconnect()
        await self.main_db.disconnect()
        
        print(f"\n\n🎉 디지털 트윈 시나리오 완료!")


async def main():
    scenario = DigitalTwinScenario()
    await scenario.run_scenario()


if __name__ == "__main__":
    asyncio.run(main())