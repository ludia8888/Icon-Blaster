import { ObjectType } from '../ObjectType';
import { NodeStatus, NodeVisibility } from '../types';

describe('ObjectType Entity', () => {
  it('should create an instance with required properties', () => {
    // Arrange & Act
    const objectType = new ObjectType();
    objectType.apiName = 'TestObject';
    objectType.displayName = 'Test Object';
    objectType.pluralDisplayName = 'Test Objects';
    objectType.status = NodeStatus.ACTIVE;
    objectType.visibility = NodeVisibility.NORMAL;

    // Assert
    expect(objectType.apiName).toBe('TestObject');
    expect(objectType.displayName).toBe('Test Object');
    expect(objectType.pluralDisplayName).toBe('Test Objects');
    expect(objectType.status).toBe(NodeStatus.ACTIVE);
    expect(objectType.visibility).toBe(NodeVisibility.NORMAL);
  });

  it('should have optional properties', () => {
    // Arrange & Act
    const objectType = new ObjectType();

    // Assert
    expect(objectType).toHaveProperty('description');
    expect(objectType).toHaveProperty('icon');
    expect(objectType).toHaveProperty('color');
    expect(objectType).toHaveProperty('metadata');
    expect(objectType).toHaveProperty('titleProperty');
  });

  it('should have base entity properties', () => {
    // Arrange & Act
    const objectType = new ObjectType();

    // Assert
    expect(objectType).toHaveProperty('rid');
    expect(objectType).toHaveProperty('createdAt');
    expect(objectType).toHaveProperty('updatedAt');
    expect(objectType).toHaveProperty('version');
  });

  it('should have properties relation', () => {
    // Arrange & Act
    const objectType = new ObjectType();

    // Assert
    expect(objectType).toHaveProperty('properties');
  });

  it('should have sourceLinks and targetLinks relations', () => {
    // Arrange & Act
    const objectType = new ObjectType();

    // Assert
    expect(objectType).toHaveProperty('sourceLinks');
    expect(objectType).toHaveProperty('targetLinks');
  });
});
