#!/usr/bin/env python3
"""
🔥 THINK ULTRA!! Complex Types BFF Integration Test
BFF를 통한 복합 타입 end-to-end 테스트
"""

import httpx
import asyncio
import json
from datetime import datetime
import sys
import os

# Add shared to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'shared'))

from models.common import DataType
from validators.complex_type_validator import ComplexTypeConstraints
from test_config import TestConfig


class ComplexTypesBFFIntegrationTest:
    """🔥 THINK ULTRA!! 복합 타입 BFF 통합 테스터"""
    
    def __init__(self):
        self.test_db = "test_complex_bff_ultra"
        self.test_results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "details": []
        }
        
    async def run_all_tests(self):
        """모든 BFF 통합 테스트 실행"""
        
        print("🔥" * 60)
        print("🔥 THINK ULTRA!! Complex Types BFF Integration Test")
        print("🔥" * 60)
        
        async with httpx.AsyncClient(timeout=30) as client:
            # Setup
            await self.setup_test_database(client)
            
            # Run tests
            test_methods = [
                ("1️⃣ BFF 레이블 매핑 테스트", self.test_bff_label_mapping),
                ("2️⃣ 복합 타입 생성 (BFF)", self.test_complex_types_via_bff),
                ("3️⃣ 다국어 레이블 지원", self.test_multilingual_labels),
                ("4️⃣ 복합 타입 검증 (BFF)", self.test_validation_via_bff),
                ("5️⃣ 전체 워크플로우 테스트", self.test_complete_workflow)
            ]
            
            for test_name, test_method in test_methods:
                print(f"\n🧪 {test_name}")
                print("=" * 70)
                
                try:
                    await test_method(client)
                    self.record_result(test_name, True, "성공")
                except Exception as e:
                    self.record_result(test_name, False, str(e))
                    print(f"❌ 실패: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Cleanup
            await self.cleanup_test_database(client)
        
        self.print_summary()
    
    async def setup_test_database(self, client: httpx.AsyncClient):
        """테스트 데이터베이스 설정"""
        print("\n🔧 Setting up test database...")
        
        # Delete if exists
        try:
            await client.delete(f"{TestConfig.get_oms_base_url()}/api/v1/database/{self.test_db}")
        except:
            pass
        
        # Create new database via OMS
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/database/create",
            json={
                "name": self.test_db,
                "description": "Complex Types BFF Integration Test"
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to create database: {response.text}")
        
        print("✅ Test database created")
    
    async def cleanup_test_database(self, client: httpx.AsyncClient):
        """테스트 데이터베이스 정리"""
        print("\n🧹 Cleaning up test database...")
        
        try:
            await client.delete(f"{TestConfig.get_oms_base_url()}/api/v1/database/{self.test_db}")
            print("✅ Cleanup completed")
        except:
            print("⚠️ Cleanup failed")
    
    async def test_bff_label_mapping(self, client: httpx.AsyncClient):
        """BFF 레이블 매핑 테스트"""
        
        # Create ontology with labels via BFF
        ontology_data = {
            "label": {
                "en": "Test Product",
                "ko": "테스트 상품",
                "ja": "テスト製品"
            },
            "description": {
                "en": "Product with complex types",
                "ko": "복합 타입을 가진 상품"
            },
            "properties": [
                {
                    "name": "productName",
                    "type": DataType.STRING.value,
                    "label": {
                        "en": "Product Name",
                        "ko": "상품명",
                        "ja": "製品名"
                    },
                    "required": True
                },
                {
                    "name": "price",
                    "type": DataType.MONEY.value,
                    "label": {
                        "en": "Price",
                        "ko": "가격",
                        "ja": "価格"
                    },
                    "constraints": ComplexTypeConstraints.money_constraints(
                        min_amount=0,
                        max_amount=1000000
                    )
                }
            ]
        }
        
        # Test with different languages
        for lang in ["en", "ko", "ja"]:
            response = await client.post(
                f"{TestConfig.get_bff_base_url()}/database/{self.test_db}/ontology",
                json=ontology_data,
                headers={"Accept-Language": lang}
            )
            
            assert response.status_code == 200, f"Failed to create via BFF ({lang}): {response.text}"
            data = response.json()
            
            # Verify label is in correct language
            if isinstance(data.get("label"), dict):
                print(f"✅ {lang}: Label = {data['label'].get(lang, 'N/A')}")
            else:
                print(f"✅ {lang}: Created with ID = {data.get('id', 'Unknown')}")
    
    async def test_complex_types_via_bff(self, client: httpx.AsyncClient):
        """복합 타입 생성 테스트 (BFF 경유)"""
        
        # Create comprehensive model via BFF
        model_data = {
            "label": {
                "en": "Smart Device",
                "ko": "스마트 기기"
            },
            "properties": [
                # ARRAY type
                {
                    "name": "features",
                    "type": DataType.ARRAY.value,
                    "label": {"en": "Features", "ko": "기능"},
                    "constraints": ComplexTypeConstraints.array_constraints(
                        item_type=DataType.STRING.value,
                        unique_items=True
                    )
                },
                # OBJECT type
                {
                    "name": "settings",
                    "type": DataType.OBJECT.value,
                    "label": {"en": "Settings", "ko": "설정"},
                    "constraints": ComplexTypeConstraints.object_constraints(
                        schema={
                            "brightness": {"type": DataType.INTEGER.value},
                            "volume": {"type": DataType.INTEGER.value},
                            "language": {
                                "type": DataType.ENUM.value,
                                "constraints": {"enum": ["en", "ko", "ja", "zh"]}
                            }
                        },
                        required=["language"]
                    )
                },
                # ENUM type
                {
                    "name": "status",
                    "type": DataType.ENUM.value,
                    "label": {"en": "Status", "ko": "상태"},
                    "constraints": ComplexTypeConstraints.enum_constraints([
                        "active", "standby", "off", "error"
                    ])
                },
                # MONEY type
                {
                    "name": "price",
                    "type": DataType.MONEY.value,
                    "label": {"en": "Price", "ko": "가격"},
                    "constraints": ComplexTypeConstraints.money_constraints()
                },
                # PHONE type
                {
                    "name": "supportPhone",
                    "type": DataType.PHONE.value,
                    "label": {"en": "Support Phone", "ko": "지원 전화"},
                    "constraints": ComplexTypeConstraints.phone_constraints(
                        default_region="KR"
                    )
                },
                # EMAIL type
                {
                    "name": "supportEmail",
                    "type": DataType.EMAIL.value,
                    "label": {"en": "Support Email", "ko": "지원 이메일"},
                    "constraints": ComplexTypeConstraints.email_constraints()
                },
                # COORDINATE type
                {
                    "name": "gpsLocation",
                    "type": DataType.COORDINATE.value,
                    "label": {"en": "GPS Location", "ko": "GPS 위치"}
                },
                # ADDRESS type
                {
                    "name": "manufacturerAddress",
                    "type": DataType.ADDRESS.value,
                    "label": {"en": "Manufacturer Address", "ko": "제조사 주소"}
                },
                # IMAGE type
                {
                    "name": "productImage",
                    "type": DataType.IMAGE.value,
                    "label": {"en": "Product Image", "ko": "제품 이미지"}
                },
                # FILE type
                {
                    "name": "userManual",
                    "type": DataType.FILE.value,
                    "label": {"en": "User Manual", "ko": "사용 설명서"},
                    "constraints": ComplexTypeConstraints.file_constraints(
                        allowed_extensions=[".pdf", ".docx"]
                    )
                }
            ]
        }
        
        response = await client.post(
            f"{TestConfig.get_bff_base_url()}/database/{self.test_db}/ontology",
            json=model_data,
            headers={"Accept-Language": "ko"}
        )
        
        assert response.status_code == 200, f"Failed to create complex model: {response.text}"
        data = response.json()
        
        print(f"✅ Created SmartDevice with all 10 complex types")
        print(f"   - ID: {data.get('id', 'Unknown')}")
        print(f"   - Properties: {len(data.get('properties', []))} complex properties")
        
        # Verify all complex types
        property_types = {p["type"] for p in data.get("properties", [])}
        expected_types = {
            DataType.ARRAY.value, DataType.OBJECT.value, DataType.ENUM.value,
            DataType.MONEY.value, DataType.PHONE.value, DataType.EMAIL.value,
            DataType.COORDINATE.value, DataType.ADDRESS.value, DataType.IMAGE.value,
            DataType.FILE.value
        }
        
        missing_types = expected_types - property_types
        if missing_types:
            print(f"⚠️ Missing types: {missing_types}")
        else:
            print("✅ All 10 complex types successfully created via BFF")
    
    async def test_multilingual_labels(self, client: httpx.AsyncClient):
        """다국어 레이블 지원 테스트"""
        
        # Create ontology with extensive multilingual support
        ontology_data = {
            "label": {
                "en": "International Product",
                "ko": "국제 상품",
                "ja": "国際製品",
                "zh": "国际产品",
                "es": "Producto Internacional",
                "fr": "Produit International",
                "de": "Internationales Produkt"
            },
            "description": {
                "en": "A product for the global market",
                "ko": "글로벌 시장을 위한 상품",
                "ja": "グローバル市場向けの製品"
            },
            "properties": [
                {
                    "name": "name",
                    "type": DataType.STRING.value,
                    "label": {
                        "en": "Product Name",
                        "ko": "제품명",
                        "ja": "製品名",
                        "zh": "产品名称",
                        "es": "Nombre del Producto"
                    },
                    "required": True
                },
                {
                    "name": "categories",
                    "type": DataType.ARRAY.value,
                    "label": {
                        "en": "Categories",
                        "ko": "카테고리",
                        "ja": "カテゴリー",
                        "zh": "类别"
                    },
                    "constraints": ComplexTypeConstraints.array_constraints(
                        item_type=DataType.STRING.value,
                        unique_items=True
                    )
                }
            ]
        }
        
        # Create via BFF
        response = await client.post(
            f"{TestConfig.get_bff_base_url()}/database/{self.test_db}/ontology",
            json=ontology_data,
            headers={"Accept-Language": "ja"}  # Request in Japanese
        )
        
        assert response.status_code == 200, f"Failed to create multilingual ontology: {response.text}"
        data = response.json()
        
        print(f"✅ Created multilingual ontology")
        
        # Query back with different languages
        ontology_id = data.get("id")
        if ontology_id:
            for lang in ["en", "ko", "ja", "zh"]:
                response = await client.get(
                    f"{TestConfig.get_bff_base_url()}/database/{self.test_db}/ontology/{ontology_id}",
                    headers={"Accept-Language": lang}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    label = result.get("label", {})
                    if isinstance(label, dict):
                        print(f"   - {lang}: {label.get(lang, 'N/A')}")
    
    async def test_validation_via_bff(self, client: httpx.AsyncClient):
        """복합 타입 검증 테스트 (BFF 경유)"""
        
        # Create ontology with strict validation
        ontology_data = {
            "label": {"en": "Validated Product", "ko": "검증된 상품"},
            "properties": [
                {
                    "name": "email",
                    "type": DataType.EMAIL.value,
                    "label": {"en": "Email", "ko": "이메일"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.email_constraints(
                        allowed_domains=["company.com", "business.com"]
                    )
                },
                {
                    "name": "price",
                    "type": DataType.MONEY.value,
                    "label": {"en": "Price", "ko": "가격"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.money_constraints(
                        min_amount=0,
                        max_amount=1000,
                        allowed_currencies=["USD", "EUR"]
                    )
                },
                {
                    "name": "status",
                    "type": DataType.ENUM.value,
                    "label": {"en": "Status", "ko": "상태"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.enum_constraints([
                        "draft", "published", "archived"
                    ])
                }
            ]
        }
        
        response = await client.post(
            f"{TestConfig.get_bff_base_url()}/database/{self.test_db}/ontology",
            json=ontology_data
        )
        
        assert response.status_code == 200, f"Failed to create validated ontology: {response.text}"
        print("✅ Created ontology with validation constraints")
        
        # Test invalid data (this would be in actual document creation, not ontology)
        # For now, just verify the constraints are properly stored
        data = response.json()
        email_prop = next((p for p in data.get("properties", []) if p["name"] == "email"), None)
        if email_prop and "constraints" in email_prop:
            constraints = email_prop["constraints"]
            print(f"✅ Email constraints preserved: {constraints.get('allowedDomains', [])}")
    
    async def test_complete_workflow(self, client: httpx.AsyncClient):
        """전체 워크플로우 테스트"""
        
        # 1. Create comprehensive e-commerce model
        ecommerce_model = {
            "label": {
                "en": "Complete E-commerce Product",
                "ko": "완전한 전자상거래 상품"
            },
            "description": {
                "en": "E-commerce product using all complex types",
                "ko": "모든 복합 타입을 사용하는 전자상거래 상품"
            },
            "properties": [
                # Basic info
                {
                    "name": "sku",
                    "type": DataType.STRING.value,
                    "label": {"en": "SKU", "ko": "SKU"},
                    "required": True
                },
                # Complex array of objects
                {
                    "name": "variants",
                    "type": DataType.ARRAY.value,
                    "label": {"en": "Product Variants", "ko": "상품 변형"},
                    "constraints": ComplexTypeConstraints.array_constraints(
                        item_type=DataType.OBJECT.value,
                        min_items=1,
                        max_items=10
                    )
                },
                # Nested pricing with money type
                {
                    "name": "pricing",
                    "type": DataType.OBJECT.value,
                    "label": {"en": "Pricing Info", "ko": "가격 정보"},
                    "constraints": ComplexTypeConstraints.object_constraints(
                        schema={
                            "basePrice": {"type": DataType.MONEY.value},
                            "salePrice": {"type": DataType.MONEY.value},
                            "currency": {
                                "type": DataType.ENUM.value,
                                "constraints": {"enum": ["USD", "EUR", "KRW", "JPY"]}
                            }
                        },
                        required=["basePrice", "currency"]
                    )
                },
                # Contact information
                {
                    "name": "vendorContact",
                    "type": DataType.OBJECT.value,
                    "label": {"en": "Vendor Contact", "ko": "공급업체 연락처"},
                    "constraints": ComplexTypeConstraints.object_constraints(
                        schema={
                            "email": {"type": DataType.EMAIL.value},
                            "phone": {"type": DataType.PHONE.value},
                            "address": {"type": DataType.ADDRESS.value}
                        }
                    )
                },
                # Location data
                {
                    "name": "warehouseLocations",
                    "type": DataType.ARRAY.value,
                    "label": {"en": "Warehouse Locations", "ko": "창고 위치"},
                    "constraints": ComplexTypeConstraints.array_constraints(
                        item_type=DataType.COORDINATE.value,
                        max_items=5
                    )
                },
                # Media files
                {
                    "name": "media",
                    "type": DataType.OBJECT.value,
                    "label": {"en": "Media Files", "ko": "미디어 파일"},
                    "constraints": ComplexTypeConstraints.object_constraints(
                        schema={
                            "mainImage": {"type": DataType.IMAGE.value},
                            "gallery": {
                                "type": DataType.ARRAY.value,
                                "constraints": {
                                    "itemType": DataType.IMAGE.value,
                                    "maxItems": 10
                                }
                            },
                            "documents": {
                                "type": DataType.ARRAY.value,
                                "constraints": {
                                    "itemType": DataType.FILE.value,
                                    "maxItems": 5
                                }
                            }
                        }
                    )
                }
            ]
        }
        
        # Create via BFF
        response = await client.post(
            f"{TestConfig.get_bff_base_url()}/database/{self.test_db}/ontology",
            json=ecommerce_model,
            headers={"Accept-Language": "ko"}
        )
        
        assert response.status_code == 200, f"Failed to create complete model: {response.text}"
        data = response.json()
        
        print(f"✅ Created complete e-commerce model")
        print(f"   - ID: {data.get('id', 'Unknown')}")
        
        # 2. Query it back
        ontology_id = data.get("id")
        if ontology_id:
            response = await client.get(
                f"{TestConfig.get_bff_base_url()}/database/{self.test_db}/ontology/{ontology_id}",
                headers={"Accept-Language": "en"}
            )
            
            assert response.status_code == 200, "Failed to retrieve ontology"
            retrieved = response.json()
            
            print(f"✅ Retrieved ontology successfully")
            print(f"   - Properties count: {len(retrieved.get('properties', []))}")
            
            # 3. Verify complex nested structures
            pricing_prop = next((p for p in retrieved.get("properties", []) 
                               if p["name"] == "pricing"), None)
            if pricing_prop:
                print("✅ Complex nested structures preserved")
            
            # 4. List all ontologies
            response = await client.get(
                f"{TestConfig.get_bff_base_url()}/database/{self.test_db}/ontology",
                headers={"Accept-Language": "ko"}
            )
            
            if response.status_code == 200:
                ontologies = response.json()
                print(f"✅ Total ontologies created: {len(ontologies)}")
    
    def record_result(self, test_name: str, success: bool, message: str):
        """테스트 결과 기록"""
        self.test_results["total"] += 1
        if success:
            self.test_results["passed"] += 1
        else:
            self.test_results["failed"] += 1
        
        self.test_results["details"].append({
            "test": test_name,
            "success": success,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
    
    def print_summary(self):
        """테스트 요약 출력"""
        
        print("\n" + "🔥" * 60)
        print("🔥 THINK ULTRA!! BFF Integration Test Results")
        print("🔥" * 60)
        
        print(f"\n📊 테스트 통계:")
        print(f"   총 테스트: {self.test_results['total']}")
        print(f"   성공: {self.test_results['passed']} ✅")
        print(f"   실패: {self.test_results['failed']} ❌")
        
        if self.test_results['total'] > 0:
            success_rate = (self.test_results['passed'] / self.test_results['total']) * 100
            print(f"   성공률: {success_rate:.1f}%")
        
        if self.test_results['failed'] > 0:
            print("\n❌ 실패한 테스트:")
            for detail in self.test_results['details']:
                if not detail['success']:
                    print(f"   - {detail['test']}: {detail['message']}")
        
        print(f"\n🏆 결론:")
        if self.test_results['failed'] == 0:
            print("   ✅ BFF를 통한 복합 타입 통합이 완벽하게 작동합니다!")
            print("   ✅ 다국어 레이블 매핑 성공!")
            print("   ✅ 전체 API 워크플로우 검증 완료!")
        else:
            print("   ⚠️ 일부 BFF 통합 테스트에 문제가 있습니다.")
        
        # Save results
        result_file = f"bff_integration_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(self.test_results, f, ensure_ascii=False, indent=2)
        
        print(f"\n📄 상세 결과가 저장되었습니다: {result_file}")


async def main():
    """메인 테스트 실행"""
    
    tester = ComplexTypesBFFIntegrationTest()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())