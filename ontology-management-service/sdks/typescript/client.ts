/**
 * Auto-generated TypeScript client for oms-event-sdk
 * Generated at: 2025-06-25T11:15:14.778100
 * DO NOT EDIT - This file is auto-generated
 */

import { EventPublisher, EventSubscriber, PublishResult, Subscription } from './types';

export interface ClientConfig {
  natsUrl?: string;
  websocketUrl?: string;
  httpUrl?: string;
  credentials?: {
    username?: string;
    password?: string;
    token?: string;
  };
}

export class OMSEventClient {
  private publisher: EventPublisher;
  private subscriber: EventSubscriber;
  
  constructor(
    publisher: EventPublisher,
    subscriber: EventSubscriber
  ) {
    this.publisher = publisher;
    this.subscriber = subscriber;
  }
  
  static async connect(config: ClientConfig = {}): Promise<OMSEventClient> {
    // Factory method to create client with appropriate adapters
    const natsUrl = config.natsUrl || 'nats://nats.oms.company.com:4222';
    const wsUrl = config.websocketUrl || 'ws://localhost:8080';
    
    // Implementation would depend on the actual transport libraries
    // This is a placeholder for the interface
    throw new Error('Please implement transport-specific adapters');
  }

  // Generated client methods

  /**
   * Publish Schema Created
   * Channel: oms.schema.created.{branch}
   */
  async publishschemacreated(payload: SchemacreatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.schema.created.{branch}', payload);
  }

  /**
   * Publish Schema Created to EventBridge
   * Channel: eventbridge/schema/created
   */
  async publisheventbridgeschemacreated(payload: SchemacreatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/schema/created', payload);
  }

  /**
   * Publish Schema Updated
   * Channel: oms.schema.updated.{branch}
   */
  async publishschemaupdated(payload: SchemaupdatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.schema.updated.{branch}', payload);
  }

  /**
   * Publish Schema Updated to EventBridge
   * Channel: eventbridge/schema/updated
   */
  async publisheventbridgeschemaupdated(payload: SchemaupdatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/schema/updated', payload);
  }

  /**
   * Publish Schema Deleted
   * Channel: oms.schema.deleted.{branch}
   */
  async publishschemadeleted(payload: SchemadeletedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.schema.deleted.{branch}', payload);
  }

  /**
   * Publish Schema Deleted to EventBridge
   * Channel: eventbridge/schema/deleted
   */
  async publisheventbridgeschemadeleted(payload: SchemadeletedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/schema/deleted', payload);
  }

  /**
   * Publish Schema Validated
   * Channel: oms.schema.validated.{branch}
   */
  async publishschemavalidated(payload: SchemavalidatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.schema.validated.{branch}', payload);
  }

  /**
   * Publish Schema Validated to EventBridge
   * Channel: eventbridge/schema/validated
   */
  async publisheventbridgeschemavalidated(payload: SchemavalidatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/schema/validated', payload);
  }

  /**
   * Publish Object Type Created
   * Channel: oms.objecttype.created.{branch}.{resourceId}
   */
  async publishobjecttypecreated(payload: ObjecttypecreatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.objecttype.created.{branch}.{resourceId}', payload);
  }

  /**
   * Publish Object Type Created to EventBridge
   * Channel: eventbridge/objecttype/created
   */
  async publisheventbridgeobjecttypecreated(payload: ObjecttypecreatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/objecttype/created', payload);
  }

  /**
   * Publish Object Type Updated
   * Channel: oms.objecttype.updated.{branch}.{resourceId}
   */
  async publishobjecttypeupdated(payload: ObjecttypeupdatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.objecttype.updated.{branch}.{resourceId}', payload);
  }

  /**
   * Publish Object Type Updated to EventBridge
   * Channel: eventbridge/objecttype/updated
   */
  async publisheventbridgeobjecttypeupdated(payload: ObjecttypeupdatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/objecttype/updated', payload);
  }

  /**
   * Publish Object Type Deleted
   * Channel: oms.objecttype.deleted.{branch}.{resourceId}
   */
  async publishobjecttypedeleted(payload: ObjecttypedeletedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.objecttype.deleted.{branch}.{resourceId}', payload);
  }

  /**
   * Publish Object Type Deleted to EventBridge
   * Channel: eventbridge/objecttype/deleted
   */
  async publisheventbridgeobjecttypedeleted(payload: ObjecttypedeletedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/objecttype/deleted', payload);
  }

  /**
   * Publish Property Created
   * Channel: oms.property.created.{branch}.{resourceId}
   */
  async publishpropertycreated(payload: PropertycreatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.property.created.{branch}.{resourceId}', payload);
  }

  /**
   * Publish Property Created to EventBridge
   * Channel: eventbridge/property/created
   */
  async publisheventbridgepropertycreated(payload: PropertycreatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/property/created', payload);
  }

