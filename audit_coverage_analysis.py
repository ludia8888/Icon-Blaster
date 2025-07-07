#!/usr/bin/env python3
"""
User Service Audit Coverage Analysis
User Service의 모든 감사 대상 이벤트가 완전히 커버되고 있는지 분석
"""
import os
import re
from typing import Dict, List, Set


def analyze_audit_coverage():
    """User Service의 감사 커버리지 분석"""
    print("Analyzing User Service Audit Coverage...")
    
    # User Service 루트 경로
    user_service_path = "/Users/isihyeon/Desktop/Arrakis-Project/user-service/src"
    
    # 1. 모든 감사 대상 이벤트 식별
    audit_events = identify_audit_events(user_service_path)
    
    # 2. 현재 감사되고 있는 이벤트 분석
    audited_events = analyze_current_audit_calls(user_service_path)
    
    # 3. 누락된 감사 이벤트 식별
    missing_events = identify_missing_audit_events(audit_events, audited_events)
    
    # 4. 보고서 생성
    generate_audit_coverage_report(audit_events, audited_events, missing_events)


def identify_audit_events(base_path: str) -> Dict[str, List[Dict]]:
    """감사 대상 이벤트 식별"""
    events = {
        "authentication": [],
        "user_management": [],
        "authorization": [],
        "security": [],
        "administrative": [],
        "data_access": []
    }
    
    # API 라우터 파일들 분석
    router_files = [
        "api/auth_router.py",
        "api/registration_router.py", 
        "api/account_router.py",
        "api/mfa_router.py",
        "api/iam_adapter.py",
        "api/internal.py"
    ]
    
    for router_file in router_files:
        file_path = os.path.join(base_path, router_file)
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
                
            # 엔드포인트 패턴 찾기
            endpoint_patterns = re.findall(r'@router\.(post|get|put|delete|patch)\(["\']([^"\']+)["\']', content)
            function_patterns = re.findall(r'async def ([a-zA-Z_][a-zA-Z0-9_]*)\(', content)
            
            for method, endpoint in endpoint_patterns:
                for func_name in function_patterns:
                    if endpoint in content and func_name in content:
                        event_info = {
                            "file": router_file,
                            "endpoint": f"{method.upper()} {endpoint}",
                            "function": func_name,
                            "category": categorize_event(endpoint, func_name),
                            "risk_level": assess_risk_level(endpoint, func_name),
                            "audit_required": is_audit_required(endpoint, func_name)
                        }
                        
                        category = event_info["category"]
                        if category in events:
                            events[category].append(event_info)
                        break
    
    # 서비스 메서드 분석
    service_files = [
        "services/user_service.py",
        "services/auth_service.py", 
        "services/mfa_service.py"
    ]
    
    for service_file in service_files:
        file_path = os.path.join(base_path, service_file)
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
                
            # 서비스 메서드 패턴 찾기
            method_patterns = re.findall(r'async def ([a-zA-Z_][a-zA-Z0-9_]*)\(', content)
            
            for method_name in method_patterns:
                if should_audit_service_method(method_name):
                    event_info = {
                        "file": service_file,
                        "method": method_name,
                        "category": categorize_service_method(method_name),
                        "risk_level": assess_service_risk_level(method_name),
                        "audit_required": True
                    }
                    
                    category = event_info["category"]
                    if category in events:
                        events[category].append(event_info)
    
    return events


def analyze_current_audit_calls(base_path: str) -> Dict[str, List[str]]:
    """현재 감사되고 있는 이벤트 분석"""
    audited_events = {
        "user_service": [],
        "auth_service": [],
        "mfa_service": [],
        "routers": []
    }
    
    # 감사 호출 패턴
    audit_patterns = [
        r'await self\.audit_service\.log_([a-zA-Z_]+)\(',
        r'await audit_service\.log_([a-zA-Z_]+)\(',
        r'log_([a-zA-Z_]+)\('
    ]
    
    # 모든 Python 파일 검사
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, base_path)
                
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    for pattern in audit_patterns:
                        matches = re.findall(pattern, content)
                        for match in matches:
                            service_type = determine_service_type(relative_path)
                            if service_type in audited_events:
                                audited_events[service_type].append({
                                    "file": relative_path,
                                    "audit_method": f"log_{match}",
                                    "context": extract_context(content, f"log_{match}")
                                })
                                
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
    
    return audited_events


