from django.shortcuts import render
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from .serializers import MessageSerializer, SystemPromptSerializer
from utils_module.utils import genarate_system_prompt


class MessageView(generics.GenericAPIView):
    serializer_class = MessageSerializer

    def post(self, request, *args, **kwargs):
        print('chat got a message:')
        print(self.request.data)
        return Response(status=status.HTTP_200_OK)


class SystemPrompt(generics.GenericAPIView):
    serializer_class = SystemPromptSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            result = genarate_system_prompt(serializer.validated_data)
        else:
            result = genarate_system_prompt(request.data)
        return Response(result, status=status.HTTP_200_OK)

    def get(self, request, *args, **kwargs):
        result = genarate_system_prompt({})
        return Response(result, status=status.HTTP_200_OK)
