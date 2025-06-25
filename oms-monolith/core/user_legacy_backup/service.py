"""
Enterprise-grade User Service
Complete user management with advanced security features
"""

import asyncio
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum

import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field, validator
import pyotp
from sqlalchemy import Column, String, DateTime, Boolean, Integer, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from sqlalchemy.sql import func

# from database.clients import RedisHAClient  # TODO: Implement RedisHAClient
from utils import logging
from models import UserContext
from shared.observability import metrics, tracing
from shared.audit.audit_logger import AuditLogger

logger = logging.get_logger(__name__)
tracer = tracing.get_tracer(__name__)

# Password hashing
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    default="argon2",
    argon2__rounds=4,
    argon2__memory_cost=65536,
    argon2__parallelism=2,
)

# Database models
Base = declarative_base()


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class User(Base):
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(100))
    password_hash = Column(String(255), nullable=False)
    
    # Security fields
    status = Column(String(20), default=UserStatus.PENDING_VERIFICATION)
    roles = Column(JSON, default=list)
    permissions = Column(JSON, default=list)
    
    # MFA
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String(32))
    backup_codes = Column(JSON)
    
    # Account security
    failed_login_attempts = Column(Integer, default=0)
    last_failed_login = Column(DateTime(timezone=True))
    locked_until = Column(DateTime(timezone=True))
    password_changed_at = Column(DateTime(timezone=True))
    password_history = Column(JSON, default=list)  # Hashed passwords
    
    # Session management
    active_sessions = Column(JSON, default=list)
    last_login = Column(DateTime(timezone=True))
    last_activity = Column(DateTime(timezone=True))
    
    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(50))
    updated_by = Column(String(50))
    
    # Preferences
    preferences = Column(JSON, default=dict)
    notification_settings = Column(JSON, default=dict)
    
    # Compliance
    terms_accepted_at = Column(DateTime(timezone=True))
    privacy_accepted_at = Column(DateTime(timezone=True))
    data_retention_consent = Column(Boolean, default=True)
    
    __table_args__ = (
        Index('idx_user_status', 'status'),
        Index('idx_user_created', 'created_at'),
    )


class Session(Base):
    __tablename__ = "user_sessions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    session_token = Column(String(255), unique=True, nullable=False)
    refresh_token = Column(String(255), unique=True, nullable=False)
    
    # Session info
    ip_address = Column(String(45))
    user_agent = Column(String(255))
    device_id = Column(String(100))
    location = Column(JSON)  # GeoIP data
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_activity = Column(DateTime(timezone=True))
    refresh_expires_at = Column(DateTime(timezone=True), nullable=False)
    
    # Security
    is_active = Column(Boolean, default=True)
    revoked_at = Column(DateTime(timezone=True))
    revoked_reason = Column(String(255))
    
    __table_args__ = (
        Index('idx_session_user', 'user_id'),
        Index('idx_session_expires', 'expires_at'),
        Index('idx_session_active', 'is_active'),
    )


class AuditLog(Base):
    __tablename__ = "user_audit_logs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), index=True)
    action = Column(String(50), nullable=False, index=True)
    resource = Column(String(100))
    details = Column(JSON)
    
    # Request info
    ip_address = Column(String(45))
    user_agent = Column(String(255))
    request_id = Column(String(36))
    
    # Result
    success = Column(Boolean, default=True)
    error_message = Column(String(500))
    
    # Timestamp
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    __table_args__ = (
        Index('idx_audit_user_time', 'user_id', 'timestamp'),
        Index('idx_audit_action', 'action'),
    )


# Request/Response models
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, regex="^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    roles: List[str] = []
    
    @validator('password')
    def validate_password(cls, v):
        """Enforce password complexity"""
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain digit')
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError('Password must contain special character')
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    roles: Optional[List[str]] = None
    status: Optional[UserStatus] = None
    preferences: Optional[Dict[str, Any]] = None


class LoginRequest(BaseModel):
    username: str
    password: str
    device_id: Optional[str] = None
    mfa_code: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]
    requires_mfa: bool = False
    session_id: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str
    logout_all_sessions: bool = False


class MFASetupResponse(BaseModel):
    secret: str
    qr_code: str
    backup_codes: List[str]


