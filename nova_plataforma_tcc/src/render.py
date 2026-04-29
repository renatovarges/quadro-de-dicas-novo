from .config import FONT_BLACK_FILE, FONT_BOLD_FILE, FONT_MEDIUM_FILE, FONT_REGULAR_FILE, MAIN_LOGO_FILE
from .utils import file_to_base64


SCOUT_FULL_LABELS = {
    "SG": "SALDO DE GOLS",
    "DE": "DEFESAS",
    "%DE": "% DEFESAS",
    "DS": "DESARMES",
    "FIN": "FINALIZAÇÕES",
    "M.BÁS": "MÉDIA BÁSICA",
    "G+A": "GOL + ASSISTÊNCIA",
    "CHT AG": "CHUTE A GOL",
    "CHT": "FINALIZAÇÕES TOTAIS",
    "M.PTS": "MÉDIA DE PONTOS",
    "VIT": "VITÓRIAS",
    "5PTS+": "FEZ 5PTS OU +",
}

_CONFIDENCE_COLORS = {
    "A": "linear-gradient(180deg, #2fdd71 0%, #1fa84f 100%)",
    "B": "linear-gradient(180deg, #d9f15f 0%, #a9c93a 100%)",
    "C": "linear-gradient(180deg, #ffd25a 0%, #ef9f1f 100%)",
    "D": "linear-gradient(180deg, #ff9670 0%, #de5b38 100%)",
}

_GOLD_STAR = "★"

_PREMIUM_CHECK_SVG = (
    '<svg viewBox="0 0 24 24" style="width:62%;height:62%;display:block">'
    '<path d="M5 12.5 L10 17.5 L19 7.5" stroke="white" stroke-width="3.2" '
    'fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>'
)


def _conf_badge(confidence: str, style_class: str) -> str:
    color = _CONFIDENCE_COLORS.get(confidence, "#2bd268")
    return (
        f'<div class="confidence-badge {style_class}" style="background:{color}">'
        f'<span class="confidence-label">CONF.</span>'
        f'<span class="confidence-value">{confidence}</span>'
        f'</div>'
    )


def _badge_html(cls: str, txt: str, size_class: str) -> str:
    if cls == "fora20":
        return f'<div class="tag-fora20 {size_class}">{_GOLD_STAR}</div>'
    return f'<div class="tag-circle {cls} {size_class}">{txt}</div>'


def _build_tags_stack(badges: dict, confidence: str) -> str:
    # Pilha vertical à esquerda. CONF sempre na base; RL acima; Capitão no topo.
    # Ordem do HTML é base->topo; o CSS usa flex-direction: column-reverse.
    items = [_conf_badge(confidence, "conf-stack")]
    if badges.get("bom_rl"):
        items.append('<div class="tag-circle rl badge-stack">RL</div>')
    if badges.get("bom_capitao"):
        items.append('<div class="tag-circle captain badge-stack">C</div>')
    return f'<div class="tags-stack">{"".join(items)}</div>'


