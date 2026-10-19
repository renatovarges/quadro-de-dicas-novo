"""Guarda as indicações fechadas e os resultados de cada rodada.

Usa a mesma tabela `tcc_secrets` do Supabase já configurada para os tokens (conteúdo criptografado),
então não é preciso criar nada novo. Sem Supabase, grava arquivos JSON em `.local_secrets/`.
"""
from __future__ import annotations

import json
import os

import requests
from cryptography.fernet import InvalidToken

from .auth_store import AUTH_DIR, _load_remote_payload, _save_remote_payload, _remote_headers, _remote_url


def _record_id(kind: str, project: str, round_number: int) -> str:
    """Indicações são por marca (tcc/guardiola); a pontuação real da rodada é a mesma para todos."""
    if kind in ("resultado", "mais_escalados"):
        return f"{kind}_r{int(round_number):02d}"
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
    """Pontuação das rodadas pedidas. O que não estiver guardado é buscado na API (por número de rodada) e guardado."""
    from .feedback import fetch_round_results

    archive = {}
    for round_number in rounds:
        results = load_results(project, round_number, remote_config)
        if not results:
            try:
                results = fetch_round_results(round_number)
                save_results(project, results, remote_config)
            except Exception:
                results = None
        if results:
            archive[round_number] = results
    return archive


def archive_latest_round(project: str, remote_config: dict | None = None) -> int | None:
    """Guarda a pontuação da última rodada FINALIZADA (mercado aberto), se ainda não estiver arquivada.

    Devolve o número da rodada arquivada ou None.
    """
    from .feedback import fetch_market_status, fetch_round_results

    market = fetch_market_status()
    if market.get("status_mercado") != 1:  # 1 = mercado aberto -> a rodada anterior já terminou
        return None
    finished_round = int(market.get("rodada_atual", 0)) - 1
    if finished_round < 1 or load_results(project, finished_round, remote_config):
        return None
    results = fetch_round_results(finished_round)
    if results["round"] != finished_round:
        return None
    save_results(project, results, remote_config)
    return finished_round


def save_most_escalated(round_number: int, payload: dict, remote_config: dict | None = None) -> None:
    _save(_record_id("mais_escalados", "", round_number), {**payload, "round": int(round_number)}, remote_config)


def load_most_escalated(round_number: int, remote_config: dict | None = None) -> dict | None:
    """Supabase/local primeiro; depois o arquivo de segurança commitado no repositório."""
    from .most_escalated import load_repo_archive

    return _load(_record_id("mais_escalados", "", round_number), remote_config) or load_repo_archive(round_number)


def archive_most_escalated(remote_config: dict | None = None, access_token: str | None = None) -> int | None:
    """Guarda os mais escalados da rodada atual, mas só com o mercado FECHADO (números finais).

    Com `access_token` (login Globo) guarda também a lista OFICIAL (top 20 e reservas) e completa registros
    que foram guardados antes sem ela. Devolve a rodada guardada/completada ou None.
    """
    from .feedback import fetch_market_status
    from .most_escalated import fetch_captains, fetch_most_escalated, fetch_official_destaques

    market = fetch_market_status()
    if market.get("status_mercado") != 2:  # 2 = fechado
        return None
    round_number = int(market.get("rodada_atual", 0))
    existing = load_most_escalated(round_number, remote_config)
    if existing:
        # completa o que faltou no registro (lista oficial e/ou capitães); nunca sobrescreve o que já existe
        completed = dict(existing)
        changed = False
        if access_token and not existing.get("official"):
            official = fetch_official_destaques(access_token)
            if official:
                completed["official"] = official
                changed = True
        if not existing.get("captain_data") and os.environ.get("H2H_ROBO_LEITURA_CHAVE", "").strip():
            captains = fetch_captains((market.get("fechamento") or {}).get("timestamp"))
            if captains and captains.get("captains"):
                completed["captain_data"] = captains
                changed = True
        if changed:
            save_most_escalated(round_number, completed, remote_config)
            return round_number
        return None
    payload = fetch_most_escalated()
    if len(payload["players"]) < 12:
        return None  # página incompleta: não guarda dado ruim
    close_timestamp = (market.get("fechamento") or {}).get("timestamp")
    payload["captain_data"] = fetch_captains(close_timestamp)  # None se a fonte de terceiros estiver fora do ar
    if access_token:
        payload["official"] = fetch_official_destaques(access_token)
    save_most_escalated(round_number, payload, remote_config)
    return round_number
