import { generateResourceId, isValidResourceId, parseResourceId } from '../resourceId';

describe('ResourceId utilities', () => {
  describe('generateResourceId', () => {
    it('should generate a valid UUID v4 format', () => {
      // Arrange & Act
      const rid = generateResourceId();

      // Assert
      expect(rid).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    });

    it('should generate unique IDs', () => {
      // Arrange & Act
      const ids = new Set(Array.from({ length: 100 }, () => generateResourceId()));

      // Assert
      expect(ids.size).toBe(100);
    });
  });

  describe('isValidResourceId', () => {
    it('should return true for valid UUID v4', () => {
      // Arrange
      const validId = '550e8400-e29b-41d4-a716-446655440000';

      // Act & Assert
      expect(isValidResourceId(validId)).toBe(true);
    });

    it('should return false for invalid formats', () => {
      // Arrange
      const invalidIds = [
        '',
        'not-a-uuid',
        '550e8400-e29b-41d4-a716',
        '550e8400-e29b-41d4-a716-44665544000g', // invalid character
        null,
        undefined,
      ];

      // Act & Assert
      invalidIds.forEach((id) => {
        expect(isValidResourceId(id as any)).toBe(false);
      });
    });
  });

  describe('parseResourceId', () => {
    it('should parse valid resource ID', () => {
      // Arrange
      const validId = '550e8400-e29b-41d4-a716-446655440000';

      // Act
      const result = parseResourceId(validId);

      // Assert
      expect(result).toEqual({
        valid: true,
        id: validId,
        error: null,
      });
    });

    it('should return error for invalid ID', () => {
      // Arrange
      const invalidId = 'invalid-id';

      // Act
      const result = parseResourceId(invalidId);

      // Assert
      expect(result).toEqual({
        valid: false,
        id: null,
        error: 'Invalid resource ID format',
      });
    });
  });
});
