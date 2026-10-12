"""Artes do feedback pós-rodada (estilo TCC): resumo horizontal e painel de cards por posição."""
from __future__ import annotations

from html import escape
from typing import Callable

from .brand import BRAND
from .config import BACKGROUND_FILE, FONT_BLACK_FILE, FONT_BOLD_FILE, FONT_MEDIUM_FILE, FONT_REGULAR_FILE, MAIN_LOGO_FILE
from .feedback import DEFAULT_FORMATION, FORMATIONS, POSITION_ORDER
from .photos import photo_data_uri, prefetch_photos
from .utils import normalize_text, abbreviate_player_name, display_profile_label, file_to_base64, team_badge_path

PhotoResolver = Callable[[str, str, str], str]

GREEN, RED, GOLD, GRAY = "#138a2f", "#cf3a34", "#e0a100", "#8a8a8a"
TIER_STYLE = {
    "mitou": (GOLD, "MITOU"),
    "bom": (GREEN, "ACIMA DA MÉDIA"),
    "abaixo": (RED, "ABAIXO DA MÉDIA"),
    "nao_jogou": (GRAY, "NÃO JOGOU"),
}


def fmt(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{decimals}f}".replace(".", ",")


def _bg_css() -> str:
    if BRAND.art_bg == "image":
        return f"url(data:image/png;base64,{file_to_base64(BACKGROUND_FILE)}) center/cover"
    return BRAND.art_bg


def _base_css() -> str:
    fonts = {
        "REG": (FONT_REGULAR_FILE, 400),
        "MED": (FONT_MEDIUM_FILE, 500),
        "BOLD": (FONT_BOLD_FILE, 700),
        "BLACK": (FONT_BLACK_FILE, 900),
    }
    faces = "".join(
        f"@font-face {{ font-family: 'Barlow'; src: url(data:font/ttf;base64,{file_to_base64(path)}) format('truetype'); font-weight: {weight}; }}\n"
        for path, weight in fonts.values()
    )
    return faces + """
    * { box-sizing: border-box; }
    body { margin: 0; background: #f4f2ed; font-family: 'Barlow', sans-serif; -webkit-font-smoothing: antialiased; text-rendering: geometricPrecision; }
    .art { margin: 0 auto; padding: 28px 36px 30px; background: __BGCSS__; color: __TEXT__; }
    .hero { display: grid; grid-template-columns: 170px 1fr; align-items: center; gap: 18px; margin-bottom: 20px; }
    .hero-logo { width: 140px; justify-self: center; }
    .hero-copy { text-align: center; }
    .hero-title { font-size: 62px; line-height: .96; font-weight: 900; text-transform: uppercase; white-space: nowrap; }
    .hero-subtitle { font-size: 30px; font-style: italic; margin-top: 8px; text-transform: uppercase; font-weight: 700; }
    .photo { width: 92px; height: 92px; border-radius: 50%; object-fit: cover; object-position: top center; border: 4px solid #fff; background: #fff; display: block; }
    .photo.ph { display: flex; align-items: center; justify-content: center; color: #0f5d00; font-weight: 800; font-size: 26px; }
    .badge { position: absolute; width: 36px; height: 36px; right: -4px; bottom: -2px; border-radius: 50%; background: #fff; border: 2px solid #d6d6d6; object-fit: contain; padding: 3px; }
    .legend { margin-top: 16px; display: flex; justify-content: center; gap: 26px; font-size: 17px; font-weight: 700; flex-wrap: wrap; }
    .legend i { display: inline-block; width: 16px; height: 16px; border-radius: 50%; margin-right: 7px; vertical-align: -2px; }
    """.replace("__BGCSS__", _bg_css()).replace("__TEXT__", BRAND.art_text)


def _themed(css: str) -> str:
    return (
        css.replace("__CARD__", BRAND.art_card)
        .replace("__ACCENT__", BRAND.art_accent)
        .replace("__ACCENTTEXT__", "#0f5d00" if BRAND.key == "tcc" else "#7a5c00")
    )


