"""Shared error response schema for OpenAPI documentation."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Schema for all structured error responses."""

    status: str
    code: str
    detail: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "error",
                "code": "UNAUTHORIZED",
                "detail": "Missing API key.",
            }
        }
    }
