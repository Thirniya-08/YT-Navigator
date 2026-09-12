"""Chatbot views."""

import asyncio
import json
import traceback
from typing import Dict

import structlog
from asgiref.sync import sync_to_async
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

from app.services.agent.main_graph import get_graph_instance
from app.utils.rate_limiter import RateLimiter, create_retry_decorator

logger = structlog.get_logger(__name__)


@login_required
@require_http_methods(["GET"])
async def chatbot_page(request):
    """Render the chatbot page with chat history."""
    channel = await sync_to_async(lambda: request.user.channel)()
    user_id = await sync_to_async(lambda: str(request.user.id))()

    graph = await get_graph_instance()
    chat_history = await graph.get_chat_history(user_id)

    try:
        return render(
            request,
            "chatbot.html",
            {
                "channel": channel,
                "chat_history": chat_history,
            },
        )
    except Exception as e:
        logger.error("Failed to load chatbot page", error=str(e), traceback=traceback.format_exc())
        return render(request, "chatbot.html")


@login_required
@require_http_methods(["POST"])
async def send_message(request):
    """Process a message from the user and return a response."""
    user = await sync_to_async(lambda: request.user)()
    user_id = await sync_to_async(lambda: str(user.id))()
    message = request.POST.get("message", "").strip()

    if not message:
        logger.warning("Empty message received", user_id=user_id, message=message)
        return JsonResponse(
            {"error": True, "response": "Please enter a message before sending."},
            status=400,
        )

    try:
        # Get user's channel if available
        try:
            user_channel = await sync_to_async(
                lambda: request.user.channel if request.user.channel_id else None,
                thread_sensitive=True
            )()
        except Exception:
            user_channel = None

        # Get graph instance for the current event loop
        graph = await get_graph_instance()

        # Add better error handling and debugging
        try:
            logger.info("Starting agent processing", user_id=user_id, message=message)
            
            # Try direct processing first without rate limiter to isolate the issue
            try:
                response = await asyncio.wait_for(
                    graph.process_message(
                        message=message,
                        channel=user_channel,
                        user=user,
                    ),
                    timeout=60,  # Shorter timeout for debugging
                )
                logger.info("Direct processing successful", user_id=user_id, response_received=response is not None)
            except Exception as direct_error:
                logger.error("Direct processing failed", user_id=user_id, error=str(direct_error), traceback=traceback.format_exc())
                
                # Try with rate limiter as fallback
                rate_limiter = RateLimiter(max_retries=2, base_delay=1.0, max_delay=30.0)
                
                @create_retry_decorator(max_retries=2, base_delay=1.0, max_delay=30.0)
                async def process_with_rate_limit():
                    return await graph.process_message(
                        message=message,
                        channel=user_channel,
                        user=user,
                    )
                
                response = await asyncio.wait_for(
                    rate_limiter.execute_with_backoff(process_with_rate_limit),
                    timeout=120,  # 2 minute timeout
                )
                logger.info("Rate limited processing successful", user_id=user_id, response_received=response is not None)
                
        except asyncio.TimeoutError:
            logger.error("Agent processing timed out", user_id=user_id, message=message)
            return JsonResponse(
                {"error": True, "response": "The request took too long. Please try a simpler question."},
                status=504,
            )
        except Exception as e:
            logger.error("Agent processing failed completely", user_id=user_id, error=str(e), traceback=traceback.format_exc())
            return JsonResponse(
                {"error": True, "response": f"An error occurred: {str(e)}"},
                status=500,
            )

        if response is None:
            logger.warning("No response generated for message", user_id=user_id)
            from app.schemas import AgentOutput
            response = AgentOutput(
                placeholder="I couldn't find relevant information. Please try rephrasing your question.",
                videos=[],
            ).model_dump_json()

        return JsonResponse(response, safe=False)

    except Exception as e:
        error_message = str(e)
        status_code = 500

        if "Rate limit reached" in error_message:
            import re

            wait_time_match = re.search(r"try again in (\d+m\d+\.\d+s)", error_message)
            wait_time = wait_time_match.group(1) if wait_time_match else "a few minutes"
            error_message = f"Rate limit reached. Please wait {wait_time} before trying again."
            status_code = 429
        else:
            error_message = f"An error occurred: {error_message}"

        logger.error("Message processing failed", error=error_message, traceback=traceback.format_exc())
        return JsonResponse(
            {"error": True, "response": error_message},
            status=status_code,
        )


@login_required
@require_http_methods(["POST"])
async def clear_chat_history(request):
    """Clear the chat history for the current user."""
    user_id = await sync_to_async(lambda: str(request.user.id))()

    try:
        graph = await get_graph_instance()
        await graph.clear_chat_history(user_id)
        return JsonResponse({"success": True})

    except Exception as e:
        logger.error("Failed to clear chat history", type="error", error=str(e), traceback=traceback.format_exc())
        return JsonResponse({"success": False, "error": str(e)}, status=500)
