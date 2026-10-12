"""Importa indicações de um CSV (o mesmo formato do "Baixar CSV das indicações" da plataforma).

Colunas: posicao, nome, clube, atleta_id (opcional), unanimidade, bom_capitao, bom_rl, fora_dos_20 (opcional),
confianca, perfis (separados por "|"), preco e mpv (opcionais; vêm do mercado quando houver).
"""
from __future__ import annotations

import io

import pandas as pd

from .config import POSITION_CONFIG
from .utils import normalize_text, order_indication_players, resolve_team_name

VALID_PROFILES = {"SG", "CONFRONTO", "ESTATISTICO", "ESTRATEGICO", "BOA FASE"}


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "sim", "s", "x", "verdadeiro", "yes"}


def _find_market_row(market_df: pd.DataFrame | None, athlete_id, team: str, name: str):
    if market_df is None or market_df.empty:
        return None
    if athlete_id not in (None, "") and not pd.isna(athlete_id):
        try:
            hit = market_df[market_df["atleta_id"] == int(float(athlete_id))]
            if len(hit):
                return hit.iloc[0].to_dict()
        except (TypeError, ValueError):
            pass
    team_norm = normalize_text(resolve_team_name(team))
    name_norm = normalize_text(name)
    candidates = market_df[market_df["time"].map(lambda t: normalize_text(resolve_team_name(t))) == team_norm]
    for column in ("nome", "nome_completo"):
        exact = candidates[candidates[column].map(normalize_text) == name_norm]
        if len(exact) == 1:
            return exact.iloc[0].to_dict()
    partial = candidates[
        candidates["nome"].map(normalize_text).map(lambda n: bool(n) and (name_norm in n or n in name_norm))
    ]
    if len(partial) == 1:
        return partial.iloc[0].to_dict()
    return None


def parse_indications_csv(file_bytes: bytes, market_df: pd.DataFrame | None = None) -> tuple[dict[str, list[dict]], list[str]]:
    """Devolve ({posição: [jogadores]}, avisos). Linhas que não casam com o mercado entram sem preço/MPV e geram aviso."""
    frame = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8-sig", dtype=str).fillna("")
    frame.columns = [normalize_text(c).lower() for c in frame.columns]
    required = {"posicao", "nome", "clube"}
    if not required.issubset(frame.columns):
        raise ValueError("O CSV precisa ter as colunas: posicao, nome, clube (e, de preferência, atleta_id).")

    players: dict[str, list[dict]] = {key: [] for key in POSITION_CONFIG}
    warnings: list[str] = []
    for row in frame.to_dict("records"):
        position = next((k for k in POSITION_CONFIG if normalize_text(k) == normalize_text(row["posicao"])), None)
        if not position:
            warnings.append(f'Posição desconhecida "{row["posicao"]}" ({row["nome"]}); linha ignorada.')
            continue
        market_row = _find_market_row(market_df, row.get("atleta_id"), row["clube"], row["nome"])
        if market_df is not None and not market_df.empty and market_row is None:
            warnings.append(f'{row["nome"]} ({row["clube"]}) não foi encontrado no mercado; entra sem preço, MPV e ID.')
        profiles = [
            p for p in (normalize_text(x) for x in str(row.get("perfis", "")).split("|"))
            if p in VALID_PROFILES
        ]
        confidence = str(row.get("confianca", "A")).strip().upper()
        players[position].append(
            {
                "name": (market_row or {}).get("nome") or row["nome"],
                "full_name": (market_row or {}).get("nome_completo") or row.get("nome_completo", "") or row["nome"],
                "athlete_id": int((market_row or {}).get("atleta_id")) if market_row else (
                    int(float(row["atleta_id"])) if str(row.get("atleta_id", "")).strip() not in ("", "nan") else None
                ),
                "team": (market_row or {}).get("time") or resolve_team_name(row["clube"]),
                "price": float((market_row or {}).get("preco", row.get("preco") or 0.0) or 0.0),
                "mpv": float((market_row or {}).get("minimo_valorizar", row.get("mpv") or 0.0) or 0.0),
                "confidence": confidence if confidence in {"A", "B", "C", "D"} else "A",
                "profiles": profiles,
                "badges": {
                    "unanimidade": _truthy(row.get("unanimidade")),
                    "bom_capitao": _truthy(row.get("bom_capitao")),
                    "bom_rl": _truthy(row.get("bom_rl")),
                    "fora_dos_20": _truthy(row.get("fora_dos_20")),
                },
            }
        )
    return {k: order_indication_players(v) for k, v in players.items()}, warnings
