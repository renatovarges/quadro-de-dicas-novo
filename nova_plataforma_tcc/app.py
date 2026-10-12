import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

from src.analysis import ScoutAnalyzer
from src.auth_store import delete_globo_auth, load_globo_auth, load_mpv_cache, save_globo_auth, save_mpv_cache
from src.config import DEFAULT_EXCEL_FILE, POSITION_CONFIG, ROOT_PROJECT_DIR
from src.data_sources import (
    build_mpv_cache_payload,
    build_photo_index,
    count_mpv_values,
    fetch_market_snapshot,
    fetch_mpv_map,
    load_excel_data,
    load_rounds_file,
    mpv_map_from_cache_payload,
)
from src.brand import BRAND
from src.exporter import combine_files_to_zip_bytes, combine_pngs_to_pdf_bytes, export_html_to_png_bytes, export_htmls_to_png
from src.feedback_ui import render_feedback_tab
from src.photos import photo_data_uri
from src.render import build_preview_html
from src.summary_render import build_summary_html
from src.utils import display_profile_label, normalize_text, order_indication_players, position_storage_key


ROUNDS_FILE = ROOT_PROJECT_DIR / "RODADAS_BRASILEIRAO_2026.txt"
PHOTOS_FILE = ROOT_PROJECT_DIR / "tcc_fotos_jogadores.html"
EXPORT_POSITION_ORDER = list(POSITION_CONFIG.keys())
INDICATION_ORDER_HELP = (
    "Ordem automática por posição: 1º Unanimidade → 2º Bom capitão → "
    "3º Bom RL/Luxo → 4º Confiança A, B, C e D. "
    "A mesma regra é aplicada às listas e às artes; em empate, prevalece a ordem manual."
)

HAS_MD3 = BRAND.has_md3
HAS_FORA20 = BRAND.has_fora_dos_20
BRAND_LABEL = BRAND.key.upper() if BRAND.key == "tcc" else BRAND.key.title()

st.set_page_config(page_title=BRAND.title, page_icon="⚽", layout="wide")


def get_remote_auth_config() -> dict[str, str] | None:
    try:
        config = {
            "url": str(st.secrets["SUPABASE_URL"]),
            "service_role_key": str(st.secrets["SUPABASE_SERVICE_ROLE_KEY"]),
            "encryption_key": str(st.secrets["AUTH_ENCRYPTION_KEY"]),
        }
        return config if all(config.values()) else None
    except Exception:
        return None


def describe_mpv_cache(cache_payload: dict | None) -> str:
    mpv_map = mpv_map_from_cache_payload(cache_payload)
    mpv_count = count_mpv_values(mpv_map)
    if not mpv_count:
        return ""
    generated_at = str((cache_payload or {}).get("generated_at") or "").strip()
    updated_label = generated_at[:16].replace("T", " ") + " UTC" if generated_at else "horario nao informado"
    return f"Cache MPV ativo: {mpv_count} atletas; atualizado em {updated_label}."


def check_pin() -> bool:
    try:
        correct_pin = st.secrets["PIN"]
    except Exception:
        return True

    if st.session_state.get("authenticated", False):
        return True

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("## Acesso Restrito")
        pin_input = st.text_input("PIN", type="password", max_chars=4, placeholder="****")
        if st.button("Entrar", type="primary", use_container_width=True):
            if pin_input == str(correct_pin):
                st.session_state["authenticated"] = True
                st.rerun()
            st.error("PIN incorreto.")
    return False


if not check_pin():
    st.stop()


@st.cache_resource(show_spinner=False)
def get_rounds():
    return load_rounds_file(ROUNDS_FILE)


@st.cache_resource(show_spinner=False)
def get_photo_index():
    return build_photo_index(PHOTOS_FILE)


@st.cache_resource(show_spinner="Carregando planilha de scouts...")
def get_analyzer(file_bytes: bytes | None, uploaded_name: str | None) -> ScoutAnalyzer:
    """Planilha + analisador ficam em memória e não são recriados a cada clique."""
    if file_bytes and uploaded_name:
        temp_dir = ROOT_DIR / ".tmp"
        temp_dir.mkdir(exist_ok=True)
        temp_path = temp_dir / uploaded_name
        temp_path.write_bytes(file_bytes)
        datasets = load_excel_data(temp_path)
    else:
        datasets = load_excel_data(DEFAULT_EXCEL_FILE)
    return ScoutAnalyzer(datasets["POR_JOGO"], get_rounds(), get_photo_index())


REMOTE_CACHE_SECONDS = 120


def remote_cached(name: str, loader):
    """Evita consultar o Supabase a cada interação: guarda o resultado por alguns minutos."""
    entry = st.session_state.get(f"_remote_{name}")
    if entry and time.monotonic() - entry[0] < REMOTE_CACHE_SECONDS:
        return entry[1]
    value = loader()
    st.session_state[f"_remote_{name}"] = (time.monotonic(), value)
    return value


def invalidate_remote_cache() -> None:
    for name in ("auth", "mpv_cache"):
        st.session_state.pop(f"_remote_{name}", None)


def ensure_state():
    st.session_state.setdefault("market_data", pd.DataFrame())
    st.session_state.setdefault("preview_html", None)
    st.session_state.setdefault("preview_cards", [])
    st.session_state.setdefault("preview_context", {})
    st.session_state.setdefault("preview_png_bytes", None)
    st.session_state.setdefault("preview_png_name", "")
    st.session_state.setdefault("preview_png_scale", None)
    st.session_state.setdefault("preview_pdf_bytes", None)
    st.session_state.setdefault("preview_pdf_name", "")
    st.session_state.setdefault("all_pngs_zip_bytes", None)
    st.session_state.setdefault("all_pngs_zip_name", "")
    st.session_state.setdefault("tcc_summary_png", None)
    st.session_state.setdefault("md3_summary_png", None)
    st.session_state.setdefault("tcc_summary_html", None)
    st.session_state.setdefault("md3_summary_html", None)
    st.session_state.setdefault("last_position", "Goleiros")
    if "mpv_cache" not in st.session_state:
        st.session_state["mpv_cache"] = load_mpv_cache(get_remote_auth_config())
    for position_key in POSITION_CONFIG:
        st.session_state.setdefault(position_storage_key(position_key), [])
        st.session_state.setdefault(md3_storage_key(position_key), [])
        st.session_state.setdefault(f"market_{position_key}", "")
        st.session_state.setdefault(f"last_market_{position_key}", "")
        st.session_state.setdefault(f"name_{position_key}", "")
        st.session_state.setdefault(f"full_name_{position_key}", "")
        st.session_state.setdefault(f"athlete_id_{position_key}", None)
        st.session_state.setdefault(f"team_{position_key}", "")
        st.session_state.setdefault(f"price_{position_key}", 0.0)
        st.session_state.setdefault(f"mpv_{position_key}", 0.0)
        st.session_state.setdefault(f"conf_{position_key}", "A")
        st.session_state.setdefault(f"una_{position_key}", False)
        st.session_state.setdefault(f"cap_{position_key}", False)
        st.session_state.setdefault(f"rl_{position_key}", False)
        st.session_state.setdefault(f"fora20_{position_key}", False)
        st.session_state.setdefault(f"pending_reset_{position_key}", False)
        for profile_name in POSITION_CONFIG[position_key]["profiles"]:
            st.session_state.setdefault(f"profile_{position_key}_{profile_name}", False)


