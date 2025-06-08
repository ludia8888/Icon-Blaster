/**
 * Common type definitions used throughout the application
 * These provide more specific types than 'unknown' or 'any'
 */

/**
 * JSON-serializable values
 */
export type JsonValue = 
  | string 
  | number 
  | boolean 
  | null
  | JsonArray 
  | JsonObject;

export interface JsonObject {
  [key: string]: JsonValue;
}

export interface JsonArray extends Array<JsonValue> {}

/**
 * API Response types
 */
export interface ApiResponse<T = JsonObject> {
  data?: T;
  error?: string;
  message?: string;
  status?: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
  };
}

/**
 * Database entity base types
 */
export interface BaseEntity {
  id: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface AuditableEntity extends BaseEntity {
  createdBy: string;
  updatedBy: string;
}

/**
 * Request/Response helper types
 */
export type RequestBody = JsonObject;
export type RequestQuery = Record<string, string | string[] | undefined>;
export type RequestParams = Record<string, string>;

/**
 * Error response types
 */
export interface ErrorResponse {
  message: string;
  code?: string;
  details?: JsonObject;
  stack?: string;
}

/**
 * Configuration types
 */
export interface DatabaseConfig {
  host: string;
  port: number;
  username: string;
  password: string;
  database: string;
}

export interface ServerConfig {
  port: number;
  host: string;
  environment: 'development' | 'test' | 'production';
}

/**
 * User context types
 */
export interface UserContext {
  id: string;
  email: string;
  roles: string[];
  permissions?: string[];
}

/**
 * Utility types
 */
export type Nullable<T> = T | null;
export type Optional<T> = T | undefined;
export type MaybePromise<T> = T | Promise<T>;

/**
 * Type guards
 */
export function isJsonObject(value: unknown): value is JsonObject {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    !(value instanceof Date) &&
    !(value instanceof RegExp)
  );
}

export function isJsonArray(value: unknown): value is JsonArray {
  return Array.isArray(value);
}

export function isString(value: unknown): value is string {
  return typeof value === 'string';
}

export function isNumber(value: unknown): value is number {
  return typeof value === 'number' && !isNaN(value);
}

export function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean';
}

/**
 * Type assertion helpers
 */
export function assertDefined<T>(
  value: T | null | undefined,
  message = 'Value is null or undefined'
): asserts value is T {
  if (value === null || value === undefined) {
    throw new Error(message);
  }
}

export function assertString(
  value: unknown,
  message = 'Value is not a string'
): asserts value is string {
  if (typeof value !== 'string') {
    throw new Error(message);
  }
}

export function assertNumber(
  value: unknown,
  message = 'Value is not a number'
): asserts value is number {
  if (typeof value !== 'number' || isNaN(value)) {
    throw new Error(message);
  }
}