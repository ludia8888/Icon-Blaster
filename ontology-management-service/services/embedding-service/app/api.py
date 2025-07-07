"""
FastAPI application for Embedding Service
"""
import os
import logging
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.embeddings.service import VectorEmbeddingService
from app.embeddings.providers import EmbeddingServiceProvider
from app.startup_optimizer import EmbeddingServiceOptimizer, profile_startup

logger = logging.getLogger(__name__)


# Request/Response models
class EmbeddingRequest(BaseModel):
    text: str
    model_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BatchEmbeddingRequest(BaseModel):
    texts: List[str]
    model_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SimilarityRequest(BaseModel):
    text1: str
    text2: str
    metric: str = "cosine"


class SearchRequest(BaseModel):
    query: str
    collection: str = "default"
    top_k: int = Field(default=10, ge=1, le=100)
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    filters: Optional[Dict[str, Any]] = None


class EmbeddingResponse(BaseModel):
    embedding: List[float]
    dimensions: int
    model_used: str
    processing_time_ms: float


class SimilarityResponse(BaseModel):
    similarity: float
    metric_used: str


class SearchResult(BaseModel):
    id: str
    similarity: float
    metadata: Dict[str, Any]


class SearchResponse(BaseModel):
    results: List[SearchResult]
    total_found: int
    search_time_ms: float


# Application lifespan
@asynccontextmanager
@profile_startup
async def lifespan(app: FastAPI):
    """Manage application lifecycle with optimized startup"""
    logger.info("Starting Embedding Service with optimization...")
    
    # Initialize embedding service
    provider = EmbeddingServiceProvider()
    service = VectorEmbeddingService()
    
    # Use startup optimizer
    optimizer = EmbeddingServiceOptimizer(service)
    startup_stats = await optimizer.optimize_startup()
    
    # Complete provider initialization
    await provider.initialize()
    app.state.provider = provider
    app.state.service = service
    
    logger.info(f"Embedding Service started - {startup_stats}")
    
    yield
    
    logger.info("Shutting down Embedding Service...")
    await provider.shutdown()
    logger.info("Embedding Service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Embedding Service",
    description="Vector embedding and similarity service",
    version="1.0.0",
    lifespan=lifespan
)

# Add OpenTelemetry instrumentation
FastAPIInstrumentor.instrument_app(app)


# Dependencies
async def get_embedding_service(request) -> VectorEmbeddingService:
    """Get embedding service from app state"""
    return await request.app.state.provider.provide()


# Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "embedding-service",
        "version": "1.0.0",
        "model_loaded": True
    }


@app.post("/api/v1/embedding", response_model=EmbeddingResponse)
async def generate_embedding(
    request: EmbeddingRequest,
    service: VectorEmbeddingService = Depends(get_embedding_service)
):
    """Generate embedding for a single text"""
    try:
        import time
        start_time = time.time()
        
        embedding = await service.generate_embedding(
            request.text,
            metadata=request.metadata
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        return EmbeddingResponse(
            embedding=embedding.tolist() if hasattr(embedding, 'tolist') else embedding,
            dimensions=len(embedding),
            model_used=request.model_name or "sentence-transformers/all-MiniLM-L6-v2",
            processing_time_ms=processing_time
        )
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/embeddings/batch", response_model=List[EmbeddingResponse])
async def generate_batch_embeddings(
    request: BatchEmbeddingRequest,
    service: VectorEmbeddingService = Depends(get_embedding_service)
):
    """Generate embeddings for multiple texts"""
    try:
        import time
        start_time = time.time()
        
        embeddings = await service.generate_batch_embeddings(
            request.texts,
            metadata=request.metadata
        )
        
        processing_time = (time.time() - start_time) * 1000
        model_name = request.model_name or "sentence-transformers/all-MiniLM-L6-v2"
        
        responses = []
        for embedding in embeddings:
            responses.append(EmbeddingResponse(
                embedding=embedding.tolist() if hasattr(embedding, 'tolist') else embedding,
                dimensions=len(embedding),
                model_used=model_name,
                processing_time_ms=processing_time / len(embeddings)
            ))
        
        return responses
    except Exception as e:
        logger.error(f"Error generating batch embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/similarity", response_model=SimilarityResponse)
async def calculate_similarity(
    request: SimilarityRequest,
    service: VectorEmbeddingService = Depends(get_embedding_service)
):
    """Calculate similarity between two texts"""
    try:
        # Generate embeddings for both texts
        embedding1 = await service.generate_embedding(request.text1)
        embedding2 = await service.generate_embedding(request.text2)
        
        # Calculate similarity
        similarity = await service.calculate_similarity(
            embedding1,
            embedding2,
            metric=request.metric
        )
        
        return SimilarityResponse(
            similarity=float(similarity),
            metric_used=request.metric
        )
    except Exception as e:
        logger.error(f"Error calculating similarity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/search", response_model=SearchResponse)
async def search_similar(
    request: SearchRequest,
    service: VectorEmbeddingService = Depends(get_embedding_service)
):
    """Search for similar documents"""
    try:
        import time
        start_time = time.time()
        
        # Generate query embedding
        query_embedding = await service.generate_embedding(request.query)
        
        # Search for similar documents
        results = await service.find_similar(
            query_embedding,
            collection=request.collection,
            top_k=request.top_k,
            min_similarity=request.min_similarity,
            filters=request.filters
        )
        
        search_time = (time.time() - start_time) * 1000
        
        # Convert results to response format
        search_results = []
        for result in results:
            search_results.append(SearchResult(
                id=result.get("id", ""),
                similarity=result.get("similarity", 0.0),
                metadata=result.get("metadata", {})
            ))
        
        return SearchResponse(
            results=search_results,
            total_found=len(search_results),
            search_time_ms=search_time
        )
    except Exception as e:
        logger.error(f"Error searching similar documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stats")
async def get_stats(service: VectorEmbeddingService = Depends(get_embedding_service)):
    """Get service statistics"""
    try:
        stats = await service.get_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("EMBEDDING_SERVICE_PORT", "8001"))
    host = os.getenv("EMBEDDING_SERVICE_HOST", "0.0.0.0")
    
    uvicorn.run(
        "api:app",
        host=host,
        port=port,
        reload=os.getenv("ENV", "production") == "development"
    )