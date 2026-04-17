from __future__ import annotations

import json
import re
import shutil
import zipfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT_DIR.parent
TMP_DIR = ROOT_DIR / ".tmp" / "fontes_fotos"
HTML_FILE = PROJECT_DIR / "tcc_fotos_jogadores.html"

PRIMARY_EXTENSION_ID = "aiaglkhmijligfamllijmcpjjfngepje"
SECONDARY_EXTENSION_ID = "ggkdinokjkdheimpjnonpbpmbafmgapf"

EXT1_TEAM_MAP = {
    "cam": "ATLÉTICO-MG",
    "bah": "BAHIA",
    "bot": "BOTAFOGO",
    "rbb": "BRAGANTINO",
    "cea": "CEARÁ",
    "cor": "CORINTHIANS",
    "cru": "CRUZEIRO",
    "fla": "FLAMENGO",
    "flu": "FLUMINENSE",
    "fort": "FORTALEZA",
    "gre": "GRÊMIO",
    "intz": "INTERNACIONAL",
    "juv": "JUVENTUDE",
    "mir": "MIRASSOL",
    "pal": "PALMEIRAS",
    "san": "SANTOS",
    "spo": "SPORT",
    "sao": "SÃO PAULO",
    "vas": "VASCO",
    "vit": "VITÓRIA",
    "chap": "CHAPECOENSE",
    "remo": "REMO",
    "cap": "ATHLETICO-PR",
    "cwb": "CORITIBA",
}

TEAM_ORDER = [
    "ATHLETICO-PR",
    "ATLÉTICO-MG",
    "BAHIA",
    "BOTAFOGO",
    "BRAGANTINO",
    "CEARÁ",
    "CHAPECOENSE",
    "CORINTHIANS",
    "CORITIBA",
    "CRUZEIRO",
    "FLAMENGO",
    "FLUMINENSE",
    "FORTALEZA",
    "GRÊMIO",
    "INTERNACIONAL",
    "JUVENTUDE",
    "MIRASSOL",
    "PALMEIRAS",
    "REMO",
    "SANTOS",
    "SÃO PAULO",
    "SPORT",
    "VASCO",
    "VITÓRIA",
]

MANUAL_PHOTO_OVERRIDES = {
    "SANTOS": OrderedDict(
        {
            "CUCA": "https://cdn-img.zerozero.pt/img/treinadores/005/1005_cuca_1774056665.jpg",
        }
    )
}


def download_crx(extension_id: str, output_name: str) -> Path:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    crx_path = TMP_DIR / f"{output_name}.crx"
    url = (
        "https://clients2.google.com/service/update2/crx"
        "?response=redirect"
        "&prodversion=131.0.0.0"
        "&acceptformat=crx2,crx3"
        f"&x=id%3D{extension_id}%26installsource%3Dondemand%26uc"
    )
    response = requests.get(url, timeout=60, allow_redirects=True)
    response.raise_for_status()
    crx_path.write_bytes(response.content)
    return crx_path


def unpack_crx(crx_path: Path, output_name: str) -> Path:
    raw_bytes = crx_path.read_bytes()
    zip_offset = raw_bytes.find(b"PK\x03\x04")
    if zip_offset < 0:
        raise RuntimeError(f"Não foi possível localizar o ZIP interno em {crx_path.name}")

    zip_path = TMP_DIR / f"{output_name}.zip"
    extract_dir = TMP_DIR / output_name
    zip_path.write_bytes(raw_bytes[zip_offset:])
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)

    return extract_dir


