"""Response schema for the /health endpoint."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Schema for the application health check response."""

    status: str
    uptime_seconds: float
    vpn_interface_bound: bool
