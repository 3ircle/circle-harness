from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.MessageView.as_view(), name='chat-message'),
    re_path(r'^system-?prompt/?$', views.SystemPrompt.as_view(), name='system-prompt'),
]
