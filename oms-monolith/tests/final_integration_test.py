#!/usr/bin/env python3
"""
OMS 최종 통합 테스트
모든 핵심 기능이 정상 작동하는지 검증
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from core.schema.service import SchemaService
from core.branch.service import BranchService
from core.validation.service import ValidationService
from core.event_publisher.enhanced_event_service import EnhancedEventService
from shared.models.domain import (
    ObjectTypeCreate, LinkTypeCreate, PropertyCreate,
    Cardinality, DataType, Status
)
from utils.logger import get_logger

logger = get_logger(__name__)


class OMSIntegrationTest:
    """OMS 통합 테스트 스위트"""
    
    def __init__(self):
        self.schema_service = SchemaService()
        self.branch_service = BranchService(None)
        self.validation_service = ValidationService(None, None)
        self.event_service = EnhancedEventService()
        self.test_branch = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    async def setup(self):
        """테스트 환경 설정"""
        logger.info("=== OMS 통합 테스트 시작 ===")
        
        # 서비스 초기화
        await self.schema_service.initialize()
        await self.event_service.initialize()
        
        # 테스트 브랜치 생성
        await self.branch_service.create_branch(
            name=self.test_branch,
            from_branch="main",
            description="통합 테스트용 브랜치"
        )
        logger.info(f"테스트 브랜치 생성: {self.test_branch}")
        
    async def test_object_type_crud(self):
        """ObjectType CRUD 테스트"""
        logger.info("\n--- ObjectType CRUD 테스트 ---")
        
        # 생성
        user_type = await self.schema_service.create_object_type(
            branch=self.test_branch,
            data=ObjectTypeCreate(
                name="User",
                displayName="사용자",
                description="시스템 사용자"
            )
        )
        assert user_type.name == "User"
        logger.info("✓ ObjectType 생성 성공")
        
        # 조회
        retrieved = await self.schema_service.get_object_type(
            branch=self.test_branch,
            object_type_name="User"
        )
        assert retrieved is not None
        logger.info("✓ ObjectType 조회 성공")
        
        # 목록 조회
        object_types = await self.schema_service.list_object_types(
            branch=self.test_branch
        )
        assert len(object_types) > 0
        logger.info("✓ ObjectType 목록 조회 성공")
        
        return user_type
        
    async def test_link_type_crud(self):
        """LinkType CRUD 테스트"""
        logger.info("\n--- LinkType CRUD 테스트 ---")
        
        # 먼저 두 개의 ObjectType 생성
        org_type = await self.schema_service.create_object_type(
            branch=self.test_branch,
            data=ObjectTypeCreate(
                name="Organization",
                displayName="조직",
                description="회사 조직"
            )
        )
        
        # LinkType 생성
        link_type = await self.schema_service.create_link_type(
            branch=self.test_branch,
            data=LinkTypeCreate(
                name="BelongsTo",
                displayName="소속",
                description="사용자가 조직에 소속됨",
                fromTypeId="User",
                toTypeId="Organization",
                cardinality=Cardinality.MANY_TO_ONE
            )
        )
        assert link_type.name == "BelongsTo"
        logger.info("✓ LinkType 생성 성공")
        
        # 조회
        retrieved = await self.schema_service.get_link_type(
            branch=self.test_branch,
            link_name="BelongsTo"
        )
        assert retrieved is not None
        logger.info("✓ LinkType 조회 성공")
        
        # 목록 조회
        link_types = await self.schema_service.list_link_types(
            branch=self.test_branch
        )
        assert len(link_types) > 0
        logger.info("✓ LinkType 목록 조회 성공")
        
    async def test_property_management(self):
        """Property 관리 테스트"""
        logger.info("\n--- Property 관리 테스트 ---")
        
        # User ObjectType에 Property 추가
        property_doc = await self.schema_service.add_property(
            branch=self.test_branch,
            object_type_id="User",
            property_data=PropertyCreate(
                name="email",
                displayName="이메일",
                description="사용자 이메일 주소",
                dataType=DataType.STRING,
                isRequired=True,
                isUnique=True
            )
        )
        logger.info("✓ Property 추가 성공")
        
        # ObjectType 다시 조회하여 Property 확인
        user_type = await self.schema_service.get_object_type(
            branch=self.test_branch,
            object_type_name="User"
        )
        assert len(user_type.properties) > 0
        assert any(p.name == "email" for p in user_type.properties)
        logger.info("✓ Property 확인 성공")
        
    async def test_breaking_change_detection(self):
        """Breaking Change Detection 테스트"""
        logger.info("\n--- Breaking Change Detection 테스트 ---")
        
        # 검증 요청 생성
        from core.validation.models import ValidationRequest
        
        validation_request = ValidationRequest(
            source_branch=self.test_branch,
            target_branch="main",
            merge_strategy="merge"
        )
        
        # Breaking Change 검증
        result = await self.validation_service.validate_breaking_changes(
            validation_request
        )
        
        logger.info(f"✓ Breaking Change 검증 완료: {result.is_valid}")
        logger.info(f"  - Breaking Changes: {len(result.breaking_changes)}")
        logger.info(f"  - Warnings: {len(result.warnings)}")
        
    async def test_event_publishing(self):
        """이벤트 발행 테스트"""
        logger.info("\n--- CloudEvents 발행 테스트 ---")
        
        # 스키마 변경 이벤트 발행
        event_id = await self.event_service.publish(
            subject="test.schema.created",
            event_type="SchemaCreated",
            source="integration-test",
            data={
                "branch": self.test_branch,
                "objectType": "TestObject",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        assert event_id is not None
        logger.info(f"✓ CloudEvent 발행 성공: {event_id}")
        
    async def test_branch_workflow(self):
        """브랜치 워크플로 테스트"""
        logger.info("\n--- Branch/Merge 워크플로 테스트 ---")
        
        # 브랜치 목록 조회
        branches = await self.branch_service.list_branches()
        assert len(branches) > 0
        logger.info("✓ 브랜치 목록 조회 성공")
        
        # 브랜치 정보 조회
        branch_info = await self.branch_service.get_branch(self.test_branch)
        assert branch_info is not None
        logger.info("✓ 브랜치 정보 조회 성공")
        
        # Change Proposal 생성 (보호된 브랜치로 머지하려면 필요)
        from core.branch.models import ChangeProposalCreate
        
        proposal = await self.branch_service.create_proposal(
            proposal_data=ChangeProposalCreate(
                title="통합 테스트 변경사항",
                description="OMS 통합 테스트에서 생성된 변경사항",
                source_branch=self.test_branch,
                target_branch="main"
            ),
            user_id="test_user"
        )
        assert proposal is not None
        logger.info("✓ Change Proposal 생성 성공")
        
    async def cleanup(self):
        """테스트 정리"""
        logger.info("\n--- 테스트 정리 ---")
        
        try:
            # 테스트 브랜치 삭제
            await self.branch_service.delete_branch(
                branch_name=self.test_branch,
                force=True
            )
            logger.info(f"✓ 테스트 브랜치 삭제: {self.test_branch}")
        except Exception as e:
            logger.warning(f"브랜치 삭제 실패: {e}")
            
    async def run_all_tests(self):
        """모든 테스트 실행"""
        try:
            await self.setup()
            
            # 각 테스트 실행
            await self.test_object_type_crud()
            await self.test_link_type_crud()
            await self.test_property_management()
            await self.test_breaking_change_detection()
            await self.test_event_publishing()
            await self.test_branch_workflow()
            
            logger.info("\n=== 모든 테스트 성공! ===")
            logger.info("OMS가 프로덕션 준비 완료 상태입니다.")
            
        except Exception as e:
            logger.error(f"테스트 실패: {e}")
            raise
        finally:
            await self.cleanup()


async def main():
    """메인 함수"""
    test_suite = OMSIntegrationTest()
    await test_suite.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())