def _logo() -> str:
    note = (
        f'<div style="color:{BRAND.art_accent};font-size:12px;font-weight:700;letter-spacing:2px;'
        f'text-transform:uppercase;font-style:italic;text-align:center;margin-top:6px;white-space:nowrap">{BRAND.hero_note}</div>'
        if BRAND.hero_note else ""
    )
    return (
        f'<div style="justify-self:center"><img class="hero-logo" '
        f'src="data:image/png;base64,{file_to_base64(MAIN_LOGO_FILE)}" alt="logo">{note}</div>'
    )


def _photo(player: dict, resolver: PhotoResolver, size_class: str = "") -> str:
    url = resolver(player["team"], player["name"], player.get("full_name", ""))
    src = photo_data_uri(url) if url else ""
    if src:
        return f'<img class="photo {size_class}" src="{src}" alt="">'
    initials = "".join(part[0] for part in player["name"].split()[:2]).upper()
    return f'<div class="photo ph {size_class}">{escape(initials)}</div>'


def _badge(team: str) -> str:
    encoded = file_to_base64(team_badge_path(team))
    return f'<img class="badge" src="data:image/png;base64,{encoded}" alt="">' if encoded else ""


def _collect_urls(players: list[dict], resolver: PhotoResolver) -> None:
    prefetch_photos([resolver(p["team"], p["name"], p.get("full_name", "")) for p in players])


# ------------------------------------------------------------------ resumo horizontal ---------

SUMMARY_CSS = """

    .art.wide { width: 1800px; }
    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px; }
    .stat { background: __CARD__; color: #fff; border: 3px solid #f5f5f0; border-radius: 16px; padding: 10px 14px; text-align: center; }
    .stat b { display: block; font-size: 40px; font-weight: 900; line-height: 1; }
    .stat span { font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: .3px; }
    .stat small { display: block; font-size: 14px; opacity: .9; margin-top: 3px; }
    .teams { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }
    .team-box { background: __CARD__; border: 3px solid #f5f5f0; border-radius: 20px; padding: 14px 16px 16px; color: #fff; }
    .team-head { display: flex; justify-content: space-between; align-items: baseline; padding: 0 6px 8px; }
    .team-head h2 { margin: 0; font-size: 30px; font-weight: 900; text-transform: uppercase; }
    .team-head .tot { font-size: 36px; font-weight: 900; color: __ACCENT__; }
    .team-head .tot small { font-size: 15px; color: #fff; font-weight: 700; }
    .pitch { position: relative; background:
        repeating-linear-gradient(0deg, rgba(255,255,255,.05) 0 70px, rgba(255,255,255,0) 70px 140px), #167a1c;
        border: 3px solid rgba(255,255,255,.8); border-radius: 14px; padding: 14px 10px 10px; display: flex; flex-direction: column; gap: 10px; min-height: 800px; justify-content: space-between; }
    .line { display: flex; justify-content: space-evenly; align-items: flex-start; }
    .pl { position: relative; width: 190px; text-align: center; }
    .pl .ph-wrap { position: relative; width: 100px; margin: 0 auto; }
    .pl .photo { width: 92px; height: 92px; margin: 0 auto; }
    .pl .nm { margin: 6px auto 0; max-width: 176px; background: #f7efe7; color: #2d1908; font-weight: 800; font-size: 17px; text-transform: uppercase; padding: 3px 8px; border-radius: 6px; white-space: nowrap; overflow: hidden; }
    .pl .pts { margin-top: 4px; display: inline-block; min-width: 74px; font-size: 25px; font-weight: 900; color: #fff; border-radius: 10px; padding: 1px 10px; background: rgba(0,0,0,.35); }
    .pl .pts.mitou { background: #e0a100; } .pl .pts.neg { background: #cf3a34; }
    .pl .cap { position: absolute; top: -4px; left: 28px; width: 34px; height: 34px; border-radius: 50%; background: #38c172; color: #fff; font-weight: 900; font-size: 20px; line-height: 30px; border: 3px solid #fff; z-index: 2; }
    .pl .tag { position: absolute; top: -8px; right: 20px; background: #ffc61e; color: #241108; font-size: 12px; font-weight: 900; padding: 2px 7px; border-radius: 8px; z-index: 2; text-transform: uppercase; }
    .pl.hit .photo { border-color: #ffc61e; box-shadow: 0 0 0 4px rgba(255,198,30,.55); }
    .pl .pos { font-size: 12px; font-weight: 700; opacity: .85; text-transform: uppercase; }
    .forms { margin-top: 16px; background: __CARD__; color: #fff; border: 3px solid #f5f5f0; border-radius: 16px; padding: 12px 18px; display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
    .forms h3 { margin: 0; font-size: 22px; font-weight: 900; text-transform: uppercase; }
    .fchip { background: rgba(255,255,255,.14); border-radius: 10px; padding: 6px 12px; font-size: 20px; font-weight: 800; }
    .fchip.best { background: #ffc61e; color: #241108; }
    .fchip.def { outline: 2px solid #fff; }
"""


