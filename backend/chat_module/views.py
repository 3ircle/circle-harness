import os
import sys
import json
from django.shortcuts import render
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from .models import ChatSession, ChatMessage
from .serializers import MessageSerializer, SystemPromptSerializer, ChatSessionSerializer
from utils_module.utils import genarate_system_prompt, build_system_prompt, get_default_environment
from tools_module import ToolRegistry, PermissionMode, PermissionManager
from tools_module.parser import parse_tool_calls

# Ensure stdout handles UTF-8 / Persian unicode safely across Windows terminals
try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def resolve_session_and_project_path(session_id: str, client_project_path: str = ""):
    """
    Finds ChatSession by session_id, or auto-binds new DeepSeek UUID to the most recent session,
    or falls back to client_project_path / the latest configured workspace.
    Returns (chat_session, project_path, permission_mode).
    """
    chat_session = None
    if session_id:
        chat_session = ChatSession.objects.filter(session_id=session_id).first()

    if not chat_session:
        # Check if there is a recent session
        recent = ChatSession.objects.exclude(project_path="").order_by("-updated_at").first()
        if recent:
            if session_id and not session_id.startswith("session_"):
                # Auto-bind this new real DeepSeek UUID to the existing session!
                recent.session_id = session_id
                if client_project_path:
                    recent.project_path = client_project_path
                    recent.project_name = os.path.basename(os.path.normpath(client_project_path)) or recent.project_name
                recent.save()
                chat_session = recent
                print(f"🔗 [Auto-Bound Session] Linked DeepSeek UUID '{session_id}' -> Project '{recent.project_name}' ({recent.project_path})")
            else:
                chat_session = recent

    project_path = ""
    if chat_session and chat_session.project_path:
        project_path = chat_session.project_path
    elif client_project_path:
        project_path = client_project_path
    else:
        last = ChatSession.objects.exclude(project_path="").order_by("-updated_at").first()
        if last:
            project_path = last.project_path

    mode = chat_session.permission_mode if chat_session else "bypass_permissions"
    return chat_session, project_path, mode


def resolve_tool_params(tool_name: str, params: dict, project_path: str) -> dict:
    """
    Ensures file paths and bash cwd strictly resolve against the session's local project_path.
    """
    resolved = dict(params or {})
    if not project_path:
        return resolved

    if tool_name == "bash":
        if "cwd" not in resolved or not resolved["cwd"] or resolved["cwd"] == ".":
            resolved["cwd"] = project_path
    elif tool_name == "list_dir":
        p = resolved.get("path", ".")
        if not p or p == ".":
            resolved["path"] = project_path
        elif not os.path.isabs(p):
            resolved["path"] = os.path.normpath(os.path.join(project_path, p))
    elif tool_name in ("read_file", "write_file", "edit_file"):
        fp = resolved.get("file_path")
        if fp and not os.path.isabs(fp):
            resolved["file_path"] = os.path.normpath(os.path.join(project_path, fp))

    return resolved


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
        client_project_path = data.get("project_path") or ""

        chat_session, project_path, mode = resolve_session_and_project_path(session_id, client_project_path)

        saved_msg = ChatMessage.objects.create(
            session=chat_session,
            session_slug=session_id,
            role=role,
            message=message_text,
            thinking=thinking_text,
            model=model,
            url=url,
        )

        print("\n" + "=" * 70)
        print(f"📩 [New Message Received] (ID: #{saved_msg.id} | Session: {session_id or 'unknown'})")
        if thinking_text:
            print(f"\n🧠 [Thinking / Reasoning]:\n{thinking_text}")
        print(f"\n💬 [Message Content]:\n{message_text}")
        print("=" * 70 + "\n")

        # Parse potential tool calls from message
        tool_calls = parse_tool_calls(message_text)
        tool_execution_info = None

        if tool_calls:
            tc = tool_calls[0]
            tool_name = tc.get("tool", "")
            raw_params = tc.get("params", {})

            # Ensure all paths and cwd resolve against project_path
            params = resolve_tool_params(tool_name, raw_params, project_path)
            print(f"🔧 [Tool Call Detected] Tool: '{tool_name}' | Project Path: '{project_path}' | Params: {params}")

            tool_obj = ToolRegistry.get(tool_name) if ToolRegistry else None
            if not tool_obj:
                err_msg = f"Tool '{tool_name}' is not registered. Available: {ToolRegistry.list_tool_names() if ToolRegistry else []}"
                chat_reply = f"```json\n{{\n  \"tool_result\": {{\n    \"tool\": \"{tool_name}\",\n    \"success\": false,\n    \"error\": \"{err_msg}\"\n  }}\n}}\n```"
                tool_execution_info = {
                    "has_tool_call": True,
                    "action": "executed",
                    "tool": tool_name,
                    "params": params,
                    "chat_reply": chat_reply
                }
            else:
                perm_check = PermissionManager.check_permission(tool_obj.category, PermissionMode(mode))

                if not perm_check["allowed"]:
                    # Permission completely blocked by mode (e.g. Plan mode forbids edits directly)
                    reason = perm_check["reason"]
                    print(f"🚫 [Tool Blocked] '{tool_name}' in '{mode}' mode: {reason}")
                    chat_reply = f"```json\n{{\n  \"tool_result\": {{\n    \"tool\": \"{tool_name}\",\n    \"success\": false,\n    \"error\": \"{reason}\"\n  }}\n}}\n```"
                    tool_execution_info = {
                        "has_tool_call": True,
                        "action": "executed",
                        "tool": tool_name,
                        "params": params,
                        "chat_reply": chat_reply,
                        "blocked": True,
                        "reason": reason
                    }
                elif perm_check["requires_approval"]:
                    # Requires user approval! Send approval request to extension UI
                    print(f"⚠️ [Tool Requires Approval] '{tool_name}' in '{mode}' mode: {perm_check['reason']}")
                    tool_execution_info = {
                        "has_tool_call": True,
                        "action": "requires_approval",
                        "tool": tool_name,
                        "params": params,
                        "reason": perm_check["reason"],
                        "mode": mode
                    }
                else:
                    # Allowed automatically (e.g. bypass_permissions or safe reads)
                    print(f"⚡ [Executing Tool Automatically] '{tool_name}' (Mode: {mode}) with params: {params}")
                    exec_res = ToolRegistry.execute_tool(tool_name, params, mode=mode)
                    reply_dict = {
                        "tool_result": {
                            "tool": tool_name,
                            "success": exec_res.success,
                            "output": exec_res.output,
                            "error": exec_res.error
                        }
                    }
                    chat_reply = f"```json\n{json.dumps(reply_dict, indent=2, ensure_ascii=False)}\n```"
                    print(f"✅ [Tool Result] Success: {exec_res.success} | Output length: {len(str(exec_res.output))}")
                    tool_execution_info = {
                        "has_tool_call": True,
                        "action": "executed",
                        "tool": tool_name,
                        "params": params,
                        "result": exec_res.to_dict(),
                        "chat_reply": chat_reply
                    }

        response_data = {
            "status": "success",
            "message_id": saved_msg.id,
            "session_id": session_id,
            "saved": True,
            "tool_execution": tool_execution_info
        }

        return Response(response_data, status=status.HTTP_200_OK)


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
                        "permission_mode": session.permission_mode,
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
    Registers or updates a session with its project workspace and permission mode.
    Generates tailored system prompt with tools documentation and saves to DB.
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
        permission_mode = data.get("permission_mode", "bypass_permissions").strip()

        if not project_name and project_path:
            clean_path = os.path.normpath(project_path)
            project_name = os.path.basename(clean_path) or "project"

        defaults = get_default_environment()
        env_os = data.get("os") or defaults["os"]
        env_shell = data.get("shell") or defaults["shell"]

        prompt_params = {
            "os": env_os,
            "shell": env_shell,
            "working_directory": project_path or defaults["working_directory"],
            "repository": project_name or defaults["repository"],
            "permission_mode": permission_mode,
            "has_tools": True,
        }
        system_prompt = build_system_prompt(prompt_params)

        session, created = ChatSession.objects.update_or_create(
            session_id=session_id,
            defaults={
                "project_path": project_path,
                "project_name": project_name,
                "os": env_os,
                "shell": env_shell,
                "permission_mode": permission_mode,
                "system_prompt": system_prompt,
            },
        )

        filename = f"{project_name or 'project'}_system_prompt.md"

        print(f"[ChatSession] {'Created' if created else 'Updated'} session '{session_id}' for project '{project_name}' (Mode: {permission_mode})")

        return Response(
            {
                "status": "created" if created else "updated",
                "exists": True,
                "session_id": session.session_id,
                "project_path": session.project_path,
                "project_name": session.project_name,
                "permission_mode": session.permission_mode,
                "system_prompt": session.system_prompt,
                "filename": filename,
            },
            status=status.HTTP_200_OK,
        )


