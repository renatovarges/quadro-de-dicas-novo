from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.auth_store import load_globo_auth, save_globo_auth, save_mpv_cache
from src.data_sources import (
    build_mpv_cache_payload,
    count_mpv_values,
    fetch_market_snapshot,
    fetch_mpv_map,
    refresh_globo_tokens,
)


def remote_config_from_env() -> dict[str, str]:
    env_values = {
        "SUPABASE_URL": os.environ.get("SUPABASE_URL", "").strip(),
        "SUPABASE_SERVICE_ROLE_KEY": os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        "AUTH_ENCRYPTION_KEY": os.environ.get("AUTH_ENCRYPTION_KEY", "").strip(),
    }
    missing = [name for name, value in env_values.items() if not value]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Segredos ausentes para o robo: {names}")
    return {
        "url": env_values["SUPABASE_URL"],
        "service_role_key": env_values["SUPABASE_SERVICE_ROLE_KEY"],
        "encryption_key": env_values["AUTH_ENCRYPTION_KEY"],
    }


def load_tokens(remote_config: dict[str, str]) -> dict[str, str]:
    saved_tokens = load_globo_auth(remote_config)
    if saved_tokens:
        return saved_tokens

    env_tokens = {
        "access_token": os.environ.get("GLOBO_ACCESS_TOKEN", "").strip(),
        "id_token": os.environ.get("GLOBO_ID_TOKEN", "").strip(),
        "refresh_token": os.environ.get("GLOBO_REFRESH_TOKEN", "").strip(),
    }
    if all(env_tokens.values()):
        return env_tokens

    raise RuntimeError(
        "Nenhum token Globo foi encontrado no Supabase. "
        "Conecte a conta pelo Streamlit uma vez ou configure GLOBO_ACCESS_TOKEN, "
        "GLOBO_ID_TOKEN e GLOBO_REFRESH_TOKEN no GitHub Actions."
    )


def main() -> int:
    remote_config = remote_config_from_env()
    tokens = load_tokens(remote_config)

    renewed_tokens = refresh_globo_tokens(**tokens)
    save_globo_auth(renewed_tokens, remote_config)

    mpv_map = fetch_mpv_map(renewed_tokens["access_token"])
    mpv_count = count_mpv_values(mpv_map)
    if not mpv_count:
        raise RuntimeError("Gato Mestre nao retornou minimo para valorizar.")

    market_df = fetch_market_snapshot(mpv_map=mpv_map)
    cache_payload = build_mpv_cache_payload(
        mpv_map,
        source="gato_mestre_robot",
        market_count=len(market_df),
    )
    save_mpv_cache(cache_payload, remote_config)

    print(
        "Cache MPV atualizado com sucesso: "
        f"{cache_payload['mpv_count']} valores para {cache_payload['market_count']} atletas."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
