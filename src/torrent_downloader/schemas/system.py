"""Response schemas for system endpoints."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Schema for the application health check response."""

    status: str
    uptime_seconds: float
    vpn_interface_bound: bool


class CacheClearResponse(BaseModel):
    """Schema for the cache clear response."""

    cleared: bool
    message: str


class DiskUsageResponse(BaseModel):
    """Schema for disk usage response for a given save path."""

    path: str
    total_gb: float
    used_gb: float
    free_gb: float
    used_percent: float
