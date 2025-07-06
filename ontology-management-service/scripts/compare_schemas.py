#!/usr/bin/env python3
"""
Schema Comparison Script for CI/CD
Compares generated schemas to detect structural differences
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
from deepdiff import DeepDiff


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Compare OMS schemas")
    parser.add_argument(
        "baseline_dir",
        type=str,
        help="Directory containing baseline schemas"
    )
    parser.add_argument(
        "compare_dir",
        type=str,
        help="Directory containing schemas to compare"
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "console"],
        default="console",
        help="Output format"
    )
    parser.add_argument(
        "--ignore-metadata",
        action="store_true",
        help="Ignore metadata fields like timestamps"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error on any difference"
    )
    return parser.parse_args()


def load_graphql_schema(file_path: Path) -> Dict[str, Any]:
    """Load and parse GraphQL schema"""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Basic parsing to extract types and fields
    types = {}
    current_type = None
    
    for line in content.split('\n'):
        line = line.strip()
        
        if line.startswith('type ') and '{' in line:
            type_name = line.split()[1].rstrip('{').strip()
            current_type = type_name
            types[type_name] = {
                'fields': {},
                'kind': 'type'
            }
        elif line.startswith('input ') and '{' in line:
            type_name = line.split()[1].rstrip('{').strip()
            current_type = type_name
            types[type_name] = {
                'fields': {},
                'kind': 'input'
            }
        elif line.startswith('enum ') and '{' in line:
            type_name = line.split()[1].rstrip('{').strip()
            current_type = type_name
            types[type_name] = {
                'values': [],
                'kind': 'enum'
            }
        elif current_type and ':' in line and not line.startswith('#'):
            # Parse field
            parts = line.split(':')
            if len(parts) == 2:
                field_name = parts[0].strip()
                field_type = parts[1].strip()
                if types[current_type]['kind'] in ['type', 'input']:
                    types[current_type]['fields'][field_name] = field_type
        elif current_type and line == '}':
            current_type = None
    
    return types


def load_openapi_schema(file_path: Path) -> Dict[str, Any]:
    """Load OpenAPI schema"""
    with open(file_path, 'r') as f:
        return json.load(f)


def compare_graphql_schemas(
    baseline: Dict[str, Any],
    compare: Dict[str, Any],
    ignore_metadata: bool = False
) -> Dict[str, Any]:
    """Compare GraphQL schemas"""
    diff_result = {
        'structural_changes': 0,
        'changes': [],
        'added_types': [],
        'removed_types': [],
        'modified_types': []
    }
    
    # Check for added/removed types
    baseline_types = set(baseline.keys())
    compare_types = set(compare.keys())
    
    added = compare_types - baseline_types
    removed = baseline_types - compare_types
    
    for type_name in added:
        diff_result['added_types'].append(type_name)
        diff_result['changes'].append(f"Added type: {type_name}")
        diff_result['structural_changes'] += 1
    
    for type_name in removed:
        diff_result['removed_types'].append(type_name)
        diff_result['changes'].append(f"Removed type: {type_name}")
        diff_result['structural_changes'] += 1
    
    # Check for modified types
    for type_name in baseline_types & compare_types:
        baseline_type = baseline[type_name]
        compare_type = compare[type_name]
        
        if baseline_type['kind'] != compare_type['kind']:
            diff_result['changes'].append(f"Type kind changed: {type_name}")
            diff_result['structural_changes'] += 1
            continue
        
        if baseline_type['kind'] in ['type', 'input']:
            # Compare fields
            baseline_fields = baseline_type.get('fields', {})
            compare_fields = compare_type.get('fields', {})
            
            added_fields = set(compare_fields.keys()) - set(baseline_fields.keys())
            removed_fields = set(baseline_fields.keys()) - set(compare_fields.keys())
            
            for field in added_fields:
                diff_result['changes'].append(f"Added field: {type_name}.{field}")
                diff_result['structural_changes'] += 1
            
            for field in removed_fields:
                diff_result['changes'].append(f"Removed field: {type_name}.{field}")
                diff_result['structural_changes'] += 1
            
            # Check field type changes
            for field in set(baseline_fields.keys()) & set(compare_fields.keys()):
                if baseline_fields[field] != compare_fields[field]:
                    diff_result['changes'].append(
                        f"Field type changed: {type_name}.{field} "
                        f"({baseline_fields[field]} -> {compare_fields[field]})"
                    )
                    diff_result['structural_changes'] += 1
    
    return diff_result


def compare_openapi_schemas(
    baseline: Dict[str, Any],
    compare: Dict[str, Any],
    ignore_metadata: bool = False
) -> Dict[str, Any]:
    """Compare OpenAPI schemas"""
    diff_result = {
        'structural_changes': 0,
        'changes': [],
        'added_paths': [],
        'removed_paths': [],
        'modified_paths': []
    }
    
    # Ignore certain fields if requested
    exclude_paths = []
    if ignore_metadata:
        exclude_paths = [
            "root['info']['version']",
            "root['servers']"
        ]
    
    # Deep comparison
    diff = DeepDiff(
        baseline,
        compare,
        exclude_paths=exclude_paths,
        ignore_order=True
    )
    
    # Process differences
    if 'dictionary_item_added' in diff:
        for path in diff['dictionary_item_added']:
            if 'paths' in str(path):
                path_name = str(path).split("'")[1]
                diff_result['added_paths'].append(path_name)
                diff_result['changes'].append(f"Added path: {path_name}")
                diff_result['structural_changes'] += 1
            elif 'schemas' in str(path):
                schema_name = str(path).split("'")[-2]
                diff_result['changes'].append(f"Added schema: {schema_name}")
                diff_result['structural_changes'] += 1
    
    if 'dictionary_item_removed' in diff:
        for path in diff['dictionary_item_removed']:
            if 'paths' in str(path):
                path_name = str(path).split("'")[1]
                diff_result['removed_paths'].append(path_name)
                diff_result['changes'].append(f"Removed path: {path_name}")
                diff_result['structural_changes'] += 1
            elif 'schemas' in str(path):
                schema_name = str(path).split("'")[-2]
                diff_result['changes'].append(f"Removed schema: {schema_name}")
                diff_result['structural_changes'] += 1
    
    if 'values_changed' in diff:
        for path, change in diff['values_changed'].items():
            if 'properties' in str(path) or 'required' in str(path):
                diff_result['changes'].append(f"Schema modified: {path}")
                diff_result['structural_changes'] += 1
    
    return diff_result


def format_output(results: Dict[str, Any], format: str) -> str:
    """Format comparison results"""
    if format == "json":
        return json.dumps(results, indent=2)
    
    elif format == "markdown":
        output = "# Schema Comparison Report\n\n"
        
        if 'graphql' in results:
            output += "## GraphQL Schema\n\n"
            graphql = results['graphql']
            output += f"- Structural changes: {graphql['structural_changes']}\n"
            if graphql['changes']:
                output += "\n### Changes:\n"
                for change in graphql['changes']:
                    output += f"- {change}\n"
            output += "\n"
        
        if 'openapi' in results:
            output += "## OpenAPI Schema\n\n"
            openapi = results['openapi']
            output += f"- Structural changes: {openapi['structural_changes']}\n"
            if openapi['changes']:
                output += "\n### Changes:\n"
                for change in openapi['changes']:
                    output += f"- {change}\n"
        
        return output
    
    else:  # console
        output = "\n=== Schema Comparison Results ===\n"
        
        if 'graphql' in results:
            graphql = results['graphql']
            output += f"\nGraphQL: {graphql['structural_changes']} structural changes"
            if graphql['changes']:
                output += "\n" + "\n".join(f"  - {c}" for c in graphql['changes'][:5])
                if len(graphql['changes']) > 5:
                    output += f"\n  ... and {len(graphql['changes']) - 5} more"
        
        if 'openapi' in results:
            openapi = results['openapi']
            output += f"\n\nOpenAPI: {openapi['structural_changes']} structural changes"
            if openapi['changes']:
                output += "\n" + "\n".join(f"  - {c}" for c in openapi['changes'][:5])
                if len(openapi['changes']) > 5:
                    output += f"\n  ... and {len(openapi['changes']) - 5} more"
        
        return output


def main():
    """Main execution"""
    args = parse_args()
    
    baseline_dir = Path(args.baseline_dir)
    compare_dir = Path(args.compare_dir)
    
    if not baseline_dir.exists() or not compare_dir.exists():
        print("Error: One or both directories do not exist", file=sys.stderr)
        sys.exit(1)
    
    results = {}
    has_changes = False
    
    # Compare GraphQL schemas
    baseline_graphql = baseline_dir / "schema.graphql"
    compare_graphql = compare_dir / "schema.graphql"
    
    if baseline_graphql.exists() and compare_graphql.exists():
        baseline_types = load_graphql_schema(baseline_graphql)
        compare_types = load_graphql_schema(compare_graphql)
        
        results['graphql'] = compare_graphql_schemas(
            baseline_types,
            compare_types,
            args.ignore_metadata
        )
        
        if results['graphql']['structural_changes'] > 0:
            has_changes = True
    
    # Compare OpenAPI schemas
    baseline_openapi = baseline_dir / "openapi.json"
    compare_openapi = compare_dir / "openapi.json"
    
    if baseline_openapi.exists() and compare_openapi.exists():
        baseline_spec = load_openapi_schema(baseline_openapi)
        compare_spec = load_openapi_schema(compare_openapi)
        
        results['openapi'] = compare_openapi_schemas(
            baseline_spec,
            compare_spec,
            args.ignore_metadata
        )
        
        if results['openapi']['structural_changes'] > 0:
            has_changes = True
    
    # Add performance data if available
    baseline_summary = baseline_dir / "generation_summary.json"
    compare_summary = compare_dir / "generation_summary.json"
    
    if baseline_summary.exists() and compare_summary.exists():
        with open(baseline_summary) as f:
            baseline_perf = json.load(f)
        with open(compare_summary) as f:
            compare_perf = json.load(f)
        
        results['performance'] = {
            'graphql_ms': compare_perf.get('results', {}).get('graphql', {}).get('generation_time_ms', 0),
            'openapi_ms': compare_perf.get('results', {}).get('openapi', {}).get('generation_time_ms', 0)
        }
    
    # Output results
    print(format_output(results, args.format))
    
    # Exit with error if strict mode and changes detected
    if args.strict and has_changes:
        sys.exit(1)


if __name__ == "__main__":
    main()