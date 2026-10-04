from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.MessageView.as_view(), name='chat-message'),
    re_path(r'^system-?prompt/?$', views.SystemPrompt.as_view(), name='system-prompt'),
    re_path(r'^sessions/?$', views.SessionCreateOrUpdateView.as_view(), name='session-create'),
    re_path(r'^sessions/(?P<session_id>[\w\-]+)/worktree/status/?$', views.WorktreeStatusView.as_view(), name='worktree-status'),
    re_path(r'^sessions/(?P<session_id>[\w\-]+)/worktree/diff/?$', views.WorktreeDiffView.as_view(), name='worktree-diff'),
    re_path(r'^sessions/(?P<session_id>[\w\-]+)/worktree/merge/?$', views.WorktreeMergeView.as_view(), name='worktree-merge'),
    re_path(r'^sessions/(?P<session_id>[\w\-]+)/worktree/discard/?$', views.WorktreeDiscardView.as_view(), name='worktree-discard'),
    re_path(r'^sessions/(?P<session_id>[\w\-]+)/mode/?$', views.SessionModeUpdateView.as_view(), name='session-mode-update'),
    re_path(r'^sessions/(?P<session_id>[\w\-]+)/?$', views.SessionDetailView.as_view(), name='session-detail'),
    re_path(r'^tools/execute/?$', views.ToolExecuteView.as_view(), name='tool-execute'),
]
