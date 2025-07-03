#!/usr/bin/env python3
"""Check if core modules can be imported (syntax check)"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def check_import(module_path, name):
    """Try to import a module and report result"""
    try:
        exec(f"import {module_path}")
        print(f"✅ {name}: OK")
        return True
    except SyntaxError as e:
        print(f"❌ {name}: Syntax Error - {e}")
        return False
    except ModuleNotFoundError as e:
        # This is expected without dependencies installed
        print(f"⚠️  {name}: Missing dependency - {e}")
        return True  # Syntax is OK, just missing deps
    except Exception as e:
        print(f"❌ {name}: Error - {type(e).__name__}: {e}")
        return False

def main():
    """Check all core modules"""
    print("Checking core modules for syntax errors...")
    print("=" * 60)
    
    modules = [
        ("shared.database.sqlite_connector", "SQLiteConnector"),
        ("core.events.unified_publisher", "Unified Publisher"),
        ("core.events.backends.audit_backend", "Audit Backend"),
        ("core.audit.audit_service", "Audit Service"),
        ("core.audit.audit_database", "Audit Database"),
        ("core.issue_tracking.issue_database", "Issue Database"),
        ("core.versioning.version_service", "Version Service"),
        ("core.idempotent.consumer_service", "Consumer Service"),
        ("database.clients.unified_http_client", "HTTP Client"),
    ]
    
    results = []
    for module, name in modules:
        result = check_import(module, name)
        results.append(result)
    
    print("\n" + "=" * 60)
    syntax_ok = all(results)
    
    if syntax_ok:
        print("✅ All modules have valid syntax!")
        print("\nNote: Some modules show missing dependencies (⚠️)")
        print("This is expected without packages installed.")
    else:
        print("❌ Some modules have syntax errors!")
        print("Please fix the errors marked with ❌ above.")
    
    return syntax_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)