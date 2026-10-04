from django.db import models


class ChatSession(models.Model):
    """
    Represents a DeepSeek chat session linked to a local project workspace.
    """
    session_id = models.CharField(max_length=255, unique=True, db_index=True, verbose_name="Session ID")
    project_path = models.CharField(max_length=500, blank=True, default="", verbose_name="Project Path")
    project_name = models.CharField(max_length=255, blank=True, default="", verbose_name="Project Name")
    os = models.CharField(max_length=100, blank=True, default="", verbose_name="Operating System")
    shell = models.CharField(max_length=100, blank=True, default="", verbose_name="Shell")
    permission_mode = models.CharField(
        max_length=50,
        default="bypass_permissions",
        verbose_name="Permission Execution Mode"
    )
    system_prompt = models.TextField(blank=True, default="", verbose_name="Generated System Prompt")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    # Isolated Git Worktree Environment Fields
    is_worktree_enabled = models.BooleanField(
        default=False,
        verbose_name="Is Worktree Isolation Enabled"
    )
    worktree_path = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Worktree Directory Path"
    )
    worktree_branch = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Worktree Branch Name"
    )
    base_ref = models.CharField(
        max_length=255,
        blank=True,
        default="HEAD",
        verbose_name="Worktree Base Ref"
    )

    @property
    def effective_path(self) -> str:
        """
        Returns worktree_path if worktree isolation is active and the directory exists on disk,
        otherwise falls back to the main project_path.
        """
        import os
        if self.is_worktree_enabled and self.worktree_path and os.path.exists(self.worktree_path):
            return self.worktree_path
        return self.project_path

    class Meta:
        verbose_name = "Chat Session"
        verbose_name_plural = "Chat Sessions"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.project_name or 'Session'} ({self.session_id})"


class ChatMessage(models.Model):
    """
    Stores all messages exchanged within a chat session.
    """
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
        null=True,
        blank=True,
        verbose_name="Chat Session"
    )
    session_slug = models.CharField(max_length=255, db_index=True, blank=True, default="", verbose_name="Session Slug/ID")
    role = models.CharField(max_length=50, default="assistant", verbose_name="Role")
    message = models.TextField(verbose_name="Message Content")
    thinking = models.TextField(blank=True, null=True, verbose_name="Thinking / Reasoning")
    model = models.CharField(max_length=100, blank=True, default="deepseek", verbose_name="Model")
    url = models.CharField(max_length=500, blank=True, default="", verbose_name="URL")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = "Chat Message"
        verbose_name_plural = "Chat Messages"
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] {self.message[:50]}"
