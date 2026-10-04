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


import os
import shutil
import tempfile
import subprocess
from utils_module.worktree import WorktreeManager, safe_rmtree


class WorktreeManagerTestCase(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Initialize a real git repo in temp_dir
        subprocess.run(["git", "init"], cwd=self.temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=self.temp_dir, capture_output=True, check=True)

        # Initial commit
        readme_path = os.path.join(self.temp_dir, "README.md")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("# Test Repo\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.temp_dir, capture_output=True, check=True)

    def tearDown(self):
        safe_rmtree(self.temp_dir)

    def test_is_git_repo(self):
        mgr = WorktreeManager(self.temp_dir, "sess_1")
        self.assertTrue(mgr.is_git_repo())

        # Test non-git directory
        non_git = tempfile.mkdtemp()
        try:
            non_mgr = WorktreeManager(non_git, "sess_non")
            self.assertFalse(non_mgr.is_git_repo())
        finally:
            safe_rmtree(non_git)

    def test_worktree_creation_and_isolation(self):
        session_id = "test_isolation_session"
        mgr = WorktreeManager(self.temp_dir, session_id)
        res = mgr.create_worktree()
        self.assertTrue(res["success"])
        self.assertTrue(os.path.exists(res["worktree_path"]))

        # Check gitignore was automatically updated
        gitignore_path = os.path.join(self.temp_dir, ".gitignore")
        self.assertTrue(os.path.exists(gitignore_path))
        with open(gitignore_path, "r", encoding="utf-8") as f:
            self.assertIn(".circle/", f.read())

        # Modify a file inside the isolated worktree
        isolated_file = os.path.join(res["worktree_path"], "new_feature.py")
        with open(isolated_file, "w", encoding="utf-8") as f:
            f.write("print('Isolated in worktree')\n")

        # Crucial check: the file MUST NOT exist in main repo!
        main_file = os.path.join(self.temp_dir, "new_feature.py")
        self.assertFalse(os.path.exists(main_file))

        # Check diff detects the new file
        diff_res = mgr.get_diff()
        self.assertTrue(diff_res["success"])
        self.assertIn("new_feature.py", diff_res["diff"])

        # Merge the worktree
        merge_res = mgr.merge_worktree(strategy="squash", commit_message="Merged isolated feature")
        self.assertTrue(merge_res["success"])

        # Now the file MUST exist in main repo after merge!
        self.assertTrue(os.path.exists(main_file))

        # And the worktree directory must be cleaned up
        self.assertFalse(os.path.exists(res["worktree_path"]))

    def test_discard_worktree(self):
        mgr = WorktreeManager(self.temp_dir, "discard_session")
        res = mgr.create_worktree()
        self.assertTrue(res["success"])
        self.assertTrue(os.path.exists(res["worktree_path"]))

        # Discard
        discard_res = mgr.discard_worktree(delete_branch=True)
        self.assertTrue(discard_res["success"])
        self.assertFalse(os.path.exists(res["worktree_path"]))


class WorktreeApiTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.temp_dir = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self.temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=self.temp_dir, capture_output=True, check=True)
        with open(os.path.join(self.temp_dir, "file.txt"), "w", encoding="utf-8") as f:
            f.write("Initial")
        subprocess.run(["git", "add", "file.txt"], cwd=self.temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.temp_dir, capture_output=True, check=True)

    def tearDown(self):
        safe_rmtree(self.temp_dir)

    def test_session_creation_with_worktree_and_tool_execution(self):
        session_id = "session_api_wt_test"
        payload = {
            "session_id": session_id,
            "project_path": self.temp_dir,
            "project_name": "test_repo",
            "is_worktree_enabled": True
        }
        res = self.client.post("/chat/sessions/", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["is_worktree_enabled"])
        self.assertTrue(os.path.exists(data["worktree_path"]))

        # Execute a tool call (write_file) via /chat/
        tool_call_msg = '```json\n{"tool": "write_file", "params": {"file_path": "isolated.py", "content": "x = 1"}}\n```'
        chat_res = self.client.post("/chat/", data=json.dumps({
            "message": tool_call_msg,
            "session_id": session_id,
            "role": "assistant"
        }), content_type="application/json")
        self.assertEqual(chat_res.status_code, 200)

        # Confirm file was written into worktree path, NOT main repo!
        file_in_worktree = os.path.join(data["worktree_path"], "isolated.py")
        file_in_main = os.path.join(self.temp_dir, "isolated.py")
        self.assertTrue(os.path.exists(file_in_worktree))
        self.assertFalse(os.path.exists(file_in_main))

        # Check status API
        status_res = self.client.get(f"/chat/sessions/{session_id}/worktree/status/")
        self.assertEqual(status_res.status_code, 200)
        self.assertTrue(status_res.json()["is_worktree_active"])

        # Check diff API
        diff_res = self.client.get(f"/chat/sessions/{session_id}/worktree/diff/")
        self.assertEqual(diff_res.status_code, 200)
        self.assertIn("isolated.py", diff_res.json()["diff"])

        # Merge API
        merge_res = self.client.post(f"/chat/sessions/{session_id}/worktree/merge/", data=json.dumps({
            "strategy": "squash"
        }), content_type="application/json")
        self.assertEqual(merge_res.status_code, 200)
        self.assertTrue(merge_res.json()["success"])

        # Now file MUST exist in main repo!
        self.assertTrue(os.path.exists(file_in_main))


