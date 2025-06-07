import { Entity, Column, ManyToOne, JoinColumn, Index } from 'typeorm';

import { BaseEntity } from './BaseEntity';
import { ObjectType } from './ObjectType';
import { PropertyType, PropertyConstraints, NodeMetadata } from './types';

@Entity('properties')
@Index(['objectType', 'apiName'], { unique: true })
export class Property extends BaseEntity {
  @Column({ type: 'varchar', length: 200 })
  apiName!: string;

  @Column({ type: 'varchar', length: 200 })
  displayName!: string;

  @Column({ type: 'text', nullable: true })
  description?: string;

  @Column({
    type: 'enum',
    enum: PropertyType,
  })
  type!: PropertyType;

  @Column({ type: 'boolean', default: false })
  required!: boolean;

  @Column({ type: 'boolean', default: false })
  multiple!: boolean;

  @Column({ type: 'jsonb', nullable: true })
  defaultValue?: unknown;

  @Column({ type: 'jsonb', nullable: true })
  constraints?: PropertyConstraints;

  @Column({ type: 'jsonb', nullable: true })
  metadata?: NodeMetadata;

  @ManyToOne(() => ObjectType, (objectType) => objectType.properties, {
    onDelete: 'CASCADE',
  })
  @JoinColumn({ name: 'object_type_id' })
  objectType!: ObjectType;
}