class SessionModeUpdateView(generics.GenericAPIView):
    """
    Updates the permission execution mode of an existing session.
    POST /chat/sessions/<session_id>/mode/
    """

    def post(self, request, session_id, *args, **kwargs):
        mode = request.data.get("mode", "bypass_permissions")
        session = ChatSession.objects.filter(session_id=session_id.strip()).first()

        if not session:
            return Response({"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND)

        session.permission_mode = mode

        # Rebuild prompt with new mode
        defaults = get_default_environment()
        prompt_params = {
            "os": session.os or defaults["os"],
            "shell": session.shell or defaults["shell"],
            "working_directory": session.project_path or defaults["working_directory"],
            "repository": session.project_name or defaults["repository"],
            "permission_mode": mode,
            "has_tools": True,
        }
        session.system_prompt = build_system_prompt(prompt_params)
        session.save()

        print(f"[ChatSession] Switched mode to '{mode}' for session '{session_id}'")

        return Response(
            {
                "success": True,
                "session_id": session.session_id,
                "permission_mode": session.permission_mode,
                "system_prompt": session.system_prompt,
            },
            status=status.HTTP_200_OK,
        )


class ToolExecuteView(generics.GenericAPIView):
    """
    Executes a tool on the host under the session's permission mode and project workspace.
    POST /chat/tools/execute/
    Payload: { "tool": "read_file", "params": {...}, "session_id": "...", "project_path": "..." }
    """

    def post(self, request, *args, **kwargs):
        tool_name = request.data.get("tool")
        raw_params = request.data.get("params", {})
        session_id = request.data.get("session_id", "")
        client_project_path = request.data.get("project_path", "")

        chat_session, project_path, mode = resolve_session_and_project_path(session_id, client_project_path)
        params = resolve_tool_params(tool_name, raw_params, project_path)

        print(f"⚡ [Manual Execution Approved] Tool: '{tool_name}' | Project: '{project_path}' | Params: {params}")

        result = ToolRegistry.execute_tool(tool_name, params, mode=mode)
        return Response(result.to_dict(), status=status.HTTP_200_OK)
