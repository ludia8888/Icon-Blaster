#!/usr/bin/env python3
"""
AsyncAPI Generation Test Script
"""
import sys
import os
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.schema_generator.asyncapi_generator import (
    AsyncAPIGenerator, generate_oms_asyncapi_spec
)
from core.schema_generator.graphql_to_asyncapi import (
    convert_graphql_to_asyncapi, GraphQLSchemaParser
)


def test_cloudevents_to_asyncapi():
    """CloudEvents에서 AsyncAPI 생성 테스트"""
    print("=== CloudEvents to AsyncAPI Test ===\n")
    
    try:
        # AsyncAPI 스펙 생성
        spec = generate_oms_asyncapi_spec(
            output_file="docs/oms-asyncapi.json",
            include_examples=True
        )
        
        print("✅ AsyncAPI 스펙 생성 성공!")
        print(f"📊 생성된 채널 수: {len(spec.get('channels', {}))}")
        print(f"📊 생성된 메시지 수: {len(spec.get('components', {}).get('messages', {}))}")
        print(f"📊 생성된 스키마 수: {len(spec.get('components', {}).get('schemas', {}))}")
        
        # 몇 가지 주요 채널 확인
        channels = spec.get('channels', {})
        print("\n🔍 생성된 주요 채널들:")
        for channel_name in list(channels.keys())[:5]:
            print(f"  • {channel_name}")
        
        # 서버 정보 확인
        servers = spec.get('servers', {})
        print(f"\n🖥️  설정된 서버들: {list(servers.keys())}")
        
        return True
        
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_graphql_parsing():
    """GraphQL 스키마 파싱 테스트"""
    print("\n=== GraphQL Schema Parsing Test ===\n")
    
    try:
        # 기존 GraphQL 스키마 파일 경로
        graphql_schema_path = "api/graphql/schema.py"
        
        if not Path(graphql_schema_path).exists():
            print(f"⚠️  GraphQL 스키마 파일을 찾을 수 없습니다: {graphql_schema_path}")
            print("📝 샘플 스키마로 테스트합니다...")
            
            # 샘플 GraphQL 스키마 생성
            sample_schema = '''
            type Query {
                objectTypes: [ObjectType!]!
                objectType(id: ID!): ObjectType
                properties(objectTypeId: ID!): [Property!]!
            }
            
            type Mutation {
                createObjectType(input: CreateObjectTypeInput!): ObjectType!
                updateObjectType(id: ID!, input: UpdateObjectTypeInput!): ObjectType!
                deleteObjectType(id: ID!): Boolean!
                createProperty(input: CreatePropertyInput!): Property!
            }
            
            type Subscription {
                objectTypeChanged(id: ID): ObjectType!
                propertyChanged(objectTypeId: ID): Property!
                schemaChanged: SchemaChangeEvent!
            }
            
            type ObjectType {
                id: ID!
                name: String!
                description: String
                properties: [Property!]!
                createdAt: DateTime!
                updatedAt: DateTime!
            }
            
            type Property {
                id: ID!
                name: String!
                dataType: DataType!
                objectType: ObjectType!
                required: Boolean!
            }
            
            enum DataType {
                STRING
                INTEGER
                FLOAT
                BOOLEAN
                DATE
                DATETIME
            }
            
            input CreateObjectTypeInput {
                name: String!
                description: String
            }
            
            input UpdateObjectTypeInput {
                name: String
                description: String
            }
            
            input CreatePropertyInput {
                name: String!
                dataType: DataType!
                objectTypeId: ID!
                required: Boolean = false
            }
            
            type SchemaChangeEvent {
                operation: String!
                resourceType: String!
                resourceId: String!
            }
            
            scalar DateTime
            '''
            
            # 임시 파일로 저장
            temp_schema_path = "temp_schema.graphql"
            with open(temp_schema_path, 'w') as f:
                f.write(sample_schema)
            
            graphql_schema_path = temp_schema_path
        
        # GraphQL 스키마 파싱
        parser = GraphQLSchemaParser()
        parsed_data = parser.parse_schema_file(graphql_schema_path)
        
        print("✅ GraphQL 스키마 파싱 성공!")
        print(f"📊 파싱된 타입 수: {len(parsed_data.get('types', {}))}")
        print(f"📊 Subscription 필드 수: {len(parsed_data.get('subscriptions', []))}")
        print(f"📊 Mutation 필드 수: {len(parsed_data.get('mutations', []))}")
        print(f"📊 Query 필드 수: {len(parsed_data.get('queries', []))}")
        
        # 타입들 출력
        print("\n🔍 파싱된 타입들:")
        for type_name, graphql_type in list(parsed_data.get('types', {}).items())[:5]:
            print(f"  • {type_name} ({graphql_type.kind})")
        
        # 구독들 출력
        print("\n📡 Subscription 필드들:")
        for sub in parsed_data.get('subscriptions', []):
            print(f"  • {sub.name}: {sub.type}")
        
        # 임시 파일 정리
        if 'temp_schema_path' in locals() and Path(temp_schema_path).exists():
            os.remove(temp_schema_path)
        
        return True
        
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_complete_conversion():
    """전체 변환 프로세스 테스트"""
    print("\n=== Complete Conversion Test ===\n")
    
    try:
        # 1. CloudEvents AsyncAPI 생성
        print("1️⃣ CloudEvents에서 AsyncAPI 생성...")
        generator = AsyncAPIGenerator()
        cloudevents_spec = generator.generate_from_cloudevents(include_examples=True)
        
        # 2. 스펙 검증
        required_fields = ['asyncapi', 'info', 'channels', 'components']
        for field in required_fields:
            if field not in cloudevents_spec:
                raise ValueError(f"Required field missing: {field}")
        
        print("✅ CloudEvents AsyncAPI 검증 완료")
        
        # 3. 파일 저장
        output_dir = Path("docs")
        output_dir.mkdir(exist_ok=True)
        
        with open(output_dir / "oms-events-asyncapi.json", 'w') as f:
            json.dump(cloudevents_spec, f, indent=2, default=str)
        
        print("✅ AsyncAPI 스펙 파일 저장 완료")
        
        # 4. 스펙 통계
        channels = cloudevents_spec.get('channels', {})
        messages = cloudevents_spec.get('components', {}).get('messages', {})
        schemas = cloudevents_spec.get('components', {}).get('schemas', {})
        
        print(f"\n📊 최종 통계:")
        print(f"  • 총 채널 수: {len(channels)}")
        print(f"  • 총 메시지 수: {len(messages)}")
        print(f"  • 총 스키마 수: {len(schemas)}")
        print(f"  • 서버 수: {len(cloudevents_spec.get('servers', {}))}")
        
        # 5. 샘플 채널 내용 출력
        print(f"\n🔍 샘플 채널 (첫 번째):")
        if channels:
            first_channel_name = list(channels.keys())[0]
            first_channel = channels[first_channel_name]
            print(f"  채널명: {first_channel_name}")
            print(f"  설명: {first_channel.get('description', 'N/A')}")
            
            if 'publish' in first_channel:
                print(f"  Operation: publish")
                print(f"  Operation ID: {first_channel['publish'].get('operationId', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ 변환 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_asyncapi_features():
    """AsyncAPI 고급 기능 테스트"""
    print("\n=== AsyncAPI Advanced Features Test ===\n")
    
    try:
        generator = AsyncAPIGenerator()
        
        # 커스텀 서버 추가 테스트
        generator._add_default_servers()
        print("✅ 서버 설정 완료")
        
        # 개별 이벤트 타입 처리 테스트
        from core.event_publisher.cloudevents_enhanced import EventType
        
        test_event_types = [
            EventType.SCHEMA_UPDATED,
            EventType.OBJECT_TYPE_CREATED,
            EventType.BRANCH_MERGED,
            EventType.ACTION_COMPLETED
        ]
        
        for event_type in test_event_types:
            generator._process_event_type(event_type, include_examples=True)
        
        print(f"✅ {len(test_event_types)}개 이벤트 타입 처리 완료")
        
        # 공통 스키마 추가
        generator._add_common_schemas()
        print("✅ 공통 스키마 추가 완료")
        
        # NATS Subject 패턴 테스트
        for event_type in test_event_types:
            subject = generator._get_nats_subject_pattern(event_type)
            print(f"  • {event_type.name}: {subject}")
        
        print("✅ NATS Subject 패턴 생성 완료")
        
        # 최종 스펙 빌드
        spec = generator._build_asyncapi_spec()
        
        # AsyncAPI 2.6.0 호환성 검증
        if spec.get('asyncapi') != '2.6.0':
            raise ValueError("AsyncAPI version mismatch")
        
        print("✅ AsyncAPI 2.6.0 호환성 검증 완료")
        
        return True
        
    except Exception as e:
        print(f"❌ 고급 기능 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """모든 테스트 실행"""
    print("🚀 AsyncAPI Generation Test Suite")
    print("=" * 50)
    
    tests = [
        ("CloudEvents to AsyncAPI", test_cloudevents_to_asyncapi),
        ("GraphQL Schema Parsing", test_graphql_parsing),
        ("Complete Conversion", test_complete_conversion),
        ("AsyncAPI Advanced Features", test_asyncapi_features)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
            
            if result:
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
                
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")
            results.append((test_name, False))
    
    # 결과 요약
    print(f"\n📊 Test Results Summary:")
    print("=" * 30)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} {test_name}")
    
    print(f"\n🎯 Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All AsyncAPI tests completed successfully!")
        
        # 생성된 파일들 표시
        docs_dir = Path("docs")
        if docs_dir.exists():
            print(f"\n📁 Generated files in {docs_dir}:")
            for file in docs_dir.glob("*asyncapi*.json"):
                print(f"  • {file.name}")
        
        return True
    else:
        print("⚠️  Some tests failed. Please check the logs above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)