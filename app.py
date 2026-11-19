from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple
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
CPU_THREADS = max(1, int(os.environ.get("CPU_THREADS", "2")))
IDLE_UNLOAD_SECONDS = max(30, int(os.environ.get("IDLE_UNLOAD_SECONDS", "120")))

DIRECTIONS = {
    "id-en": {
        "model_dir": Path(os.environ.get("MODEL_DIR_ID_EN", BASE_DIR / "models" / "opus-mt-id-en-ct2")),
        "model_name": "Helsinki-NLP/opus-mt-id-en",
    },
    "en-id": {
        "model_dir": Path(os.environ.get("MODEL_DIR_EN_ID", BASE_DIR / "models" / "opus-mt-en-id-ct2")),
        "model_name": "Helsinki-NLP/opus-mt-en-id",
    },
}

state_lock = threading.Lock()
loaded: Dict[str, Tuple[Optional[MarianTokenizer], Optional[ctranslate2.Translator]]] = {
    key: (None, None) for key in DIRECTIONS
}
last_active = 0.0
reaper_stop = threading.Event()

ID_MARKERS = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "untuk", "dengan", "tidak",
    "saya", "kamu", "kami", "kita", "mereka", "adalah", "akan", "sudah", "belum",
    "bisa", "juga", "saja", "karena", "tetapi", "tapi", "pada", "dalam", "oleh",
    "ada", "banyak", "bagaimana", "mengapa", "kenapa", "siapa", "kapan", "dimana",
    "orang", "rumah", "makanan", "uang", "kerja", "sekolah", "hari", "waktu",
    "tahun", "bulan", "minggu", "anak", "ibu", "bapak", "sedang", "masih", "harus",
    "mau", "ingin", "perlu", "sangat", "sekali", "lagi", "lebih", "paling", "nya",
}
EN_MARKERS = {
    "the", "and", "is", "are", "was", "were", "to", "of", "in", "for", "with",
    "this", "that", "these", "those", "i", "you", "we", "they", "he", "she", "it",
    "have", "has", "had", "will", "would", "can", "could", "should", "not", "but",
    "because", "from", "by", "on", "at", "as", "there", "here", "what", "why",
    "who", "when", "where", "how", "people", "house", "food", "money", "work",
    "school", "day", "time", "year", "month", "week", "child", "mother", "father",
    "very", "more", "most", "still", "must", "want", "need", "much", "many",
}


def detect_direction(text: str) -> str:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return "id-en"
    id_hits = sum(1 for word in words if word in ID_MARKERS)
    en_hits = sum(1 for word in words if word in EN_MARKERS)
    if en_hits > id_hits:
        return "en-id"
    if id_hits > en_hits:
        return "id-en"
    return "id-en"


def load_model(direction: str):
    tokenizer, translator = loaded[direction]
    if tokenizer is not None and translator is not None:
        return tokenizer, translator
    model_dir = DIRECTIONS[direction]["model_dir"]
    if not model_dir.exists():
        raise FileNotFoundError(f"Model {direction} tidak ditemukan di {model_dir}")
    new_tokenizer = MarianTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    new_translator = ctranslate2.Translator(
        str(model_dir),
        device="cpu",
        inter_threads=1,
        intra_threads=CPU_THREADS,
        compute_type="int8",
    )
    loaded[direction] = (new_tokenizer, new_translator)
    return new_tokenizer, new_translator


def unload_model(direction: Optional[str] = None):
    with state_lock:
        targets = [direction] if direction else list(DIRECTIONS)
        for key in targets:
            tokenizer, translator = loaded.get(key, (None, None))
            loaded[key] = (None, None)
            del tokenizer, translator
        gc.collect()


def unload_when_idle():
    while not reaper_stop.wait(15):
        if not state_lock.acquire(blocking=False):
            continue
        try:
            if time.monotonic() - last_active < IDLE_UNLOAD_SECONDS:
                continue
            if any(tokenizer is not None for tokenizer, _ in loaded.values()):
                for key in list(DIRECTIONS):
                    loaded[key] = (None, None)
                gc.collect()
        finally:
            state_lock.release()


@asynccontextmanager
async def lifespan(application):
    reaper_stop.clear()
    thread = threading.Thread(target=unload_when_idle, name="model-idle-reaper", daemon=True)
    thread.start()
    yield
    reaper_stop.set()
    thread.join(timeout=2)
    unload_model()


app = FastAPI(title="Alih — Terjemah ID ⇄ EN", version="2.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class TranslationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    direction: Literal["id-en", "en-id", "auto"] = "auto"


def split_sentences(text: str):
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def run_translation(text: str, direction: str) -> str:
    tokenizer, translator = load_model(direction)
    sentences = split_sentences(text)
    translated = []
    for start in range(0, len(sentences), 8):
        batch = sentences[start:start + 8]
        tokens = [tokenizer.convert_ids_to_tokens(tokenizer.encode(sentence)) for sentence in batch]
        results = translator.translate_batch(tokens, beam_size=2, max_decoding_length=512)
        translated.extend(
            tokenizer.decode(tokenizer.convert_tokens_to_ids(result.hypotheses[0]), skip_special_tokens=True)
            for result in results
        )
    return " ".join(translated)


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index-modern.html")


@app.get("/api/health")
def health():
    if not state_lock.acquire(timeout=0.2):
        return {
            "status": "working",
            "directions": {key: "busy" for key in DIRECTIONS},
            "idle_unload_seconds": IDLE_UNLOAD_SECONDS,
        }
    try:
        directions = {
            key: ("ready" if loaded[key][1] is not None else "sleeping") for key in DIRECTIONS
        }
    finally:
        state_lock.release()
    return {
        "status": "ready" if "ready" in directions.values() else "sleeping",
        "directions": directions,
        "idle_unload_seconds": IDLE_UNLOAD_SECONDS,
    }


@app.post("/api/translate")
def translate(payload: TranslationRequest):
    global last_active
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Teks tidak boleh kosong.")
    direction = payload.direction
    if direction == "auto":
        direction = detect_direction(text)
    try:
        with state_lock:
            last_active = time.monotonic()
            result = run_translation(text, direction)
            last_active = time.monotonic()
        return {
            "translation": result,
            "source": text,
            "direction": direction,
            "model": DIRECTIONS[direction]["model_name"],
        }
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"File model {direction} belum tersedia di server.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Translasi gagal: {type(exc).__name__}") from exc
