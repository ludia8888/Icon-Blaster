/**
 * 정적 타입 검증 테스트
 *
 * 이 파일은 런타임 테스트가 아닌 컴파일 타임 타입 검증을 수행합니다.
 * TypeScript 컴파일러가 타입을 올바르게 추론하는지 확인합니다.
 */

import { Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import {
  validateBody,
  validateQuery,
  validateParams,
  middlewareChain,
  defineRoute,
} from '../type-transforming-middleware';

// 테스트용 스키마 정의
const CreateUserSchema = z.object({
  name: z.string(),
  email: z.string().email(),
  age: z.number(),
});

const IdParamSchema = z.object({
  id: z.string().uuid(),
});

const QuerySchema = z.object({
  page: z.number(),
  limit: z.number(),
});

/**
 * 타입 레벨 테스트 1: validateBody가 타입을 올바르게 변환하는지
 */
{
  const middleware = validateBody(CreateUserSchema);

  // 미들웨어 시그니처 검증
  const _test: (req: Request, res: Response, next: NextFunction) => void = middleware;

  // 미들웨어 실행 후 타입 변환 시뮬레이션
  const handler = (req: Request & { body: z.infer<typeof CreateUserSchema> }) => {
    // 이 코드가 컴파일되면 타입 추론이 성공한 것
    const name: string = req.body.name;
    const email: string = req.body.email;
    const age: number = req.body.age;

    // @ts-expect-error - body에 없는 필드 접근 시 에러
    const invalid = req.body.invalid;
  };
}

/**
 * 타입 레벨 테스트 2: 미들웨어 체인이 타입을 누적하는지
 */
{
  const chain = middlewareChain()
    .use(validateBody(CreateUserSchema))
    .use(validateParams(IdParamSchema))
    .use(validateQuery(QuerySchema));

  const route = chain.build();

  route.handler(async (req, res) => {
    // 모든 타입이 올바르게 추론되어야 함
    const name: string = req.body.name;
    const email: string = req.body.email;
    const age: number = req.body.age;

    const id: string = req.params.id;

    const page: number = req.query.page;
    const limit: number = req.query.limit;

    // @ts-expect-error - 잘못된 타입 할당
    const wrongType: boolean = req.body.name;

    res.json({ success: true });
  });
}

/**
 * 타입 레벨 테스트 3: defineRoute가 완전한 타입 안전성을 제공하는지
 */
{
  const routeHandlers = defineRoute({
    body: CreateUserSchema,
    params: IdParamSchema,
    query: QuerySchema,
    handler: async (req, res) => {
      // 모든 타입이 자동으로 추론됨
      const user = {
        id: req.params.id,
        name: req.body.name,
        email: req.body.email,
        age: req.body.age,
        page: req.query.page,
        limit: req.query.limit,
      };

      // Response 타입도 추론 가능
      res.json(user);
    },
  });
}

/**
 * 타입 레벨 테스트 4: 부분적인 검증도 지원하는지
 */
{
  // body만 검증
  const bodyOnly = defineRoute({
    body: CreateUserSchema,
    handler: (req, res) => {
      const name: string = req.body.name;

      // params와 query는 기본 타입
      const id: string = req.params.id;
      const page: string = req.query.page as string;
    },
  });

  // params만 검증
  const paramsOnly = defineRoute({
    params: IdParamSchema,
    handler: (req, res) => {
      const id: string = req.params.id;

      // body는 unknown 타입
      const body: unknown = req.body;
    },
  });
}

/**
 * 타입 레벨 테스트 5: 제네릭 Response 타입도 지원하는지
 */
{
  interface UserResponse {
    id: string;
    name: string;
    email: string;
  }

  const route = defineRoute({
    body: CreateUserSchema,
    handler: async (req, res: Response<UserResponse>) => {
      // Response 타입이 제한됨
      res.json({
        id: '123',
        name: req.body.name,
        email: req.body.email,
      });

      // @ts-expect-error - Response 타입에 맞지 않는 데이터
      res.json({ invalid: true });
    },
  });
}

/**
 * 이 파일이 TypeScript 컴파일 에러 없이 통과하면
 * 타입 시스템이 올바르게 작동하는 것입니다.
 *
 * @ts-expect-error 주석이 있는 부분은 의도적으로
 * 에러가 발생해야 하는 부분입니다.
 */
export {};
