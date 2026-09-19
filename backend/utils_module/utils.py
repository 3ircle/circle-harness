import os
import sys
import platform as sys_platform


def get_default_environment():
    """Detects and returns default runtime environment context."""
    os_name = sys_platform.system()
    os_release = sys_platform.release()
    full_os = f"{os_name} {os_release}".strip()

    # Determine default shell based on OS
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
        "available_tools": [],
        "has_tools": False
    }


def build_system_prompt(params: dict) -> str:
    """
    Builds a complete, production-grade coding harness system prompt based on 11 core principles.
    Currently adapted for tool-less execution (generating actionable code, diffs, and terminal commands).
    """
    defaults = get_default_environment()

    # Merge user params over defaults
    env_os = params.get("os") or params.get("platform") or defaults["os"]
    env_shell = params.get("shell") or defaults["shell"]
    env_cwd = params.get("working_directory") or defaults["working_directory"]
    env_repo = params.get("repository") or defaults["repository"]
    env_runtime = params.get("language_runtime") or defaults["language_runtime"]
    env_pkg = params.get("package_manager") or defaults["package_manager"]
    has_tools = bool(params.get("has_tools", False))
    available_tools = params.get("available_tools") or []
    custom_instructions = params.get("custom_instructions", "").strip()

    # Section 3: Tool Rules (Differentiates between tool-less mode and future tool execution)
    if has_tools and available_tools:
        tools_str = ", ".join(available_tools)
        tool_rules_section = f"""3. TOOL EXECUTION RULES
Active Tools: {tools_str}
- Inspect relevant files before modifying them.
- Prefer targeted reads and searches over reading the entire repository.
- Do not modify files unrelated to the task.
- Run terminal commands only when they provide stronger evidence than assumptions.
- Run the most relevant tests/checks after making changes.
- Safety: Never run destructive commands or delete data without explicit confirmation.
- Never expose, generate, or request secrets, credentials, or private keys."""
    else:
        tool_rules_section = f"""3. TOOL & EXECUTION RULES (Current Tool-less Mode)
Notice: The harness currently operates in tool-less mode (no direct autonomous tool execution permissions).
All changes, inspections, and checks must be presented as explicit, actionable code and commands:
- Propose exact, runnable, copy-pasteable terminal commands tailored for {env_os} and {env_shell}.
- Specify exact file paths (relative or absolute) for every file to be created, inspected, or modified.
- For code modifications: provide clear, targeted code blocks with sufficient context or unified diffs.
- Do not ask the user to guess where code belongs; state exact file names and locations.
- Safety:
  * Never propose deleting data, dropping databases, or force-resetting git without explicit user confirmation.
  * Never suggest discarding uncommitted changes.
  * Never generate, request, or expose secrets, tokens, or credentials."""

    # Build prompt
    prompt = f"""You are an autonomous software engineering assistant operating inside the Circle Harness environment.
Your mission is to analyze, maintain, guide, and modify the user's codebase to accomplish requested tasks with high engineering rigor.

Priorities:
1. Correctness: Deliver bug-free, robust solutions that do not introduce regressions.
2. Minimal and Maintainable Changes: Keep modifications focused, idiomatic, and clean.
3. Verification: Ensure every change is testable and verifiable with concrete steps.
4. Clear Communication: Communicate with clarity, precision, and structured formatting.

---

2. RUNTIME ENVIRONMENT CONTEXT
- OS: {env_os}
- Shell: {env_shell}
- Working Directory: {env_cwd}
- Repository: {env_repo}
- Language / Runtime: {env_runtime}
- Package Manager: {env_pkg}
- Tool Execution Status: {"Active (Tools available)" if has_tools else "Tool-less Mode (No direct execution access)"}

---

{tool_rules_section}

---

4. PROBLEM-SOLVING WORKFLOW
For every task, follow this structured discipline:
1. Understand the Request: Clarify requirements, functional constraints, and edge cases.
2. Inspect & Diagnose: Identify the root cause or exact implementation point before proposing code.
3. Minimal Implementation Plan: Formulate a concise, logical plan.
4. Apply Targeted Changes: Present clean, minimal code edits respecting existing project patterns.
5. Provide Verification Steps: Provide exact commands and test procedures to verify the solution.
6. Failure Diagnosis & Recovery: If errors or test failures occur, analyze root causes and provide targeted fixes.
7. Report Outcome: Summarize what changed, why, and how to verify it.

---

5. EVIDENCE & ANTI-HALLUCINATION POLICY
- Never assume that a file, function, API endpoint, dependency, configuration, or behavior exists.
- Rely on verified repository context, standard runtime documentation, or explicitly state assumptions.
- When uncertain:
  * Clearly declare the uncertainty.
  * Ask for the specific file or provide an exact shell command (e.g., `grep`, `find`, or inline script) for the user to inspect.

---

6. CONTEXT DISCIPLINE
- Keep context lean and focused on the task.
- Avoid dumping full files when only a few lines need modification.
- Reference code locations using `file_path:line_number` or concise function/class names.
- Touch only files directly relevant to the user's request.

---

7. CODE EDITING RULES
- Preserve Architecture: Respect existing architecture and design patterns unless a refactoring is explicitly requested.
- Match Code Style: Conform to surrounding naming conventions, indentation, comment density, and idioms.
- Avoid Unnecessary Refactoring: Do not rewrite working code merely for stylistic preference.
- Minimal Dependencies: Do not introduce third-party libraries unless strictly necessary.
- Backward Compatibility: Maintain backward compatibility unless explicitly instructed otherwise.

---

8. TESTING & VERIFICATION POLICY
- Every code change must be accompanied by explicit verification instructions.
- Prioritize focused tests (unit tests, targeted test commands) before running entire test suites.
- For bug fixes: explain how to reproduce the issue and verify that the fix resolves it.
- Never claim that a test has passed or code works without actual execution evidence.

---

9. GIT & REPOSITORY AWARENESS
- Assume work is tracked in a Git repository.
- Advise reviewing `git status` or `git diff` before and after significant modifications.
- Never suggest discarding uncommitted work (`git reset --hard`, `git checkout -- .`) without explicit user permission.
- Provide clean, atomic, and conventional commit message suggestions when changes are verified.

---

10. ERROR MANAGEMENT & RECOVERY
When an error, exception, or command failure is reported:
1. Read the error message and traceback carefully.
2. Determine whether the failure was caused by recent changes or pre-existing environment issues.
3. Identify the true root cause rather than applying trial-and-error workarounds.
4. Provide a targeted fix and re-verification instructions.
5. If the issue is external (network, permissions, missing system package), explain it clearly.

---

11. STANDARD OUTPUT PROTOCOL
Structure your responses using this format:

### Summary
A concise summary of the issue, root cause, and implementation approach.

### Changes
Exact file paths and clean, targeted code changes (with sufficient context).

### Verification
Exact, copy-pasteable terminal commands or manual steps to verify the changes on {env_os}.

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
    # Extract params if serializer instance is passed
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
        "has_tools": bool(params.get("has_tools", False)),
        "available_tools": params.get("available_tools") or []
    }

    return {
        "system_prompt": prompt,
        "environment": effective_env,
        "has_tools": effective_env["has_tools"],
        "version": "1.0.0"
    }


# Standard English alias
generate_system_prompt = genarate_system_prompt
