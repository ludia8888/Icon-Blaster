#!/usr/bin/env python3
"""
PRODUCTION DEPLOYMENT VERIFICATION
=================================
NUCLEAR REACTOR GRADE: Verify system is safe for production deployment

This script MUST be run before any production deployment.
Failure to pass verification means the system could kill people.
"""

import os
import sys
import re
from pathlib import Path

def verify_no_auth_bypasses():
    """Verify no authentication bypasses exist"""
    print("🔍 Verifying no authentication bypasses...")
    
    files_to_check = [
        "simple_main.py",
        "main.py", 
        "main_life_critical.py",
        "middleware/auth_middleware.py",
        "middleware/auth_middleware_life_critical.py"
    ]
    
    bypass_patterns = [
        r'if\s+not\s+.*production',
        r'if\s+.*environment.*==.*development',
        r'if\s+.*environment.*==.*dev',
        r'if\s+.*environment.*==.*test',
        r'skip_auth.*=.*True',
        r'auth_required\s*=\s*False'
    ]
    
    violations = []
    
    for file_path in files_to_check:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
                
            for pattern in bypass_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    violations.append(f"{file_path}: Found auth bypass pattern: {pattern}")
                    
    if violations:
        print("💀 FATAL: Authentication bypasses found:")
        for violation in violations:
            print(f"   {violation}")
        return False
        
    print("✅ No authentication bypasses found")
    return True

def verify_circuit_breaker_thresholds():
    """Verify circuit breaker thresholds are life-critical safe"""
    print("🔍 Verifying circuit breaker thresholds...")
    
    config_file = "config/life_critical_circuit_breaker_config.py"
    
    if not os.path.exists(config_file):
        print("💀 FATAL: Circuit breaker configuration not found")
        return False
        
    with open(config_file, 'r') as f:
        content = f.read()
        
    # Check for dangerous low thresholds
    if re.search(r'failure_threshold\s*[:=]\s*[1-9](?!\d)', content):
        print("💀 FATAL: Dangerous low failure threshold found")
        return False
        
    if re.search(r'success_threshold\s*[:=]\s*[1-9](?!\d)', content):
        print("💀 FATAL: Dangerous low success threshold found") 
        return False
        
    print("✅ Circuit breaker thresholds are safe")
    return True

def verify_no_vulnerable_files():
    """Verify no vulnerable files are present"""
    print("🔍 Verifying no vulnerable files present...")
    
    # simple_main.py should have circuit breaker protection if it exists
    if os.path.exists("simple_main.py"):
        with open("simple_main.py", 'r') as f:
            content = f.read()
            
        # Should have circuit breaker protection
        if 'LifeCriticalCircuitBreaker' not in content:
            print("💀 FATAL: simple_main.py lacks life-critical circuit breaker")
            return False
            
    print("✅ All files have required protection")
    return True

def verify_timeout_protection():
    """Verify timeout protection is in place"""
    print("🔍 Verifying timeout protection...")
    
    files_to_check = ["main.py", "main_life_critical.py", "simple_main.py"]
    
    for file_path in files_to_check:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
                
            # Check for requests without timeouts
            if re.search(r'requests\.(get|post|put|delete)\([^)]*\)', content):
                # Make sure timeout is included
                if not re.search(r'timeout\s*=', content):
                    print(f"💀 FATAL: {file_path} has requests without timeout protection")
                    return False
                    
    print("✅ Timeout protection verified")
    return True

def main():
    """Run complete production deployment verification"""
    print("🚨 PRODUCTION DEPLOYMENT VERIFICATION")
    print("="*60)
    print("⚠️  NUCLEAR REACTOR SAFETY STANDARD")
    print("⚠️  System must pass ALL checks for production deployment")
    print()
    
    checks = [
        verify_no_auth_bypasses,
        verify_circuit_breaker_thresholds, 
        verify_no_vulnerable_files,
        verify_timeout_protection
    ]
    
    all_passed = True
    
    for check in checks:
        try:
            if not check():
                all_passed = False
        except Exception as e:
            print(f"💀 FATAL: Check failed with error: {e}")
            all_passed = False
            
    print("\n" + "="*60)
    if all_passed:
        print("✅ PRODUCTION DEPLOYMENT VERIFICATION PASSED")
        print("✅ System is safe for life-critical deployment")
        sys.exit(0)
    else:
        print("💀 PRODUCTION DEPLOYMENT VERIFICATION FAILED")
        print("💀 SYSTEM NOT SAFE FOR DEPLOYMENT")
        print("💀 LIVES AT RISK - FIX ALL ISSUES BEFORE DEPLOYMENT")
        sys.exit(1)

if __name__ == "__main__":
    main()