def parse_primary_extension(extract_dir: Path) -> dict[str, OrderedDict[str, str]]:
    script_path = extract_dir / "scripts" / "cartola_imgs.js"
    text = script_path.read_text(encoding="utf-8")

    object_pattern = re.compile(r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{(.*?)\n\};", re.S)
    entry_pattern = re.compile(r'"([^"]+)"\s*:\s*"([^"]+)"')

    teams: dict[str, OrderedDict[str, str]] = {}
    for variable_name, body in object_pattern.findall(text):
        team_name = EXT1_TEAM_MAP.get(variable_name)
        if not team_name:
            continue
        team_entries = OrderedDict()
        for player_name, url in entry_pattern.findall(body):
            team_entries[player_name] = url
        teams[team_name] = team_entries
    return teams


def parse_secondary_extension(extract_dir: Path) -> dict[str, OrderedDict[str, str]]:
    config_path = extract_dir / "config.js"
    text = config_path.read_text(encoding="utf-8")

    start_index = text.find("const JOGADORES = {")
    end_index = text.find("window.CARTOLA_CONFIG")
    if start_index < 0 or end_index < 0:
        raise RuntimeError("Não foi possível localizar o bloco JOGADORES na extensão secundária.")

    blob = text[start_index:end_index]
    team_pattern = re.compile(r"'([A-Z]{3})':\s*\{(.*?)\n\s*\},", re.S)
    entry_pattern = re.compile(r"'([^']+)'\s*:\s*'([^']+)'")

    sigla_to_team = {
        "FLA": "FLAMENGO",
        "FLU": "FLUMINENSE",
        "INT": "INTERNACIONAL",
        "BOT": "BOTAFOGO",
        "SAO": "SÃO PAULO",
        "COR": "CORINTHIANS",
        "MIR": "MIRASSOL",
        "CAM": "ATLÉTICO-MG",
        "CFC": "CORITIBA",
        "VIT": "VITÓRIA",
        "CHA": "CHAPECOENSE",
        "GRE": "GRÊMIO",
        "CRU": "CRUZEIRO",
        "BAH": "BAHIA",
        "VAS": "VASCO",
        "PAL": "PALMEIRAS",
        "CAP": "ATHLETICO-PR",
        "RBB": "BRAGANTINO",
        "REM": "REMO",
        "SAN": "SANTOS",
    }

    teams: dict[str, OrderedDict[str, str]] = {}
    for team_sigla, body in team_pattern.findall(blob):
        team_name = sigla_to_team.get(team_sigla)
        if not team_name:
            continue
        team_entries = OrderedDict()
        for player_name, url in entry_pattern.findall(body):
            team_entries[player_name] = url
        teams[team_name] = team_entries
    return teams


def parse_existing_html() -> tuple[str, dict[str, OrderedDict[str, str]]]:
    html_text = HTML_FILE.read_text(encoding="utf-8")
    match = re.search(r"const CLUBES = (\{.*?\});\s*const TODOS = \[\];", html_text, re.S)
    if not match:
        raise RuntimeError("Não foi possível localizar o bloco CLUBES no HTML atual.")

    source_data = json.loads(match.group(1), object_pairs_hook=OrderedDict)
    teams: dict[str, OrderedDict[str, str]] = {}
    for team_name, players in source_data.items():
        teams[team_name] = OrderedDict(players)
    return html_text, teams


def merge_sources(
    primary: dict[str, OrderedDict[str, str]],
    secondary: dict[str, OrderedDict[str, str]],
    existing: dict[str, OrderedDict[str, str]],
    manual: dict[str, OrderedDict[str, str]],
) -> tuple[dict[str, OrderedDict[str, str]], dict[str, dict[str, int]]]:
    merged: dict[str, OrderedDict[str, str]] = {}
    stats: dict[str, dict[str, int]] = {}

    all_teams = []
    seen = set()
    for team_name in TEAM_ORDER + list(primary.keys()) + list(secondary.keys()) + list(existing.keys()) + list(manual.keys()):
        if team_name not in seen:
            seen.add(team_name)
            all_teams.append(team_name)

    for team_name in all_teams:
        merged_players: OrderedDict[str, str] = OrderedDict()
        source_stats = {"primary": 0, "secondary": 0, "existing": 0, "manual": 0}

        for source_name, source_data in (
            ("primary", primary),
            ("secondary", secondary),
            ("existing", existing),
            ("manual", manual),
        ):
            for player_name, url in source_data.get(team_name, {}).items():
                if player_name not in merged_players:
                    merged_players[player_name] = url
                    source_stats[source_name] += 1

        if merged_players:
            merged[team_name] = merged_players
            stats[team_name] = source_stats

    return merged, stats


def backup_html() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = HTML_FILE.with_name(f"{HTML_FILE.stem}.backup_{timestamp}{HTML_FILE.suffix}")
    shutil.copy2(HTML_FILE, backup_path)
    return backup_path


def write_html(template_text: str, clubs_data: dict[str, OrderedDict[str, str]]) -> None:
    clubs_json = json.dumps(clubs_data, ensure_ascii=False)
    replacement = f"const CLUBES = {clubs_json};\n\nconst TODOS = [];"
    updated_text, replacements = re.subn(
        r"const CLUBES = \{.*?\};\s*const TODOS = \[\];",
        replacement,
        template_text,
        flags=re.S,
    )
    if replacements != 1:
        raise RuntimeError("Falha ao substituir o bloco CLUBES no HTML.")
    HTML_FILE.write_text(updated_text, encoding="utf-8")


def main() -> int:
    print("Reconstruindo banco de fotos a partir das extensões publicadas...")

    primary_crx = download_crx(PRIMARY_EXTENSION_ID, "extensao_principal")
    secondary_crx = download_crx(SECONDARY_EXTENSION_ID, "extensao_secundaria")

    primary_dir = unpack_crx(primary_crx, "extensao_principal_unpacked")
    secondary_dir = unpack_crx(secondary_crx, "extensao_secundaria_unpacked")

    primary_data = parse_primary_extension(primary_dir)
    secondary_data = parse_secondary_extension(secondary_dir)
    template_text, existing_data = parse_existing_html()

    merged_data, stats = merge_sources(primary_data, secondary_data, existing_data, MANUAL_PHOTO_OVERRIDES)
    backup_path = backup_html()
    write_html(template_text, merged_data)

    total_entries = sum(len(players) for players in merged_data.values())
    print(f"Backup criado em: {backup_path}")
    print(f"Arquivo atualizado: {HTML_FILE}")
    print(f"Total de times no banco consolidado: {len(merged_data)}")
    print(f"Total de entradas no banco consolidado: {total_entries}")
    print("Resumo por time (principal / secundária / banco antigo / manual):")
    for team_name in TEAM_ORDER:
        if team_name not in stats:
            continue
        source_stats = stats[team_name]
        team_total = len(merged_data[team_name])
        print(
            f"- {team_name}: {team_total} entradas "
            f"(principal={source_stats['primary']}, secundária={source_stats['secondary']}, "
            f"antigo={source_stats['existing']}, manual={source_stats['manual']})"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
