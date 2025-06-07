import { LinkType } from '../LinkType';
import { ObjectType } from '../ObjectType';
import { Property } from '../Property';
import { NodeStatus, NodeVisibility, PropertyType, LinkCardinality } from '../types';

describe('Entity Integration Tests', () => {
  describe('ObjectType', () => {
    it('should create with default values', () => {
      // Arrange & Act
      const objectType = new ObjectType();

      // Assert - just instantiate to ensure decorators work
      expect(objectType).toBeInstanceOf(ObjectType);
    });

    it('should create with all properties', () => {
      // Arrange & Act
      const objectType = new ObjectType();
      objectType.apiName = 'TestObject';
      objectType.displayName = 'Test Object';
      objectType.pluralDisplayName = 'Test Objects';
      objectType.description = 'Test description';
      objectType.icon = 'test-icon';
      objectType.color = '#123456';
      objectType.status = NodeStatus.ACTIVE;
      objectType.visibility = NodeVisibility.NORMAL;
      objectType.metadata = {
        visibility: NodeVisibility.NORMAL,
        status: NodeStatus.ACTIVE,
      };
      objectType.titleProperty = 'name';

      // Assert
      expect(objectType.apiName).toBe('TestObject');
      expect(objectType.icon).toBe('test-icon');
      expect(objectType.color).toBe('#123456');
      expect(objectType.metadata).toBeDefined();
      expect(objectType.titleProperty).toBe('name');
    });
  });

  describe('Property', () => {
    it('should create with all properties', () => {
      // Arrange
      const objectType = new ObjectType();
      objectType.rid = 'test-object-type';

      // Act
      const property = new Property();
      property.apiName = 'testProp';
      property.displayName = 'Test Property';
      property.description = 'Test description';
      property.type = PropertyType.STRING;
      property.required = true;
      property.multiple = true;
      property.defaultValue = 'default';
      property.constraints = {
        minLength: 1,
        maxLength: 100,
      };
      property.metadata = {
        visibility: NodeVisibility.NORMAL,
        status: NodeStatus.ACTIVE,
      };
      property.objectType = objectType;

      // Assert
      expect(property.description).toBe('Test description');
      expect(property.defaultValue).toBe('default');
      expect(property.constraints).toBeDefined();
      expect(property.metadata).toBeDefined();
    });
  });

  describe('LinkType', () => {
    it('should create with all properties', () => {
      // Arrange
      const sourceObjectType = new ObjectType();
      sourceObjectType.rid = 'source-type';
      const targetObjectType = new ObjectType();
      targetObjectType.rid = 'target-type';

      // Act
      const linkType = new LinkType();
      linkType.apiName = 'hasRelation';
      linkType.displayName = 'Has Relation';
      linkType.reverseDisplayName = 'Is Related To';
      linkType.description = 'Test description';
      linkType.cardinality = LinkCardinality.ONE_TO_MANY;
      linkType.required = true;
      linkType.status = NodeStatus.ACTIVE;
      linkType.metadata = {
        visibility: NodeVisibility.NORMAL,
        status: NodeStatus.ACTIVE,
      };
      linkType.sourceObjectType = sourceObjectType;
      linkType.targetObjectType = targetObjectType;

      // Assert
      expect(linkType.description).toBe('Test description');
      expect(linkType.metadata).toBeDefined();
      expect(linkType.sourceObjectType).toBe(sourceObjectType);
      expect(linkType.targetObjectType).toBe(targetObjectType);
    });
  });
});
