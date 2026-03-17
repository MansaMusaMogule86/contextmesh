"""ContextMesh exception hierarchy."""

from __future__ import annotations


class ContextMeshError(Exception):
    """Base exception for all ContextMesh errors."""
    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthError(ContextMeshError):
    """Invalid or revoked API key."""


class RateLimitError(ContextMeshError):
    """Rate limit or monthly quota exceeded. Upgrade your plan."""


class NotFoundError(ContextMeshError):
    """Requested entry not found."""


class APIError(ContextMeshError):
    """Unexpected API response."""
