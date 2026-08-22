from openai import OpenAI
from django.conf import settings

_client = None


def get_client():
    """Load OpenAI API"""
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.ENV_OBJECT('OPENAI_API_KEY'))
    return _client