def _pitch_player(player: dict, resolver: PhotoResolver, captain_id=None, highlight_tag: str = "") -> str:
    points = player["points"]
    pts_class = "mitou" if points > 10 else ("neg" if points < 0 else "")
    hit = "hit" if highlight_tag else ""
    cap = '<div class="cap">C</div>' if captain_id is not None and player["athlete_id"] == captain_id else ""
    tag = f'<div class="tag">{highlight_tag}</div>' if highlight_tag else ""
    return (
        f'<div class="pl {hit}">{cap}{tag}'
        f'<div class="ph-wrap">{_photo(player, resolver)}{_badge(player["team"])}</div>'
        f'<div class="nm">{escape(abbreviate_player_name(player["name"], 14))}</div>'
        f'<div class="pts {pts_class}">{fmt(points)}</div></div>'
    )


def _pitch(team: dict, resolver: PhotoResolver, captain_id=None, mark_ids: set | None = None, tag: str = "") -> str:
    by_pos = {key: [p for p in team["players"] if p["position"] == key] for key in POSITION_ORDER}
    lat, zag = by_pos["Laterais"], by_pos["Zagueiros"]
    if len(lat) == 2:
        defense = [lat[0], *zag, lat[1]]
    else:
        defense = [*lat, *zag]
    rows = [by_pos["Atacantes"], by_pos["Meias"], defense, by_pos["Goleiros"] + by_pos["Técnicos"]]
    html = []
    for row in rows:
        cells = "".join(
            _pitch_player(p, resolver, captain_id, tag if (mark_ids is not None and p["athlete_id"] in mark_ids) else "")
            for p in row
        )
        html.append(f'<div class="line">{cells}</div>')
    return f'<div class="pitch">{"".join(html)}</div>'


