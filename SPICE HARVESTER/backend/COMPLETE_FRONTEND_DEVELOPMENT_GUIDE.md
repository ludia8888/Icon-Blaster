# 🔥 SPICE HARVESTER Backend - Complete Frontend Development Guide

## 📋 Table of Contents

1. [System Architecture](#system-architecture)
2. [Services Overview](#services-overview)
3. [Complex Data Types System](#complex-data-types-system)
4. [Version Control System](#version-control-system)
5. [Security & Validation](#security--validation)
6. [Label Mapping System](#label-mapping-system)
7. [Merge Conflict Resolution](#merge-conflict-resolution)
8. [Database Management](#database-management)
9. [Query System](#query-system)
10. [Authentication & Authorization](#authentication--authorization)
11. [Error Handling](#error-handling)
12. [WebSocket & Real-time Features](#websocket--real-time-features)
13. [Testing & Development](#testing--development)
14. [Production Deployment](#production-deployment)

---

## 🏗️ System Architecture

### Service Architecture
The SPICE HARVESTER backend follows a **microservices architecture** with two main services:

1. **Backend-for-Frontend (BFF)** - Port 8002
   - User-facing API layer
   - Data aggregation and transformation
   - Label mapping and localization
   - Merge conflict resolution

2. **Ontology Management Service (OMS)** - Port 8000
   - Core ontology operations
   - TerminusDB integration
   - Version control (Git-like)
   - Advanced relationship management

### Technology Stack
- **FastAPI** - REST API framework
- **TerminusDB** - Graph database for ontologies
- **httpx** - Async HTTP client
- **SQLite** - Label mapping persistence
- **Pydantic** - Data validation
- **WebSocket** - Real-time updates

---

## 🌐 Services Overview

### 1. Backend-for-Frontend (BFF) Service
**Base URL**: `http://localhost:8002`

#### Available Endpoints:
- **Ontology Management**: `/api/v1/ontology/{db_name}/`
- **Query System**: `/api/v1/query/{db_name}/`
- **Label Mappings**: `/api/v1/database/{db_name}/mappings/`
- **Merge Conflicts**: `/api/v1/database/{db_name}/merge/`

### 2. Ontology Management Service (OMS)
**Base URL**: `http://localhost:8000`

#### Available Endpoints:
- **Database**: `/api/v1/database/`
- **Ontology**: `/api/v1/ontology/{db_name}/`
- **Version Control**: `/api/v1/version/{db_name}/`
- **Branch Management**: `/api/v1/branch/{db_name}/`

---

## 🔥 Complex Data Types System

### Supported Data Types

#### Basic Types (XSD):
```typescript
type BasicDataType = 
  | "xsd:string" | "xsd:integer" | "xsd:decimal" | "xsd:boolean"
  | "xsd:date" | "xsd:dateTime" | "xsd:time" | "xsd:duration"
  | "xsd:anyURI" | "xsd:base64Binary" | "xsd:hexBinary"
  | "xsd:normalizedString" | "xsd:token" | "xsd:language"
  | "xsd:double" | "xsd:float" | "xsd:long" | "xsd:int"
  | "xsd:short" | "xsd:byte" | "xsd:nonNegativeInteger"
  | "xsd:positiveInteger" | "xsd:nonPositiveInteger"
  | "xsd:negativeInteger" | "xsd:unsignedLong"
  | "xsd:unsignedInt" | "xsd:unsignedShort" | "xsd:unsignedByte"
  | "xsd:gYear" | "xsd:gMonth" | "xsd:gDay" | "xsd:gYearMonth"
  | "xsd:gMonthDay" | "xsd:QName" | "xsd:NOTATION";
```

#### 🔥 Complex Types (Custom):
```typescript
type ComplexDataType = 
  | "custom:array"      // Dynamic arrays with validation
  | "custom:object"     // Nested objects with schema validation
  | "custom:enum"       // Enumeration with localized labels
  | "custom:money"      // Currency with precision and locale
  | "custom:phone"      // International phone number validation
  | "custom:email"      // Email validation with domain checking
  | "custom:coordinate" // Geographic coordinates (lat/lng)
  | "custom:address"    // Structured postal addresses
  | "custom:image"      // Image metadata with validation
  | "custom:file";      // File attachments with type checking
```

### Complex Type Usage Examples

#### 1. Array Type
```typescript
// Request Body
{
  "id": "Product",
  "properties": {
    "tags": {
      "type": "custom:array",
      "constraints": {
        "items": {
          "type": "xsd:string",
          "maxLength": 50
        },
        "minItems": 1,
        "maxItems": 10,
        "uniqueItems": true
      }
    }
  }
}

// Valid Data
{
  "tags": ["electronics", "mobile", "smartphone"]
}
```

#### 2. Object Type
```typescript
// Request Body
{
  "id": "Person",
  "properties": {
    "address": {
      "type": "custom:object",
      "constraints": {
        "properties": {
          "street": {"type": "xsd:string", "maxLength": 100},
          "city": {"type": "xsd:string", "maxLength": 50},
          "zipCode": {"type": "xsd:string", "pattern": "\\d{5}"}
        },
        "required": ["street", "city"]
      }
    }
  }
}

// Valid Data
{
  "address": {
    "street": "123 Main St",
    "city": "Seoul",
    "zipCode": "12345"
  }
}
```

#### 3. Money Type
```typescript
// Request Body
{
  "id": "Product",
  "properties": {
    "price": {
      "type": "custom:money",
      "constraints": {
        "currency": "KRW",
        "precision": 2,
        "minimum": 0,
        "maximum": 10000000
      }
    }
  }
}

// Valid Data
{
  "price": {
    "amount": 29900,
    "currency": "KRW"
  }
}
```

#### 4. Email Type
```typescript
// Request Body
{
  "id": "User",
  "properties": {
    "email": {
      "type": "custom:email",
      "constraints": {
        "domains": ["company.com", "gmail.com"],
        "maxLength": 255
      }
    }
  }
}

// Valid Data
{
  "email": "user@company.com"
}
```

#### 5. Coordinate Type
```typescript
// Request Body
{
  "id": "Location",
  "properties": {
    "position": {
      "type": "custom:coordinate",
      "constraints": {
        "crs": "EPSG:4326",
        "precision": 6
      }
    }
  }
}

// Valid Data
{
  "position": {
    "latitude": 37.5665,
    "longitude": 126.9780
  }
}
```

---

## 🔀 Version Control System

### Git-Like Operations

#### 1. Branch Management
```typescript
// List branches
GET /api/v1/branch/{db_name}/list

// Create branch
POST /api/v1/branch/{db_name}/create
{
  "branch_name": "feature/new-ontology",
  "from_branch": "main"
}

// Delete branch
DELETE /api/v1/branch/{db_name}/branch/{branch_name}?force=false

// Checkout branch
POST /api/v1/branch/{db_name}/checkout
{
  "target": "develop",
  "target_type": "branch"
}
```

#### 2. Commit Operations
```typescript
// Create commit
POST /api/v1/version/{db_name}/commit
{
  "message": "Add new product ontology",
  "author": "admin"
}

// Get commit history
GET /api/v1/version/{db_name}/history?branch=main&limit=10&offset=0

// Get diff between commits
GET /api/v1/version/{db_name}/diff?from_ref=main&to_ref=feature/new-ontology
```

#### 3. Merge Operations
```typescript
// Merge branches
POST /api/v1/version/{db_name}/merge
{
  "source_branch": "feature/new-ontology",
  "target_branch": "main",
  "strategy": "auto"
}

// Rollback to commit
POST /api/v1/version/{db_name}/rollback
{
  "target": "HEAD~1"
}

// Rebase branch
POST /api/v1/version/{db_name}/rebase?onto=main&branch=feature/new-ontology
```

---

## 🔒 Security & Validation

### Input Sanitization
All user inputs are automatically sanitized using the comprehensive `InputSanitizer` class:

#### Security Patterns Detected:
- **SQL Injection**: `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `DROP`, `--`, `/*`, etc.
- **XSS**: `<script>`, `<iframe>`, `javascript:`, `eval()`, etc.
- **Path Traversal**: `../`, `..\\`, URL encoded variants
- **Command Injection**: Shell metacharacters, command patterns
- **NoSQL Injection**: `$where`, `$ne`, `$regex`, etc.
- **LDAP Injection**: Filter patterns, special characters

#### Request Validation Middleware
```typescript
// Security Configuration
{
  "MAX_REQUEST_SIZE": 10 * 1024 * 1024, // 10MB
  "MAX_JSON_DEPTH": 10,
  "MAX_FIELD_LENGTH": 1000,
  "MAX_ARRAY_LENGTH": 1000,
  "MAX_REQUESTS_PER_MINUTE": 100,
  "MAX_REQUESTS_PER_HOUR": 1000
}

// Automatic Security Headers
{
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "X-XSS-Protection": "1; mode=block",
  "Referrer-Policy": "strict-origin-when-cross-origin"
}
```

### Authentication & Authorization
```typescript
// Database name validation
function validateDbName(name: string): boolean {
  return /^[a-zA-Z][a-zA-Z0-9_-]*$/.test(name);
}

// Branch name validation
function validateBranchName(name: string): boolean {
  return /^[a-zA-Z0-9_/-]+$/.test(name);
}

// Class ID validation
function validateClassId(id: string): boolean {
  return /^[a-zA-Z][a-zA-Z0-9_:-]*$/.test(id);
}
```

---

## 🏷️ Label Mapping System

### Multi-Language Support
The system supports comprehensive label mapping for internationalization:

#### 1. Export Mappings
```typescript
// Export all mappings
GET /api/v1/database/{db_name}/mappings/export

// Response
{
  "db_name": "product_ontology",
  "classes": [
    {
      "class_id": "Product",
      "label": "제품",
      "label_lang": "ko",
      "description": "제품 정보"
    }
  ],
  "properties": [
    {
      "property_id": "name",
      "label": "이름",
      "label_lang": "ko"
    }
  ],
  "relationships": [
    {
      "predicate": "hasCategory",
      "label": "카테고리",
      "label_lang": "ko"
    }
  ]
}
```

#### 2. Import Mappings
```typescript
// Import with file upload
POST /api/v1/database/{db_name}/mappings/import
Content-Type: multipart/form-data

// Security features:
// - File size limit: 10MB
// - Content type validation
// - Schema validation
// - Integrity checks (SHA256)
// - Rollback on failure
```

#### 3. Mapping Statistics
```typescript
// Get mapping summary
GET /api/v1/database/{db_name}/mappings/

// Response
{
  "database": "product_ontology",
  "total": {
    "classes": 25,
    "properties": 150,
    "relationships": 45
  },
  "by_language": {
    "ko": {"classes": 25, "properties": 150, "relationships": 45},
    "en": {"classes": 25, "properties": 150, "relationships": 45},
    "ja": {"classes": 12, "properties": 80, "relationships": 20}
  }
}
```

---

## ⚔️ Merge Conflict Resolution

### Foundry-Style Conflict Resolution

#### 1. Simulate Merge
```typescript
// Simulate merge to detect conflicts
POST /api/v1/database/{db_name}/merge/simulate
{
  "source_branch": "feature/new-ontology",
  "target_branch": "main",
  "strategy": "merge"
}

// Response
{
  "status": "success",
  "message": "병합 시뮬레이션 완료: 3개 충돌 감지",
  "data": {
    "merge_preview": {
      "source_branch": "feature/new-ontology",
      "target_branch": "main",
      "conflicts": [
        {
          "path": "Product.name",
          "type": "content_conflict",
          "source_change": {
            "type": "modified",
            "new_value": "Product Name v2",
            "old_value": "Product Name"
          },
          "target_change": {
            "type": "modified",
            "new_value": "Product Title",
            "old_value": "Product Name"
          }
        }
      ],
      "statistics": {
        "changes_to_apply": 15,
        "conflicts_detected": 3,
        "mergeable": false,
        "requires_manual_resolution": true
      }
    }
  }
}
```

#### 2. Resolve Conflicts
```typescript
// Resolve conflicts manually
POST /api/v1/database/{db_name}/merge/resolve
{
  "source_branch": "feature/new-ontology",
  "target_branch": "main",
  "strategy": "merge",
  "message": "Resolve conflicts: Product name updates",
  "author": "admin@company.com",
  "resolutions": [
    {
      "path": "Product.name",
      "resolution_type": "use_value",
      "resolved_value": "Product Title v2",
      "metadata": {
        "reason": "Combine both changes"
      }
    }
  ]
}
```

---

## 🗄️ Database Management

### Database Operations

#### 1. Create Database
```typescript
POST /api/v1/database/create
{
  "name": "product_ontology",
  "description": "Product catalog ontology"
}
```

#### 2. List Databases
```typescript
GET /api/v1/database/list

// Response
{
  "databases": [
    {
      "name": "product_ontology",
      "description": "Product catalog ontology",
      "created_at": "2024-01-01T00:00:00Z",
      "size": "15.2MB",
      "status": "active"
    }
  ]
}
```

#### 3. Database Status
```typescript
GET /api/v1/database/exists/{db_name}

// Response
{
  "exists": true,
  "name": "product_ontology",
  "status": "active",
  "branches": ["main", "develop"],
  "current_branch": "main"
}
```

---

## 🔍 Query System

### Structured Query Interface

#### 1. Basic Query
```typescript
POST /api/v1/query/{db_name}/execute
{
  "type": "select",
  "class_id": "Product",
  "filters": [
    {
      "property": "category",
      "operator": "eq",
      "value": "electronics"
    }
  ],
  "limit": 10,
  "offset": 0
}
```

#### 2. Complex Query with Relationships
```typescript
POST /api/v1/query/{db_name}/execute
{
  "type": "select",
  "class_id": "Product",
  "filters": [
    {
      "property": "price",
      "operator": "gte",
      "value": {
        "amount": 100000,
        "currency": "KRW"
      }
    }
  ],
  "relationships": [
    {
      "predicate": "hasCategory",
      "target_class": "Category",
      "direction": "outgoing"
    }
  ],
  "include_labels": true,
  "language": "ko"
}
```

#### 3. Aggregation Query
```typescript
POST /api/v1/query/{db_name}/execute
{
  "type": "count",
  "class_id": "Product",
  "filters": [
    {
      "property": "status",
      "operator": "eq",
      "value": "active"
    }
  ],
  "group_by": ["category"]
}
```

---

## 🔄 Relationship Management

### Advanced Relationship Features

#### 1. Circular Reference Detection
```typescript
// Automatic detection during ontology creation
POST /api/v1/ontology/{db_name}/create
{
  "id": "Category",
  "relationships": [
    {
      "predicate": "hasParent",
      "target_class": "Category",
      "cardinality": "many_to_one"
    }
  ]
}

// System automatically detects and prevents circular references
```

#### 2. Relationship Path Tracking
```typescript
// Find path between entities
GET /api/v1/ontology/{db_name}/path?from=Product&to=Brand

// Response
{
  "paths": [
    {
      "length": 2,
      "relationships": [
        {"predicate": "hasCategory", "target": "Category"},
        {"predicate": "hasBrand", "target": "Brand"}
      ]
    }
  ]
}
```

#### 3. Relationship Validation
```typescript
// Validation results with severity levels
{
  "validation_results": [
    {
      "severity": "error",
      "message": "Circular reference detected",
      "path": "Product -> Category -> Product"
    },
    {
      "severity": "warning",
      "message": "Deep relationship nesting (>5 levels)",
      "path": "Product -> Category -> SubCategory -> ..."
    }
  ]
}
```

---

## 🌐 WebSocket & Real-time Features

### Real-time Updates
```typescript
// WebSocket connection for real-time updates
const ws = new WebSocket('ws://localhost:8000/ws/updates/{db_name}');

// Message types
interface UpdateMessage {
  type: 'ontology_created' | 'ontology_updated' | 'ontology_deleted' | 'merge_completed';
  data: {
    entity_id: string;
    database: string;
    timestamp: string;
    changes: any;
  };
}

// Subscribe to specific events
ws.send(JSON.stringify({
  action: 'subscribe',
  events: ['ontology_created', 'merge_completed']
}));
```

---

## 📊 Error Handling

### Standardized Error Responses

#### 1. Validation Errors
```typescript
// HTTP 400 - Bad Request
{
  "status": "error",
  "message": "Validation failed",
  "detail": "Email format is invalid",
  "code": "VALIDATION_ERROR",
  "field": "email"
}
```

#### 2. Security Violations
```typescript
// HTTP 400 - Bad Request
{
  "status": "error",
  "message": "Security violation detected",
  "detail": "SQL injection pattern detected",
  "code": "SECURITY_VIOLATION"
}
```

#### 3. Conflict Errors
```typescript
// HTTP 409 - Conflict
{
  "status": "error",
  "message": "Merge conflict detected",
  "detail": "Manual resolution required",
  "code": "MERGE_CONFLICT",
  "conflicts": [...]
}
```

#### 4. Not Found Errors
```typescript
// HTTP 404 - Not Found
{
  "status": "error",
  "message": "Resource not found",
  "detail": "Database 'test_db' does not exist",
  "code": "NOT_FOUND"
}
```

---

## 🧪 Testing & Development

### Development Environment Setup

#### 1. Start Services
```bash
# Start all services
cd /Users/isihyeon/Desktop/SPICE\ HARVESTER/backend
./start_services.sh

# Services will be available at:
# - BFF: http://localhost:8002
# - OMS: http://localhost:8000
# - TerminusDB: http://localhost:6363
```

#### 2. Health Checks
```typescript
// Check service health
GET http://localhost:8002/health  // BFF
GET http://localhost:8000/health  // OMS

// Expected response
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z",
  "services": {
    "database": "connected",
    "terminus": "connected"
  }
}
```

#### 3. Test Complex Types
```typescript
// Test complex type validation
POST http://localhost:8002/api/v1/ontology/test_db/create
{
  "id": "TestClass",
  "properties": {
    "email": {
      "type": "custom:email",
      "constraints": {
        "domains": ["test.com"]
      }
    }
  }
}
```

---

## 🚀 Production Deployment

### Production Considerations

#### 1. Environment Variables
```bash
# Required environment variables
TERMINUS_DB_URL=http://terminusdb:6363
TERMINUS_DB_USER=admin
TERMINUS_DB_PASSWORD=password
BFF_PORT=8002
OMS_PORT=8000
DATABASE_PATH=/data/label_mappings.db
LOG_LEVEL=INFO
```

#### 2. Security Configuration
```typescript
// Production security settings
{
  "ALLOWED_ORIGINS": ["https://yourapp.com"],
  "RATE_LIMIT_ENABLED": true,
  "CORS_CREDENTIALS": true,
  "HTTPS_ONLY": true,
  "CSRF_PROTECTION": true
}
```

#### 3. Monitoring & Logging
```typescript
// Structured logging format
{
  "timestamp": "2024-01-01T00:00:00Z",
  "level": "INFO",
  "service": "BFF",
  "message": "Ontology created",
  "context": {
    "database": "product_ontology",
    "class_id": "Product",
    "user": "admin"
  }
}
```

---

## 📱 Frontend Integration Examples

### React Integration

#### 1. API Client Setup
```typescript
// api/client.ts
class SpiceHarvesterClient {
  private bffUrl = 'http://localhost:8002';
  private omsUrl = 'http://localhost:8000';
  
  async createOntology(dbName: string, ontologyData: any) {
    const response = await fetch(`${this.bffUrl}/api/v1/ontology/${dbName}/create`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(ontologyData),
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    return response.json();
  }
  
  async queryOntologies(dbName: string, queryData: any) {
    const response = await fetch(`${this.bffUrl}/api/v1/query/${dbName}/execute`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(queryData),
    });
    
    return response.json();
  }
}
```

#### 2. Complex Types Form Component
```typescript
// components/ComplexTypeForm.tsx
import React, { useState } from 'react';

interface ComplexTypeFormProps {
  onSubmit: (data: any) => void;
}

const ComplexTypeForm: React.FC<ComplexTypeFormProps> = ({ onSubmit }) => {
  const [formData, setFormData] = useState({
    id: '',
    properties: {}
  });
  
  const handleAddProperty = (name: string, type: string, constraints: any) => {
    setFormData(prev => ({
      ...prev,
      properties: {
        ...prev.properties,
        [name]: {
          type,
          constraints
        }
      }
    }));
  };
  
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(formData); }}>
      {/* Email property */}
      <div>
        <label>Email Property:</label>
        <input 
          type="text" 
          placeholder="Property name"
          onChange={(e) => handleAddProperty(e.target.value, 'custom:email', {
            domains: ['company.com'],
            maxLength: 255
          })}
        />
      </div>
      
      {/* Money property */}
      <div>
        <label>Money Property:</label>
        <input 
          type="text" 
          placeholder="Property name"
          onChange={(e) => handleAddProperty(e.target.value, 'custom:money', {
            currency: 'KRW',
            precision: 2,
            minimum: 0
          })}
        />
      </div>
      
      <button type="submit">Create Ontology</button>
    </form>
  );
};
```

#### 3. Version Control Component
```typescript
// components/VersionControl.tsx
import React, { useState, useEffect } from 'react';

const VersionControl: React.FC<{ dbName: string }> = ({ dbName }) => {
  const [branches, setBranches] = useState([]);
  const [currentBranch, setCurrentBranch] = useState('');
  
  useEffect(() => {
    fetchBranches();
  }, [dbName]);
  
  const fetchBranches = async () => {
    const response = await fetch(`http://localhost:8000/api/v1/branch/${dbName}/list`);
    const data = await response.json();
    setBranches(data.branches);
    setCurrentBranch(data.current);
  };
  
  const createBranch = async (branchName: string) => {
    await fetch(`http://localhost:8000/api/v1/branch/${dbName}/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        branch_name: branchName,
        from_branch: currentBranch
      })
    });
    fetchBranches();
  };
  
  const checkout = async (branchName: string) => {
    await fetch(`http://localhost:8000/api/v1/branch/${dbName}/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target: branchName,
        target_type: 'branch'
      })
    });
    fetchBranches();
  };
  
  return (
    <div>
      <h3>Version Control</h3>
      <p>Current Branch: <strong>{currentBranch}</strong></p>
      
      <div>
        <h4>Branches:</h4>
        <ul>
          {branches.map((branch: any) => (
            <li key={branch.name}>
              {branch.name} 
              {branch.current && <span> (current)</span>}
              {!branch.current && (
                <button onClick={() => checkout(branch.name)}>
                  Checkout
                </button>
              )}
            </li>
          ))}
        </ul>
      </div>
      
      <div>
        <input 
          type="text" 
          placeholder="New branch name"
          onKeyPress={(e) => {
            if (e.key === 'Enter') {
              createBranch(e.target.value);
              e.target.value = '';
            }
          }}
        />
      </div>
    </div>
  );
};
```

---

## 🎯 Best Practices & Recommendations

### 1. Data Validation
- Always validate complex type constraints on the frontend
- Use TypeScript interfaces that match Pydantic models
- Implement client-side validation for better UX

### 2. Error Handling
- Implement retry logic for network failures
- Show user-friendly error messages
- Log errors for debugging

### 3. Performance Optimization
- Use pagination for large datasets
- Implement caching for frequently accessed data
- Consider using WebSocket for real-time updates

### 4. Security
- Sanitize all user inputs
- Validate file uploads (size, type, content)
- Use HTTPS in production

### 5. Internationalization
- Leverage the label mapping system
- Support multiple languages
- Use locale-specific formatting

---

This comprehensive guide covers ALL implemented features in the SPICE HARVESTER backend. Use this as your complete reference for frontend development, integrating with the complex types system, version control, security features, and all available services.

For any questions or additional features, refer to the specific endpoint documentation or contact the development team.

**🔥 THINK ULTRA! This guide represents the complete implementation of the SPICE HARVESTER backend - every feature, every endpoint, every capability has been documented for your frontend development needs.**