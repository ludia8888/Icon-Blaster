# Security Configuration Guide

## Authentication

### TerminusDB Authentication
The system uses HTTP Basic Authentication for TerminusDB connections, as required by TerminusDB.

#### Security Best Practices:

1. **Use Environment Variables**
   - Never hardcode credentials in source code
   - Set `TERMINUS_USER` and `TERMINUS_KEY` in environment variables
   - Use `.env` file for local development (never commit to git)

2. **Use HTTPS in Production**
   - Always use `https://` URLs for TerminusDB in production
   - The system will warn if using HTTP for non-localhost connections

3. **Credential Rotation**
   - Regularly rotate TerminusDB credentials
   - Update environment variables when credentials change

## Input Validation

All user inputs are validated using:
- `validate_db_name()` - Validates database names
- `validate_class_id()` - Validates ontology class IDs
- `sanitize_input()` - General input sanitization

## Security Headers

The application adds security headers to all HTTP requests:
- `X-Request-ID` - For request tracking and debugging
- `User-Agent` - Identifies the service making requests

## Environment Variables

Required security-related environment variables:
```bash
# TerminusDB Credentials (Required)
TERMINUS_USER=admin
TERMINUS_KEY=your_secure_key_here  # Generate a strong key

# JWT/Session Security (Required for auth features)
SECRET_KEY=your-secret-key-here  # Generate using: openssl rand -hex 32
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# HTTPS Configuration (Production)
TERMINUS_SERVER_URL=https://your-terminus-server.com
```

## Generating Secure Keys

### Generate Secret Key for JWT:
```bash
openssl rand -hex 32
```

### Generate Strong Password:
```bash
openssl rand -base64 32
```

## Security Checklist

Before deploying to production:
- [ ] All credentials are loaded from environment variables
- [ ] No secrets are hardcoded in source code
- [ ] HTTPS is enabled for all external connections
- [ ] Input validation is enabled on all endpoints
- [ ] Error messages don't expose sensitive information
- [ ] Logging doesn't include credentials or sensitive data
- [ ] Rate limiting is configured (if applicable)
- [ ] CORS is properly configured
- [ ] Database connections use SSL/TLS
- [ ] Regular security updates are scheduled

## Reporting Security Issues

If you discover a security vulnerability, please report it to:
- Email: security@spice-harvester.com
- Do not create public GitHub issues for security vulnerabilities