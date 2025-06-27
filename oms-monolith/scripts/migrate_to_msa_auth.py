#!/usr/bin/env python3
"""
Migration script to update IAM integration to MSA architecture
Fixes circular dependencies and updates imports
"""
import os
import re
from pathlib import Path
from typing import List, Tuple


def find_files_with_imports(root_dir: Path, patterns: List[str]) -> List[Path]:
    """Find all Python files containing specific import patterns"""
    files = []
    for pattern in patterns:
        for file in root_dir.rglob("*.py"):
            if file.is_file():
                try:
                    content = file.read_text()
                    if re.search(pattern, content):
                        files.append(file)
                except Exception as e:
                    print(f"Error reading {file}: {e}")
    return list(set(files))


def update_imports(file_path: Path, replacements: List[Tuple[str, str]]):
    """Update imports in a file"""
    try:
        content = file_path.read_text()
        original = content
        
        for old, new in replacements:
            content = re.sub(old, new, content, flags=re.MULTILINE)
        
        if content != original:
            file_path.write_text(content)
            print(f"✅ Updated: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"❌ Error updating {file_path}: {e}")
        return False


def main():
    """Run the migration"""
    root_dir = Path(__file__).parent.parent
    
    print("🔍 Finding files to update...")
    
    # Define import patterns to find
    patterns = [
        r"from core\.iam\.iam_integration import",
        r"import core\.iam\.iam_integration",
        r"get_iam_integration\(\)"
    ]
    
    files = find_files_with_imports(root_dir, patterns)
    print(f"Found {len(files)} files to check")
    
    # Define replacements
    replacements = [
        # Update IAM integration imports
        (
            r"from core\.iam\.iam_integration import get_iam_integration",
            "from core.iam.iam_integration_refactored import get_iam_integration"
        ),
        (
            r"from core\.iam\.iam_integration import IAMIntegration",
            "from core.iam.iam_integration_refactored import IAMIntegration"
        ),
        # IAMScope should now come from shared contracts
        (
            r"from core\.iam\.iam_integration import IAMScope",
            "from shared.iam_contracts import IAMScope"
        ),
    ]
    
    # Update files
    updated_count = 0
    for file in files:
        # Skip the old file itself
        if "iam_integration.py" in str(file) and "refactored" not in str(file):
            continue
        
        if update_imports(file, replacements):
            updated_count += 1
    
    print(f"\n✨ Updated {updated_count} files")
    
    # Create environment template
    env_template = """
# MSA Authentication Configuration
USE_MSA_AUTH=true
IAM_SERVICE_URL=http://user-service:8000
IAM_JWKS_URL=http://user-service:8000/.well-known/jwks.json
IAM_SERVICE_ID=oms-service
IAM_SERVICE_SECRET=your-service-secret
JWT_ISSUER=iam.company
JWT_AUDIENCE=oms

# Service Discovery (optional)
SERVICE_DISCOVERY_ENABLED=false
CONSUL_URL=http://consul:8500

# Circuit Breaker
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60

# Cache Configuration
AUTH_CACHE_TTL=300
REDIS_URL=redis://localhost:6379/0
"""
    
    env_file = root_dir / ".env.msa.example"
    env_file.write_text(env_template.strip())
    print(f"\n📄 Created environment template: {env_file}")
    
    print("\n🎯 Next steps:")
    print("1. Review the changes")
    print("2. Update your .env file with MSA configuration")
    print("3. Test the integration with: pytest tests/test_iam_msa_integration.py")
    print("4. Remove the old iam_integration.py file once everything works")


if __name__ == "__main__":
    main()