def add_player_to_position(position_name: str, payload: dict):
    items = st.session_state[position_storage_key(position_name)]
    athlete_id = payload.get("athlete_id")
    if athlete_id is not None and any(item.get("athlete_id") == athlete_id for item in items):
        return
    items.append(payload)


def md3_storage_key(position_name: str) -> str:
    return f"md3_{position_storage_key(position_name)}"


def add_player_to_project(position_name: str, payload: dict, project: str) -> None:
    state_key = position_storage_key(position_name) if project == "tcc" else md3_storage_key(position_name)
    items = st.session_state[state_key]
    athlete_id = payload.get("athlete_id")
    if athlete_id is not None and any(item.get("athlete_id") == athlete_id for item in items):
        return
    items.append(payload)


def player_ui_key(player: dict, index: int) -> str:
    if player.get("_ui_key"):
        return str(player["_ui_key"])
    athlete_id = player.get("athlete_id")
    if athlete_id not in (None, ""):
        return f"id_{athlete_id}"
    raw_key = f'{player.get("team", "")}_{player.get("name", "")}'
    normalized = normalize_text(raw_key).lower().replace(" ", "_").replace("-", "_")
    player["_ui_key"] = f"manual_{normalized or 'player'}_{index}"
    return str(player["_ui_key"])


def sort_players_state(state_key: str) -> None:
    st.session_state[state_key][:] = order_indication_players(st.session_state[state_key])


def sort_all_indication_lists() -> None:
    for position in POSITION_CONFIG:
        sort_players_state(position_storage_key(position))
        sort_players_state(md3_storage_key(position))


def players_by_position(project: str) -> dict[str, list[dict]]:
    return {
        position: order_indication_players(
            st.session_state[
                position_storage_key(position) if project == "tcc" else md3_storage_key(position)
            ]
        )
        for position in POSITION_CONFIG
    }


def market_row_to_player(row: dict) -> dict:
    return {
        "name": row["nome"],
        "full_name": row.get("nome_completo", "") or row["nome"],
        "athlete_id": row.get("atleta_id"),
        "team": row["time"],
        "price": float(row.get("preco", 0.0)),
        "mpv": float(row.get("minimo_valorizar", 0.0)),
        "confidence": "A",
        "profiles": [],
        "badges": {"unanimidade": False, "bom_capitao": False, "bom_rl": False, "fora_dos_20": False},
    }


def populate_form_from_market(position_name: str, selected_row: dict | None):
    if not selected_row:
        return
    st.session_state[f"name_{position_name}"] = selected_row["nome"]
    st.session_state[f"full_name_{position_name}"] = selected_row.get("nome_completo", "") or selected_row["nome"]
    st.session_state[f"athlete_id_{position_name}"] = selected_row.get("atleta_id")
    st.session_state[f"team_{position_name}"] = selected_row["time"]
    st.session_state[f"price_{position_name}"] = float(selected_row["preco"])
    st.session_state[f"mpv_{position_name}"] = float(selected_row.get("minimo_valorizar") or 0.0)


def reset_form(position_name: str):
    st.session_state[f"pending_reset_{position_name}"] = True


def move_player(position_name: str, index: int, direction: int):
    items = st.session_state[position_storage_key(position_name)]
    new_index = index + direction
    if 0 <= new_index < len(items):
        items[index], items[new_index] = items[new_index], items[index]


def build_cards_for_position(
    analyzer: ScoutAnalyzer,
    position_name: str,
    target_round: int,
    window_n: int,
    filter_mode: str,
) -> list[dict]:
    return [
        analyzer.build_card(player, position_name, target_round, window_n, filter_mode)
        for player in order_indication_players(st.session_state[position_storage_key(position_name)])
    ]


def build_position_preview_html(
    position_name: str,
    target_round: int,
    window_n: int,
    filter_mode: str,
    cards: list[dict],
) -> str:
    return build_preview_html(
        position_key=position_name,
        target_round=target_round,
        window_n=window_n,
        filter_mode=filter_mode,
        cards=cards,
        include_client_export=False,
    )


def build_indications_export_df(target_round: int) -> pd.DataFrame:
    rows: list[dict] = []
    global_order = 1

    for position_name in EXPORT_POSITION_ORDER:
        players = order_indication_players(st.session_state.get(position_storage_key(position_name), []))
        for position_order, player in enumerate(players, start=1):
            rows.append(
                {
                    "rodada": int(target_round),
                    "posicao": position_name,
                    "ordem_na_posicao": position_order,
                    "ordem_global": global_order,
                    "nome": player.get("name", ""),
                    "nome_completo": player.get("full_name") or player.get("name", ""),
                    "clube": player.get("team", ""),
                    "atleta_id": player.get("athlete_id", ""),
                    "unanimidade": bool(player.get("badges", {}).get("unanimidade", False)),
                    "bom_capitao": bool(player.get("badges", {}).get("bom_capitao", False)),
                    "bom_rl": bool(player.get("badges", {}).get("bom_rl", False)),
                    "fora_dos_20": bool(player.get("badges", {}).get("fora_dos_20", False)),
                    "confianca": player.get("confidence", ""),
                    "perfis": "|".join(player.get("profiles", [])),
                    "preco": float(player.get("price", 0.0)),
                    "mpv": float(player.get("mpv", 0.0)),
                }
            )
            global_order += 1

    return pd.DataFrame(rows)


