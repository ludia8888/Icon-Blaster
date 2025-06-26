"""수정된 SchemaService 테스트"""
import asyncio
import sys
sys.path.append('/Users/sihyun/Desktop/ARRAKIS/SPICE/oms-monolith')

from core.schema.service_fixed import SchemaService

async def test_fixed_service():
    print("🧪 Testing Fixed SchemaService")
    
    # 서비스 생성 및 초기화
    service = SchemaService(tdb_endpoint="http://localhost:6363")
    await service.initialize()
    
    # 1. 목록 조회 테스트
    print("\n1️⃣ Testing list_object_types...")
    object_types = await service.list_object_types()
    print(f"Found {len(object_types)} object types")
    for ot in object_types:
        print(f"  - {ot.get('name', 'Unknown')}: {ot.get('description', 'No description')}")
    
    # 2. 새 ObjectType 생성 테스트
    print("\n2️⃣ Testing create_object_type...")
    from models.domain import ObjectTypeCreate
    
    new_type = ObjectTypeCreate(
        name="Employee",
        display_name="Employee Type",
        description="An employee in the organization"
    )
    
    try:
        created = await service.create_object_type("main", new_type)
        print(f"✅ Created: {created.name}")
    except Exception as e:
        print(f"❌ Creation failed: {e}")
    
    # 3. 다시 목록 조회
    print("\n3️⃣ Verifying creation...")
    object_types = await service.list_object_types()
    print(f"Now have {len(object_types)} object types")
    
    print("\n🎉 Test completed!")

if __name__ == "__main__":
    asyncio.run(test_fixed_service())