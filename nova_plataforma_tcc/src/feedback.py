"""Feedback pós-rodada: registra as indicações, cruza com o desempenho real e monta as seleções.

Sem dependência do Streamlit. Pontos e scouts vêm da API pública do Cartola (/atletas/pontuados).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import requests

from .config import POSITION_CONFIG
from .utils import normalize_text, resolve_team_name

PONTUADOS_URL = "https://api.cartola.globo.com/atletas/pontuados"
SNAPSHOT_VERSION = 1

POSITION_BY_ID = {1: "Goleiros", 2: "Laterais", 3: "Zagueiros", 4: "Meias", 5: "Atacantes", 6: "Técnicos"}
POSITION_ORDER = ["Goleiros", "Laterais", "Zagueiros", "Meias", "Atacantes", "Técnicos"]

# (goleiro, lateral, zagueiro, meia, atacante); o técnico é sempre 1
FORMATIONS = {
    "4-3-3": (1, 2, 2, 3, 3),
    "3-4-3": (1, 0, 3, 4, 3),
    "4-4-2": (1, 2, 2, 4, 2),
    "3-5-2": (1, 0, 3, 5, 2),
    "4-5-1": (1, 2, 2, 5, 1),
    "5-3-2": (1, 2, 3, 3, 2),
    "5-4-1": (1, 2, 3, 4, 1),
}
DEFAULT_FORMATION = "4-3-3"
CAPTAIN_MULTIPLIER = 1.5

# Defensores (goleiro, lateral, zagueiro) são avaliados pela MÉDIA BÁSICA dos últimos 5 jogos:
# pontuação sem gol, assistência, SG, defesa de pênalti etc. Bateu a própria média básica = foi bem.
BASIC_POSITIONS = {"Goleiros", "Laterais", "Zagueiros"}
BASIC_WINDOW = 5
# CRITÉRIO DE BOA PONTUAÇÃO por posição (definido pelo Renato e pelo Lucas): (pontos mínimos, pontos mínimos SEM SG).
# Goleiro/zagueiro: 4 pts sempre é bom; sem SG, 3 pts já é bom. Lateral: 5 (3,5 sem SG).
# Meia/atacante (sem SG): 6. Técnico: 5. A comparação com a média do jogador e com a média da posição é só informação.
GOOD_SCORE = {
    "Goleiros": (4.0, 3.0),
    "Zagueiros": (4.0, 3.0),
    "Laterais": (5.0, 3.5),
    "Meias": (6.0, 6.0),
    "Atacantes": (6.0, 6.0),
    "Técnicos": (5.0, 5.0),
}
HAS_SG = {"Goleiros", "Laterais", "Zagueiros"}

MITOU_POINTS = 10.0          # "mitou" = mais de 10 pontos
TOP_RANK_FOR_BADGES = 5      # capitão/RL correspondem se ficarem no top N da posição na rodada

# Scouts que justificam a indicação por posição (estatística/confronto): (chave, rótulo)
REFERENCE_SCOUTS = {
    "Goleiros": [("DE", "defesas")],
    "Laterais": [("DS", "desarmes"), ("PG", "G+A")],
    "Zagueiros": [("DS", "desarmes"), ("PG", "G+A")],
    "Meias": [("PG", "G+A"), ("CHT_AG", "chutes a gol")],
    "Atacantes": [("PG", "G+A"), ("CHT_AG", "chutes a gol")],
    "Técnicos": [],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def position_key_of(position_id: int) -> str | None:
    return POSITION_BY_ID.get(int(position_id))


# ---------------------------------------------------------------- resultados (API) -------------

def basic_points(points: float, scout: dict, position_key: str) -> float | None:
    """Média básica do jogo = pontos sem gols, assistências, SG, defesa de pênalti etc.
    (mesma conta da planilha de scouts). Técnicos não têm pontuação básica."""
    if position_key == "Técnicos":
        return None
    s = lambda key: float(scout.get(key, 0) or 0)  # noqa: E731
    extras = 8 * s("G") + 5 * s("A") + 5 * s("SG") + 7 * s("DP") - 4 * s("PP") - 3 * s("GC") - 3 * s("CV")
    return round(points - extras, 2)


def scout_value(scout: dict, key: str) -> float:
    s = lambda k: float(scout.get(k, 0) or 0)  # noqa: E731
    if key == "PG":
        return s("G") + s("A")
    if key == "CHT_AG":
        return s("FD") + s("G")
    return s(key)


def latest_round_number(timeout: int = 20) -> int:
    """Rodada mais recente com pontuação: a atual se o mercado está fechado (em andamento), senão a anterior."""
    market = fetch_market_status(timeout)
    current = int(market.get("rodada_atual") or 0)
    return current if market.get("status_mercado") == 2 else current - 1


def fetch_round_results(round_number: int | None = None, timeout: int = 30) -> dict:
    """Pontuação de uma rodada: {'round': n, 'players': {atleta_id: {...}}}.

    Usa /atletas/pontuados/<rodada>, que funciona para qualquer rodada já jogada. O endereço sem número
    devolve vazio (204) depois que o mercado reabre. Sem `round_number`, usa a rodada mais recente.
    """
    if round_number is None:
        round_number = latest_round_number(timeout)
    response = requests.get(f"{PONTUADOS_URL}/{int(round_number)}", headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
    if response.status_code in (204, 400, 404) or not response.content.strip():
        raise RuntimeError(f"O Cartola ainda não liberou a pontuação da rodada {round_number}.")
    response.raise_for_status()
    payload = response.json()
    clubs = payload.get("clubes", {})
    players: dict[int, dict] = {}
    for athlete_id, data in (payload.get("atletas") or {}).items():
        position_key = position_key_of(data.get("posicao_id", 0))
        if not position_key:
            continue
        club = clubs.get(str(data.get("clube_id")), {})
        scout = data.get("scout") or {}
        points = float(data.get("pontuacao") or 0.0)
        players[int(athlete_id)] = {
            "athlete_id": int(athlete_id),
            "name": data.get("apelido", ""),
            "team": resolve_team_name(club.get("nome_fantasia") or club.get("apelido") or ""),
            "team_slug": club.get("slug", ""),
            "position": position_key,
            "points": points,
            "basic": basic_points(points, scout, position_key),
            "scout": scout,
            "played": bool(data.get("entrou_em_campo")),
        }
    return {"round": int(payload.get("rodada") or 0), "players": players, "fetched_at": now_iso()}


# ---------------------------------------------------------------- registro das indicações ------

def _archive_points(entry: dict, archive: dict[int, dict] | None, after_round: int, before_round: int) -> list[tuple[int, float, float | None]]:
    """Pontos do jogador nas rodadas arquivadas da API que a planilha ainda não cobre."""
    extra = []
    team, names = normalize_text(entry["team"]), {normalize_text(entry["name"]), normalize_text(entry.get("full_name", ""))}
    for round_number, results in sorted((archive or {}).items()):
        if not after_round < round_number < before_round:
            continue
        found = results["players"].get(entry.get("athlete_id")) if entry.get("athlete_id") not in (None, "") else None
        if found is None:
            found = next(
                (r for r in results["players"].values()
                 if normalize_text(r["team"]) == team and normalize_text(r["name"]) in names),
                None,
            )
        if found and found["played"]:
            extra.append((round_number, found["points"], found["basic"]))
    return extra


def player_baseline(
    analyzer,
    player: dict,
    position_key: str,
    target_round: int,
    window_n: int,
    filter_mode: str,
    archive: dict[int, dict] | None = None,
) -> dict:
    """Números de referência congelados no momento da indicação (o que o card mostrava).

    Histórico = planilha de scouts + rodadas já arquivadas da API que a planilha ainda não tem.
    """
    team = resolve_team_name(player["team"])
    df = analyzer.df_games
    season = df[
        (df["TIME_NORM"] == normalize_text(team))
        & (df["NOME_NORM"] == normalize_text(player["name"]))
        & (df["RODADA"] < target_round)
    ]
    season = analyzer.filter_position_rows(season, position_key).sort_values("DATA")
    window = analyzer.get_player_rows(
        player["name"], team, target_round, position_key,
        target_mando=analyzer.get_match_context(team, target_round).mando,
        window_n=window_n, filter_mode=filter_mode,
    )

    sheet_last_round = int(df["RODADA"].max())
    extra = _archive_points(player, archive, sheet_last_round, target_round)
    season_points = [float(v) for v in season["PTS"]] + [pts for _, pts, _ in extra]
    season_basic = [float(v) for v in season["BASICA"]] + [b for _, _, b in extra if b is not None]

    def avg(values):
        return round(sum(values) / len(values), 2) if values else None

    refs = {}
    for key, _label in REFERENCE_SCOUTS.get(position_key, []):
        if not len(window):
            refs[key] = None
        elif key == "PG":
            refs[key] = round(float((window["G"] + window["A"]).mean()), 2)
        elif key == "CHT_AG":
            refs[key] = round(float((window["FD"] + window["G"]).mean()), 2)
        else:
            refs[key] = round(float(window[key].mean()), 2)

    return {
        "games_season": len(season_points),
        "avg_points_season": avg(season_points),
        "avg_points_last3": avg(season_points[-3:]),
        "avg_points_window": round(float(window["PTS"].mean()), 2) if len(window) else None,
        "avg_basic_season": avg(season_basic),
        "avg_basic_last5": avg(season_basic[-BASIC_WINDOW:]),
        "games_basic_last5": len(season_basic[-BASIC_WINDOW:]),
        "ref_scouts": refs,
        "sheet_last_round": sheet_last_round,
        "archive_rounds_used": [r for r, _, _ in extra],
    }


def missing_history_rounds(analyzer, archive: dict[int, dict] | None, target_round: int) -> list[int]:
    """Rodadas entre o fim da planilha e a rodada-alvo que não estão arquivadas (médias ficariam defasadas)."""
    sheet_last_round = int(analyzer.df_games["RODADA"].max())
    return [r for r in range(sheet_last_round + 1, target_round) if r not in (archive or {})]


def enrich_snapshot(analyzer, snapshot: dict, archive: dict[int, dict] | None = None) -> dict:
    """Completa registros salvos antes de existir a média básica dos últimos 5 jogos.

    Recalcula só os campos que faltam, com os dados disponíveis até a rodada-alvo; os valores já congelados são mantidos.
    """
    enriched = {**snapshot, "players": [dict(p) for p in snapshot["players"]]}
    for entry in enriched["players"]:
        old = entry.get("baseline") or {}
        if "avg_basic_last5" in old:
            continue
        fresh = player_baseline(
            analyzer, entry, entry["position"], enriched["round"],
            enriched.get("window_n", 3), enriched.get("filter_mode", "POR_MANDO"), archive,
        )
        entry["baseline"] = {**fresh, **old}
    return enriched


def build_snapshot(
    analyzer,
    players_by_position: dict[str, list[dict]],
    target_round: int,
    window_n: int,
    filter_mode: str,
    project: str = "tcc",
    archive: dict[int, dict] | None = None,
) -> dict:
    entries = []
    for position_key in POSITION_ORDER:
        for order, player in enumerate(players_by_position.get(position_key, []), start=1):
            entries.append(
                {
                    "athlete_id": player.get("athlete_id"),
                    "name": player["name"],
                    "full_name": player.get("full_name", ""),
                    "team": resolve_team_name(player["team"]),
                    "position": position_key,
                    "order": order,
                    "price": float(player.get("price", 0.0)),
                    "mpv": float(player.get("mpv", 0.0)),
                    "confidence": player.get("confidence", "A"),
                    "profiles": list(player.get("profiles", [])),
                    "badges": dict(player.get("badges", {})),
                    "baseline": player_baseline(analyzer, player, position_key, target_round, window_n, filter_mode, archive),
                }
            )
    return {
        "version": SNAPSHOT_VERSION,
        "project": project,
        "round": int(target_round),
        "window_n": int(window_n),
        "filter_mode": filter_mode,
        "saved_at": now_iso(),
        "players": entries,
    }


# ---------------------------------------------------------------- avaliação ---------------------

def _check(key: str, label: str, status: str, detail: str) -> dict:
    return {"key": key, "label": label, "status": status, "detail": detail}


def _fmt(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") if value % 1 else f"{int(value)}"


def evaluate_player(entry: dict, result: dict | None, position_rank: int | None, captain_ids: set, luxury_ids: set,
                    position_averages: dict | None = None) -> dict:
    """Cruza uma indicação com o desempenho. status: ok | fail | info | na"""
    position_key = entry["position"]
    baseline = entry.get("baseline") or {}
    evaluated = {**entry, "played": False, "points": None, "basic": None, "scout": {}, "rank_position": position_rank,
                 "tier": "nao_jogou", "checks": []}
    if not result or not result["played"]:
        return evaluated

    points = result["points"]
    scout = result["scout"]
    evaluated.update(played=True, points=points, basic=result["basic"], scout=scout)
    season_avg = baseline.get("avg_points_season")
    last3_avg = baseline.get("avg_points_last3")
    checks = evaluated["checks"]

    # ---- critério de boa pontuação (decide positivo/negativo) ----
    has_sg = scout_value(scout, "SG") > 0
    full_limit, no_sg_limit = GOOD_SCORE[position_key]
    if position_key in HAS_SG:
        limit = full_limit if has_sg else no_sg_limit
        sg_text = "com SG" if has_sg else "sem SG"
        criterion = (
            f"{_fmt(points)} pts {sg_text}: bom a partir de {_fmt(limit)}"
            if full_limit != no_sg_limit
            else f"{_fmt(points)} pts: bom a partir de {_fmt(limit)}"
        )
    else:
        limit = full_limit
        criterion = f"{_fmt(points)} pts: bom a partir de {_fmt(limit)}"
    is_good = points >= limit
    evaluated.update(
        is_good=bool(is_good), criterion_limit=limit, criterion_text=criterion, has_sg=bool(has_sg),
    )
    checks.append(_check("criterio", "Pontuação", "ok" if is_good else "fail", criterion))

    # ---- referências (só informação, não julgam) ----
    position_avg = (position_averages or {}).get(position_key)
    own_avg = season_avg
    evaluated.update(position_avg=position_avg, own_avg=own_avg)
    basic_now = result.get("basic")
    basic_avg = baseline.get("avg_basic_last5")
    basic_games = baseline.get("games_basic_last5") or 0
    uses_basic = position_key in BASIC_POSITIONS and basic_now is not None
    if uses_basic:
        games_text = f"últimos {basic_games} jogos" if basic_games != 1 else "último jogo"
        if basic_avg is not None:
            relation = "acima" if basic_now >= basic_avg else "abaixo"
            checks.append(_check("ref_basica", "Média básica", "ref",
                                 f"básica {_fmt(basic_now)}, {relation} da média básica dos {games_text} ({_fmt(basic_avg)})"))
        else:
            checks.append(_check("ref_basica", "Média básica", "ref", f"básica {_fmt(basic_now)} (sem histórico)"))
    evaluated.update(
        uses_basic=uses_basic, basic_avg=basic_avg, basic_games=basic_games,
        basic_beat=bool(uses_basic and basic_avg is not None and basic_now >= basic_avg),
    )

    # camada geral: mitou (>10) | bom (critério da posição) | abaixo
    if points > MITOU_POINTS:
        evaluated["tier"] = "mitou"
    else:
        evaluated["tier"] = "bom" if is_good else "abaixo"

    badges = entry.get("badges", {})
    if badges.get("unanimidade") or entry.get("confidence") == "A":
        label = "Unanimidade" if badges.get("unanimidade") else "Confiança A"
        if points > MITOU_POINTS:
            checks.append(_check("unanimidade", label, "ok", f"MITOU com {_fmt(points)} pts"))
        else:
            checks.append(_check("unanimidade", label, "ok" if is_good else "fail", criterion))

    profiles = entry.get("profiles", [])
    if "SG" in profiles:
        sg = scout_value(scout, "SG") > 0
        checks.append(_check("sg", "SG", "ok" if sg else "fail", "time não tomou gol" if sg else "time sofreu gol"))
    if "BOA FASE" in profiles:
        checks.append(_check("boa_fase", "Boa fase", "ok" if is_good else "fail", criterion))
    for profile, label in (("ESTATISTICO", "Estatística"), ("CONFRONTO", "Confronto")):
        if profile in profiles:
            refs = REFERENCE_SCOUTS.get(position_key, [])
            parts, met, total = [], 0, 0
            for key, ref_label in refs:
                reference = (baseline.get("ref_scouts") or {}).get(key)
                if reference is None:
                    continue
                value = scout_value(scout, key)
                total += 1
                hit = value > 0 and value >= reference
                met += hit
                parts.append(f"{ref_label} {_fmt(value)} (méd. {_fmt(reference)})")
            if not total:
                checks.append(_check(profile.lower(), label, "na", "sem histórico"))
            else:
                checks.append(_check(profile.lower(), label, "ok" if met >= math.ceil(total / 2) else "fail", "; ".join(parts)))
    if "ESTRATEGICO" in profiles:
        if is_good:
            checks.append(_check("estrategico", "Estratégia", "ok", "valeu para quem escalou"))
        else:
            checks.append(_check("estrategico", "Estratégia", "info", "valeu para quem diferenciou"))

    top_label = f"top {TOP_RANK_FOR_BADGES} da posição"
    in_top = position_rank is not None and position_rank <= TOP_RANK_FOR_BADGES
    if badges.get("bom_capitao"):
        best = _best_of(captain_ids, entry["athlete_id"], points)
        checks.append(_check("capitao", "Capitão", "ok" if (in_top or best) else "fail",
                             f"{position_rank}º da posição" if position_rank else top_label))
    if badges.get("bom_rl"):
        best = _best_of(luxury_ids, entry["athlete_id"], points)
        checks.append(_check("rl", "Reserva de luxo", "ok" if (in_top or best) else "fail",
                             f"{position_rank}º da posição" if position_rank else top_label))
    return evaluated


def _best_of(group_points: set, athlete_id, points: float) -> bool:
    """group_points guarda tuplas (id, pontos) dos indicados do mesmo selo que jogaram."""
    return all(points >= other_points for other_id, other_points in group_points if other_id != athlete_id)


def position_ranks(results: dict) -> dict[int, int]:
    """Posição de cada atleta que jogou, no ranking de pontos da própria posição na rodada."""
    ranks: dict[int, int] = {}
    for position_key in POSITION_ORDER:
        scored = sorted(
            (p for p in results["players"].values() if p["position"] == position_key and p["played"]),
            key=lambda p: -p["points"],
        )
        for index, player in enumerate(scored, start=1):
            ranks[player["athlete_id"]] = index
    return ranks


def _match_without_id(entry: dict, results: dict) -> int | None:
    """Jogador cadastrado à mão (sem atleta_id): procura por time + nome na pontuação."""
    team, names = normalize_text(entry["team"]), {normalize_text(entry["name"]), normalize_text(entry.get("full_name", ""))}
    for athlete_id, data in results["players"].items():
        if normalize_text(data["team"]) == team and normalize_text(data["name"]) in names:
            return athlete_id
    return None


def position_point_averages(results: dict) -> dict[str, float]:
    """Média de pontos de todos os jogadores da posição que entraram em campo na rodada."""
    totals: dict[str, list[float]] = {}
    for player in results["players"].values():
        if player["played"]:
            totals.setdefault(player["position"], []).append(player["points"])
    return {pos: round(sum(v) / len(v), 2) for pos, v in totals.items() if v}


def evaluate_snapshot(snapshot: dict, results: dict, most_escalated: dict | None = None) -> dict:
    ranks = position_ranks(results)
    position_averages = position_point_averages(results)
    pool = results["players"]
    snapshot = {**snapshot, "players": [dict(p) for p in snapshot["players"]]}
    for entry in snapshot["players"]:
        if entry.get("athlete_id") in (None, ""):
            entry["athlete_id"] = _match_without_id(entry, results)

    def badge_pool(badge: str) -> set:
        return {
            (p["athlete_id"], pool[p["athlete_id"]]["points"])
            for p in snapshot["players"]
            if p.get("badges", {}).get(badge) and p["athlete_id"] in pool and pool[p["athlete_id"]]["played"]
        }

    captains, luxury = badge_pool("bom_capitao"), badge_pool("bom_rl")
    evaluated = [
        evaluate_player(p, pool.get(p["athlete_id"]), ranks.get(p["athlete_id"]), captains, luxury, position_averages)
        for p in snapshot["players"]
    ]
    cartola_team = build_cartola_team(results)
    cartola_ids = {p["athlete_id"] for p in cartola_team["players"]}
    for player in evaluated:
        player["in_cartola_team"] = player["athlete_id"] in cartola_ids

    escalated_team = None
    reserves: list[dict] = []
    if most_escalated and most_escalated.get("players"):
        from .most_escalated import build_team as build_escalated_team

        escalated_team = build_escalated_team(most_escalated, results)
        from .most_escalated import build_reserves

        reserves = build_reserves(most_escalated, results)

    return {
        "round": snapshot["round"],
        "players": evaluated,
        "position_averages": position_averages,
        "most_escalated": escalated_team,
        "reserves": reserves,
        "cartola_team": cartola_team,
        "my_team": best_formations(evaluated),
        "summary": summarize(evaluated),
    }


# ---------------------------------------------------------------- seleções ---------------------

def _pick(players: list[dict], position_key: str, count: int) -> list[dict]:
    pool = [p for p in players if p["position"] == position_key and p.get("played") and p.get("points") is not None]
    return sorted(pool, key=lambda p: -p["points"])[:count]


def build_cartola_team(results: dict, formation: str = DEFAULT_FORMATION) -> dict:
    players = list(results["players"].values())
    counts = dict(zip(POSITION_ORDER, (*FORMATIONS[formation], 1)))
    picks = [p for position_key in POSITION_ORDER for p in _pick(players, position_key, counts[position_key])]
    return {"formation": formation, "players": picks, "total": round(sum(p["points"] for p in picks), 2)}


def build_team(evaluated: list[dict], formation: str) -> dict | None:
    counts = dict(zip(POSITION_ORDER, (*FORMATIONS[formation], 1)))
    picks: list[dict] = []
    for position_key in POSITION_ORDER:
        chosen = _pick(evaluated, position_key, counts[position_key])
        if len(chosen) < counts[position_key]:
            return None
        picks.extend(chosen)

    # capitão: o indicado como "bom capitão" que mais pontuou (nunca técnico)
    candidates = [p for p in evaluated if p.get("badges", {}).get("bom_capitao") and p["played"]
                  and p["position"] != "Técnicos"]
    captain = max(candidates, key=lambda p: p["points"]) if candidates else None
    if captain and captain["athlete_id"] not in {p["athlete_id"] for p in picks}:
        same_position = [p for p in picks if p["position"] == captain["position"]]
        if same_position:
            picks.remove(min(same_position, key=lambda p: p["points"]))
            picks.append(captain)
    captain_id = captain["athlete_id"] if captain else None
    total = sum(p["points"] for p in picks)
    bonus = (CAPTAIN_MULTIPLIER - 1) * captain["points"] if captain else 0.0
    picks.sort(key=lambda p: POSITION_ORDER.index(p["position"]))
    return {
        "formation": formation,
        "players": picks,
        "captain_id": captain_id,
        "captain_bonus": round(bonus, 2),
        "total": round(total + bonus, 2),
    }


def best_formations(evaluated: list[dict]) -> dict:
    teams = {name: build_team(evaluated, name) for name in FORMATIONS}
    teams = {name: team for name, team in teams.items() if team}
    default = teams.get(DEFAULT_FORMATION)
    best = max(teams.values(), key=lambda t: t["total"]) if teams else None
    return {
        "default": default,
        "best": best,
        "ranking": sorted(((name, team["total"]) for name, team in teams.items()), key=lambda item: -item[1]),
    }


# ---------------------------------------------------------------- resumo -----------------------

def summarize(evaluated: list[dict]) -> dict:
    played = [p for p in evaluated if p["played"]]
    graded = [c for p in played for c in p["checks"] if c["status"] in ("ok", "fail")]
    ok = sum(1 for c in graded if c["status"] == "ok")
    ranked = sorted(played, key=lambda p: -p["points"])
    return {
        "indicated": len(evaluated),
        "played": len(played),
        "did_not_play": len(evaluated) - len(played),
        "mitou": [p for p in played if p["tier"] == "mitou"],
        "above_average": sum(1 for p in played if p["tier"] in ("bom", "mitou")),
        "checks_ok": ok,
        "checks_total": len(graded),
        "check_rate": round(100 * ok / len(graded)) if graded else 0,
        "best": ranked[:3],
        "worst": ranked[-3:][::-1] if len(ranked) > 3 else [],
        "in_cartola_team": [p for p in evaluated if p.get("in_cartola_team")],
        "unanimities_ok": sum(1 for p in played for c in p["checks"] if c["key"] == "unanimidade" and c["status"] == "ok"),
        "unanimities_total": sum(1 for p in played for c in p["checks"] if c["key"] == "unanimidade"),
        "avg_points": round(sum(p["points"] for p in played) / len(played), 2) if played else 0.0,
    }


def fetch_market_status(timeout: int = 20) -> dict:
    response = requests.get("https://api.cartola.globo.com/mercado/status", headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
    response.raise_for_status()
    return response.json()