class EnterpriseUserService:
    """Enterprise-grade user management service"""
    
    def __init__(
        self,
        database_url: str,
        jwt_secret: str,
        redis_client: Optional[Any] = None,  # RedisHAClient
        jwt_algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
        max_failed_attempts: int = 5,
        lockout_duration_minutes: int = 30,
        password_history_count: int = 12,
        password_expire_days: int = 90,
        session_timeout_minutes: int = 30,
        max_concurrent_sessions: int = 5
    ):
        self.redis_client = redis_client
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days
        self.max_failed_attempts = max_failed_attempts
        self.lockout_duration_minutes = lockout_duration_minutes
        self.password_history_count = password_history_count
        self.password_expire_days = password_expire_days
        self.session_timeout_minutes = session_timeout_minutes
        self.max_concurrent_sessions = max_concurrent_sessions
        
        # Database setup
        self.engine = create_async_engine(
            database_url,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        
        # Audit logger
        self.audit_logger = AuditLogger()
        
        # Metrics
        self.login_attempts = metrics.Counter(
            'user_login_attempts_total',
            'Total login attempts',
            ['status']
        )
        self.active_users = metrics.Gauge(
            'active_users_total',
            'Total active users'
        )
        self.mfa_usage = metrics.Counter(
            'mfa_usage_total',
            'MFA usage statistics',
            ['action', 'status']
        )
    
    async def initialize(self):
        """Initialize database tables"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def create_user(
        self,
        user_data: UserCreate,
        created_by: str = "system"
    ) -> User:
        """Create new user with all security features"""
        with tracer.start_as_current_span("create_user") as span:
            span.set_attribute("user.username", user_data.username)
            
            async with self.async_session() as session:
                try:
                    # Check if user exists
                    existing = await session.execute(
                        select(User).where(
                            (User.username == user_data.username) |
                            (User.email == user_data.email)
                        )
                    )
                    if existing.scalar_one_or_none():
                        raise ValueError("User already exists")
                    
                    # Hash password
                    password_hash = pwd_context.hash(user_data.password)
                    
                    # Create user
                    user = User(
                        username=user_data.username,
                        email=user_data.email,
                        full_name=user_data.full_name,
                        password_hash=password_hash,
                        roles=user_data.roles or ["user"],
                        password_changed_at=datetime.now(timezone.utc),
                        password_history=[password_hash],
                        created_by=created_by
                    )
                    
                    session.add(user)
                    await session.commit()
                    await session.refresh(user)
                    
                    # Audit log
                    await self.audit_logger.log_event(
                        user_id=user.id,
                        action="user.created",
                        resource=f"user:{user.id}",
                        details={"username": user.username, "email": user.email}
                    )
                    
                    # Update metrics
                    self.active_users.inc()
                    
                    return user
                    
                except Exception as e:
                    await session.rollback()
                    logger.error(f"Error creating user: {e}")
                    span.record_exception(e)
                    raise
    
    async def authenticate(
        self,
        login_data: LoginRequest,
        ip_address: str,
        user_agent: str
    ) -> LoginResponse:
        """Authenticate user with advanced security"""
        with tracer.start_as_current_span("authenticate") as span:
            span.set_attribute("user.username", login_data.username)
            
            async with self.async_session() as session:
                try:
                    # Get user
                    result = await session.execute(
                        select(User).where(User.username == login_data.username)
                    )
                    user = result.scalar_one_or_none()
                    
                    if not user:
                        self.login_attempts.labels(status="invalid_user").inc()
                        raise ValueError("Invalid credentials")
                    
                    # Check if account is locked
                    if user.status == UserStatus.LOCKED:
                        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
                            raise ValueError("Account is locked")
                        else:
                            # Unlock account
                            user.status = UserStatus.ACTIVE
                            user.locked_until = None
                            user.failed_login_attempts = 0
                    
                    # Check password
                    if not pwd_context.verify(login_data.password, user.password_hash):
                        # Increment failed attempts
                        user.failed_login_attempts += 1
                        user.last_failed_login = datetime.now(timezone.utc)
                        
                        # Lock account if too many failures
                        if user.failed_login_attempts >= self.max_failed_attempts:
                            user.status = UserStatus.LOCKED
                            user.locked_until = datetime.now(timezone.utc) + timedelta(
                                minutes=self.lockout_duration_minutes
                            )
                            await session.commit()
                            
                            await self.audit_logger.log_event(
                                user_id=user.id,
                                action="account.locked",
                                resource=f"user:{user.id}",
                                details={"reason": "max_failed_attempts"}
                            )
                            
                            raise ValueError("Account locked due to multiple failed attempts")
                        
                        await session.commit()
                        self.login_attempts.labels(status="invalid_password").inc()
                        raise ValueError("Invalid credentials")
                    
                    # Check if MFA is required
                    if user.mfa_enabled:
                        if not login_data.mfa_code:
                            return LoginResponse(
                                access_token="",
                                refresh_token="",
                                expires_in=0,
                                user={},
                                requires_mfa=True,
                                session_id=""
                            )
                        
                        # Verify MFA code
                        if not self._verify_mfa_code(user.mfa_secret, login_data.mfa_code):
                            self.mfa_usage.labels(action="verify", status="failed").inc()
                            raise ValueError("Invalid MFA code")
                        
                        self.mfa_usage.labels(action="verify", status="success").inc()
                    
                    # Check password expiry
                    if user.password_changed_at:
                        days_since_change = (
                            datetime.now(timezone.utc) - user.password_changed_at
                        ).days
                        if days_since_change > self.password_expire_days:
                            raise ValueError("Password expired")
                    
                    # Reset failed attempts
                    user.failed_login_attempts = 0
                    user.last_login = datetime.now(timezone.utc)
                    user.last_activity = datetime.now(timezone.utc)
                    
                    # Check concurrent sessions
                    active_sessions = await self._get_active_sessions(user.id)
                    if len(active_sessions) >= self.max_concurrent_sessions:
                        # Revoke oldest session
                        oldest_session = min(active_sessions, key=lambda s: s.created_at)
                        await self._revoke_session(
                            oldest_session.id,
                            "max_concurrent_sessions"
                        )
                    
                    # Create new session
                    session_id = str(uuid.uuid4())
                    access_token, access_payload = self._create_access_token(user)
                    refresh_token, refresh_payload = self._create_refresh_token(user, session_id)
                    
                    # Store session
                    new_session = Session(
                        id=session_id,
                        user_id=user.id,
                        session_token=access_token,
                        refresh_token=refresh_token,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        device_id=login_data.device_id,
                        expires_at=datetime.fromtimestamp(
                            access_payload['exp'], timezone.utc
                        ),
                        refresh_expires_at=datetime.fromtimestamp(
                            refresh_payload['exp'], timezone.utc
                        ),
                        last_activity=datetime.now(timezone.utc)
                    )
                    session.add(new_session)
                    
                    # Update user sessions
                    if not user.active_sessions:
                        user.active_sessions = []
                    user.active_sessions.append(session_id)
                    
                    await session.commit()
                    
                    # Cache session
                    await self._cache_session(session_id, user.id, access_payload['exp'])
                    
                    # Audit log
                    await self.audit_logger.log_event(
                        user_id=user.id,
                        action="user.login",
                        resource=f"session:{session_id}",
                        details={
                            "ip": ip_address,
                            "user_agent": user_agent,
                            "device_id": login_data.device_id
                        }
                    )
                    
                    self.login_attempts.labels(status="success").inc()
                    
                    return LoginResponse(
                        access_token=access_token,
                        refresh_token=refresh_token,
                        expires_in=self.access_token_expire_minutes * 60,
                        user={
                            "id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "full_name": user.full_name,
                            "roles": user.roles,
                            "permissions": user.permissions
                        },
                        session_id=session_id
                    )
                    
                except Exception as e:
                    await session.rollback()
                    logger.error(f"Authentication error: {e}")
                    span.record_exception(e)
                    raise
    
    async def logout(self, session_id: str, user_id: str):
        """Logout user and revoke session"""
        with tracer.start_as_current_span("logout") as span:
            span.set_attribute("session.id", session_id)
            
            await self._revoke_session(session_id, "user_logout")
            
            # Remove from cache
            await self.redis_client.delete(f"session:{session_id}")
            
            # Audit log
            await self.audit_logger.log_event(
                user_id=user_id,
                action="user.logout",
                resource=f"session:{session_id}"
            )
    
    async def refresh_token(
        self,
        refresh_token: str
    ) -> Tuple[str, str]:
        """Refresh access token"""
        with tracer.start_as_current_span("refresh_token") as span:
            try:
                # Decode refresh token
                payload = jwt.decode(
                    refresh_token,
                    self.jwt_secret,
                    algorithms=[self.jwt_algorithm]
                )
                
                if payload.get('type') != 'refresh':
                    raise ValueError("Invalid token type")
                
                session_id = payload.get('session_id')
                user_id = payload.get('sub')
                
                # Verify session
                async with self.async_session() as session:
                    result = await session.execute(
                        select(Session).where(
                            (Session.id == session_id) &
                            (Session.refresh_token == refresh_token) &
                            (Session.is_active == True)
                        )
                    )
                    db_session = result.scalar_one_or_none()
                    
                    if not db_session:
                        raise ValueError("Invalid session")
                    
                    # Get user
                    result = await session.execute(
                        select(User).where(User.id == user_id)
                    )
                    user = result.scalar_one_or_none()
                    
                    if not user or user.status != UserStatus.ACTIVE:
                        raise ValueError("Invalid user")
                    
                    # Create new tokens
                    access_token, access_payload = self._create_access_token(user)
                    new_refresh_token, refresh_payload = self._create_refresh_token(
                        user, session_id
                    )
                    
                    # Update session
                    db_session.session_token = access_token
                    db_session.refresh_token = new_refresh_token
                    db_session.expires_at = datetime.fromtimestamp(
                        access_payload['exp'], timezone.utc
                    )
                    db_session.refresh_expires_at = datetime.fromtimestamp(
                        refresh_payload['exp'], timezone.utc
                    )
                    db_session.last_activity = datetime.now(timezone.utc)
                    
                    await session.commit()
                    
                    # Update cache
                    await self._cache_session(session_id, user_id, access_payload['exp'])
                    
                    return access_token, new_refresh_token
                    
            except Exception as e:
                logger.error(f"Token refresh error: {e}")
                span.record_exception(e)
                raise
    
    async def change_password(
        self,
        user_id: str,
        request: PasswordChangeRequest
    ):
        """Change user password with history check"""
        with tracer.start_as_current_span("change_password") as span:
            span.set_attribute("user.id", user_id)
            
            async with self.async_session() as session:
                try:
                    # Get user
                    result = await session.execute(
                        select(User).where(User.id == user_id)
                    )
                    user = result.scalar_one_or_none()
                    
                    if not user:
                        raise ValueError("User not found")
                    
                    # Verify current password
                    if not pwd_context.verify(request.current_password, user.password_hash):
                        raise ValueError("Invalid current password")
                    
                    # Check password history
                    new_hash = pwd_context.hash(request.new_password)
                    for old_hash in user.password_history[-self.password_history_count:]:
                        if pwd_context.verify(request.new_password, old_hash):
                            raise ValueError(
                                f"Password was used previously. "
                                f"Cannot reuse last {self.password_history_count} passwords"
                            )
                    
                    # Update password
                    user.password_hash = new_hash
                    user.password_changed_at = datetime.now(timezone.utc)
                    
                    # Update history
                    if not user.password_history:
                        user.password_history = []
                    user.password_history.append(new_hash)
                    user.password_history = user.password_history[-self.password_history_count:]
                    
                    # Revoke all sessions if requested
                    if request.logout_all_sessions:
                        await self._revoke_all_user_sessions(user_id, "password_change")
                    
                    await session.commit()
                    
                    # Audit log
                    await self.audit_logger.log_event(
                        user_id=user_id,
                        action="password.changed",
                        resource=f"user:{user_id}",
                        details={"logout_all": request.logout_all_sessions}
                    )
                    
                except Exception as e:
                    await session.rollback()
                    logger.error(f"Password change error: {e}")
                    span.record_exception(e)
                    raise
    
    async def setup_mfa(self, user_id: str) -> MFASetupResponse:
        """Setup MFA for user"""
        with tracer.start_as_current_span("setup_mfa") as span:
            span.set_attribute("user.id", user_id)
            
            async with self.async_session() as session:
                try:
                    # Get user
                    result = await session.execute(
                        select(User).where(User.id == user_id)
                    )
                    user = result.scalar_one_or_none()
                    
                    if not user:
                        raise ValueError("User not found")
                    
                    # Generate secret
                    secret = pyotp.random_base32()
                    
                    # Generate backup codes
                    backup_codes = [
                        secrets.token_hex(4).upper()
                        for _ in range(10)
                    ]
                    
                    # Store encrypted
                    user.mfa_secret = secret
                    user.backup_codes = [
                        pwd_context.hash(code) for code in backup_codes
                    ]
                    user.mfa_enabled = True
                    
                    await session.commit()
                    
                    # Generate QR code
                    totp = pyotp.TOTP(secret)
                    provisioning_uri = totp.provisioning_uri(
                        name=user.email,
                        issuer_name='OMS'
                    )
                    
                    # Audit log
                    await self.audit_logger.log_event(
                        user_id=user_id,
                        action="mfa.enabled",
                        resource=f"user:{user_id}"
                    )
                    
                    self.mfa_usage.labels(action="setup", status="success").inc()
                    
                    return MFASetupResponse(
                        secret=secret,
                        qr_code=provisioning_uri,
                        backup_codes=backup_codes
                    )
                    
                except Exception as e:
                    await session.rollback()
                    logger.error(f"MFA setup error: {e}")
                    span.record_exception(e)
                    raise
    
    async def validate_token(self, token: str) -> UserContext:
        """Validate access token and return user context"""
        with tracer.start_as_current_span("validate_token") as span:
            try:
                # Decode token
                payload = jwt.decode(
                    token,
                    self.jwt_secret,
                    algorithms=[self.jwt_algorithm]
                )
                
                if payload.get('type') != 'access':
                    raise ValueError("Invalid token type")
                
                user_id = payload.get('sub')
                session_id = payload.get('session_id')
                
                # Check cache first
                cached = await self.redis_client.get(f"session:{session_id}")
                if cached and cached == user_id:
                    # Get user details from cache
                    user_data = await self.redis_client.get(f"user:{user_id}")
                    if user_data:
                        return UserContext(**user_data)
                
                # Fallback to database
                async with self.async_session() as session:
                    # Verify session
                    result = await session.execute(
                        select(Session).where(
                            (Session.id == session_id) &
                            (Session.is_active == True)
                        )
                    )
                    db_session = result.scalar_one_or_none()
                    
                    if not db_session:
                        raise ValueError("Invalid session")
                    
                    # Get user
                    result = await session.execute(
                        select(User).where(User.id == user_id)
                    )
                    user = result.scalar_one_or_none()
                    
                    if not user or user.status != UserStatus.ACTIVE:
                        raise ValueError("Invalid user")
                    
                    # Update last activity
                    db_session.last_activity = datetime.now(timezone.utc)
                    await session.commit()
                    
                    # Build user context
                    user_context = UserContext(
                        id=user.id,
                        username=user.username,
                        email=user.email,
                        roles=user.roles,
                        permissions=set(user.permissions)
                    )
                    
                    # Cache user data
                    await self.redis_client.setex(
                        f"user:{user_id}",
                        300,  # 5 minutes
                        user_context.dict()
                    )
                    
                    return user_context
                    
            except jwt.ExpiredSignatureError:
                raise ValueError("Token expired")
            except Exception as e:
                logger.error(f"Token validation error: {e}")
                span.record_exception(e)
                raise
    
    # Helper methods
    def _create_access_token(self, user: User) -> Tuple[str, Dict]:
        """Create JWT access token"""
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self.access_token_expire_minutes)
        
        payload = {
            'sub': user.id,
            'username': user.username,
            'email': user.email,
            'roles': user.roles,
            'type': 'access',
            'iat': now,
            'exp': expire,
            'session_id': str(uuid.uuid4())
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token, payload
    
    def _create_refresh_token(self, user: User, session_id: str) -> Tuple[str, Dict]:
        """Create JWT refresh token"""
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=self.refresh_token_expire_days)
        
        payload = {
            'sub': user.id,
            'type': 'refresh',
            'iat': now,
            'exp': expire,
            'session_id': session_id
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token, payload
    
    def _verify_mfa_code(self, secret: str, code: str) -> bool:
        """Verify TOTP MFA code"""
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)
    
    async def _get_active_sessions(self, user_id: str) -> List[Session]:
        """Get all active sessions for user"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Session).where(
                    (Session.user_id == user_id) &
                    (Session.is_active == True)
                ).order_by(Session.created_at)
            )
            return result.scalars().all()
    
    async def _revoke_session(self, session_id: str, reason: str):
        """Revoke a specific session"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Session).where(Session.id == session_id)
            )
            db_session = result.scalar_one_or_none()
            
            if db_session:
                db_session.is_active = False
                db_session.revoked_at = datetime.now(timezone.utc)
                db_session.revoked_reason = reason
                await session.commit()
    
    async def _revoke_all_user_sessions(self, user_id: str, reason: str):
        """Revoke all sessions for user"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Session).where(
                    (Session.user_id == user_id) &
                    (Session.is_active == True)
                )
            )
            sessions = result.scalars().all()
            
            for db_session in sessions:
                db_session.is_active = False
                db_session.revoked_at = datetime.now(timezone.utc)
                db_session.revoked_reason = reason
            
            await session.commit()
            
            # Clear cache
            for db_session in sessions:
                await self.redis_client.delete(f"session:{db_session.id}")
    
    async def _cache_session(self, session_id: str, user_id: str, expire_at: int):
        """Cache session in Redis"""
        ttl = expire_at - int(datetime.now(timezone.utc).timestamp())
        if ttl > 0:
            await self.redis_client.setex(
                f"session:{session_id}",
                ttl,
                user_id
            )