def render_card(card: dict) -> str:
    check_html = f'<div class="check-badge">{_PREMIUM_CHECK_SVG}</div>' if card["badges"]["unanimidade"] else ""
    name_inner = f'<div class="player-name">{card["display_name"]}</div>'
    if card["badges"].get("fora_dos_20"):
        name_block = (
            f'<div class="name-anchor">'
            f'{name_inner}'
            f'<span class="fora20-mark">{_GOLD_STAR}</span>'
            f'</div>'
        )
    else:
        name_block = name_inner
    photo_html = (
        f'<img class="player-photo" src="{card["photo_url"]}" alt="{card["name"]}">'
        if card["photo_url"]
        else '<div class="player-photo placeholder">SEM FOTO</div>'
    )
    team_logo_html = (
        f'<img class="team-badge" src="data:image/png;base64,{card["team_logo_b64"]}" alt="{card["team"]}">'
        if card["team_logo_b64"]
        else ""
    )

    tags_section_html = _build_tags_stack(card["badges"], card["confidence"])

    metrics_html = "".join(
        f"""
        <div class="metric-box">
            <div class="metric-title-full">{SCOUT_FULL_LABELS.get(metric["title"], metric["title"])}</div>
            <div class="metric-body">
                <div class="metric-side metric-side-left">
                    <span class="metric-side-label">{metric["left_label"]}</span>
                    <span class="metric-value" style="color:{metric.get('left_color', '#241108')}">{metric["left_value"]}</span>
                </div>
                <div class="metric-divider">X</div>
                <div class="metric-side metric-side-right">
                    <span class="metric-side-label">{metric["right_label"]}</span>
                    <span class="metric-value" style="color:{metric.get('right_color', '#241108')}">{metric["right_value"]}</span>
                </div>
            </div>
        </div>
        """
        for metric in card["metrics"]
    )
    meta_html = f'<div class="player-meta">C$ {card["price"]:.2f} | MPV {card["mpv"]:.2f}</div>'
    avg_points_html = (
        f'<div class="player-average"><span class="player-average-label">{card["avg_points_label"]}</span>'
        f'<span class="player-average-value">{card["avg_points"]:.2f}'.replace(".", ",")
        + "</span></div>"
    )

    n_metrics = max(1, len(card["metrics"]))
    return f"""
    <section class="player-card">
        <div class="card-aside">
            <div class="card-aside-top">
                <div class="photo-wrap">{photo_html}{team_logo_html}{check_html}</div>
                {name_block}
            </div>
            <div class="card-aside-bottom">{avg_points_html}{meta_html}</div>
        </div>
        <div class="card-main">
            <div class="metrics-row" style="grid-template-columns: repeat({n_metrics}, minmax(0, 1fr));">{metrics_html}</div>
            <div class="bottom-row">
                {tags_section_html}
                <div class="write-rect"></div>
            </div>
        </div>
    </section>
    """


