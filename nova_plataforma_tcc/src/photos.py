from __future__ import annotations

import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO

import requests

from .config import ROOT_PROJECT_DIR

PHOTO_CACHE_DIR = ROOT_PROJECT_DIR / "nova_plataforma_tcc" / ".tmp" / "photo_cache"
MAX_PHOTO_SIDE = 400
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "image/*,*/*;q=0.8"}


def _encode(content: bytes) -> str:
    """Normaliza a foto (tamanho máx. 400px) e devolve um data URI. Sem Pillow, usa o original."""
    try:
        from PIL import Image
    except ModuleNotFoundError:
        return "data:image/png;base64," + base64.b64encode(content).decode()

    with Image.open(BytesIO(content)) as image:
        image.load()
        if max(image.size) > MAX_PHOTO_SIDE:
            image.thumbnail((MAX_PHOTO_SIDE, MAX_PHOTO_SIDE), Image.LANCZOS)
        has_alpha = image.mode in ("RGBA", "LA", "P") and "transparency" in image.info or image.mode in ("RGBA", "LA")
        output = BytesIO()
        if has_alpha:
            image.convert("RGBA").save(output, format="PNG", optimize=True)
            mime = "image/png"
        else:
            image.convert("RGB").save(output, format="JPEG", quality=94, subsampling=0)
            mime = "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(output.getvalue()).decode()


@lru_cache(maxsize=2048)
def photo_data_uri(url: str) -> str:
    """Baixa a foto uma vez, guarda em disco e devolve como data URI.

    Embutir a foto na arte elimina falhas de rede (imgur/cloudinary) na hora de exportar o PNG.
    Se não for possível baixar, devolve vazio: a arte usa o aviso "SEM FOTO" em vez de imagem quebrada.
    """
    if not url:
        return ""
    if url.startswith("data:"):
        return url
    if not url.startswith(("http://", "https://")):
        local_file = ROOT_PROJECT_DIR / url
        try:
            return _encode(local_file.read_bytes())
        except Exception:
            return ""

    cache_file = PHOTO_CACHE_DIR / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".txt")
    if cache_file.exists():
        cached = cache_file.read_text(encoding="utf-8")
        if cached.startswith("data:"):
            return cached

    for _ in range(2):
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
            response.raise_for_status()
            data_uri = _encode(response.content)
            try:
                PHOTO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(data_uri, encoding="utf-8")
            except OSError:
                pass
            return data_uri
        except Exception:
            continue
    return ""


def prefetch_photos(urls: list[str]) -> None:
    unique = [url for url in dict.fromkeys(urls) if url]
    if len(unique) > 1:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(photo_data_uri, unique))
