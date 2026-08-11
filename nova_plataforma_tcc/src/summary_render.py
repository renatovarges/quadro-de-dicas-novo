from __future__ import annotations

from html import escape
from pathlib import Path

from .config import ASSETS_DIR, FONTS_DIR, MAIN_LOGO_FILE, MAIN_LOGO_WHITE_FILE
from .utils import file_to_base64, team_badge_path


SUMMARY_ASSETS = ASSETS_DIR / "summaries"
POSITION_COLUMNS = (
    ("Técnicos", "Laterais", "Meias"),
    ("Goleiros", "Zagueiros", "Atacantes"),
)


def _data_uri(path: Path, mime: str) -> str:
    encoded = file_to_base64(path)
    return f"data:{mime};base64,{encoded}" if encoded else ""


def _theme(theme: str) -> dict:
    if theme == "md3":
        logo = SUMMARY_ASSETS / "md3_logo.png"
        return {
            "key": "md3",
            "brand": "MD3",
            "font_name": "Barlow",
            "font_file": FONTS_DIR / "barlow" / "Barlow-ExtraBold.ttf",
            "background": "linear-gradient(135deg, #fbf0d2 0%, #d4d1ca 100%)",
            "card": "#171717",
            "card_border": "#b68413",
            "header": "#1a1a1a",
            "accent": "#b68413",
            "title_text": "#ffffff",
            "logo": logo,
            "footer_logo": logo,
            "unanimity": "✔",
            "unanimity_class": "round green",
            "captain_class": "round red",
            "rl_class": "round red",
            "material": "MATERIAL EXCLUSIVO – MD3",
        }
    return {
        "key": "tcc",
        "brand": "TCC",
        "font_name": "Decalotype",
        "font_file": FONTS_DIR / "Decalotype-ExtraBold.otf",
        "background": f"url({_data_uri(SUMMARY_ASSETS / 'tcc_background.jpg', 'image/jpeg')}) center/cover",
        "card": "#074b36",
        "card_border": "#098660",
        "header": "#073f2e",
        "accent": "#0b5c43",
        "title_text": "#ffffff",
        "logo": MAIN_LOGO_FILE,
        "footer_logo": MAIN_LOGO_WHITE_FILE,
        "unanimity": "★",
        "unanimity_class": "star",
        "captain_class": "round captain",
        "rl_class": "round orange",
        "material": "MATERIAL EXCLUSIVO – TREINANDO CAMPEÕES DE CARTOLA",
    }


def _mpv_class(position: str, value: float) -> str:
    green_limit = 2.0 if position == "Técnicos" else 3.0
    if value <= green_limit:
        return "positive"
    if value > 6.0:
        return "negative"
    return ""


def _badges(player: dict, theme: dict) -> str:
    badges = player.get("badges", {})
    parts = []
    if badges.get("unanimidade"):
        parts.append(f'<span class="badge {theme["unanimity_class"]}">{theme["unanimity"]}</span>')
    if badges.get("bom_capitao"):
        parts.append(f'<span class="badge {theme["captain_class"]}">C</span>')
    if badges.get("bom_rl"):
        parts.append(f'<span class="badge {theme["rl_class"]}">RL</span>')
    return "".join(parts)


def _player_card(player: dict, position: str, theme: dict) -> str:
    badge_path = team_badge_path(player.get("team", ""))
    badge_uri = _data_uri(badge_path, "image/png") if badge_path else ""
    badge_img = f'<img src="{badge_uri}" alt="">' if badge_uri else ""
    price = float(player.get("price", 0.0))
    mpv = float(player.get("mpv", 0.0))
    confidence = str(player.get("confidence", "A")).upper()
    if confidence not in {"A", "B", "C", "D"}:
        confidence = "A"
    return f"""
    <div class="player-card">
      <div class="player-main">
        <div class="team-badge">{badge_img}</div>
        <div class="player-name">{escape(str(player.get("name", "")))}{_badges(player, theme)}</div>
      </div>
      <div class="stats">
        <div class="stat"><span>C$</span><strong>{price:.1f}</strong></div>
        <div class="stat"><span>MPV</span><strong class="{_mpv_class(position, mpv)}">{mpv:.1f}</strong></div>
        <div class="stat"><span>CONF</span><strong class="confidence confidence-{confidence.lower()}">{confidence}</strong></div>
      </div>
    </div>
    """


def _position_block(position: str, players: list[dict], theme: dict) -> str:
    if not players:
        return ""
    ordered = sorted(
        players,
        key=lambda p: (
            not bool(p.get("badges", {}).get("unanimidade")),
            not bool(p.get("badges", {}).get("bom_capitao")),
            str(p.get("confidence", "A")),
            str(p.get("name", "")),
        ),
    )
    cards = "".join(_player_card(player, position, theme) for player in ordered)
    return f'<section class="position"><h2>{escape(position.upper())}</h2>{cards}</section>'