  /**
   * Publish Property Updated
   * Channel: oms.property.updated.{branch}.{resourceId}
   */
  async publishpropertyupdated(payload: PropertyupdatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.property.updated.{branch}.{resourceId}', payload);
  }

  /**
   * Publish Property Updated to EventBridge
   * Channel: eventbridge/property/updated
   */
  async publisheventbridgepropertyupdated(payload: PropertyupdatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/property/updated', payload);
  }

  /**
   * Publish Property Deleted
   * Channel: oms.property.deleted.{branch}.{resourceId}
   */
  async publishpropertydeleted(payload: PropertydeletedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.property.deleted.{branch}.{resourceId}', payload);
  }

  /**
   * Publish Property Deleted to EventBridge
   * Channel: eventbridge/property/deleted
   */
  async publisheventbridgepropertydeleted(payload: PropertydeletedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/property/deleted', payload);
  }

  /**
   * Publish Link Type Created
   * Channel: oms.linktype.created.{branch}.{resourceId}
   */
  async publishlinktypecreated(payload: LinktypecreatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.linktype.created.{branch}.{resourceId}', payload);
  }

  /**
   * Publish Link Type Created to EventBridge
   * Channel: eventbridge/linktype/created
   */
  async publisheventbridgelinktypecreated(payload: LinktypecreatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/linktype/created', payload);
  }

  /**
   * Publish Link Type Updated
   * Channel: oms.linktype.updated.{branch}.{resourceId}
   */
  async publishlinktypeupdated(payload: LinktypeupdatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.linktype.updated.{branch}.{resourceId}', payload);
  }

  /**
   * Publish Link Type Updated to EventBridge
   * Channel: eventbridge/linktype/updated
   */
  async publisheventbridgelinktypeupdated(payload: LinktypeupdatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/linktype/updated', payload);
  }

  /**
   * Publish Link Type Deleted
   * Channel: oms.linktype.deleted.{branch}.{resourceId}
   */
  async publishlinktypedeleted(payload: LinktypedeletedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.linktype.deleted.{branch}.{resourceId}', payload);
  }

  /**
   * Publish Link Type Deleted to EventBridge
   * Channel: eventbridge/linktype/deleted
   */
  async publisheventbridgelinktypedeleted(payload: LinktypedeletedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/linktype/deleted', payload);
  }

  /**
   * Publish Branch Created
   * Channel: oms.branch.created.{branchName}
   */
  async publishbranchcreated(payload: BranchcreatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.branch.created.{branchName}', payload);
  }

  /**
   * Publish Branch Created to EventBridge
   * Channel: eventbridge/branch/created
   */
  async publisheventbridgebranchcreated(payload: BranchcreatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/branch/created', payload);
  }

  /**
   * Publish Branch Updated
   * Channel: oms.branch.updated.{branchName}
   */
  async publishbranchupdated(payload: BranchupdatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.branch.updated.{branchName}', payload);
  }

  /**
   * Publish Branch Updated to EventBridge
   * Channel: eventbridge/branch/updated
   */
  async publisheventbridgebranchupdated(payload: BranchupdatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/branch/updated', payload);
  }

  /**
   * Publish Branch Deleted
   * Channel: oms.branch.deleted.{branchName}
   */
  async publishbranchdeleted(payload: BranchdeletedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.branch.deleted.{branchName}', payload);
  }

  /**
   * Publish Branch Deleted to EventBridge
   * Channel: eventbridge/branch/deleted
   */
  async publisheventbridgebranchdeleted(payload: BranchdeletedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/branch/deleted', payload);
  }

  /**
   * Publish Branch Merged
   * Channel: oms.branch.merged.{branchName}
   */
  async publishbranchmerged(payload: BranchmergedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.branch.merged.{branchName}', payload);
  }

  /**
   * Publish Branch Merged to EventBridge
   * Channel: eventbridge/branch/merged
   */
  async publisheventbridgebranchmerged(payload: BranchmergedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/branch/merged', payload);
  }

  /**
   * Publish Proposal Created
   * Channel: oms.proposal.created.{branch}
   */
  async publishproposalcreated(payload: ProposalcreatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.proposal.created.{branch}', payload);
  }

  /**
   * Publish Proposal Created to EventBridge
   * Channel: eventbridge/proposal/created
   */
  async publisheventbridgeproposalcreated(payload: ProposalcreatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/proposal/created', payload);
  }

  /**
   * Publish Proposal Updated
   * Channel: oms.proposal.updated.{branch}
   */
  async publishproposalupdated(payload: ProposalupdatedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.proposal.updated.{branch}', payload);
  }

