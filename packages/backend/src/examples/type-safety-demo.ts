/**
 * 타입 안전성 데모
 * 
 * 실제 사용 시나리오에서 타입 안전성이 어떻게 작동하는지 보여줍니다.
 */

import { z } from 'zod';
import { Request, Response } from 'express';
import { 
  validateBody,
  validateParams,
  validateQuery,
  middlewareChain,
  defineRoute 
} from '../middlewares/type-transforming-middleware';

// 1. 스키마 정의
const CreateProductSchema = z.object({
  name: z.string().min(1).max(100),
  price: z.number().positive(),
  category: z.enum(['electronics', 'clothing', 'food']),
  tags: z.array(z.string()).optional()
});

const ProductIdSchema = z.object({
  productId: z.string().uuid()
});

const PaginationSchema = z.object({
  page: z.number().int().positive().default(1),
  limit: z.number().int().positive().max(100).default(20),
  sortBy: z.enum(['name', 'price', 'createdAt']).optional()
});

// 2. 타입 추출
type CreateProductDto = z.infer<typeof CreateProductSchema>;
type ProductId = z.infer<typeof ProductIdSchema>;
type PaginationQuery = z.infer<typeof PaginationSchema>;

// 3. 방법 1: defineRoute 사용 (가장 간단하고 타입 안전)
export const createProductRoute = defineRoute({
  body: CreateProductSchema,
  handler: async (req, res) => {
    // ✅ 모든 타입이 자동으로 추론됨
    console.log(`Creating product: ${req.body.name}`);
    console.log(`Price: $${req.body.price}`);
    console.log(`Category: ${req.body.category}`);
    
    // ✅ Optional 필드도 올바르게 처리
    if (req.body.tags) {
      console.log(`Tags: ${req.body.tags.join(', ')}`);
    }
    
    // ✅ 타입 에러 예시 (주석 해제 시 컴파일 에러)
    // const wrongType: boolean = req.body.price; // Error: number를 boolean에 할당 불가
    // const nonExistent = req.body.nonExistentField; // Error: 존재하지 않는 필드
    
    res.json({
      id: '123e4567-e89b-12d3-a456-426614174000',
      ...req.body,
      createdAt: new Date()
    });
  }
});

// 4. 방법 2: middlewareChain 사용 (더 유연한 체이닝)
export const updateProductRoute = middlewareChain()
  .use(validateParams(ProductIdSchema))
  .use(validateBody(CreateProductSchema.partial())) // Partial update
  .build()
  .handler(async (req, res) => {
    // ✅ params와 body 모두 타입 안전
    const productId: string = req.params.productId;
    
    // ✅ Partial 타입도 올바르게 추론
    const updates: Partial<CreateProductDto> = req.body;
    
    if (updates.name !== undefined) {
      console.log(`Updating name to: ${updates.name}`);
    }
    
    if (updates.price !== undefined) {
      console.log(`Updating price to: $${updates.price}`);
    }
    
    res.json({
      id: productId,
      ...updates,
      updatedAt: new Date()
    });
  });

// 5. 방법 3: 복잡한 비즈니스 로직을 위한 타입 안전 서비스
class ProductService {
  // 타입 안전한 메서드 시그니처
  async createProduct(data: CreateProductDto): Promise<Product> {
    // 비즈니스 로직
    if (data.price > 10000) {
      throw new Error('Price too high for this category');
    }
    
    // DB 저장 시뮬레이션
    const product: Product = {
      id: generateId(),
      ...data,
      tags: data.tags || [],
      createdAt: new Date(),
      updatedAt: new Date()
    };
    
    return product;
  }
  
  async getProducts(pagination: PaginationQuery): Promise<PaginatedResponse<Product>> {
    // 타입 안전한 페이지네이션 처리
    const { page, limit, sortBy } = pagination;
    
    // DB 쿼리 시뮬레이션
    const products: Product[] = [];
    const total = 100;
    
    return {
      data: products,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit)
      }
    };
  }
}

// 6. 타입 정의
interface Product extends CreateProductDto {
  id: string;
  tags: string[]; // Optional에서 Required로
  createdAt: Date;
  updatedAt: Date;
}

interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
  };
}

// 7. 실제 사용 예제
export function setupProductRoutes() {
  const service = new ProductService();
  
  // 모든 라우트가 타입 안전
  return {
    // POST /products
    create: defineRoute({
      body: CreateProductSchema,
      handler: async (req, res) => {
        try {
          const product = await service.createProduct(req.body);
          res.status(201).json(product);
        } catch (error) {
          res.status(400).json({ 
            error: error instanceof Error ? error.message : 'Unknown error' 
          });
        }
      }
    }),
    
    // GET /products
    list: defineRoute({
      query: PaginationSchema,
      handler: async (req, res) => {
        const result = await service.getProducts(req.query);
        res.json(result);
      }
    }),
    
    // PUT /products/:productId
    update: middlewareChain()
      .use(validateParams(ProductIdSchema))
      .use(validateBody(CreateProductSchema.partial()))
      .build()
      .handler(async (req, res) => {
        // 완전한 타입 안전성과 함께 비즈니스 로직 수행
        const { productId } = req.params;
        const updates = req.body;
        
        console.log(`Updating product ${productId}`, updates);
        res.json({ id: productId, ...updates });
      })
  };
}

// 유틸리티
function generateId(): string {
  return '123e4567-e89b-12d3-a456-426614174000';
}

// 8. 타입 안전성의 실질적 이점 데모
function demonstrateTypeSafety() {
  // ✅ 자동완성이 작동함
  const handler = defineRoute({
    body: CreateProductSchema,
    handler: async (req, res) => {
      // req.body. 입력 시 IDE가 다음을 제안:
      // - name: string
      // - price: number
      // - category: "electronics" | "clothing" | "food"
      // - tags?: string[]
      
      // ✅ 잘못된 사용은 즉시 에러
      // req.body.nmae; // Error: 오타 감지
      // req.body.price.toLowerCase(); // Error: number에 toLowerCase 없음
      // req.body.category = 'invalid'; // Error: 유효하지 않은 enum 값
    }
  });
  
  return handler;
}

/**
 * 결론:
 * 
 * 1. 컴파일 타임 안전성
 *    - 모든 타입 오류가 코드 작성 시점에 발견됨
 *    - 런타임 에러 대폭 감소
 * 
 * 2. 개발자 경험 향상
 *    - IDE 자동완성 완벽 지원
 *    - 리팩토링 시 모든 영향받는 코드 자동 감지
 * 
 * 3. 유지보수성
 *    - 스키마 변경 시 타입 시스템이 모든 수정 필요 지점 표시
 *    - 새 개발자도 타입을 보고 API 이해 가능
 * 
 * 4. 실수 방지
 *    - 오타, 잘못된 타입 사용 등 즉시 감지
 *    - Optional/Required 필드 명확히 구분
 */

export {};