from django.contrib import admin
from .models import ChatSession, ChatMessage


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("session_id", "project_name", "project_path", "os", "created_at", "updated_at")
    search_fields = ("session_id", "project_name", "project_path")
    list_filter = ("os", "created_at")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "session_slug", "role", "model", "created_at")
    search_fields = ("session_slug", "message", "thinking")
    list_filter = ("role", "model", "created_at")
