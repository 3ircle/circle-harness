import os
from rest_framework import serializers
from .models import ChatSession, ChatMessage


class MessageSerializer(serializers.Serializer):
    message = serializers.CharField()
    thinking = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    role = serializers.CharField(required=False, default="assistant")
    model = serializers.CharField(required=False, default="deepseek")
    url = serializers.CharField(required=False, allow_blank=True, default="")
    session_id = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")


class SystemPromptSerializer(serializers.Serializer):
    os = serializers.CharField(required=False, allow_blank=True, default=None)
    platform = serializers.CharField(required=False, allow_blank=True, default=None)
    shell = serializers.CharField(required=False, allow_blank=True, default=None)
    working_directory = serializers.CharField(required=False, allow_blank=True, default=None)
    repository = serializers.CharField(required=False, allow_blank=True, default=None)
    language_runtime = serializers.CharField(required=False, allow_blank=True, default=None)
    package_manager = serializers.CharField(required=False, allow_blank=True, default=None)
    has_tools = serializers.BooleanField(required=False, default=False)
    available_tools = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    custom_instructions = serializers.CharField(required=False, allow_blank=True, default="")


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = [
            "id",
            "session_id",
            "project_path",
            "project_name",
            "os",
            "shell",
            "system_prompt",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
