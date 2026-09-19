import os
import fnmatch
from tools_module.base import BaseTool, ToolResult
from tools_module.permissions import ToolCategory
from tools_module.registry import register_tool


@register_tool
class ListDirectoryTool(BaseTool):
    name = "list_dir"
    description = "Lists files and subdirectories in a target directory with optional glob pattern filtering."
    category = ToolCategory.READ

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the directory to list (default: current working directory)."
            },
            "pattern": {
                "type": "string",
                "description": "Optional glob pattern to filter entries (e.g. '*.py', '*.json')."
            },
            "recursive": {
                "type": "boolean",
                "description": "Whether to list subdirectories recursively (default: false)."
            },
            "max_entries": {
                "type": "integer",
                "description": "Maximum number of entries to return (default: 200)."
            }
        }
    }

    example_call = {
        "tool": "list_dir",
        "params": {
            "path": "backend",
            "pattern": "*.py",
            "recursive": False
        }
    }

    def execute(self, path: str = ".", pattern: str = None, recursive: bool = False, max_entries: int = 200) -> ToolResult:
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"Directory path not found: '{path}'")

        if not os.path.isdir(path):
            return ToolResult(success=False, error=f"Path is a file, not a directory: '{path}'")

        entries = []
        try:
            if recursive:
                for root, dirs, files in os.walk(path):
                    # Skip common heavy dirs
                    dirs[:] = [d for d in dirs if d not in (".git", ".venv", "node_modules", "__pycache__", ".idea")]
                    for item in dirs + files:
                        rel_path = os.path.relpath(os.path.join(root, item), path)
                        if not pattern or fnmatch.fnmatch(item, pattern):
                            entries.append(rel_path)
                            if len(entries) >= max_entries:
                                break
                    if len(entries) >= max_entries:
                        break
            else:
                for item in sorted(os.listdir(path)):
                    if item.startswith(".") and item not in (".env", ".gitignore"):
                        continue
                    if not pattern or fnmatch.fnmatch(item, pattern):
                        is_dir = os.path.isdir(os.path.join(path, item))
                        entries.append(f"{item}/" if is_dir else item)
                        if len(entries) >= max_entries:
                            break

            output = "\n".join(entries) if entries else "(Directory is empty or no matches found)"
            return ToolResult(
                success=True,
                output=output,
                metadata={"total_found": len(entries), "path": path}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list directory: {str(e)}")
