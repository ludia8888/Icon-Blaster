"""
GraphQL Subscription Resolvers - Real-time Event Streaming
Foundry OMS 원칙: P3 (Event-Driven), P4 (Cache-First)
"""
import asyncio
import logging
import uuid
from typing import AsyncGenerator, Optional

import strawberry
from strawberry.types import Info

from shared.auth import User

from .realtime_publisher import realtime_publisher
from .schema import (
    ActionProgressEvent,
    BranchChangeEvent,
    ProposalUpdateEvent,
    ResourceTypeEnum,
    SchemaChangeEvent,
)

logger = logging.getLogger(__name__)


@strawberry.type
class Subscription:
    """GraphQL Subscription 루트 - Real-time 이벤트 스트리밍"""

    @strawberry.subscription
    async def schema_changes(
        self,
        info: Info,
        branch: Optional[str] = None,
        resource_types: Optional[list[ResourceTypeEnum]] = None
    ) -> AsyncGenerator[SchemaChangeEvent, None]:
        """
        스키마 변경 이벤트 구독
        
        P3 Event-Driven: NATS JetStream 기반 실시간 이벤트
        P4 Cache-First: 브랜치별 필터링으로 효율적인 구독
        """
        user: Optional[User] = info.context.get("user")
        subscription_id = str(uuid.uuid4())

        # 사용자 인증 확인
        if not user:
            logger.warning("Unauthorized subscription attempt for schema changes")
            return

        logger.info(f"Starting schema changes subscription for user {user.user_id}")

        try:
            # 구독 등록
            realtime_publisher.add_schema_subscription(subscription_id)

            # NATS 연결 및 구독 설정
            async with realtime_publisher.connection():
                # 필터 주제 설정
                if branch and resource_types:
                    # 특정 브랜치와 리소스 타입 필터링
                    filter_subjects = [
                        f"oms.schema.*.{rt.value.lower()}.{branch}"
                        for rt in resource_types
                    ]
                elif branch:
                    # 특정 브랜치만 필터링
                    filter_subjects = [f"oms.schema.*.*.{branch}"]
                elif resource_types:
                    # 특정 리소스 타입만 필터링
                    filter_subjects = [
                        f"oms.schema.*.{rt.value.lower()}.*"
                        for rt in resource_types
                    ]
                else:
                    # 모든 스키마 변경 이벤트
                    filter_subjects = ["oms.schema.>"]

                # 각 필터에 대해 구독 설정
                event_queue = asyncio.Queue()

                async def event_handler(event_data):
                    """이벤트 핸들러"""
                    try:
                        # SchemaChangeEvent로 변환
                        schema_event = SchemaChangeEvent(
                            event_id=event_data.get("event_id", ""),
                            event_type=event_data.get("event_type", ""),
                            resource_type=ResourceTypeEnum(event_data.get("resource_type", "object_type")),
                            resource_id=event_data.get("resource_id", ""),
                            resource_name=event_data.get("resource_name", ""),
                            branch=event_data.get("branch", ""),
                            changes=event_data.get("changes", {}),
                            timestamp=event_data.get("timestamp"),
                            user_id=event_data.get("user_id", ""),
                            version_hash=event_data.get("version_hash", "")
                        )
                        await event_queue.put(schema_event)
                    except Exception as e:
                        logger.error(f"Error processing schema change event: {e}")

                # 각 필터 주제에 대해 구독
                for filter_subject in filter_subjects:
                    consumer_name = f"graphql_schema_{subscription_id}_{filter_subject.replace('.', '_').replace('>', 'all')}"
                    await realtime_publisher.subscribe_to_stream(
                        "OMS_SCHEMA_EVENTS",
                        consumer_name,
                        event_handler,
                        filter_subject
                    )

                # 이벤트 스트리밍
                try:
                    while True:
                        event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                        yield event
                except asyncio.TimeoutError:
                    # 30초 타임아웃으로 연결 유지 확인
                    continue
                except asyncio.CancelledError:
                    logger.info(f"Schema changes subscription cancelled for user {user.user_id}")
                    break

        except Exception as e:
            logger.error(f"Error in schema changes subscription: {e}")
        finally:
            # 구독 정리
            realtime_publisher.remove_schema_subscription(subscription_id)
            logger.info(f"Cleaned up schema changes subscription for user {user.user_id}")

    @strawberry.subscription
    async def branch_changes(
        self,
        info: Info,
        branch_names: Optional[list[str]] = None
    ) -> AsyncGenerator[BranchChangeEvent, None]:
        """
        브랜치 변경 이벤트 구독
        
        P3 Event-Driven: Git 워크플로우 실시간 알림
        """
        user: Optional[User] = info.context.get("user")
        subscription_id = str(uuid.uuid4())

        if not user:
            logger.warning("Unauthorized subscription attempt for branch changes")
            return

        logger.info(f"Starting branch changes subscription for user {user.user_id}")

        try:
            realtime_publisher.add_branch_subscription(subscription_id)

            async with realtime_publisher.connection():
                # 필터 설정
                if branch_names:
                    filter_subjects = [f"oms.branch.*.{branch}" for branch in branch_names]
                else:
                    filter_subjects = ["oms.branch.>"]

                event_queue = asyncio.Queue()

                async def event_handler(event_data):
                    try:
                        branch_event = BranchChangeEvent(
                            event_id=event_data.get("event_id", ""),
                            branch_name=event_data.get("branch_name", ""),
                            event_type=event_data.get("event_type", ""),
                            commit_hash=event_data.get("commit_hash"),
                            commit_message=event_data.get("commit_message"),
                            author=event_data.get("author", ""),
                            timestamp=event_data.get("timestamp"),
                            affected_resources=event_data.get("affected_resources", [])
                        )
                        await event_queue.put(branch_event)
                    except Exception as e:
                        logger.error(f"Error processing branch change event: {e}")

                # 구독 설정
                for filter_subject in filter_subjects:
                    consumer_name = f"graphql_branch_{subscription_id}_{filter_subject.replace('.', '_').replace('>', 'all')}"
                    await realtime_publisher.subscribe_to_stream(
                        "OMS_BRANCH_EVENTS",
                        consumer_name,
                        event_handler,
                        filter_subject
                    )

                # 이벤트 스트리밍
                try:
                    while True:
                        event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                        yield event
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    logger.info(f"Branch changes subscription cancelled for user {user.user_id}")
                    break

        except Exception as e:
            logger.error(f"Error in branch changes subscription: {e}")
        finally:
            realtime_publisher.remove_branch_subscription(subscription_id)
            logger.info(f"Cleaned up branch changes subscription for user {user.user_id}")

    @strawberry.subscription
    async def proposal_updates(
        self,
        info: Info,
        proposal_ids: Optional[list[str]] = None,
        reviewer_id: Optional[str] = None
    ) -> AsyncGenerator[ProposalUpdateEvent, None]:
        """
        제안(PR) 업데이트 이벤트 구독
        
        P3 Event-Driven: 협업 워크플로우 실시간 알림
        """
        user: Optional[User] = info.context.get("user")
        subscription_id = str(uuid.uuid4())

        if not user:
            logger.warning("Unauthorized subscription attempt for proposal updates")
            return

        logger.info(f"Starting proposal updates subscription for user {user.user_id}")

        try:
            realtime_publisher.add_proposal_subscription(subscription_id)

            async with realtime_publisher.connection():
                # 필터 설정
                if proposal_ids:
                    filter_subjects = [f"oms.proposal.*.{pid}" for pid in proposal_ids]
                else:
                    filter_subjects = ["oms.proposal.>"]

                event_queue = asyncio.Queue()

                async def event_handler(event_data):
                    try:
                        # 리뷰어 필터링
                        if reviewer_id and event_data.get("reviewer") != reviewer_id:
                            return

                        proposal_event = ProposalUpdateEvent(
                            event_id=event_data.get("event_id", ""),
                            proposal_id=event_data.get("proposal_id", ""),
                            event_type=event_data.get("event_type", ""),
                            title=event_data.get("title", ""),
                            status=event_data.get("status", ""),
                            reviewer=event_data.get("reviewer"),
                            comment=event_data.get("comment"),
                            timestamp=event_data.get("timestamp")
                        )
                        await event_queue.put(proposal_event)
                    except Exception as e:
                        logger.error(f"Error processing proposal update event: {e}")

                # 구독 설정
                for filter_subject in filter_subjects:
                    consumer_name = f"graphql_proposal_{subscription_id}_{filter_subject.replace('.', '_').replace('>', 'all')}"
                    await realtime_publisher.subscribe_to_stream(
                        "OMS_PROPOSAL_EVENTS",
                        consumer_name,
                        event_handler,
                        filter_subject
                    )

                # 이벤트 스트리밍
                try:
                    while True:
                        event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                        yield event
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    logger.info(f"Proposal updates subscription cancelled for user {user.user_id}")
                    break

        except Exception as e:
            logger.error(f"Error in proposal updates subscription: {e}")
        finally:
            realtime_publisher.remove_proposal_subscription(subscription_id)
            logger.info(f"Cleaned up proposal updates subscription for user {user.user_id}")

    @strawberry.subscription
    async def action_progress(
        self,
        info: Info,
        job_ids: Optional[list[str]] = None,
        user_jobs_only: bool = False
    ) -> AsyncGenerator[ActionProgressEvent, None]:
        """
        액션 진행 상황 이벤트 구독
        
        P3 Event-Driven: 장기 실행 작업 모니터링
        """
        user: Optional[User] = info.context.get("user")
        subscription_id = str(uuid.uuid4())

        if not user:
            logger.warning("Unauthorized subscription attempt for action progress")
            return

        logger.info(f"Starting action progress subscription for user {user.user_id}")

        try:
            realtime_publisher.add_action_subscription(subscription_id)

            async with realtime_publisher.connection():
                # 필터 설정
                if job_ids:
                    filter_subjects = [f"oms.action.*.{jid}" for jid in job_ids]
                else:
                    filter_subjects = ["oms.action.>"]

                event_queue = asyncio.Queue()

                async def event_handler(event_data):
                    try:
                        # 사용자 작업 필터링 (사용자별 작업만 표시)
                        if user_jobs_only:
                            # TODO: 작업 소유자 확인 로직 구현
                            pass

                        action_event = ActionProgressEvent(
                            event_id=event_data.get("event_id", ""),
                            job_id=event_data.get("job_id", ""),
                            status=event_data.get("status", ""),
                            progress_percentage=event_data.get("progress_percentage", 0),
                            current_step=event_data.get("current_step", ""),
                            total_steps=event_data.get("total_steps", 1),
                            message=event_data.get("message"),
                            estimated_completion=event_data.get("estimated_completion"),
                            timestamp=event_data.get("timestamp")
                        )
                        await event_queue.put(action_event)
                    except Exception as e:
                        logger.error(f"Error processing action progress event: {e}")

                # 구독 설정
                for filter_subject in filter_subjects:
                    consumer_name = f"graphql_action_{subscription_id}_{filter_subject.replace('.', '_').replace('>', 'all')}"
                    await realtime_publisher.subscribe_to_stream(
                        "OMS_ACTION_EVENTS",
                        consumer_name,
                        event_handler,
                        filter_subject
                    )

                # 이벤트 스트리밍
                try:
                    while True:
                        event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                        yield event
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    logger.info(f"Action progress subscription cancelled for user {user.user_id}")
                    break

        except Exception as e:
            logger.error(f"Error in action progress subscription: {e}")
        finally:
            realtime_publisher.remove_action_subscription(subscription_id)
            logger.info(f"Cleaned up action progress subscription for user {user.user_id}")
