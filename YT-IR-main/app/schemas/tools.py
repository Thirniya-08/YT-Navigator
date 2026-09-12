"""Schemas for the tools."""

from pydantic import (
    BaseModel,
    Field,
)
from typing import Optional


class VectorDatabaseToolInput(BaseModel):
    """Input for the vector database tool."""

    query: str = Field(description="The textual query to search for videos, optimized for similarity search")
    channel_id: Optional[str] = Field(default=None, description="The ID of the YouTube channel associated with the query (optional for single video mode)")


class SQLQueryToolInput(BaseModel):
    """Input for the SQL query tool."""

    query: str = Field(description="The SQL query to execute that respects the database schema")
