"""
Compatibility Layer for IAM Integration
Maintains exact backward compatibility while using MSA architecture
"""
import os
from typing import Optional

# Re-export IAMScope from shared contracts to maintain import compatibility
from shared.iam_contracts import IAMScope

# Import the appropriate implementation based on configuration
USE_MSA_AUTH = os.getenv("USE_MSA_AUTH", "false").lower() == "true"

if USE_MSA_AUTH:
    from core.iam.iam_integration_refactored import (
        IAMIntegration,
        get_iam_integration
    )
else:
    from core.iam.iam_integration import (
        IAMIntegration as _OriginalIAMIntegration,
        get_iam_integration as _original_get_iam_integration
    )
    
    # Use original implementation
    IAMIntegration = _OriginalIAMIntegration
    get_iam_integration = _original_get_iam_integration

# Export all public APIs
__all__ = [
    'IAMScope',
    'IAMIntegration', 
    'get_iam_integration'
]