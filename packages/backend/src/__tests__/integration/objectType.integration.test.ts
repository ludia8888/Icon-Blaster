/**
 * ObjectType API 통합 테스트
 *
 * 실제 PostgreSQL을 사용하여 전체 API 스택을 검증
 * 명시적 테스트 원칙:
 * 1. 각 테스트는 독립적이고 명확한 목적을 가짐
 * 2. 실패 시 정확한 원인을 알 수 있도록 assertion 작성
 * 3. 테스트 데이터는 예측 가능하고 의미 있게 설계
 */

import { Application } from 'express';
import request from 'supertest';
import { DataSource } from 'typeorm';

import { ObjectType } from '../../entities/ObjectType';
import { PaginatedResponse, ApiResponse } from '../../types/common';
import { generateTestToken } from '../utils/auth-helper';

import { createTestApp } from './test-app';
import { testEnvironment, TestDatabaseConfig } from './test-db-setup';

// Constants to avoid string duplication
const API_BASE_PATH = '/api/object-types';
const AUTH_HEADER = 'Authorization';
const CONTENT_TYPE = 'Content-Type';
const JSON_CONTENT = /json/;

// Type definitions
interface ObjectTypeResponse {
  rid: string;
  apiName: string;
  displayName: string;
  description?: string;
  status: string;
  visibility: string;
  icon?: string;
  color?: string;
  pluralDisplayName?: string;
  createdAt: string;
  updatedAt: string;
  createdBy: string;
  updatedBy: string;
}


