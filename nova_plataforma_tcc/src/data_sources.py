import json
import re
from pathlib import Path

import pandas as pd
import requests

from .config import POSITION_CONFIG
from .utils import normalize_text, resolve_team_name


def load_rounds_file(file_path: Path) -> dict[int, list[tuple[str, str]]]:
    rounds: dict[int, list[tuple[str, str]]] = {}
    current_round = None

    with file_path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line:
                continue
            round_match = re.match(r"^Rodada\s+(\d+)", line, re.IGNORECASE)
            if round_match:
                current_round = int(round_match.group(1))
                rounds[current_round] = []
                continue
            if current_round and " x " in line:
                home, away = re.split(r"\s+[xX]\s+", line)
                rounds[current_round].append((resolve_team_name(home), resolve_team_name(away)))
    return rounds


def load_excel_data(file_path: Path) -> dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(file_path)
    sheet_map = {normalize_text(name): name for name in xls.sheet_names}
    por_jogo_name = next(name for key, name in sheet_map.items() if "POR JOGO" in key)
    scouts_name = next(name for key, name in sheet_map.items() if "SCOUTS" in key)

    df_games = pd.read_excel(file_path, sheet_name=por_jogo_name)
    df_games = df_games.rename(
        columns={
            "Time": "TIME",
            "Adversário": "ADVERSARIO",
            "PosReal": "POS_REAL",
            "Mand": "MANDO",
            "Nome2": "NOME",
            "PosID": "POS_ID",
            "G": "G",
            "A": "A",
            "FT": "FT",
            "SG": "SG",
            "DP": "DP",
            "GC": "GC",
            "CV": "CV",
            "DE": "DE",
            "FD": "FD",
            "FF": "FF",
            "FS": "FS",
            "DS": "DS",
            "PP": "PP",
            "CA": "CA",
            "GS": "GS",
            "FC": "FC",
            "I": "I",
            "PS": "PS",
            "PC": "PC",
            "PI": "PI",
            "Bás Tec": "BAS_TEC",
            "Pts": "PTS",
            "Básica": "BASICA",
            "Rodada PADV": "RODADA",
            "G+A": "PG",
            "Data": "DATA",
        }
    )

    df_games["DATA"] = pd.to_datetime(df_games["DATA"], errors="coerce")
    df_games["TIME"] = df_games["TIME"].apply(resolve_team_name)
    df_games["ADVERSARIO"] = df_games["ADVERSARIO"].apply(resolve_team_name)
    df_games["NOME_NORM"] = df_games["NOME"].apply(normalize_text)
    df_games["TIME_NORM"] = df_games["TIME"].apply(normalize_text)
    df_games["ADVERSARIO_NORM"] = df_games["ADVERSARIO"].apply(normalize_text)
    df_games["POS_ID_STR"] = df_games["POS_ID"].astype(str)
    df_games["POS_REAL_STR"] = df_games["POS_REAL"].astype(str)
    df_games["MANDO"] = df_games["MANDO"].map({"Casa": "CASA", "Fora": "FORA"}).fillna(
        df_games["MANDO"].astype(str).str.upper()
    )

    numeric_cols = [
        "G",
        "A",
        "FT",
        "SG",
        "DP",
        "GC",
        "CV",
        "DE",
        "FD",
        "FF",
        "FS",
        "DS",
        "PP",
        "CA",
        "GS",
        "FC",
        "I",
        "PS",
        "PC",
        "PI",
        "BAS_TEC",
        "PTS",
        "BASICA",
        "RODADA",
        "PG",
    ]
    for column in numeric_cols:
        if column in df_games.columns:
            df_games[column] = pd.to_numeric(df_games[column], errors="coerce").fillna(0)

    def build_match_id(row):
        if row["MANDO"] == "CASA":
            home, away = row["TIME"], row["ADVERSARIO"]
        else:
            home, away = row["ADVERSARIO"], row["TIME"]
        day = row["DATA"].strftime("%Y-%m-%d") if pd.notna(row["DATA"]) else "0000-00-00"
        return f"{day}|{home}|{away}"

    df_games["MATCH_ID"] = df_games.apply(build_match_id, axis=1)

    df_scouts = pd.read_excel(file_path, sheet_name=scouts_name)
    return {"POR_JOGO": df_games, "SCOUTS": df_scouts}


