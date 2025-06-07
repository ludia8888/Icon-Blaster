import {
  CreateObjectTypeDto,
  UpdateObjectTypeDto,
  ObjectTypeQuery,
  ErrorCode,
} from '@arrakis/contracts';
import { NodeStatus } from '@arrakis/shared';

import { ObjectType } from '../entities/ObjectType';
import { AppError } from '../middlewares/errorHandler';
import { ObjectTypeRepository, PaginatedResult } from '../repositories/ObjectTypeRepository';

export class ObjectTypeService {
  constructor(private repository: ObjectTypeRepository) {}

  async create(data: CreateObjectTypeDto, createdBy: string): Promise<ObjectType> {
    // Check if apiName already exists
    const exists = await this.repository.existsByApiName(data.apiName);
    if (exists) {
      throw new AppError(
        `ObjectType with apiName '${data.apiName}' already exists`,
        409,
        ErrorCode.CONFLICT
      );
    }

    const objectType = await this.repository.create({
      ...data,
      pluralDisplayName: data.pluralDisplayName || `${data.displayName}s`,
      createdBy,
      updatedBy: createdBy,
    });

    return objectType;
  }

  async findById(id: string): Promise<ObjectType> {
    const objectType = await this.repository.findById(id);
    if (!objectType) {
      throw new AppError('ObjectType not found', 404, ErrorCode.NOT_FOUND);
    }
    return objectType;
  }

  async findByApiName(apiName: string): Promise<ObjectType> {
    const objectType = await this.repository.findByApiName(apiName);
    if (!objectType) {
      throw new AppError('ObjectType not found', 404, ErrorCode.NOT_FOUND);
    }
    return objectType;
  }

  async list(query: ObjectTypeQuery): Promise<PaginatedResult<ObjectType>> {
    const { page, limit, search, status, visibility, groups, sortBy, sortOrder } = query;

    const filters = {
      search,
      status,
      visibility,
      groups: groups ? groups.split(',') : undefined,
    };

    const pagination = {
      page,
      limit,
      sortBy,
      sortOrder: sortOrder?.toUpperCase() as 'ASC' | 'DESC',
    };

    return this.repository.findPaginated(filters, pagination);
  }

  async update(id: string, data: UpdateObjectTypeDto, updatedBy: string): Promise<ObjectType> {
    await this.findById(id);

    const updated = await this.repository.update(id, {
      ...data,
      updatedBy,
    });

    if (!updated) {
      throw new AppError('Failed to update ObjectType', 500, ErrorCode.INTERNAL_ERROR);
    }

    return updated;
  }

  async delete(id: string): Promise<void> {
    await this.findById(id);

    // Soft delete by updating status to DEPRECATED
    await this.repository.updateStatus(id, NodeStatus.DEPRECATED);
  }

  async activate(id: string, updatedBy: string): Promise<ObjectType> {
    const objectType = await this.findById(id);

    if (objectType.status === NodeStatus.ACTIVE) {
      throw new AppError('ObjectType is already active', 400, ErrorCode.BAD_REQUEST);
    }

    const updated = await this.repository.update(id, {
      status: NodeStatus.ACTIVE,
      updatedBy,
    });

    if (!updated) {
      throw new AppError('Failed to activate ObjectType', 500, ErrorCode.INTERNAL_ERROR);
    }

    return updated;
  }

  async deactivate(id: string, updatedBy: string): Promise<ObjectType> {
    const objectType = await this.findById(id);

    if (objectType.status === NodeStatus.DEPRECATED) {
      throw new AppError('ObjectType is already deprecated', 400, ErrorCode.BAD_REQUEST);
    }

    const updated = await this.repository.update(id, {
      status: NodeStatus.DEPRECATED,
      updatedBy,
    });

    if (!updated) {
      throw new AppError('Failed to deactivate ObjectType', 500, ErrorCode.INTERNAL_ERROR);
    }

    return updated;
  }
}
