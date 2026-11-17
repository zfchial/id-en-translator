from contextlib import asynccontextmanager
from pathlib import Path
import gc
import os
import re
import threading
import time

import ctranslate2
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from transformers import MarianTokenizer

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = Path(os.environ.get("MODEL_DIR", BASE_DIR / "models" / "opus-mt-id-en-ct2"))
CPU_THREADS = max(1, int(os.environ.get("CPU_THREADS", "2")))
IDLE_UNLOAD_SECONDS = max(30, int(os.environ.get("IDLE_UNLOAD_SECONDS", "120")))
MODEL_NAME = "Helsinki-NLP/opus-mt-id-en"

model_lock = threading.Lock()
tokenizer = None
translator = None
last_active = 0.0
reaper_stop = threading.Event()


@asynccontextmanager
async def lifespan(application):
    reaper_stop.clear()
    thread = threading.Thread(target=unload_when_idle, name="model-idle-reaper", daemon=True)
    thread.start()
    yield
    reaper_stop.set()
    thread.join(timeout=2)
    unload_model()


app = FastAPI(title="Alih — Terjemah ID → EN", version="1.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class TranslationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


def load_model():
    global tokenizer, translator
    if tokenizer is not None and translator is not None:
        return
    if not MODEL_DIR.exists():
        raise FileNotFoundError(f"Model tidak ditemukan di {MODEL_DIR}")
    loaded_tokenizer = MarianTokenizer.from_pretrained(str(MODEL_DIR), local_files_only=True)
    loaded_translator = ctranslate2.Translator(
        str(MODEL_DIR),
        device="cpu",
        inter_threads=1,
        intra_threads=CPU_THREADS,
        compute_type="int8",
    )
    tokenizer = loaded_tokenizer
    translator = loaded_translator


def unload_model():
    global tokenizer, translator
    with model_lock:
        old_translator = translator
        old_tokenizer = tokenizer
        translator = None
        tokenizer = None
        del old_translator, old_tokenizer
        gc.collect()


def unload_when_idle():
    while not reaper_stop.wait(15):
        if not model_lock.acquire(blocking=False):
            continue
        try:
            if translator is not None and time.monotonic() - last_active >= IDLE_UNLOAD_SECONDS:
                globals()["translator"] = None
                globals()["tokenizer"] = None
                gc.collect()
        finally:
            model_lock.release()


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index-modern.html")


@app.get("/api/health")
def health():
    if not model_lock.acquire(timeout=0.2):
        return {"status": "working", "model": MODEL_NAME, "idle_unload_seconds": IDLE_UNLOAD_SECONDS}
    try:
        status = "ready" if translator is not None else "sleeping"
    finally:
        model_lock.release()
    return {"status": status, "model": MODEL_NAME, "idle_unload_seconds": IDLE_UNLOAD_SECONDS}


@app.post("/api/translate")
def translate(payload: TranslationRequest):
    global last_active
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Teks tidak boleh kosong.")
    try:
        with model_lock:
            load_model()
            last_active = time.monotonic()
            sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
            translated = []
            for start in range(0, len(sentences), 8):
                batch = sentences[start:start + 8]
                tokens = [tokenizer.convert_ids_to_tokens(tokenizer.encode(sentence)) for sentence in batch]
                results = translator.translate_batch(tokens, beam_size=2, max_decoding_length=512)
                translated.extend(
                    tokenizer.decode(tokenizer.convert_tokens_to_ids(result.hypotheses[0]), skip_special_tokens=True)
                    for result in results
                )
            last_active = time.monotonic()
            return {"translation": " ".join(translated), "source": text}
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="File model belum tersedia di server.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Translasi gagal: {type(exc).__name__}") from exc
