"""Views for the app."""

from .authentication import register_view
from .chatbot import (
    chatbot_page,
    clear_chat_history,
    send_message,
)
from .content_generator import (
    generate_mindmap,
    generate_notes,
    mindmap_generator_page,
    notes_generator_page,
)
from .home import home_view
from .profile import profile_view
from .query import (
    query,
    query_page,
)
from .scan import (
    delete_video,
    process_single_video,
)

__all__ = [
    "home_view",
    "register_view",
    "profile_view",
    "process_single_video",
    "delete_video",
    "query_page",
    "query",
    "send_message",
    "chatbot_page",
    "clear_chat_history",
    "notes_generator_page",
    "generate_notes",
    "mindmap_generator_page",
    "generate_mindmap",
]
