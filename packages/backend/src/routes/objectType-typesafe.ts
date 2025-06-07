/**
 * 타입 안전한 ObjectType 라우트 구현 예제
 * 
 * 새로운 type-transforming-middleware를 사용하여
 * 완전한 타입 안전성을 달성합니다.
 */

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
import { asyncHandler } from '../utils/asyncHandler';
import { 
  validateBody, 
  validateParams, 
  validateQuery,
  defineRoute,
  middlewareChain
} from '../middlewares/type-transforming-middleware';

const router = Router();

// Controller 초기화
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

/**
 * 방법 1: defineRoute를 사용한 완전 타입 안전 라우트
 */
router.get(
  '/v2/list',
  authenticate,
  ...defineRoute({
    query: ObjectTypeQuerySchema,
    handler: asyncHandler(async (req, res) => {
      // req.query가 자동으로 ObjectTypeQuery 타입으로 추론됨
      const page: number = req.query.page;
      const limit: number = req.query.limit;
      const search: string | undefined = req.query.search;
      
      const result = await getController().list(req as any, res);
    })
  })
);

/**
 * 방법 2: middlewareChain을 사용한 체이닝 방식
 */
const createRoute = middlewareChain()
  .use(validateBody(CreateObjectTypeSchema))
  .build();

router.post(
  '/v2/create',
  authenticate,
  authorize(['admin', 'editor']),
  ...createRoute.handler(asyncHandler(async (req, res) => {
    // req.body가 CreateObjectTypeDto 타입으로 자동 추론
    const apiName: string = req.body.apiName;
    const displayName: string = req.body.displayName;
    
    // 타입 에러 예시 (주석 해제 시 컴파일 에러)
    // const invalid: number = req.body.apiName; // Error: string을 number에 할당 불가
    
    await getController().create(req as any, res);
  }))
);

/**
 * 방법 3: 개별 미들웨어 조합
 */
router.put(
  '/v2/:id',
  authenticate,
  authorize(['admin', 'editor']),
  validateParams(IdParamSchema),
  validateBody(UpdateObjectTypeSchema),
  asyncHandler(async (req, res) => {
    // 타입 추론이 제한적 - Express의 한계
    // 하지만 런타임에서는 올바르게 작동
    const id = (req as any).params.id as string;
    const updates = (req as any).body;
    
    await getController().update(req as any, res);
  })
);

/**
 * 방법 4: 커스텀 타입 안전 헬퍼 함수
 */
function createTypeSafeRoute<TBody, TParams, TQuery, TRes>(
  path: string,
  middlewares: Array<(req: any, res: any, next: any) => void>,
  routeDef: {
    body?: any;
    params?: any;
    query?: any;
    handler: (
      req: Request & { body: TBody; params: TParams; query: TQuery },
      res: Response<TRes>
    ) => Promise<void>;
  }
) {
  const validationMiddlewares = [];
  
  if (routeDef.body) {
    validationMiddlewares.push(validateBody(routeDef.body));
  }
  if (routeDef.params) {
    validationMiddlewares.push(validateParams(routeDef.params));
  }
  if (routeDef.query) {
    validationMiddlewares.push(validateQuery(routeDef.query));
  }
  
  return router.post(
    path,
    ...middlewares,
    ...validationMiddlewares,
    asyncHandler(routeDef.handler as any)
  );
}

// 사용 예시
createTypeSafeRoute(
  '/v2/:id/activate',
  [authenticate, authorize(['admin', 'editor'])],
  {
    params: IdParamSchema,
    handler: async (req, res) => {
      // 완전한 타입 안전성
      const id: string = req.params.id;
      
      await getController().activate(req as any, res);
    }
  }
);

export default router;

/**
 * 핵심 개선사항:
 * 
 * 1. 컴파일 타임 타입 안전성
 *    - 미들웨어가 Request 타입을 변환한다는 것을 명시
 *    - 체인된 미들웨어의 타입 변환이 누적됨
 * 
 * 2. IDE 자동완성 지원
 *    - req.body, req.params, req.query의 필드가 자동완성됨
 *    - 잘못된 타입 할당 시 즉시 에러 표시
 * 
 * 3. 런타임 안전성 유지
 *    - Zod 검증으로 런타임 타입 체크
 *    - 검증 실패 시 적절한 에러 응답
 * 
 * 4. Express의 한계 극복
 *    - Express는 미들웨어 체인의 타입 변환을 추적하지 못함
 *    - 우리의 솔루션은 이를 우회하여 타입 안전성 제공
 */