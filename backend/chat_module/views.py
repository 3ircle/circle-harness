from django.shortcuts import render
from rest_framework import generics
from .serializers import MessageSerializer 
from rest_framework.response import Response
from rest_framework import status
# Create your views here.


class MessageView(generics.GenericAPIView):
    serializer_class = MessageSerializer
    
    def post(self, request, *args, **kwargs):
        print(self.request.data)
        return Response(status=status.HTTP_200_OK)
