# User Service (IdP)

Enterprise-grade Identity Provider service separated from OMS monolith.

## Overview

This service handles all authentication and user management functionalities:
- User registration and management
- JWT-based authentication
- Multi-factor authentication (MFA)
- Session management
- Role-based access control (RBAC)
- Audit logging

## Tech Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL (users, sessions)
- **Cache**: Redis (session cache, rate limiting)
- **Authentication**: JWT + Argon2
- **MFA**: TOTP (pyotp)

## Project Structure

```
user-service/
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py         # Authentication endpoints
│   │   ├── users.py        # User management endpoints
│   │   └── admin.py        # Admin endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py       # Configuration
│   │   ├── security.py     # Security utilities
│   │   └── database.py     # Database connection
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py         # User model
│   │   └── session.py      # Session model
│   ├── services/
│   │   ├── __init__.py
│   │   ├── user_service.py # User business logic
│   │   ├── auth_service.py # Authentication logic
│   │   └── mfa_service.py  # MFA logic
│   └── main.py            # Application entry point
├── tests/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── requirements.txt
└── README.md
```

## Quick Start

### Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Redis 6+

### Installation

```bash
# Clone repository
git clone https://github.com/ludia8888/User-Service.git
cd User-Service

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Run database migrations
alembic upgrade head

# Start the service
uvicorn src.main:app --reload
```

### Docker Setup

```bash
# Build and run with Docker Compose
docker-compose up -d

# Check logs
docker-compose logs -f
```

## API Documentation

Once running, API documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Key Endpoints

#### Authentication

```
POST   /auth/login      - User login
POST   /auth/logout     - User logout  
POST   /auth/refresh    - Refresh access token
GET    /auth/userinfo   - Get current user info
```

#### User Management

```
POST   /users           - Create user
GET    /users/{id}      - Get user
PUT    /users/{id}      - Update user
DELETE /users/{id}      - Delete user
GET    /users           - List users (admin)
```

#### MFA

```
POST   /mfa/setup       - Setup MFA
POST   /mfa/verify      - Verify MFA code
POST   /mfa/disable     - Disable MFA
GET    /mfa/backup-codes - Get backup codes
```

## Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost/userdb
REDIS_URL=redis://localhost:6379

# JWT
JWT_SECRET=your-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Security
PASSWORD_MIN_LENGTH=8
MAX_FAILED_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=30

# MFA
MFA_ISSUER=YourCompany
MFA_BACKUP_CODES_COUNT=10
```

## Security Features

- **Password Security**: Argon2 hashing with salt
- **JWT Tokens**: Short-lived access tokens with refresh tokens
- **MFA Support**: TOTP-based 2FA with backup codes
- **Account Lockout**: After failed login attempts
- **Session Management**: Concurrent session limits
- **Audit Logging**: All authentication events logged

## Integration with OMS

OMS integrates with this service via JWT tokens:

1. User authenticates with User Service
2. User Service returns JWT token
3. OMS validates JWT and extracts user info
4. OMS checks permissions locally

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_auth.py
```

### Code Style

```bash
# Format code
black src tests

# Lint
flake8 src tests

# Type checking
mypy src
```

## Production Deployment

### Health Checks

- `GET /health` - Service health
- `GET /ready` - Readiness check (DB/Redis connection)

### Monitoring

- Prometheus metrics at `/metrics`
- Structured JSON logging
- OpenTelemetry tracing support

### Scaling

- Stateless design (JWT + Redis)
- Horizontal scaling supported
- Database connection pooling
- Redis for session caching

## License

MIT License