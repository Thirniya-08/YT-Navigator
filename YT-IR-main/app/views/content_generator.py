"""Views for content generation features."""

import json
import traceback

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
)
from django.shortcuts import (
    redirect,
    render,
)
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from structlog import get_logger

from app.services.content_generator.notes_generator import NotesGenerator
from app.services.content_generator.mindmap_generator import MindmapGenerator
from app.services.scraping.youtube_scraper import YoutubeScraper

logger = get_logger(__name__)

notes_generator = NotesGenerator()
mindmap_generator = MindmapGenerator()
youtube_scraper = YoutubeScraper()


@login_required
@require_http_methods(["GET"])
def notes_generator_page(request: HttpRequest) -> HttpResponse:
    """Render the notes generator page."""
    return render(request, "notes_generator.html", {})


@login_required
@require_http_methods(["POST"])
async def generate_notes(request: HttpRequest) -> JsonResponse:
    """Generate notes from stored video chunks in SQLite."""
    try:
        from asgiref.sync import sync_to_async
        from app.models import Video
        
        data = json.loads(request.body)
        video_url = data.get("video_url", "").strip()

        if not video_url:
            return JsonResponse({"error": "Video URL is required"}, status=400)

        # Extract video ID
        video_id = youtube_scraper.validate_video_link(video_url)
        if not video_id:
            return JsonResponse({"error": "Invalid YouTube URL"}, status=400)

        # Check if video exists in SQLite database
        get_video = sync_to_async(lambda: Video.objects.filter(id=video_id).first(), thread_sensitive=True)
        video_obj = await get_video()
        
        if not video_obj:
            # Video not in database, needs to be scanned first
            logger.warning("Video not found in database, user needs to scan it first", video_id=video_id)
            return JsonResponse({
                "error": "Video not found in database. Please process/scan the video first on the home page.",
                "status": "needs_scanning"
            }, status=404)
        
        # Generate notes from stored chunks
        notes_data = await notes_generator.generate_notes_from_video_id(
            video_id, 
            video_obj.title
        )

        logger.info("Notes generated successfully from stored chunks", 
                   video_id=video_id, 
                   video_title=video_obj.title)
        return JsonResponse({
            "success": True,
            "notes": notes_data,
            "video_info": {
                "id": video_id,
                "title": video_obj.title,
                "thumbnail": video_obj.thumbnail,
                "duration": ""
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request format"}, status=400)
    except Exception as e:
        logger.error("Error generating notes", error=str(e), traceback=traceback.format_exc())
        return JsonResponse({"error": "Failed to generate notes. Please try again."}, status=500)


@login_required
@require_http_methods(["GET"])
def mindmap_generator_page(request: HttpRequest) -> HttpResponse:
    """Render the mindmap generator page."""
    return render(request, "mindmap_generator.html", {})


@login_required
@require_http_methods(["POST"])
async def generate_mindmap(request: HttpRequest) -> JsonResponse:
    """Generate mindmap from YouTube video URL."""
    try:
        data = json.loads(request.body)
        video_url = data.get("video_url", "").strip()

        if not video_url:
            return JsonResponse({"error": "Video URL is required"}, status=400)

        # Extract video ID and get transcript using existing scraper
        video_id = youtube_scraper.validate_video_link(video_url)
        if not video_id:
            return JsonResponse({"error": "Invalid YouTube URL"}, status=400)

        # Get video info and transcript
        video_info_result = await youtube_scraper.scrape_single_video(video_url)
        if not video_info_result or not video_info_result[0]:
            return JsonResponse({"error": "Unable to fetch video information"}, status=404)

        video_info = video_info_result[0]
        video_chunks = video_info_result[1]
        
        # Extract transcript text from chunks
        transcript = ""
        if video_chunks:
            transcript = " ".join([chunk.get("text", "") for chunk in video_chunks if chunk.get("text")])

        if not transcript:
            return JsonResponse({"error": "Unable to fetch transcript for this video"}, status=404)

        # Generate mindmap
        mindmap_data = mindmap_generator.generate_mindmap(transcript, video_info.get("title", ""))

        logger.info("Mindmap generated successfully", video_id=video_id, video_title=video_info.get("title"))
        return JsonResponse({
            "success": True,
            "mindmap": mindmap_data,
            "video_info": {
                "id": video_id,
                "title": video_info.get("title", ""),
                "thumbnail": video_info.get("thumbnail", "https://i.ytimg.com/vi/default/default.jpg"),
                "duration": video_info.get("duration", "")
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request format"}, status=400)
    except Exception as e:
        logger.error("Error generating mindmap", error=str(e), traceback=traceback.format_exc())
        return JsonResponse({"error": "Failed to generate mindmap. Please try again."}, status=500)
