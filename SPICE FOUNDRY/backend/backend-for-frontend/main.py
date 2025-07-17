"""
Backend for Frontend (BFF) Service
Provides a unified API interface for the Ontology Management System
"""

from fastapi import FastAPI, HTTPException, Query, Path, Body, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import logging
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OMS backend URL
OMS_URL = "http://localhost:8000"

# Create HTTP client
http_client = httpx.AsyncClient(base_url=OMS_URL, timeout=30.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    logger.info("Starting BFF service...")
    yield
    logger.info("Shutting down BFF service...")
    await http_client.aclose()

# Create FastAPI app
app = FastAPI(
    title="Backend for Frontend (BFF)",
    description="Unified API interface for Ontology Management System",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper functions
async def forward_request(method: str, path: str, **kwargs) -> Dict[str, Any]:
    """Forward request to OMS backend"""
    try:
        response = await http_client.request(method, path, **kwargs)
        return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"OMS error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=e.response.json().get("detail", str(e))
        )
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backend service error: {str(e)}"
        )

# Health endpoint
@app.get("/health")
async def health_check():
    """Check BFF and OMS health"""
    try:
        # Check OMS health
        oms_response = await http_client.get("/health")
        oms_health = oms_response.json()
        
        return {
            "status": "healthy",
            "service": "BFF",
            "timestamp": datetime.now().isoformat(),
            "backend": {
                "oms": oms_health
            }
        }
    except Exception as e:
        return {
            "status": "degraded",
            "service": "BFF",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

# Database endpoints
@app.post("/api/v1/databases", status_code=status.HTTP_200_OK)
async def create_database(database: Dict[str, Any] = Body(...)):
    """Create a new database"""
    # Validate required fields
    if "name" not in database:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database name is required"
        )
    
    # Validate database name format
    name = database["name"]
    if not name.replace("_", "").isalnum():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database name must be alphanumeric with underscores only"
        )
    
    # Forward to OMS
    return await forward_request("POST", "/api/v1/databases", json=database)

@app.get("/api/v1/databases")
async def list_databases():
    """List all databases"""
    return await forward_request("GET", "/api/v1/databases")

@app.get("/api/v1/databases/{db_name}")
async def get_database(db_name: str = Path(...)):
    """Get database details"""
    return await forward_request("GET", f"/api/v1/databases/{db_name}")

@app.delete("/api/v1/databases/{db_name}")
async def delete_database(db_name: str = Path(...)):
    """Delete a database"""
    return await forward_request("DELETE", f"/api/v1/databases/{db_name}")

# Ontology class endpoints
@app.post("/api/v1/databases/{db_name}/classes", status_code=status.HTTP_200_OK)
async def create_class(
    db_name: str = Path(...),
    ontology_class: Dict[str, Any] = Body(...)
):
    """Create a new ontology class"""
    # Validate required fields
    if "@type" not in ontology_class:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="@type field is required"
        )
    
    if "@id" not in ontology_class:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="@id field is required"
        )
    
    # Validate properties if present
    if "properties" in ontology_class:
        for prop_name, prop_def in ontology_class["properties"].items():
            if "@type" not in prop_def:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Property '{prop_name}' must have @type"
                )
    
    # Forward to OMS
    return await forward_request(
        "POST",
        f"/api/v1/databases/{db_name}/classes",
        json=ontology_class
    )

@app.get("/api/v1/databases/{db_name}/classes")
async def list_classes(
    db_name: str = Path(...),
    type: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    offset: Optional[int] = Query(None)
):
    """List ontology classes"""
    params = {}
    if type:
        params["type"] = type
    if limit:
        params["limit"] = limit
    if offset:
        params["offset"] = offset
        
    return await forward_request(
        "GET",
        f"/api/v1/databases/{db_name}/classes",
        params=params
    )

@app.get("/api/v1/databases/{db_name}/classes/{class_id}")
async def get_class(
    db_name: str = Path(...),
    class_id: str = Path(...),
    language: Optional[str] = Query("en")
):
    """Get ontology class with label mapping"""
    return await forward_request(
        "GET",
        f"/api/v1/databases/{db_name}/classes/{class_id}",
        params={"language": language}
    )

@app.put("/api/v1/databases/{db_name}/classes/{class_id}")
async def update_class(
    db_name: str = Path(...),
    class_id: str = Path(...),
    ontology_class: Dict[str, Any] = Body(...)
):
    """Update ontology class"""
    return await forward_request(
        "PUT",
        f"/api/v1/databases/{db_name}/classes/{class_id}",
        json=ontology_class
    )

@app.delete("/api/v1/databases/{db_name}/classes/{class_id}")
async def delete_class(
    db_name: str = Path(...),
    class_id: str = Path(...)
):
    """Delete ontology class"""
    return await forward_request(
        "DELETE",
        f"/api/v1/databases/{db_name}/classes/{class_id}"
    )

# Branch endpoints
@app.post("/api/v1/databases/{db_name}/branches", status_code=status.HTTP_200_OK)
async def create_branch(
    db_name: str = Path(...),
    branch: Dict[str, Any] = Body(...)
):
    """Create a new branch"""
    if "name" not in branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Branch name is required"
        )
    
    return await forward_request(
        "POST",
        f"/api/v1/databases/{db_name}/branches",
        json=branch
    )

@app.get("/api/v1/databases/{db_name}/branches")
async def list_branches(db_name: str = Path(...)):
    """List branches"""
    return await forward_request(
        "GET",
        f"/api/v1/databases/{db_name}/branches"
    )

@app.get("/api/v1/databases/{db_name}/branches/{branch_name}")
async def get_branch(
    db_name: str = Path(...),
    branch_name: str = Path(...)
):
    """Get branch details"""
    return await forward_request(
        "GET",
        f"/api/v1/databases/{db_name}/branches/{branch_name}"
    )

# Version endpoints
@app.get("/api/v1/databases/{db_name}/versions")
async def list_versions(
    db_name: str = Path(...),
    branch: Optional[str] = Query("main"),
    limit: Optional[int] = Query(50)
):
    """List version history"""
    return await forward_request(
        "GET",
        f"/api/v1/databases/{db_name}/versions",
        params={"branch": branch, "limit": limit}
    )

@app.get("/api/v1/databases/{db_name}/versions/{version_id}")
async def get_version(
    db_name: str = Path(...),
    version_id: str = Path(...)
):
    """Get version details"""
    return await forward_request(
        "GET",
        f"/api/v1/databases/{db_name}/versions/{version_id}"
    )

# Query endpoints
@app.post("/api/v1/databases/{db_name}/query")
async def execute_query(
    db_name: str = Path(...),
    query: Dict[str, Any] = Body(...)
):
    """Execute a query"""
    return await forward_request(
        "POST",
        f"/api/v1/databases/{db_name}/query",
        json=query
    )

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "timestamp": datetime.now().isoformat()
            }
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": 500,
                "message": "Internal server error",
                "timestamp": datetime.now().isoformat()
            }
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        log_level="info"
    )