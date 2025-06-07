import * as entityExports from '../index';

describe('Entity exports', () => {
  it('should export all entities', () => {
    // Assert
    expect(entityExports).toHaveProperty('BaseEntity');
    expect(entityExports).toHaveProperty('ObjectType');
    expect(entityExports).toHaveProperty('Property');
    expect(entityExports).toHaveProperty('LinkType');
  });
});
