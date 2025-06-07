import { Entity, Column } from 'typeorm';

import { BaseEntity } from '../BaseEntity';

@Entity()
class TestEntity extends BaseEntity {
  @Column()
  name!: string;
}

describe('BaseEntity', () => {
  it('should have rid property', () => {
    // Arrange & Act
    const entity = new TestEntity();

    // Assert
    expect(entity).toHaveProperty('rid');
  });

  it('should have createdAt property', () => {
    // Arrange & Act
    const entity = new TestEntity();

    // Assert
    expect(entity).toHaveProperty('createdAt');
  });

  it('should have updatedAt property', () => {
    // Arrange & Act
    const entity = new TestEntity();

    // Assert
    expect(entity).toHaveProperty('updatedAt');
  });

  it('should have version property', () => {
    // Arrange & Act
    const entity = new TestEntity();

    // Assert
    expect(entity).toHaveProperty('version');
  });

  it('should have createdBy property', () => {
    // Arrange & Act
    const entity = new TestEntity();

    // Assert
    expect(entity).toHaveProperty('createdBy');
  });

  it('should have updatedBy property', () => {
    // Arrange & Act
    const entity = new TestEntity();

    // Assert
    expect(entity).toHaveProperty('updatedBy');
  });

  describe('generateRid', () => {
    it('should generate a new rid when not set', () => {
      // Arrange
      const entity = new TestEntity();

      // Act
      entity.generateRid();

      // Assert
      expect(entity.rid).toBeDefined();
      expect(entity.rid).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
    });

    it('should not override existing rid', () => {
      // Arrange
      const entity = new TestEntity();
      const existingRid = 'existing-rid-12345';
      entity.rid = existingRid;

      // Act
      entity.generateRid();

      // Assert
      expect(entity.rid).toBe(existingRid);
    });
  });
});
