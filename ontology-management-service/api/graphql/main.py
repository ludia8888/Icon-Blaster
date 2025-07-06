"""
GraphQL WebSocket Service - Handles real-time subscriptions
This service focuses on WebSocket connections and GraphQL subscriptions.
For HTTP GraphQL queries/mutations, use modular_main.py
"""
import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Removed dangerous create_scope_rbac_middleware import

# shared 모듈 import를 위한 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.graphql.auth import get_current_user_optional, GraphQLWebSocketAuth, AuthenticationManager
from core.auth_utils import UserContext

from .realtime_publisher import realtime_publisher
from .websocket_manager import websocket_manager

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
auth_manager: Optional[AuthenticationManager] = None
graphql_ws_auth: Optional[GraphQLWebSocketAuth] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 실행
    global auth_manager, graphql_ws_auth
    logger.info("GraphQL Service starting...")

    try:
        # Authentication Manager 초기화
        auth_manager = AuthenticationManager()
        await auth_manager.init_redis()
        logger.info("Authentication manager initialized")

        # GraphQL WebSocket 인증 초기화
        graphql_ws_auth = GraphQLWebSocketAuth(auth_manager)
        logger.info("GraphQL WebSocket authentication initialized")

        # NATS 연결 초기화
        await realtime_publisher.connect()
        logger.info("Connected to NATS for real-time events")
    except Exception as e:
        logger.warning(f"Failed to connect to NATS: {e}")

    yield

    # 종료 시 실행
    logger.info("GraphQL Service shutting down gracefully...")

    try:
        # 1. WebSocket 연결 정리
        logger.info("Cleaning up WebSocket connections...")
        websocket_manager.stop_background_tasks()

        # 2. NATS 연결 해제
        logger.info("Disconnecting from NATS...")
        await realtime_publisher.disconnect()

        # 3. Authentication Manager 정리
        if auth_manager:
            logger.info("Closing authentication manager...")
            await auth_manager.close()

        # 4. 새로운 GraphQL 요청 중단
        logger.info("Stopping new GraphQL requests...")

        # 5. 진행 중인 GraphQL 쿼리 완료 대기
        logger.info("Waiting for GraphQL queries to complete...")
        await asyncio.sleep(1)  # 짧은 대기 시간

        logger.info("GraphQL Service shutdown completed gracefully")
    except Exception as e:
        logger.error(f"Error during graceful shutdown: {e}")
        raise


app = FastAPI(
    title="OMS GraphQL WebSocket Service",
    description="WebSocket service for GraphQL subscriptions",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# RBAC 미들웨어 추가 - 실제 ScopeRBACMiddleware 사용
from core.iam.scope_rbac_middleware import ScopeRBACMiddleware
app.add_middleware(ScopeRBACMiddleware, config={
    "public_paths": ["/health", "/", "/graphql", "/ws", "/schema"]
})


# Remove GraphQL router - this service only handles WebSocket connections
# For GraphQL HTTP endpoints, use modular_main.py


@app.get("/health")
async def health_check():
    """헬스 체크 엔드포인트"""
    return {
        "status": "healthy",
        "service": "graphql-service",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """루트 엔드포인트 - GraphQL 엔드포인트 안내"""
    return {
        "message": "OMS GraphQL Service",
        "graphql_endpoint": "/graphql",
        "graphiql_endpoint": "/graphql",
        "documentation": "Visit /graphql in your browser to access GraphQL Playground"
    }


@app.get("/schema")
async def get_schema():
    """WebSocket subscription info"""
    return {
        "service": "websocket-only",
        "subscriptions": ["object_type_updates"],
        "note": "For GraphQL schema, use the HTTP endpoint on port 8006"
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 엔드포인트 - GraphQL Subscriptions
    
    P3 Event-Driven: WebSocket 기반 실시간 이벤트 스트리밍
    P4 Cache-First: 연결 풀링 및 효율적인 관리
    """
    # WebSocket 인증 수행
    user_context = None
    if graphql_ws_auth:
        try:
            user_context = await graphql_ws_auth.authenticate_graphql_subscription(websocket)
            if user_context:
                logger.info(f"WebSocket authenticated: {user_context.username}")
        except Exception as e:
            logger.error(f"WebSocket authentication failed: {e}")
            await websocket.close(code=1008, reason="Authentication failed")
            return
    else:
        logger.warning("GraphQL WebSocket authentication not initialized, allowing anonymous connection")
        await websocket.accept()

    connection = None
    try:
        # WebSocket 연결 수락 및 등록 (user_context를 user로 전달)
        connection = await websocket_manager.connect(websocket, user_context)
        logger.info(f"WebSocket connection established: {connection.connection_id}")

        # 환영 메시지 전송
        await connection.send_message({
            "type": "connection_ack",
            "connection_id": connection.connection_id,
            "message": "WebSocket connection established for GraphQL subscriptions"
        })

        # 메시지 처리 루프
        while True:
            try:
                # 클라이언트 메시지 수신
                data = await websocket.receive_text()
                message = json.loads(data) if data else {}

                connection.messages_received += 1
                message_type = message.get("type", "")

                if message_type == "ping":
                    # Ping 응답
                    connection.update_last_ping()
                    await connection.send_message({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })

                elif message_type == "pong":
                    # Pong 수신
                    connection.update_last_ping()

                elif message_type == "subscription_start":
                    # 구독 시작 - 권한 확인 포함
                    subscription_id = message.get("subscription_id")
                    subscription_name = message.get("subscription_name", "")
                    variables = message.get("variables", {})

                    if subscription_id:
                        # 인증된 사용자만 구독 권한 확인
                        if user_context and graphql_ws_auth:
                            authorized = await graphql_ws_auth.authorize_subscription(
                                user_context, subscription_name, variables
                            )
                            if not authorized:
                                await connection.send_message({
                                    "type": "subscription_error",
                                    "subscription_id": subscription_id,
                                    "message": "Insufficient permissions for this subscription"
                                })
                                continue

                        websocket_manager.add_subscription(
                            connection.connection_id,
                            subscription_id
                        )
                        await connection.send_message({
                            "type": "subscription_ack",
                            "subscription_id": subscription_id
                        })

                elif message_type == "subscription_stop":
                    # 구독 중지
                    subscription_id = message.get("subscription_id")
                    if subscription_id:
                        websocket_manager.remove_subscription(
                            connection.connection_id,
                            subscription_id
                        )
                        await connection.send_message({
                            "type": "subscription_complete",
                            "subscription_id": subscription_id
                        })

            except WebSocketDisconnect:
                logger.info(f"WebSocket client disconnected: {connection.connection_id}")
                break
            except json.JSONDecodeError:
                await connection.send_message({
                    "type": "error",
                    "message": "Invalid JSON format"
                })
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")
                await connection.send_message({
                    "type": "error",
                    "message": "Internal server error"
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected during connection setup")
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        # 연결 정리
        if connection:
            await websocket_manager.disconnect(connection.connection_id)


@app.get("/ws/stats")
async def websocket_stats():
    """WebSocket 연결 통계"""
    return websocket_manager.get_statistics()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
