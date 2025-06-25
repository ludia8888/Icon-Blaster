import { Request, Response } from 'express';
import { LinkTypeService } from '../services/LinkTypeService';
import { asyncHandler } from '../utils/asyncHandler';
import { 
  CreateLinkTypeSchema, 
  UpdateLinkTypeSchema,
  LinkTypeQuerySchema 
} from '@oms/contracts';
import { logger } from '../utils/logger';

export class LinkTypeController {
  constructor(private linkTypeService: LinkTypeService) {}

  /**
   * LinkType 목록 조회
   */
  listLinkTypes = asyncHandler(async (req: Request, res: Response) => {
    const query = LinkTypeQuerySchema.parse(req.query);
    const result = await this.linkTypeService.findAll(query);
    
    res.json({
      data: result.data,
      meta: {
        page: result.page,
        pageSize: result.pageSize,
        totalCount: result.totalCount,
        totalPages: result.totalPages
      }
    });
  });

  /**
   * LinkType 단건 조회
   */
  getLinkType = asyncHandler(async (req: Request, res: Response) => {
    const { id } = req.params;
    const linkType = await this.linkTypeService.findById(id);
    
    if (!linkType) {
      return res.status(404).json({
        error: 'LinkType not found'
      });
    }
    
    res.json({ data: linkType });
  });

  /**
   * LinkType 생성
   */
  createLinkType = asyncHandler(async (req: Request, res: Response) => {
    const data = CreateLinkTypeSchema.parse(req.body);
    const linkType = await this.linkTypeService.create({
      ...data,
      createdBy: req.user?.id || 'system'
    });
    
    logger.info('LinkType created', {
      linkTypeId: linkType.id,
      name: linkType.name,
      createdBy: linkType.createdBy
    });
    
    res.status(201).json({ data: linkType });
  });

  /**
   * LinkType 수정
   */
  updateLinkType = asyncHandler(async (req: Request, res: Response) => {
    const { id } = req.params;
    const data = UpdateLinkTypeSchema.parse(req.body);
    
    const linkType = await this.linkTypeService.update(id, {
      ...data,
      updatedBy: req.user?.id || 'system'
    });
    
    if (!linkType) {
      return res.status(404).json({
        error: 'LinkType not found'
      });
    }
    
    logger.info('LinkType updated', {
      linkTypeId: linkType.id,
      updatedBy: linkType.updatedBy
    });
    
    res.json({ data: linkType });
  });

  /**
   * LinkType 삭제 (소프트 삭제)
   */
  deleteLinkType = asyncHandler(async (req: Request, res: Response) => {
    const { id } = req.params;
    
    const result = await this.linkTypeService.delete(id, req.user?.id || 'system');
    
    if (!result) {
      return res.status(404).json({
        error: 'LinkType not found'
      });
    }
    
    logger.info('LinkType deleted', {
      linkTypeId: id,
      deletedBy: req.user?.id
    });
    
    res.status(204).send();
  });

  /**
   * LinkType 활성화
   */
  activateLinkType = asyncHandler(async (req: Request, res: Response) => {
    const { id } = req.params;
    
    const linkType = await this.linkTypeService.activate(id, req.user?.id || 'system');
    
    if (!linkType) {
      return res.status(404).json({
        error: 'LinkType not found'
      });
    }
    
    res.json({ data: linkType });
  });

  /**
   * LinkType 비활성화
   */
  deactivateLinkType = asyncHandler(async (req: Request, res: Response) => {
    const { id } = req.params;
    
    const linkType = await this.linkTypeService.deactivate(id, req.user?.id || 'system');
    
    if (!linkType) {
      return res.status(404).json({
        error: 'LinkType not found'
      });
    }
    
    res.json({ data: linkType });
  });
}