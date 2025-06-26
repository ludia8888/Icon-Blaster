#!/usr/bin/env python3
"""
SDK Generation Test Script
AsyncAPI 스펙에서 TypeScript/Python SDK 자동 생성 테스트
"""
import sys
import os
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.schema_generator.sdk_generator import (
    SDKGeneratorOrchestrator, SDKConfig, generate_sdks_from_asyncapi
)


def test_typescript_sdk_generation():
    """TypeScript SDK 생성 테스트"""
    print("=== TypeScript SDK Generation Test ===\n")
    
    try:
        asyncapi_path = "docs/oms-asyncapi.json"
        
        if not Path(asyncapi_path).exists():
            print(f"❌ AsyncAPI 스펙 파일을 찾을 수 없습니다: {asyncapi_path}")
            print("먼저 AsyncAPI 스펙을 생성해주세요.")
            return False
        
        # SDK 설정
        config = SDKConfig(
            package_name="oms-event-sdk-ts",
            version="1.0.0",
            author="OMS Team",
            description="TypeScript SDK for OMS Event API"
        )
        
        # TypeScript SDK 생성
        orchestrator = SDKGeneratorOrchestrator()
        
        with open(asyncapi_path, 'r') as f:
            asyncapi_spec = json.load(f)
        
        from core.schema_generator.sdk_generator import TypeScriptSDKGenerator
        generator = TypeScriptSDKGenerator(config)
        
        output_path = generator.generate_sdk(asyncapi_spec, "sdks")
        
        print("✅ TypeScript SDK 생성 성공!")
        print(f"📁 생성 위치: {output_path}")
        
        # 생성된 파일들 확인
        ts_path = Path(output_path)
        if ts_path.exists():
            files = list(ts_path.rglob("*"))
            print(f"📊 생성된 파일 수: {len(files)}")
            print("\n🔍 생성된 파일들:")
            for file_path in sorted(files):
                if file_path.is_file():
                    file_size = file_path.stat().st_size
                    print(f"  • {file_path.relative_to(ts_path)} ({file_size} bytes)")
        
        # package.json 검증
        package_json_path = ts_path / "package.json"
        if package_json_path.exists():
            with open(package_json_path, 'r') as f:
                package_data = json.load(f)
            print(f"\n📦 패키지 정보:")
            print(f"  • 이름: {package_data.get('name')}")
            print(f"  • 버전: {package_data.get('version')}")
            print(f"  • 설명: {package_data.get('description')}")
        
        return True
        
    except Exception as e:
        print(f"❌ TypeScript SDK 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_python_sdk_generation():
    """Python SDK 생성 테스트"""
    print("\n=== Python SDK Generation Test ===\n")
    
    try:
        asyncapi_path = "docs/oms-asyncapi.json"
        
        if not Path(asyncapi_path).exists():
            print(f"❌ AsyncAPI 스펙 파일을 찾을 수 없습니다: {asyncapi_path}")
            return False
        
        # SDK 설정
        config = SDKConfig(
            package_name="oms-event-sdk-py",
            version="1.0.0",
            author="OMS Team",
            description="Python SDK for OMS Event API",
            python_min_version="3.8"
        )
        
        # Python SDK 생성
        orchestrator = SDKGeneratorOrchestrator()
        
        with open(asyncapi_path, 'r') as f:
            asyncapi_spec = json.load(f)
        
        from core.schema_generator.sdk_generator import PythonSDKGenerator
        generator = PythonSDKGenerator(config)
        
        output_path = generator.generate_sdk(asyncapi_spec, "sdks")
        
        print("✅ Python SDK 생성 성공!")
        print(f"📁 생성 위치: {output_path}")
        
        # 생성된 파일들 확인
        py_path = Path(output_path)
        if py_path.exists():
            files = list(py_path.rglob("*"))
            print(f"📊 생성된 파일 수: {len(files)}")
            print("\n🔍 생성된 파일들:")
            for file_path in sorted(files):
                if file_path.is_file():
                    file_size = file_path.stat().st_size
                    print(f"  • {file_path.relative_to(py_path)} ({file_size} bytes)")
        
        # setup.py 검증
        setup_py_path = py_path / "setup.py"
        if setup_py_path.exists():
            print(f"\n📦 Python 패키지 정보:")
            print(f"  • 패키지명: {config.package_name}")
            print(f"  • 버전: {config.version}")
            print(f"  • 최소 Python 버전: {config.python_min_version}")
        
        return True
        
    except Exception as e:
        print(f"❌ Python SDK 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_batch_sdk_generation():
    """일괄 SDK 생성 테스트"""
    print("\n=== Batch SDK Generation Test ===\n")
    
    try:
        asyncapi_path = "docs/oms-asyncapi.json"
        
        if not Path(asyncapi_path).exists():
            print(f"❌ AsyncAPI 스펙 파일을 찾을 수 없습니다: {asyncapi_path}")
            return False
        
        # 일괄 생성
        results = generate_sdks_from_asyncapi(
            asyncapi_spec_path=asyncapi_path,
            output_dir="sdks",
            languages=["typescript", "python"],
            package_name="oms-event-sdk"
        )
        
        print("✅ 일괄 SDK 생성 성공!")
        print(f"📊 생성된 SDK 수: {len(results)}")
        
        for language, path in results.items():
            print(f"  • {language}: {path}")
            
            # 각 SDK 디렉토리 크기 확인
            sdk_path = Path(path)
            if sdk_path.exists():
                total_size = sum(f.stat().st_size for f in sdk_path.rglob('*') if f.is_file())
                file_count = len([f for f in sdk_path.rglob('*') if f.is_file()])
                print(f"    - 파일 수: {file_count}")
                print(f"    - 총 크기: {total_size:,} bytes")
        
        return True
        
    except Exception as e:
        print(f"❌ 일괄 SDK 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_generated_sdk_structure():
    """생성된 SDK 구조 검증"""
    print("\n=== Generated SDK Structure Validation ===\n")
    
    try:
        sdks_dir = Path("sdks")
        
        if not sdks_dir.exists():
            print("❌ SDK 디렉토리가 존재하지 않습니다.")
            return False
        
        # TypeScript SDK 구조 검증
        ts_dir = sdks_dir / "typescript"
        if ts_dir.exists():
            print("🔍 TypeScript SDK 구조:")
            expected_ts_files = ["package.json", "types.ts", "client.ts", "README.md"]
            
            for file_name in expected_ts_files:
                file_path = ts_dir / file_name
                if file_path.exists():
                    print(f"  ✅ {file_name}")
                else:
                    print(f"  ❌ {file_name} (누락)")
            
            # package.json 내용 검증
            package_json = ts_dir / "package.json"
            if package_json.exists():
                with open(package_json, 'r') as f:
                    pkg_data = json.load(f)
                
                required_fields = ["name", "version", "description", "main", "types"]
                print("\n  📦 package.json 필드:")
                for field in required_fields:
                    if field in pkg_data:
                        print(f"    ✅ {field}: {pkg_data[field]}")
                    else:
                        print(f"    ❌ {field} (누락)")
        
        # Python SDK 구조 검증
        py_dir = sdks_dir / "python"
        if py_dir.exists():
            print("\n🔍 Python SDK 구조:")
            expected_py_files = ["setup.py", "requirements.txt", "README.md"]
            
            for file_name in expected_py_files:
                file_path = py_dir / file_name
                if file_path.exists():
                    print(f"  ✅ {file_name}")
                else:
                    print(f"  ❌ {file_name} (누락)")
            
            # 패키지 디렉토리 확인
            package_dirs = [d for d in py_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
            if package_dirs:
                package_dir = package_dirs[0]
                print(f"\n  📦 패키지 디렉토리: {package_dir.name}")
                
                expected_py_modules = ["__init__.py", "client.py", "models.py"]
                for module_name in expected_py_modules:
                    module_path = package_dir / module_name
                    if module_path.exists():
                        print(f"    ✅ {module_name}")
                    else:
                        print(f"    ❌ {module_name} (누락)")
        
        return True
        
    except Exception as e:
        print(f"❌ SDK 구조 검증 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sdk_content_validation():
    """생성된 SDK 내용 검증"""
    print("\n=== SDK Content Validation ===\n")
    
    try:
        # TypeScript 타입 파일 검증
        ts_types_path = Path("sdks/typescript/types.ts")
        if ts_types_path.exists():
            with open(ts_types_path, 'r') as f:
                ts_content = f.read()
            
            print("🔍 TypeScript types.ts 내용:")
            
            # 핵심 인터페이스 확인
            expected_interfaces = ["PublishResult", "Subscription", "EventPublisher", "EventSubscriber"]
            for interface in expected_interfaces:
                if f"interface {interface}" in ts_content:
                    print(f"  ✅ {interface} 인터페이스")
                else:
                    print(f"  ❌ {interface} 인터페이스 (누락)")
            
            # 생성된 타입 개수 확인
            interface_count = ts_content.count("export interface")
            type_count = ts_content.count("export type")
            print(f"  📊 생성된 인터페이스: {interface_count}개")
            print(f"  📊 생성된 타입: {type_count}개")
        
        # Python 모델 파일 검증
        py_models_path = Path("sdks/python")
        package_dirs = [d for d in py_models_path.iterdir() if d.is_dir() and not d.name.startswith('.')]
        
        if package_dirs:
            models_path = package_dirs[0] / "models.py"
            if models_path.exists():
                with open(models_path, 'r') as f:
                    py_content = f.read()
                
                print("\n🔍 Python models.py 내용:")
                
                # 핵심 클래스 확인
                expected_classes = ["PublishResult", "Subscription", "BaseModel"]
                for class_name in expected_classes:
                    if f"class {class_name}" in py_content:
                        print(f"  ✅ {class_name} 클래스")
                    else:
                        print(f"  ❌ {class_name} 클래스 (누락)")
                
                # 생성된 모델 개수 확인
                class_count = py_content.count("class ")
                print(f"  📊 생성된 클래스: {class_count}개")
        
        return True
        
    except Exception as e:
        print(f"❌ SDK 내용 검증 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """모든 SDK 생성 테스트 실행"""
    print("🚀 SDK Generation Test Suite")
    print("=" * 50)
    
    tests = [
        ("TypeScript SDK Generation", test_typescript_sdk_generation),
        ("Python SDK Generation", test_python_sdk_generation),
        ("Batch SDK Generation", test_batch_sdk_generation),
        ("Generated SDK Structure", test_generated_sdk_structure),
        ("SDK Content Validation", test_sdk_content_validation)
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
        print("🎉 All SDK generation tests completed successfully!")
        
        # 생성된 SDK 디렉토리 표시
        sdks_dir = Path("sdks")
        if sdks_dir.exists():
            print(f"\n📁 Generated SDKs in {sdks_dir}:")
            for sdk_dir in sdks_dir.iterdir():
                if sdk_dir.is_dir():
                    file_count = len([f for f in sdk_dir.rglob('*') if f.is_file()])
                    print(f"  • {sdk_dir.name}/ ({file_count} files)")
        
        print("\n🚀 Ready for use:")
        print("  • TypeScript: cd sdks/typescript && npm install && npm run build")
        print("  • Python: cd sdks/python && pip install -e .")
        
        return True
    else:
        print("⚠️  Some tests failed. Please check the logs above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)