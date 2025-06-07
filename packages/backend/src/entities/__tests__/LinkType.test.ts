import { LinkType } from '../LinkType';
import { ObjectType } from '../ObjectType';
import { LinkCardinality, NodeStatus } from '../types';

describe('LinkType Entity', () => {
  it('should create an instance with required properties', () => {
    // Arrange
    const sourceObjectType = new ObjectType();
    sourceObjectType.rid = 'source-object-type-id';

    const targetObjectType = new ObjectType();
    targetObjectType.rid = 'target-object-type-id';

    // Act
    const linkType = new LinkType();
    linkType.apiName = 'hasParent';
    linkType.displayName = 'Has Parent';
    linkType.reverseDisplayName = 'Has Child';
    linkType.cardinality = LinkCardinality.ONE_TO_MANY;
    linkType.required = false;
    linkType.status = NodeStatus.ACTIVE;
    linkType.sourceObjectType = sourceObjectType;
    linkType.targetObjectType = targetObjectType;

    // Assert
    expect(linkType.apiName).toBe('hasParent');
    expect(linkType.displayName).toBe('Has Parent');
    expect(linkType.reverseDisplayName).toBe('Has Child');
    expect(linkType.cardinality).toBe(LinkCardinality.ONE_TO_MANY);
    expect(linkType.required).toBe(false);
    expect(linkType.status).toBe(NodeStatus.ACTIVE);
    expect(linkType.sourceObjectType).toBe(sourceObjectType);
    expect(linkType.targetObjectType).toBe(targetObjectType);
  });

  it('should have optional properties', () => {
    // Arrange & Act
    const linkType = new LinkType();

    // Assert
    expect(linkType).toHaveProperty('description');
    expect(linkType).toHaveProperty('metadata');
  });

  it('should have base entity properties', () => {
    // Arrange & Act
    const linkType = new LinkType();

    // Assert
    expect(linkType).toHaveProperty('rid');
    expect(linkType).toHaveProperty('createdAt');
    expect(linkType).toHaveProperty('updatedAt');
    expect(linkType).toHaveProperty('version');
  });

  it('should support all cardinality types', () => {
    // Arrange & Act
    const linkType = new LinkType();

    // Assert - verify cardinality field accepts all enum values
    linkType.cardinality = LinkCardinality.ONE_TO_ONE;
    expect(linkType.cardinality).toBe(LinkCardinality.ONE_TO_ONE);

    linkType.cardinality = LinkCardinality.ONE_TO_MANY;
    expect(linkType.cardinality).toBe(LinkCardinality.ONE_TO_MANY);

    linkType.cardinality = LinkCardinality.MANY_TO_MANY;
    expect(linkType.cardinality).toBe(LinkCardinality.MANY_TO_MANY);
  });
});
