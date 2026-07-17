"""Cliente da API de narracao ai33 (OpenSpeaker).

Fluxo do TTS (assincrono):
  1. POST /v3/text-to-speech (FormData) -> { task_id }
  2. GET  /v1/task/{task_id} ate status == 'done' -> metadata.audio_url
  3. baixa o audio_url

A API key fica salva localmente em backend/ai33_config.json (NAO vai pro git).
"""
import json
import time
from pathlib import Path

import requests

API_BASE = "https://api.ai33.pro"
CONFIG_FILE = Path(__file__).resolve().parents[1] / "ai33_config.json"


# ------------------------------------------------------------- API key (local)
def get_key() -> str | None:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("api_key") or None
        except Exception:  # noqa: BLE001
            return None
    return None


def set_key(key: str):
    CONFIG_FILE.write_text(json.dumps({"api_key": key.strip()}), encoding="utf-8")


def _headers(json_body: bool = False) -> dict:
    key = get_key()
    if not key:
        raise RuntimeError("API key da ai33 nao configurada.")
    h = {"xi-api-key": key}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


# ------------------------------------------------------------- endpoints
def get_credits() -> int:
    r = requests.get(f"{API_BASE}/v1/credits", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json().get("credits", 0)


def list_voices(provider: str, q: str = "", page: int = 1, page_size: int = 60) -> dict:
    params = {"provider": provider, "page": page, "page_size": page_size}
    if q:
        params["q"] = q
    r = requests.get(f"{API_BASE}/v3/voices", headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def tts(text: str, voice_id: str, speed: float = 1.0) -> str:
    """Dispara a geracao e devolve o task_id."""
    # -F do curl = multipart/form-data -> usar files com (None, valor)
    files = {
        "text": (None, text),
        "voice_id": (None, voice_id),
        "speed": (None, str(speed)),
    }
    r = requests.post(f"{API_BASE}/v3/text-to-speech", headers=_headers(),
                      files=files, timeout=60)
    r.raise_for_status()
    data = r.json()
    if not data.get("success") or not data.get("task_id"):
        raise RuntimeError(f"ai33 recusou o TTS: {data}")
    return data["task_id"]


def get_task(task_id: str) -> dict:
    r = requests.get(f"{API_BASE}/v1/task/{task_id}", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def wait_task(task_id: str, on_progress=None, poll_every: float = 3.0,
              timeout: float = 900.0) -> str:
    """Pola o task ate 'done' e devolve o audio_url. Levanta erro se falhar."""
    waited = 0.0
    while waited < timeout:
        t = get_task(task_id)
        status = t.get("status")
        if on_progress:
            on_progress(t.get("progress", 0))
        if status == "done":
            url = (t.get("metadata") or {}).get("audio_url")
            if not url:
                raise RuntimeError("Tarefa concluida mas sem audio_url.")
            return url
        if status == "error":
            raise RuntimeError(t.get("error_message") or "Tarefa falhou na ai33.")
        time.sleep(poll_every)
        waited += poll_every
    raise RuntimeError("Tempo esgotado esperando a narracao ficar pronta.")


def download(url: str, dest: Path) -> Path:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest
