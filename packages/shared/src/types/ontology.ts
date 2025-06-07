import { generateResourceId } from '../utils/resourceId';

/**
 * 노드 타입
 */
export enum NodeType {
  OBJECT = 'object',
  INTERFACE = 'interface',
  ACTION = 'action',
}

/**
 * 노드 상태
 */
export enum NodeStatus {
  ACTIVE = 'active',
  EXPERIMENTAL = 'experimental',
  DEPRECATED = 'deprecated',
}

/**
 * 노드 가시성
 */
export enum NodeVisibility {
  PROMINENT = 'prominent',
  NORMAL = 'normal',
  HIDDEN = 'hidden',
}

/**
 * 링크 카디널리티
 */
export enum Cardinality {
  ONE_TO_ONE = 'ONE_TO_ONE',
  ONE_TO_MANY = 'ONE_TO_MANY',
  MANY_TO_MANY = 'MANY_TO_MANY',
}

/**
 * 속성 기본 타입
 */
export enum BaseType {
  STRING = 'string',
  INTEGER = 'integer',
  BOOLEAN = 'boolean',
  DATE = 'date',
  DECIMAL = 'decimal',
}

/**
 * 노드 메타데이터
 */
export interface NodeMetadata {
  description?: string;
  icon?: string;
  color?: string;
  groups?: string[];
  visibility: NodeVisibility;
  status: NodeStatus;
}

/**
 * 온톨로지 노드
 */
export interface OntologyNode {
  rid: string;
  apiName: string;
  displayName: string;
  type: NodeType;
  position: { x: number; y: number };
  metadata: NodeMetadata;
  version: number;
  createdAt: Date;
  updatedAt: Date;
}

/**
 * 렌더 힌트
 */
export interface RenderHints {
  searchable: boolean;
  sortable: boolean;
  filterable: boolean;
}

/**
 * 속성
 */
export interface Property {
  rid: string;
  apiName: string;
  displayName: string;
  baseType: BaseType;
  objectRid: string;
  titleKey: boolean;
  primaryKey: boolean;
  renderHints: RenderHints;
  conditionalFormatting?: Record<string, unknown>;
  valueFormatting?: string;
  visibility: NodeVisibility;
  status: NodeStatus;
  version: number;
  createdAt: Date;
  updatedAt: Date;
}

/**
 * 링크 타입
 */
export interface LinkType {
  rid: string;
  apiName: string;
  displayName: string;
  sourceObjectRid: string;
  targetObjectRid: string;
  cardinality: Cardinality;
  bidirectional: boolean;
  description?: string;
  visibility: NodeVisibility;
  status: NodeStatus;
  version: number;
  createdAt: Date;
  updatedAt: Date;
}

/**
 * 기본 노드 생성
 */
export function createDefaultNode(params: {
  apiName: string;
  displayName: string;
  type: NodeType;
  position?: { x: number; y: number };
  metadata?: Partial<NodeMetadata>;
}): OntologyNode {
  const now = new Date();
  return {
    rid: generateResourceId(),
    apiName: params.apiName,
    displayName: params.displayName,
    type: params.type,
    position: params.position ?? { x: 0, y: 0 },
    metadata: {
      visibility: NodeVisibility.NORMAL,
      status: NodeStatus.ACTIVE,
      ...params.metadata,
    },
    version: 1,
    createdAt: now,
    updatedAt: now,
  };
}

/**
 * 기본 속성 생성
 */
export function createDefaultProperty(params: {
  apiName: string;
  displayName: string;
  baseType: BaseType;
  objectRid: string;
}): Property {
  const now = new Date();
  return {
    rid: generateResourceId(),
    apiName: params.apiName,
    displayName: params.displayName,
    baseType: params.baseType,
    objectRid: params.objectRid,
    titleKey: false,
    primaryKey: false,
    renderHints: {
      searchable: true,
      sortable: true,
      filterable: true,
    },
    visibility: NodeVisibility.NORMAL,
    status: NodeStatus.ACTIVE,
    version: 1,
    createdAt: now,
    updatedAt: now,
  };
}

/**
 * 메타데이터 검증 결과
 */
interface ValidationResult {
  valid: boolean;
  errors: string[];
}

/**
 * 노드 메타데이터 검증
 */
export function validateNodeMetadata(metadata: NodeMetadata): ValidationResult {
  const errors: string[] = [];

  // 색상 검증
  if (metadata.color && !/^#[0-9A-F]{6}$/i.test(metadata.color)) {
    errors.push('Invalid color format');
  }

  // 필수 필드 검증
  if (!Object.values(NodeVisibility).includes(metadata.visibility)) {
    errors.push('Invalid visibility value');
  }

  if (!Object.values(NodeStatus).includes(metadata.status)) {
    errors.push('Invalid status value');
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
