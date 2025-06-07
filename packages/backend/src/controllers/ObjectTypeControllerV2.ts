import {
  ObjectTypeResponse,
  ObjectTypeListResponse,
  CreateObjectTypeDto,
  UpdateObjectTypeDto,
  ObjectTypeQuery,
} from '@arrakis/contracts';
import { Request, Response } from 'express';

import { ObjectTypeService } from '../services/ObjectTypeService';
import { mapObjectTypeToResponse } from '../utils/mappers';

/**
 * Type-safe ObjectType Controller V2
 * 
 * This version works seamlessly with type-transforming middleware,
 * providing full compile-time type safety without additional type annotations.
 */
export class ObjectTypeControllerV2 {
  constructor(private service: ObjectTypeService) {}

  async create(
    req: Request & { body: CreateObjectTypeDto },
    res: Response<ObjectTypeResponse>
  ): Promise<void> {
    const userId = req.user?.id ?? 'system';
    const objectType = await this.service.create(req.body, userId);
    res.status(201).json(mapObjectTypeToResponse(objectType));
  }

  async list(
    req: Request & { query: ObjectTypeQuery },
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
    req: Request & { params: { id: string } },
    res: Response<ObjectTypeResponse>
  ): Promise<void> {
    const objectType = await this.service.findById(req.params.id);
    res.json(mapObjectTypeToResponse(objectType));
  }

  async update(
    req: Request & { params: { id: string }; body: UpdateObjectTypeDto },
    res: Response<ObjectTypeResponse>
  ): Promise<void> {
    const userId = req.user?.id ?? 'system';
    const objectType = await this.service.update(req.params.id, req.body, userId);
    res.json(mapObjectTypeToResponse(objectType));
  }

  async delete(
    req: Request & { params: { id: string } },
    res: Response<{ message: string }>
  ): Promise<void> {
    const userId = req.user?.id ?? 'system';
    await this.service.delete(req.params.id, userId);
    res.json({ message: 'ObjectType deleted successfully' });
  }

  async activate(
    req: Request & { params: { id: string } },
    res: Response<ObjectTypeResponse>
  ): Promise<void> {
    const userId = req.user?.id ?? 'system';
    const objectType = await this.service.activate(req.params.id, userId);
    res.json(mapObjectTypeToResponse(objectType));
  }

  async deactivate(
    req: Request & { params: { id: string } },
    res: Response<ObjectTypeResponse>
  ): Promise<void> {
    const userId = req.user?.id ?? 'system';
    const objectType = await this.service.deactivate(req.params.id, userId);
    res.json(mapObjectTypeToResponse(objectType));
  }
}