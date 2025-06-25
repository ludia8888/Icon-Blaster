"""
User Service API Routes
Enterprise-grade user management endpoints
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.user.service import (
    EnterpriseUserService,
    UserCreate,
    UserUpdate,
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    MFASetupResponse,
    UserStatus
)
from models import UserContext
from utils import logging

logger = logging.get_logger(__name__)

# Security
security = HTTPBearer()

# Router
router = APIRouter(prefix="/api/v1/users", tags=["users"])

# Dependency to get user service
async def get_user_service(request: Request) -> EnterpriseUserService:
    """Get user service from app state"""
    return request.app.state.services.get("user_service")

# Dependency to get current user
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_service: EnterpriseUserService = Depends(get_user_service)
) -> UserContext:
    """Get current authenticated user"""
    try:
        return await user_service.validate_token(credentials.credentials)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

# Dependency for admin users
async def require_admin(
    current_user: UserContext = Depends(get_current_user)
) -> UserContext:
    """Require admin role"""
    if "admin" not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# === Public Endpoints ===

@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Register new user
    
    - Validates email and username uniqueness
    - Enforces password complexity
    - Sends verification email (if configured)
    """
    try:
        user = await user_service.create_user(user_data)
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "status": user.status,
            "message": "Registration successful. Please verify your email."
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    User login
    
    - Validates credentials
    - Enforces account lockout policy
    - Handles MFA if enabled
    - Returns JWT tokens
    """
    try:
        # Get client info
        ip_address = request.client.host
        user_agent = request.headers.get("User-Agent", "Unknown")
        
        response = await user_service.authenticate(
            login_data,
            ip_address,
            user_agent
        )
        
        if response.requires_mfa:
            return response
        
        # Set secure cookie for refresh token
        return response
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/refresh", response_model=dict)
async def refresh_token(
    refresh_token: str,
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Refresh access token
    
    - Validates refresh token
    - Issues new access and refresh tokens
    """
    try:
        access_token, new_refresh_token = await user_service.refresh_token(
            refresh_token
        )
        
        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer"
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


# === Authenticated Endpoints ===

