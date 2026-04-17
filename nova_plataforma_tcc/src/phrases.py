from .config import POSITION_CONFIG
from .utils import join_with_e, team_name_with_article


DEFENSIVE_PROFILE_TEXT = {
    "SG": "para SG",
    "ESTATISTICO": "pelas estatísticas",
    "ESTRATEGICO": "pela estratégia",
    "BOA FASE": "pela boa fase",
}

OFFENSIVE_PROFILE_TEXT = {
    "CONFRONTO": "pelo confronto",
    "BOA FASE": "pela boa fase",
    "ESTATISTICO": "pelas estatísticas",
    "ESTRATEGICO": "pela estratégia",
}

MANDO_LABELS = {
    "CASA": "em casa",
    "FORA": "fora de casa",
}


def pluralize(value: int, singular: str, plural: str | None = None) -> str:
    if value == 1:
        return singular
    return plural or f"{singular}s"


def format_count(value: int, singular: str, plural: str | None = None) -> str:
    return f"{value} {pluralize(value, singular, plural)}"


def format_points(value: float) -> str:
    return f"{value:.2f} pontos"


def format_sg_count(value: int, qualifier: str | None = None) -> str:
    if value == 0:
        base = "nenhum SG"
    elif value == 1:
        base = "1 SG"
    else:
        base = f"{value} SGs"

    if not qualifier:
        return base
    if value in {0, 1}:
        return f"{base} {qualifier}"
    return f"{base} {pluralize(value, qualifier)}"


def format_participations(value: int) -> str:
    return f"{format_count(value, 'participação', 'participações')} em gols"


def format_recent_window(value: int, mando: str, filter_mode: str, possessive: bool = False) -> str:
    scope = f" {MANDO_LABELS[mando]}" if filter_mode == "POR_MANDO" and mando in MANDO_LABELS else ""

    if value <= 0:
        base = "em seu recorte recente" if possessive else "no recorte recente"
    elif value == 1:
        base = "em seu último jogo" if possessive else "no último jogo"
    else:
        base = f"em seus últimos {value} jogos" if possessive else f"nos últimos {value} jogos"

    return f"{base}{scope}"


def format_record_window(value: int, mando: str, filter_mode: str) -> str:
    if value <= 0:
        return "no recorte recente"
    if filter_mode == "POR_MANDO" and mando in MANDO_LABELS:
        if value == 1:
            return f"no único jogo {MANDO_LABELS[mando]}"
        return f"em {value} {pluralize(value, 'jogo')} {MANDO_LABELS[mando]}"
    return format_recent_window(value, mando, filter_mode)


def opponent_mando(player_mando: str) -> str:
    return "FORA" if player_mando == "CASA" else "CASA"


def build_intro(position_key: str, profiles: list[str]) -> str:
    role = POSITION_CONFIG[position_key]["role"]
    style = POSITION_CONFIG[position_key]["profile_style"]
    profile_map = DEFENSIVE_PROFILE_TEXT if style == "defensive" else OFFENSIVE_PROFILE_TEXT
    translated = [profile_map.get(profile) for profile in profiles if profile_map.get(profile)]

    if not translated:
        return f"Indicado como bom {role}."

    if translated[0] == "para SG" and len(translated) > 1:
        return f"Indicado como bom {role} para SG, {join_with_e(translated[1:])}."

    return f"Indicado como bom {role} {join_with_e(translated)}."


def build_phrase(
    position_key: str,
    opponent_name: str,
    profiles: list[str],
    own_stats: dict,
    opp_stats: dict,
    player_mando: str,
    filter_mode: str,
) -> str:
    role = POSITION_CONFIG[position_key]["role"]
    opponent_label = team_name_with_article(opponent_name)
    rival_mando = opponent_mando(player_mando)

    if role == "tecnico":
        own_games = own_stats.get("games", 0)
        opp_games = opp_stats.get("games", 0)
        return (
            f"Indicado como bom técnico, com média de {format_points(own_stats['avg_points'])}, "
            f"somando {format_count(own_stats['wins'], 'vitória')} {format_record_window(own_games, player_mando, filter_mode)}. "
            f"Enfrenta {opponent_label}, que cedeu em média {format_points(opp_stats['avg_points'])} para técnicos adversários "
            f"{format_recent_window(opp_games, rival_mando, filter_mode, possessive=True)}, "
            f"sofrendo {format_count(opp_stats['wins'], 'derrota')} nesse recorte."
        )

    intro = build_intro(position_key, profiles)
    games = own_stats.get("games", 0)
    opponent_games = opp_stats.get("games", 0)

    if role == "goleiro":
        return (
            f"{intro} Conquistou {format_count(own_stats['de'], 'defesa')} {format_recent_window(games, player_mando, filter_mode)}, "
            f"com {own_stats['pct_de']}% de defesas e {format_sg_count(own_stats['sg'], 'conquistado')}. "
            f"Enfrenta {opponent_label}, que cedeu {format_count(opp_stats['de'], 'defesa')} "
            f"{format_recent_window(opponent_games, rival_mando, filter_mode, possessive=True)}, "
            f"com {opp_stats['pct_de']}% de defesas cedidas e {format_sg_count(opp_stats['sg'], 'cedido')}."
        )

    if role in {"lateral", "zagueiro"}:
        role_label = "laterais" if role == "lateral" else "zagueiros"
        conceded_target = opp_stats.get("lateral_side") if role == "lateral" and opp_stats.get("lateral_side") else role_label
        return (
            f"{intro} Conquistou {format_count(own_stats['ds'], 'desarme')}, {format_sg_count(own_stats['sg'])} e "
            f"{format_participations(own_stats['pg'])} {format_recent_window(games, player_mando, filter_mode)}. "
            f"Enfrenta {opponent_label}, que cedeu {format_count(opp_stats['ds'], 'desarme')}, "
            f"{format_sg_count(opp_stats['sg'])} e {format_participations(opp_stats['pg'])} para {conceded_target} "
            f"{format_recent_window(opponent_games, rival_mando, filter_mode, possessive=True)}."
        )

    role_label = "meias" if role == "meia" else "atacantes"
    return (
        f"{intro} Conquistou {format_count(own_stats['shots'], 'finalização', 'finalizações')} e "
        f"{format_count(own_stats['shots_on_target'], 'chute a gol', 'chutes a gol')} "
        f"{format_recent_window(games, player_mando, filter_mode)}. "
        f"Enfrenta {opponent_label}, que cedeu {format_count(opp_stats['shots'], 'finalização', 'finalizações')}, "
        f"{format_count(opp_stats['shots_on_target'], 'chute a gol', 'chutes a gol')} e "
        f"{format_participations(opp_stats['pg'])} para {role_label} "
        f"{format_recent_window(opponent_games, rival_mando, filter_mode, possessive=True)}."
    )
