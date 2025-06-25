# NamingConventionRule 개선 방안

## 1. 이전 이름 추적 메타데이터 추가

```python
# 엔티티에 이름 변경 이력 추가
{
    "name": "currentName",
    "previous_names": [
        {
            "name": "oldName",
            "changed_at": "2024-01-01T00:00:00Z",
            "reason": "refactoring"
        }
    ],
    "name_alias": "oldName"  # 하위 호환성을 위한 별칭
}
```

## 2. 개선된 변경 감지 로직

```python
async def _check_object_types(self, context: ValidationContext) -> List[BreakingChange]:
    breaking_changes = []
    
    for obj_id, obj_type in context.target_schemas.get("object_types", {}).items():
        source_obj = context.source_schemas.get("object_types", {}).get(obj_id)
        
        # 이름 변경 감지 개선
        name_changed = False
        previous_name = None
        
        if source_obj:
            current_name = obj_type.get("name", "")
            source_name = source_obj.get("name", "")
            
            if current_name != source_name:
                name_changed = True
                previous_name = source_name
                
                # 이름 변경 이력 추적
                previous_names = obj_type.get("previous_names", [])
                if not any(p["name"] == source_name for p in previous_names):
                    # 이력에 추가 권장
                    logger.warning(
                        f"Name change detected for {obj_id}: "
                        f"'{source_name}' -> '{current_name}' "
                        "but no history recorded"
                    )
        
        # 새 엔티티거나 이름이 변경된 경우 검증
        if not source_obj or name_changed:
            name = obj_type.get("name", "")
            result = self.engine.validate(EntityType.OBJECT_TYPE, name)
            
            if not result.is_valid:
                # Breaking change 생성 시 이전 이름 정보 포함
                details = {
                    "issues": [...],
                    "auto_fix_available": bool(result.suggestions),
                    "suggested_name": result.suggestions.get(name)
                }
                
                if previous_name:
                    details["previous_name"] = previous_name
                    details["name_change_type"] = "rename"
                
                breaking_changes.append(
                    BreakingChange(
                        change_id=f"naming-{obj_id}",
                        resource_type="ObjectType",
                        resource_id=obj_id,
                        change_type="naming-violation",
                        severity=severity,
                        description=self._format_description(name, previous_name),
                        affected_resources=affected_resources,
                        migration_required=True,
                        migration_complexity=self._calculate_complexity(name_changed, result),
                        details=details
                    )
                )
```

## 3. 이름 변경 영향도 분석 강화

```python
def _format_description(self, name: str, previous_name: Optional[str]) -> str:
    if previous_name:
        return (
            f"ObjectType renamed from '{previous_name}' to '{name}' "
            "violates naming convention"
        )
    else:
        return f"ObjectType '{name}' violates naming convention"

def _calculate_complexity(self, is_rename: bool, result) -> str:
    # 이름 변경은 더 높은 복잡도
    if is_rename:
        return "high" if not result.suggestions else "medium"
    else:
        return "low" if result.suggestions else "medium"
```

## 4. 별칭(Alias) 지원을 통한 하위 호환성

```python
def _check_alias_compatibility(self, entity: Dict, previous_name: str) -> bool:
    """별칭을 통한 하위 호환성 확인"""
    alias = entity.get("name_alias")
    return alias == previous_name

# Breaking change 심각도 조정
if self._check_alias_compatibility(obj_type, previous_name):
    severity = Severity.LOW  # 별칭이 있으면 낮은 심각도
else:
    severity = Severity.HIGH  # 별칭이 없으면 높은 심각도
```

## 5. 추천 구현 사항

1. **Schema Migration 도구와 연동**
   - 이름 변경 시 자동으로 이력 기록
   - 별칭 자동 생성 옵션

2. **Validation Context 확장**
   - 이름 변경 이력을 컨텍스트에 포함
   - 전체 변경 히스토리 추적

3. **리포트 개선**
   - 이름 변경 경로 표시 (A → B → C)
   - 영향받는 코드/API 목록 자동 생성

4. **자동 수정 제안**
   - 이름 변경 시 별칭 추가 제안
   - 이전 이름 이력 자동 기록