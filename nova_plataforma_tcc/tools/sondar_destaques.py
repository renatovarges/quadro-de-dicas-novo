"""Sonda: o endpoint autenticado /auth/mercado/destaques do Cartola traz capitães mais escalados?

Usa o token Globo já guardado (o mesmo do robô do MPV). NÃO imprime token nem dados pessoais:
só o status HTTP, a mensagem de erro (curta) e o FORMATO da resposta (nomes dos campos e tipos).
Rodar só quando precisar investigar.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.auth_store import load_globo_auth, save_globo_auth  # noqa: E402
from src.data_sources import refresh_globo_tokens  # noqa: E402

BASE = "https://api.cartola.globo.com"
CANDIDATES = [
    "/auth/mercado/destaques",
    "/auth/mercado/destaques/capitaes",
    "/auth/mercado/capitaes",
    "/auth/destaques",
]


def remote_config() -> dict[str, str]:
    values = {
        "url": os.environ.get("SUPABASE_URL", "").strip(),
        "service_role_key": os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        "encryption_key": os.environ.get("AUTH_ENCRYPTION_KEY", "").strip(),
    }
    if not all(values.values()):
        raise RuntimeError("Segredos do Supabase ausentes.")
    return values


def shape(value, depth: int = 0, max_depth: int = 4):
    """Descreve a estrutura sem expor valores (só tipos e nomes de campos)."""
    if depth >= max_depth:
        return type(value).__name__
    if isinstance(value, dict):
        return {key: shape(item, depth + 1, max_depth) for key, item in list(value.items())[:40]}
    if isinstance(value, list):
        return [f"lista de {len(value)}", shape(value[0], depth + 1, max_depth)] if value else ["lista vazia"]
    return type(value).__name__


def call(path: str, token: str, variant: int) -> requests.Response:
    base_headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "x-glb-app-name": "cartola-web",
    }
    variants = [
        {"X-GLB-Token": token},
        {"Authorization": f"Bearer {token}"},
        {"X-GLB-Token": token, "Authorization": f"Bearer {token}"},
    ]
    return requests.get(BASE + path, headers=base_headers | variants[variant], timeout=25)


def main() -> int:
    config = remote_config()
    tokens = load_globo_auth(config)
    if not tokens:
        print("Sem tokens Globo guardados.")
        return 1
    token = tokens["access_token"]
    refreshed = False
    for path in CANDIDATES:
        for variant in range(3):
            response = call(path, token, variant)
            if response.status_code == 401 and not refreshed and variant == 0:
                print("Token expirado; renovando uma vez.")
                tokens = refresh_globo_tokens(**tokens)
                save_globo_auth(tokens, config)
                token, refreshed = tokens["access_token"], True
                response = call(path, token, variant)
            print(f"\n== {path} [formato {variant + 1}] -> HTTP {response.status_code} ({len(response.content)} bytes)")
            if response.status_code != 200:
                print("   mensagem:", response.text[:160].replace("\n", " "))
                if response.status_code == 404:
                    break
                continue
            try:
                payload = response.json()
            except ValueError:
                print("Resposta não é JSON.")
                break
            print("FORMATO:", json.dumps(shape(payload), ensure_ascii=False, indent=1)[:3500])
            text = json.dumps(payload, ensure_ascii=False).lower()
            print("menciona 'capitao'/'capitão':", "capit" in text)
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
