import * as databaseExports from '../index';

describe('Database exports', () => {
  it('should export all database functions', () => {
    // Assert
    expect(databaseExports).toHaveProperty('initializeDatabase');
    expect(databaseExports).toHaveProperty('closeDatabase');
    expect(databaseExports).toHaveProperty('getDataSource');
    expect(databaseExports).toHaveProperty('getDatabaseConfig');
    expect(databaseExports).toHaveProperty('validateDatabaseConfig');
  });
});
