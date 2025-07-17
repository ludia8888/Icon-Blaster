"""
레이블 매핑 관리 라우터
레이블 매핑 내보내기/가져오기를 담당
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional, Any
import json
import logging

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


@router.post("/import")
async def import_mappings(
    db_name: str,
    file: UploadFile = File(...),
    mapper: LabelMapper = Depends(get_label_mapper)
):
    """
    레이블 매핑 가져오기
    
    JSON 파일에서 레이블 매핑을 가져옵니다.
    """
    try:
        # 파일 확장자 확인
        if not file.filename.endswith('.json'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON 파일만 지원됩니다"
            )
        
        # 파일 내용 읽기
        content = await file.read()
        
        try:
            mappings = json.loads(content)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="잘못된 JSON 형식입니다"
            )
        
        # 데이터베이스 이름 확인
        if mappings.get('db_name') != db_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"매핑 데이터의 데이터베이스 이름이 일치하지 않습니다: "
                      f"예상: {db_name}, 실제: {mappings.get('db_name')}"
            )
        
        # 매핑 가져오기
        mapper.import_mappings(mappings)
        
        return {
            "message": "레이블 매핑을 성공적으로 가져왔습니다",
            "database": db_name,
            "stats": {
                "classes": len(mappings.get('classes', [])),
                "properties": len(mappings.get('properties', [])),
                "relationships": len(mappings.get('relationships', []))
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import mappings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"매핑 가져오기 실패: {str(e)}"
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