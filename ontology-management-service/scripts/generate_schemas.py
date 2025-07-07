#!/usr/bin/env python3
"""
Schema Generation Script for CI/CD
Generates GraphQL and OpenAPI schemas for smoke testing
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from core.api.schema_generator import GraphQLSchemaGenerator, OpenAPISchemaGenerator
from models.domain import ObjectType, LinkType, Property, Status
from core.schema.registry import schema_registry


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Generate OMS schemas")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate schemas without persisting to database"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./generated_schemas",
        help="Output directory for generated schemas"
    )
    parser.add_argument(
        "--format",
        choices=["all", "graphql", "openapi"],
        default="all",
        help="Schema format to generate"
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include inactive object types"
    )
    parser.add_argument(
        "--measure-performance",
        action="store_true",
        help="Measure and report generation performance"
    )
    return parser.parse_args()


async def load_schema_data(dry_run: bool = False) -> tuple[list[ObjectType], list[LinkType]]:
    """Load schema data from registry or use test data"""
    if dry_run:
        # Use test data for dry run
        from datetime import datetime
        
        object_types = [
            ObjectType(
                id="User",
                name="User",
                display_name="User",
                status=Status.ACTIVE,
                properties=[
                    Property(
                        id="user_id",
                        object_type_id="User",
                        name="id",
                        display_name="ID",
                        data_type_id="string",
                        is_required=True,
                        is_primary_key=True,
                        visibility="VISIBLE",
                        version_hash="test",
                        created_at=datetime.utcnow(),
                        modified_at=datetime.utcnow()
                    ),
                    Property(
                        id="user_name",
                        object_type_id="User",
                        name="name",
                        display_name="Name",
                        data_type_id="string",
                        is_required=True,
                        visibility="VISIBLE",
                        version_hash="test",
                        created_at=datetime.utcnow(),
                        modified_at=datetime.utcnow()
                    )
                ],
                version_hash="test",
                created_by="system",
                created_at=datetime.utcnow(),
                modified_by="system",
                modified_at=datetime.utcnow()
            ),
            ObjectType(
                id="Post",
                name="Post",
                display_name="Post",
                status=Status.ACTIVE,
                properties=[
                    Property(
                        id="post_id",
                        object_type_id="Post",
                        name="id",
                        display_name="ID",
                        data_type_id="string",
                        is_required=True,
                        is_primary_key=True,
                        visibility="VISIBLE",
                        version_hash="test",
                        created_at=datetime.utcnow(),
                        modified_at=datetime.utcnow()
                    ),
                    Property(
                        id="post_title",
                        object_type_id="Post",
                        name="title",
                        display_name="Title",
                        data_type_id="string",
                        is_required=True,
                        visibility="VISIBLE",
                        version_hash="test",
                        created_at=datetime.utcnow(),
                        modified_at=datetime.utcnow()
                    )
                ],
                version_hash="test",
                created_by="system",
                created_at=datetime.utcnow(),
                modified_by="system",
                modified_at=datetime.utcnow()
            )
        ]
        
        link_types = [
            LinkType(
                id="user_posts",
                name="posts",
                displayName="User Posts",
                fromTypeId="User",
                toTypeId="Post",
                cardinality="ONE_TO_MANY",
                directionality="UNIDIRECTIONAL",
                cascadeDelete=False,
                isRequired=False,
                status=Status.ACTIVE,
                versionHash="test",
                createdBy="system",
                createdAt=datetime.utcnow(),
                modifiedBy="system",
                modifiedAt=datetime.utcnow()
            )
        ]
        
        return object_types, link_types
    else:
        # Load from actual registry
        object_types = await schema_registry.list_object_types()
        link_types = await schema_registry.list_link_types()
        return object_types, link_types


def generate_graphql(
    object_types: list[ObjectType],
    link_types: list[LinkType],
    output_dir: Path
) -> Dict[str, Any]:
    """Generate GraphQL schema"""
    start_time = time.time()
    
    generator = GraphQLSchemaGenerator()
    schema = generator.generate_complete_schema(object_types, link_types)
    
    # Save schema
    graphql_file = output_dir / "schema.graphql"
    with open(graphql_file, "w") as f:
        f.write(schema)
    
    # Save metadata
    metadata = generator.export_schema_metadata()
    metadata_file = output_dir / "graphql_metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)
    
    end_time = time.time()
    
    return {
        "file": str(graphql_file),
        "metadata_file": str(metadata_file),
        "generation_time_ms": round((end_time - start_time) * 1000, 2),
        "size_bytes": len(schema),
        "object_types": len(object_types),
        "link_types": len(link_types),
        "link_fields": sum(len(fields) for fields in generator.link_fields.values())
    }


def generate_openapi(
    object_types: list[ObjectType],
    link_types: list[LinkType],
    output_dir: Path
) -> Dict[str, Any]:
    """Generate OpenAPI schema"""
    start_time = time.time()
    
    generator = OpenAPISchemaGenerator()
    spec = generator.generate_complete_spec(
        object_types,
        link_types,
        {
            "title": "OMS API",
            "version": "1.0.0",
            "description": "Ontology Management Service API"
        }
    )
    
    # Save spec
    openapi_file = output_dir / "openapi.json"
    with open(openapi_file, "w") as f:
        json.dump(spec, f, indent=2)
    
    end_time = time.time()
    
    return {
        "file": str(openapi_file),
        "generation_time_ms": round((end_time - start_time) * 1000, 2),
        "size_bytes": len(json.dumps(spec)),
        "paths": len(spec.get("paths", {})),
        "schemas": len(spec.get("components", {}).get("schemas", {}))
    }


async def main():
    """Main execution"""
    args = parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load schema data
    print(f"Loading schema data (dry_run={args.dry_run})...")
    object_types, link_types = await load_schema_data(args.dry_run)
    
    # Filter by status if not including inactive
    if not args.include_inactive:
        object_types = [ot for ot in object_types if ot.status == Status.ACTIVE]
        link_types = [lt for lt in link_types if lt.status == Status.ACTIVE]
    
    print(f"Loaded {len(object_types)} object types and {len(link_types)} link types")
    
    results = {}
    
    # Generate schemas based on format
    if args.format in ["all", "graphql"]:
        print("Generating GraphQL schema...")
        results["graphql"] = generate_graphql(object_types, link_types, output_dir)
        print(f"✅ GraphQL schema generated: {results['graphql']['file']}")
    
    if args.format in ["all", "openapi"]:
        print("Generating OpenAPI schema...")
        results["openapi"] = generate_openapi(object_types, link_types, output_dir)
        print(f"✅ OpenAPI schema generated: {results['openapi']['file']}")
    
    # Save summary
    summary_file = output_dir / "generation_summary.json"
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": args.dry_run,
        "object_types_count": len(object_types),
        "link_types_count": len(link_types),
        "results": results
    }
    
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n📋 Summary saved to: {summary_file}")
    
    # Display performance metrics if requested
    if args.measure_performance:
        print("\n⏱️  Performance Metrics:")
        if "graphql" in results:
            print(f"  GraphQL: {results['graphql']['generation_time_ms']}ms")
        if "openapi" in results:
            print(f"  OpenAPI: {results['openapi']['generation_time_ms']}ms")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())