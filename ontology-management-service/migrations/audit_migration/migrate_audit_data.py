#!/usr/bin/env python3
"""
Audit Data Migration Script
OMS 모놀리스에서 audit-service로 데이터 벌크 마이그레이션
"""
import asyncio
import os
import sys
import asyncpg
import httpx
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import argparse
import logging
from contextlib import asynccontextmanager

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('audit_migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class MigrationConfig:
    """마이그레이션 설정"""
    # 소스 데이터베이스 (OMS 모놀리스)
    source_db_url: str
    
    # 대상 audit-service
    audit_service_url: str
    audit_service_api_key: str
    
    # 마이그레이션 옵션
    batch_size: int = 1000
    max_concurrent_batches: int = 5
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    dry_run: bool = False
    
    # 재시도 설정
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # 검증 옵션
    verify_migration: bool = True
    delete_after_migration: bool = False


@dataclass
class MigrationStats:
    """마이그레이션 통계"""
    total_records: int = 0
    migrated_records: int = 0
    failed_records: int = 0
    skipped_records: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def duration(self) -> float:
        """마이그레이션 소요 시간 (초)"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def success_rate(self) -> float:
        """성공률 계산"""
        if self.total_records == 0:
            return 0.0
        return (self.migrated_records / self.total_records) * 100


class AuditDataMigrator:
    """Audit 데이터 마이그레이션 클래스"""
    
    def __init__(self, config: MigrationConfig):
        self.config = config
        self.stats = MigrationStats()
        self.failed_records: List[Dict[str, Any]] = []
        
        # HTTP 클라이언트 설정
        self.http_client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self):
        """Async context manager 진입"""
        # HTTP 클라이언트 초기화
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.audit_service_api_key}"
        }
        
        self.http_client = httpx.AsyncClient(
            base_url=self.config.audit_service_url,
            headers=headers,
            timeout=httpx.Timeout(60.0),
            limits=httpx.Limits(max_connections=20)
        )
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager 종료"""
        if self.http_client:
            await self.http_client.aclose()
    
    async def connect_source_db(self) -> asyncpg.Connection:
        """소스 데이터베이스 연결"""
        try:
            conn = await asyncpg.connect(self.config.source_db_url)
            logger.info("Connected to source database")
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to source database: {e}")
            raise
    
    async def get_total_count(self, conn: asyncpg.Connection) -> int:
        """마이그레이션 대상 레코드 총 개수 조회"""
        query = """
        SELECT COUNT(*) 
        FROM audit_events_v1 
        WHERE 1=1
        """
        params = []
        
        if self.config.start_date:
            query += " AND created_at >= $" + str(len(params) + 1)
            params.append(self.config.start_date)
        
        if self.config.end_date:
            query += " AND created_at <= $" + str(len(params) + 1)
            params.append(self.config.end_date)
        
        result = await conn.fetchval(query, *params)
        return result or 0
    
    async def fetch_batch(
        self, 
        conn: asyncpg.Connection, 
        offset: int, 
        limit: int
    ) -> List[Dict[str, Any]]:
        """배치 단위로 데이터 조회"""
        query = """
        SELECT 
            id,
            event_id,
            event_type,
            event_category,
            severity,
            user_id,
            username,
            service_account,
            target_type,
            target_id,
            operation,
            branch,
            commit_id,
            terminus_db,
            request_id,
            session_id,
            ip_address,
            user_agent,
            before_state,
            after_state,
            changes,
            metadata,
            created_at,
            updated_at
        FROM audit_events_v1 
        WHERE 1=1
        """
        params = []
        
        if self.config.start_date:
            query += " AND created_at >= $" + str(len(params) + 1)
            params.append(self.config.start_date)
        
        if self.config.end_date:
            query += " AND created_at <= $" + str(len(params) + 1)
            params.append(self.config.end_date)
        
        query += f" ORDER BY created_at ASC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        params.extend([limit, offset])
        
        rows = await conn.fetch(query, *params)
        
        # 결과를 딕셔너리로 변환
        return [dict(row) for row in rows]
    
    def transform_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """레코드를 audit-service 형식으로 변환"""
        # 기본 필드 매핑
        transformed = {
            "event_type": record.get("event_type", "UNKNOWN"),
            "event_category": record.get("event_category", "GENERAL"),
            "severity": record.get("severity", "INFO"),
            "user_id": record.get("user_id", "unknown"),
            "username": record.get("username", "unknown"),
            "target_type": record.get("target_type", "UNKNOWN"),
            "target_id": record.get("target_id", "unknown"),
            "operation": record.get("operation", "UNKNOWN"),
            "timestamp": record.get("created_at", datetime.utcnow()).isoformat(),
        }
        
        # 선택적 필드들
        if record.get("service_account"):
            transformed["service_account"] = record["service_account"]
        if record.get("branch"):
            transformed["branch"] = record["branch"]
        if record.get("commit_id"):
            transformed["commit_id"] = record["commit_id"]
        if record.get("terminus_db"):
            transformed["terminus_db"] = record["terminus_db"]
        if record.get("request_id"):
            transformed["request_id"] = record["request_id"]
        if record.get("session_id"):
            transformed["session_id"] = record["session_id"]
        if record.get("ip_address"):
            transformed["ip_address"] = record["ip_address"]
        if record.get("user_agent"):
            transformed["user_agent"] = record["user_agent"]
        
        # JSON 필드들
        if record.get("before_state"):
            transformed["before_state"] = record["before_state"]
        if record.get("after_state"):
            transformed["after_state"] = record["after_state"]
        if record.get("changes"):
            transformed["changes"] = record["changes"]
        
        # 메타데이터 통합
        metadata = record.get("metadata", {}) or {}
        metadata.update({
            "migrated_from": "oms-monolith",
            "migration_date": datetime.utcnow().isoformat(),
            "original_id": record.get("id"),
            "original_event_id": record.get("event_id")
        })
        transformed["metadata"] = metadata
        
        return transformed
    
    async def send_batch_to_audit_service(
        self, 
        batch: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """배치를 audit-service로 전송"""
        if not self.http_client:
            raise RuntimeError("HTTP client not initialized")
        
        # 배치 페이로드 구성
        payload = {
            "events": batch,
            "batch_id": f"migration_batch_{datetime.utcnow().isoformat()}",
            "source_service": "oms-monolith-migration"
        }
        
        for attempt in range(self.config.max_retries):
            try:
                if self.config.dry_run:
                    # Dry run 모드에서는 실제 전송하지 않음
                    return {
                        "success": True,
                        "processed_count": len(batch),
                        "failed_count": 0,
                        "batch_id": payload["batch_id"]
                    }
                
                response = await self.http_client.post(
                    "/api/v2/events/batch",
                    json=payload
                )
                response.raise_for_status()
                return response.json()
                
            except Exception as e:
                logger.warning(f"Batch send attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                else:
                    raise
    
    async def migrate_batch(
        self, 
        conn: asyncpg.Connection, 
        offset: int
    ) -> Dict[str, Any]:
        """단일 배치 마이그레이션"""
        try:
            # 배치 데이터 조회
            records = await self.fetch_batch(conn, offset, self.config.batch_size)
            
            if not records:
                return {"processed": 0, "failed": 0}
            
            # 데이터 변환
            transformed_records = [self.transform_record(record) for record in records]
            
            # audit-service로 전송
            result = await self.send_batch_to_audit_service(transformed_records)
            
            processed_count = result.get("processed_count", 0)
            failed_count = result.get("failed_count", 0)
            
            # 실패한 레코드 기록
            if failed_count > 0:
                self.failed_records.extend(records[-failed_count:])
            
            logger.info(f"Batch {offset//self.config.batch_size + 1}: "
                       f"processed={processed_count}, failed={failed_count}")
            
            return {"processed": processed_count, "failed": failed_count}
            
        except Exception as e:
            logger.error(f"Batch migration failed at offset {offset}: {e}")
            return {"processed": 0, "failed": len(records) if 'records' in locals() else self.config.batch_size}
    
    async def run_migration(self) -> MigrationStats:
        """마이그레이션 실행"""
        self.stats.start_time = datetime.utcnow()
        
        try:
            conn = await self.connect_source_db()
            
            try:
                # 총 레코드 수 조회
                self.stats.total_records = await self.get_total_count(conn)
                logger.info(f"Total records to migrate: {self.stats.total_records}")
                
                if self.stats.total_records == 0:
                    logger.info("No records to migrate")
                    return self.stats
                
                # 배치 단위로 마이그레이션
                semaphore = asyncio.Semaphore(self.config.max_concurrent_batches)
                tasks = []
                
                for offset in range(0, self.stats.total_records, self.config.batch_size):
                    task = self._migrate_batch_with_semaphore(semaphore, conn, offset)
                    tasks.append(task)
                
                # 모든 배치 처리 대기
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 결과 집계
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Batch task failed: {result}")
                        self.stats.failed_records += self.config.batch_size
                    else:
                        self.stats.migrated_records += result["processed"]
                        self.stats.failed_records += result["failed"]
                
                self.stats.skipped_records = (
                    self.stats.total_records - 
                    self.stats.migrated_records - 
                    self.stats.failed_records
                )
                
            finally:
                await conn.close()
        
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise
        
        finally:
            self.stats.end_time = datetime.utcnow()
        
        return self.stats
    
    async def _migrate_batch_with_semaphore(
        self, 
        semaphore: asyncio.Semaphore, 
        conn: asyncpg.Connection, 
        offset: int
    ):
        """세마포어를 사용한 배치 마이그레이션"""
        async with semaphore:
            return await self.migrate_batch(conn, offset)
    
    async def verify_migration(self, conn: asyncpg.Connection) -> bool:
        """마이그레이션 검증"""
        if not self.config.verify_migration:
            return True
        
        logger.info("Verifying migration...")
        
        try:
            # 소스에서 샘플 레코드 조회
            sample_records = await conn.fetch("""
                SELECT event_id, user_id, target_type, target_id, created_at
                FROM audit_events_v1 
                ORDER BY created_at DESC 
                LIMIT 10
            """)
            
            # audit-service에서 해당 레코드들 확인
            for record in sample_records:
                if not await self._verify_record_exists(record):
                    logger.warning(f"Record verification failed for event_id: {record['event_id']}")
                    return False
            
            logger.info("Migration verification passed")
            return True
            
        except Exception as e:
            logger.error(f"Migration verification failed: {e}")
            return False
    
    async def _verify_record_exists(self, record: Dict[str, Any]) -> bool:
        """개별 레코드 존재 확인"""
        if not self.http_client:
            return False
        
        try:
            response = await self.http_client.get(
                "/api/v2/events/query",
                params={
                    "user_id": record["user_id"],
                    "target_type": record["target_type"],
                    "target_id": record["target_id"],
                    "limit": 1
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("total", 0) > 0
            
            return False
            
        except Exception:
            return False
    
    def save_failed_records(self):
        """실패한 레코드를 파일로 저장"""
        if not self.failed_records:
            return
        
        filename = f"failed_audit_records_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.failed_records, f, indent=2, default=str)
        
        logger.info(f"Failed records saved to: {filename}")
    
    def print_summary(self):
        """마이그레이션 결과 요약 출력"""
        logger.info("="*60)
        logger.info("AUDIT MIGRATION SUMMARY")
        logger.info("="*60)
        logger.info(f"Total records: {self.stats.total_records}")
        logger.info(f"Migrated: {self.stats.migrated_records}")
        logger.info(f"Failed: {self.stats.failed_records}")
        logger.info(f"Skipped: {self.stats.skipped_records}")
        logger.info(f"Success rate: {self.stats.success_rate():.2f}%")
        logger.info(f"Duration: {self.stats.duration():.2f} seconds")
        logger.info(f"Records per second: {self.stats.migrated_records / max(self.stats.duration(), 1):.2f}")
        
        if self.failed_records:
            logger.warning(f"Failed records count: {len(self.failed_records)}")


async def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="Audit Data Migration to audit-service")
    parser.add_argument("--source-db", required=True, help="Source database URL")
    parser.add_argument("--audit-service-url", required=True, help="Audit service URL")
    parser.add_argument("--api-key", required=True, help="Audit service API key")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size")
    parser.add_argument("--max-concurrent", type=int, default=5, help="Max concurrent batches")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--no-verify", action="store_true", help="Skip verification")
    
    args = parser.parse_args()
    
    # 날짜 파싱
    start_date = None
    end_date = None
    
    if args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    
    # 설정 생성
    config = MigrationConfig(
        source_db_url=args.source_db,
        audit_service_url=args.audit_service_url,
        audit_service_api_key=args.api_key,
        batch_size=args.batch_size,
        max_concurrent_batches=args.max_concurrent,
        start_date=start_date,
        end_date=end_date,
        dry_run=args.dry_run,
        verify_migration=not args.no_verify
    )
    
    # 마이그레이션 실행
    async with AuditDataMigrator(config) as migrator:
        try:
            stats = await migrator.run_migration()
            migrator.print_summary()
            migrator.save_failed_records()
            
            # 검증 실행
            if config.verify_migration and not config.dry_run:
                conn = await migrator.connect_source_db()
                try:
                    verification_passed = await migrator.verify_migration(conn)
                    if not verification_passed:
                        logger.error("Migration verification failed!")
                        sys.exit(1)
                finally:
                    await conn.close()
            
            if stats.failed_records > 0:
                logger.warning("Migration completed with failures")
                sys.exit(1)
            else:
                logger.info("Migration completed successfully")
                
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())