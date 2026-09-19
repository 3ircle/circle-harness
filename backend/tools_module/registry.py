from typing import Dict, List, Optional, Type
from .base import BaseTool, ToolResult
from .permissions import PermissionManager, PermissionMode, ToolCategory


class ToolRegistry:
    """
    Central Registry for all tools in Circle Harness.
    """

    _tools: Dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool_cls_or_instance):
        """Registers a tool class or instance."""
        if isinstance(tool_cls_or_instance, type) and issubclass(tool_cls_or_instance, BaseTool):
            instance = tool_cls_or_instance()
        elif isinstance(tool_cls_or_instance, BaseTool):
            instance = tool_cls_or_instance
        else:
            raise TypeError("Tool must be an instance or subclass of BaseTool")

        if not instance.name:
            raise ValueError(f"Tool {tool_cls_or_instance} must define a unique 'name'")

        cls._tools[instance.name] = instance
        return tool_cls_or_instance

    @classmethod
    def get(cls, name: str) -> Optional[BaseTool]:
        return cls._tools.get(name)

    @classmethod
    def get_all(cls) -> Dict[str, BaseTool]:
        return dict(cls._tools)

    @classmethod
    def list_tool_names(cls) -> List[str]:
        return list(cls._tools.keys())

    @classmethod
    def get_tools_documentation(cls) -> str:
        """
        Compiles the full documentation of all registered tools for the system prompt.
        """
        if not cls._tools:
            return "No tools currently registered in the registry."

        docs = [
            "## AVAILABLE TOOLS REGISTRY",
            "You have access to the following tools. Always format your tool requests accurately:\n"
        ]

        # Group by category
        categories = {
            ToolCategory.READ: "### [Read-Only] File & Repository Inspection",
            ToolCategory.EDIT: "### [Edit/Write] Code & File Modification",
            ToolCategory.EXECUTE: "### [Execute] Terminal & Shell Commands",
            ToolCategory.DANGEROUS: "### [Dangerous] System Operations"
        }

        for cat, header in categories.items():
            cat_tools = [t for t in cls._tools.values() if t.category == cat]
            if cat_tools:
                docs.append(header)
                for tool in cat_tools:
                    docs.append(tool.get_documentation())
                    docs.append("")  # Empty line

        return "\n".join(docs).strip()

    @classmethod
    def execute_tool(cls, name: str, params: dict, mode: str = PermissionMode.BYPASS_PERMISSIONS.value) -> ToolResult:
        """
        Checks permission against the specified mode and executes the tool.
        """
        tool = cls.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' is not registered in ToolRegistry. Available tools: {cls.list_tool_names()}"
            )

        # Check permissions
        perm_check = PermissionManager.check_permission(tool.category, PermissionMode(mode))
        if not perm_check["allowed"]:
            return ToolResult(
                success=False,
                error=f"Permission Denied in '{mode}' mode: {perm_check['reason']}",
                metadata={"permission_denied": True, "requires_approval": perm_check["requires_approval"]}
            )

        if perm_check["requires_approval"]:
            return ToolResult(
                success=False,
                error=f"Permission Approval Required: {perm_check['reason']}",
                metadata={"requires_approval": True, "tool_name": name, "params": params}
            )

        try:
            return tool.execute(**params)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Tool execution failed with exception: {str(e)}"
            )


# Decorator for easy tool registration
def register_tool(cls):
    return ToolRegistry.register(cls)
