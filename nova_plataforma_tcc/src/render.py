from .config import BACKGROUND_FILE, FONT_BLACK_FILE, FONT_BOLD_FILE, FONT_MEDIUM_FILE, FONT_REGULAR_FILE, MAIN_LOGO_FILE
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


def render_card(card: dict) -> str:
    star_html = '<div class="star-badge">★</div>' if card["badges"]["unanimidade"] else ""
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
    confidence_colors = {
        "A": "linear-gradient(180deg, #2fdd71 0%, #1fa84f 100%)",
        "B": "linear-gradient(180deg, #d9f15f 0%, #a9c93a 100%)",
        "C": "linear-gradient(180deg, #ffd25a 0%, #ef9f1f 100%)",
        "D": "linear-gradient(180deg, #ff9670 0%, #de5b38 100%)",
    }
    confidence_html = (
        f'<div class="confidence-badge" style="background:{confidence_colors.get(card["confidence"], "#2bd268")}">'
        f'<span class="confidence-label">CONF.</span><span class="confidence-value">{card["confidence"]}</span></div>'
    )
    rl_html = '<div class="tag-circle rl">RL</div>' if card["badges"]["bom_rl"] else ""
    cap_html = '<div class="tag-circle captain">C</div>' if card["badges"]["bom_capitao"] else ""
    profile_html = "".join(
        f'<div class="profile-chip" style="background:{profile["color"]}">{profile["label"]}</div>'
        for profile in card["profile_chips"]
    )
    profile_block_html = (
        f'<div class="profiles-row"><div class="profile-label">Perfil:</div>{profile_html}</div>'
        if profile_html
        else ""
    )
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
    phrase_html = f'<div class="phrase">{card["phrase"]}</div>' if card["phrase"] else ""
    meta_html = f'<div class="player-meta">C$ {card["price"]:.2f} | MPV {card["mpv"]:.2f}</div>'
    avg_points_html = (
        f'<div class="player-average"><span class="player-average-label">{card["avg_points_label"]}</span>'
        f'<span class="player-average-value">{card["avg_points"]:.2f}'.replace(".", ",")
        + "</span></div>"
    )

    return f"""
    <section class="player-card">
        <div class="card-aside">
            <div class="card-aside-top">
                <div class="photo-wrap">{photo_html}{team_logo_html}</div>
                {star_html}
                <div class="player-name">{card["display_name"]}</div>
            </div>
            <div class="card-aside-bottom">{avg_points_html}{meta_html}</div>
        </div>
        <div class="card-main">
            <div class="metrics-row" style="grid-template-columns: repeat({max(1, len(card['metrics']))}, minmax(0, 1fr));">{metrics_html}</div>
            {phrase_html}
            <div class="tags-row">{confidence_html}{rl_html}{cap_html}{profile_block_html}</div>
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
    bg_b64 = file_to_base64(BACKGROUND_FILE)
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
                    backgroundColor: '#f4f2ed',
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
            body {{ margin: 0; background: #f4f2ed; font-family: 'Barlow', sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; text-rendering: geometricPrecision; }}
            #controls {{ position: fixed; top: 16px; right: 16px; z-index: 9999; display: flex; gap: 10px; align-items: center; }}
            #controls button {{ border: 0; border-radius: 10px; background: #0f5d00; color: white; padding: 12px 16px; font-family: 'Barlow', sans-serif; font-size: 16px; cursor: pointer; }}
            #controls select {{ border-radius: 8px; padding: 8px 10px; font-size: 14px; }}
            .report {{ width: 1080px; margin: 0 auto; padding: 28px 36px 30px; background-image: url(data:image/png;base64,{bg_b64}); background-size: cover; }}
            .report.capture-mode {{ margin: 0 !important; }}
            .hero {{ display: grid; grid-template-columns: 180px 1fr; align-items: center; gap: 18px; margin-bottom: 26px; }}
            .hero-logo {{ width: 150px; justify-self: center; }}
            .hero-copy {{ text-align: center; color: #0f5d00; }}
            .hero-title {{ font-size: 68px; line-height: 0.96; font-weight: 900; text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }}
            .hero-title.compact {{ font-size: 60px; }}
            .hero-subtitle {{ font-size: 34px; font-style: italic; margin-top: 10px; text-transform: uppercase; font-weight: 700; }}
            .cards {{ display: flex; flex-direction: column; gap: 16px; }}
            .player-card {{ display: grid; grid-template-columns: 186px 1fr; gap: 16px; background: #0f5d00; border: 3px solid #f5f5f0; border-radius: 18px; color: white; padding: 14px 16px 14px 12px; box-shadow: 0 2px 0 rgba(255,255,255,0.7) inset; }}
            .card-aside {{ position: relative; min-height: 100%; display: flex; flex-direction: column; justify-content: space-between; align-items: center; padding: 2px 0 0; }}
            .card-aside-top {{ display: flex; flex-direction: column; align-items: center; gap: 10px; width: 100%; }}
            .card-aside-bottom {{ width: 100%; display: flex; flex-direction: column; align-items: center; gap: 8px; margin-top: 8px; }}
            .photo-wrap {{ position: relative; width: 138px; height: 138px; margin-top: 2px; }}
            .player-photo {{ width: 128px; height: 128px; border-radius: 50%; object-fit: cover; object-position: top center; border: 5px solid white; background: white; }}
            .player-photo.placeholder {{ display: flex; align-items: center; justify-content: center; color: #0f5d00; font-size: 16px; font-weight: 700; }}
            .team-badge {{ position: absolute; width: 58px; height: 58px; right: 0; bottom: 0; border-radius: 50%; background: white; border: 2px solid #d6d6d6; object-fit: contain; padding: 4px; }}
            .star-badge {{ position: absolute; top: -4px; right: 10px; color: #ffc61e; font-size: 48px; line-height: 1; }}
            .player-name {{ max-width: 164px; background: #f7efe7; color: #2d1908; padding: 5px 10px; border-radius: 6px; font-size: 17px; line-height: 1; font-weight: 700; text-transform: uppercase; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: clip; }}
            .player-average {{ width: 142px; border-radius: 12px; padding: 7px 9px 6px; background: linear-gradient(180deg, rgba(245,245,240,0.96) 0%, rgba(230,238,220,0.96) 100%); border: 2px solid rgba(255,255,255,0.9); box-shadow: 0 1px 0 rgba(20,20,20,0.10); display: flex; flex-direction: column; align-items: center; gap: 3px; }}
            .player-average-label {{ color: #0f5d00; font-size: 10px; font-weight: 800; line-height: 1; text-transform: uppercase; letter-spacing: 0.25px; text-align: center; }}
            .player-average-value {{ color: #1f2d10; font-size: 21px; font-weight: 900; line-height: 1; }}
            .player-meta {{ color: #ffffff; font-size: 18px; font-weight: 700; letter-spacing: 0.15px; text-align: center; white-space: nowrap; }}
            .card-main {{ display: flex; flex-direction: column; gap: 12px; padding-top: 2px; justify-content: center; }}
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
            .phrase {{ font-size: 17px; line-height: 1.3; font-weight: 400; text-transform: none; text-align: center; max-width: 92%; margin: 0 auto; }}
            .tags-row {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: flex-start; }}
            .confidence-badge {{ min-width: 82px; height: 54px; border-radius: 16px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: white; border: 4px solid rgba(255,255,255,0.9); padding: 3px 10px 2px; }}
            .confidence-label {{ font-size: 11px; font-weight: 700; line-height: 1; letter-spacing: 0.6px; }}
            .confidence-value {{ font-size: 24px; font-weight: 800; line-height: 1; }}
            .tag-circle {{ width: 54px; height: 54px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 26px; font-weight: 700; color: white; border: 4px solid rgba(255,255,255,0.9); }}
            .tag-circle.rl {{ background: #ef8b2d; }}
            .tag-circle.captain {{ background: #e04a43; }}
            .profiles-row {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-start; }}
            .profile-label {{ color: #ffffff; font-size: 18px; font-weight: 700; line-height: 1; text-transform: uppercase; }}
            .profile-chip {{ border-radius: 10px; padding: 7px 12px 6px; color: #17210b; font-size: 18px; font-weight: 700; line-height: 1; text-transform: uppercase; }}
            .legend {{ margin-top: 18px; display: flex; justify-content: center; gap: 22px; color: #0f5d00; font-size: 18px; font-weight: 700; }}
            .legend-item {{ display: flex; align-items: center; gap: 8px; }}
            .legend-dot {{ min-width: 36px; height: 36px; padding: 0 10px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center; color: white; font-size: 18px; font-weight: 700; }}
            .legend-dot.a {{ background: #2bd268; }}
            .legend-dot.rl {{ background: #ef8b2d; }}
            .legend-dot.c {{ background: #e04a43; }}
            .legend-dot.star {{ background: #ffc61e; color: #241108; font-size: 24px; }}
            .empty-state {{ background: rgba(255,255,255,0.8); border-radius: 16px; padding: 32px; text-align: center; color: #0f5d00; font-size: 24px; font-weight: 700; }}
        </style>
    </head>
    <body>
        {controls_html}
        <div class="report" id="capture">
            <header class="hero"><img class="hero-logo" src="data:image/png;base64,{logo_b64}" alt="TCC"><div class="hero-copy"><div class="{title_class}">INDICAÇÕES - {position_key.upper()}</div><div class="hero-subtitle">{subtitle}</div></div></header>
            <main class="cards">{cards_html}</main>
            <footer class="legend">
                <div class="legend-item"><span class="legend-dot star">★</span><span>Unanimidade</span></div>
                <div class="legend-item"><span class="legend-dot a">A</span><span>Nível de confiança</span></div>
                <div class="legend-item"><span class="legend-dot rl">RL</span><span>Reserva de Luxo</span></div>
                <div class="legend-item"><span class="legend-dot c">C</span><span>Bom capitão</span></div>
            </footer>
        </div>
        {client_export_script}
    </body>
    </html>
    """
