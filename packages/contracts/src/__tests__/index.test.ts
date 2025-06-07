import * as contractExports from '../index';

describe('Contract exports', () => {
  it('should export common schemas', () => {
    expect(contractExports.ErrorResponseSchema).toBeDefined();
    expect(contractExports.PaginationSchema).toBeDefined();
    expect(contractExports.QueryParamsSchema).toBeDefined();
    expect(contractExports.createErrorResponse).toBeDefined();
    expect(contractExports.createSuccessResponse).toBeDefined();
  });

  it('should export objectType schemas', () => {
    expect(contractExports.CreateObjectTypeSchema).toBeDefined();
    expect(contractExports.UpdateObjectTypeSchema).toBeDefined();
    expect(contractExports.ObjectTypeResponseSchema).toBeDefined();
    expect(contractExports.validateCreateObjectType).toBeDefined();
    expect(contractExports.validateUpdateObjectType).toBeDefined();
  });

  it('should re-export shared enums', () => {
    expect(contractExports.NodeType).toBeDefined();
    expect(contractExports.NodeStatus).toBeDefined();
    expect(contractExports.NodeVisibility).toBeDefined();
    expect(contractExports.Cardinality).toBeDefined();
    expect(contractExports.BaseType).toBeDefined();
  });
});
