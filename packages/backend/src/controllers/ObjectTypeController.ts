import { 
  ObjectTypeResponse,
  ObjectTypeListResponse,
  CreateObjectTypeSchema,
  UpdateObjectTypeSchema,
  ObjectTypeQuerySchema,
  IdParamSchema
} from '@arrakis/contracts';
import { Response } from 'express';

import { ObjectTypeService } from '../services/ObjectTypeService';
import { ValidatedRequest } from '../types/safe-handler';
import { mapObjectTypeToResponse } from '../utils/mappers';

// 📋 Validation Contracts (Specification-Driven Coding)
type CreateValidation = { body: typeof CreateObjectTypeSchema };
type ListValidation = { query: typeof ObjectTypeQuerySchema };
type GetValidation = { params: typeof IdParamSchema };
type UpdateValidation = { params: typeof IdParamSchema; body: typeof UpdateObjectTypeSchema };
type DeleteValidation = { params: typeof IdParamSchema };
type ActivateValidation = { params: typeof IdParamSchema };
type DeactivateValidation = { params: typeof IdParamSchema };

export class ObjectTypeController {
  constructor(private service: ObjectTypeService) {}

  async create(
    req: ValidatedRequest<CreateValidation>,
    res: Response<ObjectTypeResponse>
  ): Promise<void> {
    const userId = req.user?.id ?? 'system';
    const objectType = await this.service.create(req.body, userId);
    res.status(201).json(mapObjectTypeToResponse(objectType));
  }

  async list(
    req: ValidatedRequest<ListValidation>,
    res: Response<ObjectTypeListResponse>
  ): Promise<void> {
    const result = await this.service.list(req.query);
    
    const response: ObjectTypeListResponse = {
      data: result.data.map(mapObjectTypeToResponse),
      pagination: {
        total: result.total,
        page: result.page,
        limit: result.limit,
        totalPages: result.totalPages,
      },
    };

    res.json(response);
  }

  async get(
    req: ValidatedRequest<GetValidation>,
    res: Response<ObjectTypeResponse>
  ): Promise<void> {
    const objectType = await this.service.findById(req.params.id);
    res.json(mapObjectTypeToResponse(objectType));
  }

  async update(
    req: ValidatedRequest<UpdateValidation>,
    res: Response<ObjectTypeResponse>
  ): Promise<void> {
    const userId = req.user?.id ?? 'system';
    const objectType = await this.service.update(req.params.id, req.body, userId);
    res.json(mapObjectTypeToResponse(objectType));
  }

  async delete(
    req: ValidatedRequest<DeleteValidation>,
    res: Response<{ message: string }>
  ): Promise<void> {
    await this.service.delete(req.params.id);
    res.json({ message: 'ObjectType deleted successfully' });
  }

  async activate(
    req: ValidatedRequest<ActivateValidation>,
    res: Response<ObjectTypeResponse>
  ): Promise<void> {
    const userId = req.user?.id ?? 'system';
    const objectType = await this.service.activate(req.params.id, userId);
    res.json(mapObjectTypeToResponse(objectType));
  }

  async deactivate(
    req: ValidatedRequest<DeactivateValidation>,
    res: Response<ObjectTypeResponse>
  ): Promise<void> {
    const userId = req.user?.id ?? 'system';
    const objectType = await this.service.deactivate(req.params.id, userId);
    res.json(mapObjectTypeToResponse(objectType));
  }
}