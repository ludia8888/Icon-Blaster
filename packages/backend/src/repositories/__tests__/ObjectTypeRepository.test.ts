import { NodeStatus } from '@arrakis/shared';
import { Repository } from 'typeorm';

import { ObjectType } from '../../entities/ObjectType';
import { ObjectTypeRepository } from '../ObjectTypeRepository';

describe('ObjectTypeRepository', () => {
  let repository: ObjectTypeRepository;
  let mockTypeOrmRepo: jest.Mocked<Repository<ObjectType>>;

  beforeEach(() => {
    mockTypeOrmRepo = {
      findOne: jest.fn(),
      find: jest.fn(),
      findAndCount: jest.fn(),
      create: jest.fn(),
      save: jest.fn(),
      delete: jest.fn(),
      count: jest.fn(),
      createQueryBuilder: jest.fn(),
    } as unknown as jest.Mocked<Repository<ObjectType>>;

    repository = new ObjectTypeRepository(mockTypeOrmRepo);
  });

  describe('findByApiName', () => {
    it('should find object type by API name', async () => {
      const mockObjectType = { rid: '123', apiName: 'TestObject' } as ObjectType;
      mockTypeOrmRepo.findOne.mockResolvedValue(mockObjectType);

      const result = await repository.findByApiName('TestObject');

      expect(mockTypeOrmRepo.findOne).toHaveBeenCalledWith({
        where: { apiName: 'TestObject' },
      });
      expect(result).toBe(mockObjectType);
    });

    it('should return null if not found', async () => {
      mockTypeOrmRepo.findOne.mockResolvedValue(null);

      const result = await repository.findByApiName('NonExistent');

      expect(result).toBeNull();
    });
  });

  describe('findPaginated', () => {
    it('should return paginated results with filters', async () => {
      const mockData = [
        { rid: '1', apiName: 'Object1' },
        { rid: '2', apiName: 'Object2' },
      ] as ObjectType[];

      mockTypeOrmRepo.findAndCount.mockResolvedValue([mockData, 10]);

      const result = await repository.findPaginated(
        { search: 'test', status: NodeStatus.ACTIVE },
        { page: 1, limit: 20, sortBy: 'apiName', sortOrder: 'ASC' }
      );

      expect(mockTypeOrmRepo.findAndCount).toHaveBeenCalledWith({
        where: {
          displayName: expect.objectContaining({ _value: '%test%' }),
          status: NodeStatus.ACTIVE,
        },
        skip: 0,
        take: 20,
        order: { apiName: 'ASC' },
      });

      expect(result).toEqual({
        data: mockData,
        total: 10,
        page: 1,
        limit: 20,
        totalPages: 1,
      });
    });

    it('should calculate correct pagination', async () => {
      mockTypeOrmRepo.findAndCount.mockResolvedValue([[], 100]);

      const result = await repository.findPaginated({}, { page: 3, limit: 20 });

      expect(mockTypeOrmRepo.findAndCount).toHaveBeenCalledWith({
        where: {},
        skip: 40,
        take: 20,
        order: { apiName: 'ASC' },
      });

      expect(result.totalPages).toBe(5);
    });
  });

  describe('existsByApiName', () => {
    it('should return true if exists', async () => {
      mockTypeOrmRepo.count.mockResolvedValue(1);

      const result = await repository.existsByApiName('TestObject');

      expect(mockTypeOrmRepo.count).toHaveBeenCalledWith({
        where: { apiName: 'TestObject' },
      });
      expect(result).toBe(true);
    });

    it('should return false if not exists', async () => {
      mockTypeOrmRepo.count.mockResolvedValue(0);

      const result = await repository.existsByApiName('NonExistent');

      expect(result).toBe(false);
    });
  });

  describe('updateStatus', () => {
    it('should update status', async () => {
      const mockObjectType = { rid: '123', status: NodeStatus.ACTIVE } as ObjectType;
      mockTypeOrmRepo.findOne.mockResolvedValue(mockObjectType);
      mockTypeOrmRepo.save.mockResolvedValue({
        ...mockObjectType,
        status: NodeStatus.DEPRECATED,
      } as ObjectType);

      const result = await repository.updateStatus('123', NodeStatus.DEPRECATED);

      expect(result?.status).toBe(NodeStatus.DEPRECATED);
    });
  });

  describe('findByGroups', () => {
    it('should find by groups using query builder', async () => {
      const mockData = [{ rid: '1' }] as ObjectType[];
      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue(mockData),
      };

      mockTypeOrmRepo.createQueryBuilder.mockReturnValue(mockQueryBuilder as any);

      const result = await repository.findByGroups(['group1', 'group2']);

      expect(mockTypeOrmRepo.createQueryBuilder).toHaveBeenCalledWith('objectType');
      expect(mockQueryBuilder.where).toHaveBeenCalledWith('objectType.groups && :groups', {
        groups: ['group1', 'group2'],
      });
      expect(result).toBe(mockData);
    });
  });
});