  /**
   * Publish Proposal Updated to EventBridge
   * Channel: eventbridge/proposal/updated
   */
  async publisheventbridgeproposalupdated(payload: ProposalupdatedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/proposal/updated', payload);
  }

  /**
   * Publish Proposal Approved
   * Channel: oms.proposal.approved.{branch}
   */
  async publishproposalapproved(payload: ProposalapprovedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.proposal.approved.{branch}', payload);
  }

  /**
   * Publish Proposal Approved to EventBridge
   * Channel: eventbridge/proposal/approved
   */
  async publisheventbridgeproposalapproved(payload: ProposalapprovedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/proposal/approved', payload);
  }

  /**
   * Publish Proposal Rejected
   * Channel: oms.proposal.rejected.{branch}
   */
  async publishproposalrejected(payload: ProposalrejectedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.proposal.rejected.{branch}', payload);
  }

  /**
   * Publish Proposal Rejected to EventBridge
   * Channel: eventbridge/proposal/rejected
   */
  async publisheventbridgeproposalrejected(payload: ProposalrejectedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/proposal/rejected', payload);
  }

  /**
   * Publish Proposal Merged
   * Channel: oms.proposal.merged.{branch}
   */
  async publishproposalmerged(payload: ProposalmergedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.proposal.merged.{branch}', payload);
  }

  /**
   * Publish Proposal Merged to EventBridge
   * Channel: eventbridge/proposal/merged
   */
  async publisheventbridgeproposalmerged(payload: ProposalmergedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/proposal/merged', payload);
  }

  /**
   * Publish Action Started
   * Channel: oms.action.started.{jobId}
   */
  async publishactionstarted(payload: ActionstartedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.action.started.{jobId}', payload);
  }

  /**
   * Publish Action Started to EventBridge
   * Channel: eventbridge/action/started
   */
  async publisheventbridgeactionstarted(payload: ActionstartedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/action/started', payload);
  }

  /**
   * Publish Action Completed
   * Channel: oms.action.completed.{jobId}
   */
  async publishactioncompleted(payload: ActioncompletedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.action.completed.{jobId}', payload);
  }

  /**
   * Publish Action Completed to EventBridge
   * Channel: eventbridge/action/completed
   */
  async publisheventbridgeactioncompleted(payload: ActioncompletedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/action/completed', payload);
  }

  /**
   * Publish Action Failed
   * Channel: oms.action.failed.{jobId}
   */
  async publishactionfailed(payload: ActionfailedPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.action.failed.{jobId}', payload);
  }

  /**
   * Publish Action Failed to EventBridge
   * Channel: eventbridge/action/failed
   */
  async publisheventbridgeactionfailed(payload: ActionfailedEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/action/failed', payload);
  }

  /**
   * Publish Action Cancelled
   * Channel: oms.action.cancelled.{jobId}
   */
  async publishactioncancelled(payload: ActioncancelledPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.action.cancelled.{jobId}', payload);
  }

  /**
   * Publish Action Cancelled to EventBridge
   * Channel: eventbridge/action/cancelled
   */
  async publisheventbridgeactioncancelled(payload: ActioncancelledEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/action/cancelled', payload);
  }

  /**
   * Publish System Health Check
   * Channel: oms.system.healthcheck.{branch}
   */
  async publishsystemhealthcheck(payload: SystemhealthcheckPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.system.healthcheck.{branch}', payload);
  }

  /**
   * Publish System Health Check to EventBridge
   * Channel: eventbridge/system/healthcheck
   */
  async publisheventbridgesystemhealthcheck(payload: SystemhealthcheckEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/system/healthcheck', payload);
  }

  /**
   * Publish System Error
   * Channel: oms.system.error.{branch}
   */
  async publishsystemerror(payload: SystemerrorPayload): Promise<PublishResult> {
    return this.publisher.publish('oms.system.error.{branch}', payload);
  }

  /**
   * Publish System Error to EventBridge
   * Channel: eventbridge/system/error
   */
  async publisheventbridgesystemerror(payload: SystemerrorEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/system/error', payload);
  }

  /**
   * Publish System Maintenance
   * Channel: oms.system.maintenance.{branch}
   */
  async publishsystemmaintenance(payload: SystemmaintenancePayload): Promise<PublishResult> {
    return this.publisher.publish('oms.system.maintenance.{branch}', payload);
  }

  /**
   * Publish System Maintenance to EventBridge
   * Channel: eventbridge/system/maintenance
   */
  async publisheventbridgesystemmaintenance(payload: SystemmaintenanceEventBridgePayload): Promise<PublishResult> {
    return this.publisher.publish('eventbridge/system/maintenance', payload);
  }
  
  /**
   * Close all connections and cleanup resources
   */
  async close(): Promise<void> {
    // Implementation depends on transport
  }
}

// Export everything
export * from './types';
