"""
Test API Endpoints for Full Stack Testing
Provides mock endpoints for testing all TerminusDB extension features
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import hashlib
import math

router = APIRouter(prefix="/api/v1", tags=["test"])

# Models
class DeltaEncodeRequest(BaseModel):
    old: Dict[str, Any]
    new: Dict[str, Any]

class EmbeddingRequest(BaseModel):
    texts: List[str]
    provider: str = "local"

class SearchRequest(BaseModel):
    query: str
    embeddings: List[List[float]]
    top_k: int = 5

class TimeResourceRequest(BaseModel):
    resource_id: str
    data: Dict[str, Any]
    timestamp: str

class CacheSetRequest(BaseModel):
    key: str
    value: Any
    ttl: Optional[int] = 300

class DocumentFoldRequest(BaseModel):
    document: Dict[str, Any]
    level: str = "collapsed"

class DocumentUnfoldRequest(BaseModel):
    document: Dict[str, Any]
    path: str

class MetadataParseRequest(BaseModel):
    content: str

class AuditLogRequest(BaseModel):
    action: str
    resource: str
    user_id: str
    details: Dict[str, Any]
    timestamp: str

# In-memory storage for testing
time_travel_storage = {}
cache_storage = {}
cache_stats = {"hits": 0, "misses": 0, "sets": 0}
audit_logs = []

# Delta Encoding
@router.post("/delta/encode")
async def encode_delta(request: DeltaEncodeRequest):
    """Encode delta between two documents"""
    # Simple JSON patch implementation
    patches = []
    
    for key in request.new:
        if key not in request.old:
            patches.append({"op": "add", "path": f"/{key}", "value": request.new[key]})
        elif request.old[key] != request.new[key]:
            patches.append({"op": "replace", "path": f"/{key}", "value": request.new[key]})
    
    for key in request.old:
        if key not in request.new:
            patches.append({"op": "remove", "path": f"/{key}"})
    
    encoded = json.dumps(patches).encode()
    original_size = len(json.dumps(request.new).encode())
    delta_size = len(encoded)
    
    return {
        "delta": patches,
        "size": delta_size,
        "original_size": original_size,
        "compression_ratio": f"{(1 - delta_size/original_size) * 100:.1f}%"
    }

# Vector Embeddings
@router.post("/embeddings/generate")
async def generate_embeddings(request: EmbeddingRequest):
    """Generate mock embeddings for texts"""
    embeddings = []
    
    for text in request.texts:
        # Simple hash-based embedding for testing
        hash_val = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        
        # Generate deterministic 384-dim embedding
        embedding = []
        for i in range(384):
            val = math.sin(hash_val + i) * 0.5 + 0.5
            embedding.append(val)
        
        embeddings.append(embedding)
    
    return {"embeddings": embeddings, "provider": request.provider, "dimension": 384}

@router.post("/embeddings/search")
async def search_embeddings(request: SearchRequest):
    """Search similar embeddings"""
    # Generate query embedding
    hash_val = int(hashlib.md5(request.query.encode()).hexdigest()[:8], 16)
    query_embedding = [math.sin(hash_val + i) * 0.5 + 0.5 for i in range(384)]
    
    # Calculate similarities
    results = []
    for idx, embedding in enumerate(request.embeddings):
        # Cosine similarity
        dot_product = sum(a * b for a, b in zip(query_embedding, embedding))
        mag1 = math.sqrt(sum(a * a for a in query_embedding))
        mag2 = math.sqrt(sum(b * b for b in embedding))
        similarity = dot_product / (mag1 * mag2) if mag1 and mag2 else 0
        
        results.append({"index": idx, "score": similarity})
    
    # Sort by similarity
    results.sort(key=lambda x: x["score"], reverse=True)
    
    return {"results": results[:request.top_k]}

# Time Travel
@router.post("/time-travel/resource")
async def create_time_resource(request: TimeResourceRequest):
    """Create versioned resource"""
    if request.resource_id not in time_travel_storage:
        time_travel_storage[request.resource_id] = []
    
    time_travel_storage[request.resource_id].append({
        "data": request.data,
        "timestamp": request.timestamp
    })
    
    return {"success": True, "versions": len(time_travel_storage[request.resource_id])}

@router.get("/time-travel/as-of/{resource_id}")
async def get_resource_as_of(
    resource_id: str,
    timestamp: str = Query(..., description="ISO format timestamp")
):
    """Get resource state at specific time"""
    if resource_id not in time_travel_storage:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    versions = time_travel_storage[resource_id]
    
    # Find the latest version before timestamp
    for version in reversed(versions):
        if version["timestamp"] <= timestamp:
            return {"resource_id": resource_id, "timestamp": timestamp, "data": version["data"]}
    
    raise HTTPException(status_code=404, detail="No version found before timestamp")

@router.get("/time-travel/between/{resource_id}")
async def get_resource_between(
    resource_id: str,
    start: str = Query(..., description="Start timestamp"),
    end: str = Query(..., description="End timestamp")
):
    """Get all versions between timestamps"""
    if resource_id not in time_travel_storage:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    versions = time_travel_storage[resource_id]
    
    # Filter versions in range
    result_versions = [
        v for v in versions
        if start <= v["timestamp"] <= end
    ]
    
    return {"resource_id": resource_id, "start": start, "end": end, "versions": result_versions}

# Smart Cache
@router.post("/cache/set")
async def set_cache(request: CacheSetRequest):
    """Set cache value"""
    cache_storage[request.key] = {
        "value": request.value,
        "ttl": request.ttl,
        "created": datetime.now().isoformat()
    }
    cache_stats["sets"] += 1
    return {"success": True}

@router.get("/cache/get/{key}")
async def get_cache(key: str):
    """Get cache value"""
    if key in cache_storage:
        cache_stats["hits"] += 1
        return cache_storage[key]["value"]
    else:
        cache_stats["misses"] += 1
        raise HTTPException(status_code=404, detail="Key not found")

@router.get("/cache/stats")
async def get_cache_stats():
    """Get cache statistics"""
    total = cache_stats["hits"] + cache_stats["misses"]
    hit_rate = cache_stats["hits"] / total if total > 0 else 0
    
    return {
        "hits": cache_stats["hits"],
        "misses": cache_stats["misses"],
        "sets": cache_stats["sets"],
        "total_operations": total,
        "hit_rate": f"{hit_rate * 100:.1f}%"
    }

# Unfoldable Documents
@router.post("/documents/fold")
async def fold_document(request: DocumentFoldRequest):
    """Fold document to specified level"""
    def fold_recursive(obj, level):
        if level == "collapsed" and isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                if key == "@unfoldable" and isinstance(value, dict):
                    result[key] = {}
                    for k, v in value.items():
                        if isinstance(v, dict) and "summary" in v:
                            result[key][k] = {"summary": v["summary"]}
                        else:
                            result[key][k] = v
                else:
                    result[key] = value
            return result
        return obj
    
    folded = fold_recursive(request.document, request.level)
    return folded

@router.post("/documents/unfold")
async def unfold_document(request: DocumentUnfoldRequest):
    """Unfold specific path in document"""
    # Simple implementation - in real system would fetch from storage
    return {
        "document": request.document,
        "unfolded_path": request.path,
        "status": "unfolded"
    }

# Metadata Frames
@router.post("/metadata/parse")
async def parse_metadata(request: MetadataParseRequest):
    """Parse metadata frames from markdown"""
    import re
    
    pattern = r'```@metadata:(\w+)\s+(\w+)\n(.*?)\n```'
    frames = []
    
    for match in re.finditer(pattern, request.content, re.DOTALL):
        frames.append({
            "type": match.group(1),
            "format": match.group(2),
            "content": match.group(3),
            "position": {"start": match.start(), "end": match.end()}
        })
    
    # Remove frames from content
    cleaned_content = re.sub(pattern, "", request.content, flags=re.DOTALL).strip()
    
    return {
        "frames": frames,
        "cleaned_content": cleaned_content,
        "frame_count": len(frames)
    }

# Traced endpoint for Jaeger
@router.get("/traced-endpoint")
async def traced_endpoint():
    """Endpoint that generates traces"""
    # In real implementation, this would use OpenTelemetry
    return {"message": "This request is being traced", "timestamp": datetime.now().isoformat()}

# Audit Logging
@router.post("/audit/log")
async def create_audit_log(request: AuditLogRequest):
    """Create audit log entry"""
    log_entry = {
        "id": len(audit_logs) + 1,
        "action": request.action,
        "resource": request.resource,
        "user_id": request.user_id,
        "details": request.details,
        "timestamp": request.timestamp
    }
    
    audit_logs.append(log_entry)
    return {"success": True, "log_id": log_entry["id"]}

@router.get("/audit/logs")
async def get_audit_logs(
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = Query(100, le=1000)
):
    """Query audit logs"""
    filtered_logs = audit_logs
    
    if action:
        filtered_logs = [l for l in filtered_logs if l["action"] == action]
    
    if user_id:
        filtered_logs = [l for l in filtered_logs if l["user_id"] == user_id]
    
    # Sort by timestamp descending
    filtered_logs.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return {"logs": filtered_logs[:limit], "total": len(filtered_logs)}