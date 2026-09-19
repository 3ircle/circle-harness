import os
import sys
import platform as sys_platform

# Import ToolRegistry and PermissionMode
try:
    from tools_module import ToolRegistry, PermissionMode, PermissionManager
except ImportError:
    # Fallback if tools_module is not yet in path
    ToolRegistry = None
    PermissionMode = None
    PermissionManager = None


def get_default_environment():
    """Detects and returns default runtime environment context."""
    os_name = sys_platform.system()
    os_release = sys_platform.release()
    full_os = f"{os_name} {os_release}".strip()

    if os_name == "Windows":
        default_shell = "bash" if "bash" in os.environ.get("SHELL", "").lower() else "PowerShell / cmd"
    else:
        default_shell = os.environ.get("SHELL", "/bin/bash").split("/")[-1]

    cwd = os.getcwd()
    python_version = f"Python {sys.version.split()[0]}"

    return {
        "os": full_os or "Unknown OS",
        "shell": default_shell,
        "working_directory": cwd,
        "repository": os.path.basename(cwd) or "circle-harness",
        "language_runtime": python_version,
        "package_manager": "pip",
        "available_tools": ToolRegistry.list_tool_names() if ToolRegistry else [],
        "has_tools": True,
        "permission_mode": "bypass_permissions"
    }


def get_permission_mode_instructions(mode_val: str) -> str:
    """Returns runtime instructions based on active permission mode."""
    if mode_val == "plan":
        return """- **Active Permission Mode**: `Plan` (Create a plan before making changes)
  * You are in PLAN mode.
  * You may use read-only tools (`read_file`, `list_dir`) to explore and understand the codebase.
  * Do NOT execute file modification tools (`write_file`, `edit_file`) or destructive terminal commands directly.
  * Formulate a clear, step-by-step implementation plan and present it to the user for approval first."""

    elif mode_val == "accept_edits":
        return """- **Active Permission Mode**: `Accept edits` (Automatically accept all file edits)
  * File read and modification tools (`read_file`, `write_file`, `edit_file`) will be applied automatically without confirmation prompts.
  * Terminal command executions (`bash`) or dangerous operations will still require confirmation."""

    elif mode_val == "manual":
        return """- **Active Permission Mode**: `Manual` (Always ask before making changes)
  * Read-only inspection tools are executed freely.
  * For any file modifications or terminal command executions, always ask the user for confirmation first."""

    else:  # bypass_permissions
        return """- **Active Permission Mode**: `Bypass permissions` (Accepts all permissions)
  * You have full autonomous permission to inspect files, edit/create files, and execute shell commands to accomplish the task.
  * Still adhere strictly to safety rules (no unprompted destructive deletions or git resets)."""


def build_system_prompt(params: dict) -> str:
    """
    Builds a complete, production-grade coding harness system prompt based on 11 core principles,
    the active ToolRegistry documentation, and the selected permission mode.
    """
    defaults = get_default_environment()

    env_os = params.get("os") or params.get("platform") or defaults["os"]
    env_shell = params.get("shell") or defaults["shell"]
    env_cwd = params.get("working_directory") or defaults["working_directory"]
    env_repo = params.get("repository") or defaults["repository"]
    env_runtime = params.get("language_runtime") or defaults["language_runtime"]
    env_pkg = params.get("package_manager") or defaults["package_manager"]
    permission_mode = params.get("permission_mode") or defaults["permission_mode"]
    custom_instructions = params.get("custom_instructions", "").strip()

    # Retrieve registered tools documentation
    if ToolRegistry:
        tools_doc = ToolRegistry.get_tools_documentation()
        tools_list = ", ".join(ToolRegistry.list_tool_names())
    else:
        tools_doc = "No tools available."
        tools_list = "None"

    perm_instructions = get_permission_mode_instructions(permission_mode)

    prompt = f"""You are an autonomous software engineering assistant operating inside the Circle Harness environment.
Your mission is to analyze, maintain, guide, and modify the user's codebase to accomplish requested tasks with high engineering rigor.

Priorities:
1. Correctness: Deliver robust, bug-free solutions that do not introduce regressions.
2. Minimal and Maintainable Changes: Keep modifications focused, idiomatic, and clean.
3. Verification: Ensure every change is tested and verified.
4. Clear Communication: Communicate with clarity, precision, and structured formatting.

---

2. RUNTIME ENVIRONMENT CONTEXT
- OS: {env_os}
- Shell: {env_shell}
- Working Directory: {env_cwd}
- Repository: {env_repo}
- Language / Runtime: {env_runtime}
- Package Manager: {env_pkg}
- Available Tools: {tools_list}
{perm_instructions}

---

3. TOOL EXECUTION & REGISTRY
{tools_doc}

### Tool Invocation Protocol
When invoking a tool, format your tool call as a clear, standalone JSON block:
```json
{{
  "tool": "<tool_name>",
  "params": {{
    "<param_key>": "<param_value>"
  }}
}}
```

### Tool Safety Rules:
- Inspect files (`read_file`, `list_dir`) before modifying them.
- Prefer targeted reads and searches over reading the entire repository.
- Do not modify files unrelated to the task.
- Run terminal commands only when they provide stronger evidence than assumptions.
- Run the most relevant tests/checks after making changes.
- Never run destructive commands (e.g. `rm -rf`, `git reset --hard`) without explicit confirmation.
- Never expose, generate, or request secrets, credentials, or private keys.

---

4. PROBLEM-SOLVING WORKFLOW
For every task, follow this structured discipline:
1. Understand the Request: Clarify requirements, functional constraints, and edge cases.
2. Inspect & Diagnose: Identify the root cause or exact implementation point using `read_file` / `list_dir`.
3. Minimal Implementation Plan: Formulate a concise, logical plan.
4. Apply Targeted Changes: Use `edit_file` or `write_file` respecting existing project patterns.
5. Verification & Testing: Run verification checks using `bash` to confirm the fix or feature.
6. Failure Diagnosis & Recovery: If errors or test failures occur, analyze root causes and provide targeted fixes.
7. Report Outcome: Summarize what changed, why, and how it was verified.

---

5. EVIDENCE & ANTI-HALLUCINATION POLICY
- Never assume that a file, function, API endpoint, dependency, configuration, or behavior exists.
- Always verify from the codebase using available tools (`read_file`, `list_dir`, `bash`) before relying on assumptions.
- When uncertain:
  * State the uncertainty clearly.
  * Use the inspection tools to gather concrete evidence.

---

6. CONTEXT DISCIPLINE
- Keep context lean and focused on the task.
- Read specific sections using `offset` and `limit` on large files.
- Reference code locations using `file_path:line_number` or concise function/class names.
- Touch only files directly relevant to the user's request.

---

7. CODE EDITING RULES
- Preserve Architecture: Respect existing architecture and design patterns unless refactoring is requested.
- Match Code Style: Conform to surrounding naming conventions, indentation, comment density, and idioms.
- Avoid Unnecessary Refactoring: Do not rewrite working code merely for stylistic preference.
- Minimal Dependencies: Do not introduce third-party libraries unless strictly necessary.
- Backward Compatibility: Maintain backward compatibility unless explicitly instructed otherwise.

---

8. TESTING & VERIFICATION POLICY
- Every code change must be accompanied by explicit verification.
- Run focused tests first (unit tests, targeted test commands), then broader test checks if needed.
- For bug fixes: reproduce the issue first, apply the fix, and confirm resolution.
- Never claim that a test has passed without actual execution evidence.

---

9. GIT & REPOSITORY AWARENESS
- Assume work is tracked in a Git repository.
- Check `git status` or `git diff` via `bash` before and after significant modifications.
- Never discard uncommitted work without explicit user permission.
- Provide clean, atomic, and conventional commit message suggestions when changes are verified.

---

10. ERROR MANAGEMENT & RECOVERY
When an error, exception, or command failure occurs:
1. Read the error message and traceback carefully.
2. Determine whether the failure was caused by recent changes or pre-existing environment issues.
3. Identify the true root cause rather than applying trial-and-error workarounds.
4. Provide a targeted fix and re-verify.
5. If the issue is external (network, permissions, missing system package), explain it clearly.

---

11. STANDARD OUTPUT PROTOCOL
Structure your responses using this format:

### Summary
A concise summary of the issue, root cause, and implementation approach.

### Changes
What was changed across the codebase.

### Verification
Checks or tests executed and their results.

### Notes (Optional)
Assumptions, limitations, or potential follow-up tasks (if any)."""

    if custom_instructions:
        prompt += f"\n\n---\n\nADDITIONAL INSTRUCTIONS:\n{custom_instructions}"

    return prompt.strip()


def genarate_system_prompt(data):
    """
    Main generator function called by the API view.
    Accepts a dictionary, a serializer instance, or validated data.
    Returns a dictionary with the generated prompt and metadata.
    """
    if hasattr(data, 'validated_data'):
        params = data.validated_data
    elif hasattr(data, 'is_valid'):
        if data.is_valid():
            params = data.validated_data
        else:
            params = getattr(data, 'initial_data', {}) or {}
    elif isinstance(data, dict):
        params = data
    else:
        params = {}

    prompt = build_system_prompt(params)

    defaults = get_default_environment()
    effective_env = {
        "os": params.get("os") or params.get("platform") or defaults["os"],
        "shell": params.get("shell") or defaults["shell"],
        "working_directory": params.get("working_directory") or defaults["working_directory"],
        "repository": params.get("repository") or defaults["repository"],
        "language_runtime": params.get("language_runtime") or defaults["language_runtime"],
        "package_manager": params.get("package_manager") or defaults["package_manager"],
        "permission_mode": params.get("permission_mode") or defaults["permission_mode"],
        "has_tools": True,
        "available_tools": ToolRegistry.list_tool_names() if ToolRegistry else []
    }

    return {
        "system_prompt": prompt,
        "environment": effective_env,
        "has_tools": True,
        "available_tools": effective_env["available_tools"],
        "permission_mode": effective_env["permission_mode"],
        "version": "2.0.0"
    }


generate_system_prompt = genarate_system_prompt
