from typing import Generic, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class APIResponse(BaseModel, Generic[DataT]):
    success: bool
    message: str = ""
    data: DataT
    request_id: str = Field(default="")


class HealthData(BaseModel):
    status: str
    mongodb: str
    request_id: str