def build_indications_csv_bytes(target_round: int) -> bytes | None:
    export_df = build_indications_export_df(target_round)
    if export_df.empty:
        return None
    return export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


@st.fragment
def render_quick_selection(quick_position: str, status_filter: list[str]) -> None:
    """Grade de seleção rápida. É um fragmento: marcar uma caixinha re-executa só esta grade,
    não a página inteira (barra lateral, abas, indicadores etc.)."""
    market_df = st.session_state["market_data"]
    position_names = set(POSITION_CONFIG[quick_position]["market_positions"])
    quick_df = market_df[market_df["posicao_norm"].isin(position_names)].copy()
    if status_filter:
        quick_df = quick_df[quick_df["status"].isin(status_filter)]
    selected_tcc_ids = {p.get("athlete_id") for p in st.session_state[position_storage_key(quick_position)]}
    selected_md3_ids = {p.get("athlete_id") for p in st.session_state[md3_storage_key(quick_position)]}
    quick_df.insert(0, "MD3", quick_df["atleta_id"].isin(selected_md3_ids))
    quick_df.insert(0, "TCC", quick_df["atleta_id"].isin(selected_tcc_ids))
    edited = st.data_editor(
        quick_df[["TCC", "MD3", "atleta_id", "nome", "time", "status", "preco", "minimo_valorizar"]],
        hide_index=True,
        column_order=["TCC", "MD3", "nome", "time", "status", "preco", "minimo_valorizar"] if HAS_MD3
        else ["TCC", "nome", "time", "status", "preco", "minimo_valorizar"],
        disabled=["atleta_id", "nome", "time", "status", "preco", "minimo_valorizar"],
        column_config={
            "TCC": st.column_config.CheckboxColumn(BRAND_LABEL if HAS_MD3 else "Indicar"),
            "MD3": st.column_config.CheckboxColumn("MD3"),
            "atleta_id": None,
            "nome": "Jogador", "time": "Clube", "status": "Status",
            "preco": st.column_config.NumberColumn("Preço", format="C$ %.2f"),
            "minimo_valorizar": st.column_config.NumberColumn("MPV", format="%.2f"),
        },
        use_container_width=True,
        key=f"quick_grid_{quick_position}",
    )
    if st.button("Aplicar seleção", key=f"apply_quick_{quick_position}", type="primary", use_container_width=True):
        chosen_tcc_ids = set(edited.loc[edited["TCC"], "atleta_id"].tolist())
        chosen_md3_ids = set(edited.loc[edited["MD3"], "atleta_id"].tolist())
        visible_ids = set(quick_df["atleta_id"].tolist())
        for project, chosen_ids in (("tcc", chosen_tcc_ids), ("md3", chosen_md3_ids)):
            state_key = position_storage_key(quick_position) if project == "tcc" else md3_storage_key(quick_position)
            current = st.session_state[state_key]
            current[:] = [
                player for player in current
                if player.get("athlete_id") not in visible_ids or player.get("athlete_id") in chosen_ids
            ]
            chosen_rows = quick_df[quick_df["atleta_id"].isin(chosen_ids)]
            for _, row in chosen_rows.iterrows():
                add_player_to_project(quick_position, market_row_to_player(row.to_dict()), project)
            sort_players_state(state_key)
        tcc_count = len(st.session_state[position_storage_key(quick_position)])
        md3_count = len(st.session_state[md3_storage_key(quick_position)])
        st.toast(
            f"{quick_position}: {tcc_count} no TCC e {md3_count} no MD3." if HAS_MD3
            else f"{quick_position}: {tcc_count} indicado(s)."
        )
        st.rerun()  # reexecuta a página inteira para atualizar as listas de indicadores abaixo


def describe_exports(exports, label: str = "") -> None:
    """Avisa quando a escala teve de ser reduzida ou quando alguma imagem não carregou."""
    prefix = f"{label}: " if label else ""
    for export in exports:
        if export.scale_reduced:
            st.info(
                f"{prefix}a arte é muito alta para {export.requested_scale:g}x; foi exportada em "
                f"{export.scale:g}x ({export.width}x{export.height}px) para não ficar cortada ou deformada."
            )
        if export.broken_images:
            st.warning(f"{prefix}{len(export.broken_images)} imagem(ns) não carregaram na arte. Gere novamente.")


def warn_missing_photos(cards: list[dict], label: str = "") -> None:
    missing = [f'{card["name"]} ({card["team"].title()})' for card in cards if not photo_data_uri(card["photo_url"])]
    if missing:
        prefix = f"{label}: " if label else ""
        st.warning(
            f"{prefix}{len(missing)} jogador(es) SEM FOTO na arte: " + ", ".join(missing) +
            ". Rode `python nova_plataforma_tcc/tools/buscar_fotos_faltantes.py` ou adicione a foto em `assets/players/`."
        )


def render_position_pngs(positions: list[str], scale: float = 4) -> list[tuple[str, object]]:
    """Gera os PNGs de várias posições numa única sessão do navegador."""
    htmls, used = [], []
    for pos in positions:
        cards = build_cards_for_position(analyzer, pos, target_round, window_n, filter_mode)
        if not cards:
            continue
        warn_missing_photos(cards, pos)
        htmls.append(build_position_preview_html(pos, target_round, window_n, filter_mode, cards))
        used.append(pos)
    return list(zip(used, export_htmls_to_png(htmls, scale)))


ensure_state()
sort_all_indication_lists()

st.title(BRAND.title)
st.caption(f"Projeto base em `{ROOT_PROJECT_DIR}`")

rounds_data = get_rounds()
photo_index = get_photo_index()