def build_photo_index(file_path: Path) -> dict[str, dict[str, str]]:
    html = file_path.read_text(encoding="utf-8")
    match = re.search(r"const CLUBES = (\{.*?\});\s*const TODOS", html, re.S)
    if not match:
        return {}
    data = json.loads(match.group(1))
    photo_index: dict[str, dict[str, str]] = {}
    for team, players in data.items():
        photo_index[normalize_text(resolve_team_name(team))] = {
            normalize_text(name): url for name, url in players.items()
        }
    return photo_index


def fetch_market_snapshot(gm_token: str | None = None) -> pd.DataFrame:
    market_url = "https://api.cartola.globo.com/atletas/mercado"
    response = requests.get(market_url, timeout=20)
    response.raise_for_status()
    payload = response.json()

    clubes = payload.get("clubes", {})
    posicoes = payload.get("posicoes", {})
    mpv_map = fetch_mpv_map(gm_token) if gm_token else {}

    rows = []
    valid_positions = {
        normalize_text(position_name)
        for cfg in POSITION_CONFIG.values()
        for position_name in cfg["market_positions"]
    }

    for athlete in payload.get("atletas", []):
        team_payload = clubes.get(str(athlete.get("clube_id")), {})
        pos_payload = posicoes.get(str(athlete.get("posicao_id")), {})
        team_name = resolve_team_name(team_payload.get("nome", ""))
        position_name = normalize_text(pos_payload.get("nome", ""))
        if position_name not in valid_positions:
            continue

        athlete_id = int(athlete["atleta_id"])
        rows.append(
            {
                "atleta_id": athlete_id,
                "nome": athlete.get("apelido") or athlete.get("nome"),
                "nome_completo": athlete.get("nome") or athlete.get("apelido") or "",
                "time": team_name,
                "posicao_norm": position_name,
                "preco": float(athlete.get("preco_num", 0.0)),
                "minimo_valorizar": float(mpv_map.get(athlete_id, 0.0)),
            }
        )

    return pd.DataFrame(rows).sort_values(["posicao_norm", "nome"]).reset_index(drop=True)


def extract_mpv_map(payload) -> dict[int, float]:
    mpv_map: dict[int, float] = {}

    if isinstance(payload, dict) and "atletas" in payload:
        for athlete in payload["atletas"]:
            if "atleta_id" in athlete:
                mpv_map[int(athlete["atleta_id"])] = float(athlete.get("minimo_para_valorizar", 0.0))
        if mpv_map:
            return mpv_map

    if isinstance(payload, dict):
        for athlete_id, values in payload.items():
            if isinstance(values, dict) and "minimo_para_valorizar" in values:
                try:
                    mpv_map[int(athlete_id)] = float(values.get("minimo_para_valorizar", 0.0))
                except (TypeError, ValueError):
                    continue
        if mpv_map:
            return mpv_map

    if isinstance(payload, list):
        for athlete in payload:
            if "atleta_id" in athlete:
                mpv_map[int(athlete["atleta_id"])] = float(athlete.get("minimo_para_valorizar", 0.0))

    return mpv_map


def fetch_mpv_map(gm_token: str) -> dict[int, float]:
    clean_token = gm_token.strip().strip('"').strip("'")
    if clean_token.lower().startswith("bearer "):
        clean_token = clean_token[7:].strip()

    endpoints = [
        "https://api.cartola.globo.com/auth/gatomestre/atletas",
        "https://api.cartola.globo.com/auth/mercado/atleta/gatomestre",
    ]
    headers_base = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "x-glb-app-name": "cartola-web",
    }
    auth_variants = [
        {"X-GLB-Token": clean_token},
        {"Authorization": f"Bearer {clean_token}"},
        {
            "X-GLB-Token": clean_token,
            "Authorization": f"Bearer {clean_token}",
        },
    ]

    for headers_auth in auth_variants:
        headers = headers_base | headers_auth
        for url in endpoints:
            try:
                response = requests.get(url, headers=headers, timeout=20)
                if response.status_code != 200:
                    continue
                mpv_map = extract_mpv_map(response.json())
                if mpv_map:
                    return mpv_map
            except Exception:
                continue
    return {}
