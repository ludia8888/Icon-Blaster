import { NodeStatus, NodeVisibility } from '@arrakis/shared';

import {
  CreateObjectTypeSchema,
  UpdateObjectTypeSchema,
  ObjectTypeResponseSchema,
  validateCreateObjectType,
  validateUpdateObjectType,
} from '../objectType';

describe('ObjectType Schemas', () => {
  describe('CreateObjectTypeSchema', () => {
    it('should validate valid create request', () => {
      // Arrange
      const validData = {
        apiName: 'Employee',
        displayName: 'Employee',
        description: 'Employee entity',
        icon: 'person',
        color: '#0052CC',
        groups: ['HR', 'Core'],
        visibility: NodeVisibility.NORMAL,
        status: NodeStatus.ACTIVE,
      };

      // Act & Assert
      const result = CreateObjectTypeSchema.safeParse(validData);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toMatchObject(validData);
      }
    });

    it('should require mandatory fields', () => {
      // Arrange
      const invalidData = {
        displayName: 'Employee',
      };

      // Act
      const result = CreateObjectTypeSchema.safeParse(invalidData);

      // Assert
      expect(result.success).toBe(false);
      if (!result.success) {
        const errors = result.error.flatten();
        expect(errors.fieldErrors.apiName).toBeDefined();
      }
    });

    it('should validate apiName format', () => {
      // Arrange
      const invalidData = {
        apiName: 'Employee-123', // contains hyphen
        displayName: 'Employee',
      };

      // Act
      const result = CreateObjectTypeSchema.safeParse(invalidData);

      // Assert
      expect(result.success).toBe(false);
    });
  });

  describe('UpdateObjectTypeSchema', () => {
    it('should allow partial updates', () => {
      // Arrange
      const updateData = {
        displayName: 'Updated Employee',
        description: 'Updated description',
      };

      // Act
      const result = UpdateObjectTypeSchema.safeParse(updateData);

      // Assert
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toMatchObject(updateData);
      }
    });

    it('should validate color format when provided', () => {
      // Arrange
      const invalidData = {
        color: 'not-a-color',
      };

      // Act
      const result = UpdateObjectTypeSchema.safeParse(invalidData);

      // Assert
      expect(result.success).toBe(false);
    });
  });

  describe('ObjectTypeResponseSchema', () => {
    it('should validate complete response object', () => {
      // Arrange
      const responseData = {
        rid: '550e8400-e29b-41d4-a716-446655440000',
        apiName: 'Employee',
        displayName: 'Employee',
        description: 'Employee entity',
        icon: 'person',
        color: '#0052CC',
        groups: ['HR'],
        visibility: NodeVisibility.NORMAL,
        status: NodeStatus.ACTIVE,
        version: 1,
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
        createdBy: 'user123',
        updatedBy: 'user123',
      };

      // Act
      const result = ObjectTypeResponseSchema.safeParse(responseData);

      // Assert
      expect(result.success).toBe(true);
    });
  });

  describe('Validation functions', () => {
    it('should validate and transform create request', () => {
      // Arrange
      const data = {
        apiName: 'Employee',
        displayName: 'Employee',
      };

      // Act
      const result = validateCreateObjectType(data);

      // Assert
      expect(result.success).toBe(true);
      if (result.success && result.data) {
        expect(result.data.visibility).toBe(NodeVisibility.NORMAL);
        expect(result.data.status).toBe(NodeStatus.ACTIVE);
      }
    });

    it('should return errors for invalid data', () => {
      // Arrange
      const data = {
        apiName: '',
        displayName: '',
      };

      // Act
      const result = validateCreateObjectType(data);

      // Assert
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.errors).toContain('API name must be at least 1 character');
        expect(result.errors).toContain('Display name must be at least 1 character');
      }
    });

    it('should validate update request', () => {
      // Arrange
      const data = {
        displayName: 'Updated Name',
        status: NodeStatus.DEPRECATED,
      };

      // Act
      const result = validateUpdateObjectType(data);

      // Assert
      expect(result.success).toBe(true);
      if (result.success && result.data) {
        expect(result.data.displayName).toBe('Updated Name');
        expect(result.data.status).toBe(NodeStatus.DEPRECATED);
      }
    });

    it('should handle invalid update data', () => {
      // Arrange
      const data = {
        displayName: '', // too short
        color: 'not-hex',
      };

      // Act
      const result = validateUpdateObjectType(data);

      // Assert
      expect(result.success).toBe(false);
      if (!result.success && result.errors) {
        expect(result.errors.length).toBeGreaterThan(0);
      }
    });
  });
});