with st.sidebar:
    st.header("Parâmetros")
    if st.session_state["last_position"] not in POSITION_CONFIG:
        st.session_state["last_position"] = "Goleiros"
    position_key = st.selectbox(
        "Posição",
        list(POSITION_CONFIG.keys()),
        index=list(POSITION_CONFIG.keys()).index(st.session_state["last_position"]),
    )
    st.session_state["last_position"] = position_key
    position_cfg = POSITION_CONFIG[position_key]

    round_options = sorted(rounds_data.keys())
    target_round = st.selectbox("Rodada-alvo", round_options, index=min(11, len(round_options) - 1))
    window_n = st.slider("Janela de jogos", min_value=1, max_value=10, value=3)
    filter_mode_label = st.radio("Filtro de mando", ["Por mando", "Todos"], index=0)
    filter_mode = "POR_MANDO" if filter_mode_label == "Por mando" else "TODOS"

    st.divider()
    st.subheader("Fontes")
    uploaded_excel = st.file_uploader("Planilha de scouts", type=["xlsx"])
    remote_config = get_remote_auth_config()
    saved_auth = remote_cached("auth", lambda: bool(load_globo_auth(remote_config)))
    gm_token = ""
    globo_id_token = ""
    globo_refresh_token = ""
    with st.expander("Renovação automática do token"):
        if saved_auth:
            st.success("Conta Globo conectada. A renovação é feita exclusivamente pelo robô automático.")
            replace_tokens = st.checkbox(
                "Substituir tokens da Globo",
                help="Use somente quando a Globo encerrar a sessão automática.",
            )
        else:
            replace_tokens = True
        if replace_tokens:
            st.caption("Cole o conjunto obtido no Response do refresh-token.")
            gm_token = st.text_input("Access token", type="password")
            globo_id_token = st.text_input("ID token", type="password")
            globo_refresh_token = st.text_input("Refresh token", type="password")
        if saved_auth and st.button("Desconectar conta Globo", use_container_width=True):
            delete_globo_auth(remote_config)
            invalidate_remote_cache()
            st.rerun()
    latest_cache = remote_cached("mpv_cache", lambda: load_mpv_cache(remote_config))
    if latest_cache:
        st.session_state["mpv_cache"] = latest_cache
    cache_description = describe_mpv_cache(st.session_state.get("mpv_cache"))
    if cache_description:
        st.caption(cache_description)
    if st.button("Atualizar mercado", use_container_width=True, type="primary"):
        with st.spinner("Buscando mercado do Cartola..."):
            active_access_token = ""
            live_mpv_map: dict[int, float] = {}
            live_mpv_count = 0
            invalidate_remote_cache()
            latest_cache = remote_cached("mpv_cache", lambda: load_mpv_cache(remote_config))
            if latest_cache:
                st.session_state["mpv_cache"] = latest_cache
            cached_mpv_map = mpv_map_from_cache_payload(st.session_state.get("mpv_cache"))
            used_cached_mpv = False
            supplied_tokens = [gm_token.strip(), globo_id_token.strip(), globo_refresh_token.strip()]
            if any(supplied_tokens):
                if all(supplied_tokens):
                    new_tokens = {
                        "access_token": gm_token.strip(),
                        "id_token": globo_id_token.strip(),
                        "refresh_token": globo_refresh_token.strip(),
                    }
                    save_globo_auth(new_tokens, remote_config)
                    invalidate_remote_cache()
                    active_access_token = new_tokens["access_token"]
                    st.caption("Tokens salvos. A partir de agora, somente o robô fará a renovação.")
                else:
                    st.warning("Para substituir a sessão, preencha os três tokens.")
            if not active_access_token:
                if cached_mpv_map:
                    used_cached_mpv = True
                    st.caption("Usando o cache automático de MPV salvo.")
                else:
                    st.warning("Mercado público será carregado sem MPV. Conecte a conta Globo para iniciar o cache automático.")
            else:
                live_mpv_map = fetch_mpv_map(active_access_token)
                live_mpv_count = count_mpv_values(live_mpv_map)
                if live_mpv_count:
                    st.caption("MPV puxado do Gato Mestre; cache será atualizado.")
                elif cached_mpv_map:
                    used_cached_mpv = True
                    st.warning("Gato Mestre não retornou MPV agora; usando o cache automático salvo.")
                else:
                    st.warning("Gato Mestre não retornou MPV e ainda não existe cache automático salvo.")
            try:
                st.session_state["market_data"] = fetch_market_snapshot(
                    mpv_map=live_mpv_map,
                    fallback_mpv_map=cached_mpv_map,
                )
                if live_mpv_count:
                    cache_payload = build_mpv_cache_payload(
                        live_mpv_map,
                        source="gato_mestre_manual",
                        market_count=len(st.session_state["market_data"]),
                    )
                    try:
                        save_mpv_cache(cache_payload, remote_config)
                        invalidate_remote_cache()
                        st.session_state["mpv_cache"] = cache_payload
                        st.caption("Cache MPV salvo para o robô e para os próximos acessos.")
                    except Exception as exc:
                        st.warning(f"MPV carregado, mas não foi possível salvar o cache: {exc}")
            except Exception as exc:
                st.session_state["market_data"] = pd.DataFrame()
                st.error(
                    "Não foi possível acessar a API do Cartola. Verifique a conexão com a internet "
                    f"e tente novamente. Detalhe: {exc}"
                )
        if not st.session_state["market_data"].empty:
            total_market = len(st.session_state["market_data"])
            if "minimo_valorizar" in st.session_state["market_data"]:
                mpv_values = st.session_state["market_data"]["minimo_valorizar"].fillna(0)
                mpv_count = int(mpv_values.ne(0).sum())
            else:
                mpv_count = 0
            if live_mpv_count and mpv_count > 0:
                st.success(f"{total_market} atletas carregados; MPV atualizado ao vivo para {mpv_count} atletas.")
            elif used_cached_mpv and mpv_count > 0:
                st.success(f"{total_market} atletas carregados; MPV carregado do cache automático para {mpv_count} atletas.")
            elif active_access_token:
                st.error(
                    f"{total_market} atletas carregados, mas nenhum MPV foi retornado. "
                    "O access token não liberou o Gato Mestre e não há cache automático disponível."
                )
            else:
                st.success(f"{total_market} atletas carregados.")
                st.info("MPV não carregado porque nenhum token Globo foi informado.")

analyzer = get_analyzer(
    uploaded_excel.getvalue() if uploaded_excel else None,
    uploaded_excel.name if uploaded_excel else None,
)
indications_csv_bytes = build_indications_csv_bytes(target_round)

market_df = st.session_state["market_data"]
cards_state_key = position_storage_key(position_key)
current_cards = st.session_state[cards_state_key]

