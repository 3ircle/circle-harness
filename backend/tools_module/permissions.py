from enum import Enum


class PermissionMode(str, Enum):
    MANUAL = "manual"
    ACCEPT_EDITS = "accept_edits"
    PLAN = "plan"
    BYPASS_PERMISSIONS = "bypass_permissions"

    @classmethod
    def get_choices(cls):
        return [
            (cls.MANUAL.value, "Manual - Always ask before making changes"),
            (cls.ACCEPT_EDITS.value, "Accept edits - Automatically accept all file edits"),
            (cls.PLAN.value, "Plan - Create a plan before making changes"),
            (cls.BYPASS_PERMISSIONS.value, "Bypass permissions - Accepts all permissions"),
        ]

    @classmethod
    def get_info(cls, mode_val: str):
        descriptions = {
            cls.MANUAL.value: {
                "title": "Manual",
                "description": "Always ask before making changes",
                "shortcut": "1",
            },
            cls.ACCEPT_EDITS.value: {
                "title": "Accept edits",
                "description": "Automatically accept all file edits",
                "shortcut": "2",
            },
            cls.PLAN.value: {
                "title": "Plan",
                "description": "Create a plan before making changes",
                "shortcut": "3",
            },
            cls.BYPASS_PERMISSIONS.value: {
                "title": "Bypass permissions",
                "description": "Accepts all permissions",
                "shortcut": "4",
            },
        }
        return descriptions.get(mode_val, descriptions[cls.BYPASS_PERMISSIONS.value])


class ToolCategory(str, Enum):
    READ = "read"          # Inspecting, reading, searching (safe)
    EDIT = "edit"          # Modifying, creating, writing files
    EXECUTE = "execute"    # Terminal/shell commands
    DANGEROUS = "dangerous"# File deletion, git reset, force overrides


class PermissionManager:
    """
    Evaluates whether a tool can be executed automatically or requires user confirmation.
    """

    @staticmethod
    def check_permission(category: ToolCategory, mode: PermissionMode = PermissionMode.BYPASS_PERMISSIONS):
        # 1. Bypass Permissions: Everything is allowed automatically
        if mode == PermissionMode.BYPASS_PERMISSIONS:
            return {
                "allowed": True,
                "requires_approval": False,
                "reason": "Bypass permissions mode active: all operations are permitted automatically."
            }

        # 2. Plan Mode: Read tools are allowed automatically; edits and executions require user confirmation
        if mode == PermissionMode.PLAN:
            if category == ToolCategory.READ:
                return {
                    "allowed": True,
                    "requires_approval": False,
                    "reason": "Plan mode: Read operations allowed automatically for investigation."
                }
            return {
                "allowed": True,
                "requires_approval": True,
                "reason": "حالت Plan: اجرای دستور یا تغییر فایل نیازمند تایید شما در وب است."
            }

        # 3. Accept Edits Mode: File edits allowed automatically, execute/dangerous requires approval
        if mode == PermissionMode.ACCEPT_EDITS:
            if category in (ToolCategory.READ, ToolCategory.EDIT):
                return {
                    "allowed": True,
                    "requires_approval": False,
                    "reason": "Accept edits mode: File read and edit operations accepted automatically."
                }
            return {
                "allowed": True,
                "requires_approval": True,
                "reason": "Accept edits mode: Terminal commands and dangerous operations require explicit approval."
            }

        # 4. Manual Mode: Read tools allowed; edits and executions always require approval
        if mode == PermissionMode.MANUAL:
            if category == ToolCategory.READ:
                return {
                    "allowed": True,
                    "requires_approval": False,
                    "reason": "Manual mode: Read operations allowed."
                }
            return {
                "allowed": True,
                "requires_approval": True,
                "reason": "Manual mode: Any changes or command executions require user confirmation."
            }

        return {
            "allowed": True,
            "requires_approval": False,
            "reason": "Default permitted."
        }