def identify_missing_audit_events(audit_events: Dict, audited_events: Dict) -> Dict[str, List]:
    """누락된 감사 이벤트 식별"""
    missing = {
        "critical_missing": [],
        "important_missing": [],
        "recommended_missing": []
    }
    
    # 현재 감사 중인 메서드들 추출
    current_audit_methods = set()
    for service_events in audited_events.values():
        for event in service_events:
            if isinstance(event, dict):
                current_audit_methods.add(event.get("audit_method", ""))
    
    # 각 카테고리별로 누락 확인
    for category, events in audit_events.items():
        for event in events:
            if event.get("audit_required", False):
                expected_audit_method = generate_expected_audit_method(event)
                
                if expected_audit_method not in current_audit_methods:
                    risk_level = event.get("risk_level", "medium")
                    
                    missing_info = {
                        "category": category,
                        "event": event,
                        "expected_audit_method": expected_audit_method,
                        "risk_level": risk_level
                    }
                    
                    if risk_level == "critical":
                        missing["critical_missing"].append(missing_info)
                    elif risk_level == "high":
                        missing["important_missing"].append(missing_info)
                    else:
                        missing["recommended_missing"].append(missing_info)
    
    return missing


def categorize_event(endpoint: str, func_name: str) -> str:
    """이벤트 카테고리 분류"""
    if any(keyword in endpoint.lower() or keyword in func_name.lower() 
           for keyword in ['login', 'logout', 'token', 'auth']):
        return "authentication"
    elif any(keyword in endpoint.lower() or keyword in func_name.lower()
             for keyword in ['user', 'register', 'create', 'update', 'delete']):
        return "user_management"
    elif any(keyword in endpoint.lower() or keyword in func_name.lower()
             for keyword in ['permission', 'role', 'access']):
        return "authorization"
    elif any(keyword in endpoint.lower() or keyword in func_name.lower()
             for keyword in ['mfa', 'password', 'security']):
        return "security"
    elif any(keyword in endpoint.lower() or keyword in func_name.lower()
             for keyword in ['admin', 'internal', 'system']):
        return "administrative"
    else:
        return "data_access"


def categorize_service_method(method_name: str) -> str:
    """서비스 메서드 카테고리 분류"""
    if any(keyword in method_name.lower() 
           for keyword in ['create_user', 'update_user', 'delete_user']):
        return "user_management"
    elif any(keyword in method_name.lower()
             for keyword in ['authenticate', 'login', 'logout', 'token']):
        return "authentication"
    elif any(keyword in method_name.lower()
             for keyword in ['password', 'mfa', 'enable', 'disable']):
        return "security"
    elif any(keyword in method_name.lower()
             for keyword in ['permission', 'role']):
        return "authorization"
    else:
        return "data_access"


def assess_risk_level(endpoint: str, func_name: str) -> str:
    """위험 수준 평가"""
    critical_keywords = ['delete', 'admin', 'password', 'token', 'auth']
    high_keywords = ['create', 'update', 'register', 'login', 'mfa']
    
    text = f"{endpoint} {func_name}".lower()
    
    if any(keyword in text for keyword in critical_keywords):
        return "critical"
    elif any(keyword in text for keyword in high_keywords):
        return "high"
    else:
        return "medium"


def assess_service_risk_level(method_name: str) -> str:
    """서비스 메서드 위험 수준 평가"""
    critical_methods = ['create_user', 'update_user', 'change_password', 'authenticate']
    high_methods = ['update_last_login', 'enable_mfa', 'disable_mfa']
    
    if method_name in critical_methods:
        return "critical"
    elif method_name in high_methods:
        return "high"
    else:
        return "medium"


