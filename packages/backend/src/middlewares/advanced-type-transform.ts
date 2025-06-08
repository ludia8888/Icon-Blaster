import { Request } from 'express';
import { z } from 'zod';

import { logger } from '../utils/logger';

import { TransformingMiddleware } from './type-transforming-middleware';

/**
 * Advanced type transformations for production use
 * 
 * These examples show how to implement complex type transformations
 * while maintaining full type safety.
 */

/**
 * Transform and enrich user context
 */
export interface EnrichedUser {
  id: string;
  email: string;
  roles: string[];
  permissions: string[];
  organizationId?: string;
  metadata: {
    lastActivity: Date;
    ipAddress: string;
    userAgent: string;
  };
}

export function enrichUserContext(): TransformingMiddleware<
  Request & { user?: { id: string; email: string; roles: string[] } },
  Request & { user: EnrichedUser }
> {
  return async (req, _res, next) => {
    if (!req.user) {
      throw new Error('User not authenticated');
    }

    // Enrich user with additional context
    const enrichedUser: EnrichedUser = {
      ...req.user,
      permissions: await loadUserPermissions(req.user.id),
      organizationId: await loadUserOrganization(req.user.id),
      metadata: {
        lastActivity: new Date(),
        ipAddress: req.ip ?? 'unknown',
        userAgent: req.get('user-agent') ?? 'unknown',
      },
    };

    (req as Request & { user: EnrichedUser }).user = enrichedUser;
    next();
  };
}

/**
 * Parse and validate complex query parameters
 */
const PaginationSchema = z.object({
  page: z.coerce.number().min(1).default(1),
  limit: z.coerce.number().min(1).max(100).default(20),
  sortBy: z.string().optional(),
  sortOrder: z.enum(['asc', 'desc']).default('asc'),
});

const FilterSchema = z.object({
  status: z.enum(['active', 'inactive', 'all']).optional(),
  createdAfter: z.coerce.date().optional(),
  createdBefore: z.coerce.date().optional(),
  tags: z.array(z.string()).optional(),
});

export interface EnhancedQuery {
  pagination: z.infer<typeof PaginationSchema>;
  filters: z.infer<typeof FilterSchema>;
  searchTerm?: string;
}

export function parseComplexQuery(): TransformingMiddleware<
  Request,
  Request & { query: EnhancedQuery }
> {
  return (req, _res, next) => {
    try {
      // Extract pagination params
      const paginationResult = PaginationSchema.safeParse({
        page: req.query.page,
        limit: req.query.limit,
        sortBy: req.query.sortBy,
        sortOrder: req.query.sortOrder,
      });

      if (!paginationResult.success) {
        throw new Error(`Invalid pagination: ${paginationResult.error.message}`);
      }

      // Extract filter params
      const filterResult = FilterSchema.safeParse({
        status: req.query.status,
        createdAfter: req.query.createdAfter,
        createdBefore: req.query.createdBefore,
        tags: req.query.tags ? String(req.query.tags).split(',') : undefined,
      });

      if (!filterResult.success) {
        throw new Error(`Invalid filters: ${filterResult.error.message}`);
      }

      const enhancedQuery: EnhancedQuery = {
        pagination: paginationResult.data,
        filters: filterResult.data,
        searchTerm: req.query.search ? String(req.query.search) : undefined,
      };

      (req as Request & { query: EnhancedQuery }).query = enhancedQuery;
      next();
    } catch (error) {
      next(error);
    }
  };
}

/**
 * Add request context for logging and tracing
 */
export interface RequestContext {
  requestId: string;
  timestamp: Date;
  path: string;
  method: string;
  userId?: string;
  correlationId?: string;
}

export function addRequestContext(): TransformingMiddleware<
  Request,
  Request & { context: RequestContext }
> {
  return (req, _res, next) => {
    const context: RequestContext = {
      requestId: generateRequestId(),
      timestamp: new Date(),
      path: req.path,
      method: req.method,
      userId: req.user?.id,
      correlationId: req.get('x-correlation-id'),
    };

    (req as Request & { context: RequestContext }).context = context;
    
    // Add context to logger
    logger.info('Request started', { context });
    
    next();
  };
}

/**
 * Transform file uploads
 */
export interface ProcessedFile {
  originalName: string;
  mimeType: string;
  size: number;
  buffer: Buffer;
  metadata: {
    width?: number;
    height?: number;
    duration?: number;
  };
}

export function processFileUpload(): TransformingMiddleware<
  Request & { file?: Express.Multer.File },
  Request & { file: ProcessedFile }
> {
  return async (req, _res, next) => {
    if (!req.file) {
      throw new Error('No file uploaded');
    }

    const processedFile: ProcessedFile = {
      originalName: req.file.originalname,
      mimeType: req.file.mimetype,
      size: req.file.size,
      buffer: req.file.buffer,
      metadata: await extractFileMetadata(req.file),
    };

    (req as Request & { file: ProcessedFile }).file = processedFile;
    next();
  };
}

/**
 * Chain multiple transformations
 */
export function createAdvancedChain() {
  return {
    withAuth: enrichUserContext(),
    withPagination: parseComplexQuery(),
    withContext: addRequestContext(),
    withFileProcessing: processFileUpload(),
  };
}

// Helper functions (implementations would be in separate modules)
async function loadUserPermissions(userId: string): Promise<string[]> {
  // Load from database or cache
  return ['read:objects', 'write:objects'];
}

async function loadUserOrganization(userId: string): Promise<string | undefined> {
  // Load from database
  return 'org-123';
}

function generateRequestId(): string {
  return `req-${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
}

interface FileMetadata {
  width?: number;
  height?: number;
  duration?: number;
  format?: string;
  size: number;
}

async function extractFileMetadata(file: Express.Multer.File): Promise<FileMetadata> {
  // Extract metadata based on file type
  return {
    size: file.size,
    format: file.mimetype,
  };
}

/**
 * Example usage in routes:
 * 
 * router.get('/objects',
 *   authenticate,
 *   enrichUserContext(),
 *   parseComplexQuery(),
 *   addRequestContext(),
 *   asyncHandler(async (req, res) => {
 *     // req.user is EnrichedUser
 *     // req.query is EnhancedQuery
 *     // req.context is RequestContext
 *     
 *     const permissions = req.user.permissions; // string[]
 *     const page = req.query.pagination.page; // number
 *     const requestId = req.context.requestId; // string
 *   })
 * );
 */