@router.get("/me", response_model=dict)
async def get_current_user_info(
    current_user: UserContext = Depends(get_current_user),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Get current user information
    """
    # Get full user details from database
    async with user_service.async_session() as session:
        from sqlalchemy.future import select
        from core.user.service import User
        
        result = await session.execute(
            select(User).where(User.id == current_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "roles": user.roles,
            "permissions": user.permissions,
            "status": user.status,
            "mfa_enabled": user.mfa_enabled,
            "created_at": user.created_at.isoformat(),
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "preferences": user.preferences,
            "notification_settings": user.notification_settings
        }


@router.put("/me", response_model=dict)
async def update_current_user(
    update_data: UserUpdate,
    current_user: UserContext = Depends(get_current_user),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Update current user information
    """
    async with user_service.async_session() as session:
        from sqlalchemy.future import select
        from core.user.service import User
        
        result = await session.execute(
            select(User).where(User.id == current_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Update allowed fields
        if update_data.full_name is not None:
            user.full_name = update_data.full_name
        if update_data.email is not None:
            # Check email uniqueness
            existing = await session.execute(
                select(User).where(
                    (User.email == update_data.email) &
                    (User.id != current_user.id)
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use"
                )
            user.email = update_data.email
        if update_data.preferences is not None:
            user.preferences = update_data.preferences
        
        user.updated_by = current_user.username
        
        await session.commit()
        
        return {"message": "User updated successfully"}


@router.post("/logout")
async def logout(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Logout current user
    
    - Revokes current session
    - Clears session cache
    """
    # Get session ID from token
    credentials = await security(request)
    token = credentials.credentials
    
    import jwt
    payload = jwt.decode(
        token,
        user_service.jwt_secret,
        algorithms=[user_service.jwt_algorithm]
    )
    session_id = payload.get('session_id')
    
    await user_service.logout(session_id, current_user.id)
    
    return {"message": "Logout successful"}


@router.post("/change-password")
async def change_password(
    request: PasswordChangeRequest,
    current_user: UserContext = Depends(get_current_user),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Change user password
    
    - Validates current password
    - Enforces password history
    - Optional: logout all sessions
    """
    try:
        await user_service.change_password(current_user.id, request)
        return {"message": "Password changed successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Password change error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password change failed"
        )


# === MFA Endpoints ===

@router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    current_user: UserContext = Depends(get_current_user),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Setup MFA for current user
    
    - Generates TOTP secret
    - Returns QR code and backup codes
    """
    try:
        return await user_service.setup_mfa(current_user.id)
    except Exception as e:
        logger.error(f"MFA setup error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MFA setup failed"
        )


@router.post("/mfa/disable")
async def disable_mfa(
    password: str,
    current_user: UserContext = Depends(get_current_user),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Disable MFA for current user
    
    - Requires password verification
    """
    async with user_service.async_session() as session:
        from sqlalchemy.future import select
        from core.user.service import User, pwd_context
        
        result = await session.execute(
            select(User).where(User.id == current_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Verify password
        if not pwd_context.verify(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password"
            )
        
        # Disable MFA
        user.mfa_enabled = False
        user.mfa_secret = None
        user.backup_codes = None
        
        await session.commit()
        
        # Audit log
        await user_service.audit_logger.log_event(
            user_id=user.id,
            action="mfa.disabled",
            resource=f"user:{user.id}"
        )
        
        return {"message": "MFA disabled successfully"}


@router.post("/mfa/verify")
async def verify_mfa(
    code: str,
    current_user: UserContext = Depends(get_current_user),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Verify MFA code
    
    - For testing MFA setup
    """
    async with user_service.async_session() as session:
        from sqlalchemy.future import select
        from core.user.service import User
        
        result = await session.execute(
            select(User).where(User.id == current_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user or not user.mfa_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MFA not enabled"
            )
        
        if user_service._verify_mfa_code(user.mfa_secret, code):
            return {"valid": True, "message": "MFA code verified"}
        else:
            return {"valid": False, "message": "Invalid MFA code"}


# === Admin Endpoints ===

@router.get("/", response_model=dict)
async def list_users(
    offset: int = 0,
    limit: int = 100,
    status: Optional[UserStatus] = None,
    role: Optional[str] = None,
    search: Optional[str] = None,
    current_user: UserContext = Depends(require_admin),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    List all users (admin only)
    
    - Supports filtering and pagination
    - Returns user summaries
    """
    async with user_service.async_session() as session:
        from sqlalchemy.future import select
        from sqlalchemy import or_, and_
        from core.user.service import User
        
        query = select(User)
        
        # Apply filters
        filters = []
        if status:
            filters.append(User.status == status)
        if role:
            filters.append(User.roles.contains([role]))
        if search:
            filters.append(
                or_(
                    User.username.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%"),
                    User.full_name.ilike(f"%{search}%")
                )
            )
        
        if filters:
            query = query.where(and_(*filters))
        
        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = await session.scalar(count_query)
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        
        result = await session.execute(query)
        users = result.scalars().all()
        
        return {
            "users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "roles": user.roles,
                    "status": user.status,
                    "mfa_enabled": user.mfa_enabled,
                    "created_at": user.created_at.isoformat(),
                    "last_login": user.last_login.isoformat() if user.last_login else None
                }
                for user in users
            ],
            "total": total,
            "offset": offset,
            "limit": limit
        }


@router.get("/{user_id}", response_model=dict)
async def get_user(
    user_id: str,
    current_user: UserContext = Depends(require_admin),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Get specific user details (admin only)
    """
    async with user_service.async_session() as session:
        from sqlalchemy.future import select
        from core.user.service import User
        
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "roles": user.roles,
            "permissions": user.permissions,
            "status": user.status,
            "mfa_enabled": user.mfa_enabled,
            "failed_login_attempts": user.failed_login_attempts,
            "last_failed_login": user.last_failed_login.isoformat() if user.last_failed_login else None,
            "locked_until": user.locked_until.isoformat() if user.locked_until else None,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "last_activity": user.last_activity.isoformat() if user.last_activity else None,
            "active_sessions": len(user.active_sessions) if user.active_sessions else 0
        }


@router.put("/{user_id}", response_model=dict)
async def update_user(
    user_id: str,
    update_data: UserUpdate,
    current_user: UserContext = Depends(require_admin),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Update user (admin only)
    
    - Can update roles, status, etc.
    """
    async with user_service.async_session() as session:
        from sqlalchemy.future import select
        from core.user.service import User
        
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Update fields
        if update_data.full_name is not None:
            user.full_name = update_data.full_name
        if update_data.email is not None:
            user.email = update_data.email
        if update_data.roles is not None:
            user.roles = update_data.roles
        if update_data.status is not None:
            user.status = update_data.status
            # Clear lock if activating
            if update_data.status == UserStatus.ACTIVE:
                user.locked_until = None
                user.failed_login_attempts = 0
        
        user.updated_by = current_user.username
        
        await session.commit()
        
        # Audit log
        await user_service.audit_logger.log_event(
            user_id=current_user.id,
            action="user.updated",
            resource=f"user:{user_id}",
            details=update_data.dict(exclude_unset=True)
        )
        
        return {"message": "User updated successfully"}


@router.post("/{user_id}/unlock")
async def unlock_user(
    user_id: str,
    current_user: UserContext = Depends(require_admin),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Unlock user account (admin only)
    """
    async with user_service.async_session() as session:
        from sqlalchemy.future import select
        from core.user.service import User
        
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user.status = UserStatus.ACTIVE
        user.locked_until = None
        user.failed_login_attempts = 0
        user.updated_by = current_user.username
        
        await session.commit()
        
        # Audit log
        await user_service.audit_logger.log_event(
            user_id=current_user.id,
            action="user.unlocked",
            resource=f"user:{user_id}"
        )
        
        return {"message": "User unlocked successfully"}


@router.post("/{user_id}/revoke-sessions")
async def revoke_user_sessions(
    user_id: str,
    current_user: UserContext = Depends(require_admin),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Revoke all sessions for user (admin only)
    """
    await user_service._revoke_all_user_sessions(user_id, "admin_action")
    
    # Audit log
    await user_service.audit_logger.log_event(
        user_id=current_user.id,
        action="sessions.revoked",
        resource=f"user:{user_id}"
    )
    
    return {"message": "All user sessions revoked"}


@router.get("/{user_id}/sessions", response_model=dict)
async def get_user_sessions(
    user_id: str,
    current_user: UserContext = Depends(require_admin),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Get active sessions for user (admin only)
    """
    sessions = await user_service._get_active_sessions(user_id)
    
    return {
        "sessions": [
            {
                "id": session.id,
                "ip_address": session.ip_address,
                "user_agent": session.user_agent,
                "device_id": session.device_id,
                "created_at": session.created_at.isoformat(),
                "last_activity": session.last_activity.isoformat() if session.last_activity else None,
                "expires_at": session.expires_at.isoformat()
            }
            for session in sessions
        ],
        "total": len(sessions)
    }


@router.get("/{user_id}/audit-logs", response_model=dict)
async def get_user_audit_logs(
    user_id: str,
    offset: int = 0,
    limit: int = 100,
    action: Optional[str] = None,
    current_user: UserContext = Depends(require_admin),
    user_service: EnterpriseUserService = Depends(get_user_service)
):
    """
    Get audit logs for user (admin only)
    """
    async with user_service.async_session() as session:
        from sqlalchemy.future import select
        from sqlalchemy import and_
        from core.user.service import AuditLog
        
        query = select(AuditLog).where(AuditLog.user_id == user_id)
        
        if action:
            query = query.where(AuditLog.action == action)
        
        query = query.order_by(AuditLog.timestamp.desc())
        
        # Count total
        from sqlalchemy.sql import func
        count_query = select(func.count()).select_from(query.subquery())
        total = await session.scalar(count_query)
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        
        result = await session.execute(query)
        logs = result.scalars().all()
        
        return {
            "logs": [
                {
                    "id": log.id,
                    "action": log.action,
                    "resource": log.resource,
                    "details": log.details,
                    "ip_address": log.ip_address,
                    "success": log.success,
                    "error_message": log.error_message,
                    "timestamp": log.timestamp.isoformat()
                }
                for log in logs
            ],
            "total": total,
            "offset": offset,
            "limit": limit
        }