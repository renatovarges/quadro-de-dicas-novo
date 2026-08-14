from __future__ import annotations

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

import requests
from cryptography.fernet import Fernet, InvalidToken


AUTH_DIR = Path(__file__).resolve().parents[2] / ".local_secrets"
AUTH_FILE = AUTH_DIR / "globo_auth.bin"
MPV_CACHE_FILE = AUTH_DIR / "cartola_mpv_cache.json"
DESCRIPTION = "Nova Plataforma TCC - tokens Globo"
REMOTE_RECORD_ID = "globo_cartola"
REMOTE_MPV_CACHE_RECORD_ID = "cartola_mpv_cache"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("O cofre local criptografado está disponível somente no Windows.")
    input_blob, input_buffer = _blob(data)
    output_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob), DESCRIPTION, None, None, None, 0,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)
        del input_buffer


def _unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("O cofre local criptografado está disponível somente no Windows.")
    input_blob, input_buffer = _blob(data)
    output_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob), None, None, None, None, 0,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)
        del input_buffer


def _remote_headers(config: dict[str, str]) -> dict[str, str]:
    key = config["service_role_key"]
    headers = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _remote_url(config: dict[str, str]) -> str:
    return f'{config["url"].rstrip("/")}/rest/v1/tcc_secrets'


def _fernet(config: dict[str, str]) -> Fernet:
    return Fernet(config["encryption_key"].encode("ascii"))


def _save_remote_payload(record_id: str, payload: dict, remote_config: dict[str, str]) -> None:
    encrypted = _fernet(remote_config).encrypt(json.dumps(payload).encode("utf-8")).decode("ascii")
    response = requests.post(
        _remote_url(remote_config),
        params={"on_conflict": "id"},
        headers=_remote_headers(remote_config) | {"Prefer": "resolution=merge-duplicates"},
        json={"id": record_id, "payload": encrypted},
        timeout=20,
    )
    response.raise_for_status()


def _load_remote_payload(record_id: str, remote_config: dict[str, str]) -> dict | None:
    response = requests.get(
        _remote_url(remote_config),
        params={"id": f"eq.{record_id}", "select": "payload", "limit": "1"},
        headers=_remote_headers(remote_config),
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return None
    clear_data = _fernet(remote_config).decrypt(rows[0]["payload"].encode("ascii"))
    payload = json.loads(clear_data.decode("utf-8"))
    return payload if isinstance(payload, dict) else None


def save_globo_auth(tokens: dict[str, str], remote_config: dict[str, str] | None = None) -> None:
    required = ("access_token", "id_token", "refresh_token")
    payload = {field: str(tokens[field]) for field in required}
    if remote_config:
        _save_remote_payload(REMOTE_RECORD_ID, payload, remote_config)
        return
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_bytes(_protect(json.dumps(payload).encode("utf-8")))


def load_globo_auth(remote_config: dict[str, str] | None = None) -> dict[str, str] | None:
    if remote_config:
        try:
            payload = _load_remote_payload(REMOTE_RECORD_ID, remote_config)
            if not payload:
                return None
            required = ("access_token", "id_token", "refresh_token")
            if not all(payload.get(field) for field in required):
                return None
            return {field: str(payload[field]) for field in required}
        except (requests.RequestException, InvalidToken, KeyError, ValueError, TypeError):
            return None
    if not AUTH_FILE.exists():
        return None
    try:
        payload = json.loads(_unprotect(AUTH_FILE.read_bytes()).decode("utf-8"))
        required = ("access_token", "id_token", "refresh_token")
        if not all(payload.get(field) for field in required):
            return None
        return {field: str(payload[field]) for field in required}
    except Exception:
        return None


def delete_globo_auth(remote_config: dict[str, str] | None = None) -> None:
    if remote_config:
        response = requests.delete(
            _remote_url(remote_config),
            params={"id": f"eq.{REMOTE_RECORD_ID}"},
            headers=_remote_headers(remote_config),
            timeout=20,
        )
        response.raise_for_status()
        return
    if AUTH_FILE.exists():
        AUTH_FILE.unlink()


def save_mpv_cache(cache_payload: dict, remote_config: dict[str, str] | None = None) -> None:
    if remote_config:
        _save_remote_payload(REMOTE_MPV_CACHE_RECORD_ID, cache_payload, remote_config)
        return
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    MPV_CACHE_FILE.write_text(json.dumps(cache_payload, ensure_ascii=False), encoding="utf-8")


def load_mpv_cache(remote_config: dict[str, str] | None = None) -> dict | None:
    if remote_config:
        try:
            return _load_remote_payload(REMOTE_MPV_CACHE_RECORD_ID, remote_config)
        except (requests.RequestException, InvalidToken, KeyError, ValueError, TypeError):
            return None
    if not MPV_CACHE_FILE.exists():
        return None
    try:
        payload = json.loads(MPV_CACHE_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None
