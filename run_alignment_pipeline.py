import alignment_pipeline
from llama_cpp import Llama
import time

checkpoint = "unsloth/gemma-4-12B-it-qat-GGUF"
model = Llama.from_pretrained(checkpoint, device_map="auto", trust_remote_code=True, filename="*UD-Q4_K_XL.gguf", n_ctx=16382, n_batch=512, n_gpu_layers=32, verbose=False)

annotation_request_choir_wikipedia = {
    "source_lang":"en",
    "source":"""Choirs are often led by a conductor, choirmaster or choir director. 
    Most often, choirs consist of four sections intended to sing in four-part harmony, 
    but there is no limit to the number of possible parts as long as there is a singer available to sing the part. 
    For instance, Thomas Tallis wrote a 40-part motet for eight choirs of five parts each.
        """,
    "target_lang":"es",
    "translation":"""Los coros suelen estar dirigidos por un director de orquesta, maestro de coro o director coral.
Generalmente, los coros constan de cuatro secciones destinadas a cantar a cuatro voces,
pero no hay límite en el número de voces posibles, siempre que haya un cantante disponible para interpretarlas.
Por ejemplo, Thomas Tallis compuso un motete de 40 voces para ocho coros de cinco voces cada uno.
        """,
}

print(alignment_pipeline.align_and_annotate(
    model,
    annotation_request_choir_wikipedia["source"],
    annotation_request_choir_wikipedia["translation"],
    annotation_request_choir_wikipedia["source_lang"],
    annotation_request_choir_wikipedia["target_lang"]
))