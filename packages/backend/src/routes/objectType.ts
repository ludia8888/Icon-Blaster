import {
  CreateObjectTypeSchema,
  UpdateObjectTypeSchema,
  ObjectTypeQuerySchema,
  IdParamSchema
} from '@arrakis/contracts';
import { Router } from 'express';

import { ObjectTypeController } from '../controllers/ObjectTypeController';
import { getDataSource } from '../database';
import { ObjectType } from '../entities/ObjectType';
import { authenticate } from '../middlewares/auth';
import { authorize } from '../middlewares/authorize';
import { ObjectTypeRepository } from '../repositories/ObjectTypeRepository';
import { ObjectTypeService } from '../services/ObjectTypeService';
import { createValidatedHandler } from '../types/safe-handler';

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
  ...createValidatedHandler(
    { query: ObjectTypeQuerySchema },
    async (req, res) => getController().list(req, res)
  )
);

// Create a new object type
router.post(
  '/',
  authenticate,
  authorize(['admin', 'editor']),
  ...createValidatedHandler(
    { body: CreateObjectTypeSchema },
    async (req, res) => getController().create(req, res)
  )
);

// Get a single object type
router.get(
  '/:id',
  authenticate,
  ...createValidatedHandler(
    { params: IdParamSchema },
    async (req, res) => getController().get(req, res)
  )
);

// Update an object type
router.put(
  '/:id',
  authenticate,
  authorize(['admin', 'editor']),
  ...createValidatedHandler(
    { params: IdParamSchema, body: UpdateObjectTypeSchema },
    async (req, res) => getController().update(req, res)
  )
);

// Delete an object type (soft delete)
router.delete(
  '/:id',
  authenticate,
  authorize(['admin']),
  ...createValidatedHandler(
    { params: IdParamSchema },
    async (req, res) => getController().delete(req, res)
  )
);

// Activate an object type
router.post(
  '/:id/activate',
  authenticate,
  authorize(['admin', 'editor']),
  ...createValidatedHandler(
    { params: IdParamSchema },
    async (req, res) => getController().activate(req, res)
  )
);

// Deactivate an object type
router.post(
  '/:id/deactivate',
  authenticate,
  authorize(['admin', 'editor']),
  ...createValidatedHandler(
    { params: IdParamSchema },
    async (req, res) => getController().deactivate(req, res)
  )
);

export default router;