"""Guarda as indicações fechadas e os resultados de cada rodada.

Usa a mesma tabela `tcc_secrets` do Supabase já configurada para os tokens (conteúdo criptografado),
então não é preciso criar nada novo. Sem Supabase, grava arquivos JSON em `.local_secrets/`.
"""
from __future__ import annotations

import json

import requests
from cryptography.fernet import InvalidToken

from .auth_store import AUTH_DIR, _load_remote_payload, _save_remote_payload, _remote_headers, _remote_url


def _record_id(kind: str, project: str, round_number: int) -> str:
    """Indicações são por marca (tcc/guardiola); a pontuação real da rodada é a mesma para todos."""
    if kind == "resultado":
        return f"resultado_r{int(round_number):02d}"
    return f"{kind}_{project}_r{int(round_number):02d}"


def _local_file(record_id: str):
    return AUTH_DIR / f"{record_id}.json"


def _save(record_id: str, payload: dict, remote_config: dict | None) -> None:
    if remote_config:
        _save_remote_payload(record_id, payload, remote_config)
        return
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    _local_file(record_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _load(record_id: str, remote_config: dict | None) -> dict | None:
    if remote_config:
        try:
            return _load_remote_payload(record_id, remote_config)
        except (requests.RequestException, InvalidToken, KeyError, ValueError, TypeError):
            return None
    file = _local_file(record_id)
    if not file.exists():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_snapshot(snapshot: dict, remote_config: dict | None = None) -> None:
    _save(_record_id("indicacoes", snapshot["project"], snapshot["round"]), snapshot, remote_config)


def load_snapshot(project: str, round_number: int, remote_config: dict | None = None) -> dict | None:
    return _load(_record_id("indicacoes", project, round_number), remote_config)


def save_results(project: str, results: dict, remote_config: dict | None = None) -> None:
    """A API só devolve a última rodada; guardamos o resultado para consultar depois."""
    payload = {**results, "players": {str(k): v for k, v in results["players"].items()}}
    _save(_record_id("resultado", project, results["round"]), payload, remote_config)


def load_results(project: str, round_number: int, remote_config: dict | None = None) -> dict | None:
    payload = _load(_record_id("resultado", project, round_number), remote_config)
    if not payload:
        return None
    payload["players"] = {int(k): v for k, v in payload["players"].items()}
    return payload


def list_saved_rounds(project: str, remote_config: dict | None = None) -> list[int]:
    prefix = f"indicacoes_{project}_r"
    rounds: list[int] = []
    if remote_config:
        try:
            response = requests.get(
                _remote_url(remote_config),
                params={"id": f"like.{prefix}*", "select": "id"},
                headers=_remote_headers(remote_config),
                timeout=20,
            )
            response.raise_for_status()
            names = [row["id"] for row in response.json()]
        except (requests.RequestException, KeyError, ValueError):
            names = []
    else:
        names = [f.stem for f in AUTH_DIR.glob(f"{prefix}*.json")] if AUTH_DIR.exists() else []
    for name in names:
        try:
            rounds.append(int(name.rsplit("_r", 1)[1]))
        except (IndexError, ValueError):
            continue
    return sorted(set(rounds), reverse=True)


def load_archive(project: str, rounds: list[int], remote_config: dict | None = None) -> dict[int, dict]:
    archive = {}
    for round_number in rounds:
        results = load_results(project, round_number, remote_config)
        if results:
            archive[round_number] = results
    return archive


def archive_latest_round(project: str, remote_config: dict | None = None) -> int | None:
    """Guarda a pontuação da última rodada FINALIZADA (mercado aberto), se ainda não estiver arquivada.

    A API do Cartola só devolve a última rodada; arquivar evita perder o histórico.
    Devolve o número da rodada arquivada ou None.
    """
    from .feedback import fetch_market_status, fetch_round_results

    market = fetch_market_status()
    if market.get("status_mercado") != 1:  # 1 = mercado aberto -> a rodada anterior já terminou
        return None
    results = fetch_round_results()
    finished_round = int(market.get("rodada_atual", 0)) - 1
    if results["round"] != finished_round or load_results(project, finished_round, remote_config):
        return None
    save_results(project, results, remote_config)
    return finished_round