if st.session_state.get(f"pending_reset_{position_key}", False):
    st.session_state[f"market_{position_key}"] = ""
    st.session_state[f"last_market_{position_key}"] = ""
    st.session_state[f"name_{position_key}"] = ""
    st.session_state[f"full_name_{position_key}"] = ""
    st.session_state[f"athlete_id_{position_key}"] = None
    st.session_state[f"team_{position_key}"] = ""
    st.session_state[f"price_{position_key}"] = 0.0
    st.session_state[f"mpv_{position_key}"] = 0.0
    st.session_state[f"conf_{position_key}"] = "A"
    st.session_state[f"una_{position_key}"] = False
    st.session_state[f"cap_{position_key}"] = False
    st.session_state[f"rl_{position_key}"] = False
    st.session_state[f"fora20_{position_key}"] = False
    for profile_name in POSITION_CONFIG[position_key]["profiles"]:
        st.session_state[f"profile_{position_key}_{profile_name}"] = False
    st.session_state[f"pending_reset_{position_key}"] = False

tab_quick, tab_editor, tab_preview, tab_summaries, tab_feedback = st.tabs(
    ["Seleção rápida", f"Editor detalhado {BRAND_LABEL}", f"Premium {BRAND_LABEL}",
     "Resumos TCC e MD3" if HAS_MD3 else f"Resumo {BRAND_LABEL}", "Feedback da rodada"]
)

with tab_quick:
    st.subheader("Seleção rápida de jogadores")
    st.caption("Marque prováveis e dúvidas em qualquer posição. Eles entram com confiança A e podem ser refinados logo abaixo.")
    if market_df.empty:
        st.info("Clique em Atualizar mercado na barra lateral para carregar os atletas.")
    else:
        status_options = sorted(market_df["status"].dropna().unique().tolist())
        status_filter = st.multiselect(
            "Status exibidos",
            options=status_options,
            default=[status for status in ["Provável", "Dúvida"] if status in status_options],
        )
        quick_tabs = st.tabs(list(POSITION_CONFIG.keys()))
        for quick_tab, quick_position in zip(quick_tabs, POSITION_CONFIG.keys()):
            with quick_tab:
                render_quick_selection(quick_position, status_filter)

        st.divider()
        st.subheader(f"Indicadores {BRAND_LABEL}")
        st.caption(f"Configure confiança, destaques e perfis do {BRAND_LABEL}.")
        st.info(INDICATION_ORDER_HELP)
        for edit_position in POSITION_CONFIG:
            players = st.session_state[position_storage_key(edit_position)]
            if not players:
                continue
            with st.expander(f"{edit_position} ({len(players)})"):
                profile_options = POSITION_CONFIG[edit_position]["profiles"]
                column_widths = [2.4, 0.8, 0.8, 0.9, 0.8] + [1.0] * len(profile_options) + ([1.0] if HAS_FORA20 else [])
                header_labels = ["Jogador", "Conf.", "Unân.", "Capitão", "Bom RL"] + [
                    display_profile_label(profile) for profile in profile_options
                ] + (["Fora 20+"] if HAS_FORA20 else [])
                header_columns = st.columns(column_widths)
                for column, label in zip(header_columns, header_labels):
                    column.caption(label)

                pending_indicators: list[dict] = []
                with st.form(f"indicator_form_{edit_position}"):
                    for idx, player in enumerate(players):
                        player_key = player_ui_key(player, idx)
                        row_columns = st.columns(column_widths)
                        row_columns[0].markdown(f'**{player["name"]}**  \n{player["team"]}')
                        confidence_value = player.get("confidence", "A")
                        confidence = row_columns[1].selectbox(
                            f"Confiança de {player['name']}",
                            options=["A", "B", "C", "D"],
                            index=["A", "B", "C", "D"].index(confidence_value) if confidence_value in ["A", "B", "C", "D"] else 0,
                            key=f"quick_conf_{edit_position}_{player_key}",
                            label_visibility="collapsed",
                        )
                        unanimity = row_columns[2].checkbox(
                            f"Unanimidade - {player['name']}",
                            value=bool(player.get("badges", {}).get("unanimidade", False)),
                            key=f"quick_una_{edit_position}_{player_key}",
                            label_visibility="collapsed",
                        )
                        captain = row_columns[3].checkbox(
                            f"Bom capitão - {player['name']}",
                            value=bool(player.get("badges", {}).get("bom_capitao", False)),
                            key=f"quick_cap_{edit_position}_{player_key}",
                            label_visibility="collapsed",
                        )
                        good_rl = row_columns[4].checkbox(
                            f"Bom RL - {player['name']}",
                            value=bool(player.get("badges", {}).get("bom_rl", False)),
                            key=f"quick_rl_{edit_position}_{player_key}",
                            label_visibility="collapsed",
                        )
                        fora20 = False
                        if HAS_FORA20:
                            fora20 = row_columns[5 + len(profile_options)].checkbox(
                                f"Fora dos 20+ - {player['name']}",
                                value=bool(player.get("badges", {}).get("fora_dos_20", False)),
                                key=f"quick_fora20_{edit_position}_{player_key}",
                                label_visibility="collapsed",
                            )
                        selected_profiles = []
                        for profile_idx, profile in enumerate(profile_options):
                            if row_columns[5 + profile_idx].checkbox(
                                f"{display_profile_label(profile)} - {player['name']}",
                                value=profile in player.get("profiles", []),
                                key=f"quick_profile_{edit_position}_{player_key}_{profile}",
                                label_visibility="collapsed",
                            ):
                                selected_profiles.append(profile)
                        pending_indicators.append(
                            {
                                "confidence": confidence,
                                "profiles": selected_profiles,
                                "badges": {
                                    "unanimidade": unanimity,
                                    "bom_capitao": captain,
                                    "bom_rl": good_rl,
                                    "fora_dos_20": fora20,
                                },
                            }
                        )
                    submitted = st.form_submit_button("Salvar indicadores", use_container_width=True, type="primary")
                if submitted:
                    for player, values in zip(players, pending_indicators):
                        player.update(values)
                    sort_players_state(position_storage_key(edit_position))
                    st.success("Confianças, destaques e perfis salvos.")

        if HAS_MD3:
            st.divider()
            st.subheader("Indicadores MD3")
            st.caption("Os indicadores do MD3 são independentes dos indicadores do TCC.")
            st.info(INDICATION_ORDER_HELP)
            for edit_position in POSITION_CONFIG:
                md3_players = st.session_state[md3_storage_key(edit_position)]
                if not md3_players:
                    continue
                with st.expander(f"{edit_position} · MD3 ({len(md3_players)})"):
                    widths = [2.8, 1.0, 1.0, 1.0, 1.0]
                    headers = st.columns(widths)
                    for column, label in zip(headers, ["Jogador", "Conf.", "Unân.", "Capitão", "Luxo"]):
                        column.caption(label)
                    pending_md3: list[dict] = []
                    with st.form(f"md3_indicator_form_{edit_position}"):
                        for idx, player in enumerate(md3_players):
                            player_key = player_ui_key(player, idx)
                            columns = st.columns(widths)
                            columns[0].markdown(f'**{player["name"]}**  \n{player["team"]}')
                            current_confidence = player.get("confidence", "A")
                            confidence = columns[1].selectbox(
                                f"Confiança MD3 de {player['name']}",
                                options=["A", "B", "C", "D"],
                                index=["A", "B", "C", "D"].index(current_confidence) if current_confidence in ["A", "B", "C", "D"] else 0,
                                key=f"md3_conf_{edit_position}_{player_key}",
                                label_visibility="collapsed",
                            )
                            unanimity = columns[2].checkbox(
                                f"Unanimidade MD3 - {player['name']}",
                                value=bool(player.get("badges", {}).get("unanimidade", False)),
                                key=f"md3_una_{edit_position}_{player_key}",
                                label_visibility="collapsed",
                            )
                            captain = columns[3].checkbox(
                                f"Bom capitão MD3 - {player['name']}",
                                value=bool(player.get("badges", {}).get("bom_capitao", False)),
                                key=f"md3_cap_{edit_position}_{player_key}",
                                label_visibility="collapsed",
                            )
                            luxury = columns[4].checkbox(
                                f"Luxo MD3 - {player['name']}",
                                value=bool(player.get("badges", {}).get("bom_rl", False)),
                                key=f"md3_rl_{edit_position}_{player_key}",
                                label_visibility="collapsed",
                            )
                            pending_md3.append(
                                {
                                    "confidence": confidence,
                                    "badges": {
                                        "unanimidade": unanimity,
                                        "bom_capitao": captain,
                                        "bom_rl": luxury,
                                    },
                                }
                            )
                        submitted_md3 = st.form_submit_button(
                            "Salvar indicadores MD3", use_container_width=True, type="primary"
                        )
                    if submitted_md3:
                        for player, values in zip(md3_players, pending_md3):
                            player.update(values)
                        sort_players_state(md3_storage_key(edit_position))
                        st.success("Indicadores do MD3 salvos.")

