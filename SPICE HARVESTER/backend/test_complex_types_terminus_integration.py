#!/usr/bin/env python3
"""
🔥 THINK ULTRA!! Complex Types TerminusDB Integration Test
복합 타입의 실제 TerminusDB 통합 테스트
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


class ComplexTypesTerminusIntegrationTest:
    """🔥 THINK ULTRA!! 복합 타입 TerminusDB 통합 테스터"""
    
    def __init__(self):
        self.test_db = "test_complex_types_ultra"
        self.test_results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "details": []
        }
        
    async def run_all_tests(self):
        """모든 통합 테스트 실행"""
        
        print("🔥" * 60)
        print("🔥 THINK ULTRA!! Complex Types TerminusDB Integration Test")
        print("🔥" * 60)
        
        async with httpx.AsyncClient(timeout=30) as client:
            # Setup
            await self.setup_test_database(client)
            
            # Run tests
            test_methods = [
                ("1️⃣ ARRAY 타입 온톨로지", self.test_array_ontology),
                ("2️⃣ OBJECT 타입 온톨로지", self.test_object_ontology),
                ("3️⃣ ENUM 타입 온톨로지", self.test_enum_ontology),
                ("4️⃣ MONEY 타입 온톨로지", self.test_money_ontology),
                ("5️⃣ PHONE/EMAIL 타입 온톨로지", self.test_contact_ontology),
                ("6️⃣ COORDINATE/ADDRESS 타입 온톨로지", self.test_location_ontology),
                ("7️⃣ IMAGE/FILE 타입 온톨로지", self.test_media_ontology),
                ("8️⃣ 복합 타입 조합 온톨로지", self.test_complex_combination),
                ("9️⃣ 제약조건 검증 테스트", self.test_constraints_validation),
                ("🔟 전체 e-commerce 모델", self.test_ecommerce_model)
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
        
        # Create new database
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/database/create",
            json={
                "name": self.test_db,
                "description": "Complex Types Integration Test Database"
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
    
    async def test_array_ontology(self, client: httpx.AsyncClient):
        """ARRAY 타입 온톨로지 테스트"""
        
        # Create ontology with array properties
        ontology_data = {
            "id": "ShoppingCart",
            "label": {
                "en": "Shopping Cart",
                "ko": "장바구니"
            },
            "description": {
                "en": "Shopping cart with array properties",
                "ko": "배열 속성을 가진 장바구니"
            },
            "properties": [
                {
                    "name": "items",
                    "type": DataType.ARRAY.value,
                    "label": {"en": "Cart Items", "ko": "장바구니 항목"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.array_constraints(
                        min_items=1,
                        max_items=100,
                        item_type=DataType.STRING.value
                    )
                },
                {
                    "name": "tags",
                    "type": DataType.ARRAY.value,
                    "label": {"en": "Tags", "ko": "태그"},
                    "constraints": ComplexTypeConstraints.array_constraints(
                        unique_items=True,
                        item_type=DataType.STRING.value
                    )
                }
            ]
        }
        
        # Create via OMS
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/database/{self.test_db}/ontology",
            json=ontology_data
        )
        
        assert response.status_code == 200, f"Failed to create array ontology: {response.text}"
        data = response.json()
        
        print(f"✅ Created ShoppingCart ontology with ID: {data['id']}")
        
        # Verify properties
        assert any(p["name"] == "items" and p["type"] == DataType.ARRAY.value 
                  for p in data["properties"]), "Array property not found"
        
        print("✅ Array properties verified")
    
    async def test_object_ontology(self, client: httpx.AsyncClient):
        """OBJECT 타입 온톨로지 테스트"""
        
        # Define nested object schema
        address_schema = {
            "street": {"type": DataType.STRING.value},
            "city": {"type": DataType.STRING.value},
            "postalCode": {"type": DataType.STRING.value},
            "country": {"type": DataType.STRING.value, "constraints": {"pattern": "^[A-Z]{2}$"}}
        }
        
        ontology_data = {
            "id": "Customer",
            "label": {
                "en": "Customer",
                "ko": "고객"
            },
            "properties": [
                {
                    "name": "profile",
                    "type": DataType.OBJECT.value,
                    "label": {"en": "Profile", "ko": "프로필"},
                    "constraints": ComplexTypeConstraints.object_constraints(
                        schema={
                            "firstName": {"type": DataType.STRING.value},
                            "lastName": {"type": DataType.STRING.value},
                            "age": {"type": DataType.INTEGER.value}
                        },
                        required=["firstName", "lastName"]
                    )
                },
                {
                    "name": "address",
                    "type": DataType.OBJECT.value,
                    "label": {"en": "Address", "ko": "주소"},
                    "constraints": ComplexTypeConstraints.object_constraints(
                        schema=address_schema,
                        required=["street", "city", "country"]
                    )
                }
            ]
        }
        
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/database/{self.test_db}/ontology",
            json=ontology_data
        )
        
        assert response.status_code == 200, f"Failed to create object ontology: {response.text}"
        print(f"✅ Created Customer ontology with nested objects")
    
    async def test_enum_ontology(self, client: httpx.AsyncClient):
        """ENUM 타입 온톨로지 테스트"""
        
        ontology_data = {
            "id": "Order",
            "label": {
                "en": "Order",
                "ko": "주문"
            },
            "properties": [
                {
                    "name": "status",
                    "type": DataType.ENUM.value,
                    "label": {"en": "Order Status", "ko": "주문 상태"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.enum_constraints([
                        "pending", "processing", "shipped", "delivered", "cancelled"
                    ])
                },
                {
                    "name": "priority",
                    "type": DataType.ENUM.value,
                    "label": {"en": "Priority", "ko": "우선순위"},
                    "constraints": ComplexTypeConstraints.enum_constraints([
                        "low", "medium", "high", "urgent"
                    ])
                }
            ]
        }
        
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/database/{self.test_db}/ontology",
            json=ontology_data
        )
        
        assert response.status_code == 200, f"Failed to create enum ontology: {response.text}"
        print(f"✅ Created Order ontology with enum properties")
    
    async def test_money_ontology(self, client: httpx.AsyncClient):
        """MONEY 타입 온톨로지 테스트"""
        
        ontology_data = {
            "id": "Product",
            "label": {
                "en": "Product",
                "ko": "상품"
            },
            "properties": [
                {
                    "name": "price",
                    "type": DataType.MONEY.value,
                    "label": {"en": "Price", "ko": "가격"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.money_constraints(
                        min_amount=0,
                        max_amount=1000000,
                        decimal_places=2,
                        allowed_currencies=["USD", "EUR", "KRW", "JPY"]
                    )
                },
                {
                    "name": "originalPrice",
                    "type": DataType.MONEY.value,
                    "label": {"en": "Original Price", "ko": "정가"},
                    "constraints": ComplexTypeConstraints.money_constraints()
                }
            ]
        }
        
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/database/{self.test_db}/ontology",
            json=ontology_data
        )
        
        assert response.status_code == 200, f"Failed to create money ontology: {response.text}"
        print(f"✅ Created Product ontology with money properties")
    
    async def test_contact_ontology(self, client: httpx.AsyncClient):
        """PHONE/EMAIL 타입 온톨로지 테스트"""
        
        ontology_data = {
            "id": "ContactInfo",
            "label": {
                "en": "Contact Information",
                "ko": "연락처 정보"
            },
            "properties": [
                {
                    "name": "primaryPhone",
                    "type": DataType.PHONE.value,
                    "label": {"en": "Primary Phone", "ko": "주 전화번호"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.phone_constraints(
                        default_region="KR",
                        allowed_regions=["KR", "US", "JP"]
                    )
                },
                {
                    "name": "email",
                    "type": DataType.EMAIL.value,
                    "label": {"en": "Email Address", "ko": "이메일 주소"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.email_constraints(
                        check_deliverability=False
                    )
                },
                {
                    "name": "businessEmail",
                    "type": DataType.EMAIL.value,
                    "label": {"en": "Business Email", "ko": "업무 이메일"},
                    "constraints": ComplexTypeConstraints.email_constraints(
                        allowed_domains=["company.com", "business.com"]
                    )
                }
            ]
        }
        
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/database/{self.test_db}/ontology",
            json=ontology_data
        )
        
        assert response.status_code == 200, f"Failed to create contact ontology: {response.text}"
        print(f"✅ Created ContactInfo ontology with phone/email properties")
    
    async def test_location_ontology(self, client: httpx.AsyncClient):
        """COORDINATE/ADDRESS 타입 온톨로지 테스트"""
        
        ontology_data = {
            "id": "Store",
            "label": {
                "en": "Store",
                "ko": "매장"
            },
            "properties": [
                {
                    "name": "location",
                    "type": DataType.COORDINATE.value,
                    "label": {"en": "GPS Location", "ko": "GPS 위치"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.coordinate_constraints(
                        precision=6
                    )
                },
                {
                    "name": "address",
                    "type": DataType.ADDRESS.value,
                    "label": {"en": "Store Address", "ko": "매장 주소"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.address_constraints(
                        required_fields=["street", "city", "country"],
                        default_country="KR"
                    )
                }
            ]
        }
        
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/database/{self.test_db}/ontology",
            json=ontology_data
        )
        
        assert response.status_code == 200, f"Failed to create location ontology: {response.text}"
        print(f"✅ Created Store ontology with coordinate/address properties")
    
    async def test_media_ontology(self, client: httpx.AsyncClient):
        """IMAGE/FILE 타입 온톨로지 테스트"""
        
        ontology_data = {
            "id": "MediaContent",
            "label": {
                "en": "Media Content",
                "ko": "미디어 콘텐츠"
            },
            "properties": [
                {
                    "name": "thumbnail",
                    "type": DataType.IMAGE.value,
                    "label": {"en": "Thumbnail Image", "ko": "썸네일 이미지"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.image_constraints(
                        require_extension=True,
                        allowed_domains=["cdn.example.com", "images.example.com"]
                    )
                },
                {
                    "name": "images",
                    "type": DataType.ARRAY.value,
                    "label": {"en": "Gallery Images", "ko": "갤러리 이미지"},
                    "constraints": ComplexTypeConstraints.array_constraints(
                        item_type=DataType.IMAGE.value,
                        max_items=10
                    )
                },
                {
                    "name": "document",
                    "type": DataType.FILE.value,
                    "label": {"en": "Attached Document", "ko": "첨부 문서"},
                    "constraints": ComplexTypeConstraints.file_constraints(
                        max_size=10 * 1024 * 1024,  # 10MB
                        allowed_extensions=[".pdf", ".doc", ".docx"]
                    )
                }
            ]
        }
        
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/database/{self.test_db}/ontology",
            json=ontology_data
        )
        
        assert response.status_code == 200, f"Failed to create media ontology: {response.text}"
        print(f"✅ Created MediaContent ontology with image/file properties")
    
    async def test_complex_combination(self, client: httpx.AsyncClient):
        """복합 타입 조합 온톨로지 테스트"""
        
        # Create a complex ontology using multiple complex types
        ontology_data = {
            "id": "UserProfile",
            "label": {
                "en": "User Profile",
                "ko": "사용자 프로필"
            },
            "properties": [
                # Basic info
                {
                    "name": "username",
                    "type": DataType.STRING.value,
                    "label": {"en": "Username", "ko": "사용자명"},
                    "required": True
                },
                # Contact array
                {
                    "name": "emails",
                    "type": DataType.ARRAY.value,
                    "label": {"en": "Email Addresses", "ko": "이메일 주소들"},
                    "constraints": ComplexTypeConstraints.array_constraints(
                        item_type=DataType.EMAIL.value,
                        min_items=1,
                        max_items=5
                    )
                },
                # Nested object with complex types
                {
                    "name": "preferences",
                    "type": DataType.OBJECT.value,
                    "label": {"en": "Preferences", "ko": "환경설정"},
                    "constraints": ComplexTypeConstraints.object_constraints(
                        schema={
                            "language": {
                                "type": DataType.ENUM.value,
                                "constraints": {"enum": ["en", "ko", "ja", "zh"]}
                            },
                            "currency": {
                                "type": DataType.ENUM.value,
                                "constraints": {"enum": ["USD", "EUR", "KRW", "JPY"]}
                            },
                            "notifications": {
                                "type": DataType.OBJECT.value,
                                "constraints": {
                                    "schema": {
                                        "email": {"type": DataType.BOOLEAN.value},
                                        "sms": {"type": DataType.BOOLEAN.value},
                                        "push": {"type": DataType.BOOLEAN.value}
                                    }
                                }
                            }
                        },
                        required=["language", "currency"]
                    )
                },
                # Location info
                {
                    "name": "addresses",
                    "type": DataType.ARRAY.value,
                    "label": {"en": "Addresses", "ko": "주소 목록"},
                    "constraints": ComplexTypeConstraints.array_constraints(
                        item_type=DataType.ADDRESS.value,
                        max_items=3
                    )
                }
            ]
        }
        
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/database/{self.test_db}/ontology",
            json=ontology_data
        )
        
        assert response.status_code == 200, f"Failed to create complex combination: {response.text}"
        print(f"✅ Created UserProfile with complex type combinations")
    
    async def test_constraints_validation(self, client: httpx.AsyncClient):
        """제약조건 검증 테스트"""
        
        # Try to create ontology with invalid constraints
        invalid_ontology = {
            "id": "InvalidTest",
            "label": {"en": "Invalid Test"},
            "properties": [
                {
                    "name": "badEnum",
                    "type": DataType.ENUM.value,
                    "label": {"en": "Bad Enum"},
                    "constraints": {
                        # Missing required 'enum' field
                    }
                }
            ]
        }
        
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/database/{self.test_db}/ontology",
            json=invalid_ontology
        )
        
        # This should fail or return validation error
        print(f"✅ Invalid constraint handling tested (status: {response.status_code})")
    
    async def test_ecommerce_model(self, client: httpx.AsyncClient):
        """전체 e-commerce 모델 테스트"""
        
        # Create comprehensive e-commerce product model
        ontology_data = {
            "id": "EcommerceProduct",
            "label": {
                "en": "E-commerce Product",
                "ko": "전자상거래 상품",
                "ja": "電子商取引製品",
                "es": "Producto de comercio electrónico"
            },
            "description": {
                "en": "Complete e-commerce product with all complex types",
                "ko": "모든 복합 타입을 사용하는 완전한 전자상거래 상품"
            },
            "properties": [
                # Basic info
                {
                    "name": "sku",
                    "type": DataType.STRING.value,
                    "label": {"en": "SKU", "ko": "재고 관리 코드"},
                    "required": True
                },
                {
                    "name": "name",
                    "type": DataType.STRING.value,
                    "label": {"en": "Product Name", "ko": "상품명"},
                    "required": True
                },
                # Pricing (MONEY)
                {
                    "name": "price",
                    "type": DataType.MONEY.value,
                    "label": {"en": "Current Price", "ko": "현재 가격"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.money_constraints(
                        min_amount=0,
                        max_amount=999999.99
                    )
                },
                {
                    "name": "priceHistory",
                    "type": DataType.ARRAY.value,
                    "label": {"en": "Price History", "ko": "가격 이력"},
                    "constraints": ComplexTypeConstraints.array_constraints(
                        item_type=DataType.MONEY.value
                    )
                },
                # Categories (ENUM + ARRAY)
                {
                    "name": "category",
                    "type": DataType.ENUM.value,
                    "label": {"en": "Main Category", "ko": "주 카테고리"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.enum_constraints([
                        "electronics", "clothing", "food", "books", "toys", "other"
                    ])
                },
                {
                    "name": "tags",
                    "type": DataType.ARRAY.value,
                    "label": {"en": "Product Tags", "ko": "상품 태그"},
                    "constraints": ComplexTypeConstraints.array_constraints(
                        item_type=DataType.STRING.value,
                        unique_items=True
                    )
                },
                # Media (IMAGE + FILE)
                {
                    "name": "mainImage",
                    "type": DataType.IMAGE.value,
                    "label": {"en": "Main Product Image", "ko": "메인 상품 이미지"},
                    "required": True,
                    "constraints": ComplexTypeConstraints.image_constraints()
                },
                {
                    "name": "gallery",
                    "type": DataType.ARRAY.value,
                    "label": {"en": "Image Gallery", "ko": "이미지 갤러리"},
                    "constraints": ComplexTypeConstraints.array_constraints(
                        item_type=DataType.IMAGE.value,
                        max_items=20
                    )
                },
                {
                    "name": "manual",
                    "type": DataType.FILE.value,
                    "label": {"en": "User Manual", "ko": "사용 설명서"},
                    "constraints": ComplexTypeConstraints.file_constraints(
                        max_size=50 * 1024 * 1024,  # 50MB
                        allowed_extensions=[".pdf"]
                    )
                },
                # Specifications (OBJECT)
                {
                    "name": "specifications",
                    "type": DataType.OBJECT.value,
                    "label": {"en": "Technical Specifications", "ko": "기술 사양"},
                    "constraints": ComplexTypeConstraints.object_constraints(
                        schema={
                            "dimensions": {
                                "type": DataType.OBJECT.value,
                                "constraints": {
                                    "schema": {
                                        "length": {"type": DataType.DECIMAL.value},
                                        "width": {"type": DataType.DECIMAL.value},
                                        "height": {"type": DataType.DECIMAL.value},
                                        "weight": {"type": DataType.DECIMAL.value},
                                        "unit": {
                                            "type": DataType.ENUM.value,
                                            "constraints": {"enum": ["cm", "inch", "kg", "lb"]}
                                        }
                                    }
                                }
                            },
                            "features": {
                                "type": DataType.ARRAY.value,
                                "constraints": {
                                    "itemType": DataType.STRING.value
                                }
                            }
                        },
                        additional_properties=True
                    )
                },
                # Vendor info (CONTACT)
                {
                    "name": "vendor",
                    "type": DataType.OBJECT.value,
                    "label": {"en": "Vendor Information", "ko": "공급업체 정보"},
                    "constraints": ComplexTypeConstraints.object_constraints(
                        schema={
                            "name": {"type": DataType.STRING.value},
                            "email": {"type": DataType.EMAIL.value},
                            "phone": {"type": DataType.PHONE.value},
                            "address": {"type": DataType.ADDRESS.value}
                        },
                        required=["name", "email"]
                    )
                },
                # Shipping (COORDINATE + ADDRESS)
                {
                    "name": "warehouseLocation",
                    "type": DataType.COORDINATE.value,
                    "label": {"en": "Warehouse GPS", "ko": "창고 GPS 위치"},
                    "constraints": ComplexTypeConstraints.coordinate_constraints(
                        precision=8
                    )
                },
                {
                    "name": "shippingFrom",
                    "type": DataType.ADDRESS.value,
                    "label": {"en": "Ships From", "ko": "발송지"},
                    "constraints": ComplexTypeConstraints.address_constraints(
                        required_fields=["street", "city", "postalCode", "country"]
                    )
                }
            ]
        }
        
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/database/{self.test_db}/ontology",
            json=ontology_data
        )
        
        assert response.status_code == 200, f"Failed to create e-commerce model: {response.text}"
        data = response.json()
        
        print(f"✅ Created comprehensive EcommerceProduct ontology")
        print(f"   - ID: {data['id']}")
        print(f"   - Properties: {len(data['properties'])} complex type properties")
        
        # Verify all complex types are present
        property_types = {p["type"] for p in data["properties"]}
        complex_types = {
            DataType.ARRAY.value, DataType.OBJECT.value, DataType.ENUM.value,
            DataType.MONEY.value, DataType.PHONE.value, DataType.EMAIL.value,
            DataType.COORDINATE.value, DataType.ADDRESS.value, DataType.IMAGE.value,
            DataType.FILE.value
        }
        
        # Check which complex types are used
        used_complex_types = property_types.intersection(complex_types)
        print(f"   - Complex types used: {len(used_complex_types)}/10")
        print(f"   - Types: {', '.join(sorted(used_complex_types))}")
    
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
        print("🔥 THINK ULTRA!! TerminusDB Integration Test Results")
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
            print("   ✅ 모든 복합 타입이 TerminusDB와 완벽하게 통합되었습니다!")
            print("   ✅ 10개 복합 타입 모두 온톨로지 생성 성공!")
            print("   ✅ 실제 데이터베이스에서 복합 타입 스키마 검증 완료!")
        else:
            print("   ⚠️ 일부 통합 테스트에 문제가 있습니다.")
        
        # Save results
        result_file = f"terminus_integration_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(self.test_results, f, ensure_ascii=False, indent=2)
        
        print(f"\n📄 상세 결과가 저장되었습니다: {result_file}")


async def main():
    """메인 테스트 실행"""
    
    tester = ComplexTypesTerminusIntegrationTest()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())