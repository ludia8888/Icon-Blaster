# 🔥 SPICE HARVESTER Frontend Development Guide

## 📋 목차
1. [시스템 개요](#시스템-개요)
2. [아키텍처 구조](#아키텍처-구조)
3. [API 엔드포인트](#api-엔드포인트)
4. [데이터 타입 시스템](#데이터-타입-시스템)
5. [복합 데이터 타입](#복합-데이터-타입)
6. [관계 관리 시스템](#관계-관리-시스템)
7. [요청/응답 스키마](#요청응답-스키마)
8. [에러 처리](#에러-처리)
9. [실제 사용 예시](#실제-사용-예시)
10. [테스트 가이드](#테스트-가이드)

---

## 시스템 개요

**SPICE HARVESTER**는 온톨로지 기반 데이터 관리 시스템으로, 다음과 같은 핵심 기능을 제공합니다:

### 핵심 기능
- **온톨로지 관리**: 클래스 생성, 수정, 삭제, 조회
- **복합 데이터 타입**: 10가지 고급 데이터 타입 지원
- **관계 관리**: 엔티티 간 관계 정의 및 관리
- **검증 시스템**: 실시간 데이터 검증 및 제약 조건 적용
- **다국어 지원**: 한국어/영어 레이블 및 설명 지원

### 백엔드 서비스
- **OMS (Ontology Management Service)**: 포트 8000
- **BFF (Backend for Frontend)**: 포트 8002
- **TerminusDB**: 포트 6363 (내부 그래프 데이터베이스)

---

## 아키텍처 구조

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   BFF (8002)    │    │   OMS (8000)    │
│   (React/D3.js)   │◄──►│   User-facing   │◄──►│   Internal API  │
│                 │    │   API           │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
                                              ┌─────────────────┐
                                              │  TerminusDB     │
                                              │  (6363)         │
                                              └─────────────────┘
```

### 권장 프론트엔드 아키텍처
```
src/
├── components/
│   ├── ontology/
│   │   ├── OntologyForm.vue
│   │   ├── OntologyList.vue
│   │   └── PropertyEditor.vue
│   ├── complex-types/
│   │   ├── PhoneInput.vue
│   │   ├── EmailInput.vue
│   │   ├── MoneyInput.vue
│   │   └── CoordinateInput.vue
│   └── relationships/
│       ├── RelationshipGraph.vue
│       └── RelationshipEditor.vue
├── services/
│   ├── api.js
│   ├── ontologyService.js
│   ├── complexTypeService.js
│   └── relationshipService.js
├── types/
│   ├── ontology.ts
│   ├── complexTypes.ts
│   └── api.ts
└── utils/
    ├── validation.js
    └── typeConverters.js
```

---

## API 엔드포인트

### 기본 URL
- **BFF (권장)**: `http://localhost:8002`
- **OMS (내부용)**: `http://localhost:8000`

### 🔑 인증 헤더
```javascript
{
  "Content-Type": "application/json",
  "Accept": "application/json"
}
```

### 1. 데이터베이스 관리

#### 데이터베이스 생성
```http
POST /api/v1/database/create
Content-Type: application/json

{
  "name": "my_ontology_db"
}
```

#### 데이터베이스 목록 조회
```http
GET /api/v1/database/list
```

#### 데이터베이스 존재 여부 확인
```http
GET /api/v1/database/exists/{db_name}
```

#### 데이터베이스 삭제
```http
DELETE /api/v1/database/{db_name}
```

### 2. 온톨로지 관리

#### 온톨로지 생성
```http
POST /api/v1/ontology/{db_name}/create
Content-Type: application/json

{
  "id": "Person",
  "label": "사람",
  "description": "사람을 나타내는 클래스",
  "properties": [
    {
      "name": "name",
      "label": "이름",
      "type": "xsd:string",
      "required": true
    },
    {
      "name": "phone",
      "label": "전화번호",
      "type": "custom:phone",
      "required": false,
      "constraints": {
        "format": "E164"
      }
    }
  ],
  "parent_class": null,
  "abstract": false
}
```

#### 온톨로지 목록 조회
```http
GET /api/v1/ontology/{db_name}/list?limit=100&offset=0
```

#### 온톨로지 조회
```http
GET /api/v1/ontology/{db_name}/{class_id}
```

#### 온톨로지 수정
```http
PUT /api/v1/ontology/{db_name}/{class_id}
Content-Type: application/json

{
  "label": "수정된 라벨",
  "description": "수정된 설명",
  "properties": [...]
}
```

#### 온톨로지 삭제
```http
DELETE /api/v1/ontology/{db_name}/{class_id}
```

#### 온톨로지 쿼리
```http
POST /api/v1/ontology/{db_name}/query
Content-Type: application/json

{
  "class_id": "Person",
  "filters": [
    {
      "field": "name",
      "operator": "contains",
      "value": "김"
    }
  ],
  "select": ["name", "phone"],
  "limit": 50,
  "offset": 0
}
```

### 3. 고급 관계 관리

#### 고급 관계 기능을 포함한 온톨로지 생성
```http
POST /api/v1/ontology/{db_name}/create-advanced
Content-Type: application/json

{
  "id": "Company",
  "label": "회사",
  "properties": [...],
  "auto_generate_inverse": true,
  "validate_relationships": true,
  "check_circular_references": true
}
```

#### 관계 검증
```http
POST /api/v1/ontology/{db_name}/validate-relationships
Content-Type: application/json

{
  "id": "Employee",
  "properties": [
    {
      "name": "works_for",
      "type": "relationship",
      "target_class": "Company",
      "cardinality": "many_to_one"
    }
  ]
}
```

#### 순환 참조 탐지
```http
POST /api/v1/ontology/{db_name}/detect-circular-references
Content-Type: application/json

{
  "id": "NewClass",
  "properties": [...]
}
```

#### 관계 경로 탐색
```http
GET /api/v1/ontology/{db_name}/relationship-paths/{start_entity}?end_entity={end_entity}&max_depth=5&path_type=shortest
```

#### 도달 가능한 엔티티 조회
```http
GET /api/v1/ontology/{db_name}/reachable-entities/{start_entity}?max_depth=3
```

#### 관계 네트워크 분석
```http
GET /api/v1/ontology/{db_name}/analyze-network
```

---

## 데이터 타입 시스템

### 기본 XSD 타입
```javascript
const XSD_TYPES = {
  STRING: 'xsd:string',
  INTEGER: 'xsd:integer',
  DECIMAL: 'xsd:decimal',
  BOOLEAN: 'xsd:boolean',
  DATE: 'xsd:date',
  DATETIME: 'xsd:dateTime',
  TIME: 'xsd:time',
  DURATION: 'xsd:duration',
  FLOAT: 'xsd:float',
  DOUBLE: 'xsd:double',
  BYTE: 'xsd:byte',
  SHORT: 'xsd:short',
  LONG: 'xsd:long',
  UNSIGNED_INT: 'xsd:unsignedInt',
  POSITIVE_INTEGER: 'xsd:positiveInteger',
  NON_NEGATIVE_INTEGER: 'xsd:nonNegativeInteger',
  NORMALIZED_STRING: 'xsd:normalizedString',
  TOKEN: 'xsd:token',
  LANGUAGE: 'xsd:language',
  NAME: 'xsd:Name',
  NCNAME: 'xsd:NCName',
  ID: 'xsd:ID',
  IDREF: 'xsd:IDREF',
  IDREFS: 'xsd:IDREFS',
  ENTITY: 'xsd:ENTITY',
  ENTITIES: 'xsd:ENTITIES',
  NMTOKEN: 'xsd:NMTOKEN',
  NMTOKENS: 'xsd:NMTOKENS',
  ANYURI: 'xsd:anyURI',
  QNAME: 'xsd:QName',
  NOTATION: 'xsd:NOTATION',
  BASE64_BINARY: 'xsd:base64Binary',
  HEX_BINARY: 'xsd:hexBinary'
};
```

---

## 복합 데이터 타입

### 🔥 THINK ULTRA! 10가지 복합 데이터 타입

#### 1. ARRAY (배열)
```javascript
{
  "name": "tags",
  "type": "custom:array",
  "constraints": {
    "item_type": "xsd:string",
    "min_items": 1,
    "max_items": 10
  }
}
```

#### 2. OBJECT (객체)
```javascript
{
  "name": "address",
  "type": "custom:object",
  "constraints": {
    "properties": {
      "street": "xsd:string",
      "city": "xsd:string",
      "postal_code": "xsd:string"
    },
    "required": ["street", "city"]
  }
}
```

#### 3. ENUM (열거형)
```javascript
{
  "name": "status",
  "type": "custom:enum",
  "constraints": {
    "enum_values": ["active", "inactive", "pending"]
  }
}
```

#### 4. MONEY (화폐)
```javascript
{
  "name": "salary",
  "type": "custom:money",
  "constraints": {
    "currency": "KRW",
    "min_amount": 0,
    "max_amount": 1000000000
  }
}
```

#### 5. PHONE (전화번호)
```javascript
{
  "name": "phone",
  "type": "custom:phone",
  "constraints": {
    "format": "E164",  // 또는 "NATIONAL", "INTERNATIONAL"
    "region": "KR"
  }
}
```

#### 6. EMAIL (이메일)
```javascript
{
  "name": "email",
  "type": "custom:email",
  "constraints": {
    "allow_international": true,
    "require_tld": true
  }
}
```

#### 7. COORDINATE (좌표)
```javascript
{
  "name": "location",
  "type": "custom:coordinate",
  "constraints": {
    "format": "decimal",  // 또는 "dms"
    "precision": 6
  }
}
```

#### 8. ADDRESS (주소)
```javascript
{
  "name": "address",
  "type": "custom:address",
  "constraints": {
    "country": "KR",
    "format": "korean"
  }
}
```

#### 9. IMAGE (이미지)
```javascript
{
  "name": "profile_image",
  "type": "custom:image",
  "constraints": {
    "max_size": 5242880,  // 5MB
    "allowed_formats": ["jpg", "png", "gif"],
    "max_width": 1920,
    "max_height": 1080
  }
}
```

#### 10. FILE (파일)
```javascript
{
  "name": "document",
  "type": "custom:file",
  "constraints": {
    "max_size": 10485760,  // 10MB
    "allowed_extensions": ["pdf", "doc", "docx"],
    "require_virus_scan": true
  }
}
```

### 복합 타입 입력 컴포넌트 예시

#### Vue.js 전화번호 컴포넌트
```vue
<template>
  <div class="phone-input">
    <label>{{ label }}</label>
    <div class="input-group">
      <select v-model="selectedCountry">
        <option value="KR">🇰🇷 +82</option>
        <option value="US">🇺🇸 +1</option>
        <option value="JP">🇯🇵 +81</option>
      </select>
      <input 
        v-model="phoneNumber"
        type="tel"
        :placeholder="placeholder"
        @input="validatePhone"
        :class="{ 'error': hasError }"
      />
    </div>
    <span v-if="hasError" class="error-message">{{ errorMessage }}</span>
  </div>
</template>

<script>
export default {
  name: 'PhoneInput',
  props: {
    label: String,
    value: String,
    constraints: Object
  },
  data() {
    return {
      selectedCountry: 'KR',
      phoneNumber: '',
      hasError: false,
      errorMessage: ''
    };
  },
  computed: {
    placeholder() {
      return this.selectedCountry === 'KR' ? '010-1234-5678' : 'Phone number';
    }
  },
  methods: {
    validatePhone() {
      // 전화번호 검증 로직
      const phoneRegex = /^[0-9+\-\s()]+$/;
      if (!phoneRegex.test(this.phoneNumber)) {
        this.hasError = true;
        this.errorMessage = '유효한 전화번호를 입력하세요';
        return;
      }
      
      this.hasError = false;
      this.errorMessage = '';
      this.$emit('input', {
        country: this.selectedCountry,
        number: this.phoneNumber
      });
    }
  }
};
</script>
```

#### React 이메일 컴포넌트
```jsx
import React, { useState, useEffect } from 'react';

const EmailInput = ({ label, value, constraints, onChange }) => {
  const [email, setEmail] = useState(value || '');
  const [error, setError] = useState('');

  const validateEmail = (emailValue) => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    
    if (!emailRegex.test(emailValue)) {
      setError('유효한 이메일 주소를 입력하세요');
      return false;
    }
    
    if (constraints?.require_tld && !emailValue.includes('.')) {
      setError('최상위 도메인이 필요합니다');
      return false;
    }
    
    setError('');
    return true;
  };

  const handleChange = (e) => {
    const newValue = e.target.value;
    setEmail(newValue);
    
    if (validateEmail(newValue)) {
      onChange(newValue);
    }
  };

  return (
    <div className="email-input">
      <label>{label}</label>
      <input
        type="email"
        value={email}
        onChange={handleChange}
        placeholder="example@domain.com"
        className={error ? 'error' : ''}
      />
      {error && <span className="error-message">{error}</span>}
    </div>
  );
};

export default EmailInput;
```

---

## 관계 관리 시스템

### 관계 타입
```javascript
const RELATIONSHIP_TYPES = {
  ONE_TO_ONE: 'one_to_one',
  ONE_TO_MANY: 'one_to_many',
  MANY_TO_ONE: 'many_to_one',
  MANY_TO_MANY: 'many_to_many'
};
```

### 관계 정의 예시
```javascript
{
  "id": "Employee",
  "properties": [
    {
      "name": "works_for",
      "type": "relationship",
      "target_class": "Company",
      "cardinality": "many_to_one",
      "inverse_property": "employees",
      "constraints": {
        "required": true,
        "cascade_delete": false
      }
    }
  ]
}
```

### 관계 검증 응답
```javascript
{
  "status": "success",
  "data": {
    "valid": true,
    "issues": [],
    "suggestions": [
      {
        "type": "inverse_relationship",
        "message": "Company.employees 역관계를 자동 생성할 수 있습니다",
        "auto_fix": true
      }
    ],
    "circular_references": []
  }
}
```

---

## 요청/응답 스키마

### 공통 응답 스키마
```javascript
{
  "status": "success" | "error",
  "message": "상태 메시지",
  "data": {}, // 실제 데이터
  "timestamp": "2025-01-18T10:30:00Z",
  "request_id": "unique-request-id"
}
```

### 온톨로지 응답 스키마
```javascript
{
  "status": "success",
  "message": "온톨로지가 성공적으로 생성되었습니다",
  "data": {
    "id": "Person",
    "label": "사람",
    "description": "사람을 나타내는 클래스",
    "properties": [
      {
        "name": "name",
        "label": "이름",
        "type": "xsd:string",
        "required": true,
        "constraints": {}
      }
    ],
    "relationships": [
      {
        "name": "works_for",
        "target_class": "Company",
        "cardinality": "many_to_one"
      }
    ],
    "parent_class": null,
    "abstract": false,
    "metadata": {
      "created_at": "2025-01-18T10:30:00Z",
      "updated_at": "2025-01-18T10:30:00Z",
      "version": 1
    }
  }
}
```

### 목록 응답 스키마
```javascript
{
  "status": "success",
  "message": "온톨로지 목록을 성공적으로 조회했습니다",
  "data": {
    "ontologies": [
      {
        "id": "Person",
        "label": "사람",
        "description": "사람 클래스",
        "property_count": 5,
        "relationship_count": 2
      }
    ],
    "pagination": {
      "total": 25,
      "page": 1,
      "per_page": 10,
      "total_pages": 3
    }
  }
}
```

---

## 에러 처리

### 에러 응답 스키마
```javascript
{
  "status": "error",
  "message": "사용자 친화적 에러 메시지",
  "error_code": "VALIDATION_ERROR",
  "details": {
    "field": "properties.0.type",
    "value": "invalid_type",
    "constraint": "must be valid data type"
  },
  "timestamp": "2025-01-18T10:30:00Z"
}
```

### 주요 에러 코드
```javascript
const ERROR_CODES = {
  // 검증 에러
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  INVALID_DATA_TYPE: 'INVALID_DATA_TYPE',
  REQUIRED_FIELD_MISSING: 'REQUIRED_FIELD_MISSING',
  CONSTRAINT_VIOLATION: 'CONSTRAINT_VIOLATION',
  
  // 데이터베이스 에러
  DATABASE_NOT_FOUND: 'DATABASE_NOT_FOUND',
  DUPLICATE_ONTOLOGY: 'DUPLICATE_ONTOLOGY',
  ONTOLOGY_NOT_FOUND: 'ONTOLOGY_NOT_FOUND',
  
  // 관계 에러
  CIRCULAR_REFERENCE: 'CIRCULAR_REFERENCE',
  INVALID_RELATIONSHIP: 'INVALID_RELATIONSHIP',
  RELATIONSHIP_CONFLICT: 'RELATIONSHIP_CONFLICT',
  
  // 시스템 에러
  INTERNAL_SERVER_ERROR: 'INTERNAL_SERVER_ERROR',
  SERVICE_UNAVAILABLE: 'SERVICE_UNAVAILABLE',
  RATE_LIMIT_EXCEEDED: 'RATE_LIMIT_EXCEEDED'
};
```

### 프론트엔드 에러 처리 예시
```javascript
// services/api.js
class ApiService {
  async request(url, options = {}) {
    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        }
      });

      const data = await response.json();

      if (!response.ok) {
        throw new ApiError(data.error_code, data.message, data.details);
      }

      return data;
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      throw new ApiError('NETWORK_ERROR', '네트워크 오류가 발생했습니다');
    }
  }
}

class ApiError extends Error {
  constructor(code, message, details = null) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

// 사용 예시
try {
  const result = await apiService.createOntology(dbName, ontologyData);
  console.log('성공:', result);
} catch (error) {
  if (error.code === 'VALIDATION_ERROR') {
    showValidationErrors(error.details);
  } else if (error.code === 'DUPLICATE_ONTOLOGY') {
    showMessage('이미 존재하는 온톨로지입니다');
  } else {
    showMessage('오류가 발생했습니다: ' + error.message);
  }
}
```

---

## 실제 사용 예시

### 1. 완전한 온톨로지 생성 워크플로우

```javascript
// 1. 데이터베이스 생성
const createDatabase = async (dbName) => {
  const response = await fetch('/api/v1/database/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: dbName })
  });
  return response.json();
};

// 2. 복합 타입을 포함한 온톨로지 생성
const createPersonOntology = async (dbName) => {
  const ontologyData = {
    id: 'Person',
    label: '사람',
    description: '사람을 나타내는 온톨로지 클래스',
    properties: [
      {
        name: 'name',
        label: '이름',
        type: 'xsd:string',
        required: true
      },
      {
        name: 'email',
        label: '이메일',
        type: 'custom:email',
        required: true,
        constraints: {
          allow_international: true,
          require_tld: true
        }
      },
      {
        name: 'phone',
        label: '전화번호',
        type: 'custom:phone',
        required: false,
        constraints: {
          format: 'E164',
          region: 'KR'
        }
      },
      {
        name: 'salary',
        label: '급여',
        type: 'custom:money',
        required: false,
        constraints: {
          currency: 'KRW',
          min_amount: 0
        }
      },
      {
        name: 'address',
        label: '주소',
        type: 'custom:address',
        required: false,
        constraints: {
          country: 'KR',
          format: 'korean'
        }
      },
      {
        name: 'profile_image',
        label: '프로필 사진',
        type: 'custom:image',
        required: false,
        constraints: {
          max_size: 5242880,
          allowed_formats: ['jpg', 'png']
        }
      }
    ],
    parent_class: null,
    abstract: false
  };

  const response = await fetch(`/api/v1/ontology/${dbName}/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ontologyData)
  });
  
  return response.json();
};

// 3. 관계가 있는 온톨로지 생성
const createCompanyOntology = async (dbName) => {
  const ontologyData = {
    id: 'Company',
    label: '회사',
    description: '회사를 나타내는 온톨로지 클래스',
    properties: [
      {
        name: 'name',
        label: '회사명',
        type: 'xsd:string',
        required: true
      },
      {
        name: 'employees',
        label: '직원들',
        type: 'relationship',
        target_class: 'Person',
        cardinality: 'one_to_many',
        inverse_property: 'works_for'
      }
    ]
  };

  const response = await fetch(`/api/v1/ontology/${dbName}/create-advanced`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...ontologyData,
      auto_generate_inverse: true,
      validate_relationships: true,
      check_circular_references: true
    })
  });
  
  return response.json();
};

// 4. 전체 워크플로우 실행
const setupOntologySystem = async () => {
  try {
    // 데이터베이스 생성
    await createDatabase('hr_system');
    console.log('✅ 데이터베이스 생성 완료');

    // 사람 온톨로지 생성
    const personResult = await createPersonOntology('hr_system');
    console.log('✅ 사람 온톨로지 생성 완료:', personResult);

    // 회사 온톨로지 생성 (관계 포함)
    const companyResult = await createCompanyOntology('hr_system');
    console.log('✅ 회사 온톨로지 생성 완료:', companyResult);

    // 관계 검증
    const validationResult = await validateRelationships('hr_system');
    console.log('✅ 관계 검증 완료:', validationResult);

  } catch (error) {
    console.error('❌ 오류 발생:', error);
  }
};
```

### 2. 복합 타입 데이터 입력 폼

```vue
<template>
  <div class="ontology-form">
    <h2>사람 정보 입력</h2>
    
    <form @submit.prevent="submitForm">
      <!-- 기본 문자열 타입 -->
      <div class="form-group">
        <label>이름 *</label>
        <input 
          v-model="formData.name" 
          type="text" 
          required
          :class="{ error: errors.name }"
        />
        <span v-if="errors.name" class="error">{{ errors.name }}</span>
      </div>

      <!-- 이메일 복합 타입 -->
      <div class="form-group">
        <label>이메일 *</label>
        <input 
          v-model="formData.email" 
          type="email" 
          required
          @blur="validateEmail"
          :class="{ error: errors.email }"
        />
        <span v-if="errors.email" class="error">{{ errors.email }}</span>
      </div>

      <!-- 전화번호 복합 타입 -->
      <div class="form-group">
        <label>전화번호</label>
        <div class="phone-input">
          <select v-model="formData.phone.country">
            <option value="KR">🇰🇷 +82</option>
            <option value="US">🇺🇸 +1</option>
          </select>
          <input 
            v-model="formData.phone.number" 
            type="tel"
            @blur="validatePhone"
            :class="{ error: errors.phone }"
          />
        </div>
        <span v-if="errors.phone" class="error">{{ errors.phone }}</span>
      </div>

      <!-- 급여 복합 타입 -->
      <div class="form-group">
        <label>급여</label>
        <div class="money-input">
          <select v-model="formData.salary.currency">
            <option value="KRW">원 (KRW)</option>
            <option value="USD">달러 (USD)</option>
          </select>
          <input 
            v-model="formData.salary.amount" 
            type="number"
            min="0"
            @blur="validateSalary"
            :class="{ error: errors.salary }"
          />
        </div>
        <span v-if="errors.salary" class="error">{{ errors.salary }}</span>
      </div>

      <!-- 주소 복합 타입 -->
      <div class="form-group">
        <label>주소</label>
        <div class="address-input">
          <input 
            v-model="formData.address.street" 
            placeholder="도로명 주소"
            @blur="validateAddress"
          />
          <input 
            v-model="formData.address.city" 
            placeholder="시/구"
          />
          <input 
            v-model="formData.address.postal_code" 
            placeholder="우편번호"
          />
        </div>
        <span v-if="errors.address" class="error">{{ errors.address }}</span>
      </div>

      <!-- 프로필 이미지 복합 타입 -->
      <div class="form-group">
        <label>프로필 사진</label>
        <input 
          type="file"
          accept="image/jpeg,image/png"
          @change="handleImageUpload"
          :class="{ error: errors.profile_image }"
        />
        <div v-if="imagePreview" class="image-preview">
          <img :src="imagePreview" alt="미리보기" />
        </div>
        <span v-if="errors.profile_image" class="error">{{ errors.profile_image }}</span>
      </div>

      <button type="submit" :disabled="!isFormValid">저장</button>
    </form>
  </div>
</template>

<script>
export default {
  name: 'PersonForm',
  data() {
    return {
      formData: {
        name: '',
        email: '',
        phone: {
          country: 'KR',
          number: ''
        },
        salary: {
          currency: 'KRW',
          amount: ''
        },
        address: {
          street: '',
          city: '',
          postal_code: ''
        },
        profile_image: null
      },
      errors: {},
      imagePreview: null
    };
  },
  computed: {
    isFormValid() {
      return this.formData.name && 
             this.formData.email && 
             Object.keys(this.errors).length === 0;
    }
  },
  methods: {
    validateEmail() {
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(this.formData.email)) {
        this.errors.email = '유효한 이메일 주소를 입력하세요';
      } else {
        delete this.errors.email;
      }
    },
    
    validatePhone() {
      if (this.formData.phone.number) {
        const phoneRegex = /^[0-9+\-\s()]+$/;
        if (!phoneRegex.test(this.formData.phone.number)) {
          this.errors.phone = '유효한 전화번호를 입력하세요';
        } else {
          delete this.errors.phone;
        }
      }
    },
    
    validateSalary() {
      if (this.formData.salary.amount) {
        const amount = parseFloat(this.formData.salary.amount);
        if (isNaN(amount) || amount < 0) {
          this.errors.salary = '유효한 급여 금액을 입력하세요';
        } else {
          delete this.errors.salary;
        }
      }
    },
    
    validateAddress() {
      if (this.formData.address.street) {
        if (this.formData.address.street.length < 5) {
          this.errors.address = '주소를 정확히 입력하세요';
        } else {
          delete this.errors.address;
        }
      }
    },
    
    handleImageUpload(event) {
      const file = event.target.files[0];
      if (file) {
        // 파일 크기 검증 (5MB)
        if (file.size > 5242880) {
          this.errors.profile_image = '이미지 크기는 5MB 이하여야 합니다';
          return;
        }
        
        // 파일 형식 검증
        const allowedTypes = ['image/jpeg', 'image/png'];
        if (!allowedTypes.includes(file.type)) {
          this.errors.profile_image = 'JPG, PNG 파일만 업로드 가능합니다';
          return;
        }
        
        this.formData.profile_image = file;
        delete this.errors.profile_image;
        
        // 미리보기 생성
        const reader = new FileReader();
        reader.onload = (e) => {
          this.imagePreview = e.target.result;
        };
        reader.readAsDataURL(file);
      }
    },
    
    async submitForm() {
      try {
        // 복합 타입 데이터를 API에 맞게 변환
        const apiData = {
          name: this.formData.name,
          email: this.formData.email,
          phone: {
            country: this.formData.phone.country,
            number: this.formData.phone.number
          },
          salary: {
            currency: this.formData.salary.currency,
            amount: parseFloat(this.formData.salary.amount)
          },
          address: {
            street: this.formData.address.street,
            city: this.formData.address.city,
            postal_code: this.formData.address.postal_code
          }
        };
        
        // 이미지 업로드가 있는 경우 별도 처리
        if (this.formData.profile_image) {
          const formData = new FormData();
          formData.append('image', this.formData.profile_image);
          
          const imageResponse = await fetch('/api/v1/upload/image', {
            method: 'POST',
            body: formData
          });
          
          const imageResult = await imageResponse.json();
          apiData.profile_image = imageResult.data.url;
        }
        
        // 온톨로지 데이터 생성
        const response = await fetch('/api/v1/ontology/hr_system/Person/instances', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(apiData)
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
          this.$emit('success', result.data);
          this.resetForm();
        } else {
          this.handleApiError(result);
        }
        
      } catch (error) {
        console.error('폼 제출 오류:', error);
        this.$emit('error', '데이터 저장 중 오류가 발생했습니다');
      }
    },
    
    resetForm() {
      this.formData = {
        name: '',
        email: '',
        phone: { country: 'KR', number: '' },
        salary: { currency: 'KRW', amount: '' },
        address: { street: '', city: '', postal_code: '' },
        profile_image: null
      };
      this.errors = {};
      this.imagePreview = null;
    },
    
    handleApiError(result) {
      if (result.error_code === 'VALIDATION_ERROR') {
        // 필드별 검증 오류 처리
        if (result.details && result.details.field) {
          this.errors[result.details.field] = result.details.message;
        }
      } else {
        this.$emit('error', result.message);
      }
    }
  }
};
</script>
```

### 3. 관계 시각화 컴포넌트

```javascript
// components/RelationshipGraph.vue
<template>
  <div class="relationship-graph">
    <div class="graph-container" ref="graphContainer">
      <svg :width="svgWidth" :height="svgHeight">
        <!-- 관계 선 -->
        <g class="relationships">
          <line
            v-for="relationship in relationships"
            :key="`${relationship.source}-${relationship.target}`"
            :x1="getNodePosition(relationship.source).x"
            :y1="getNodePosition(relationship.source).y"
            :x2="getNodePosition(relationship.target).x"
            :y2="getNodePosition(relationship.target).y"
            :stroke="getRelationshipColor(relationship.type)"
            stroke-width="2"
            marker-end="url(#arrowhead)"
          />
          
          <!-- 관계 라벨 -->
          <text
            v-for="relationship in relationships"
            :key="`label-${relationship.source}-${relationship.target}`"
            :x="getRelationshipLabelPosition(relationship).x"
            :y="getRelationshipLabelPosition(relationship).y"
            text-anchor="middle"
            class="relationship-label"
          >
            {{ relationship.label }}
          </text>
        </g>
        
        <!-- 노드 -->
        <g class="nodes">
          <circle
            v-for="node in nodes"
            :key="node.id"
            :cx="node.x"
            :cy="node.y"
            :r="nodeRadius"
            :fill="getNodeColor(node.type)"
            :stroke="getNodeStroke(node.selected)"
            stroke-width="2"
            @click="selectNode(node)"
            class="node"
          />
          
          <!-- 노드 라벨 -->
          <text
            v-for="node in nodes"
            :key="`text-${node.id}`"
            :x="node.x"
            :y="node.y + 5"
            text-anchor="middle"
            class="node-label"
          >
            {{ node.label }}
          </text>
        </g>
        
        <!-- 화살표 마커 정의 -->
        <defs>
          <marker
            id="arrowhead"
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon
              points="0 0, 10 3.5, 0 7"
              fill="#666"
            />
          </marker>
        </defs>
      </svg>
    </div>
    
    <!-- 컨트롤 패널 -->
    <div class="control-panel">
      <h3>관계 분석</h3>
      <div class="analysis-results">
        <div class="stat">
          <label>전체 노드:</label>
          <span>{{ nodes.length }}</span>
        </div>
        <div class="stat">
          <label>전체 관계:</label>
          <span>{{ relationships.length }}</span>
        </div>
        <div class="stat">
          <label>순환 참조:</label>
          <span :class="{ error: circularReferences.length > 0 }">
            {{ circularReferences.length }}
          </span>
        </div>
      </div>
      
      <div class="path-finder">
        <h4>경로 찾기</h4>
        <select v-model="pathStart">
          <option value="">시작 노드 선택</option>
          <option v-for="node in nodes" :key="node.id" :value="node.id">
            {{ node.label }}
          </option>
        </select>
        <select v-model="pathEnd">
          <option value="">끝 노드 선택</option>
          <option v-for="node in nodes" :key="node.id" :value="node.id">
            {{ node.label }}
          </option>
        </select>
        <button @click="findPath" :disabled="!pathStart || !pathEnd">
          경로 찾기
        </button>
      </div>
      
      <div v-if="foundPaths.length > 0" class="path-results">
        <h4>발견된 경로</h4>
        <div v-for="(path, index) in foundPaths" :key="index" class="path">
          <div class="path-info">
            <span class="path-length">길이: {{ path.length }}</span>
            <span class="path-type">타입: {{ path.type }}</span>
          </div>
          <div class="path-nodes">
            {{ path.nodes.join(' → ') }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'RelationshipGraph',
  props: {
    dbName: {
      type: String,
      required: true
    }
  },
  data() {
    return {
      nodes: [],
      relationships: [],
      circularReferences: [],
      foundPaths: [],
      pathStart: '',
      pathEnd: '',
      svgWidth: 800,
      svgHeight: 600,
      nodeRadius: 30,
      selectedNode: null
    };
  },
  async mounted() {
    await this.loadGraphData();
    this.layoutNodes();
  },
  methods: {
    async loadGraphData() {
      try {
        // 온톨로지 목록 로드
        const ontologyResponse = await fetch(`/api/v1/ontology/${this.dbName}/list`);
        const ontologyResult = await ontologyResponse.json();
        
        if (ontologyResult.status === 'success') {
          this.nodes = ontologyResult.data.ontologies.map(ont => ({
            id: ont.id,
            label: ont.label || ont.id,
            type: ont.abstract ? 'abstract' : 'concrete',
            x: 0,
            y: 0,
            selected: false
          }));
        }
        
        // 관계 네트워크 분석 로드
        const analysisResponse = await fetch(`/api/v1/ontology/${this.dbName}/analyze-network`);
        const analysisResult = await analysisResponse.json();
        
        if (analysisResult.status === 'success') {
          this.relationships = analysisResult.data.relationships || [];
          this.circularReferences = analysisResult.data.circular_references || [];
        }
        
      } catch (error) {
        console.error('그래프 데이터 로드 오류:', error);
      }
    },
    
    layoutNodes() {
      // 간단한 원형 레이아웃
      const centerX = this.svgWidth / 2;
      const centerY = this.svgHeight / 2;
      const radius = Math.min(centerX, centerY) * 0.7;
      
      this.nodes.forEach((node, index) => {
        const angle = (2 * Math.PI * index) / this.nodes.length;
        node.x = centerX + radius * Math.cos(angle);
        node.y = centerY + radius * Math.sin(angle);
      });
    },
    
    getNodePosition(nodeId) {
      const node = this.nodes.find(n => n.id === nodeId);
      return node ? { x: node.x, y: node.y } : { x: 0, y: 0 };
    },
    
    getRelationshipLabelPosition(relationship) {
      const sourcePos = this.getNodePosition(relationship.source);
      const targetPos = this.getNodePosition(relationship.target);
      
      return {
        x: (sourcePos.x + targetPos.x) / 2,
        y: (sourcePos.y + targetPos.y) / 2
      };
    },
    
    getNodeColor(type) {
      return type === 'abstract' ? '#ffeb3b' : '#4caf50';
    },
    
    getNodeStroke(selected) {
      return selected ? '#ff5722' : '#333';
    },
    
    getRelationshipColor(type) {
      const colors = {
        'one_to_one': '#2196f3',
        'one_to_many': '#ff9800',
        'many_to_one': '#9c27b0',
        'many_to_many': '#f44336'
      };
      return colors[type] || '#666';
    },
    
    selectNode(node) {
      this.nodes.forEach(n => n.selected = false);
      node.selected = true;
      this.selectedNode = node;
    },
    
    async findPath() {
      if (!this.pathStart || !this.pathEnd) return;
      
      try {
        const response = await fetch(
          `/api/v1/ontology/${this.dbName}/relationship-paths/${this.pathStart}?end_entity=${this.pathEnd}&max_depth=5&path_type=all`
        );
        const result = await response.json();
        
        if (result.status === 'success') {
          this.foundPaths = result.data.paths || [];
        }
      } catch (error) {
        console.error('경로 찾기 오류:', error);
      }
    }
  }
};
</script>

<style scoped>
.relationship-graph {
  display: flex;
  gap: 20px;
}

.graph-container {
  flex: 1;
  border: 1px solid #ddd;
  border-radius: 8px;
  overflow: hidden;
}

.control-panel {
  width: 300px;
  padding: 20px;
  background: #f5f5f5;
  border-radius: 8px;
}

.node {
  cursor: pointer;
  transition: all 0.2s;
}

.node:hover {
  r: 35;
}

.node-label {
  font-size: 12px;
  font-weight: bold;
  fill: #333;
  pointer-events: none;
}

.relationship-label {
  font-size: 10px;
  fill: #666;
  pointer-events: none;
}

.analysis-results {
  margin-bottom: 20px;
}

.stat {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.stat .error {
  color: #f44336;
  font-weight: bold;
}

.path-finder select,
.path-finder button {
  width: 100%;
  margin-bottom: 10px;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.path-results {
  margin-top: 20px;
}

.path {
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 10px;
  margin-bottom: 10px;
  background: white;
}

.path-info {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #666;
  margin-bottom: 5px;
}

.path-nodes {
  font-size: 14px;
  font-weight: bold;
}
</style>
```

---

## 테스트 가이드

### 1. API 테스트

```javascript
// tests/api.test.js
describe('SPICE HARVESTER API Tests', () => {
  const API_BASE = 'http://localhost:8002';
  const TEST_DB = 'test_frontend_db';
  
  beforeAll(async () => {
    // 테스트 데이터베이스 생성
    await fetch(`${API_BASE}/api/v1/database/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: TEST_DB })
    });
  });
  
  afterAll(async () => {
    // 테스트 데이터베이스 정리
    await fetch(`${API_BASE}/api/v1/database/${TEST_DB}`, {
      method: 'DELETE'
    });
  });
  
  test('should create ontology with complex types', async () => {
    const ontologyData = {
      id: 'TestPerson',
      label: '테스트 사람',
      properties: [
        {
          name: 'email',
          type: 'custom:email',
          required: true
        },
        {
          name: 'phone',
          type: 'custom:phone',
          constraints: { format: 'E164' }
        }
      ]
    };
    
    const response = await fetch(`${API_BASE}/api/v1/ontology/${TEST_DB}/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ontologyData)
    });
    
    const result = await response.json();
    
    expect(response.status).toBe(200);
    expect(result.status).toBe('success');
    expect(result.data.id).toBe('TestPerson');
  });
  
  test('should validate complex type constraints', async () => {
    const invalidData = {
      id: 'InvalidPerson',
      properties: [
        {
          name: 'email',
          type: 'custom:email',
          constraints: { invalid_constraint: true }
        }
      ]
    };
    
    const response = await fetch(`${API_BASE}/api/v1/ontology/${TEST_DB}/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(invalidData)
    });
    
    const result = await response.json();
    
    expect(response.status).toBe(400);
    expect(result.status).toBe('error');
    expect(result.error_code).toBe('VALIDATION_ERROR');
  });
});
```

### 2. 컴포넌트 테스트

```javascript
// tests/components/PhoneInput.test.js
import { mount } from '@vue/test-utils';
import PhoneInput from '@/components/PhoneInput.vue';

describe('PhoneInput Component', () => {
  test('should validate phone number format', async () => {
    const wrapper = mount(PhoneInput, {
      props: {
        label: '전화번호',
        constraints: { format: 'E164' }
      }
    });
    
    const input = wrapper.find('input[type="tel"]');
    await input.setValue('010-1234-5678');
    await input.trigger('blur');
    
    expect(wrapper.vm.hasError).toBe(false);
    expect(wrapper.emitted('input')).toBeTruthy();
  });
  
  test('should show error for invalid phone number', async () => {
    const wrapper = mount(PhoneInput);
    
    const input = wrapper.find('input[type="tel"]');
    await input.setValue('invalid-phone');
    await input.trigger('blur');
    
    expect(wrapper.vm.hasError).toBe(true);
    expect(wrapper.find('.error-message').text()).toContain('유효한 전화번호');
  });
});
```

### 3. 통합 테스트

```javascript
// tests/integration/ontology-workflow.test.js
describe('Ontology Management Workflow', () => {
  test('complete ontology creation and retrieval workflow', async () => {
    const dbName = 'integration_test_db';
    
    // 1. 데이터베이스 생성
    const dbResponse = await createDatabase(dbName);
    expect(dbResponse.status).toBe('success');
    
    // 2. 복합 타입 온톨로지 생성
    const ontologyResponse = await createOntology(dbName, {
      id: 'IntegrationPerson',
      properties: [
        { name: 'email', type: 'custom:email' },
        { name: 'phone', type: 'custom:phone' },
        { name: 'salary', type: 'custom:money' }
      ]
    });
    expect(ontologyResponse.status).toBe('success');
    
    // 3. 온톨로지 조회
    const retrievedOntology = await getOntology(dbName, 'IntegrationPerson');
    expect(retrievedOntology.data.id).toBe('IntegrationPerson');
    expect(retrievedOntology.data.properties).toHaveLength(3);
    
    // 4. 관계 추가
    const relationshipResponse = await addRelationship(dbName, 'IntegrationPerson', {
      name: 'works_for',
      target_class: 'Company',
      cardinality: 'many_to_one'
    });
    expect(relationshipResponse.status).toBe('success');
    
    // 5. 정리
    await deleteDatabase(dbName);
  });
});
```

---

## 추가 개발 팁

### 1. 상태 관리 (Vuex/Pinia)

```javascript
// store/ontology.js
export const useOntologyStore = defineStore('ontology', {
  state: () => ({
    databases: [],
    currentDatabase: null,
    ontologies: [],
    selectedOntology: null,
    loading: false,
    error: null
  }),
  
  actions: {
    async createDatabase(name) {
      this.loading = true;
      try {
        const response = await ontologyService.createDatabase(name);
        this.databases.push(response.data);
        return response;
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.loading = false;
      }
    },
    
    async loadOntologies(dbName) {
      this.loading = true;
      try {
        const response = await ontologyService.listOntologies(dbName);
        this.ontologies = response.data.ontologies;
        return response;
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.loading = false;
      }
    },
    
    async createOntology(dbName, ontologyData) {
      this.loading = true;
      try {
        const response = await ontologyService.createOntology(dbName, ontologyData);
        this.ontologies.push(response.data);
        return response;
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.loading = false;
      }
    }
  }
});
```

### 2. 타입 정의 (TypeScript)

```typescript
// types/ontology.ts
export interface Property {
  name: string;
  label?: string;
  type: DataType;
  required?: boolean;
  constraints?: Record<string, any>;
}

export interface Relationship {
  name: string;
  target_class: string;
  cardinality: 'one_to_one' | 'one_to_many' | 'many_to_one' | 'many_to_many';
  inverse_property?: string;
}

export interface Ontology {
  id: string;
  label: string;
  description?: string;
  properties: Property[];
  relationships: Relationship[];
  parent_class?: string;
  abstract: boolean;
  metadata?: Record<string, any>;
}

export interface ApiResponse<T> {
  status: 'success' | 'error';
  message: string;
  data?: T;
  error_code?: string;
  details?: any;
  timestamp: string;
}

export enum DataType {
  // 기본 타입
  STRING = 'xsd:string',
  INTEGER = 'xsd:integer',
  DECIMAL = 'xsd:decimal',
  BOOLEAN = 'xsd:boolean',
  DATE = 'xsd:date',
  
  // 복합 타입
  ARRAY = 'custom:array',
  OBJECT = 'custom:object',
  ENUM = 'custom:enum',
  MONEY = 'custom:money',
  PHONE = 'custom:phone',
  EMAIL = 'custom:email',
  COORDINATE = 'custom:coordinate',
  ADDRESS = 'custom:address',
  IMAGE = 'custom:image',
  FILE = 'custom:file'
}
```

### 3. 유틸리티 함수

```javascript
// utils/validation.js
export const validateComplexType = (value, type, constraints = {}) => {
  switch (type) {
    case 'custom:email':
      return validateEmail(value, constraints);
    case 'custom:phone':
      return validatePhone(value, constraints);
    case 'custom:money':
      return validateMoney(value, constraints);
    default:
      return { valid: true };
  }
};

export const validateEmail = (email, constraints) => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  
  if (!emailRegex.test(email)) {
    return { valid: false, error: '유효한 이메일 형식이 아닙니다' };
  }
  
  if (constraints.require_tld && !email.includes('.')) {
    return { valid: false, error: '최상위 도메인이 필요합니다' };
  }
  
  return { valid: true };
};

export const validatePhone = (phone, constraints) => {
  const phoneRegex = /^[0-9+\-\s()]+$/;
  
  if (!phoneRegex.test(phone)) {
    return { valid: false, error: '유효한 전화번호 형식이 아닙니다' };
  }
  
  if (constraints.format === 'E164' && !phone.startsWith('+')) {
    return { valid: false, error: 'E164 형식은 +로 시작해야 합니다' };
  }
  
  return { valid: true };
};
```

---

## 마무리

이 문서는 **SPICE HARVESTER** 시스템의 프론트엔드 개발에 필요한 모든 정보를 포함하고 있습니다. 

### 주요 특징:
- ✅ **10가지 복합 데이터 타입** 완전 지원
- ✅ **고급 관계 관리** 시스템
- ✅ **실시간 검증** 및 제약 조건
- ✅ **다국어 지원** (한국어/영어)
- ✅ **프로덕션 레벨** 안정성

### 개발 시 주의사항:
1. **API 응답 구조**를 정확히 파악하고 사용하세요
2. **복합 타입 검증**을 프론트엔드에서도 구현하세요
3. **에러 처리**를 체계적으로 구현하세요
4. **관계 시각화**를 통해 사용자 경험을 향상시키세요

문의사항이 있으시면 언제든지 연락 주세요! 🚀