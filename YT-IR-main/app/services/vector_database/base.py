"""This module provides a service for managing vector database operations and embeddings.

The VectorDatabaseService class handles vector storage operations, including initialization of embeddings,
managing database instances, and handling document operations. It supports both PostgreSQL (PGVector)
and SQLite (with FAISS fallback) for vector storage.
"""

import asyncio
import json
import os
import traceback
from functools import lru_cache
from typing import (
    Dict,
    List,
    Optional,
)

import structlog
import torch
from asgiref.sync import sync_to_async
from django.conf import settings
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents.base import Document
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from langchain_postgres.vectorstores import PGVector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import (
    Video,
    VideoChunk,
)
from yt_navigator.settings import DATABASE_URL

from .retriever import VectorRetriever
from .utils import get_chunk_id

logger = structlog.get_logger(__name__)


class VectorDatabaseService:
    """Service for managing vector database operations and embeddings.

    This service handles vector storage operations, including initialization of embeddings,
    managing database instances, and handling document operations.
    """

    # Singleton instance
    _instance = None

    # Create engine as a class attribute but use it to create separate connections
    # Skip async engine creation for SQLite (not supported)
    _ENGINE = None
    if "sqlite" not in DATABASE_URL.lower():
        _ENGINE = create_async_engine(
            DATABASE_URL,
            pool_size=20,  # Increase connection pool size
            max_overflow=10,  # Allow additional connections when pool is full
            pool_pre_ping=True,  # Check connection validity before using
            pool_recycle=3600,  # Recycle connections after 1 hour
            echo=False,
            future=True,  # Use the new future API
            pool_use_lifo=True,  # Use LIFO to reduce connection churn
        )

    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the VectorDatabaseService.

        Sets up the device for model inference and initializes the embeddings model
        with the configured settings. Supports both PostgreSQL (PGVector) and SQLite (FAISS).
        """
        if self._initialized:
            return
        self._initialized = True

        # Determine the best available device
        self.device = self._get_optimal_device()

        self._db_instances: Dict[str, Optional[PGVector]] = {}
        self._bm25_retrievers: Dict[str, Optional[BM25Retriever]] = {}
        
        # Check if using SQLite (fallback to FAISS)
        self.is_sqlite = "sqlite" in DATABASE_URL.lower()
        self._faiss_stores: Dict[str, Optional[FAISS]] = {}  # For SQLite fallback
        self._documents_store: Dict[str, List[Document]] = {}  # For storing documents with SQLite
        
        if self.is_sqlite:
            logger.info("Using SQLite database - will use FAISS for vector storage")
        else:
            logger.info("Using PostgreSQL database - will use PGVector for vector storage")

        logger.info("VectorDatabaseService initialized with connection pool")

    @property
    @lru_cache(maxsize=1)  # noqa: B019
    def embeddings(self):
        """Get the embeddings model.

        Returns:
            HuggingFaceEmbeddings: The embeddings model.
        """
        try:
            return HuggingFaceEmbeddings(
                model_name=settings.EMBEDDING_MODEL,
                model_kwargs={"device": self.device},
                cache_folder=os.environ.get("HF_HOME"),
            )
        except Exception as e:
            logger.error("Failed to initialize embeddings model", error=e, traceback=traceback.format_exc())
            raise

    def _get_optimal_device(self) -> str:
        """Determine the optimal device for model inference.

        Returns:
            str: 'cuda' if available and supported, otherwise 'cpu'

        Note:
            This method checks for CUDA availability and falls back to CPU if
            CUDA is not available or if an error occurs during detection.
        """
        try:
            # Check if CUDA is available and has GPU devices
            if torch.cuda.is_available() and torch.cuda.device_count() > 0:
                logger.info("CUDA is available. Using GPU.")
                return "cuda"
            else:
                logger.warning("CUDA not available. Falling back to CPU.")
                return "cpu"
        except Exception as e:
            logger.error(f"Error detecting device: {e}. Defaulting to CPU.")
            return "cpu"

    async def get_vstore(self, channel_id: str = None):
        """Get or create a vector store instance for a specific channel.

        Args:
            channel_id: The ID of the channel to get the vector store for (can be None for single video mode).

        Returns:
            Optional[Union[PGVector, FAISS]]: The vector store instance for the channel,
                or None if creation fails. Returns FAISS for SQLite, PGVector for PostgreSQL.
        """
        # Use a default channel ID for single video mode
        if not channel_id:
            channel_id = "default_channel"
        
        # For SQLite, use FAISS
        if self.is_sqlite:
            if channel_id not in self._faiss_stores:
                try:
                    logger.debug("Creating FAISS vector store for SQLite", channel_id=channel_id)
                    # Create empty FAISS store if documents don't exist yet
                    if channel_id not in self._documents_store or not self._documents_store[channel_id]:
                        # Create a dummy document to initialize FAISS
                        dummy_doc = Document(page_content="", metadata={"channel_id": channel_id})
                        self._faiss_stores[channel_id] = FAISS.from_documents(
                            documents=[dummy_doc],
                            embedding=self.embeddings,
                        )
                        logger.info("Initialized empty FAISS store", channel_id=channel_id)
                    else:
                        self._faiss_stores[channel_id] = FAISS.from_documents(
                            documents=self._documents_store[channel_id],
                            embedding=self.embeddings,
                        )
                except Exception as e:
                    logger.error("Failed to create FAISS store", error=str(e), traceback=traceback.format_exc())
                    self._faiss_stores[channel_id] = None
            
            return self._faiss_stores[channel_id]
        
        # For PostgreSQL, use PGVector
        if channel_id not in self._db_instances:
            try:
                # Get the current event loop
                current_loop = asyncio.get_running_loop()
                logger.debug("Creating PGVector instance in event loop", loop_id=id(current_loop))

                # Create a new connection engine for this specific operation
                # This ensures we're using the current event loop
                engine = create_async_engine(
                    DATABASE_URL,
                    pool_size=20,
                    max_overflow=10,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                    echo=False,
                    future=True,
                    pool_use_lifo=True,
                )

                self._db_instances[channel_id] = PGVector(
                    connection=engine,  # Use the new engine instance
                    collection_name=f"{channel_id}",
                    embeddings=self.embeddings,
                    create_extension=False,
                    use_jsonb=True,
                    async_mode=True,
                )
            except Exception as e:
                logger.error("Failed to create PGVector instance", error=str(e), traceback=traceback.format_exc())
                self._db_instances[channel_id] = None

        return self._db_instances[channel_id]

    def dict_to_langchain_documents(self, data: List[dict], **kwargs) -> List[Document]:
        """Convert dictionary data to Langchain Document objects.

        Args:
            data: List of dictionaries containing document data.
            **kwargs: Additional keyword arguments, must include 'channel_id'.

        Returns:
            List[Document]: List of Langchain Document objects with metadata.
        """
        documents = []
        for chunk in data:
            # Preserve all chunk metadata, including video_id if present
            metadata = {k: v for k, v in chunk.items() if v is not None and k != "text"}
            # Add channel_id to metadata
            metadata["channel_id"] = kwargs["channel_id"]
            
            # Debug: Log the first few chunks to verify metadata
            if len(documents) < 3:
                logger.info("Creating document with metadata", 
                           chunk_sample=chunk, 
                           metadata_keys=list(metadata.keys()),
                           has_video_id="video_id" in metadata)
            
            documents.append(
                Document(
                    page_content=chunk["text"],
                    metadata=metadata,
                )
            )
        return documents

    async def delete_video(self, video_id: str) -> int:
        """Delete a video and its associated vector embeddings.

        Args:
            video_id: The ID of the video to delete.

        Returns:
            int: Number of deleted records (0 if deletion fails).
        """
        try:
            async with self._ENGINE.begin() as conn:
                await conn.execute(
                    text("DELETE FROM langchain_pg_embedding WHERE cmetadata @> :metadata"),
                    {"metadata": json.dumps({"videoId": video_id})},
                )

            @sync_to_async(thread_sensitive=True)
            def delete_video_objects():
                return Video.objects.filter(id=video_id).delete()[0]

            try:
                return await delete_video_objects()
            except RuntimeError as e:
                logger.error("Event loop error during video deletion", error=e, traceback=traceback.format_exc())
                raise
        except Exception as e:
            logger.error(f"Error deleting video {video_id}", error=str(e), traceback=traceback.format_exc())
            return 0

    async def add_chunks(self, chunks: List[dict], channel_id: str = None) -> None:
        """Add chunks to the vector database.

        Args:
            chunks: List of chunks to add.
            channel_id: Channel ID for the chunks (optional, defaults to 'default_channel' for single video mode).

        Raises:
            Exception: If there's an error adding chunks.
        """
        if not channel_id:
            channel_id = "default_channel"
        
        try:
            logger.info("Adding chunks to vector database", chunks_count=len(chunks), channel_id=channel_id)
            
            # For SQLite with FAISS
            if self.is_sqlite:
                documents = self.dict_to_langchain_documents(chunks, channel_id=channel_id)
                
                if channel_id not in self._documents_store:
                    self._documents_store[channel_id] = []
                
                # Add new documents to store
                self._documents_store[channel_id].extend(documents)
                
                # Recreate FAISS store with all documents
                if documents:
                    try:
                        self._faiss_stores[channel_id] = FAISS.from_documents(
                            documents=self._documents_store[channel_id],
                            embedding=self.embeddings,
                        )
                        logger.info("Added chunks to FAISS store", chunks_count=len(documents), channel_id=channel_id)
                    except Exception as e:
                        logger.error("Error adding chunks to FAISS", error=str(e), traceback=traceback.format_exc())
                        raise

                # Also save VideoChunk objects to SQLite for BM25 keyword search
                await self._save_video_chunks_to_db(documents, channel_id)
                return
            
            # For PostgreSQL with PGVector
            vstore = await self.get_vstore(channel_id)
            if not vstore:
                logger.error("Failed to get vector store", channel_id=channel_id)
                return

            documents = self.dict_to_langchain_documents(chunks, channel_id=channel_id)
            chunks_ids = [get_chunk_id(c) for c in documents]
            non_existing_ids = await VectorRetriever.get_non_existing_ids(chunks_ids)

            if non_existing_ids:
                non_existing_chunks = [c for c in documents if get_chunk_id(c) in non_existing_ids]
                logger.info("Adding new chunks to the vector database", new_chunks_count=len(non_existing_chunks))
                try:
                    # Ensure we're using the same event loop
                    current_loop = asyncio.get_running_loop()
                    logger.debug("Adding documents in event loop", loop_id=id(current_loop))

                    # Create a new vstore instance specifically for this operation
                    # This ensures we're using the current event loop
                    temp_vstore = await self.get_vstore(channel_id)
                    if not temp_vstore:
                        logger.error("Failed to get vector store for document addition", channel_id=channel_id)
                        return

                    await self._add_chunks_in_batches(non_existing_chunks, channel_id, temp_vstore)
                except RuntimeError as e:
                    logger.error(
                        "Event loop error during document addition", error=e, traceback=traceback.format_exc()
                    )
                    raise

            # Create a function that performs the entire synchronous operation
            async def get_existing_texts():
                try:

                    @sync_to_async(thread_sensitive=True)
                    def _get_existing_texts():
                        return set(
                            VideoChunk.objects.filter(text__in=[c.page_content for c in documents]).values_list(
                                "text", flat=True
                            )
                        )

                    return await _get_existing_texts()
                except RuntimeError as e:
                    logger.error("Event loop error during text retrieval", error=e, traceback=traceback.format_exc())
                    raise

            # Get existing texts using the properly wrapped function
            existing_texts = await get_existing_texts()
            filtered_chunks = [c for c in documents if c.page_content not in existing_texts]

            # Create a function that performs the entire synchronous operation for videos
            async def get_videos():
                try:

                    @sync_to_async(thread_sensitive=True)
                    def _get_videos():
                        return {video.id: video for video in Video.objects.filter(channel_id=channel_id)}

                    return await _get_videos()
                except RuntimeError as e:
                    logger.error("Event loop error during video retrieval", error=e, traceback=traceback.format_exc())
                    raise

            # Get videos using the properly wrapped function
            videos = await get_videos()

            # Create VideoChunk objects for the filtered chunks
            video_chunks = []
            for chunk in filtered_chunks:
                video_id = chunk.metadata.get("video_id")
                if video_id in videos:
                    video = videos[video_id]

                    # Convert start_time and end_time to proper time format
                    start_time = chunk.metadata.get("start_time")
                    duration = chunk.metadata.get("duration")
                    end_time = start_time + duration if start_time is not None else None

                    # Format time values for Django TimeField (if they're not None)
                    formatted_start = self._format_time_for_django(start_time) if start_time is not None else None
                    formatted_end = self._format_time_for_django(end_time) if end_time is not None else None

                    video_chunks.append(
                        VideoChunk(
                            video=video,  # ForeignKey to Video model
                            start=formatted_start,  # TimeField
                            end=formatted_end,    # TimeField  
                            text=chunk.page_content,  # TextField
                        )
                    )

            # Bulk create the VideoChunk objects
            if video_chunks:
                logger.info("Creating VideoChunk objects", chunks_count=len(video_chunks))
                try:
                    await sync_to_async(VideoChunk.objects.bulk_create, thread_sensitive=True)(video_chunks)
                except Exception as e:
                    logger.error("Error creating VideoChunk objects", error=e, traceback=traceback.format_exc())
                    raise

        except Exception as e:
            logger.error("Error adding chunks", error=str(e), traceback=traceback.format_exc())
            raise

    async def _add_chunks_in_batches(self, chunks: List[Document], channel_id: str, vstore: PGVector):
        """Add chunks to the vector database in batches.

        Args:
            chunks: List of chunks to add.
            channel_id: Channel ID for the chunks.
            vstore: Vector store instance.
        """
        for i in range(0, len(chunks), settings.EMBEDDING_BATCH_SIZE):
            batch = chunks[i : i + settings.EMBEDDING_BATCH_SIZE]
            await vstore.aadd_documents(batch)

    def _format_time_for_django(self, seconds: float) -> str:
        """Format seconds into a time string compatible with Django TimeField.

        Args:
            seconds: Time in seconds.

        Returns:
            str: Time formatted as HH:MM:SS string.
        """
        if seconds is None:
            return None

        # Convert seconds to hours, minutes, seconds
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)

        # Format as HH:MM:SS
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    async def _save_video_chunks_to_db(self, documents: List[Document], channel_id: str) -> None:
        """Save VideoChunk objects to the database for BM25 keyword search.

        Args:
            documents: List of Langchain Document objects.
            channel_id: Channel ID for the chunks.
        """
        try:
            # Get existing texts to avoid duplicates
            existing_texts = await sync_to_async(
                lambda: set(
                    VideoChunk.objects.filter(text__in=[c.page_content for c in documents]).values_list("text", flat=True)
                )
            )()

            filtered_docs = [c for c in documents if c.page_content not in existing_texts]
            if not filtered_docs:
                return

            # Get videos for linking
            video_ids = list({c.metadata.get("video_id") for c in filtered_docs if c.metadata.get("video_id")})
            videos = await sync_to_async(
                lambda: {v.id: v for v in Video.objects.filter(id__in=video_ids)}
            )()

            video_chunks = []
            for chunk in filtered_docs:
                video_id = chunk.metadata.get("video_id")
                if video_id and video_id in videos:
                    start_time = chunk.metadata.get("start_time")
                    duration = chunk.metadata.get("duration")
                    end_time = start_time + duration if start_time is not None and duration is not None else None

                    video_chunks.append(
                        VideoChunk(
                            video=videos[video_id],
                            start=self._format_time_for_django(start_time) if start_time is not None else None,
                            end=self._format_time_for_django(end_time) if end_time is not None else None,
                            text=chunk.page_content,
                        )
                    )

            if video_chunks:
                await sync_to_async(VideoChunk.objects.bulk_create, thread_sensitive=True)(video_chunks)
                logger.info("Saved VideoChunk objects to DB", count=len(video_chunks))
        except Exception as e:
            logger.error("Error saving VideoChunks to DB", error=str(e), traceback=traceback.format_exc())

    async def close(self):
        """Close all database connections.

        This method should be called when the service is no longer needed
        to properly clean up resources and prevent connection leaks.
        """
        logger.info("Closing vector database connections")
        try:
            # Close all PGVector instances
            for channel_id, instance in self._db_instances.items():
                if instance:
                    try:
                        # PGVector doesn't have a direct close method, but we can close the engine
                        if hasattr(instance, "connection") and instance.connection:
                            await instance.connection.dispose()
                    except Exception as e:
                        logger.error(
                            f"Error closing PGVector instance for channel {channel_id}",
                            error=str(e),
                            traceback=traceback.format_exc(),
                        )

            # Clear the instances dictionary
            self._db_instances.clear()

            logger.info("All vector database connections closed")
        except Exception as e:
            logger.error("Error during database connection cleanup", error=str(e), traceback=traceback.format_exc())