describe('ObjectType API Integration Tests', () => {
  let app: Application;
  let dataSource: DataSource;
  let dbConfig: TestDatabaseConfig;
  let authToken: string;

  // 전체 테스트 스위트 시작 전 한 번만 실행
  beforeAll(async () => {
    // JWT secret 설정
    process.env['JWT_SECRET'] = 'test-secret-key';
    // 1. PostgreSQL 컨테이너 시작
    dbConfig = await testEnvironment.start();

    // 2. DataSource 초기화
    dataSource = await testEnvironment.createDataSource(dbConfig);

    // 3. 테스트 데이터 시드
    await testEnvironment.seedTestData(dataSource);

    // 4. Express 앱 생성 (테스트 DataSource 사용)
    app = createTestApp(dataSource);

    // 5. 인증 토큰 생성
    authToken = generateTestToken({
      sub: 'test-user',
      email: 'test@example.com',
      roles: ['admin'],
    });
  }, 30000); // 컨테이너 시작에 시간이 걸릴 수 있음

  // 전체 테스트 스위트 종료 후 정리
  afterAll(async () => {
    await testEnvironment.cleanup();
  });

  // 각 테스트 후 데이터 정리 (선택적)
  afterEach(async () => {
    // 특정 테스트에서 생성한 데이터만 정리
    // 시드 데이터는 유지
  });

  describe('GET /api/object-types', () => {
    it('should return paginated list of object types', async () => {
      const response = await request(app)
        .get(API_BASE_PATH)
        .set(AUTH_HEADER, `Bearer ${authToken}`)
        .query({ page: 1, limit: 10 })
        .expect(200)
        .expect(CONTENT_TYPE, JSON_CONTENT);

      // 명시적 검증: 응답 구조
      // 타입 안전성을 위한 명시적 검증
      const expectedStructure = {
        data: expect.arrayContaining([
          expect.objectContaining({
            rid: expect.any(String),
            apiName: expect.any(String),
            displayName: expect.any(String),
            status: expect.stringMatching(/^(active|experimental|deprecated)$/),
            visibility: expect.stringMatching(/^(prominent|normal|hidden)$/),
          }),
        ]),
        pagination: {
          page: 1,
          limit: 10,
          total: expect.any(Number),
          totalPages: expect.any(Number),
        },
      };
      expect(response.body).toMatchObject(expectedStructure);

      // 명시적 검증: 시드 데이터 확인
      const responseBody = response.body as PaginatedResponse<ObjectTypeResponse>;
      const customerType = responseBody.data.find((t) => t.apiName === 'customer');
      expect(customerType).toBeDefined();
      expect(customerType?.displayName).toBe('Customer');
    });

    it('should filter by status', async () => {
      const response = await request(app)
        .get(API_BASE_PATH)
        .set(AUTH_HEADER, `Bearer ${authToken}`)
        .query({ status: 'active' })
        .expect(200);

      // 모든 결과가 active 상태인지 검증
      const responseBody = response.body as PaginatedResponse<ObjectTypeResponse>;
      expect(responseBody.data).toHaveLength(2); // customer, product
      responseBody.data.forEach((item) => {
        expect(item.status).toBe('active');
      });
    });

    it('should require authentication', async () => {
      const response = await request(app).get(API_BASE_PATH).expect(401);

      expect(response.body).toMatchObject({
        error: expect.objectContaining({
          message: expect.stringContaining('authorization header'),
        }),
      });
    });
  });

  describe('POST /api/object-types', () => {
    it('should create a new object type with valid data', async () => {
      const newObjectType = {
        apiName: 'employee',
        displayName: 'Employee',
        description: 'Employee object type for HR system',
        icon: '👤',
        color: '#4285F4',
      };

      const response = await request(app)
        .post('/api/object-types')
        .set('Authorization', `Bearer ${authToken}`)
        .send(newObjectType);

      // Log error if 500
      if (response.status === 500) {
        console.error('Create failed:', response.body);
      }

      expect(response.status).toBe(201);
      expect(response.type).toMatch(/json/);

      // 명시적 검증: 생성된 객체
      expect(response.body).toMatchObject({
        rid: expect.stringMatching(/^[0-9a-f-]{36}$/), // UUID 형식
        ...newObjectType,
        status: 'active', // 기본값
        visibility: 'normal', // 기본값
        createdBy: 'test-user',
        updatedBy: 'test-user',
        createdAt: expect.any(String),
        updatedAt: expect.any(String),
      });

      // DB에 실제로 저장되었는지 검증
      const repository = dataSource.getRepository(ObjectType);
      const saved = await repository.findOne({
        where: { apiName: 'employee' },
      });
      expect(saved).toBeDefined();
      expect(saved?.displayName).toBe('Employee');
    });

    it('should reject duplicate apiName', async () => {
      const duplicate = {
        apiName: 'customer', // 이미 존재
        displayName: 'Another Customer',
      };

      const response = await request(app)
        .post(API_BASE_PATH)
        .set(AUTH_HEADER, `Bearer ${authToken}`)
        .send(duplicate)
        .expect(409);

      expect(response.body).toMatchObject({
        error: expect.objectContaining({
          message: expect.stringContaining('already exists'),
          code: 'CONFLICT',
        }),
      });
    });

    it('should validate required fields', async () => {
      const invalid = {
        displayName: 'Missing API Name', // apiName 누락
      };

      const response = await request(app)
        .post(API_BASE_PATH)
        .set(AUTH_HEADER, `Bearer ${authToken}`)
        .send(invalid)
        .expect(400);

      expect(response.body).toMatchObject({
        error: expect.objectContaining({
          message: 'Validation failed',
          details: expect.arrayContaining([expect.stringContaining('apiName')]),
        }),
      });
    });

    it('should require proper authorization', async () => {
      const viewerToken = generateTestToken({
        sub: 'viewer',
        email: 'viewer@example.com',
        roles: ['viewer'], // 읽기 권한만
      });

      await request(app)
        .post(API_BASE_PATH)
        .set(AUTH_HEADER, `Bearer ${viewerToken}`)
        .send({ apiName: 'test', displayName: 'Test' })
        .expect(403);
    });
  });

  describe('PUT /api/object-types/:id', () => {
    it('should update existing object type', async () => {
      const updates = {
        displayName: 'Updated Customer',
        description: 'Updated description',
      };

      const response = await request(app)
        .put(`${API_BASE_PATH}/550e8400-e29b-41d4-a716-446655440001`)
        .set(AUTH_HEADER, `Bearer ${authToken}`)
        .send(updates)
        .expect(200);

      const updatedObject = response.body as ObjectTypeResponse;
      expect(updatedObject.displayName).toBe('Updated Customer');
      expect(updatedObject.description).toBe('Updated description');
      expect(updatedObject.updatedBy).toBe('test-user');

      // updatedAt이 변경되었는지 확인
      expect(new Date(updatedObject.updatedAt).getTime()).toBeGreaterThan(
        new Date(updatedObject.createdAt).getTime()
      );
    });

    it('should return 404 for non-existent ID', async () => {
      await request(app)
        .put(`${API_BASE_PATH}/550e8400-e29b-41d4-a716-446655440099`)
        .set(AUTH_HEADER, `Bearer ${authToken}`)
        .send({ displayName: 'Test' })
        .expect(404);
    });

    it('should validate UUID format', async () => {
      await request(app)
        .put(`${API_BASE_PATH}/invalid-uuid`)
        .set(AUTH_HEADER, `Bearer ${authToken}`)
        .send({ displayName: 'Test' })
        .expect(400);
    });
  });

  describe('DELETE /api/object-types/:id', () => {
    let objectTypeToDelete: ObjectType;

    beforeEach(async () => {
      // 삭제 테스트용 객체 생성 (각 테스트마다 고유한 apiName 사용)
      const repository = dataSource.getRepository(ObjectType);
      const uniqueSuffix = Date.now() + Math.random().toString(36).substring(2, 11);
      const newObjectType = repository.create({
        apiName: `to_delete_${uniqueSuffix}`,
        displayName: 'To Delete',
        pluralDisplayName: 'To Delete',
        createdBy: 'test-user',
        updatedBy: 'test-user',
      });
      objectTypeToDelete = await repository.save(newObjectType);
    });

    it('should soft delete object type', async () => {
      await request(app)
        .delete(`${API_BASE_PATH}/${objectTypeToDelete.rid}`)
        .set(AUTH_HEADER, `Bearer ${authToken}`)
        .expect(200);

      // Soft delete 확인
      const repository = dataSource.getRepository(ObjectType);
      const found = await repository.findOne({
        where: { rid: objectTypeToDelete.rid },
        withDeleted: true,
      });

      expect(found).toBeDefined();
      expect(found?.deletedAt).toBeDefined();
    });

    it('should require admin role', async () => {
      const editorToken = generateTestToken({
        sub: 'editor',
        email: 'editor@example.com',
        roles: ['editor'], // admin 권한 없음
      });

      await request(app)
        .delete(`${API_BASE_PATH}/${objectTypeToDelete.rid}`)
        .set(AUTH_HEADER, `Bearer ${editorToken}`)
        .expect(403);
    });
  });

  describe('Status Management', () => {
    it('POST /:id/activate should change status to active', async () => {
      const response = await request(app)
        .post(`${API_BASE_PATH}/550e8400-e29b-41d4-a716-446655440003/activate`)
        .set(AUTH_HEADER, `Bearer ${authToken}`)
        .expect(200);

      const activatedObject = response.body as ObjectTypeResponse;
      expect(activatedObject.status).toBe('active');
    });

    it('POST /:id/deactivate should change status to deprecated', async () => {
      const response = await request(app)
        .post(`${API_BASE_PATH}/550e8400-e29b-41d4-a716-446655440001/deactivate`)
        .set(AUTH_HEADER, `Bearer ${authToken}`)
        .expect(200);

      const deactivatedObject = response.body as ObjectTypeResponse;
      expect(deactivatedObject.status).toBe('deprecated');
    });
  });

  describe('Error Handling', () => {
    it('should handle database connection errors gracefully', async () => {
      // DataSource를 일시적으로 끊기
      await dataSource.destroy();

      const response = await request(app)
        .get(API_BASE_PATH)
        .set(AUTH_HEADER, `Bearer ${authToken}`)
        .expect(500);

      expect(response.body.error).toBeDefined();
      expect(response.body.error.code).toBe('INTERNAL_ERROR');

      // 재연결
      await dataSource.initialize();
    });

    it('should handle malformed JSON', async () => {
      await request(app)
        .post('/api/object-types')
        .set('Authorization', `Bearer ${authToken}`)
        .set('Content-Type', 'application/json')
        .send('{ invalid json')
        .expect(400);
    });
  });
});

/**
 * 명시적 코드 작성으로 얻는 이점:
 *
 * 1. 각 테스트가 무엇을 검증하는지 명확
 * 2. 실패 시 정확한 원인 파악 가능
 * 3. 실제 DB 사용으로 진짜 동작 검증
 * 4. 엣지 케이스와 에러 상황 커버
 * 5. CI/CD에서 자동 실행 가능
 */
