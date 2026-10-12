"""Busca fotos para jogadores do mercado do Cartola que estão sem foto (ou com link morto).

Segurança contra troca de jogadores: a foto só é aceita automaticamente quando
  1) o CLUBE do resultado bate com o clube do Cartola e
  2) o NOME bate (todas as palavras do nome encontrado estão no nome do Cartola, ou vice-versa).
Todo o resto vai para `revisao_manual.csv` e NÃO entra em `assets/photo_overrides.json`.

Uso:
    python tools/buscar_fotos_faltantes.py            # só prováveis/dúvidas + quem está na planilha
    python tools/buscar_fotos_faltantes.py --todos    # todos os atletas do mercado
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from io import BytesIO
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.config import DEFAULT_EXCEL_FILE, PHOTO_OVERRIDES_FILE, PLAYER_PHOTOS_DIR  # noqa: E402
from src.data_sources import build_photo_index, fetch_market_snapshot, load_excel_data  # noqa: E402
from src.utils import normalize_text, resolve_team_name  # noqa: E402

PHOTOS_FILE = ROOT_DIR.parent / "tcc_fotos_jogadores.html"
OUTPUT_DIR = ROOT_DIR / ".tmp" / "auditoria_fotos"
SEARCH_URL = "https://www.transfermarkt.com.br/schnellsuche/ergebnis/schnellsuche"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
PAUSE_SECONDS = 1.2

# palavra-chave do clube no resultado -> time normalizado do projeto
CLUB_KEYWORDS = {
    "ATHLETICO-PR": ["athletico", "atletico paranaense"],
    "ATLETICO-MG": ["atletico mineiro", "atletico-mg", "atletico mg"],
    "BAHIA": ["bahia"],
    "BOTAFOGO": ["botafogo"],
    "CHAPECOENSE": ["chapecoense"],
    "CORINTHIANS": ["corinthians"],
    "CORITIBA": ["coritiba"],
    "CRUZEIRO": ["cruzeiro"],
    "FLAMENGO": ["flamengo"],
    "FLUMINENSE": ["fluminense"],
    "GREMIO": ["gremio"],
    "INTERNACIONAL": ["internacional"],
    "MIRASSOL": ["mirassol"],
    "PALMEIRAS": ["palmeiras"],
    "RED BULL BRAGANTINO": ["bragantino"],
    "REMO": ["remo"],
    "SANTOS": ["santos"],
    "SAO PAULO": ["sao paulo"],
    "VASCO": ["vasco"],
    "VITORIA": ["vitoria"],
}

ROW_PATTERN = re.compile(r'<tr class="(?:odd|even)">(.*?)</tr>\s*(?=<tr class="(?:odd|even)">|</tbody>)', re.S)


def club_matches(club_title: str, team: str) -> bool:
    club = normalize_text(club_title).lower()
    if team == "SANTOS" and "santos laguna" in club:
        return False
    if team == "VITORIA" and ("guimaraes" in club or "setubal" in club):
        return False
    return any(keyword in club for keyword in CLUB_KEYWORDS.get(team, []))


def name_tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^A-Z0-9]+", normalize_text(value)) if len(token) > 1}


def names_match(found_name: str, *cartola_names: str) -> bool:
    found = name_tokens(found_name)
    if not found:
        return False
    for cartola_name in cartola_names:
        wanted = name_tokens(cartola_name)
        if not wanted:
            continue
        if found <= wanted or wanted <= found:
            return True
        # sobrenome + primeiro nome em comum (ex.: "Alex Bruno" x "Alex Bruno da Costa Lima")
        if len(found & wanted) >= 2:
            return True
    return False


def parse_results(html: str) -> list[dict]:
    start = html.find('class="items"')
    if start < 0:
        return []
    table = html[start:]
    results = []
    for row in ROW_PATTERN.findall(table):
        portrait = re.search(r'<img src="(https://img\.a\.transfermarkt\.technology/portrait/[^"]+)"', row)
        name = re.search(r'class="hauptlink"><a title="([^"]+)" href="(/[^"]+/profil/spieler/(\d+))"', row)
        club = re.search(r'<td class="zentriert"><a title="([^"]+)" href="/[^"]+/startseite/verein/', row)
        if portrait and name and club:
            results.append(
                {
                    "name": name.group(1),
                    "profile": "https://www.transfermarkt.com.br" + name.group(2),
                    "club": club.group(1),
                    "portrait": portrait.group(1),
                }
            )
    return results


def search_player(query: str) -> list[dict]:
    response = requests.get(SEARCH_URL, params={"query": query}, headers=HEADERS, timeout=25)
    response.raise_for_status()
    return parse_results(response.text)


def download_portrait(url: str) -> bytes | None:
    if "default" in url:
        return None
    for variant in (url.replace("/portrait/small/", "/portrait/big/"), url.replace("/portrait/small/", "/portrait/medium/")):
        try:
            response = requests.get(variant, headers=HEADERS, timeout=25)
            if response.status_code == 200 and response.headers.get("content-type", "").startswith("image"):
                return response.content
        except requests.RequestException:
            continue
    return None


def save_photo(content: bytes, target: Path) -> None:
    from PIL import Image

    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(BytesIO(content)) as image:
        image.convert("RGB").save(target, format="JPEG", quality=94)


def url_is_alive(url: str) -> bool:
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20, stream=True)
        alive = response.status_code == 200 and response.headers.get("content-type", "").startswith("image")
        response.close()
        return alive
    except requests.RequestException:
        return False


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalize_text(value).lower()).strip("_")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--todos", action="store_true", help="processa todos os atletas do mercado")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    photo_index = build_photo_index(PHOTOS_FILE)
    market = fetch_market_snapshot()
    played = set()
    if DEFAULT_EXCEL_FILE.exists():
        games = load_excel_data(DEFAULT_EXCEL_FILE)["POR_JOGO"]
        played = set(zip(games["TIME_NORM"], games["NOME_NORM"]))

    overrides = json.loads(PHOTO_OVERRIDES_FILE.read_text(encoding="utf-8")) if PHOTO_OVERRIDES_FILE.exists() else {}

    targets = []
    for player in market.to_dict("records"):
        team = resolve_team_name(player["time"])
        relevant = (
            args.todos
            or player["status"] in ("Provável", "Dúvida")
            or (team, normalize_text(player["nome"])) in played
        )
        if not relevant:
            continue
        team_index = photo_index.get(normalize_text(team), {})
        urls = {
            team_index[normalize_text(name)]
            for name in (player["nome"], player.get("nome_completo", ""))
            if normalize_text(name) in team_index
        }
        if urls and any(url_is_alive(url) if url.startswith("http") else True for url in urls):
            continue
        targets.append(player | {"time_norm": team})

    print(f"{len(targets)} jogadores relevantes sem foto funcionando. Buscando...")
    accepted, review = [], []
    for position, player in enumerate(targets, start=1):
        team = player["time_norm"]
        queries = [player["nome"]]
        full_parts = player.get("nome_completo", "").split()
        if len(full_parts) > 2:
            queries.append(f"{full_parts[0]} {full_parts[-1]}")

        chosen, reason = None, "sem resultado do clube"
        for query in queries:
            try:
                results = search_player(query)
            except requests.RequestException as exc:
                reason = f"erro na busca: {exc}"
                results = []
            time.sleep(PAUSE_SECONDS)
            club_hits = [r for r in results if club_matches(r["club"], team)]
            name_hits = [r for r in club_hits if names_match(r["name"], player["nome"], player.get("nome_completo", ""))]
            if len(name_hits) == 1:
                chosen = name_hits[0]
                break
            if len(name_hits) > 1:
                reason = "mais de um resultado do clube com nome parecido"
            elif club_hits:
                reason = "jogador do clube encontrado, mas nome não confere: " + "; ".join(r["name"] for r in club_hits[:3])

        label = f'[{position}/{len(targets)}] {team} - {player["nome"]}'
        if not chosen:
            print(f"{label}: REVISAR ({reason})")
            review.append({"time": team, "nome": player["nome"], "nome_completo": player.get("nome_completo", ""), "motivo": reason})
            continue

        content = download_portrait(chosen["portrait"])
        time.sleep(PAUSE_SECONDS)
        if not content:
            print(f"{label}: REVISAR (resultado sem foto real)")
            review.append({"time": team, "nome": player["nome"], "nome_completo": player.get("nome_completo", ""), "motivo": "resultado sem foto real: " + chosen["profile"]})
            continue

        relative = Path("assets") / "players" / slug(team) / f'{player["atleta_id"]}_{slug(player["nome"])}.jpg'
        save_photo(content, ROOT_DIR.parent / relative)
        team_overrides = overrides.setdefault(team, {})
        for name in {player["nome"], player.get("nome_completo", "")}:
            if name:
                team_overrides[name.upper()] = relative.as_posix()
        accepted.append(
            {"time": team, "nome": player["nome"], "encontrado": chosen["name"], "clube_encontrado": chosen["club"], "perfil": chosen["profile"], "arquivo": relative.as_posix()}
        )
        print(f"{label}: OK -> {chosen['name']} ({chosen['club']})")

    PHOTO_OVERRIDES_FILE.write_text(json.dumps(overrides, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    for file_name, rows in (("fotos_aceitas.csv", accepted), ("revisao_manual.csv", review)):
        if rows:
            with (OUTPUT_DIR / file_name).open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
    print(f"\nAceitas automaticamente: {len(accepted)} | Para revisão manual: {len(review)}")
    print(f"Relatórios em {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
