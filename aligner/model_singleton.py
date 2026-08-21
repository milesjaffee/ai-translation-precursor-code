from llama_cpp import Llama
from openai import OpenAI
from instance import environment

_model, _client = None, None


def get_model():
    """Load the GGUF model once and cache it. Safe to call repeatedly --
    later calls just return the already-loaded instance."""
    global _model
    if _model is None:
        _model = Llama.from_pretrained(
            "LiquidAI/LFM2.5-2.6B-GGUF",
            device_map="auto",
            trust_remote_code=True,
            filename="*Q8_0.gguf",
            n_ctx=16384,
            n_gpu_layers=32,
            verbose=False,
        )
    return _model

def get_client():
    """Load OpenAI API"""
    global _client
    if _client is None:
        _client = OpenAI(api_key=environment.OPENAI_API_KEY)
    return _client
