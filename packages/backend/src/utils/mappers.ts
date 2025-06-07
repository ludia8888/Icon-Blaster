import { ObjectTypeResponse } from '@arrakis/contracts';

import { ObjectType } from '../entities/ObjectType';

export function mapObjectTypeToResponse(objectType: ObjectType): ObjectTypeResponse {
  return {
    rid: objectType.rid,
    apiName: objectType.apiName,
    displayName: objectType.displayName,
    pluralDisplayName: objectType.pluralDisplayName,
    description: objectType.description,
    icon: objectType.icon,
    color: objectType.color,
    groups: objectType.groups ?? [],
    visibility: objectType.visibility,
    status: objectType.status,
    version: objectType.version,
    createdAt: objectType.createdAt.toISOString(),
    updatedAt: objectType.updatedAt.toISOString(),
    createdBy: objectType.createdBy ?? 'system',
    updatedBy: objectType.updatedBy ?? 'system',
  };
}