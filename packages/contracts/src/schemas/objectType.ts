import { NodeStatus, NodeVisibility } from '@arrakis/shared';
import { z } from 'zod';

/**
 * API name validation pattern (alphanumeric with underscores)
 */
const API_NAME_REGEX = /^[a-zA-Z][a-zA-Z0-9_]*$/;

/**
 * Color validation pattern (hex color)
 */
const HEX_COLOR_REGEX = /^#[0-9A-F]{6}$/i;

/**
 * Create ObjectType request schema
 */
export const CreateObjectTypeSchema = z.object({
  apiName: z
    .string()
    .min(1, 'API name must be at least 1 character')
    .max(100, 'API name must not exceed 100 characters')
    .regex(API_NAME_REGEX, 'API name must be alphanumeric with underscores'),
  displayName: z
    .string()
    .min(1, 'Display name must be at least 1 character')
    .max(200, 'Display name must not exceed 200 characters'),
  description: z.string().max(1000, 'Description must not exceed 1000 characters').optional(),
  icon: z.string().max(50, 'Icon name must not exceed 50 characters').optional(),
  color: z.string().regex(HEX_COLOR_REGEX, 'Color must be a valid hex color').optional(),
  groups: z
    .array(z.string().max(50, 'Group name must not exceed 50 characters'))
    .max(10, 'Cannot have more than 10 groups')
    .optional(),
  visibility: z.nativeEnum(NodeVisibility).default(NodeVisibility.NORMAL),
  status: z.nativeEnum(NodeStatus).default(NodeStatus.ACTIVE),
});

/**
 * Update ObjectType request schema (all fields optional)
 */
export const UpdateObjectTypeSchema = CreateObjectTypeSchema.partial().omit({
  apiName: true,
});

/**
 * ObjectType response schema
 */
export const ObjectTypeResponseSchema = z.object({
  rid: z.string().uuid(),
  apiName: z.string(),
  displayName: z.string(),
  description: z.string().optional(),
  icon: z.string().optional(),
  color: z.string().optional(),
  groups: z.array(z.string()).optional(),
  visibility: z.nativeEnum(NodeVisibility),
  status: z.nativeEnum(NodeStatus),
  version: z.number().int().positive(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  createdBy: z.string(),
  updatedBy: z.string(),
});

/**
 * List response schema with pagination
 */
export const ObjectTypeListResponseSchema = z.object({
  data: z.array(ObjectTypeResponseSchema),
  pagination: z.object({
    total: z.number().int().nonnegative(),
    page: z.number().int().positive(),
    limit: z.number().int().positive(),
    totalPages: z.number().int().nonnegative(),
  }),
});

/**
 * Type exports
 */
export type CreateObjectTypeDto = z.infer<typeof CreateObjectTypeSchema>;
export type UpdateObjectTypeDto = z.infer<typeof UpdateObjectTypeSchema>;
export type ObjectTypeResponse = z.infer<typeof ObjectTypeResponseSchema>;
export type ObjectTypeListResponse = z.infer<typeof ObjectTypeListResponseSchema>;

/**
 * Validation result type
 */
interface ValidationResult<T> {
  success: boolean;
  data?: T;
  errors?: string[];
}

/**
 * Validate create request
 */
export function validateCreateObjectType(data: unknown): ValidationResult<CreateObjectTypeDto> {
  const result = CreateObjectTypeSchema.safeParse(data);

  if (result.success) {
    return { success: true, data: result.data };
  }

  const errors = result.error.issues.map((issue) => issue.message);
  return { success: false, errors };
}

/**
 * Validate update request
 */
export function validateUpdateObjectType(data: unknown): ValidationResult<UpdateObjectTypeDto> {
  const result = UpdateObjectTypeSchema.safeParse(data);

  if (result.success) {
    return { success: true, data: result.data };
  }

  const errors = result.error.issues.map((issue) => issue.message);
  return { success: false, errors };
}
