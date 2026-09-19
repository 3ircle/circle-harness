from django.apps import AppConfig


class ToolsModuleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tools_module"
    verbose_name = "Tools Module"

    def ready(self):
        # Auto-import built-in tools to register them
        import tools_module.builtin
