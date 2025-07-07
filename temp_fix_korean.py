#!/usr/bin/env python3
"""
Quick fix for Korean text in history.py that causes syntax errors
"""

import re

# Read the file
with open('/Users/isihyeon/Desktop/Arrakis-Project/audit-service/api/routes/history.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace Korean text with English equivalents
replacements = [
    ('스키마 변경 히스토리 목록을 조회합니다 (OMS에서 이관된 기능)', 'Query schema change history list (migrated from OMS)'),
    ('**권한**: `audit:read` 또는 `history:read`', '**Permissions**: `audit:read` or `history:read`'),
    ('**필터링 옵션**:', '**Filtering options**:'),
    ('- 브랜치별 필터링', '- Filter by branch'),
    ('- 리소스 타입별 필터링', '- Filter by resource type'),
    ('- 작성자별 필터링', '- Filter by author'),
    ('- 날짜 범위별 필터링', '- Filter by date range'),
    ('- 작업 타입별 필터링', '- Filter by operation type'),
    ('**페이지네이션**:', '**Pagination**:'),
    ('- cursor 기반 페이지네이션 지원', '- Cursor-based pagination support'),
    ('- limit로 결과 수 제한 (최대 1000)', '- Limit results (max 1000)'),
    ('**정렬**:', '**Sorting**:'),
    ('- timestamp, author, resource_id 등으로 정렬 가능', '- Sort by timestamp, author, resource_id etc.'),
    ('- asc/desc 정렬 순서 지원', '- asc/desc sort order support'),
    ('브랜치 필터', 'Branch filter'),
    ('리소스 타입 필터', 'Resource type filter'),
    ('리소스 ID 필터', 'Resource ID filter'),
    ('작성자 필터', 'Author filter'),
    ('작업 타입 필터', 'Operation type filter'),
    ('시작 날짜 (ISO 8601)', 'Start date (ISO 8601)'),
    ('종료 날짜 (ISO 8601)', 'End date (ISO 8601)'),
    ('상세 변경 내역 포함 여부', 'Include detailed changes'),
    ('영향받은 리소스 포함 여부', 'Include affected resources'),
    ('메타데이터 포함 여부', 'Include metadata'),
    ('결과 제한', 'Result limit'),
    ('페이지네이션 커서', 'Pagination cursor'),
    ('정렬 기준', 'Sort criteria'),
    ('정렬 순서 (asc/desc)', 'Sort order (asc/desc)'),
    ('\"\"\"스키마 변경 히스토리 목록 조회\"\"\"', '"""Query schema change history list"""'),
    ('- 커밋 기본 정보 (해시, 작성자, 메시지 등)', '- Basic commit info (hash, author, message etc.)'),
    ('- 변경 통계 (추가/수정/삭제 개수)', '- Change statistics (add/modify/delete counts)'),
    ('- 상세 변경 내역', '- Detailed changes'),
    ('- 영향받은 리소스들', '- Affected resources'),
    ('- 스키마 스냅샷 (선택적)', '- Schema snapshot (optional)'),
    ('브랜치명', 'Branch name'),
    ('스키마 스냅샷 포함 여부', 'Include schema snapshot'),
    ('\"\"\"커밋 상세 정보 조회\"\"\"', '"""Get commit details"""'),
    ('두 커밋 간의 차이점을 조회합니다.', 'Query differences between two commits.'),
    ('**권한**: `audit:read` 또는 `history:read`', '**Permissions**: `audit:read` or `history:read`'),
    ('비교할 커밋 (기본값: 이전 커밋)', 'Commit to compare with (default: previous commit)'),
    ('출력 형식 (json/text/unified)', 'Output format (json/text/unified)'),
    ('\"\"\"커밋 차이점 조회\"\"\"', '"""Get commit differences"""'),
    ('히스토리 통계 정보를 조회합니다.', 'Query history statistics.'),
    ('그룹화 기준 (hour/day/week/month)', 'Grouping criteria (hour/day/week/month)'),
    ('\"\"\"히스토리 통계 조회\"\"\"', '"""Get history statistics"""'),
    ('히스토리 데이터를 내보냅니다.', 'Export history data.'),
    ('**권한**: `audit:export` 또는 `history:export`', '**Permissions**: `audit:export` or `history:export`'),
    ('**지원 형식**: CSV, JSON, Excel', '**Supported formats**: CSV, JSON, Excel'),
    ('내보내기 형식 (csv/json/xlsx)', 'Export format (csv/json/xlsx)'),
    ('\"\"\"히스토리 데이터 내보내기\"\"\"', '"""Export history data"""'),
]

for korean, english in replacements:
    content = content.replace(korean, english)

# Write back the file
with open('/Users/isihyeon/Desktop/Arrakis-Project/audit-service/api/routes/history.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Korean text replaced successfully")