import base64
import unicodedata
from pathlib import Path

from .config import TEAM_ALIASES, TEAM_BADGE_SLUGS, TEAMS_DIR


TEAM_DISPLAY_NAMES = {
    "ATHLETICO-PR": "Athletico-PR",
    "ATLETICO-MG": "Atlético-MG",
    "BAHIA": "Bahia",
    "BOTAFOGO": "Botafogo",
    "CHAPECOENSE": "Chapecoense",
    "CORINTHIANS": "Corinthians",
    "CORITIBA": "Coritiba",
    "CRUZEIRO": "Cruzeiro",
    "FLAMENGO": "Flamengo",
    "FLUMINENSE": "Fluminense",
    "GREMIO": "Grêmio",
    "INTERNACIONAL": "Internacional",
    "MIRASSOL": "Mirassol",
    "PALMEIRAS": "Palmeiras",
    "RED BULL BRAGANTINO": "Red Bull Bragantino",
    "REMO": "Remo",
    "SANTOS": "Santos",
    "SAO PAULO": "São Paulo",
    "SPORT": "Sport",
    "VASCO": "Vasco",
    "VITORIA": "Vitória",
}

TEAM_ARTICLES = {
    "ATHLETICO-PR": "o",
    "ATLETICO-MG": "o",
    "BAHIA": "o",
    "BOTAFOGO": "o",
    "CHAPECOENSE": "a",
    "CORINTHIANS": "o",
    "CORITIBA": "o",
    "CRUZEIRO": "o",
    "FLAMENGO": "o",
    "FLUMINENSE": "o",
    "GREMIO": "o",
    "INTERNACIONAL": "o",
    "MIRASSOL": "o",
    "PALMEIRAS": "o",
    "RED BULL BRAGANTINO": "o",
    "REMO": "o",
    "SANTOS": "o",
    "SAO PAULO": "o",
    "SPORT": "o",
    "VASCO": "o",
    "VITORIA": "o",
}


def normalize_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    return "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    )


def resolve_team_name(team_name: str) -> str:
    normalized = normalize_text(team_name)
    return TEAM_ALIASES.get(normalized, normalized)


def team_badge_path(team_name: str) -> Path | None:
    resolved_name = resolve_team_name(team_name)
    slug = TEAM_BADGE_SLUGS.get(resolved_name)
    if not slug:
        fallback_slug = normalize_text(resolved_name).lower().replace(" ", "_").replace("-", "_")
        candidate = TEAMS_DIR / f"{fallback_slug}.png"
        return candidate if candidate.exists() else None
    candidate = TEAMS_DIR / f"{slug}.png"
    return candidate if candidate.exists() else None


def file_to_base64(file_path: Path | None) -> str:
    if not file_path or not file_path.exists():
        return ""
    return base64.b64encode(file_path.read_bytes()).decode()


def percent(numerator: float, denominator: float) -> int:
    if denominator <= 0:
        return 0
    return round((numerator / denominator) * 100)


def join_with_e(parts: list[str]) -> str:
    values = [item for item in parts if item]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} e {values[1]}"
    return f'{", ".join(values[:-1])} e {values[-1]}'


def display_profile_label(profile_name: str) -> str:
    return {
        "ESTATISTICO": "ESTATÍSTICO",
        "ESTRATEGICO": "ESTRATÉGICO",
    }.get(profile_name, profile_name)


def display_team_name(team_name: str) -> str:
    resolved = resolve_team_name(team_name)
    return TEAM_DISPLAY_NAMES.get(resolved, str(team_name).title())


def team_name_with_article(team_name: str) -> str:
    resolved = resolve_team_name(team_name)
    article = TEAM_ARTICLES.get(resolved)
    display_name = display_team_name(resolved)
    if not article:
        return display_name
    return f"{article} {display_name}"


def abbreviate_player_name(player_name: str, limit: int = 13) -> str:
    clean = " ".join(str(player_name).split())
    if len(clean) <= limit:
        return clean.upper()

    parts = clean.split()
    if len(parts) == 1:
        return clean[:limit].upper()

    if len(parts) == 2:
        return f"{parts[0][0]}. {parts[1]}".upper()

    last = parts[-1]
    initials = " ".join(f"{part[0]}." for part in parts[:-1])
    compact = f"{initials} {last}".upper()
    if len(compact) <= limit + 2:
        return compact

    first = parts[0]
    second_last = parts[-2]
    two_last = f"{first} {second_last} {last}".upper()
    if len(two_last) <= limit + 4:
        return two_last

    return f"{parts[0][0]}. {last}".upper()


def position_storage_key(position_key: str) -> str:
    return f"cards_{normalize_text(position_key).lower()}"
