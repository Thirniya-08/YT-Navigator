"""Utility functions for vector database operations.

This module provides utility functions for generating unique IDs for documents,
calculating average scores, and converting chunks to minimal representations.
"""

import hashlib
import json
from typing import List

from langchain_core.documents.base import Document

from app.schemas import ChunkSchema


def get_chunk_id(chunk: Document) -> str:
    """Generate a unique ID for a document chunk."""
    serialized = json.dumps(
        {"content": chunk.page_content, "metadata": {k: v for k, v in chunk.metadata.items() if v is not None}}
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def get_avg_score(chunks: List[ChunkSchema], video_id: str) -> float:
    """Calculate the average score for a video."""
    import torch

    relevant_chunks = [r for r in chunks if r.videoId == video_id]
    if not relevant_chunks:
        return 0.0

    # Extract scores, handling both tensor and float types
    scores = []
    for r in relevant_chunks:
        score = r.score
        # If it's a tensor, convert to float
        if isinstance(score, torch.Tensor):
            score = score.item()
        scores.append(score)

    if not scores:
        return 0.0  # Safeguard against division by zero

    return sum(scores) / len(scores)


def minimise_chunks(chunks: List[dict]) -> List[ChunkSchema]:
    """Convert chunks to a minimal representation."""
    result = []
    for r in chunks:
        video_id = r.get("video_id") or r.get("videoId")
        text = r.get("text", "")
        score = r.get("score", 0)
        # Support both "start"/"end" and "start_time"/"duration"/"timestamp" formats
        start = r.get("start") or r.get("timestamp") or str(r.get("start_time", "0"))
        end = r.get("end")
        if not end and r.get("start_time") is not None and r.get("duration") is not None:
            end = str(r["start_time"] + r["duration"])
        elif not end:
            end = start

        if video_id and text:
            result.append(
                ChunkSchema(
                    text=text,
                    start=str(start),
                    end=str(end),
                    videoId=video_id,
                    score=score,
                )
            )
    return result
