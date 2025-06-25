# BreakingChange 생성 로직 리팩터링 계획

## 현재 문제점
- `_check_object_types`, `_check_properties`, `_check_link_types`가 유사한 구조 반복
- 새 엔티티 타입 추가 시 코드 복사 필요
- 공통 로직 변경 시 여러 곳 수정 필요

## 리팩터링 방안

### 1. 엔티티 설정 클래스 정의

```python
@dataclass
class EntityConfig:
    """엔티티별 검증 설정"""
    entity_type: EntityType
    resource_type: str  # "ObjectType", "Property", "LinkType"
    schema_path: str    # "object_types", "link_types"
    
    # 스키마 접근 방식
    schema_accessor: Callable[[Dict], Iterator[Tuple[str, Dict]]]
    
    # ID 생성 방식
    id_generator: Callable[[str, Optional[str]], str]
    
    # 영향도 분석
    impact_analyzer: Optional[Callable[[str, List], Optional[Dict]]] = None
    
    # 복잡도 계산
    complexity_calculator: Callable[[bool, Any], str] = lambda changed, result: "low" if result.suggestions else "medium"
```

### 2. 공통 검증 메서드

```python
async def _check_entity_naming(
    self, 
    context: ValidationContext, 
    config: EntityConfig
) -> List[BreakingChange]:
    """엔티티 명명 규칙 검증 (공통 로직)"""
    breaking_changes = []
    
    # 엔티티 목록 가져오기
    for entity_id, entity_data in config.schema_accessor(context.target_schemas):
        # 변경 감지
        source_entity = self._get_source_entity(context, config, entity_id)
        name_changed = self._detect_name_change(source_entity, entity_data)
        
        # 새 엔티티거나 이름이 변경된 경우만 검증
        if not source_entity or name_changed:
            name = entity_data.get("name", "")
            result = self.engine.validate(config.entity_type, name)
            
            if not result.is_valid:
                breaking_change = self._create_breaking_change(
                    config, entity_id, entity_data, result, 
                    source_entity, context
                )
                breaking_changes.append(breaking_change)
    
    return breaking_changes
```

### 3. 엔티티별 설정 정의

```python
# ObjectType 설정
OBJECT_TYPE_CONFIG = EntityConfig(
    entity_type=EntityType.OBJECT_TYPE,
    resource_type="ObjectType",
    schema_path="object_types",
    schema_accessor=lambda schemas: schemas.get("object_types", {}).items(),
    id_generator=lambda obj_id, prop_id=None: f"naming-{obj_id}",
    complexity_calculator=lambda changed, result: "low" if result.suggestions else "medium"
)

# Property 설정
PROPERTY_CONFIG = EntityConfig(
    entity_type=EntityType.PROPERTY,
    resource_type="Property", 
    schema_path="object_types",
    schema_accessor=lambda schemas: self._get_all_properties(schemas),
    id_generator=lambda obj_id, prop_id: f"naming-{obj_id}-{prop_id}",
    impact_analyzer=lambda name, issues: self._analyze_api_impact(name, issues),
    complexity_calculator=lambda changed, result: "high" if changed else "low"
)

# LinkType 설정
LINK_TYPE_CONFIG = EntityConfig(
    entity_type=EntityType.LINK_TYPE,
    resource_type="LinkType",
    schema_path="link_types", 
    schema_accessor=lambda schemas: schemas.get("link_types", {}).items(),
    id_generator=lambda link_id, _=None: f"naming-{link_id}",
    complexity_calculator=lambda changed, result: "low"
)
```

### 4. 리팩터링된 execute 메서드

```python
async def execute(self, context: ValidationContext) -> RuleExecutionResult:
    """명명 규칙 검증 실행"""
    breaking_changes = []
    warnings = []
    
    try:
        # 모든 엔티티 타입에 대해 검증
        configs = [OBJECT_TYPE_CONFIG, PROPERTY_CONFIG, LINK_TYPE_CONFIG]
        
        for config in configs:
            breaking_changes.extend(
                await self._check_entity_naming(context, config)
            )
        
        # 크로스 엔티티 충돌 검증
        warnings.extend(
            await self._check_cross_entity_conflicts(context)
        )
        
        return RuleExecutionResult(...)
    except Exception as e:
        # 에러 처리...
```

## 장점

1. **DRY 원칙**: 중복 코드 제거
2. **확장성**: 새 엔티티 타입을 설정으로 쉽게 추가
3. **유지보수성**: 공통 로직 변경 시 한 곳만 수정
4. **테스트 용이성**: 각 설정을 독립적으로 테스트 가능
5. **일관성**: 모든 엔티티가 동일한 검증 로직 사용

## 추가 개선사항

1. **Factory Pattern**: EntityConfig 생성을 팩토리로 관리
2. **Strategy Pattern**: 엔티티별 특수 로직을 전략 객체로 분리
3. **Builder Pattern**: 복잡한 BreakingChange 생성을 빌더로 처리
4. **Configuration**: 엔티티 설정을 외부 파일로 관리