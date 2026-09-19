from rest_framework import serializers


class MessageSerializer(serializers.Serializer):
    message = serializers.CharField()


class SystemPromptSerializer(serializers.Serializer):
    os = serializers.CharField(required=False, allow_blank=True, default=None)
    platform = serializers.CharField(required=False, allow_blank=True, default=None)
    shell = serializers.CharField(required=False, allow_blank=True, default=None)
    working_directory = serializers.CharField(required=False, allow_blank=True, default=None)
    repository = serializers.CharField(required=False, allow_blank=True, default=None)
    language_runtime = serializers.CharField(required=False, allow_blank=True, default=None)
    package_manager = serializers.CharField(required=False, allow_blank=True, default=None)
    has_tools = serializers.BooleanField(required=False, default=False)
    available_tools = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    custom_instructions = serializers.CharField(required=False, allow_blank=True, default="")
