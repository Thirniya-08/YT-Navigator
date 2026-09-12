"""This module contains the tools for the SQL database."""

import asyncio
from typing import (
    Any,
    Dict,
    List,
)

from django.conf import settings
from langchain.tools import StructuredTool

from app.models import (
    Channel,
    User,
    Video,
    VideoChunk,
)
from app.schemas import SQLQueryToolInput


class SQLTools:
    """A tool for executing SQL queries and database operations."""

    
    @classmethod
    def get_tables_schema(cls):
        """Retrieve the schema information for all relevant database tables, excluding User table."""
        project_models = [Channel, Video, VideoChunk]  # Removed User model
        tables = []
        for model in project_models:
            table_info = {
                "table_name": model._meta.db_table,
                "fields": [
                    {
                        "name": field.name,
                        "type": field.get_internal_type(),
                    }
                    for field in model._meta.fields
                ],
            }
            tables.append(table_info)
        return tables

    @classmethod
    def _format_tables_schema(cls, tables: List[Dict[str, Any]]) -> str:
        """Format tables schema as a concise markdown representation.

        Args:
            tables: List of table schema dictionaries

        Returns:
            Markdown formatted string of table schemas
        """
        markdown = ""
        for table in tables:
            markdown += f"### {table['table_name']}\n"
            markdown += "| Field | Type |\n|-------|------|\n"
            for field in table["fields"]:
                markdown += f"| {field['name']} | {field['type']} |\n"
            markdown += "\n"
        return markdown

    @classmethod
    async def execute_query(cls, query: str) -> str:
        """Execute a SELECT query and return the results.

        Args:
            query: The SQL query to execute (must be a SELECT query)

        Returns:
            List of result rows as strings or an error message
        """
        if not query.startswith("SELECT"):
            return "Error: Only SELECT queries are supported"

        # get Video db_name
        video_db_name = Video._meta.db_table
        chunk_db_name = VideoChunk._meta.db_table
        if video_db_name not in query and chunk_db_name not in query:
            return f"""DB SCHEMA:\n{cls.get_tables_schema()}\nError: You are allowed only to search in the {video_db_name} and {chunk_db_name} tables"""

        try:
            import sqlite3
            from django.conf import settings as django_settings
            db_path = django_settings.DATABASES["default"]["NAME"]
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(query)
                result = cursor.fetchall()
                formated_result = [str(dict(row)) for row in result]
                if len(formated_result) > 20:
                    formated_result.append(
                        f"The result is too long; truncated to 20 rows from a total of {len(formated_result)} rows."
                    )
                    return "\n".join(formated_result[:20])
                return "\n".join(formated_result) if formated_result else "No results found."
            finally:
                conn.close()
        except Exception as e:
            return f"""
            DB SCHEMA:
            {cls.get_tables_schema()}
        
            #Error: {e}
            """

    @classmethod
    def execute_query_sync(cls, query: str) -> str:
        """Execute a SELECT query synchronously and return the results.

        Args:
            query: The SQL query to execute (must be a SELECT query)

        Returns:
            Formatted result rows as a string or an error message
        """
        if not query.startswith("SELECT"):
            return "Error: Only SELECT queries are supported"

        video_db_name = Video._meta.db_table
        chunk_db_name = VideoChunk._meta.db_table
        if video_db_name not in query and chunk_db_name not in query:
            return f"""DB SCHEMA:\n{cls.get_tables_schema()}\nError: You are allowed only to search in the {video_db_name} and {chunk_db_name} tables"""

        try:
            import sqlite3
            from django.conf import settings as django_settings
            db_path = django_settings.DATABASES["default"]["NAME"]
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(query)
                result = cursor.fetchall()
                formated_result = [str(dict(row)) for row in result]
                if len(formated_result) > 20:
                    formated_result.append(
                        f"The result is too long; truncated to 20 rows from a total of {len(formated_result)} rows."
                    )
                    return "\n".join(formated_result[:20])
                return "\n".join(formated_result) if formated_result else "No results found."
            finally:
                conn.close()
        except Exception as e:
            return f"""
            DB SCHEMA:
            {cls.get_tables_schema()}
        
            #Error: {e}
            """

    @classmethod
    def tool(cls) -> StructuredTool:
        """Create a structured tool for executing SQL queries."""
        
        return StructuredTool.from_function(
            func=cls.execute_query_sync,
            name="execute_query",
            description="Powerful SQL query execution tool for advanced data retrieval and analysis. Use this to perform complex database operations such as: "
            "- Joining multiple tables to extract comprehensive insights "
            "- Filtering and aggregating video metadata "
            "- Performing complex calculations or statistical analysis "
            "- Retrieving specific subsets of data not easily accessible through other methods "
            f"\n Table schema:\nSQLITE SYNTAX:\n{cls.get_tables_schema()}",
            args_schema=SQLQueryToolInput,
            handle_tool_error=True,
        )

    @classmethod
    def get_tables_schema_markdown(cls) -> str:
        """Get database schema as concise markdown, excluding User table.

        Returns:
            Markdown formatted string of table schemas
        """
        tables = cls.get_tables_schema()
        return cls._format_tables_schema(tables)
