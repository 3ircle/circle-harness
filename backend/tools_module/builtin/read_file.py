import os
from tools_module.base import BaseTool, ToolResult
from tools_module.permissions import ToolCategory
from tools_module.registry import register_tool


@register_tool
class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Reads the content of a file from the local filesystem with optional line limits and line numbering."
    category = ToolCategory.READ

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute or relative path to the file to read."
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (1-indexed, default: 1)."
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read (default: 2000)."
            }
        },
        "required": ["file_path"]
    }

    example_call = {
        "tool": "read_file",
        "params": {
            "file_path": "backend/core/settings.py",
            "offset": 1,
            "limit": 50
        }
    }

    def execute(self, file_path: str, offset: int = 1, limit: int = 2000) -> ToolResult:
        if not os.path.exists(file_path):
            return ToolResult(success=False, error=f"File not found: '{file_path}'")

        if os.path.isdir(file_path):
            return ToolResult(success=False, error=f"Path is a directory, not a file: '{file_path}'")

        try:
            with open(file_path, "rb") as bf:
                raw_bytes = bf.read()

            # Detect encoding safely (handles UTF-16 LE from PowerShell, UTF-8 with BOM, etc.)
            encoding = "utf-8"
            if raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff") or b"\x00" in raw_bytes[:100]:
                encoding = "utf-16"
            elif raw_bytes.startswith(b"\xef\xbb\xbf"):
                encoding = "utf-8-sig"

            try:
                text_content = raw_bytes.decode(encoding)
            except Exception:
                text_content = raw_bytes.decode("utf-8", errors="replace")

            lines = text_content.splitlines(keepends=True)

            total_lines = len(lines)
            start_idx = max(0, offset - 1)
            end_idx = min(total_lines, start_idx + limit)

            selected_lines = lines[start_idx:end_idx]
            numbered = [f"{start_idx + i + 1}\t{line}" for i, line in enumerate(selected_lines)]
            content = "".join(numbered)

            return ToolResult(
                success=True,
                output=content,
                metadata={
                    "total_lines": total_lines,
                    "lines_returned": len(selected_lines),
                    "file_path": file_path,
                    "encoding": encoding
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to read file: {str(e)}")
