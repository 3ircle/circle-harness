import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from .permissions import ToolCategory


class ToolResult:
    """Represents the outcome of a tool execution."""

    def __init__(self, success: bool, output: Any = None, error: Optional[str] = None, metadata: Optional[Dict] = None):
        self.success = success
        self.output = output
        self.error = error
        self.metadata = metadata or {}

    def to_dict(self):
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }

    def __repr__(self):
        return f"<ToolResult success={self.success} output={str(self.output)[:60]} error={self.error}>"


class BaseTool(ABC):
    """
    Abstract Base Class for all Harness Tools.
    Every tool must declare its name, description, parameters schema, and category.
    """

    name: str = ""
    description: str = ""
    category: ToolCategory = ToolCategory.READ
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Executes the tool with given arguments and returns a ToolResult."""
        pass

    def get_documentation(self) -> str:
        """
        Generates clean Markdown documentation for this tool to be included in the system prompt.
        """
        props = self.parameters.get("properties", {})
        required = self.parameters.get("required", [])

        doc_lines = [
            f"### `{self.name}`",
            f"- **Description**: {self.description}",
            f"- **Category**: {self.category.value}",
            "- **Parameters**:",
        ]

        if not props:
            doc_lines.append("  * No parameters required.")
        else:
            for prop_name, prop_data in props.items():
                p_type = prop_data.get("type", "string")
                p_desc = prop_data.get("description", "")
                is_req = "(Required)" if prop_name in required else "(Optional)"
                doc_lines.append(f"  * `{prop_name}` ({p_type}, {is_req}): {p_desc}")

        example = getattr(self, "example_call", None)
        if example:
            doc_lines.append("- **Example**:")
            doc_lines.append(f"```json\n{json.dumps(example, indent=2, ensure_ascii=False)}\n```")

        return "\n".join(doc_lines)
