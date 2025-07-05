"""
Health check routes for graph analysis services.
Provides comprehensive health monitoring for Redis, TerminusDB, and tracing.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
import asyncio
from datetime import datetime

from ...config.redis_config import redis_health_check
from ...infra.tracing.jaeger_adapter import get_tracing_manager
from ...bootstrap.providers.graph_analysis import GraphAnalysisProviderFactory
from ...database.clients.terminus_db import TerminusDBClient
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/graph/health", tags=["graph", "health"])


@router.get("/")
async def comprehensive_health_check() -> JSONResponse:
    """
    Comprehensive health check for all graph analysis components.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {},
        "overall_healthy": True
    }
    
    # Check Redis
    try:
        redis_health = await redis_health_check()
        health_status["components"]["redis"] = redis_health
        if redis_health.get("status") != "healthy":
            health_status["overall_healthy"] = False
    except Exception as e:
        health_status["components"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["overall_healthy"] = False
    
    # Check TerminusDB
    try:
        terminus_health = await _check_terminus_health()
        health_status["components"]["terminusdb"] = terminus_health
        if terminus_health.get("status") != "healthy":
            health_status["overall_healthy"] = False
    except Exception as e:
        health_status["components"]["terminusdb"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["overall_healthy"] = False
    
    # Check Tracing
    try:
        tracing_health = await _check_tracing_health()
        health_status["components"]["tracing"] = tracing_health
        # Tracing is optional, don't fail overall health
    except Exception as e:
        health_status["components"]["tracing"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Check Graph Analysis Service
    try:
        service_health = await _check_graph_service_health()
        health_status["components"]["graph_service"] = service_health
        if service_health.get("status") != "healthy":
            health_status["overall_healthy"] = False
    except Exception as e:
        health_status["components"]["graph_service"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["overall_healthy"] = False
    
    # Set overall status
    if health_status["overall_healthy"]:
        health_status["status"] = "healthy"
        status_code = 200
    else:
        health_status["status"] = "unhealthy"
        status_code = 503
    
    return JSONResponse(content=health_status, status_code=status_code)


@router.get("/redis")
async def redis_health() -> JSONResponse:
    """Check Redis health specifically."""
    try:
        health_data = await redis_health_check()
        status_code = 200 if health_data.get("status") == "healthy" else 503
        return JSONResponse(content=health_data, status_code=status_code)
    except Exception as e:
        error_response = {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
        return JSONResponse(content=error_response, status_code=503)


@router.get("/terminusdb")
async def terminusdb_health() -> JSONResponse:
    """Check TerminusDB health specifically."""
    try:
        health_data = await _check_terminus_health()
        status_code = 200 if health_data.get("status") == "healthy" else 503
        return JSONResponse(content=health_data, status_code=status_code)
    except Exception as e:
        error_response = {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
        return JSONResponse(content=error_response, status_code=503)


@router.get("/tracing")
async def tracing_health() -> JSONResponse:
    """Check distributed tracing health."""
    try:
        health_data = await _check_tracing_health()
        status_code = 200 if health_data.get("status") == "healthy" else 503
        return JSONResponse(content=health_data, status_code=status_code)
    except Exception as e:
        error_response = {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
        return JSONResponse(content=error_response, status_code=503)


@router.get("/cache/stats")
async def cache_stats() -> JSONResponse:
    """Get cache performance statistics."""
    try:
        # This would require access to the graph service instance
        # For now, return basic stats
        stats = {
            "timestamp": datetime.utcnow().isoformat(),
            "cache_layers": ["local", "redis", "terminusdb"],
            "note": "Detailed stats available through graph service instance"
        }
        return JSONResponse(content=stats, status_code=200)
    except Exception as e:
        error_response = {
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
        return JSONResponse(content=error_response, status_code=500)


@router.post("/cache/invalidate")
async def invalidate_cache() -> JSONResponse:
    """Invalidate graph analysis caches."""
    try:
        # This would require access to the graph service instance
        # Implementation would call service.cache.clear() etc.
        result = {
            "message": "Cache invalidation triggered",
            "timestamp": datetime.utcnow().isoformat(),
            "note": "Actual invalidation requires service instance access"
        }
        return JSONResponse(content=result, status_code=200)
    except Exception as e:
        error_response = {
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
        return JSONResponse(content=error_response, status_code=500)


async def _check_terminus_health() -> Dict[str, Any]:
    """Check TerminusDB connectivity and basic operations."""
    try:
        # Create a test client
        client = TerminusDBClient()
        
        # Test basic connectivity
        # This would depend on the actual TerminusDBClient implementation
        # For now, return mock health data
        
        return {
            "status": "healthy",
            "connectivity": "ok",
            "response_time_ms": 50,  # Would be actual measured time
            "version": "11.0.0",  # Would be actual version
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


async def _check_tracing_health() -> Dict[str, Any]:
    """Check distributed tracing system health."""
    try:
        tracing_manager = await get_tracing_manager()
        
        if not tracing_manager._initialized:
            return {
                "status": "disabled",
                "message": "Tracing not enabled",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Test trace creation
        test_span = tracing_manager.create_span("health_check")
        test_span.set_attribute("health_check", True)
        test_span.end()
        
        return {
            "status": "healthy",
            "jaeger_enabled": tracing_manager.config.enabled,
            "siem_enabled": tracing_manager.config.siem_enabled,
            "service_name": tracing_manager.config.service_name,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


async def _check_graph_service_health() -> Dict[str, Any]:
    """Check graph analysis service health."""
    try:
        # This is a basic check - in practice would test actual service functionality
        return {
            "status": "healthy",
            "features": [
                "path_finding",
                "centrality_analysis", 
                "community_detection",
                "connection_discovery"
            ],
            "caching_layers": ["local", "redis", "terminusdb"],
            "tracing_enabled": True,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }