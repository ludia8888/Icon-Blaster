import {
  NodeType,
  NodeStatus,
  NodeVisibility,
  BaseType,
  type NodeMetadata,
  createDefaultNode,
  createDefaultProperty,
  validateNodeMetadata,
} from '../ontology';

describe('Ontology types', () => {
  describe('Enums', () => {
    it('should have correct enum values', () => {
      // Assert
      expect(NodeType.OBJECT).toBe('object');
      expect(NodeType.INTERFACE).toBe('interface');
      expect(NodeType.ACTION).toBe('action');
      
      expect(NodeStatus.ACTIVE).toBe('active');
      expect(NodeStatus.EXPERIMENTAL).toBe('experimental');
      expect(NodeStatus.DEPRECATED).toBe('deprecated');
      
      expect(NodeVisibility.PROMINENT).toBe('prominent');
      expect(NodeVisibility.NORMAL).toBe('normal');
      expect(NodeVisibility.HIDDEN).toBe('hidden');
    });
  });

  describe('createDefaultNode', () => {
    it('should create node with required fields', () => {
      // Arrange
      const params = {
        apiName: 'Employee',
        displayName: 'Employee',
        type: NodeType.OBJECT,
      };
      
      // Act
      const node = createDefaultNode(params);
      
      // Assert
      expect(node).toMatchObject({
        apiName: 'Employee',
        displayName: 'Employee',
        type: NodeType.OBJECT,
        position: { x: 0, y: 0 },
        version: 1,
      });
      expect(node.rid).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
      expect(node.createdAt).toBeInstanceOf(Date);
      expect(node.updatedAt).toBeInstanceOf(Date);
    });

    it('should create node with optional metadata', () => {
      // Arrange
      const params = {
        apiName: 'Employee',
        displayName: 'Employee',
        type: NodeType.OBJECT,
        metadata: {
          description: 'Employee entity',
          icon: 'person',
          color: '#0052CC',
        },
      };
      
      // Act
      const node = createDefaultNode(params);
      
      // Assert
      expect(node.metadata).toMatchObject({
        description: 'Employee entity',
        icon: 'person',
        color: '#0052CC',
        visibility: NodeVisibility.NORMAL,
        status: NodeStatus.ACTIVE,
      });
    });
  });

  describe('createDefaultProperty', () => {
    it('should create property with defaults', () => {
      // Arrange
      const params = {
        apiName: 'fullName',
        displayName: 'Full Name',
        baseType: BaseType.STRING,
        objectRid: '550e8400-e29b-41d4-a716-446655440000',
      };
      
      // Act
      const property = createDefaultProperty(params);
      
      // Assert
      expect(property).toMatchObject({
        apiName: 'fullName',
        displayName: 'Full Name',
        baseType: BaseType.STRING,
        objectRid: '550e8400-e29b-41d4-a716-446655440000',
        titleKey: false,
        primaryKey: false,
        renderHints: {
          searchable: true,
          sortable: true,
          filterable: true,
        },
      });
    });
  });

  describe('validateNodeMetadata', () => {
    it('should validate valid metadata', () => {
      // Arrange
      const metadata: NodeMetadata = {
        description: 'Test',
        icon: 'test-icon',
        color: '#FF0000',
        groups: ['group1'],
        visibility: NodeVisibility.NORMAL,
        status: NodeStatus.ACTIVE,
      };
      
      // Act
      const result = validateNodeMetadata(metadata);
      
      // Assert
      expect(result.valid).toBe(true);
      expect(result.errors).toEqual([]);
    });

    it('should validate invalid color format', () => {
      // Arrange
      const metadata: NodeMetadata = {
        color: 'invalid-color',
        visibility: NodeVisibility.NORMAL,
        status: NodeStatus.ACTIVE,
      };
      
      // Act
      const result = validateNodeMetadata(metadata);
      
      // Assert
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Invalid color format');
    });

    it('should validate invalid visibility', () => {
      // Arrange
      const metadata = {
        visibility: 'invalid' as any,
        status: NodeStatus.ACTIVE,
      } as NodeMetadata;
      
      // Act
      const result = validateNodeMetadata(metadata);
      
      // Assert
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Invalid visibility value');
    });

    it('should validate invalid status', () => {
      // Arrange
      const metadata = {
        visibility: NodeVisibility.NORMAL,
        status: 'invalid' as any,
      } as NodeMetadata;
      
      // Act
      const result = validateNodeMetadata(metadata);
      
      // Assert
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Invalid status value');
    });
  });
});