"""
Git utilities for getting current commit hash
"""
import subprocess
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_current_commit_hash() -> str:
    """
    Get the current git commit hash
    Returns 'development' if not in a git repository
    """
    try:
        # Check if we're in a git repository
        if not os.path.exists('.git'):
            return "development"
        
        # Get the current commit hash
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        
        commit_hash = result.stdout.strip()
        
        # Also check if there are uncommitted changes
        status_result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True,
            text=True,
            check=True
        )
        
        if status_result.stdout.strip():
            # There are uncommitted changes
            commit_hash += "-dirty"
        
        return commit_hash[:12]  # Return first 12 characters
        
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Git not available or not a git repository
        return "development"
    except Exception:
        return "unknown"


def get_git_branch() -> str:
    """Get current git branch name"""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except:
        return "unknown"