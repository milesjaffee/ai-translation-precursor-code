from rest_framework import serializers


class AlignRequestSerializer(serializers.Serializer):
    source_lang = serializers.CharField(max_length=10)
    source = serializers.CharField()
    target_lang = serializers.CharField(max_length=10)
    target = serializers.CharField()