with tab_editor:
    st.subheader(f"Editor de {position_key}")

    available_market = market_df.copy()
    if not available_market.empty:
        target_positions = set(position_cfg["market_positions"])
        available_market = available_market[available_market["posicao_norm"].isin(target_positions)].copy()
        available_market["display_name"] = available_market.apply(
            lambda row: f'{row["nome"]} - {row["time"]} (C$ {row["preco"]:.2f})',
            axis=1,
        )
        selected_market = st.selectbox(
            "Buscar atleta no mercado",
            [""] + available_market["display_name"].tolist(),
            key=f"market_{position_key}",
        )
        selected_row = (
            available_market[available_market["display_name"] == selected_market].iloc[0].to_dict()
            if selected_market
            else None
        )
        if selected_market != st.session_state.get(f"last_market_{position_key}", ""):
            st.session_state[f"last_market_{position_key}"] = selected_market
            populate_form_from_market(position_key, selected_row)
    else:
        selected_row = None
        st.info("Use o botão de atualizar mercado na barra lateral para preencher a busca automática.")

    with st.expander("Adicionar jogador", expanded=True):
        c1, c2, c3 = st.columns(3)
        player_name = c1.text_input("Nome", key=f"name_{position_key}")
        team_name = c2.text_input("Time", key=f"team_{position_key}")
        player_price = c3.number_input(
            "Preço",
            min_value=0.0,
            format="%.2f",
            key=f"price_{position_key}",
        )

        c4, c5 = st.columns(2)
        player_mpv = c4.number_input(
            "MPV",
            format="%.2f",
            key=f"mpv_{position_key}",
        )
        confidence = c5.select_slider("Confiança", options=["A", "B", "C", "D"], key=f"conf_{position_key}")

        st.caption("Destaques")
        badge_columns = st.columns(4 if HAS_FORA20 else 3)
        badge_unanimity = badge_columns[0].checkbox("Unanimidade", key=f"una_{position_key}")
        badge_captain = badge_columns[1].checkbox("Bom Capitão", key=f"cap_{position_key}")
        badge_rl = badge_columns[2].checkbox("Bom RL", key=f"rl_{position_key}")
        badge_fora20 = (
            badge_columns[3].checkbox("Fora dos 20+", key=f"fora20_{position_key}") if HAS_FORA20 else False
        )

        st.caption("Perfis")
        selected_profiles = []
        for col, profile_name in zip(st.columns(len(position_cfg["profiles"])), position_cfg["profiles"]):
            if col.checkbox(display_profile_label(profile_name).title(), key=f"profile_{position_key}_{profile_name}"):
                selected_profiles.append(profile_name)

        if st.button("Adicionar à lista", use_container_width=True, type="primary", key=f"add_{position_key}"):
            if not player_name.strip() or not team_name.strip():
                st.error("Informe ao menos nome e time do jogador.")
            else:
                add_player_to_position(
                    position_key,
                    {
                        "name": player_name.strip(),
                        "full_name": st.session_state.get(f"full_name_{position_key}", "").strip(),
                        "athlete_id": st.session_state.get(f"athlete_id_{position_key}"),
                        "team": team_name.strip(),
                        "price": float(player_price),
                        "mpv": float(player_mpv),
                        "confidence": confidence,
                        "profiles": selected_profiles,
                        "badges": {
                            "unanimidade": badge_unanimity,
                            "bom_capitao": badge_captain,
                            "bom_rl": badge_rl,
                            "fora_dos_20": badge_fora20,
                        },
                    },
                )
                sort_players_state(position_storage_key(position_key))
                reset_form(position_key)
                st.rerun()

    st.divider()
    st.subheader("Lista atual")
    st.caption(INDICATION_ORDER_HELP)
    if not current_cards:
        st.info("Nenhum jogador adicionado nesta posição.")
    else:
        for idx, player in enumerate(current_cards):
            c1, c2, c3, c4 = st.columns([6, 1, 1, 1])
            profiles_label = ", ".join(display_profile_label(profile) for profile in player["profiles"]) if player["profiles"] else "Sem perfil"
            c1.markdown(
                f'**{player["name"]}** · {player["team"]} · C$ {player["price"]:.2f} · MPV {player["mpv"]:.2f} · Conf {player["confidence"]} · {profiles_label}'
            )
            if c2.button("↑", key=f"up_{position_key}_{idx}"):
                move_player(position_key, idx, -1)
                st.rerun()
            if c3.button("↓", key=f"down_{position_key}_{idx}"):
                move_player(position_key, idx, 1)
                st.rerun()
            if c4.button("Excluir", key=f"del_{position_key}_{idx}"):
                del st.session_state[cards_state_key][idx]
                st.rerun()

    if indications_csv_bytes:
        st.download_button(
            "Baixar CSV das indicacoes",
            data=indications_csv_bytes,
            file_name=f"indicacoes_rodada_{target_round}.csv",
            mime="text/csv",
            key=f"download_csv_editor_{target_round}",
            use_container_width=True,
        )
        st.caption("O CSV consolida todas as indicacoes montadas no editor e segue a hierarquia editorial de cada posicao.")