def is_audit_required(endpoint: str, func_name: str) -> bool:
    """감사 필요 여부 판단"""
    # 모든 변경 작업과 인증 관련 작업은 감사 필요
    audit_keywords = ['post', 'put', 'delete', 'patch', 'login', 'auth', 'register', 
                     'password', 'mfa', 'token', 'create', 'update', 'delete']
    
    text = f"{endpoint} {func_name}".lower()
    return any(keyword in text for keyword in audit_keywords)


def should_audit_service_method(method_name: str) -> bool:
    """서비스 메서드 감사 필요 여부"""
    audit_methods = [
        'create_user', 'update_user', 'change_password', 'update_last_login',
        'update_user_permissions', 'authenticate', 'verify_token', 'create_access_token',
        'enable_mfa', 'disable_mfa', 'verify_mfa', 'generate_mfa_secret'
    ]
    return method_name in audit_methods


def determine_service_type(file_path: str) -> str:
    """파일 경로로 서비스 타입 결정"""
    if 'user_service.py' in file_path:
        return "user_service"
    elif 'auth_service.py' in file_path:
        return "auth_service"
    elif 'mfa_service.py' in file_path:
        return "mfa_service"
    else:
        return "routers"


def extract_context(content: str, audit_method: str) -> str:
    """감사 호출 컨텍스트 추출"""
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if audit_method in line:
            # 앞뒤 2줄씩 컨텍스트 추출
            start = max(0, i-2)
            end = min(len(lines), i+3)
            context_lines = lines[start:end]
            return '\n'.join(context_lines)
    return ""


def generate_expected_audit_method(event: Dict) -> str:
    """예상되는 감사 메서드 이름 생성"""
    if 'function' in event:
        func_name = event['function']
        if 'login' in func_name:
            return 'log_login_success' if 'success' in func_name else 'log_login_failed'
        elif 'register' in func_name:
            return 'log_user_created'
        elif 'password' in func_name:
            return 'log_password_changed'
        elif 'mfa' in func_name:
            return 'log_mfa_enabled' if 'enable' in func_name else 'log_mfa_disabled'
    elif 'method' in event:
        method_name = event['method']
        if 'create_user' in method_name:
            return 'log_user_created'
        elif 'update_user' in method_name:
            return 'log_user_updated'
        elif 'change_password' in method_name:
            return 'log_password_changed'
        elif 'authenticate' in method_name:
            return 'log_login_success'
    
    return f"log_{event.get('function', event.get('method', 'unknown'))}"


