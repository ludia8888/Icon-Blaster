#!/usr/bin/env python3
"""
Fix remaining Korean text in history.py
"""

import re

# Read the file
with open('/Users/isihyeon/Desktop/Arrakis-Project/audit-service/api/routes/history.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace remaining Korean text with English equivalents
replacements = [
    ('# 필터링 파라미터', '# Filtering parameters'),
    ('# 날짜 범위', '# Date range'),
    ('# 포함 옵션', '# Include options'),
    ('# 페이지네이션', '# Pagination'),
    ('# 정렬', '# Sorting'),
    ('# 의존성', '# Dependencies'),
    ('\"\"\"스키마 변경 히스토리 목록 조회\"\"\"', '"""Query schema change history list"""'),
    ('# 권한 확인', '# Permission check'),
    ('# 쿼리 객체 생성', '# Create query object'),
    ('# 히스토리 조회', '# Query history'),
    ('\"\"\"커밋 상세 정보 조회\"\"\"', '"""Get commit details"""'),
    ('# 커밋 상세 조회', '# Get commit details'),
    ('\"\"\"커밋 차이점 조회\"\"\"', '"""Get commit differences"""'),
    ('\"\"\"히스토리 통계 조회\"\"\"', '"""Get history statistics"""'),
    ('\"\"\"히스토리 데이터 내보내기\"\"\"', '"""Export history data"""'),
    ('# 내보내기 파일 생성', '# Create export file'),
    ('description="시작 날짜"', 'description="Start date"'),
    ('description="종료 날짜"', 'description="End date"'),
    ('description="상세 변경 내역 포함"', 'description="Include detailed changes"'),
]

for korean, english in replacements:
    content = content.replace(korean, english)

# Write back the file
with open('/Users/isihyeon/Desktop/Arrakis-Project/audit-service/api/routes/history.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Remaining Korean text replaced successfully")