# SonarQube Integration Guide

## Overview

SonarQube is integrated into the Arrakis Project to provide continuous code quality inspection, security analysis, and technical debt tracking.

## Features

- 🔍 **Code Quality Analysis**: Detects code smells, bugs, and vulnerabilities
- 📊 **Coverage Reports**: Tracks test coverage across all packages
- 🔒 **Security Analysis**: Identifies security hotspots and vulnerabilities
- 📈 **Technical Debt**: Measures and tracks technical debt over time
- 🎯 **Quality Gates**: Enforces quality standards before merging

## Local Setup

### 1. Start SonarQube

```bash
# Using the setup script
./scripts/setup-sonarqube.sh

# Or manually
npm run sonar:local
```

### 2. Configure SonarQube

1. Access SonarQube at http://localhost:9000
2. Login with default credentials: `admin/admin`
3. Change the default password when prompted
4. Create a new project:
   - Project key: `arrakis-project`
   - Display name: `Arrakis Project`
5. Generate an authentication token and save it

### 3. Configure Environment

Create a `.env` file in the project root:

```env
SONAR_HOST_URL=http://localhost:9000
SONAR_TOKEN=your_generated_token_here
```

## Running Analysis

### Local Analysis

```bash
# Run tests with coverage
npm run test:coverage

# Run SonarQube analysis
npm run sonar
```

### CI/CD Analysis

The analysis runs automatically on:
- Push to `main` or `develop` branches
- Pull requests
- Manual workflow dispatch

## Quality Gates

Our project enforces the following quality gates:

| Metric | Threshold | Description |
|--------|-----------|-------------|
| Coverage | ≥ 80% | Overall test coverage |
| Duplicated Lines | < 3% | Code duplication |
| Maintainability Rating | A | Technical debt ratio |
| Reliability Rating | A | Bug density |
| Security Rating | A | Vulnerability density |
| Security Hotspots | 0 | Potential security issues |

## Project Configuration

### sonar-project.properties

```properties
sonar.projectKey=arrakis-project
sonar.sources=packages/backend/src,packages/frontend/src,packages/shared/src
sonar.exclusions=**/*.test.ts,**/node_modules/**,**/dist/**
sonar.javascript.lcov.reportPaths=packages/*/coverage/lcov.info
```

### TypeScript Specific Settings

- Uses `tsconfig.json` for type information
- Analyzes `.ts`, `.tsx` files
- Excludes test files from main analysis
- Includes test files for test coverage

## Best Practices

### 1. Fix Issues Promptly

```typescript
// ❌ Code smell: Complex function
function processData(data: any) {
  if (data) {
    if (data.type === 'A') {
      // ... 50 lines of code
    } else if (data.type === 'B') {
      // ... 50 lines of code
    }
  }
}

// ✅ Refactored
function processData(data: DataType) {
  const processor = getProcessor(data.type);
  return processor.process(data);
}
```

### 2. Write Testable Code

```typescript
// ❌ Hard to test
class UserService {
  async createUser(data: CreateUserDto) {
    const user = new User(data);
    await database.save(user);
    await emailService.sendWelcome(user.email);
    return user;
  }
}

// ✅ Testable with dependency injection
class UserService {
  constructor(
    private db: Database,
    private emailService: EmailService
  ) {}

  async createUser(data: CreateUserDto) {
    const user = new User(data);
    await this.db.save(user);
    await this.emailService.sendWelcome(user.email);
    return user;
  }
}
```

### 3. Avoid Security Issues

```typescript
// ❌ SQL Injection vulnerability
const query = `SELECT * FROM users WHERE id = ${userId}`;

// ✅ Parameterized query
const query = 'SELECT * FROM users WHERE id = $1';
const result = await db.query(query, [userId]);
```

## Common Issues and Solutions

### Issue: Low Coverage

**Solution**: Add tests for uncovered code paths

```bash
# Check coverage report
open coverage/lcov-report/index.html
```

### Issue: Code Duplication

**Solution**: Extract common code into utilities

```typescript
// Before: Duplicated validation
function validateUser(user: User) {
  if (!user.email || !isValidEmail(user.email)) {
    throw new Error('Invalid email');
  }
}

function validateContact(contact: Contact) {
  if (!contact.email || !isValidEmail(contact.email)) {
    throw new Error('Invalid email');
  }
}

// After: Shared validation
function validateEmail(email: string | undefined): asserts email is string {
  if (!email || !isValidEmail(email)) {
    throw new Error('Invalid email');
  }
}
```

### Issue: Cognitive Complexity

**Solution**: Break down complex functions

```typescript
// Before: High complexity
function processOrder(order: Order) {
  // 15+ branches and loops
}

// After: Reduced complexity
function processOrder(order: Order) {
  validateOrder(order);
  const items = prepareItems(order.items);
  const total = calculateTotal(items);
  return createInvoice(order, items, total);
}
```

## GitHub Integration

### Pull Request Comments

SonarQube automatically comments on PRs with:
- New issues introduced
- Coverage changes
- Quality gate status

### Branch Analysis

- Feature branches are analyzed independently
- Results are compared against the target branch
- New code must meet higher standards

## Monitoring

### Dashboards

Access project dashboards at:
- http://localhost:9000/dashboard?id=arrakis-project

### Metrics to Watch

1. **Code Coverage Trend**: Should increase over time
2. **Technical Debt Ratio**: Should stay below 5%
3. **New Code Coverage**: Should be > 80%
4. **Security Hotspots**: Should be 0

## Troubleshooting

### SonarQube Won't Start

```bash
# Check logs
docker-compose -f docker-compose.sonarqube.yml logs

# Restart containers
npm run sonar:stop
npm run sonar:local
```

### Analysis Fails

```bash
# Check configuration
sonar-scanner -X  # Debug mode

# Verify paths
ls -la packages/*/coverage/lcov.info
```

### Token Issues

1. Regenerate token in SonarQube UI
2. Update `.env` file
3. Restart analysis

## Advanced Configuration

### Custom Rules

Create `.sonarjs.json` for JavaScript/TypeScript rules:

```json
{
  "rules": {
    "max-lines-per-function": {
      "maximum": 30
    },
    "cognitive-complexity": {
      "threshold": 10
    }
  }
}
```

### Exclusions

Update `sonar-project.properties`:

```properties
# Exclude generated files
sonar.exclusions=**/*.generated.ts,**/migrations/**

# Exclude from duplication detection
sonar.cpd.exclusions=**/*Schema.ts
```

## Resources

- [SonarQube Documentation](https://docs.sonarqube.org/latest/)
- [TypeScript Plugin](https://github.com/SonarSource/sonar-typescript)
- [Quality Gates](https://docs.sonarqube.org/latest/user-guide/quality-gates/)
- [Security Hotspots](https://docs.sonarqube.org/latest/user-guide/security-hotspots/)