def build_summary_html(theme_name: str, target_round: int, players_by_position: dict[str, list[dict]]) -> str:
    theme = _theme(theme_name)
    font_uri = _data_uri(theme["font_file"], "font/ttf" if theme["font_file"].suffix == ".ttf" else "font/otf")
    logo_uri = _data_uri(theme["logo"], "image/png")
    footer_logo_uri = _data_uri(theme["footer_logo"], "image/png")
    columns = [
        "".join(_position_block(position, players_by_position.get(position, []), theme) for position in positions)
        for positions in POSITION_COLUMNS
    ]
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
@font-face {{ font-family: '{theme["font_name"]}'; src: url({font_uri}); font-weight: 800; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: transparent; }}
body {{ font-family: '{theme["font_name"]}', Arial, sans-serif; }}
#capture {{
  width: 1200px; min-height: 1200px; margin: 0; padding: 42px 40px 0;
  background: {theme["background"]}; color: white; display: flex; flex-direction: column;
}}
.header {{ display: grid; grid-template-columns: 105px 1fr 105px; align-items: center; gap: 20px; margin-bottom: 38px; }}
.header img {{ width: 100px; height: 90px; object-fit: contain; }}
.header-title {{
  background: {theme["header"]}; border: 2px solid {theme["accent"]}; border-radius: 12px;
  padding: 16px 18px; text-align: center; color: {theme["title_text"]}; font-size: 39px;
  line-height: 1; text-transform: uppercase; box-shadow: 0 4px 10px #0004; white-space: nowrap;
}}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 32px; align-items: start; }}
.column {{ display: flex; flex-direction: column; gap: 25px; }}
.position {{ text-align: center; }}
.position h2 {{
  display: inline-block; margin: 0 0 14px; padding: 7px 30px; border-radius: 8px;
  background: white; color: {theme["header"]}; border: 2px solid {theme["header"]};
  font-size: 31px; line-height: 1; box-shadow: 0 3px 7px #0003;
}}
.player-card {{
  min-height: 96px; margin-bottom: 12px; padding: 11px 18px; border-radius: 16px;
  background: {theme["card"]}; border: 2px solid {theme["card_border"]};
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  box-shadow: 0 3px 7px #0005; text-align: left;
}}
.player-main {{ display: flex; align-items: center; min-width: 0; gap: 14px; flex: 1; }}
.team-badge {{
  width: 68px; height: 68px; padding: 2px; border-radius: 50%; background: white;
  display: flex; align-items: center; justify-content: center; flex: 0 0 auto;
  box-shadow: 0 4px 8px #0006;
}}
.team-badge img {{ width: 94%; height: 94%; object-fit: contain; }}
.player-name {{ font-size: 24px; line-height: 1.08; font-weight: 800; text-transform: uppercase; overflow-wrap: anywhere; }}
.badge {{ display: inline-flex; align-items: center; justify-content: center; margin-left: 5px; vertical-align: middle; }}
.badge.round {{ width: 25px; height: 25px; border-radius: 50%; color: white; border: 2px solid white; font: 800 13px Arial; }}
.badge.green {{ background: #25b967; }} .badge.red {{ background: #cc4138; }}
.badge.captain {{ background: #28bd69; }} .badge.orange {{ background: #ec792a; }}
.badge.star {{ color: #f5c400; font-size: 27px; text-shadow: 0 1px 2px #0008; }}
.stats {{ display: flex; align-items: center; gap: 12px; flex: 0 0 auto; }}
.stat {{ min-width: 48px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 6px; }}
.stat span {{ font-size: 14px; line-height: 1; }}
.stat strong {{ font-size: 22px; line-height: 1; color: white; }}
.stat strong.positive {{ color: #26d879; }} .stat strong.negative {{ color: #ff4c4c; }}
.confidence {{ width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #10251d !important; }}
.confidence-a {{ background: #2ecc71; }} .confidence-b {{ background: #cddc39; }}
.confidence-c {{ background: #f1c40f; }} .confidence-d {{ background: #e74c3c; }}
.footer {{
  min-height: 92px; margin: auto -40px 0; padding: 10px 22px; background: {theme["header"]};
  border-top: 3px solid {theme["accent"]}; display: grid; grid-template-columns: 100px 1fr 100px;
  align-items: center; gap: 10px; color: white;
}}
.footer img {{ width: 88px; height: 65px; object-fit: contain; }}
.footer-center {{ text-align: center; }}
.legend {{ display: flex; justify-content: center; align-items: center; gap: 22px; font: 700 14px Arial; margin-bottom: 7px; }}
.legend-item {{ display: inline-flex; align-items: center; gap: 5px; }}
.material {{ font-size: 14px; letter-spacing: 1px; }}
</style></head><body>
<div id="capture">
  <header class="header"><img src="{logo_uri}" alt=""><div class="header-title">DICAS POR POSIÇÃO – {theme["brand"]} – RODADA {int(target_round)}</div><img src="{logo_uri}" alt=""></header>
  <main class="grid"><div class="column">{columns[0]}</div><div class="column">{columns[1]}</div></main>
  <footer class="footer"><img src="{footer_logo_uri}" alt=""><div class="footer-center">
    <div class="legend">
      <span class="legend-item"><span class="badge {theme["rl_class"]}">RL</span> Luxo</span>
      <span class="legend-item"><span class="badge {theme["unanimity_class"]}">{theme["unanimity"]}</span> Unanimidade</span>
      <span class="legend-item"><span class="badge {theme["captain_class"]}">C</span> Bom Capitão</span>
      <span class="legend-item"><span class="confidence confidence-a" style="width:17px;height:17px"></span> Nível de Confiança</span>
    </div>
    <div class="material">{theme["material"]}</div>
  </div><img src="{footer_logo_uri}" alt=""></footer>
</div></body></html>"""
