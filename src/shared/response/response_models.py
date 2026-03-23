"""Standard API response models"""

from typing import TypeVar, Generic, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standard API response wrapper"""

    success: bool = Field(
        description="Whether the request was successful",
    )
    message: str = Field(
        description="Human-readable message",
    )
    data: Optional[T] = Field(
        default=None,
        description="Response data payload",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp",
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Optional request ID for tracking",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": None,
                "timestamp": "2026-03-14T14:35:44.591Z",
                "request_id": "req_12345",
            }
        }


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper"""

    success: bool = Field(
        description="Whether the request was successful",
    )
    message: str = Field(
        description="Human-readable message",
    )
    data: list[T] = Field(
        description="List of items",
    )
    pagination: dict = Field(
        description="Pagination metadata",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp",
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Optional request ID for tracking",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Items retrieved successfully",
                "data": [],
                "pagination": {
                    "total": 0,
                    "page": 1,
                    "per_page": 10,
                    "total_pages": 0,
                },
                "timestamp": "2026-03-14T14:35:44.591Z",
                "request_id": "req_12345",
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response"""

    success: bool = Field(default=False)
    message: str = Field(
        description="Error message",
    )
    error_code: Optional[str] = Field(
        default=None,
        description="Error code for programmatic handling",
    )
    details: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional error details",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Error timestamp",
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Optional request ID for tracking",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "message": "An error occurred",
                "error_code": "INTERNAL_SERVER_ERROR",
                "details": None,
                "timestamp": "2026-03-14T14:35:44.591Z",
                "request_id": "req_12345",
            }
        }


def create_response(
    data: Optional[T] = None,
    message: str = "Success",
    request_id: Optional[str] = None,
) -> ApiResponse:
    """Create a successful API response"""
    return ApiResponse(
        success=True,
        message=message,
        data=data,
        request_id=request_id,
    )


def create_paginated_response(
    data: list[T],
    total: int,
    page: int = 1,
    per_page: int = 10,
    message: str = "Items retrieved successfully",
    request_id: Optional[str] = None,
) -> PaginatedResponse:
    """Create a paginated API response"""
    total_pages = (total + per_page - 1) // per_page
    return PaginatedResponse(
        success=True,
        message=message,
        data=data,
        pagination={
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        },
        request_id=request_id,
    )


def create_error_response(
    message: str,
    error_code: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> ErrorResponse:
    """Create an error API response"""
    return ErrorResponse(
        success=False,
        message=message,
        error_code=error_code,
        details=details,
        request_id=request_id,
    )
