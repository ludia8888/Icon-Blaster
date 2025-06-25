/**
 * Auto-generated TypeScript types for oms-event-sdk
 * Generated at: 2025-06-25T11:15:14.777957
 * DO NOT EDIT - This file is auto-generated
 */

// Common types
export interface PublishResult {
  success: boolean;
  messageId?: string;
  error?: string;
}

export interface Subscription {
  unsubscribe(): Promise<void>;
}

export interface EventPublisher {
  publish(channel: string, payload: any): Promise<PublishResult>;
}

export interface EventSubscriber {
  subscribe(channel: string, handler: (payload: any) => void | Promise<void>): Promise<Subscription>;
}

// Generated Types
export interface CloudEvent {
  specversion: string;
  type: string;
  source: string;
  id: string;
  time?: Date;
  datacontenttype?: string;
  subject?: string;
  data?: object;
}
export interface OMSContext {
  branch?: string;
  commit?: string;
  author?: string;
  tenant?: string;
  correlationId?: string;
  causationId?: string;
}
export type EntityType = string;

// Message Interfaces
export interface SchemacreatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: Record<string, any>;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface SchemacreatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface SchemaupdatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: Record<string, any>;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface SchemaupdatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface SchemadeletedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: Record<string, any>;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface SchemadeletedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface SchemavalidatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: Record<string, any>;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface SchemavalidatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface ObjecttypecreatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface ObjecttypecreatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface ObjecttypeupdatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface ObjecttypeupdatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface ObjecttypedeletedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface ObjecttypedeletedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface PropertycreatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface PropertycreatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface PropertyupdatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface PropertyupdatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface PropertydeletedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface PropertydeletedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface LinktypecreatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: Record<string, any>;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface LinktypecreatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface LinktypeupdatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: Record<string, any>;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface LinktypeupdatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface LinktypedeletedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: Record<string, any>;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface LinktypedeletedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface BranchcreatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface BranchcreatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface BranchupdatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface BranchupdatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface BranchdeletedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface BranchdeletedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface BranchmergedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface BranchmergedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface ProposalcreatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: Record<string, any>;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface ProposalcreatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface ProposalupdatedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: Record<string, any>;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface ProposalupdatedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface ProposalapprovedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: Record<string, any>;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface ProposalapprovedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface ProposalrejectedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: Record<string, any>;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface ProposalrejectedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface ProposalmergedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: Record<string, any>;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface ProposalmergedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface ActionstartedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface ActionstartedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface ActioncompletedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface ActioncompletedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface ActionfailedPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface ActionfailedEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface ActioncancelledPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface ActioncancelledEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface SystemhealthcheckPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface SystemhealthcheckEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface SystemerrorPayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface SystemerrorEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
export interface SystemmaintenancePayload {
  /** CloudEvents specification version */
  specversion: string;
  /** Event type identifier */
  type: string;
  /** Event source identifier */
  source: string;
  /** Unique event identifier */
  id: string;
  /** Event timestamp */
  time?: Date;
  datacontenttype?: string;
  /** Subject of the event */
  subject?: string;
  data: object;
  /** Correlation ID for event tracking */
  ce_correlationid?: string;
  /** Causation ID for event chain tracking */
  ce_causationid?: string;
  /** Git branch context */
  ce_branch?: string;
  /** Git commit ID */
  ce_commit?: string;
  /** Event author */
  ce_author?: string;
  /** Tenant identifier */
  ce_tenant?: string;
}
export interface SystemmaintenanceEventBridgePayload {
  /** EventBridge source */
  Source: string;
  /** Human-readable event type */
  DetailType: string;
  Detail: object;
  /** EventBridge bus name */
  EventBusName?: string;
  Time?: Date;
  Resources?: string[];
}
