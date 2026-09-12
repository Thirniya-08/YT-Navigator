"""Query the vector database."""

import traceback

from asgiref.sync import sync_to_async
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import (
    HttpRequest,
    HttpResponse,
)
from django.shortcuts import (
    redirect,
    render,
)
from django.views.decorators.http import require_http_methods
from structlog import get_logger

from app.helpers import convert_time_to_seconds
from app.schemas import QueryVectorStoreResponse
from app.services.vector_database.tools import VectorDatabaseTools

logger = get_logger(__name__)

vector_database_tools = VectorDatabaseTools()


@login_required
@require_http_methods(["GET"])
def query_page(request: HttpRequest) -> HttpResponse:
    """Render the query page."""
    return render(request, "query.html", {})


@login_required
@require_http_methods(["POST"])
async def query(request: HttpRequest) -> HttpResponse:
    """Query the vector database."""
    query_msg: str = request.POST.get("query_msg", "")
    page_number = request.POST.get("page", 1)

    # No channel dependency - search all videos
    channel_id = None

    if not query_msg:
        messages.error(request, "Please enter a search query.")
        logger.error("No search query provided")
        return redirect("app:query_page")

    try:
        results: QueryVectorStoreResponse = await vector_database_tools.similarity_videos_search(
            query_msg, channel_id=channel_id
        )

        if not results or not results.videos:
            messages.info(request, "No results found. Try processing some videos first or try a different search query.")
            logger.info("No results found.")
            return await sync_to_async(render, thread_sensitive=True)(request, "query.html", {"query_msg": query_msg})
        # convert timestamps to seconds
        for chunk in results.chunks:
            chunk.start_in_seconds = convert_time_to_seconds(chunk.start)

        # Paginate videos
        paginator = Paginator(results.videos, 6)  # Show 6 videos per page
        page_obj = paginator.get_page(page_number)

        # Filter chunks for current page videos
        current_video_ids = [video.videoId for video in page_obj]
        current_chunks = [chunk for chunk in results.chunks if chunk.videoId in current_video_ids]

        return await sync_to_async(render, thread_sensitive=True)(
            request,
            "query.html",
            {
                "query_msg": query_msg,
                "videos": page_obj,
                "chunks": current_chunks,
                "page_obj": page_obj,
            },
        )

    except ValueError as e:
        logger.error("Invalid input error during search", error=e, traceback=traceback.format_exc())
        messages.error(request, "Invalid search parameters. Please try again.")
        return redirect("app:query_page")
    except ConnectionError as e:
        logger.error("Connection error during search", error=e, traceback=traceback.format_exc())
        messages.error(request, "Unable to connect to the search service. Please try again later.")
        return redirect("app:query_page")
    except Exception as e:
        logger.error("Unexpected error during search", error=e, traceback=traceback.format_exc())
        messages.error(request, "An unexpected error occurred while searching. Please try again.")
        return redirect("app:query_page")