def build_summary_html(evaluation: dict, resolver: PhotoResolver) -> str:
    summary = evaluation["summary"]
    mine = evaluation["my_team"]["default"] or evaluation["my_team"]["best"]
    best = evaluation["my_team"]["best"]
    cartola = evaluation["cartola_team"]
    if not mine:
        return '<html><body><div id="capture" style="padding:40px;font:24px sans-serif">Indicados insuficientes para montar a seleção.</div></body></html>'

    all_players = mine["players"] + cartola["players"]
    _collect_urls(all_players, resolver)
    my_ids = {p["athlete_id"] for p in evaluation["players"]}
    cartola_ids = {p["athlete_id"] for p in cartola["players"]}

    mitou = summary["mitou"]
    mitou_names = ", ".join(abbreviate_player_name(p["name"], 14).title() for p in mitou[:3]) or "ninguém"
    stats = [
        ("Aproveitamento", f'{summary["check_rate"]}%', f'{summary["checks_ok"]} de {summary["checks_total"]} critérios confirmados'),
        ("Acima da média", f'{summary["above_average"]}/{summary["played"]}', "indicados que jogaram"),
        ("Mitaram (+10 pts)", str(len(mitou)), escape(mitou_names)),
        ("Na seleção do Cartola", str(len(summary["in_cartola_team"])), "dos meus indicados"),
    ]
    stats_html = "".join(f'<div class="stat"><span>{t}</span><b>{v}</b><small>{s}</small></div>' for t, v, s in stats)

    chips = []
    default_total = (evaluation["my_team"]["default"] or {}).get("total")
    for name, total in evaluation["my_team"]["ranking"]:
        cls = "best" if best and name == best["formation"] else ("def" if name == DEFAULT_FORMATION else "")
        chips.append(f'<div class="fchip {cls}">{name}: {fmt(total)}</div>')
    better = best and default_total is not None and best["formation"] != DEFAULT_FORMATION and best["total"] > default_total
    forms_note = (
        f'Com os mesmos indicados, o {best["formation"]} renderia {fmt(best["total"] - default_total)} pts a mais.'
        if better else "O 4-3-3 foi a melhor formação com os meus indicados."
    )
    mine_bonus = f' <small>(inclui {fmt(mine["captain_bonus"])} do capitão)</small>' if mine.get("captain_bonus") else ""

    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><style>{_base_css()}{_themed(SUMMARY_CSS)}</style></head>
    <body><div class="art wide" id="capture">{_demo_banner(evaluation)}
      <header class="hero">{_logo()}<div class="hero-copy"><div class="hero-title">COMO FORAM MINHAS INDICAÇÕES</div>
        <div class="hero-subtitle">Rodada {evaluation["round"]} - resultado</div></div></header>
      <div class="stats">{stats_html}</div>
      <div class="teams">
        <div class="team-box"><div class="team-head"><h2>Minha seleção ({mine["formation"]})</h2><div class="tot">{fmt(mine["total"])} pts{mine_bonus}</div></div>
          {_pitch(mine, resolver, mine.get("captain_id"), cartola_ids, "na seleção")}</div>
        <div class="team-box"><div class="team-head"><h2>Seleção da rodada do Cartola</h2><div class="tot">{fmt(cartola["total"])} pts</div></div>
          {_pitch(cartola, resolver, None, my_ids, "indicado")}</div>
      </div>
      <div class="forms"><h3>Outras formações</h3>{"".join(chips)}<span style="font-weight:700">{forms_note}</span></div>
      <footer class="legend"><span><i style="background:#ffc61e"></i>Indicado que entrou na seleção do Cartola</span>
        <span><i style="background:#38c172"></i>Capitão (pontuação x1,5)</span><span><i style="background:#e0a100"></i>Mitou: mais de 10 pts</span></footer>
    </div></body></html>"""


# ------------------------------------------------------------------ painel por posição --------

PANEL_CSS = """
    .art.panel { width: 1080px; }
    .fcard { display: grid; grid-template-columns: 150px 1fr 170px; gap: 14px; align-items: center; background: __CARD__; border: 3px solid #f5f5f0; border-radius: 18px; color: #fff; padding: 12px 16px 12px 12px; margin-bottom: 14px; position: relative; }
    .fcard .who { text-align: center; }
    .fcard .ph-wrap { position: relative; width: 100px; margin: 0 auto; }
    .fcard .nm { margin: 6px auto 0; background: #f7efe7; color: #2d1908; font-weight: 800; font-size: 17px; text-transform: uppercase; padding: 3px 8px; border-radius: 6px; white-space: nowrap; overflow: hidden; max-width: 146px; }
    .fcard .mid { display: flex; flex-direction: column; gap: 8px; }
    .chips { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .chip { border-radius: 9px; padding: 4px 10px 3px; font-size: 15px; font-weight: 800; text-transform: uppercase; color: #17210b; }
    .chip.conf { background: #2bd268; color: #fff; }
    .chip.cap { background: #38c172; color: #fff; } .chip.rl { background: #ef8b2d; color: #fff; } .chip.star { background: #ffc61e; color: #241108; }
    .chk { display: flex; flex-wrap: wrap; gap: 6px 8px; }
    .ck { background: rgba(247,239,231,.96); color: #241108; border-radius: 9px; padding: 4px 10px 4px 8px; font-size: 15px; font-weight: 700; line-height: 1.15; display: flex; align-items: center; gap: 7px; }
    .ck b { width: 22px; height: 22px; border-radius: 50%; color: #fff; text-align: center; line-height: 22px; font-size: 15px; flex: none; }
    .ck.ok b { background: #138a2f; } .ck.fail b { background: #cf3a34; } .ck.info b { background: #2a7de1; } .ck.na b { background: #8a8a8a; }
    .ck small { display: block; font-size: 12px; font-weight: 500; opacity: .8; }
    .res { text-align: center; background: rgba(247,239,231,.96); color: #241108; border-radius: 14px; padding: 8px 6px 8px; }
    .res .big { font-size: 46px; font-weight: 900; line-height: 1; }
    .res .lbl { font-size: 12px; font-weight: 800; text-transform: uppercase; color: __ACCENTTEXT__; }
    .res .sub { font-size: 14px; font-weight: 700; margin-top: 3px; }
    .res .tier { margin-top: 5px; color: #fff; font-size: 13px; font-weight: 900; border-radius: 7px; padding: 2px 4px; text-transform: uppercase; }
    .fcard.dnp { opacity: .72; }
    .fcard .sel { position: absolute; top: -12px; right: 18px; background: #ffc61e; color: #241108; font-weight: 900; font-size: 13px; padding: 3px 10px; border-radius: 9px; text-transform: uppercase; }
    .empty { background: rgba(255,255,255,.85); border-radius: 16px; padding: 30px; text-align: center; font-size: 24px; font-weight: 700; }
"""

CHECK_MARK = {"ok": "✓", "fail": "✗", "info": "↔", "na": "?"}


def _result_card(player: dict, resolver: PhotoResolver) -> str:
    tier_color, tier_label = TIER_STYLE[player["tier"]]
    badges = player.get("badges", {})
    chips = [f'<span class="chip conf">CONF. {player["confidence"]}</span>']
    if badges.get("unanimidade"):
        chips.append('<span class="chip star">★ Unanimidade</span>')
    if badges.get("bom_capitao"):
        chips.append('<span class="chip cap">C Capitão</span>')
    if badges.get("bom_rl"):
        chips.append('<span class="chip rl">RL</span>')
    chips += [f'<span class="chip" style="background:#59d9f8">{display_profile_label(p)}</span>' for p in player["profiles"]]

    if player["played"]:
        checks = "".join(
            f'<div class="ck {c["status"]}"><b>{CHECK_MARK[c["status"]]}</b><div>{escape(c["label"])}<small>{escape(c["detail"])}</small></div></div>'
            for c in player["checks"]
        ) or '<div class="ck na"><b>?</b><div>Sem critério marcado</div></div>'
        base = player["baseline"].get("avg_points_season")
        res = (
            f'<div class="lbl">Pontos</div><div class="big" style="color:{tier_color}">{fmt(player["points"])}</div>'
            f'<div class="sub">média {fmt(base)} | básica {fmt(player["basic"])}</div>'
            + (f'<div class="sub" style="font-weight:500">{player["rank_position"]}º da posição na rodada</div>' if player.get("rank_position") else "")
        )
    else:
        checks = '<div class="ck na"><b>–</b><div>Não entrou em campo<small>fora das contas</small></div></div>'
        res = '<div class="lbl">Pontos</div><div class="big" style="color:#8a8a8a">-</div>'

    sel = '<div class="sel">★ Na seleção da rodada</div>' if player.get("in_cartola_team") else ""
    return (
        f'<section class="fcard {"" if player["played"] else "dnp"}">{sel}'
        f'<div class="who"><div class="ph-wrap">{_photo(player, resolver)}{_badge(player["team"])}</div>'
        f'<div class="nm">{escape(abbreviate_player_name(player["name"], 13))}</div></div>'
        f'<div class="mid"><div class="chips">{"".join(chips)}</div><div class="chk">{checks}</div></div>'
        f'<div class="res">{res}<div class="tier" style="background:{tier_color}">{tier_label}</div></div></section>'
    )


MAX_CARDS_PER_ART = 6   # acima disso a posição é dividida em mais de uma arte (leitura no celular)


def position_pages(evaluation: dict, position_key: str, max_cards: int = MAX_CARDS_PER_ART) -> list[list[dict]]:
    """Divide os jogadores de uma posição em páginas equilibradas (ex.: 11 -> 6 + 5, 12 -> 6 + 6)."""
    players = [p for p in evaluation["players"] if p["position"] == position_key]
    players.sort(key=lambda p: (not p["played"], -(p["points"] or 0)))
    if not players:
        return [[]]
    pages = -(-len(players) // max_cards)
    size = -(-len(players) // pages)
    return [players[i * size:(i + 1) * size] for i in range(pages)]


def _demo_banner(evaluation: dict) -> str:
    if not evaluation.get("demo"):
        return ""
    return (
        '<div style="background:#cf3a34;color:#fff;font-weight:900;font-size:26px;text-align:center;'
        'padding:8px;border-radius:10px;margin-bottom:14px;letter-spacing:1px">'
        "EXEMPLO PARA CONFERIR O VISUAL — DADOS SIMULADOS — NÃO PUBLICAR</div>"
    )


def build_position_panel_html(
    evaluation: dict, position_key: str, resolver: PhotoResolver, players: list[dict] | None = None,
    page: int = 1, pages: int = 1,
) -> str:
    if players is None:
        players = [p for page_players in position_pages(evaluation, position_key) for p in page_players]
    _collect_urls(players, resolver)
    cards = "".join(_result_card(p, resolver) for p in players) or '<div class="empty">Nenhum jogador indicado nesta posição.</div>'
    suffix = f" ({page}/{pages})" if pages > 1 else ""
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><style>{_base_css()}{_themed(PANEL_CSS)}</style></head>
    <body><div class="art panel" id="capture">{_demo_banner(evaluation)}
      <header class="hero">{_logo()}<div class="hero-copy"><div class="hero-title" style="font-size:56px">RESULTADO - {position_key.upper()}{suffix}</div>
        <div class="hero-subtitle">Rodada {evaluation["round"]}</div></div></header>
      <main>{cards}</main>
      <footer class="legend"><span><i style="background:#138a2f"></i>Confirmou</span><span><i style="background:#cf3a34"></i>Não confirmou</span>
        <span><i style="background:#2a7de1"></i>Estratégia: valeu para quem diferenciou</span><span><i style="background:#ffc61e"></i>Na seleção do Cartola</span></footer>
    </div></body></html>"""


def build_all_arts(evaluation: dict, resolver: PhotoResolver) -> list[dict]:
    """Todas as artes do feedback, na ordem de entrega: resumo + painéis por posição (divididos se necessário)."""
    arts = [{"label": "Resumo", "slug": "resumo", "html": build_summary_html(evaluation, resolver)}]
    for position_key in POSITION_ORDER:
        if not any(p["position"] == position_key for p in evaluation["players"]):
            continue
        pages = position_pages(evaluation, position_key)
        for number, page_players in enumerate(pages, start=1):
            label = position_key if len(pages) == 1 else f"{position_key} {number}/{len(pages)}"
            slug = normalize_text(position_key).lower() + (f"_{number}" if len(pages) > 1 else "")
            arts.append({
                "label": label,
                "slug": slug,
                "html": build_position_panel_html(evaluation, position_key, resolver, page_players, number, len(pages)),
            })
    return arts