def build_preview_html(
    position_key: str,
    target_round: int,
    window_n: int,
    filter_mode: str,
    cards: list[dict],
    include_client_export: bool = False,
) -> str:
    logo_b64 = file_to_base64(MAIN_LOGO_FILE)
    font_regular_b64 = file_to_base64(FONT_REGULAR_FILE)
    font_medium_b64 = file_to_base64(FONT_MEDIUM_FILE)
    font_bold_b64 = file_to_base64(FONT_BOLD_FILE)
    font_black_b64 = file_to_base64(FONT_BLACK_FILE)
    subtitle_prefix = "ÚLTIMOS" if window_n > 1 else "ÚLTIMO"
    subtitle_scope = "POR MANDO" if filter_mode == "POR_MANDO" else "NO GERAL"
    subtitle = f"{subtitle_prefix} {window_n} JOGOS {subtitle_scope} - RODADA {target_round}"
    cards_html = "".join(render_card(card) for card in cards) if cards else '<div class="empty-state">Nenhum jogador selecionado.</div>'
    title_class = "hero-title compact" if len(f"INDICAÇÕES - {position_key.upper()}") > 22 else "hero-title"

    controls_html = (
        '<div id="controls"><select id="scale"><option value="3">3x</option><option value="4">4x</option><option value="5" selected>5x</option><option value="6">6x</option></select><button onclick="downloadPNG()">Baixar PNG HQ</button></div>'
        if include_client_export
        else ""
    )
    client_export_script = f"""
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js"></script>
        <script>
            function waitFrame() {{
                return new Promise((resolve) => requestAnimationFrame(() => resolve()));
            }}

            async function renderBlob(target, scale) {{
                const width = target.scrollWidth;
                const height = target.scrollHeight;
                return htmlToImage.toBlob(target, {{
                    width,
                    height,
                    pixelRatio: scale,
                    backgroundColor: '#f2e1bd',
                    cacheBust: true,
                    skipAutoScale: true,
                    style: {{
                        margin: '0',
                        width: width + 'px',
                        minHeight: height + 'px',
                    }},
                }});
            }}

            async function downloadPNG() {{
                const target = document.getElementById('capture');
                const controls = document.getElementById('controls');
                const selectedScale = parseFloat(document.getElementById('scale').value);
                const fallbackScales = [selectedScale, 6, 5, 4, 3, 2.5, 2]
                    .filter((value, index, array) => array.indexOf(value) === index);

                controls.style.display = 'none';
                target.classList.add('capture-mode');
                await waitFrame();

                try {{
                    let blob = null;
                    let usedScale = selectedScale;

                    for (const scale of fallbackScales) {{
                        try {{
                            blob = await renderBlob(target, scale);
                            if (blob) {{
                                usedScale = scale;
                                break;
                            }}
                        }} catch (error) {{
                            blob = null;
                        }}
                    }}

                    if (!blob) {{
                        throw new Error('Falha ao gerar PNG');
                    }}

                    const url = URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = url;
                    link.download = 'indicacoes_{position_key.lower()}_rodada_{target_round}.png';
                    link.click();
                    setTimeout(() => URL.revokeObjectURL(url), 100);

                    if (usedScale !== selectedScale) {{
                        alert('O PNG foi gerado em uma escala menor para evitar falha na exportação.');
                    }}
                }} catch (error) {{
                    alert('Não foi possível gerar o PNG nesta escala. Se necessário, tente 4x ou 3x.');
                }} finally {{
                    target.classList.remove('capture-mode');
                    controls.style.display = 'flex';
                }}
            }}
        </script>
    """ if include_client_export else ""

    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <style>
            @font-face {{ font-family: 'Barlow'; src: url(data:font/ttf;base64,{font_regular_b64}) format('truetype'); font-weight: 400; }}
            @font-face {{ font-family: 'Barlow'; src: url(data:font/ttf;base64,{font_medium_b64}) format('truetype'); font-weight: 500; }}
            @font-face {{ font-family: 'Barlow'; src: url(data:font/ttf;base64,{font_bold_b64}) format('truetype'); font-weight: 700; }}
            @font-face {{ font-family: 'Barlow'; src: url(data:font/ttf;base64,{font_black_b64}) format('truetype'); font-weight: 900; }}
            * {{ box-sizing: border-box; }}
            body {{ margin: 0; background: #f2e1bd; font-family: 'Barlow', sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; text-rendering: geometricPrecision; }}
            #controls {{ position: fixed; top: 16px; right: 16px; z-index: 9999; display: flex; gap: 10px; align-items: center; }}
            #controls button {{ border: 0; border-radius: 10px; background: #000000; color: white; padding: 12px 16px; font-family: 'Barlow', sans-serif; font-size: 16px; cursor: pointer; }}
            #controls select {{ border-radius: 8px; padding: 8px 10px; font-size: 14px; }}
            .report {{ width: 1080px; margin: 0 auto; padding: 28px 36px 30px; background: #f2e1bd; }}
            .report.capture-mode {{ margin: 0 !important; }}
            .hero {{ display: grid; grid-template-columns: 180px 1fr; align-items: center; gap: 18px; margin-bottom: 26px; }}
            .hero-logo-wrap {{ display: flex; flex-direction: column; align-items: center; gap: 7px; justify-self: center; }}
            .hero-logo {{ width: 150px; }}
            .hero-vip {{ color: #D4AF37; font-size: 12px; font-weight: 700; letter-spacing: 2.2px; text-transform: uppercase; font-style: italic; text-align: center; white-space: nowrap; text-shadow: 0 1px 2px rgba(0,0,0,0.12); }}
            .hero-copy {{ text-align: center; color: #000000; }}
            .hero-title {{ font-size: 68px; line-height: 0.96; font-weight: 900; text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }}
            .hero-title.compact {{ font-size: 60px; }}
            .hero-subtitle {{ font-size: 26px; font-style: italic; margin-top: 10px; text-transform: uppercase; font-weight: 700; }}
            .cards {{ display: flex; flex-direction: column; gap: 16px; }}
            .player-card {{ display: grid; grid-template-columns: 186px 1fr; gap: 16px; background: #000000; border: 3px solid #f5f5f0; border-radius: 18px; color: white; padding: 14px 16px 14px 12px; box-shadow: 0 2px 0 rgba(255,255,255,0.7) inset; }}
            .card-aside {{ position: relative; min-height: 100%; display: flex; flex-direction: column; justify-content: space-between; align-items: center; padding: 2px 0 0; }}
            .card-aside-top {{ display: flex; flex-direction: column; align-items: center; gap: 10px; width: 100%; }}
            .card-aside-bottom {{ width: 100%; display: flex; flex-direction: column; align-items: center; gap: 8px; margin-top: 8px; }}
            .photo-wrap {{ position: relative; width: 138px; height: 138px; margin-top: 2px; }}
            .player-photo {{ width: 128px; height: 128px; border-radius: 50%; object-fit: cover; object-position: top center; border: 5px solid white; background: white; }}
            .player-photo.placeholder {{ display: flex; align-items: center; justify-content: center; color: #000000; font-size: 16px; font-weight: 700; }}
            .team-badge {{ position: absolute; width: 58px; height: 58px; right: 0; bottom: 0; border-radius: 50%; background: white; border: 2px solid #d6d6d6; object-fit: contain; padding: 4px; }}
            .check-badge {{ position: absolute; top: -2px; right: -2px; width: 40px; height: 40px; border-radius: 50%; background: #00c853; border: 3px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; }}
            .player-name {{ max-width: 164px; background: #f7efe7; color: #2d1908; padding: 5px 10px; border-radius: 6px; font-size: 17px; line-height: 1; font-weight: 700; text-transform: uppercase; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: clip; }}
            .name-anchor {{ position: relative; display: inline-block; max-width: 100%; }}
            .player-average {{ width: 142px; border-radius: 12px; padding: 7px 9px 6px; background: linear-gradient(180deg, rgba(245,245,240,0.96) 0%, rgba(230,238,220,0.96) 100%); border: 2px solid rgba(255,255,255,0.9); box-shadow: 0 1px 0 rgba(20,20,20,0.10); display: flex; flex-direction: column; align-items: center; gap: 3px; }}
            .player-average-label {{ color: #000000; font-size: 10px; font-weight: 800; line-height: 1; text-transform: uppercase; letter-spacing: 0.25px; text-align: center; }}
            .player-average-value {{ color: #1f2d10; font-size: 21px; font-weight: 900; line-height: 1; }}
            .player-meta {{ color: #ffffff; font-size: 18px; font-weight: 700; letter-spacing: 0.15px; text-align: center; white-space: nowrap; }}
            .card-main {{ display: flex; flex-direction: column; gap: 12px; padding-top: 2px; }}
            .metrics-row {{ display: grid; gap: 10px; }}
            .metric-box {{ background: rgba(247, 239, 231, 0.96); color: #241108; border-radius: 10px; padding: 8px 10px; min-height: 92px; display: flex; flex-direction: column; justify-content: flex-start; gap: 6px; }}
            .metric-title-full {{ color: #111111; font-size: 12px; font-weight: 900; line-height: 1; letter-spacing: 0.15px; text-align: center; text-transform: uppercase; min-height: 24px; display: flex; align-items: center; justify-content: center; white-space: nowrap; }}
            .metric-body {{ flex: 1; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 8px; border: 1.5px solid rgba(36, 17, 8, 0.75); border-radius: 8px; padding: 8px 12px 7px; }}
            .metric-side {{ display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; }}
            .metric-side-left {{ text-align: center; }}
            .metric-side-right {{ text-align: center; }}
            .metric-side-label {{ color: #241108; font-size: 9px; font-weight: 800; line-height: 1; text-transform: uppercase; letter-spacing: 0.25px; white-space: nowrap; }}
            .metric-value {{ font-size: 21px; font-weight: 900; line-height: 1; }}
            .metric-divider {{ color: #111111; font-size: 17px; font-weight: 900; line-height: 1; align-self: center; }}
            .bottom-row {{ display: flex; gap: 10px; align-items: stretch; min-height: 130px; }}
            .tags-stack {{ display: flex; flex-direction: column-reverse; align-items: center; justify-content: flex-start; gap: 7px; flex: 0 0 auto; padding: 2px 0; }}
            .write-rect {{ flex: 1; border: 1.4px solid #D4AF37; border-radius: 12px; background: transparent; }}
            .tag-circle {{ border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; color: white; border: 3px solid rgba(255,255,255,0.9); }}
            .tag-circle.rl {{ background: #ef8b2d; }}
            .tag-circle.captain {{ background: #e04a43; }}
            .tag-circle.badge-stack {{ width: 42px; height: 42px; font-size: 17px; border-width: 2.5px; }}
            .confidence-badge {{ border-radius: 12px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: white; border: 2.5px solid rgba(255,255,255,0.9); padding: 2px 8px; }}
            .confidence-badge.conf-stack {{ min-width: 56px; height: 38px; }}
            .confidence-label {{ font-weight: 700; line-height: 1; letter-spacing: 0.3px; }}
            .confidence-value {{ font-weight: 800; line-height: 1; }}
            .conf-stack .confidence-label {{ font-size: 9px; }}
            .conf-stack .confidence-value {{ font-size: 17px; }}
            .fora20-mark {{ position: absolute; left: 100%; top: 50%; transform: translateY(-50%); margin-left: 4px; color: #ffc61e; font-size: 18px; line-height: 1; text-shadow: 0 1px 3px rgba(0,0,0,0.3); pointer-events: none; }}
            .legend {{ margin-top: 18px; display: flex; justify-content: center; gap: 22px; color: #000000; font-size: 18px; font-weight: 700; flex-wrap: wrap; }}
            .legend-item {{ display: flex; align-items: center; gap: 8px; }}
            .legend-dot {{ min-width: 36px; height: 36px; padding: 0 10px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center; color: white; font-size: 18px; font-weight: 700; }}
            .legend-check {{ width: 36px; height: 36px; min-width: 36px; padding: 0; border-radius: 50%; background: #00c853; border: 2px solid white; box-shadow: 0 1px 3px rgba(0,0,0,0.3); display: inline-flex; align-items: center; justify-content: center; }}
            .legend-dot.a {{ background: #2bd268; }}
            .legend-dot.rl {{ background: #ef8b2d; }}
            .legend-dot.c {{ background: #e04a43; }}
            .legend-fora20 {{ color: #ffc61e; font-size: 28px; line-height: 1; text-shadow: 0 1px 3px rgba(0,0,0,0.2); display: inline-flex; align-items: center; }}
            .empty-state {{ background: rgba(255,255,255,0.8); border-radius: 16px; padding: 32px; text-align: center; color: #000000; font-size: 24px; font-weight: 700; }}
        </style>
    </head>
    <body>
        {controls_html}
        <div class="report" id="capture">
            <header class="hero"><div class="hero-logo-wrap"><img class="hero-logo" src="data:image/png;base64,{logo_b64}" alt="Guardiola"><span class="hero-vip">Exclusivo · VIP Guardiola</span></div><div class="hero-copy"><div class="{title_class}">INDICAÇÕES - {position_key.upper()}</div><div class="hero-subtitle">{subtitle}</div></div></header>
            <main class="cards">{cards_html}</main>
            <footer class="legend">
                <div class="legend-item"><span class="legend-check">{_PREMIUM_CHECK_SVG}</span><span>Unanimidade</span></div>
                <div class="legend-item"><span class="legend-dot a">A</span><span>Nível de confiança</span></div>
                <div class="legend-item"><span class="legend-dot rl">RL</span><span>Reserva de Luxo</span></div>
                <div class="legend-item"><span class="legend-dot c">C</span><span>Bom capitão</span></div>
                <div class="legend-item"><span class="legend-fora20">{_GOLD_STAR}</span><span>Fora dos 20+</span></div>
            </footer>
        </div>
        {client_export_script}
    </body>
    </html>
    """