def generate_audit_coverage_report(audit_events: Dict, audited_events: Dict, missing_events: Dict):
    """감사 커버리지 보고서 생성"""
    print("\n" + "="*80)
    print("USER SERVICE AUDIT COVERAGE ANALYSIS REPORT")
    print("="*80)
    
    # 1. 현재 감사되고 있는 이벤트
    print("\n📊 CURRENTLY AUDITED EVENTS:")
    total_audited = 0
    for service, events in audited_events.items():
        if events:
            print(f"\n  {service.upper()}:")
            for event in events:
                if isinstance(event, dict):
                    print(f"    ✅ {event.get('audit_method', 'unknown')} in {event.get('file', 'unknown')}")
                    total_audited += 1
    
    print(f"\n  📈 Total Currently Audited: {total_audited} events")
    
    # 2. 식별된 모든 감사 대상 이벤트
    print("\n🎯 ALL AUDIT-REQUIRED EVENTS:")
    total_required = 0
    for category, events in audit_events.items():
        audit_required_events = [e for e in events if e.get('audit_required', False)]
        if audit_required_events:
            print(f"\n  {category.upper()} ({len(audit_required_events)} events):")
            for event in audit_required_events:
                risk = event.get('risk_level', 'medium')
                risk_icon = "🚨" if risk == "critical" else "⚠️" if risk == "high" else "ℹ️"
                if 'endpoint' in event:
                    print(f"    {risk_icon} {event['endpoint']} ({event['function']})")
                else:
                    print(f"    {risk_icon} {event.get('method', 'unknown')} in {event.get('file', 'unknown')}")
                total_required += 1
    
    print(f"\n  📊 Total Audit-Required Events: {total_required}")
    
    # 3. 누락된 감사 이벤트
    print("\n❌ MISSING AUDIT EVENTS:")
    
    if missing_events["critical_missing"]:
        print(f"\n  🚨 CRITICAL MISSING ({len(missing_events['critical_missing'])} events):")
        for missing in missing_events["critical_missing"]:
            event = missing["event"]
            print(f"    🚨 {missing['expected_audit_method']}")
            if 'endpoint' in event:
                print(f"       Source: {event['endpoint']} in {event['file']}")
            else:
                print(f"       Source: {event.get('method', 'unknown')} in {event.get('file', 'unknown')}")
    
    if missing_events["important_missing"]:
        print(f"\n  ⚠️  IMPORTANT MISSING ({len(missing_events['important_missing'])} events):")
        for missing in missing_events["important_missing"]:
            event = missing["event"]
            print(f"    ⚠️  {missing['expected_audit_method']}")
            if 'endpoint' in event:
                print(f"       Source: {event['endpoint']} in {event['file']}")
            else:
                print(f"       Source: {event.get('method', 'unknown')} in {event.get('file', 'unknown')}")
    
    if missing_events["recommended_missing"]:
        print(f"\n  ℹ️  RECOMMENDED MISSING ({len(missing_events['recommended_missing'])} events):")
        for missing in missing_events["recommended_missing"]:
            event = missing["event"]
            print(f"    ℹ️  {missing['expected_audit_method']}")
            if 'endpoint' in event:
                print(f"       Source: {event['endpoint']} in {event['file']}")
            else:
                print(f"       Source: {event.get('method', 'unknown')} in {event.get('file', 'unknown')}")
    
    # 4. 커버리지 통계
    total_missing = (len(missing_events["critical_missing"]) + 
                    len(missing_events["important_missing"]) + 
                    len(missing_events["recommended_missing"]))
    
    coverage_percentage = (total_audited / (total_audited + total_missing)) * 100 if (total_audited + total_missing) > 0 else 0
    
    print(f"\n📈 AUDIT COVERAGE STATISTICS:")
    print(f"  ✅ Currently Audited: {total_audited} events")
    print(f"  ❌ Missing Audits: {total_missing} events")
    print(f"  📊 Coverage Percentage: {coverage_percentage:.1f}%")
    
    # 5. 보안 위험 평가
    critical_missing = len(missing_events["critical_missing"])
    important_missing = len(missing_events["important_missing"])
    
    print(f"\n🔒 SECURITY RISK ASSESSMENT:")
    if critical_missing > 0:
        print(f"  🚨 HIGH RISK: {critical_missing} critical events not audited")
        print("     This creates serious compliance and security gaps!")
    elif important_missing > 0:
        print(f"  ⚠️  MEDIUM RISK: {important_missing} important events not audited")
        print("     Some security monitoring gaps exist")
    else:
        print("  ✅ LOW RISK: All critical and important events are audited")
    
    # 6. 권장사항
    print(f"\n💡 RECOMMENDATIONS:")
    if critical_missing > 0:
        print("  1. 🚨 URGENT: Implement audit logging for all critical missing events")
        print("  2. 📋 Review compliance requirements (SOX, GDPR, etc.)")
        print("  3. 🔍 Conduct security audit of user management operations")
    
    if important_missing > 0:
        print("  4. ⚠️  Add audit logging for important missing events")
        print("  5. 🔄 Implement automated audit coverage testing")
    
    if total_missing > 0:
        print("  6. 📊 Set up audit coverage monitoring dashboard")
        print("  7. 🔔 Configure alerts for missing audit events")
    
    print(f"\n🎯 AUDIT COVERAGE ANALYSIS COMPLETED")
    print("="*80)


if __name__ == "__main__":
    analyze_audit_coverage()