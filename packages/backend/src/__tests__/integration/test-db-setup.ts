/**
 * 통합 테스트를 위한 실제 PostgreSQL 환경 설정
 *
 * 명시적 코드 작성 원칙:
 * 1. 모든 설정값은 명확한 이름과 타입을 가짐
 * 2. 에러 처리는 구체적이고 디버깅 가능하게
 * 3. 자원 정리는 반드시 보장
 */

import { PostgreSqlContainer, StartedPostgreSqlContainer } from '@testcontainers/postgresql';
import { DataSource } from 'typeorm';

/**
 * 테스트 DB 연결 정보
 * 명시적으로 각 필드의 용도를 정의
 */
export interface TestDatabaseConfig {
  readonly host: string;
  readonly port: number;
  readonly database: string;
  readonly username: string;
  readonly password: string;
  readonly connectionUri: string;
}

/**
 * 테스트 환경 관리 클래스
 * 생명주기를 명확히 관리
 */
export class TestDatabaseEnvironment {
  private container: StartedPostgreSqlContainer | null = null;
  private dataSource: DataSource | null = null;

  /**
   * PostgreSQL 컨테이너 시작
   * @returns 연결 정보
   * @throws {Error} 컨테이너 시작 실패 시
   */
  async start(): Promise<TestDatabaseConfig> {
    try {
      console.log('🐘 Starting PostgreSQL test container...');

      this.container = await new PostgreSqlContainer('postgres:15-alpine')
        .withDatabase('arrakis_test')
        .withUsername('test_user')
        .withPassword('test_password')
        .withExposedPorts(5432)
        .start();

      const config: TestDatabaseConfig = {
        host: this.container.getHost(),
        port: this.container.getMappedPort(5432),
        database: 'arrakis_test',
        username: 'test_user',
        password: 'test_password',
        connectionUri: this.container.getConnectionUri(),
      };

      console.log(`✅ PostgreSQL container started on port ${config.port}`);
      return config;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      throw new Error(`Failed to start PostgreSQL container: ${message}`);
    }
  }

  /**
   * TypeORM DataSource 생성 및 초기화
   * @param dbConfig 데이터베이스 연결 정보
   * @returns 초기화된 DataSource
   */
  async createDataSource(dbConfig: TestDatabaseConfig): Promise<DataSource> {
    try {
      this.dataSource = new DataSource({
        type: 'postgres',
        host: dbConfig.host,
        port: dbConfig.port,
        database: dbConfig.database,
        username: dbConfig.username,
        password: dbConfig.password,
        synchronize: true, // 테스트 환경에서만 사용
        dropSchema: true, // 각 테스트마다 깨끗한 상태 보장
        entities: [`${__dirname  }/../../entities/*.ts`],
        logging: process.env['DATABASE_LOGGING'] === 'true',
      });

      await this.dataSource.initialize();
      console.log('✅ DataSource initialized');

      return this.dataSource;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      throw new Error(`Failed to initialize DataSource: ${message}`);
    }
  }

  /**
   * 테스트 데이터 시드
   * 명시적으로 어떤 데이터가 생성되는지 정의
   */
  async seedTestData(dataSource: DataSource): Promise<void> {
    const queryRunner = dataSource.createQueryRunner();

    try {
      await queryRunner.connect();
      await queryRunner.startTransaction();

      // ObjectType 테스트 데이터
      await queryRunner.query(`
        INSERT INTO object_types (rid, "apiName", "displayName", "pluralDisplayName", status, visibility, "createdBy", "updatedBy", version)
        VALUES 
          ('550e8400-e29b-41d4-a716-446655440001', 'customer', 'Customer', 'Customers', 'active', 'normal', 'test-user', 'test-user', 1),
          ('550e8400-e29b-41d4-a716-446655440002', 'product', 'Product', 'Products', 'active', 'normal', 'test-user', 'test-user', 1),
          ('550e8400-e29b-41d4-a716-446655440003', 'order', 'Order', 'Orders', 'experimental', 'hidden', 'test-user', 'test-user', 1)
      `);

      await queryRunner.commitTransaction();
      console.log('✅ Test data seeded');
    } catch (error) {
      await queryRunner.rollbackTransaction();
      throw new Error(`Failed to seed test data: ${error}`);
    } finally {
      await queryRunner.release();
    }
  }

  /**
   * 모든 리소스 정리
   * 반드시 실행되어야 함
   */
  async cleanup(): Promise<void> {
    const errors: Error[] = [];

    // DataSource 정리
    if (this.dataSource?.isInitialized) {
      try {
        await this.dataSource.destroy();
        console.log('✅ DataSource destroyed');
      } catch (error) {
        errors.push(new Error(`Failed to destroy DataSource: ${error}`));
      }
    }

    // Container 정리
    if (this.container) {
      try {
        await this.container.stop();
        console.log('✅ PostgreSQL container stopped');
      } catch (error) {
        errors.push(new Error(`Failed to stop container: ${error}`));
      }
    }

    // 에러가 있으면 모두 보고
    if (errors.length > 0) {
      const messages = errors.map((e) => e.message).join('; ');
      throw new Error(`Cleanup failed with errors: ${messages}`);
    }
  }
}

/**
 * 전역 테스트 환경 인스턴스
 * 테스트 스위트 간 공유
 */
export const testEnvironment = new TestDatabaseEnvironment();
