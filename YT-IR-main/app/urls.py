"""URLs for the app."""

from django.contrib.auth.views import (
    LoginView,
    LogoutView,
)
from django.urls import path

from .views import (
    chatbot_page,
    clear_chat_history,
    delete_video,
    generate_mindmap,
    generate_notes,
    home_view,
    mindmap_generator_page,
    notes_generator_page,
    process_single_video,
    profile_view,
    query,
    query_page,
    register_view,
    send_message,
)

app_name = "app"

urlpatterns = [
    # authentication
    path("register/", register_view, name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    # home page
    path("", home_view, name="home"),
    # profile page
    path("profile/", profile_view, name="profile"),
    # single video processing
    path("process-single-video/", process_single_video, name="process_single_video"),
    path("delete-video/<str:video_id>/", delete_video, name="delete_video"),
    # query page
    path("query/", query_page, name="query_page"),
    path("query-request/", query, name="query_request"),
    # chatbot
    path("chatbot/", chatbot_page, name="chatbot_page"),
    path("send-message/", send_message, name="send_message"),
    path("clear-chat-history/", clear_chat_history, name="clear_chat_history"),
    # content generation
    path("notes-generator/", notes_generator_page, name="notes_generator_page"),
    path("generate-notes/", generate_notes, name="generate_notes"),
    path("mindmap-generator/", mindmap_generator_page, name="mindmap_generator_page"),
    path("generate-mindmap/", generate_mindmap, name="generate_mindmap"),
]
