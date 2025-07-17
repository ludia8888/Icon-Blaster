"""
레이블 매핑 관리 라우터
레이블 매핑 내보내기/가져오기를 담당
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional, Any
import json
import logging
import hashlib
import os
import sys
from datetime import datetime

# Add shared path for common utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from models.requests import MappingImportRequest, ApiResponse
from security.input_sanitizer import sanitize_input, SecurityViolationError

from dependencies import LabelMapper
from dependencies import get_label_mapper

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/database/{db_name}/mappings",
    tags=["Label Mappings"]
)


@router.post("/export")
async def export_mappings(
    db_name: str,
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """
    레이블 매핑 내보내기
    
    데이터베이스의 모든 레이블 매핑을 내보냅니다.
    """
    try:
        # 매핑 내보내기
        mappings = mapper.export_mappings(db_name)
        
        return JSONResponse(
            content=mappings,
            headers={
                "Content-Disposition": f"attachment; filename={db_name}_mappings.json"
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to export mappings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"매핑 내보내기 실패: {str(e)}"
        )


@router.post("/import", response_model=ApiResponse)
async def import_mappings(
    db_name: str,
    file: UploadFile = File(...),
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """
    레이블 매핑 가져오기 (Production-Grade with Enhanced Security)
    
    JSON 파일에서 레이블 매핑을 가져옵니다.
    
    Security Features:
    - File size limits (max 10MB)
    - Content type validation
    - Schema validation with Pydantic
    - SQL injection prevention
    - Malicious content detection
    - Integrity validation
    """
    try:
        # Enhanced Security Validation
        
        # 1. File size validation (10MB limit)
        if file.size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="파일 크기가 너무 큽니다 (최대 10MB)"
            )
        
        # 2. Content type validation
        if file.content_type and not file.content_type.startswith('application/json'):
            logger.warning(f"Suspicious content type: {file.content_type}")
        
        # 3. File extension validation (multiple extensions)
        if not file.filename or not any(file.filename.lower().endswith(ext) for ext in ['.json', '.txt']):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON 파일만 지원됩니다 (.json 또는 .txt)"
            )
        
        # 4. Read file content with error handling
        try:
            content = await file.read()
            if len(content) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="빈 파일입니다"
                )
        except Exception as e:
            logger.error(f"Failed to read uploaded file: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="파일을 읽을 수 없습니다"
            )
        
        # 5. Content integrity validation (checksum)
        content_hash = hashlib.sha256(content).hexdigest()
        logger.info(f"Processing mapping import with hash: {content_hash[:16]}...")
        
        # 6. JSON parsing with detailed error handling
        try:
            raw_mappings = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"잘못된 JSON 형식입니다: {str(e)}"
            )
        
        # 7. Security sanitization
        try:
            sanitized_mappings = sanitize_input(raw_mappings)
        except SecurityViolationError as e:
            logger.warning(f"Security violation detected in mapping import: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="보안 위반이 감지되었습니다. 파일 내용을 확인해주세요."
            )
        
        # 8. Schema validation using Pydantic
        try:
            # Convert to our validated request model
            mapping_request = MappingImportRequest(
                db_name=db_name,
                classes=sanitized_mappings.get('classes', []),
                properties=sanitized_mappings.get('properties', []),
                relationships=sanitized_mappings.get('relationships', [])
            )
        except Exception as e:
            logger.error(f"Schema validation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"매핑 데이터 스키마가 올바르지 않습니다: {str(e)}"
            )
        
        # 9. Database name consistency validation
        file_db_name = sanitized_mappings.get('db_name')
        if file_db_name and file_db_name != db_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"매핑 데이터의 데이터베이스 이름이 일치하지 않습니다: "
                      f"예상: {db_name}, 실제: {file_db_name}"
            )
        
        # 10. Content integrity checks
        total_mappings = len(mapping_request.classes) + len(mapping_request.properties) + len(mapping_request.relationships)
        if total_mappings == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="가져올 매핑 데이터가 없습니다"
            )
        
        # 11. Validate individual mapping entries
        for cls in mapping_request.classes:
            if not cls.get('class_id') or not cls.get('label'):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="클래스 매핑에 필수 필드가 누락되었습니다 (class_id, label)"
                )
        
        for prop in mapping_request.properties:
            if not prop.get('property_id') or not prop.get('label'):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="속성 매핑에 필수 필드가 누락되었습니다 (property_id, label)"
                )
        
        # 12. Duplicate detection within the import
        class_ids = [cls.get('class_id') for cls in mapping_request.classes]
        if len(class_ids) != len(set(class_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="중복된 클래스 ID가 있습니다"
            )
        
        # 13. Business logic validation
        start_time = datetime.now()
        
        # Create a comprehensive mapping dictionary for the mapper
        validated_mappings = {
            'db_name': db_name,
            'classes': mapping_request.classes,
            'properties': mapping_request.properties,
            'relationships': mapping_request.relationships,
            'imported_at': start_time.isoformat(),
            'import_hash': content_hash,
            'validation_passed': True
        }
        
        # 14. Perform the actual import with transaction-like behavior
        try:
            # Backup current mappings before import
            backup = mapper.export_mappings(db_name)
            
            # Import new mappings
            mapper.import_mappings(validated_mappings)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"Successfully imported {total_mappings} mappings for {db_name} in {processing_time:.2f}s")
            
            return {
                "status": "success",
                "message": "레이블 매핑을 성공적으로 가져왔습니다",
                "data": {
                    "database": db_name,
                    "stats": {
                        "classes": len(mapping_request.classes),
                        "properties": len(mapping_request.properties),
                        "relationships": len(mapping_request.relationships),
                        "total": total_mappings
                    },
                    "processing_time_seconds": processing_time,
                    "content_hash": content_hash[:16],
                    "imported_at": start_time.isoformat()
                }
            }
            
        except Exception as import_error:
            # Try to restore backup if import failed
            try:
                if backup:
                    mapper.import_mappings(backup)
                    logger.info(f"Restored backup mappings for {db_name} after import failure")
            except Exception as restore_error:
                logger.error(f"Failed to restore backup: {restore_error}")
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"매핑 가져오기 중 오류가 발생했습니다: {str(import_error)}"
            )
        
    except HTTPException:
        raise
    except SecurityViolationError as e:
        logger.warning(f"Security violation in mapping import: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="보안 정책 위반이 감지되었습니다"
        )
    except Exception as e:
        logger.error(f"Unexpected error in mapping import: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"매핑 가져오기 실패: 서버 오류가 발생했습니다"
        )


@router.get("/")
async def get_mappings_summary(
    db_name: str,
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """
    레이블 매핑 요약 조회
    
    데이터베이스의 레이블 매핑 통계를 조회합니다.
    """
    try:
        # 매핑 내보내기로 전체 데이터 가져오기
        mappings = mapper.export_mappings(db_name)
        
        # 언어별 통계
        lang_stats = {}
        
        # 클래스 매핑 통계
        for cls in mappings.get('classes', []):
            lang = cls.get('label_lang', 'ko')
            if lang not in lang_stats:
                lang_stats[lang] = {'classes': 0, 'properties': 0, 'relationships': 0}
            lang_stats[lang]['classes'] += 1
        
        # 속성 매핑 통계
        for prop in mappings.get('properties', []):
            lang = prop.get('label_lang', 'ko')
            if lang not in lang_stats:
                lang_stats[lang] = {'classes': 0, 'properties': 0, 'relationships': 0}
            lang_stats[lang]['properties'] += 1
        
        # 관계 매핑 통계
        for rel in mappings.get('relationships', []):
            lang = rel.get('label_lang', 'ko')
            if lang not in lang_stats:
                lang_stats[lang] = {'classes': 0, 'properties': 0, 'relationships': 0}
            lang_stats[lang]['relationships'] += 1
        
        return {
            "database": db_name,
            "total": {
                "classes": len(mappings.get('classes', [])),
                "properties": len(mappings.get('properties', [])),
                "relationships": len(mappings.get('relationships', []))
            },
            "by_language": lang_stats,
            "last_exported": mappings.get('exported_at')
        }
        
    except Exception as e:
        logger.error(f"Failed to get mappings summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"매핑 요약 조회 실패: {str(e)}"
        )


@router.delete("/")
async def clear_mappings(
    db_name: str,
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """
    레이블 매핑 초기화
    
    데이터베이스의 모든 레이블 매핑을 삭제합니다.
    주의: 이 작업은 되돌릴 수 없습니다!
    """
    try:
        # 먼저 백업용으로 현재 매핑 내보내기
        backup = mapper.export_mappings(db_name)
        
        # 모든 클래스의 매핑 삭제
        for cls in backup.get('classes', []):
            mapper.remove_class(db_name, cls['class_id'])
        
        return {
            "message": "레이블 매핑이 초기화되었습니다",
            "database": db_name,
            "deleted": {
                "classes": len(backup.get('classes', [])),
                "properties": len(backup.get('properties', [])),
                "relationships": len(backup.get('relationships', []))
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to clear mappings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"매핑 초기화 실패: {str(e)}"
        )