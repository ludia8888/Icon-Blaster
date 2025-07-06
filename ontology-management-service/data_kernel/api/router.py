from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path

from data_kernel.service.terminus_service import TerminusService
from data_kernel.api.deps import get_terminus_service, get_commit_meta, CommitMeta

router = APIRouter(prefix="/db/{db_name}", tags=["data-kernel"])


@router.get("/health")
async def health_check(
    svc: TerminusService = Depends(get_terminus_service)
):
    """Check health of TerminusDB connection."""
    try:
        health = await svc.health_check()
        return {"status": "healthy", "terminus_db": health}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


@router.get("/doc/{doc_id}")
async def read_document(
    db_name: str = Path(..., description="Database name"),
    doc_id: str = Path(..., description="Document ID"),
    branch: str = Query("main", description="Branch name"),
    revision: Optional[str] = Query(None, description="Specific revision/commit hash"),
    svc: TerminusService = Depends(get_terminus_service)
):
    """Retrieve a document from TerminusDB."""
    try:
        document = await svc.get_document(db_name, doc_id, branch, revision)
        if document is None:
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
        return document
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/doc")
async def create_document(
    db_name: str = Path(..., description="Database name"),
    payload: Dict[str, Any] = ...,
    svc: TerminusService = Depends(get_terminus_service),
    meta: CommitMeta = Depends(get_commit_meta)
):
    """Create a new document in TerminusDB."""
    try:
        # Add trace ID to commit message if available
        commit_msg = meta.commit_msg
        if meta.trace_id:
            commit_msg = f"{commit_msg} [trace:{meta.trace_id}]"
        
        result = await svc.insert_document(
            db_name, 
            payload, 
            commit_msg=commit_msg,
            author=meta.author
        )
        return {"status": "created", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/doc/{doc_id}")
async def update_document(
    db_name: str = Path(..., description="Database name"),
    doc_id: str = Path(..., description="Document ID"),
    updates: Dict[str, Any] = ...,
    svc: TerminusService = Depends(get_terminus_service),
    meta: CommitMeta = Depends(get_commit_meta)
):
    """Update an existing document in TerminusDB."""
    try:
        # Add trace ID to commit message if available
        commit_msg = meta.commit_msg
        if meta.trace_id:
            commit_msg = f"{commit_msg} [trace:{meta.trace_id}]"
        
        result = await svc.update_document(
            db_name,
            doc_id,
            updates,
            commit_msg=commit_msg,
            author=meta.author
        )
        return {"status": "updated", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/doc/{doc_id}")
async def delete_document(
    db_name: str = Path(..., description="Database name"),
    doc_id: str = Path(..., description="Document ID"),
    svc: TerminusService = Depends(get_terminus_service),
    meta: CommitMeta = Depends(get_commit_meta)
):
    """Delete a document from TerminusDB."""
    try:
        # Add trace ID to commit message if available
        commit_msg = f"Delete document {doc_id}"
        if meta.trace_id:
            commit_msg = f"{commit_msg} [trace:{meta.trace_id}]"
        
        result = await svc.delete_document(
            db_name,
            doc_id,
            commit_msg=commit_msg,
            author=meta.author
        )
        return {"status": "deleted", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/woql")
async def execute_query(
    db_name: str = Path(..., description="Database name"),
    query: Dict[str, Any] = ...,
    commit: bool = Query(False, description="Whether this query modifies data"),
    svc: TerminusService = Depends(get_terminus_service),
    meta: CommitMeta = Depends(get_commit_meta)
):
    """Execute a WOQL query against TerminusDB."""
    try:
        # Only pass commit message if this is a write query
        commit_msg = None
        if commit:
            commit_msg = meta.commit_msg
            if meta.trace_id:
                commit_msg = f"{commit_msg} [trace:{meta.trace_id}]"
        
        result = await svc.query(db_name, query, commit_msg=commit_msg)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema")
async def get_schema(
    db_name: str = Path(..., description="Database name"),
    svc: TerminusService = Depends(get_terminus_service)
):
    """Get the schema for a database."""
    try:
        schema = await svc.get_schema(db_name)
        return {"status": "success", "schema": schema}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/schema")
async def update_schema(
    db_name: str = Path(..., description="Database name"),
    schema: Dict[str, Any] = ...,
    svc: TerminusService = Depends(get_terminus_service),
    meta: CommitMeta = Depends(get_commit_meta)
):
    """Update the schema for a database."""
    try:
        # Add trace ID to commit message if available
        commit_msg = "Update schema"
        if meta.trace_id:
            commit_msg = f"{commit_msg} [trace:{meta.trace_id}]"
        
        result = await svc.update_schema(
            db_name,
            schema,
            commit_msg=commit_msg,
            author=meta.author
        )
        return {"status": "updated", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/branch/{branch_name}")
async def switch_branch(
    db_name: str = Path(..., description="Database name"),
    branch_name: str = Path(..., description="Branch name to switch to"),
    svc: TerminusService = Depends(get_terminus_service)
):
    """Switch to a different branch in the database."""
    try:
        success = await svc.branch_switch(db_name, branch_name)
        if success:
            return {"status": "success", "branch": branch_name}
        else:
            raise HTTPException(status_code=500, detail="Failed to switch branch")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))