with tab_preview:
    st.subheader(f"Prévia de {position_key}")
    st.caption("A visualização gera o painel completo da posição. O download recomendado agora é feito pelo servidor para maior confiabilidade.")

    if st.button("Gerar visualização", type="primary", use_container_width=True):
        rendered_cards = build_cards_for_position(analyzer, position_key, target_round, window_n, filter_mode)
        st.session_state["preview_cards"] = rendered_cards
        warn_missing_photos(rendered_cards)
        st.session_state["preview_context"] = {
            "position_key": position_key,
            "target_round": target_round,
            "window_n": window_n,
            "filter_mode": filter_mode,
        }
        st.session_state["preview_html"] = build_position_preview_html(
            position_name=position_key,
            target_round=target_round,
            window_n=window_n,
            filter_mode=filter_mode,
            cards=rendered_cards,
        )
        st.session_state["preview_png_bytes"] = None
        st.session_state["preview_png_name"] = ""
        st.session_state["preview_png_scale"] = None
        st.session_state["preview_pdf_bytes"] = None
        st.session_state["preview_pdf_name"] = ""
        st.session_state["all_pngs_zip_bytes"] = None
        st.session_state["all_pngs_zip_name"] = ""

    if st.session_state["preview_html"]:
        export_col1, export_col2, export_col3 = st.columns([1.2, 1, 1.15])
        with export_col1:
            if st.button("Gerar PNG pelo servidor", use_container_width=True, type="secondary"):
                preview_context = st.session_state.get("preview_context", {})
                export_html = build_position_preview_html(
                    position_name=preview_context["position_key"],
                    target_round=preview_context["target_round"],
                    window_n=preview_context["window_n"],
                    filter_mode=preview_context["filter_mode"],
                    cards=st.session_state.get("preview_cards", []),
                )
                with st.spinner("Gerando PNG em alta qualidade..."):
                    try:
                        export = export_htmls_to_png([export_html], 4)[0]
                        st.session_state["preview_png_bytes"] = export.png
                        st.session_state["preview_png_scale"] = export.scale
                        st.session_state["preview_png_name"] = (
                            f'indicacoes_{preview_context["position_key"].lower()}_rodada_{preview_context["target_round"]}.png'
                        )
                        st.success(f"PNG pronto em {export.scale:g}x ({export.width}x{export.height}px).")
                        describe_exports([export])
                    except Exception as exc:
                        st.error(f"Não consegui gerar o PNG no servidor: {str(exc).strip() or repr(exc)}")
        with export_col2:
            if st.session_state.get("preview_png_bytes"):
                st.download_button(
                    "Baixar PNG pronto",
                    data=st.session_state["preview_png_bytes"],
                    file_name=st.session_state["preview_png_name"],
                    mime="image/png",
                    key=f"download_png_ready_{target_round}_{position_key}",
                    use_container_width=True,
                )
        with export_col3:
            if st.button("Gerar PDF com todas as posições", use_container_width=True, type="secondary"):
                positions_with_cards = [
                    pos for pos in POSITION_CONFIG.keys()
                    if st.session_state.get(position_storage_key(pos))
                ]
                if not positions_with_cards:
                    st.error("Não há jogadores adicionados em nenhuma posição para montar o PDF.")
                else:
                    with st.spinner("Gerando PDF consolidado com todas as posições..."):
                        try:
                            rendered = render_position_pngs(positions_with_cards, 4)
                            describe_exports([item for _, item in rendered])
                            st.session_state["preview_pdf_bytes"] = combine_pngs_to_pdf_bytes(
                                [item.png for _, item in rendered]
                            )
                            st.session_state["preview_pdf_name"] = f'indicacoes_completas_rodada_{target_round}.pdf'
                            st.success("PDF pronto com: " + ", ".join(pos for pos, _ in rendered) + ".")
                        except Exception as exc:
                            st.error(f"Não consegui gerar o PDF consolidado: {str(exc).strip() or repr(exc)}")
        if st.button("Gerar pacote com todos os PNGs", use_container_width=True, type="secondary"):
            positions_with_cards = [
                pos for pos in POSITION_CONFIG
                if st.session_state.get(position_storage_key(pos))
            ]
            has_md3_cards = any(st.session_state.get(md3_storage_key(pos)) for pos in POSITION_CONFIG)
            if not positions_with_cards and not has_md3_cards:
                st.error("Não há jogadores adicionados para gerar o pacote.")
            else:
                png_files: list[tuple[str, bytes]] = []
                with st.spinner("Gerando um PNG por posição e montando o ZIP..."):
                    try:
                        rendered = render_position_pngs(positions_with_cards, 4)
                        describe_exports([item for _, item in rendered], "Posições")
                        for pos, item in rendered:
                            png_files.append((f"indicacoes_{pos.lower()}_rodada_{target_round}.png", item.png))
                        summary_projects = []
                        if positions_with_cards:
                            summary_projects.append(("tcc", "TCC"))
                        if has_md3_cards:
                            summary_projects.append(("md3", "MD3"))
                        summary_htmls = [
                            build_summary_html(
                                BRAND.summary_theme if project == "tcc" else project,
                                target_round,
                                players_by_position(project),
                            )
                            for project, _ in summary_projects
                        ]
                        summary_items = export_htmls_to_png(summary_htmls, 3)
                        describe_exports(summary_items, "Resumos")
                        for (project, _), item in zip(summary_projects, summary_items):
                            png_files.append((f"dicas_resumo_{project}_rodada_{target_round}.png", item.png))
                        st.session_state["all_pngs_zip_bytes"] = combine_files_to_zip_bytes(png_files)
                        st.session_state["all_pngs_zip_name"] = f"indicacoes_png_rodada_{target_round}.zip"
                        st.success(f"Pacote pronto com {len(png_files)} PNG(s).")
                    except Exception as exc:
                        st.error(f"Falha ao gerar o pacote: {str(exc).strip() or repr(exc)}")
        if st.session_state.get("all_pngs_zip_bytes"):
            st.download_button(
                "Baixar todos os PNGs (.zip)",
                data=st.session_state["all_pngs_zip_bytes"],
                file_name=st.session_state["all_pngs_zip_name"],
                mime="application/zip",
                key=f"download_all_pngs_{target_round}",
                use_container_width=True,
            )
        if st.session_state.get("preview_pdf_bytes"):
            st.download_button(
                "Baixar PDF consolidado",
                data=st.session_state["preview_pdf_bytes"],
                file_name=st.session_state["preview_pdf_name"],
                mime="application/pdf",
                key=f"download_pdf_ready_{target_round}",
                use_container_width=True,
            )
        if indications_csv_bytes:
            st.download_button(
                "Baixar CSV das indicacoes",
                data=indications_csv_bytes,
                file_name=f"indicacoes_rodada_{target_round}.csv",
                mime="text/csv",
                key=f"download_csv_preview_{target_round}",
                use_container_width=True,
            )

        st.components.v1.html(st.session_state["preview_html"], height=1700, scrolling=True)
    else:
        st.info("Monte a lista e clique em gerar visualização.")

