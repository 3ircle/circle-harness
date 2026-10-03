import json
from django.test import TestCase, Client
from django.urls import reverse
from tools_module.permissions import PermissionManager, PermissionMode, ToolCategory
from chat_module.models import ChatSession, ChatMessage


class PermissionManagerTestCase(TestCase):
    def test_bypass_permissions_mode(self):
        res = PermissionManager.check_permission(ToolCategory.EXECUTE, PermissionMode.BYPASS_PERMISSIONS)
        self.assertTrue(res["allowed"])
        self.assertFalse(res["requires_approval"])

    def test_accept_edits_mode(self):
        # Read and Edit allowed automatically
        res_read = PermissionManager.check_permission(ToolCategory.READ, PermissionMode.ACCEPT_EDITS)
        self.assertTrue(res_read["allowed"])
        self.assertFalse(res_read["requires_approval"])

        res_edit = PermissionManager.check_permission(ToolCategory.EDIT, PermissionMode.ACCEPT_EDITS)
        self.assertTrue(res_edit["allowed"])
        self.assertFalse(res_edit["requires_approval"])

        # Execute requires approval
        res_exec = PermissionManager.check_permission(ToolCategory.EXECUTE, PermissionMode.ACCEPT_EDITS)
        self.assertTrue(res_exec["allowed"])
        self.assertTrue(res_exec["requires_approval"])

    def test_manual_mode(self):
        # Read allowed
        res_read = PermissionManager.check_permission(ToolCategory.READ, PermissionMode.MANUAL)
        self.assertTrue(res_read["allowed"])
        self.assertFalse(res_read["requires_approval"])

        # Edit and Execute require approval
        res_edit = PermissionManager.check_permission(ToolCategory.EDIT, PermissionMode.MANUAL)
        self.assertTrue(res_edit["requires_approval"])

        res_exec = PermissionManager.check_permission(ToolCategory.EXECUTE, PermissionMode.MANUAL)
        self.assertTrue(res_exec["requires_approval"])

    def test_plan_mode(self):
        # Read allowed automatically
        res_read = PermissionManager.check_permission(ToolCategory.READ, PermissionMode.PLAN)
        self.assertTrue(res_read["allowed"])
        self.assertFalse(res_read["requires_approval"])

        # Edit and Execute require user approval (not hard-blocked without approval prompt)
        res_edit = PermissionManager.check_permission(ToolCategory.EDIT, PermissionMode.PLAN)
        self.assertTrue(res_edit["requires_approval"])

        res_exec = PermissionManager.check_permission(ToolCategory.EXECUTE, PermissionMode.PLAN)
        self.assertTrue(res_exec["requires_approval"])


class MessageApprovalFlowTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.session = ChatSession.objects.create(
            session_id="test_session_123",
            project_path=".",
            project_name="test_proj",
            permission_mode="manual"
        )

    def test_tool_requires_approval_in_manual_mode(self):
        # When assistant tries to run bash in manual mode, it must require approval
        tool_call_msg = 'I need to check files.\n```json\n{"tool": "bash", "params": {"command": "echo test"}}\n```'
        payload = {
            "message": tool_call_msg,
            "session_id": "test_session_123",
            "role": "assistant"
        }
        response = self.client.post(
            "/chat/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("tool_execution", data)
        tool_exec = data["tool_execution"]
        self.assertIsNotNone(tool_exec)
        self.assertTrue(tool_exec["has_tool_call"])
        self.assertEqual(tool_exec["action"], "requires_approval")
        self.assertEqual(tool_exec["tool"], "bash")
        self.assertIn("command", tool_exec["params"])

    def test_manual_execution_via_execute_endpoint(self):
        # When user approves in UI, extension calls /chat/tools/execute/
        payload = {
            "session_id": "test_session_123",
            "tools": [{"tool": "bash", "params": {"command": "echo approved_run"}}]
        }
        response = self.client.post(
            "/chat/tools/execute/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("tool_result", data["chat_reply"])
        self.assertIn("approved_run", data["chat_reply"])

    def test_plan_mode_triggers_approval_instead_of_hard_block(self):
        # Create plan mode session
        plan_session = ChatSession.objects.create(
            session_id="test_plan_session",
            project_path=".",
            project_name="test_proj",
            permission_mode="plan"
        )
        tool_call_msg = 'Let me modify a file.\n```json\n{"tool": "write_file", "params": {"file_path": "sample.txt", "content": "hello"}}\n```'
        payload = {
            "message": tool_call_msg,
            "session_id": "test_plan_session",
            "role": "assistant"
        }
        response = self.client.post(
            "/chat/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("tool_execution", data)
        tool_exec = data["tool_execution"]
        # Must require approval in web UI, not blocked
        self.assertEqual(tool_exec["action"], "requires_approval")
        self.assertEqual(tool_exec["tool"], "write_file")
        self.assertEqual(tool_exec["mode"], "plan")

    def test_mixed_tools_batch_turn(self):
        # Assistant emits two tools: list_dir (safe read, auto-executed) and bash (requires approval)
        tool_call_msg = '''
```json
{"tool": "list_dir", "params": {"path": "."}}
```
```json
{"tool": "bash", "params": {"command": "echo batch_test"}}
```
'''
        payload = {
            "message": tool_call_msg,
            "session_id": "test_session_123",
            "role": "assistant"
        }
        response = self.client.post(
            "/chat/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        tool_exec = data["tool_execution"]
        self.assertEqual(tool_exec["action"], "requires_approval")
        self.assertEqual(len(tool_exec["approval_items"]), 1)
        self.assertEqual(tool_exec["approval_items"][0]["tool"], "bash")
        # Ensure list_dir was executed and stored in executed_so_far
        self.assertEqual(len(tool_exec["executed_so_far"]), 1)
        self.assertEqual(tool_exec["executed_so_far"][0]["tool"], "list_dir")

