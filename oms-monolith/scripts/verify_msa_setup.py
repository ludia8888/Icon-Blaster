#!/usr/bin/env python3
"""
MSA Setup Verification Script
Verifies that all components are properly configured for MSA integration
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple


class MSAVerifier:
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.user_service_dir = self.base_dir.parent / "user-service"
        self.audit_service_dir = self.base_dir.parent / "audit-service"
        self.issues: List[str] = []
        self.warnings: List[str] = []
        
    def verify_all(self) -> bool:
        """Run all verification checks"""
        print("🔍 MSA Setup Verification")
        print("=" * 60)
        
        checks = [
            ("Directory Structure", self.check_directories),
            ("Docker Configuration", self.check_docker_config),
            ("Service Dependencies", self.check_dependencies),
            ("Environment Configuration", self.check_env_config),
            ("Integration Points", self.check_integration_points),
        ]
        
        all_passed = True
        
        for check_name, check_func in checks:
            print(f"\n📋 Checking {check_name}...")
            passed = check_func()
            if passed:
                print(f"✅ {check_name} - PASSED")
            else:
                print(f"❌ {check_name} - FAILED")
                all_passed = False
                
        # Summary
        print("\n" + "=" * 60)
        print("📊 VERIFICATION SUMMARY")
        print("=" * 60)
        
        if self.issues:
            print("\n❌ Issues found:")
            for issue in self.issues:
                print(f"  - {issue}")
                
        if self.warnings:
            print("\n⚠️  Warnings:")
            for warning in self.warnings:
                print(f"  - {warning}")
                
        if all_passed and not self.issues:
            print("\n✅ All checks passed! MSA setup is ready.")
            return True
        else:
            print("\n❌ MSA setup has issues that need to be resolved.")
            return False
            
    def check_directories(self) -> bool:
        """Check if all service directories exist"""
        dirs_to_check = [
            (self.base_dir, "OMS Service"),
            (self.user_service_dir, "User Service"),
            (self.audit_service_dir, "Audit Service"),
        ]
        
        all_exist = True
        for dir_path, service_name in dirs_to_check:
            if dir_path.exists():
                print(f"  ✓ {service_name} directory exists: {dir_path}")
            else:
                self.issues.append(f"{service_name} directory not found: {dir_path}")
                all_exist = False
                
        return all_exist
        
    def check_docker_config(self) -> bool:
        """Check Docker configuration files"""
        docker_files = [
            (self.base_dir / "docker-compose.integration.yml", "Integration docker-compose"),
            (self.base_dir / "Dockerfile", "OMS Dockerfile"),
            (self.user_service_dir / "Dockerfile", "User Service Dockerfile"),
            (self.audit_service_dir / "Dockerfile", "Audit Service Dockerfile"),
        ]
        
        all_exist = True
        for file_path, description in docker_files:
            if file_path.exists():
                print(f"  ✓ {description} exists")
            else:
                self.issues.append(f"{description} not found: {file_path}")
                all_exist = False
                
        return all_exist
        
    def check_dependencies(self) -> bool:
        """Check service dependencies"""
        passed = True
        
        # Check OMS dependencies
        oms_pyproject = self.base_dir / "pyproject.toml"
        if oms_pyproject.exists():
            content = oms_pyproject.read_text()
            required_deps = ["nats-py", "asyncpg", "httpx", "fastapi"]
            
            for dep in required_deps:
                if dep in content:
                    print(f"  ✓ OMS has {dep} dependency")
                else:
                    self.warnings.append(f"OMS might be missing {dep} dependency")
        else:
            self.issues.append("OMS pyproject.toml not found")
            passed = False
            
        return passed
        
    def check_env_config(self) -> bool:
        """Check environment configuration"""
        docker_compose = self.base_dir / "docker-compose.integration.yml"
        
        if not docker_compose.exists():
            self.issues.append("docker-compose.integration.yml not found")
            return False
            
        content = docker_compose.read_text()
        
        # Check critical environment variables
        env_vars = [
            "JWT_SECRET",
            "NATS_URL",
            "USER_SERVICE_URL",
            "USE_MSA_AUTH",
            "DATABASE_URL",
        ]
        
        for var in env_vars:
            if var in content:
                print(f"  ✓ {var} is configured")
            else:
                self.warnings.append(f"{var} might not be configured in docker-compose")
                
        return True
        
    def check_integration_points(self) -> bool:
        """Check integration points between services"""
        integration_files = [
            (self.base_dir / "core" / "integrations" / "user_service_client.py", "User Service Client"),
            (self.base_dir / "core" / "event_publisher" / "nats_publisher.py", "NATS Publisher"),
            (self.base_dir / "middleware" / "auth_middleware.py", "Auth Middleware"),
        ]
        
        all_exist = True
        for file_path, description in integration_files:
            if file_path.exists():
                print(f"  ✓ {description} exists")
            else:
                self.warnings.append(f"{description} not found: {file_path}")
                
        return all_exist


def main():
    verifier = MSAVerifier()
    success = verifier.verify_all()
    
    # Provide next steps
    print("\n" + "=" * 60)
    print("📝 NEXT STEPS")
    print("=" * 60)
    
    if success:
        print("\n1. Start the MSA environment:")
        print("   ./scripts/run_msa_integration_test.sh")
        print("\n2. Or manually:")
        print("   docker-compose -f docker-compose.integration.yml up -d")
        print("\n3. Run integration tests:")
        print("   python tests/test_msa_integration.py")
    else:
        print("\nPlease fix the issues above before running the integration tests.")
        
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()