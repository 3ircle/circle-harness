import os
import sys
from django.shortcuts import render
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from .models import ChatSession, ChatMessage
from .serializers import MessageSerializer, SystemPromptSerializer, ChatSessionSerializer
from utils_module.utils import genarate_system_prompt, build_system_prompt, get_default_environment

# Ensure stdout handles UTF-8 / Persian unicode safely across Windows terminals
try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


class MessageView(generics.GenericAPIView):
    serializer_class = MessageSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        message_text = data.get("message", "")
        thinking_text = data.get("thinking")
        role = data.get("role", "assistant")
        model = data.get("model", "deepseek")
        url = data.get("url", "")
        session_id = data.get("session_id") or ""

        # Link to ChatSession if exists
        chat_session = None
        if session_id:
            chat_session = ChatSession.objects.filter(session_id=session_id).first()

        # Persist message to database
        saved_msg = ChatMessage.objects.create(
            session=chat_session,
            session_slug=session_id,
            role=role,
            message=message_text,
            thinking=thinking_text,
            model=model,
            url=url,
        )

        # Print message clearly to terminal
        print("\n" + "=" * 70)
        print(f"📩 [New Message Received] (ID: #{saved_msg.id} | Session: {session_id or 'unknown'})")
        if thinking_text:
            print(f"\n🧠 [Thinking / Reasoning]:\n{thinking_text}")
        print(f"\n💬 [Message Content]:\n{message_text}")
        print("=" * 70 + "\n")

        return Response(
            {
                "status": "success",
                "message_id": saved_msg.id,
                "session_id": session_id,
                "saved": True,
            },
            status=status.HTTP_200_OK,
        )


class SystemPrompt(generics.GenericAPIView):
    serializer_class = SystemPromptSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            result = genarate_system_prompt(serializer.validated_data)
        else:
            result = genarate_system_prompt(request.data)
        return Response(result, status=status.HTTP_200_OK)

    def get(self, request, *args, **kwargs):
        result = genarate_system_prompt({})
        return Response(result, status=status.HTTP_200_OK)


class SessionDetailView(generics.GenericAPIView):
    """
    Checks if a session exists in the database by its session_id.
    GET /chat/sessions/<session_id>/
    """
    serializer_class = ChatSessionSerializer

    def get(self, request, session_id, *args, **kwargs):
        clean_id = session_id.strip()
        session = ChatSession.objects.filter(session_id=clean_id).first()

        if session:
            return Response(
                {
                    "exists": True,
                    "session": {
                        "session_id": session.session_id,
                        "project_path": session.project_path,
                        "project_name": session.project_name,
                        "os": session.os,
                        "shell": session.shell,
                        "system_prompt": session.system_prompt,
                        "created_at": session.created_at.isoformat(),
                    },
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "exists": False,
                "session_id": clean_id,
            },
            status=status.HTTP_200_OK,
        )


class SessionCreateOrUpdateView(generics.GenericAPIView):
    """
    Registers or updates a session with its project workspace.
    Generates tailored system prompt and saves it to the database.
    POST /chat/sessions/
    """
    serializer_class = ChatSessionSerializer

    def post(self, request, *args, **kwargs):
        data = request.data
        session_id = data.get("session_id", "").strip()

        if not session_id:
            return Response(
                {"error": "session_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        project_path = data.get("project_path", "").strip()
        project_name = data.get("project_name", "").strip()

        if not project_name and project_path:
            clean_path = os.path.normpath(project_path)
            project_name = os.path.basename(clean_path) or "project"

        defaults = get_default_environment()
        env_os = data.get("os") or defaults["os"]
        env_shell = data.get("shell") or defaults["shell"]

        # Build tailored system prompt for this project
        prompt_params = {
            "os": env_os,
            "shell": env_shell,
            "working_directory": project_path or defaults["working_directory"],
            "repository": project_name or defaults["repository"],
            "has_tools": False,
            "available_tools": [],
        }
        system_prompt = build_system_prompt(prompt_params)

        session, created = ChatSession.objects.update_or_create(
            session_id=session_id,
            defaults={
                "project_path": project_path,
                "project_name": project_name,
                "os": env_os,
                "shell": env_shell,
                "system_prompt": system_prompt,
            },
        )

        filename = f"{project_name or 'project'}_system_prompt.md"

        print(f"[ChatSession] {'Created' if created else 'Updated'} session '{session_id}' for project '{project_name}'")

        return Response(
            {
                "status": "created" if created else "updated",
                "exists": True,
                "session_id": session.session_id,
                "project_path": session.project_path,
                "project_name": session.project_name,
                "system_prompt": session.system_prompt,
                "filename": filename,
            },
            status=status.HTTP_200_OK,
        )
