"""
Naming Convention Engine 사용 예제
엔터프라이즈 환경의 명명 규칙 적용
"""
from core.validation.naming_convention import (
    NamingConventionEngine, EntityType, get_naming_engine
)


def demonstrate_naming_convention():
    """명명 규칙 엔진 데모"""
    engine = get_naming_engine()
    
    print("=== Naming Convention Engine Demo ===\n")
    
    # 1. 기본 검증
    print("1. Basic Validation:")
    test_names = [
        (EntityType.OBJECT_TYPE, "product_manager", "ProductManager"),
        (EntityType.OBJECT_TYPE, "HTTPServerError", "HTTPServerError"),
        (EntityType.PROPERTY, "FirstName", "firstName"),
        (EntityType.PROPERTY, "XMLData", "xmlData"),
        (EntityType.LINK_TYPE, "customer", "customerLink"),
        (EntityType.ACTION_TYPE, "productType", "createProductType"),
    ]
    
    for entity_type, input_name, expected in test_names:
        result = engine.validate(entity_type, input_name)
        fixed = engine.auto_fix(entity_type, input_name)
        print(f"  {entity_type.value}: '{input_name}'")
        print(f"    Valid: {result.is_valid}")
        if not result.is_valid:
            print(f"    Issues: {[issue.rule_violated for issue in result.issues]}")
        print(f"    Auto-fix: '{fixed}' (expected: '{expected}')")
        print()
    
    # 2. 복잡한 케이스
    print("\n2. Complex Cases:")
    complex_cases = [
        ("HTTP2ServerError", ["HTTP2", "Server", "Error"]),
        ("OAuth2TokenManager", ["OAuth2", "Token", "Manager"]),
        ("getAPIv3Client", ["get", "API", "v3", "Client"]),
        ("parse_JSON_data", ["parse", "JSON", "data"]),
    ]
    
    for name, expected_words in complex_cases:
        words = engine._split_words(name)
        print(f"  '{name}' → {words}")
        print(f"    Expected: {expected_words}")
        print(f"    Match: {words == expected_words}")
        print()
    
    # 3. 자동 교정 시연
    print("\n3. Auto-fix Demonstration:")
    fixes = [
        (EntityType.OBJECT_TYPE, "customer_profile_v2", "CustomerProfileV2"),
        (EntityType.PROPERTY, "HTTPHeaders", "httpHeaders"),
        (EntityType.LINK_TYPE, "user_group", "userGroupLink"),
        (EntityType.ACTION_TYPE, "HTTPClient", "createHTTPClient"),
        (EntityType.INTERFACE, "payment_processor", "IPaymentProcessor"),
    ]
    
    for entity_type, input_name, expected in fixes:
        fixed = engine.auto_fix(entity_type, input_name)
        print(f"  {entity_type.value}:")
        print(f"    Input:    '{input_name}'")
        print(f"    Fixed:    '{fixed}'")
        print(f"    Expected: '{expected}'")
        print(f"    Success:  {fixed == expected}")
        print()
    
    # 4. 검증 메시지
    print("\n4. Validation Messages:")
    result = engine.validate(EntityType.OBJECT_TYPE, "product-item")
    print(f"  Invalid name: 'product-item'")
    for issue in result.issues:
        print(f"    - {issue.message}")
        if issue.suggestion:
            print(f"      Suggestion: {issue.suggestion}")
    
    # 5. 성능 테스트
    print("\n\n5. Performance Test:")
    import time
    start = time.time()
    for i in range(1000):
        engine.validate(EntityType.OBJECT_TYPE, f"TestObject{i}")
    elapsed = time.time() - start
    print(f"  1000 validations: {elapsed:.3f}s ({1000/elapsed:.0f} ops/sec)")
    
    # 6. 엔터프라이즈 시나리오
    print("\n\n6. Enterprise Scenarios:")
    enterprise_names = [
        # 실제 시스템에서 자주 보는 이름들
        ("KafkaProducer", EntityType.OBJECT_TYPE),
        ("redisConnectionPool", EntityType.PROPERTY),
        ("S3BucketConfig", EntityType.OBJECT_TYPE),
        ("elasticsearchClient", EntityType.PROPERTY),
        ("gRPCServiceStub", EntityType.PROPERTY),
        ("OAuth2RefreshToken", EntityType.OBJECT_TYPE),
        ("JWT_SECRET_KEY", EntityType.PROPERTY),
    ]
    
    for name, entity_type in enterprise_names:
        result = engine.validate(entity_type, name)
        fixed = engine.auto_fix(entity_type, name) if not result.is_valid else name
        print(f"  {name} ({entity_type.value}):")
        print(f"    Valid: {result.is_valid}")
        if not result.is_valid:
            print(f"    Fixed: {fixed}")


if __name__ == "__main__":
    demonstrate_naming_convention()