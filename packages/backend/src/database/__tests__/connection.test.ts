import { initializeDatabase, closeDatabase, getDataSource } from '../connection';

// Mock TypeORM
jest.mock('typeorm', () => {
  const mockDataSource = {
    isInitialized: false,
    initialize: jest.fn(),
    destroy: jest.fn(),
  };

  return {
    DataSource: jest.fn().mockImplementation(() => mockDataSource),
  };
});

describe('Database Connection', () => {
  interface MockDataSource {
    isInitialized: boolean;
    initialize: jest.Mock;
    destroy: jest.Mock;
  }
  let mockDataSource: MockDataSource;

  beforeEach(() => {
    jest.clearAllMocks();
    // Get reference to the mock instance
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const TypeORMModule = require('typeorm') as { DataSource: new () => MockDataSource };
    mockDataSource = new TypeORMModule.DataSource();
  });

  afterEach(async () => {
    await closeDatabase();
  });

  describe('initializeDatabase', () => {
    it('should initialize database connection successfully', async () => {
      // Arrange
      mockDataSource.initialize.mockResolvedValueOnce(mockDataSource as never);
      mockDataSource.isInitialized = true;

      // Act
      const dataSource = await initializeDatabase();

      // Assert
      expect(dataSource).toBeDefined();
      expect(mockDataSource.initialize).toHaveBeenCalled();
    });

    it('should return existing connection if already initialized', async () => {
      // Arrange
      mockDataSource.initialize.mockResolvedValueOnce(mockDataSource as never);
      mockDataSource.isInitialized = true;

      // Act
      const firstConnection = await initializeDatabase();
      const secondConnection = await initializeDatabase();

      // Assert
      expect(secondConnection).toBe(firstConnection);
      expect(mockDataSource.initialize).toHaveBeenCalledTimes(1);
    });

    it('should handle connection errors', async () => {
      // Arrange
      const error = new Error('Connection failed');
      mockDataSource.initialize.mockRejectedValueOnce(error);

      // Act & Assert
      await expect(initializeDatabase()).rejects.toThrow(
        'Failed to connect to database: Connection failed'
      );
    });
  });

  describe('closeDatabase', () => {
    it('should close database connection successfully', async () => {
      // Arrange
      mockDataSource.initialize.mockResolvedValueOnce(mockDataSource as never);
      mockDataSource.isInitialized = true;
      await initializeDatabase();

      mockDataSource.destroy.mockResolvedValueOnce(undefined);

      // Act
      await closeDatabase();

      // Assert
      expect(mockDataSource.destroy).toHaveBeenCalled();
    });

    it('should handle multiple close calls gracefully', async () => {
      // Arrange
      mockDataSource.initialize.mockResolvedValueOnce(mockDataSource as never);
      mockDataSource.isInitialized = true;
      await initializeDatabase();

      mockDataSource.destroy.mockImplementation(() => {
        mockDataSource.isInitialized = false;
        return Promise.resolve();
      });

      // Act & Assert
      await expect(closeDatabase()).resolves.not.toThrow();
      await expect(closeDatabase()).resolves.not.toThrow();
      expect(mockDataSource.destroy).toHaveBeenCalledTimes(1);
    });
  });

  describe('getDataSource', () => {
    it('should throw error if connection not initialized', () => {
      // Act & Assert
      expect(() => getDataSource()).toThrow('Database connection not initialized');
    });

    it('should return data source after initialization', async () => {
      // Arrange
      mockDataSource.initialize.mockResolvedValueOnce(mockDataSource as never);
      mockDataSource.isInitialized = true;
      await initializeDatabase();

      // Act
      const dataSource = getDataSource();

      // Assert
      expect(dataSource).toBeDefined();
    });
  });
});
