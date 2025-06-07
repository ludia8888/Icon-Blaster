import {
  CreateObjectTypeSchema,
  UpdateObjectTypeSchema,
  ObjectTypeQuerySchema,
  IdParamSchema,
} from '@arrakis/contracts';
import { Router } from 'express';

import { ObjectTypeController } from '../controllers/ObjectTypeController';
import { getDataSource } from '../database';
import { ObjectType } from '../entities/ObjectType';
import { authenticate } from '../middlewares/auth';
import { authorize } from '../middlewares/authorize';
import { defineRoute } from '../middlewares/type-transforming-middleware';
import { ObjectTypeRepository } from '../repositories/ObjectTypeRepository';
import { ObjectTypeService } from '../services/ObjectTypeService';
import { asyncHandler } from '../utils/asyncHandler';

const router = Router();

// Lazy initialization to ensure database is ready
let controller: ObjectTypeController;

function getController(): ObjectTypeController {
  if (!controller) {
    const dataSource = getDataSource();
    const repository = new ObjectTypeRepository(dataSource.getRepository(ObjectType));
    const service = new ObjectTypeService(repository);
    controller = new ObjectTypeController(service);
  }
  return controller;
}

// List all object types
router.get(
  '/',
  authenticate,
  ...defineRoute({
    query: ObjectTypeQuerySchema,
    handler: asyncHandler(async (req, res) => {
      await getController().list(req, res);
    }),
  })
);

// Create a new object type
router.post(
  '/',
  authenticate,
  authorize(['admin', 'editor']),
  ...defineRoute({
    body: CreateObjectTypeSchema,
    handler: asyncHandler(async (req, res) => {
      await getController().create(req, res);
    }),
  })
);

// Get a single object type
router.get(
  '/:id',
  authenticate,
  ...defineRoute({
    params: IdParamSchema,
    handler: asyncHandler(async (req, res) => {
      await getController().get(req, res);
    }),
  })
);

// Update an object type
router.put(
  '/:id',
  authenticate,
  authorize(['admin', 'editor']),
  ...defineRoute({
    params: IdParamSchema,
    body: UpdateObjectTypeSchema,
    handler: asyncHandler(async (req, res) => {
      await getController().update(req, res);
    }),
  })
);

// Delete an object type (soft delete)
router.delete(
  '/:id',
  authenticate,
  authorize(['admin']),
  ...defineRoute({
    params: IdParamSchema,
    handler: asyncHandler(async (req, res) => {
      await getController().delete(req, res);
    }),
  })
);

// Activate an object type
router.post(
  '/:id/activate',
  authenticate,
  authorize(['admin', 'editor']),
  ...defineRoute({
    params: IdParamSchema,
    handler: asyncHandler(async (req, res) => {
      await getController().activate(req, res);
    }),
  })
);

// Deactivate an object type
router.post(
  '/:id/deactivate',
  authenticate,
  authorize(['admin', 'editor']),
  ...defineRoute({
    params: IdParamSchema,
    handler: asyncHandler(async (req, res) => {
      await getController().deactivate(req, res);
    }),
  })
);

export default router;
