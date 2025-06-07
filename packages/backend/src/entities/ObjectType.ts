import { Entity, Column, OneToMany, Index } from 'typeorm';

import { BaseEntity } from './BaseEntity';
import { LinkType } from './LinkType';
import { Property } from './Property';
import { NodeStatus, NodeVisibility, NodeMetadata } from './types';

@Entity('object_types')
@Index(['apiName'], { unique: true })
@Index(['status'])
export class ObjectType extends BaseEntity {
  @Column({ type: 'varchar', length: 200 })
  apiName!: string;

  @Column({ type: 'varchar', length: 200 })
  displayName!: string;

  @Column({ type: 'varchar', length: 200 })
  pluralDisplayName!: string;

  @Column({ type: 'text', nullable: true })
  description?: string;

  @Column({ type: 'varchar', length: 100, nullable: true })
  icon?: string;

  @Column({ type: 'varchar', length: 7, nullable: true })
  color?: string;

  @Column({
    type: 'enum',
    enum: NodeStatus,
    default: NodeStatus.ACTIVE,
  })
  status!: NodeStatus;

  @Column({
    type: 'enum',
    enum: NodeVisibility,
    default: NodeVisibility.NORMAL,
  })
  visibility!: NodeVisibility;

  @Column({ type: 'jsonb', nullable: true })
  metadata?: NodeMetadata;

  @Column({ type: 'simple-array', nullable: true })
  groups?: string[];

  @Column({ type: 'varchar', nullable: true })
  titleProperty?: string;

  @OneToMany(() => Property, (property) => property.objectType)
  properties!: Property[];

  @OneToMany(() => LinkType, (linkType) => linkType.sourceObjectType)
  sourceLinks!: LinkType[];

  @OneToMany(() => LinkType, (linkType) => linkType.targetObjectType)
  targetLinks!: LinkType[];
}
