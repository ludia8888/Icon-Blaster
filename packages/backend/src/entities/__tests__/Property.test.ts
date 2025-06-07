import { ObjectType } from '../ObjectType';
import { Property } from '../Property';
import { PropertyType } from '../types';

describe('Property Entity', () => {
  it('should create an instance with required properties', () => {
    // Arrange
    const objectType = new ObjectType();
    objectType.rid = 'test-object-type-id';

    // Act
    const property = new Property();
    property.apiName = 'testProperty';
    property.displayName = 'Test Property';
    property.type = PropertyType.STRING;
    property.required = false;
    property.multiple = false;
    property.objectType = objectType;

    // Assert
    expect(property.apiName).toBe('testProperty');
    expect(property.displayName).toBe('Test Property');
    expect(property.type).toBe(PropertyType.STRING);
    expect(property.required).toBe(false);
    expect(property.multiple).toBe(false);
    expect(property.objectType).toBe(objectType);
  });

  it('should have optional properties', () => {
    // Arrange & Act
    const property = new Property();

    // Assert
    expect(property).toHaveProperty('description');
    expect(property).toHaveProperty('defaultValue');
    expect(property).toHaveProperty('constraints');
    expect(property).toHaveProperty('metadata');
  });

  it('should have base entity properties', () => {
    // Arrange & Act
    const property = new Property();

    // Assert
    expect(property).toHaveProperty('rid');
    expect(property).toHaveProperty('createdAt');
    expect(property).toHaveProperty('updatedAt');
    expect(property).toHaveProperty('version');
  });

  it('should support all property types', () => {
    // Arrange & Act
    const property = new Property();

    // Assert - just verify the type field exists and can accept PropertyType enum
    property.type = PropertyType.STRING;
    expect(property.type).toBe(PropertyType.STRING);

    property.type = PropertyType.INTEGER;
    expect(property.type).toBe(PropertyType.INTEGER);

    property.type = PropertyType.BOOLEAN;
    expect(property.type).toBe(PropertyType.BOOLEAN);
  });
});
