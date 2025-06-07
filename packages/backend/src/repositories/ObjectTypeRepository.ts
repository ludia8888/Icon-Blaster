import { NodeStatus, NodeVisibility } from '@arrakis/shared';
import { Repository, FindManyOptions, Like } from 'typeorm';

import { ObjectType } from '../entities/ObjectType';

import { BaseRepository } from './BaseRepository';

export interface ObjectTypeFilters {
  search?: string;
  status?: NodeStatus;
  visibility?: NodeVisibility;
  groups?: string[];
}

export interface PaginationOptions {
  page: number;
  limit: number;
  sortBy?: 'apiName' | 'displayName' | 'createdAt' | 'updatedAt';
  sortOrder?: 'ASC' | 'DESC';
}

export interface PaginatedResult<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

export class ObjectTypeRepository extends BaseRepository<ObjectType> {
  constructor(repository: Repository<ObjectType>) {
    super(repository);
  }

  async findByApiName(apiName: string): Promise<ObjectType | null> {
    return this.repository.findOne({
      where: { apiName },
    });
  }

  async findPaginated(
    filters: ObjectTypeFilters,
    pagination: PaginationOptions
  ): Promise<PaginatedResult<ObjectType>> {
    const { page, limit, sortBy = 'apiName', sortOrder = 'ASC' } = pagination;
    const skip = (page - 1) * limit;

    const where: FindManyOptions<ObjectType>['where'] = {};

    if (filters.search) {
      where.displayName = Like(`%${filters.search}%`);
    }

    if (filters.status != null) {
      where.status = filters.status;
    }

    if (filters.visibility != null) {
      where.visibility = filters.visibility;
    }

    if (filters.groups && filters.groups.length > 0) {
      // TypeORM doesn't support array contains directly, need raw query
      // For now, we'll implement this in a service layer with custom query
    }

    const [data, total] = await this.repository.findAndCount({
      where,
      skip,
      take: limit,
      order: {
        [sortBy]: sortOrder,
      },
    });

    return {
      data,
      total,
      page,
      limit,
      totalPages: Math.ceil(total / limit),
    };
  }

  async existsByApiName(apiName: string): Promise<boolean> {
    return this.exists({ apiName });
  }

  async updateStatus(id: string, status: NodeStatus): Promise<ObjectType | null> {
    return this.update(id, { status });
  }

  async updateVisibility(id: string, visibility: NodeVisibility): Promise<ObjectType | null> {
    return this.update(id, { visibility });
  }

  async findByGroups(groups: string[]): Promise<ObjectType[]> {
    // Custom query for array contains
    const query = this.repository
      .createQueryBuilder('objectType')
      .where('objectType.groups && :groups', { groups });

    return query.getMany();
  }
}
