from dataclasses import dataclass

import pandas as pd

from .config import POSITION_CONFIG, PROFILE_COLORS
from .phrases import build_phrase
from .utils import (
    display_profile_label,
    file_to_base64,
    normalize_text,
    percent,
    resolve_team_name,
    team_badge_path,
)


LATERAL_SIDE_MAP = {
    "2.2": "laterais direitos",
    "2.6": "laterais esquerdos",
}

RED = "#cf3a34"
BLACK = "#241108"
GREEN = "#138a2f"


@dataclass
class MatchContext:
    opponent: str
    mando: str


class ScoutAnalyzer:
    def __init__(self, df_games: pd.DataFrame, rounds_data: dict[int, list[tuple[str, str]]], photo_index: dict):
        self.df_games = df_games.copy()
        self.rounds_data = rounds_data
        self.photo_index = photo_index

    def build_card(self, player: dict, position_key: str, target_round: int, window_n: int, filter_mode: str) -> dict:
        resolved_team = resolve_team_name(player["team"])
        match_context = self.get_match_context(resolved_team, target_round)
        own_rows = self.get_player_rows(
            player["name"],
            resolved_team,
            target_round,
            position_key=position_key,
            target_mando=match_context.mando,
            window_n=window_n,
            filter_mode=filter_mode,
        )

        lateral_side = self.detect_lateral_side(own_rows, position_key)
        if lateral_side:
            own_rows = own_rows[own_rows["POS_REAL_STR"] == lateral_side].copy()

        opp_rows, opponent_team_rows = self.get_conceded_rows(
            match_context.opponent,
            target_round,
            position_key,
            player_mando=match_context.mando,
            window_n=window_n,
            filter_mode=filter_mode,
            lateral_side=lateral_side,
        )

        lateral_side_label = LATERAL_SIDE_MAP.get(lateral_side, "")

        own_stats = self.aggregate_stats(own_rows, position_key)
        own_stats["lateral_side"] = lateral_side_label

        opp_stats = self.aggregate_stats(
            opp_rows,
            position_key,
            conceded=True,
            conceded_team_rows=opponent_team_rows,
        )
        opp_stats["lateral_side"] = lateral_side_label

        return {
            "name": player["name"],
            "display_name": self.get_display_name(player["name"]),
            "team": resolved_team,
            "price": player["price"],
            "mpv": player["mpv"],
            "avg_points": own_stats["avg_points"],
            "avg_points_label": self.build_average_label(match_context.mando, filter_mode, own_stats["games"]),
            "confidence": player["confidence"],
            "badges": player["badges"],
            "profiles": player["profiles"],
            "profile_chips": [
                {"label": display_profile_label(profile), "color": PROFILE_COLORS.get(profile, "#59d9f8")}
                for profile in player["profiles"]
            ],
            "photo_url": self.get_photo_url(
                resolved_team,
                player["name"],
                player.get("full_name", ""),
            ),
            "team_logo_b64": file_to_base64(team_badge_path(resolved_team)),
            "metrics": self.build_metrics(position_key, own_stats, opp_stats),
            "phrase": build_phrase(
                position_key,
                match_context.opponent,
                player["profiles"],
                own_stats,
                opp_stats,
                match_context.mando,
                filter_mode,
            ),
        }

    def build_average_label(self, mando: str, filter_mode: str, games: int) -> str:
        suffix = f" | {games}J"
        if filter_mode != "POR_MANDO":
            return f"MÉDIA GERAL{suffix}"
        return f"MÉDIA EM CASA{suffix}" if mando == "CASA" else f"MÉDIA FORA{suffix}"

    def get_match_context(self, team_name: str, target_round: int) -> MatchContext:
        team_norm = normalize_text(resolve_team_name(team_name))
        for home, away in self.rounds_data.get(target_round, []):
            if normalize_text(home) == team_norm:
                return MatchContext(opponent=away, mando="CASA")
            if normalize_text(away) == team_norm:
                return MatchContext(opponent=home, mando="FORA")
        return MatchContext(opponent="Adversário não encontrado", mando="CASA")

    def get_player_rows(
        self,
        player_name: str,
        team_name: str,
        target_round: int,
        position_key: str,
        target_mando: str,
        window_n: int,
        filter_mode: str,
    ) -> pd.DataFrame:
        df = self.df_games[
            (self.df_games["TIME_NORM"] == normalize_text(resolve_team_name(team_name)))
            & (self.df_games["NOME_NORM"] == normalize_text(player_name))
            & (self.df_games["RODADA"] < target_round)
        ].copy()
        df = self.filter_position_rows(df, position_key)
        if filter_mode == "POR_MANDO":
            df = df[df["MANDO"] == target_mando]
        return df.sort_values("DATA").tail(window_n)

    def get_conceded_rows(
        self,
        opponent_name: str,
        target_round: int,
        position_key: str,
        player_mando: str,
        window_n: int,
        filter_mode: str,
        lateral_side: str = "",
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        opponent_norm = normalize_text(resolve_team_name(opponent_name))
        opponent_mando = "FORA" if player_mando == "CASA" else "CASA"
        df_team = self.df_games[
            (self.df_games["TIME_NORM"] == opponent_norm)
            & (self.df_games["RODADA"] < target_round)
        ].copy()
        if filter_mode == "POR_MANDO":
            df_team = df_team[df_team["MANDO"] == opponent_mando]

        selected_matches = (
            df_team.groupby("MATCH_ID")["DATA"].first().sort_values().tail(window_n).index.tolist()
            if not df_team.empty
            else []
        )
        if not selected_matches:
            empty = self.df_games.iloc[0:0].copy()
            return empty, empty

        opponent_team_rows = self.df_games[
            (self.df_games["MATCH_ID"].isin(selected_matches))
            & (self.df_games["TIME_NORM"] == opponent_norm)
        ].copy()
        opponent_team_rows = self.filter_position_rows(opponent_team_rows, position_key)
        if lateral_side:
            opponent_team_rows = opponent_team_rows[opponent_team_rows["POS_REAL_STR"] == lateral_side].copy()

        opponent_rows = self.df_games[
            (self.df_games["MATCH_ID"].isin(selected_matches))
            & (self.df_games["TIME_NORM"] != opponent_norm)
        ].copy()
        opponent_rows = self.filter_position_rows(opponent_rows, position_key)
        if lateral_side:
            opponent_rows = opponent_rows[opponent_rows["POS_REAL_STR"] == lateral_side].copy()
        return opponent_rows, opponent_team_rows

    def filter_position_rows(self, df: pd.DataFrame, position_key: str) -> pd.DataFrame:
        allowed = POSITION_CONFIG[position_key]["sheet_positions"]
        return df[df["POS_ID_STR"].isin(allowed) | df["POS_REAL_STR"].isin(allowed)].copy()

    def detect_lateral_side(self, df: pd.DataFrame, position_key: str) -> str:
        if POSITION_CONFIG[position_key]["role"] != "lateral" or df.empty:
            return ""
        valid = df[df["POS_REAL_STR"].isin(LATERAL_SIDE_MAP)].copy()
        if valid.empty:
            return ""
        valid = valid.sort_values("DATA")
        return str(valid.iloc[-1]["POS_REAL_STR"])

    def get_match_score(self, match_id: str, team_norm: str) -> tuple[int, int] | None:
        match_rows = self.df_games[self.df_games["MATCH_ID"] == match_id]
        if match_rows.empty:
            return None

        team_mask = match_rows["TIME_NORM"] == team_norm
        opponent_mask = ~team_mask
        if not team_mask.any() or not opponent_mask.any():
            return None

        team_goals = int(match_rows.loc[team_mask, "G"].sum() + match_rows.loc[opponent_mask, "GC"].sum())
        opponent_goals = int(match_rows.loc[opponent_mask, "G"].sum() + match_rows.loc[team_mask, "GC"].sum())
        return team_goals, opponent_goals

    def count_wins(self, df: pd.DataFrame, position_key: str) -> int:
        if df.empty or POSITION_CONFIG[position_key]["role"] != "tecnico":
            return 0

        wins = 0
        for match_id in df["MATCH_ID"].dropna().unique().tolist():
            team_rows = df[df["MATCH_ID"] == match_id]
            if team_rows.empty:
                continue

            team_norm = team_rows["TIME_NORM"].iloc[0]
            score = self.get_match_score(match_id, team_norm)
            if score is None:
                continue

            team_goals, opponent_goals = score
            if team_goals > opponent_goals:
                wins += 1

        return wins

    def count_losses(self, df: pd.DataFrame, position_key: str) -> int:
        if df.empty or POSITION_CONFIG[position_key]["role"] != "tecnico":
            return 0

        losses = 0
        for match_id in df["MATCH_ID"].dropna().unique().tolist():
            team_rows = df[df["MATCH_ID"] == match_id]
            if team_rows.empty:
                continue

            team_norm = team_rows["TIME_NORM"].iloc[0]
            score = self.get_match_score(match_id, team_norm)
            if score is None:
                continue

            team_goals, opponent_goals = score
            if team_goals < opponent_goals:
                losses += 1

        return losses

    def aggregate_stats(
        self,
        df: pd.DataFrame,
        position_key: str,
        conceded: bool = False,
        conceded_team_rows: pd.DataFrame | None = None,
    ) -> dict:
        default_stats = {
            "games": 0,
            "sg": 0,
            "de": 0,
            "pct_de": 0,
            "ds": 0,
            "basic": 0.0,
            "pg": 0,
            "shots": 0,
            "shots_on_target": 0,
            "total_shots": 0,
            "avg_points": 0.0,
            "wins": 0,
            "plus_five": 0,
        }
        if df.empty:
            return default_stats

        role = POSITION_CONFIG[position_key]["role"]
        game_count = int(df["MATCH_ID"].nunique())
        basic = round(float(df["BASICA"].mean()), 2)
        pg = int((df["G"] + df["A"]).sum())
        shots = int((df["FF"] + df["FT"]).sum())
        shots_on_target = int((df["FD"] + df["G"]).sum())
        total_shots = shots
        avg_points = round(float(df["PTS"].mean()), 2)
        wins = self.count_wins(df, position_key)
        plus_five = self.count_threshold_games(df, 5.0)
        if conceded and role == "tecnico" and conceded_team_rows is not None:
            wins = self.count_losses(conceded_team_rows, position_key)

        stats = {
            "games": game_count,
            "sg": 0,
            "de": 0,
            "pct_de": 0,
            "ds": 0,
            "basic": basic,
            "pg": pg,
            "shots": shots,
            "shots_on_target": shots_on_target,
            "total_shots": total_shots,
            "avg_points": avg_points,
            "wins": wins,
            "plus_five": plus_five,
        }

        if role == "goleiro":
            de = int(df["DE"].sum())
            gs = int(df["GS"].sum())
            sg = int(df.groupby("MATCH_ID")["SG"].max().sum()) if conceded else int(df["SG"].sum())
            stats.update(
                {
                    "sg": sg,
                    "de": de,
                    "pct_de": percent(de, de + gs),
                }
            )
            return stats

        if role in {"lateral", "zagueiro"}:
            ds = int(df["DS"].sum())
            sg = int(df.groupby("MATCH_ID")["SG"].max().sum()) if conceded else int(df["SG"].sum())
            stats.update({"ds": ds, "sg": sg})
            return stats

        if role == "tecnico":
            stats.update(
                {
                    "pg": 0,
                    "shots": 0,
                    "shots_on_target": 0,
                    "total_shots": 0,
                }
            )
            return stats

        return stats

    def metric_value_color(self, position_key: str, label: str, raw_value) -> str:
        role = POSITION_CONFIG[position_key]["role"]
        value = self.parse_metric_value(raw_value)
        label_norm = normalize_text(label)

        if "SG" in label_norm:
            if value <= 0:
                return RED
            if value == 1:
                return BLACK
            return GREEN

        if role == "goleiro":
            if label_norm.startswith("DE"):
                return self.color_by_ranges(value, 3, 6)
            if "M.BAS" in label_norm:
                return self.color_by_ranges(value, 1.0, 2.0)
            if "%DE" in label_norm:
                return self.color_by_ranges(value, 50, 70)

        if role == "lateral":
            if label_norm.startswith("DS"):
                return self.color_by_ranges(value, 3, 6)
            if label_norm.startswith("FIN"):
                return self.color_by_ranges(value, 1, 3)
            if "M.BAS" in label_norm:
                return self.color_by_ranges(value, 1.5, 2.5)
            if "G+A" in label_norm:
                return self.color_by_goal_actions(value)

        if role == "zagueiro":
            if label_norm.startswith("DS"):
                return self.color_by_ranges(value, 2, 5)
            if label_norm.startswith("FIN"):
                return self.color_by_ranges(value, 1, 2)
            if "M.BAS" in label_norm:
                return self.color_by_ranges(value, 1.0, 1.9)
            if "G+A" in label_norm:
                return self.color_by_goal_actions(value)

        if role in {"meia", "atacante"}:
            if label_norm.startswith("CHT AG"):
                return self.color_by_ranges(value, 1, 2) if "CONQ" in label_norm else self.color_by_ranges(value, 3, 6)
            if label_norm.startswith("CHT"):
                return self.color_by_ranges(value, 2, 4) if "CONQ" in label_norm else self.color_by_ranges(value, 4, 8)
            if "G+A" in label_norm:
                return self.color_by_goal_actions(value)

        if role == "tecnico":
            if label_norm.startswith("VIT"):
                return self.color_by_ranges(value, 0, 1)
            if label_norm.startswith("5PTS"):
                return self.color_by_ranges(value, 0, 1)
            if "M.PTS" in label_norm:
                if value < 3:
                    return RED
                if value <= 5:
                    return BLACK
                return GREEN

        return BLACK

    def parse_metric_value(self, raw_value) -> float:
        text = str(raw_value).strip()
        if "/" in text:
            text = text.split("/")[0]
        text = text.replace("%", "").replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return 0.0

    def color_by_ranges(self, value: float, low_limit: float, mid_limit: float) -> str:
        if value <= low_limit:
            return RED
        if value <= mid_limit:
            return BLACK
        return GREEN

    def color_by_goal_actions(self, value: float) -> str:
        if value <= 0:
            return RED
        if value == 1:
            return BLACK
        return GREEN

    def count_threshold_games(self, df: pd.DataFrame, threshold: float) -> int:
        if df.empty:
            return 0
        if "MATCH_ID" in df.columns and df["MATCH_ID"].notna().any():
            match_points = df.groupby("MATCH_ID")["PTS"].max()
            return int((match_points >= threshold).sum())
        return int((df["PTS"] >= threshold).sum())

    def format_decimal_metric(self, value: float, decimals: int = 1) -> str:
        return f"{value:.{decimals}f}".replace(".", ",")

    def build_metric(self, position_key: str, title: str, left_value, right_value) -> dict:
        return {
            "title": title,
            "left_label": "CONQ",
            "left_value": str(left_value),
            "left_color": self.metric_value_color(position_key, f"{title} CONQ", left_value),
            "right_label": "CED",
            "right_value": str(right_value),
            "right_color": self.metric_value_color(position_key, f"{title} CED", right_value),
        }

    def build_metrics(self, position_key: str, own_stats: dict, opp_stats: dict) -> list[dict]:
        role = POSITION_CONFIG[position_key]["role"]

        if role == "goleiro":
            return [
                self.build_metric(position_key, "SG", f'{own_stats["sg"]}/{own_stats["games"]}', f'{opp_stats["sg"]}/{opp_stats["games"]}'),
                self.build_metric(position_key, "M.BÁS", self.format_decimal_metric(own_stats["basic"]), self.format_decimal_metric(opp_stats["basic"])),
                self.build_metric(position_key, "DE", own_stats["de"], opp_stats["de"]),
                self.build_metric(position_key, "%DE", f'{own_stats["pct_de"]}%', f'{opp_stats["pct_de"]}%'),
            ]

        if role == "lateral":
            return [
                self.build_metric(position_key, "SG", f'{own_stats["sg"]}/{own_stats["games"]}', f'{opp_stats["sg"]}/{opp_stats["games"]}'),
                self.build_metric(position_key, "M.BÁS", self.format_decimal_metric(own_stats["basic"]), self.format_decimal_metric(opp_stats["basic"])),
                self.build_metric(position_key, "DS", own_stats["ds"], opp_stats["ds"]),
                self.build_metric(position_key, "FIN", own_stats["total_shots"], opp_stats["total_shots"]),
                self.build_metric(position_key, "G+A", own_stats["pg"], opp_stats["pg"]),
            ]

        if role == "zagueiro":
            return [
                self.build_metric(position_key, "SG", f'{own_stats["sg"]}/{own_stats["games"]}', f'{opp_stats["sg"]}/{opp_stats["games"]}'),
                self.build_metric(position_key, "M.BÁS", self.format_decimal_metric(own_stats["basic"]), self.format_decimal_metric(opp_stats["basic"])),
                self.build_metric(position_key, "DS", own_stats["ds"], opp_stats["ds"]),
                self.build_metric(position_key, "FIN", own_stats["total_shots"], opp_stats["total_shots"]),
                self.build_metric(position_key, "G+A", own_stats["pg"], opp_stats["pg"]),
            ]

        if role == "tecnico":
            return [
                self.build_metric(position_key, "VIT", f'{own_stats["wins"]}/{own_stats["games"]}', f'{opp_stats["wins"]}/{opp_stats["games"]}'),
                self.build_metric(position_key, "5PTS+", f'{own_stats["plus_five"]}/{own_stats["games"]}', f'{opp_stats["plus_five"]}/{opp_stats["games"]}'),
                self.build_metric(position_key, "M.PTS", self.format_decimal_metric(own_stats["avg_points"], 2), self.format_decimal_metric(opp_stats["avg_points"], 2)),
            ]

        return [
            self.build_metric(position_key, "M.BÁS", self.format_decimal_metric(own_stats["basic"]), self.format_decimal_metric(opp_stats["basic"])),
            self.build_metric(position_key, "CHT", own_stats["shots"], opp_stats["shots"]),
            self.build_metric(position_key, "CHT AG", own_stats["shots_on_target"], opp_stats["shots_on_target"]),
            self.build_metric(position_key, "G+A", own_stats["pg"], opp_stats["pg"]),
        ]

    def get_photo_url(self, team_name: str, *candidate_names: str) -> str:
        team_index = self.photo_index.get(normalize_text(resolve_team_name(team_name)), {})
        normalized_candidates = []
        for candidate in candidate_names:
            candidate_norm = normalize_text(candidate)
            if candidate_norm and candidate_norm not in normalized_candidates:
                normalized_candidates.append(candidate_norm)

        for candidate_norm in normalized_candidates:
            if candidate_norm in team_index:
                return team_index[candidate_norm]

        partial_matches: dict[str, str] = {}
        for candidate_norm in normalized_candidates:
            if len(candidate_norm.split()) < 2:
                continue
            for indexed_name, url in team_index.items():
                if len(indexed_name.split()) < 2:
                    continue
                if candidate_norm in indexed_name or indexed_name in candidate_norm:
                    partial_matches[indexed_name] = url

        if len(partial_matches) == 1:
            return next(iter(partial_matches.values()))
        return ""

    def get_display_name(self, player_name: str) -> str:
        from .utils import abbreviate_player_name

        return abbreviate_player_name(player_name)
