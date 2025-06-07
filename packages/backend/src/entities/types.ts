// Re-export enums from shared with proper names for entities
export {
  BaseType as PropertyType,
  Cardinality as LinkCardinality,
  NodeStatus,
  NodeVisibility,
  NodeMetadata,
} from '@arrakis/shared';

// Additional entity-specific types
export interface PropertyConstraints {
  minLength?: number;
  maxLength?: number;
  min?: number;
  max?: number;
  pattern?: string;
  enum?: unknown[];
}
