"""
Shared modules for OMS
Compatibility Shim for import resolution

⚠️  TEMPORARY SHIM - DO NOT RELY ON THIS LONG TERM
TODO: Remove all shims once proper module structure is in place
Issue: #OMS-IMPORT-FIX-2024

Target: 0 shims = Clean codebase with proper imports

Progress Tracking:
[ ] shared.middleware.rbac_middleware → middleware.rbac_middleware
[ ] shared.auth → api.gateway.auth
[ ] shared.events.nats_client → shared.infrastructure.nats_client  
[ ] services.* namespace → core.*
[ ] shared.clients.terminus_db → database.clients.terminus_db

Last Updated: 2024-01-25
"""
import sys
import types

def _alias(real_module_path: str, alias: str):
    """
    Create module alias for backward compatibility
    
    Args:
        real_module_path: Actual existing module path
        alias: Fake package path for compatibility
    """
    try:
        # Try to import the real module
        real_mod = __import__(real_module_path, fromlist=["*"])
    except ModuleNotFoundError:
        # Create dummy module if not exists
        real_mod = types.ModuleType(alias)
        # Add basic attributes to avoid attribute errors
        real_mod.__file__ = f"<dummy {alias}>"
        real_mod.__path__ = []
    
    # Create alias tree
    parts = alias.split(".")
    for i in range(1, len(parts) + 1):
        subpath = ".".join(parts[:i])
        if subpath not in sys.modules:
            parent_mod = types.ModuleType(subpath)
            parent_mod.__path__ = []
            sys.modules[subpath] = parent_mod
    
    # Set the final alias
    sys.modules[alias] = real_mod
    
    # Also set as attribute on parent module
    if len(parts) > 1:
        parent_path = ".".join(parts[:-1])
        if parent_path in sys.modules:
            setattr(sys.modules[parent_path], parts[-1], real_mod)

# ===== IMPORT COMPATIBILITY MAPPINGS =====
# Based on comprehensive import analysis

# 1. Middleware mappings
# REMOVED: OMS-SHIM-001 - Fixed import in api/graphql/main.py
# _alias("middleware.rbac_middleware", "shared.middleware.rbac_middleware")

# 2. Auth module mappings (GraphQL needs these)
# TODO(#OMS-SHIM-003): Consolidate auth module under shared/auth
_alias("api.gateway.auth", "shared.auth")
# TODO(#OMS-SHIM-004): Websocket auth should be part of unified auth
_alias("api.gateway.auth", "shared.auth.websocket_auth")

# Create dummy User class for shared.auth
if "shared.auth" in sys.modules:
    class User:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
    sys.modules["shared.auth"].User = User
    sys.modules["shared.auth"].UserContext = User  # Alias

# 3. Event system mappings
# TODO(#OMS-SHIM-005): NATS client should be under events package
_alias("shared.infrastructure.nats_client", "shared.events.nats_client")

# Import the real shared.events module first
import shared.events

# Create dummy event models
event_models = types.ModuleType("shared.events.models")
event_models.Event = type("Event", (), {})
event_models.EventType = type("EventType", (), {})
sys.modules["shared.events.models"] = event_models
if "shared.events" in sys.modules:
    sys.modules["shared.events"].models = event_models

# 4. Services namespace mappings
# API Gateway
# TODO(#OMS-SHIM-006): Remove services namespace - use api.gateway directly
_alias("api.gateway.auth", "services.api_gateway.core.auth")
# TODO(#OMS-SHIM-007): API gateway models in wrong namespace
_alias("api.gateway.models", "services.api_gateway.core.models")

# Event Publisher
# TODO(#OMS-SHIM-008): Event publisher should not be under services namespace
_alias("core.event_publisher.models", "services.event_publisher.core.models")
# TODO(#OMS-SHIM-009): State store is part of event publisher core
_alias("core.event_publisher.state_store", "services.event_publisher.core.state_store")

# Create services parent modules
for service in ["api_gateway", "event_publisher", "validation_service", "branch_service", "schema_service"]:
    service_path = f"services.{service}"
    core_path = f"{service_path}.core"
    
    if service_path not in sys.modules:
        sys.modules[service_path] = types.ModuleType(service_path)
        sys.modules[service_path].__path__ = []
    
    if core_path not in sys.modules:
        sys.modules[core_path] = types.ModuleType(core_path)
        sys.modules[core_path].__path__ = []
        sys.modules[service_path].core = sys.modules[core_path]

# 5. Additional common aliases
# TODO(#OMS-SHIM-010): TerminusDB client should use database.clients path
_alias("database.clients.terminus_db_simple", "shared.clients.terminus_db")

# Import actual modules to make them available
# First ensure shared.events exists
if "shared.events" not in sys.modules:
    sys.modules["shared.events"] = types.ModuleType("shared.events")

# Import and expose EventPublisher
# Load the actual events.py file directly
import os
events_path = os.path.join(os.path.dirname(__file__), 'events.py')
if os.path.exists(events_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("shared.events_real", events_path)
    events_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(events_module)
    
    # Make EventPublisher available
    if hasattr(events_module, 'EventPublisher'):
        EventPublisher = events_module.EventPublisher
        sys.modules["shared.events"].EventPublisher = EventPublisher
        # Also expose at package level
        globals()['EventPublisher'] = EventPublisher

print("✅ Import compatibility shim loaded successfully")