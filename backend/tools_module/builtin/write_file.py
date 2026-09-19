import os
from tools_module.base import BaseTool, ToolResult
from tools_module.permissions import ToolCategory
from tools_module.registry import register_tool


@register_tool
class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Creates a new file or completely overwrites an existing file with the provided content."
    category = ToolCategory.EDIT

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to create or overwrite."
            },
            "content": {
                "type": "string",
                "description": "Full text content to write into the file."
            }
        },
        "required": ["file_path", "content"]
    }

    example_call = {
        "tool": "write_file",
        "params": {
            "file_path": "example.py",
            "content": "print('Hello world!')\n"
        }
    }

    def execute(self, file_path: str, content: str) -> ToolResult:
        try:
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                success=True,
                output=f"File successfully written: '{file_path}' ({len(content)} characters)",
                metadata={"file_path": file_path, "bytes": len(content.encode("utf-8"))}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to write file: {str(e)}")
