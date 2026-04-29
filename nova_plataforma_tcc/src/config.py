from pathlib import Path


ROOT_PROJECT_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT_PROJECT_DIR / "assets"
TEAMS_DIR = ASSETS_DIR / "teams"
LOGOS_DIR = ASSETS_DIR / "logos"
FONTS_DIR = ASSETS_DIR / "fonts"

DEFAULT_EXCEL_FILE = ROOT_PROJECT_DIR / "Scouts Pós R11 2026.xlsx"
BACKGROUND_FILE = LOGOS_DIR / "background.png"
MAIN_LOGO_FILE = LOGOS_DIR / "logo_guardiola.png"
MAIN_LOGO_WHITE_FILE = LOGOS_DIR / "logo_guardiola.png"
BARLOW_DIR = FONTS_DIR / "barlow"
FONT_REGULAR_FILE = BARLOW_DIR / "Barlow-Regular.ttf"
FONT_MEDIUM_FILE = BARLOW_DIR / "Barlow-Medium.ttf"
FONT_BOLD_FILE = BARLOW_DIR / "Barlow-Bold.ttf"
FONT_BLACK_FILE = BARLOW_DIR / "Barlow-Black.ttf"

TEAM_ALIASES = {
    "ATHLETICO": "ATHLETICO-PR",
    "ATLÉTICO-PR": "ATHLETICO-PR",
    "CAP": "ATHLETICO-PR",
    "ATLETICO-MG": "ATLETICO-MG",
    "ATLÉTICO": "ATLETICO-MG",
    "ATLETICO": "ATLETICO-MG",
    "CAM": "ATLETICO-MG",
    "GALO": "ATLETICO-MG",
    "BAH": "BAHIA",
    "BOT": "BOTAFOGO",
    "CHA": "CHAPECOENSE",
    "COR": "CORINTHIANS",
    "CFC": "CORITIBA",
    "CRU": "CRUZEIRO",
    "FLA": "FLAMENGO",
    "FLU": "FLUMINENSE",
    "GRE": "GREMIO",
    "INT": "INTERNACIONAL",
    "MIR": "MIRASSOL",
    "PAL": "PALMEIRAS",
    "RBB": "RED BULL BRAGANTINO",
    "RB BRAGANTINO": "RED BULL BRAGANTINO",
    "BRAGANTINO": "RED BULL BRAGANTINO",
    "REM": "REMO",
    "SAN": "SANTOS",
    "SAO": "SAO PAULO",
    "SAO PAULO": "SAO PAULO",
    "SÃO PAULO": "SAO PAULO",
    "SPO": "SPORT",
    "SPORT CLUB DO RECIFE": "SPORT",
    "VAS": "VASCO",
    "VIT": "VITORIA",
    "VITÓRIA": "VITORIA",
    "GRÊMIO": "GREMIO",
}

TEAM_BADGE_SLUGS = {
    "ATHLETICO-PR": "athletico_pr",
    "ATLETICO-MG": "atletico_mg",
    "BAHIA": "bahia",
    "BOTAFOGO": "botafogo",
    "CHAPECOENSE": "chapecoense",
    "CORINTHIANS": "corinthians",
    "CORITIBA": "coritiba",
    "CRUZEIRO": "cruzeiro",
    "FLAMENGO": "flamengo",
    "FLUMINENSE": "fluminense",
    "GREMIO": "gremio",
    "INTERNACIONAL": "internacional",
    "MIRASSOL": "mirassol",
    "PALMEIRAS": "palmeiras",
    "RED BULL BRAGANTINO": "red_bull_bragantino",
    "REMO": "remo",
    "SANTOS": "santos",
    "SAO PAULO": "sao_paulo",
    "SPORT": "sport",
    "VASCO": "vasco",
    "VITORIA": "vitoria",
}

POSITION_CONFIG = {
    "Goleiros": {
        "role": "goleiro",
        "sheet_positions": {"1.0", "1"},
        "market_positions": {"GOLEIRO"},
        "profiles": ["SG", "ESTATISTICO", "ESTRATEGICO", "BOA FASE"],
        "profile_style": "defensive",
    },
    "Laterais": {
        "role": "lateral",
        "sheet_positions": {"2.0", "2", "2.2", "2.6"},
        "market_positions": {"LATERAL"},
        "profiles": ["SG", "ESTATISTICO", "ESTRATEGICO", "BOA FASE"],
        "profile_style": "defensive",
    },
    "Zagueiros": {
        "role": "zagueiro",
        "sheet_positions": {"3.0", "3"},
        "market_positions": {"ZAGUEIRO"},
        "profiles": ["SG", "ESTATISTICO", "ESTRATEGICO", "BOA FASE"],
        "profile_style": "defensive",
    },
    "Meias": {
        "role": "meia",
        "sheet_positions": {"4.0", "4"},
        "market_positions": {"MEIA"},
        "profiles": ["CONFRONTO", "BOA FASE", "ESTATISTICO", "ESTRATEGICO"],
        "profile_style": "offensive",
    },
    "Atacantes": {
        "role": "atacante",
        "sheet_positions": {"5.0", "5"},
        "market_positions": {"ATACANTE"},
        "profiles": ["CONFRONTO", "BOA FASE", "ESTATISTICO", "ESTRATEGICO"],
        "profile_style": "offensive",
    },
    "Técnicos": {
        "role": "tecnico",
        "sheet_positions": {"6.0", "6"},
        "market_positions": {"TECNICO"},
        "profiles": ["CONFRONTO", "BOA FASE", "ESTATISTICO", "ESTRATEGICO"],
        "profile_style": "offensive",
    },
}

PROFILE_COLORS = {
    "SG": "#59d9f8",
    "CONFRONTO": "#59d9f8",
    "ESTATISTICO": "#2ed95f",
    "ESTRATEGICO": "#ffe50c",
    "BOA FASE": "#d69cec",
}
