import subprocess
from tools_module.base import BaseTool, ToolResult
from tools_module.permissions import ToolCategory
from tools_module.registry import register_tool


@register_tool
class BashTool(BaseTool):
    name = "bash"
    description = "Executes a shell command on the host system and returns stdout and stderr."
    category = ToolCategory.EXECUTE

    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command line to execute."
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 60)."
            },
            "cwd": {
                "type": "string",
                "description": "Working directory in which to execute the command."
            }
        },
        "required": ["command"]
    }

    example_call = {
        "tool": "bash",
        "params": {
            "command": "git status",
            "timeout": 30
        }
    }

    def execute(self, command: str, timeout: int = 60, cwd: str = None) -> ToolResult:
        if not command or not command.strip():
            return ToolResult(success=False, error="Command cannot be empty.")

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd
            )
            stdout, stderr = process.communicate(timeout=timeout)
            exit_code = process.returncode

            output = ""
            if stdout:
                output += stdout
            if stderr:
                if output:
                    output += "\n--- STDERR ---\n"
                output += stderr

            if not output:
                output = "(Command executed successfully with no output)"

            return ToolResult(
                success=(exit_code == 0),
                output=output,
                error=stderr if exit_code != 0 else None,
                metadata={"exit_code": exit_code, "command": command}
            )
        except subprocess.TimeoutExpired:
            process.kill()
            return ToolResult(
                success=False,
                error=f"Command timed out after {timeout} seconds: '{command}'"
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Command execution error: {str(e)}")
