import { Entity, Column, ManyToOne, JoinColumn, Index } from 'typeorm';

import { BaseEntity } from './BaseEntity';
import { ObjectType } from './ObjectType';
import { LinkCardinality, NodeStatus, NodeMetadata } from './types';

@Entity('link_types')
@Index(['sourceObjectType', 'apiName'], { unique: true })
@Index(['status'])
export class LinkType extends BaseEntity {
  @Column({ type: 'varchar', length: 200 })
  apiName!: string;

  @Column({ type: 'varchar', length: 200 })
  displayName!: string;

  @Column({ type: 'varchar', length: 200 })
  reverseDisplayName!: string;

  @Column({ type: 'text', nullable: true })
  description?: string;

  @Column({
    type: 'enum',
    enum: LinkCardinality,
  })
  cardinality!: LinkCardinality;

  @Column({ type: 'boolean', default: false })
  required!: boolean;

  @Column({
    type: 'enum',
    enum: NodeStatus,
    default: NodeStatus.ACTIVE,
  })
  status!: NodeStatus;

  @Column({ type: 'jsonb', nullable: true })
  metadata?: NodeMetadata;

  @ManyToOne(() => ObjectType, (objectType) => objectType.sourceLinks, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'source_object_type_id' })
  sourceObjectType!: ObjectType;

  @ManyToOne(() => ObjectType, (objectType) => objectType.targetLinks, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'target_object_type_id' })
  targetObjectType!: ObjectType;
}
