"""Seleção dos mais escalados do Cartola (painel público do Gato Mestre).

A página publica o "time ideal" dos mais escalados: 1 goleiro, 2 laterais, 2 zagueiros, 3 meias, 3 atacantes
e 1 técnico (titulares), mais reservas, cada um com o número de times que o escalou. Ela NÃO informa capitão.

Os números só são finais com o mercado FECHADO; por isso a captura só é guardada nessa situação
(quando o mercado reabre a página passa a mostrar a rodada seguinte).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from .config import ROOT_PROJECT_DIR
from .feedback import POSITION_ORDER, now_iso
from .utils import resolve_team_name

GATO_URL = "https://gatomestre.ge.globo.com/mais-escalados-do-cartola/"
MARKET_URL = "https://api.cartola.globo.com/atletas/mercado"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
POSITION_BY_CODE = {"gol": "Goleiros", "lat": "Laterais", "zag": "Zagueiros", "mei": "Meias", "ata": "Atacantes", "tec": "Técnicos"}
STARTERS = {"Goleiros": 1, "Laterais": 2, "Zagueiros": 2, "Meias": 3, "Atacantes": 3, "Técnicos": 1}
REPO_ARCHIVE_DIR = ROOT_PROJECT_DIR / "data" / "mais_escalados"

# Capitães e top 20 geral: foto tirada de tempos em tempos pela outra plataforma do Renato (dado de terceiros,
# Cartomante FC). O Gato Mestre não publica capitão.
H2H_URL = "https://dashboard.h2hscout.com/api/provaveis-escalados"
CAPTAIN_MAX_MINUTES_BEFORE_CLOSE = 90   # além disso o capitão é marcado como estimado


def _pick(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def parse_html(html: str) -> list[dict]:
    """HTML do Gato Mestre -> lista de escalados (titulares, reservas e técnico)."""
    players, seen = [], set()
    for block in re.split(r'(?=data-atletaid=")', html):
        athlete_id = _pick(r'^data-atletaid="(\d+)"', block)
        if not athlete_id or athlete_id in seen:
            continue
        code = _pick(r"cartola-atletas--posicao__(\w+)", block)
        name = _pick(r'class="apelido-abreviado"[^>]*>([^<]+)<', block)
        count = _pick(r'GM-pontuacao-flutuante[^"]*"[^>]*>\s*([\d.,]+)\s*<', block)
        if not (code and name and count and code in POSITION_BY_CODE):
            continue
        sheet = _pick(r'data-atletaficha="([^"]+)"', block) or ""
        seen.add(athlete_id)
        players.append(
            {
                "athlete_id": int(athlete_id),
                "name": name.strip(),
                "position": POSITION_BY_CODE[code],
                "group": "tecnico" if code == "tec" else ("reserva" if sheet.startswith("reservas") else "titular"),
                "count": int(re.sub(r"\D", "", count)),
                "club_code": _pick(r"/escudos/([A-Z]{3})/", block) or _pick(r"/silhuetas/([A-Z]{3})/", block) or "",
            }
        )
    return sorted(players, key=lambda p: -p["count"])


def fetch_most_escalated(timeout: int = 30) -> dict:
    response = requests.get(GATO_URL, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=timeout)
    response.raise_for_status()
    players = parse_html(response.text)

    # nome completo/clube vêm do mercado público (o painel só traz o nome abreviado)
    market = requests.get(MARKET_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout).json()
    clubs = market.get("clubes", {})
    by_id = {a["atleta_id"]: a for a in market.get("atletas", [])}
    for player in players:
        athlete = by_id.get(player["athlete_id"])
        if athlete:
            club = clubs.get(str(athlete.get("clube_id")), {})
            player["name"] = athlete.get("apelido") or player["name"]
            player["full_name"] = athlete.get("nome", "")
            player["team"] = resolve_team_name(club.get("nome_fantasia") or club.get("apelido") or player["club_code"])
        else:
            player["full_name"] = ""
            player["team"] = resolve_team_name(player["club_code"])
    return {"source": GATO_URL, "captured_at": now_iso(), "players": players}


def fetch_captains(close_timestamp: int | None = None, timeout: int = 30) -> dict | None:
    """Top 5 capitães e top 20 geral (fonte de terceiros), com a idade da foto em relação ao fechamento do mercado."""
    try:
        response = requests.get(H2H_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None

    def clean(item: dict) -> dict:
        return {"rank": item.get("rank"), "athlete_id": item.get("atletaId"), "name": item.get("nome"),
                "club": item.get("clube"), "position": item.get("pos"), "count": item.get("contagem")}

    result = {
        "source": "Cartomante FC (terceiro) via dashboard.h2hscout.com",
        "generated_at": data.get("geradoEm"),
        "age_hours_when_captured": data.get("idadeHoras"),
        "captains": [clean(c) for c in data.get("capitaes", [])],
        "top20": [clean(c) for c in data.get("escalados", [])],
        "minutes_before_close": None,
    }
    if close_timestamp and data.get("geradoEm"):
        from datetime import datetime

        generated = datetime.fromisoformat(data["geradoEm"].replace("Z", "+00:00")).timestamp()
        result["minutes_before_close"] = round((close_timestamp - generated) / 60, 1)
    return result


def starters(payload: dict) -> list[dict]:
    """Os 12 titulares do time dos mais escalados (1-2-2-3-3 + técnico), na ordem das posições."""
    picked: list[dict] = []
    for position in POSITION_ORDER:
        pool = [p for p in payload["players"] if p["position"] == position and p["group"] != "reserva"]
        picked.extend(sorted(pool, key=lambda p: -p["count"])[: STARTERS[position]])
    return picked


def build_team(payload: dict, results: dict) -> dict:
    """Time dos mais escalados com a pontuação real de cada um (sem capitão: a fonte não informa)."""
    team = []
    for player in starters(payload):
        result = results["players"].get(player["athlete_id"])
        played = bool(result and result["played"])
        team.append(
            {
                "athlete_id": player["athlete_id"],
                "name": player["name"],
                "full_name": player.get("full_name", ""),
                "team": player["team"],
                "position": player["position"],
                "count": player["count"],
                "played": played,
                "points": result["points"] if played else 0.0,
            }
        )
    captain_id, bonus, note = None, 0.0, ""
    captains = (payload.get("captain_data") or {}).get("captains") or []
    in_team = {p["athlete_id"]: p for p in team if p["position"] != "Técnicos"}
    for candidate in sorted(captains, key=lambda c: c.get("rank") or 99):
        if candidate.get("athlete_id") in in_team:
            captain_id = candidate["athlete_id"]
            bonus = round(0.5 * in_team[captain_id]["points"], 2)
            minutes = (payload.get("captain_data") or {}).get("minutes_before_close")
            if minutes is not None and minutes > CAPTAIN_MAX_MINUTES_BEFORE_CLOSE:
                note = f"capitão estimado: dado de terceiros colhido {minutes / 60:.0f} h antes do fechamento"
            break
    total = round(sum(p["points"] for p in team) + bonus, 2)
    return {
        "players": team,
        "total": total,
        "captain_id": captain_id,
        "captain_bonus": bonus,
        "captain_note": note,
        "captured_at": payload.get("captured_at"),
    }


# ---- arquivo de segurança dentro do repositório (não depende do Supabase) ---------------------

def save_repo_archive(round_number: int, payload: dict) -> Path:
    REPO_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = REPO_ARCHIVE_DIR / f"r{int(round_number):02d}.json"
    path.write_text(json.dumps({**payload, "round": int(round_number)}, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load_repo_archive(round_number: int) -> dict | None:
    path = REPO_ARCHIVE_DIR / f"r{int(round_number):02d}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
