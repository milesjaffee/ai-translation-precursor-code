from django.views.generic import TemplateView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

import alignment_pipeline

from . import model_singleton
from .serializers import AlignRequestSerializer


class IndexView(TemplateView):
    template_name = 'aligner/index.html'


class AlignView(APIView):
    def post(self, request):
        serializer = AlignRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        model = model_singleton.get_model()
        try:
            result = alignment_pipeline.align_and_annotate(
                model,
                data['source'],
                data['target'],
                data['source_lang'],
                data['target_lang'],
            )
        except (AssertionError, ValueError) as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result)
