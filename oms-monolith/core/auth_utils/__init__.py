"""
Auth Module - Minimal Resource Permission Checking
실제 인증/인가는 외부 IdP 서비스에 위임
"""
# Import from parent auth.py
import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from auth import UserContext, get_permission_checker

__all__ = ['UserContext', 'get_permission_checker']