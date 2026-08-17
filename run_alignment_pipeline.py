import alignment_pipeline
from llama_cpp import Llama
import time

checkpoint = "LiquidAI/LFM2.5-2.6B-GGUF"
model = Llama.from_pretrained(checkpoint, device_map="auto", trust_remote_code=True, filename="*Q8_0.gguf", n_ctx=16384, n_gpu_layers=32, verbose=False)

annotation_request_istanbul_wikipedia = {
    "source_lang":"en",
    "source":"""Istanbul is the largest city in Turkey, a megacity, constituting the country's economic, cultural, and historical center. 
        With a population of over 15 million, it is home to 18% of the population of Turkey. Istanbul is among the largest cities in Europe and in the world by population. 
        It is a city on two continents; about two-thirds of its population live in Europe and the rest in Asia. 
        Istanbul straddles the Bosphorus – one of the world's busiest waterways – in northwestern Turkey, between the Sea of Marmara and the Black Sea. 
        Its area of 5,461 square kilometers is coterminous with Istanbul Province.
        """,
    "target_lang":"es",
    "translation":"""Estambul es la ciudad más grande de Turquía, una megaciudad que constituye el centro económico, cultural e histórico del país. 
        Con una población de más de 15 millones, alberga al 18% de la población de Turquía. Estambul se encuentra entre las ciudades más grandes de Europa y del mundo por población. 
        Es una ciudad en dos continentes; aproximadamente dos tercios de su población viven en Europa y el resto en Asia. 
        Estambul se extiende a lo largo del Bósforo, uno de los canales más transitados del mundo, en el noroeste de Turquía, entre el Mar de Mármara y el Mar Negro. 
        Su área de 5,461 kilómetros cuadrados es coterminosa con la Provincia de Estambul.
        """,
}

print(alignment_pipeline.align_document(
    model,
    annotation_request_istanbul_wikipedia["source"],
    annotation_request_istanbul_wikipedia["translation"],
    annotation_request_istanbul_wikipedia["source_lang"],
    annotation_request_istanbul_wikipedia["target_lang"]
))