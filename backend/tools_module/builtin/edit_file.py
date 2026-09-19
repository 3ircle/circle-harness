import os
from tools_module.base import BaseTool, ToolResult
from tools_module.permissions import ToolCategory
from tools_module.registry import register_tool


@register_tool
class EditFileTool(BaseTool):
    name = "edit_file"
    description = "Performs exact string replacement inside a file. Replaces `old_string` with `new_string`."
    category = ToolCategory.EDIT

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to edit."
            },
            "old_string": {
                "type": "string",
                "description": "Exact text to find and replace."
            },
            "new_string": {
                "type": "string",
                "description": "Text to replace it with."
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences instead of only the first one (default: false)."
            }
        },
        "required": ["file_path", "old_string", "new_string"]
    }

    example_call = {
        "tool": "edit_file",
        "params": {
            "file_path": "backend/core/settings.py",
            "old_string": "DEBUG = False",
            "new_string": "DEBUG = True"
        }
    }

    def execute(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> ToolResult:
        if not os.path.exists(file_path):
            return ToolResult(success=False, error=f"File not found: '{file_path}'")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if old_string not in content:
                return ToolResult(
                    success=False,
                    error=f"`old_string` was not found in '{file_path}'. Ensure exact character, whitespace, and line-break matching."
                )

            count = content.count(old_string)
            if not replace_all and count > 1:
                return ToolResult(
                    success=False,
                    error=f"`old_string` matches {count} times in '{file_path}'. Provide a more unique surrounding block or set `replace_all: true`."
                )

            if replace_all:
                new_content = content.replace(old_string, new_string)
                replaced_count = count
            else:
                new_content = content.replace(old_string, new_string, 1)
                replaced_count = 1

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult(
                success=True,
                output=f"Successfully edited '{file_path}' ({replaced_count} occurrence(s) replaced).",
                metadata={"file_path": file_path, "replacements": replaced_count}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to edit file: {str(e)}")
