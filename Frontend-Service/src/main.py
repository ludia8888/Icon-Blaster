"""
Frontend Service - Main Application Entry Point
OMS 이벤트를 구독하여 UI에 실시간 업데이트 제공
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware

from .websocket_manager import frontend_websocket_manager
from .realtime_publisher import frontend_realtime_publisher
from .auth import verify_websocket_token

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 라이프사이클 관리"""
    # 시작: OMS 이벤트 구독 시작
    logger.info("Starting Frontend Service...")
    
    try:
        # NATS 연결 및 OMS 이벤트 구독
        await frontend_realtime_publisher.connect()
        logger.info("Connected to NATS and subscribed to OMS events")
        
        yield
        
    finally:
        # 종료: 연결 정리
        logger.info("Shutting down Frontend Service...")
        
        # WebSocket 연결 정리
        frontend_websocket_manager.stop_background_tasks()
        
        # NATS 연결 해제
        await frontend_realtime_publisher.disconnect()
        
        logger.info("Frontend Service shutdown complete")


# FastAPI 애플리케이션 생성
app = FastAPI(
    title="OMS Frontend Service",
    description="OMS 실시간 UI 업데이트 서비스",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check 엔드포인트"""
    return {
        "status": "healthy",
        "service": "Frontend Service",
        "version": "1.0.0",
        "websocket_stats": frontend_websocket_manager.get_statistics(),
        "subscription_stats": frontend_realtime_publisher.get_subscription_stats()
    }


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = None
):
    """
    WebSocket 연결 엔드포인트
    
    실시간 UI 업데이트를 위한 WebSocket 연결:
    - 스키마 변경 알림
    - 브랜치 상태 업데이트  
    - 사용자 알림
    - 보안 이벤트 알림
    """
    user = None
    if token:
        try:
            user = verify_websocket_token(token)
        except Exception as e:
            logger.warning(f"WebSocket authentication failed: {e}")
    
    # WebSocket 연결 수락
    connection = await frontend_websocket_manager.connect(websocket, user)
    
    try:
        while True:
            # 클라이언트 메시지 수신
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # 메시지 타입에 따른 처리
            if message.get("type") == "subscribe":
                # 구독 요청 처리
                subscription_id = message.get("subscription_id")
                if subscription_id:
                    frontend_websocket_manager.add_subscription(
                        connection.connection_id, 
                        subscription_id
                    )
                    await connection.send_message({
                        "type": "subscription_confirmed",
                        "subscription_id": subscription_id
                    })
                    
            elif message.get("type") == "unsubscribe":
                # 구독 해제 요청 처리
                subscription_id = message.get("subscription_id")
                if subscription_id:
                    frontend_websocket_manager.remove_subscription(
                        connection.connection_id,
                        subscription_id
                    )
                    await connection.send_message({
                        "type": "subscription_cancelled", 
                        "subscription_id": subscription_id
                    })
                    
            elif message.get("type") == "pong":
                # Pong 응답 처리
                connection.update_last_ping()
                
            connection.messages_received += 1
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {connection.connection_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # 연결 정리
        await frontend_websocket_manager.disconnect(connection.connection_id)


@app.get("/api/v1/connections")
async def get_connections():
    """현재 WebSocket 연결 상태 조회"""
    return frontend_websocket_manager.get_statistics()


@app.get("/api/v1/subscriptions")
async def get_subscriptions():
    """현재 구독 상태 조회"""
    return frontend_realtime_publisher.get_subscription_stats()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    )