"""Schémas collections Typesense."""

from __future__ import annotations

PINS_COLLECTION = 'pins'
USERS_COLLECTION = 'users'
BOARDS_COLLECTION = 'boards'

PINS_SCHEMA = {
    'name': PINS_COLLECTION,
    'fields': [
        {'name': 'id', 'type': 'string'},
        {'name': 'slug', 'type': 'string'},
        {'name': 'title', 'type': 'string'},
        {'name': 'description', 'type': 'string', 'optional': True},
        {'name': 'author_username', 'type': 'string', 'facet': True},
        {'name': 'author_id', 'type': 'int32', 'facet': True},
        {'name': 'hashtags', 'type': 'string[]', 'optional': True, 'facet': True},
        {'name': 'visibility', 'type': 'string', 'facet': True},
        {'name': 'moderation_hidden', 'type': 'bool', 'facet': True},
        {'name': 'author_private_profile', 'type': 'bool', 'facet': True},
        {'name': 'created_at', 'type': 'int64', 'sort': True},
    ],
    'default_sorting_field': 'created_at',
}

USERS_SCHEMA = {
    'name': USERS_COLLECTION,
    'fields': [
        {'name': 'id', 'type': 'string'},
        {'name': 'username', 'type': 'string'},
        {'name': 'display_name', 'type': 'string', 'optional': True},
        {'name': 'discoverable_profile', 'type': 'bool', 'facet': True},
        {'name': 'avatar_color', 'type': 'string', 'optional': True},
    ],
}

BOARDS_SCHEMA = {
    'name': BOARDS_COLLECTION,
    'fields': [
        {'name': 'id', 'type': 'string'},
        {'name': 'name', 'type': 'string'},
        {'name': 'description', 'type': 'string', 'optional': True},
        {'name': 'owner_username', 'type': 'string', 'facet': True},
        {'name': 'owner_id', 'type': 'int32', 'facet': True},
        {'name': 'is_private', 'type': 'bool', 'facet': True},
        {'name': 'collaborator_ids', 'type': 'int32[]', 'optional': True},
        {'name': 'created_at', 'type': 'int64', 'sort': True},
    ],
    'default_sorting_field': 'created_at',
}

ALL_SCHEMAS = [PINS_SCHEMA, USERS_SCHEMA, BOARDS_SCHEMA]