with tab_summaries:
    st.subheader("Resumos gerais TCC e MD3" if HAS_MD3 else f"Resumo geral {BRAND_LABEL}")
    tcc_total = sum(len(items) for items in players_by_position("tcc").values())
    md3_total = sum(len(items) for items in players_by_position("md3").values()) if HAS_MD3 else 0
    st.caption(
        f"Seleção atual: {tcc_total} jogador(es) no TCC e {md3_total} jogador(es) no MD3. "
        "As alturas das duas artes são ajustadas automaticamente."
        if HAS_MD3
        else f"Seleção atual: {tcc_total} jogador(es). A altura da arte é ajustada automaticamente."
    )

    if st.button(
        "Gerar/atualizar os dois resumos" if HAS_MD3 else "Gerar/atualizar o resumo",
        type="primary",
        use_container_width=True,
    ):
        st.session_state["tcc_summary_html"] = build_summary_html(
            BRAND.summary_theme, target_round, players_by_position("tcc")
        )
        st.session_state["md3_summary_html"] = (
            build_summary_html("md3", target_round, players_by_position("md3")) if HAS_MD3 else None
        )
        st.session_state["tcc_summary_png"] = None
        st.session_state["md3_summary_png"] = None

    summary_specs = [(BRAND_LABEL, "tcc_summary_html", "tcc_summary_png", "tcc")]
    if HAS_MD3:
        summary_specs.append(("MD3", "md3_summary_html", "md3_summary_png", "md3"))
    summary_columns = st.columns(len(summary_specs))
    for column, (label, html_key, png_key, file_slug) in zip(summary_columns, summary_specs):
        with column:
            st.markdown(f"### Resumo {label}")
            summary_html = st.session_state.get(html_key)
            if not summary_html:
                st.info("Gere os resumos para visualizar esta arte.")
                continue
            st.components.v1.html(summary_html, height=1100, scrolling=True)
            if st.button(
                f"Gerar PNG resumido {label}",
                key=f"generate_summary_{file_slug}",
                use_container_width=True,
            ):
                last_error = None
                with st.spinner(f"Gerando resumo {label}..."):
                    for scale in [3, 2]:
                        try:
                            st.session_state[png_key] = export_html_to_png_bytes(summary_html, scale=scale)
                            last_error = None
                            break
                        except Exception as exc:
                            last_error = exc
                if last_error and not st.session_state.get(png_key):
                    st.error(f"Não foi possível gerar o resumo {label}: {last_error}")
                else:
                    st.success(f"Resumo {label} pronto.")
            if st.session_state.get(png_key):
                st.download_button(
                    f"Baixar resumo {label}",
                    data=st.session_state[png_key],
                    file_name=f"dicas_resumo_{file_slug}_rodada_{target_round}.png",
                    mime="image/png",
                    key=f"download_summary_{file_slug}_{target_round}",
                    use_container_width=True,
                )

    if st.session_state.get("tcc_summary_png") or st.session_state.get("md3_summary_png"):
        summary_files = []
        if st.session_state.get("tcc_summary_png"):
            summary_files.append((f"dicas_resumo_tcc_rodada_{target_round}.png", st.session_state["tcc_summary_png"]))
        if st.session_state.get("md3_summary_png"):
            summary_files.append((f"dicas_resumo_md3_rodada_{target_round}.png", st.session_state["md3_summary_png"]))
        st.download_button(
            "Baixar resumos disponíveis (.zip)",
            data=combine_files_to_zip_bytes(summary_files),
            file_name=f"resumos_tcc_md3_rodada_{target_round}.zip",
            mime="application/zip",
            use_container_width=True,
        )

with tab_feedback:
    render_feedback_tab(
        analyzer, players_by_position("tcc"), target_round, window_n, filter_mode, get_remote_auth_config()
    )
