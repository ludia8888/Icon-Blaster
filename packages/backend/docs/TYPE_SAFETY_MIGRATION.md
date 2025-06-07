# Type Safety Migration Guide

## Overview

This guide documents the migration from basic Express type handling to our enhanced type-safe middleware system.

## What Changed

### Before: Basic Express Types
```typescript
// No compile-time type safety
router.post('/api/users', async (req: Request, res: Response) => {
  const name = req.body.name; // any
  const age = req.body.age; // any
  
  // Runtime errors possible
  const upperName = name.toUpperCase(); // Could crash if name is undefined
});
```

### After: Type-Safe Middleware
```typescript
// Full compile-time type safety
router.post('/api/users', 
  ...defineRoute({
    body: z.object({
      name: z.string(),
      age: z.number().min(0),
    }),
    handler: async (req, res) => {
      const name = req.body.name; // string (guaranteed)
      const age = req.body.age; // number (guaranteed)
      
      const upperName = name.toUpperCase(); // Safe!
    }
  })
);
```

## Migration Steps

### 1. Replace createValidatedHandler with defineRoute

**Before:**
```typescript
router.post('/',
  authenticate,
  ...createValidatedHandler({ body: CreateObjectTypeSchema }, async (req, res) =>
    controller.create(req, res)
  )
);
```

**After:**
```typescript
router.post('/',
  authenticate,
  ...defineRoute({
    body: CreateObjectTypeSchema,
    handler: asyncHandler(async (req, res) => {
      await controller.create(req, res);
    }),
  })
);
```

### 2. Use middlewareChain for Complex Validations

```typescript
const createObjectChain = middlewareChain()
  .use(authenticate)
  .use(authorize(['admin', 'editor']))
  .use(validateBody(CreateObjectTypeSchema))
  .use(enrichUserContext())
  .build();

router.post('/objects',
  ...createObjectChain.handler(async (req, res) => {
    // req.body is CreateObjectTypeDto
    // req.user is EnrichedUser
  })
);
```

### 3. Update Controller Signatures

**Before:**
```typescript
class Controller {
  async create(req: Request, res: Response) {
    const data = req.body as CreateDto; // Type assertion
  }
}
```

**After:**
```typescript
class Controller {
  async create(
    req: Request & { body: CreateDto },
    res: Response<ResponseDto>
  ) {
    const data = req.body; // Already typed!
  }
}
```

## Advanced Patterns

### Custom Type Transformations

```typescript
// Define a custom transformation
export function parseJsonBody<T>(): TransformingMiddleware<
  Request,
  Request & { parsedBody: T }
> {
  return (req, _res, next) => {
    try {
      req.parsedBody = JSON.parse(req.body.raw);
      next();
    } catch (error) {
      next(new Error('Invalid JSON'));
    }
  };
}

// Use in a route
router.post('/webhook',
  parseJsonBody<WebhookPayload>(),
  async (req, res) => {
    const payload = req.parsedBody; // WebhookPayload
  }
);
```

### Combining Multiple Validations

```typescript
router.put('/:id',
  authenticate,
  ...defineRoute({
    params: z.object({ id: z.string().uuid() }),
    body: UpdateSchema,
    query: z.object({ 
      validate: z.boolean().default(true),
      dryRun: z.boolean().default(false),
    }),
    handler: async (req, res) => {
      // All types are inferred:
      const id: string = req.params.id;
      const updates: UpdateDto = req.body;
      const validate: boolean = req.query.validate;
      const dryRun: boolean = req.query.dryRun;
    }
  })
);
```

## Benefits

1. **Compile-Time Safety**: Catch type errors during development
2. **Better IntelliSense**: IDE knows exact types of req.body, req.params, req.query
3. **Runtime Validation**: Zod schemas ensure data integrity
4. **Reduced Boilerplate**: No manual type assertions needed
5. **Refactoring Safety**: Changes to schemas automatically update types

## Common Patterns

### Pagination
```typescript
const PaginationSchema = z.object({
  page: z.coerce.number().min(1).default(1),
  limit: z.coerce.number().min(1).max(100).default(20),
});

router.get('/items',
  ...defineRoute({
    query: PaginationSchema,
    handler: async (req, res) => {
      const { page, limit } = req.query; // Both are numbers
    }
  })
);
```

### File Upload
```typescript
router.post('/upload',
  upload.single('file'),
  processFileUpload(),
  async (req, res) => {
    const file = req.file; // ProcessedFile type
    const { mimeType, size, metadata } = file;
  }
);
```

### Error Handling
```typescript
router.post('/risky',
  ...defineRoute({
    body: RiskySchema,
    handler: asyncHandler(async (req, res) => {
      // Errors automatically caught and forwarded
      const result = await riskyOperation(req.body);
      res.json(result);
    })
  })
);
```

## Testing

```typescript
describe('Type-safe routes', () => {
  it('should validate request body', async () => {
    const response = await request(app)
      .post('/api/objects')
      .send({ invalid: 'data' });
      
    expect(response.status).toBe(400);
    expect(response.body.error.code).toBe('VALIDATION_ERROR');
  });
  
  it('should accept valid data', async () => {
    const response = await request(app)
      .post('/api/objects')
      .send({
        apiName: 'test',
        displayName: 'Test Object',
      });
      
    expect(response.status).toBe(201);
    expect(response.body.apiName).toBe('test');
  });
});
```

## Troubleshooting

### Issue: Type inference not working
**Solution**: Ensure you're using `const` assertions:
```typescript
const validation = {
  body: Schema,
} as const; // Important!
```

### Issue: Middleware order matters
**Solution**: Put type-transforming middleware after authentication:
```typescript
router.post('/',
  authenticate, // First
  enrichUserContext(), // Second
  ...defineRoute({ // Last
    body: Schema,
    handler: async (req, res) => { ... }
  })
);
```

### Issue: Custom middleware types lost
**Solution**: Use type assertions in handler:
```typescript
const handler = async (req, res) => {
  const typed = req as Request & { customField: CustomType };
  const value = typed.customField;
};
```