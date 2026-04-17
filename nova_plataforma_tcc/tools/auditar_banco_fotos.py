from __future__ import annotations

import csv
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from src.data_sources import build_photo_index, fetch_market_snapshot
from src.utils import normalize_text, resolve_team_name


PHOTOS_FILE = PROJECT_DIR / "tcc_fotos_jogadores.html"
OUTPUT_DIR = ROOT_DIR / ".tmp" / "auditoria_fotos"


def categorize_player(team_index: dict[str, str], display_name: str, full_name: str) -> tuple[str, str]:
    candidates = []
    for raw_name in [display_name, full_name]:
        normalized = normalize_text(raw_name)
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    for candidate in candidates:
        if candidate in team_index:
            return "exato", candidate

    partial_matches: list[str] = []
    for candidate in candidates:
        if len(candidate.split()) < 2:
            continue
        for indexed_name in team_index:
            if len(indexed_name.split()) < 2:
                continue
            if candidate in indexed_name or indexed_name in candidate:
                if indexed_name not in partial_matches:
                    partial_matches.append(indexed_name)

    if len(partial_matches) == 1:
        return "parcial_unico", partial_matches[0]
    if partial_matches:
        return "ambiguo", " | ".join(partial_matches)
    return "faltando", ""


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    photo_index = build_photo_index(PHOTOS_FILE)
    market_df = fetch_market_snapshot()

    rows: list[dict[str, str]] = []
    summary = {"exato": 0, "parcial_unico": 0, "ambiguo": 0, "faltando": 0}

    for player in market_df.to_dict("records"):
        team_name = resolve_team_name(player["time"])
        team_index = photo_index.get(normalize_text(team_name), {})
        status, matched_name = categorize_player(
            team_index=team_index,
            display_name=player["nome"],
            full_name=player.get("nome_completo", ""),
        )
        summary[status] += 1
        rows.append(
            {
                "time": team_name,
                "nome_mercado": player["nome"],
                "nome_completo": player.get("nome_completo", ""),
                "status": status,
                "nome_encontrado_no_banco": matched_name,
            }
        )

    report_file = OUTPUT_DIR / "auditoria_banco_fotos.csv"
    with report_file.open("w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["time", "nome_mercado", "nome_completo", "status", "nome_encontrado_no_banco"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print("AUDITORIA DO BANCO DE FOTOS")
    print(f"Total de atletas no mercado: {len(rows)}")
    print(f"Match exato no time: {summary['exato']}")
    print(f"Match parcial único no time: {summary['parcial_unico']}")
    print(f"Casos ambíguos: {summary['ambiguo']}")
    print(f"Sem foto encontrada: {summary['faltando']}")
    print(f"Relatório salvo em: {report_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
