# Environment Configuration Guide

This document explains how to configure Icon Blaster for different environments (development, production).

## 🚀 Quick Setup

### 1. Development Environment

```bash
# Copy the example environment file
cp .env.example .env.local

# Edit .env.local with your actual values
# Minimum required: OPENAI_API_KEY
```

### 2. Production Environment

Use Vercel Dashboard or your hosting provider to set environment variables from `.env.production`.

## 📁 Environment Files

| File | Purpose | When Used |
|------|---------|-----------|
| `.env.local` | Local development | `npm run dev` |
| `.env.development` | Development defaults | Fallback for dev |
| `.env.production` | Production defaults | `npm run build` |
| `.env.example` | Template/Documentation | Reference only |

## ⚙️ Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for DALL-E | `sk-proj-...` |

### Optional Variables

#### Server Configuration
| Variable | Development Default | Production Default | Description |
|----------|--------------------|--------------------|-------------|
| `NODE_ENV` | `development` | `production` | Environment mode |
| `PORT` | `3002` | `3000` | Server port |
| `NEXT_PUBLIC_APP_URL` | `http://localhost:3002` | `https://your-domain.com` | Application URL |

#### Application Settings
| Variable | Development Default | Production Default | Description |
|----------|--------------------|--------------------|-------------|
| `NEXT_PUBLIC_DEBUG_MODE` | `true` | `false` | Enable debug logging |
| `NEXT_PUBLIC_MOCK_API` | `false` | `false` | Use mock API responses |

#### Rate Limiting
| Variable | Development Default | Production Default | Description |
|----------|--------------------|--------------------|-------------|
| `RATE_LIMIT_MAX` | `50` | `10` | Max requests per window |
| `RATE_LIMIT_WINDOW_MS` | `60000` | `60000` | Rate limit window (ms) |

#### Security Settings
| Variable | Development Default | Production Default | Description |
|----------|--------------------|--------------------|-------------|
| `SECURITY_STRICT_MODE` | `false` | `true` | Enable strict security |
| `CORS_ORIGINS` | `http://localhost:3002` | `https://your-domain.com` | Allowed CORS origins |

## 🔧 Configuration Usage

```typescript
import { useConfig } from '@/lib/config';

const config = useConfig();

if (config.isDevelopment) {
  console.log('Running in development mode');
}

// Rate limiting
const maxRequests = config.rateLimitMax;

// Security
if (config.securityStrictMode) {
  // Apply strict security measures
}
```

## 🌍 Environment-Specific Behavior

### Development Environment
- **Port**: 3002 (avoids conflict with Grafana on 3000)
- **Rate Limiting**: 50 requests/minute (more permissive)
- **Security**: Less strict (easier debugging)
- **Debug Logging**: Enabled
- **CORS**: Local origins allowed

### Production Environment  
- **Port**: 3000 (standard)
- **Rate Limiting**: 10 requests/minute (stricter)
- **Security**: Strict mode enabled
- **Debug Logging**: Disabled
- **CORS**: Production domains only

## 🚀 Deployment

### Vercel Deployment

1. **Set Environment Variables in Vercel Dashboard:**
   ```
   OPENAI_API_KEY=sk-your-actual-key
   NODE_ENV=production
   NEXT_PUBLIC_APP_URL=https://your-app.vercel.app
   ```

2. **Deploy:**
   ```bash
   vercel --prod
   ```

### Other Platforms

1. **Set environment variables** according to your platform
2. **Use production values** from `.env.production`
3. **Ensure** `NODE_ENV=production` is set

## 🔍 Environment Validation

The application validates required environment variables on startup:

- **Development**: Warnings for missing optional variables
- **Production**: Strict validation, fails if required variables missing

## 🛠️ Development Tips

### View Current Configuration
```typescript
import { logConfig } from '@/lib/config';

// In development, logs current config to console
logConfig();
```

### Override Environment Locally
Create `.env.local` with overrides:
```bash
# Override just what you need
RATE_LIMIT_MAX=100
NEXT_PUBLIC_DEBUG_MODE=false
```

### Test Production-like Environment Locally
```bash
NODE_ENV=production npm run dev
```

## 🔐 Security Notes

- **Never commit** `.env.local` or actual API keys
- **Use different API keys** for development vs production
- **Set strict CORS origins** in production
- **Enable security strict mode** in production

## 📋 Environment Checklist

### Development Setup
- [ ] Copy `.env.example` to `.env.local`
- [ ] Set `OPENAI_API_KEY`
- [ ] Verify app runs on http://localhost:3002
- [ ] Check debug logs appear in console

### Production Setup
- [ ] Set all required environment variables
- [ ] Use production OpenAI API key
- [ ] Set correct `NEXT_PUBLIC_APP_URL`
- [ ] Enable `SECURITY_STRICT_MODE=true`
- [ ] Configure proper `CORS_ORIGINS`
- [ ] Test rate limiting works
- [ ] Verify no debug info exposed

## 🆘 Troubleshooting

### Server Won't Start
1. Check all required environment variables are set
2. Verify OpenAI API key format (starts with `sk-`)
3. Ensure port isn't already in use

### API Errors
1. Verify `OPENAI_API_KEY` is valid
2. Check API key has sufficient credits
3. Verify `NEXT_PUBLIC_APP_URL` matches your domain

### Rate Limiting Issues
1. Adjust `RATE_LIMIT_MAX` for your needs
2. Check `RATE_LIMIT_WINDOW_MS` setting
3. Test with different IP addresses

---

For more help, see the main [README.md](./README.md) or check the [troubleshooting guide](./Docs/TROUBLESHOOTING.md).