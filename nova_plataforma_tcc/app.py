import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

from src.analysis import ScoutAnalyzer
from src.auth_store import delete_globo_auth, load_globo_auth, save_globo_auth
from src.config import DEFAULT_EXCEL_FILE, POSITION_CONFIG, ROOT_PROJECT_DIR
from src.data_sources import (
    build_photo_index,
    fetch_market_snapshot,
    load_excel_data,
    load_rounds_file,
    refresh_globo_tokens,
)
from src.exporter import combine_files_to_zip_bytes, combine_pngs_to_pdf_bytes, export_html_to_png_bytes
from src.render import build_preview_html
from src.utils import display_profile_label, position_storage_key


ROUNDS_FILE = ROOT_PROJECT_DIR / "RODADAS_BRASILEIRAO_2026.txt"
PHOTOS_FILE = ROOT_PROJECT_DIR / "tcc_fotos_jogadores.html"
EXPORT_POSITION_ORDER = list(POSITION_CONFIG.keys())

st.set_page_config(page_title="Nova Plataforma TCC", page_icon="⚽", layout="wide")


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


@st.cache_data(show_spinner=False)
def get_rounds():
    return load_rounds_file(ROUNDS_FILE)


@st.cache_data(show_spinner=False)
def get_photo_index():
    return build_photo_index(PHOTOS_FILE)


@st.cache_data(show_spinner=False)
def get_excel_data(file_bytes: bytes | None, uploaded_name: str | None):
    if file_bytes and uploaded_name:
        temp_dir = ROOT_DIR / ".tmp"
        temp_dir.mkdir(exist_ok=True)
        temp_path = temp_dir / uploaded_name
        temp_path.write_bytes(file_bytes)
        return load_excel_data(temp_path)
    return load_excel_data(DEFAULT_EXCEL_FILE)


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
    st.session_state.setdefault("last_position", "Goleiros")
    if "globo_auth" not in st.session_state:
        st.session_state["globo_auth"] = load_globo_auth(get_remote_auth_config())
    st.session_state.setdefault("globo_auth_source", "")
    for position_key in POSITION_CONFIG:
        st.session_state.setdefault(position_storage_key(position_key), [])
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
        st.session_state.setdefault(f"pending_reset_{position_key}", False)
        for profile_name in POSITION_CONFIG[position_key]["profiles"]:
            st.session_state.setdefault(f"profile_{position_key}_{profile_name}", False)


def add_player_to_position(position_name: str, payload: dict):
    items = st.session_state[position_storage_key(position_name)]
    athlete_id = payload.get("athlete_id")
    if athlete_id is not None and any(item.get("athlete_id") == athlete_id for item in items):
        return
    items.append(payload)


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
        "badges": {"unanimidade": False, "bom_capitao": False, "bom_rl": False},
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
        for player in st.session_state[position_storage_key(position_name)]
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
        players = st.session_state.get(position_storage_key(position_name), [])
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


ensure_state()

st.title("Nova Plataforma TCC")
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
    saved_auth = bool(st.session_state.get("globo_auth"))
    gm_token = ""
    globo_id_token = ""
    globo_refresh_token = ""
    if not saved_auth:
        gm_token = st.text_input(
            "Access token do Gato Mestre",
            type="password",
            help="Configuração inicial para carregar o mínimo para valorizar.",
        )
    with st.expander("Renovação automática do token"):
        if saved_auth:
            st.success("Conta Globo conectada. Os tokens serão renovados e salvos automaticamente.")
        else:
            st.caption("Configuração única: cole o conjunto obtido no Response do refresh-token.")
            globo_id_token = st.text_input("ID token", type="password")
            globo_refresh_token = st.text_input("Refresh token", type="password")
        if saved_auth and st.button("Desconectar conta Globo", use_container_width=True):
            delete_globo_auth(get_remote_auth_config())
            st.session_state["globo_auth"] = None
            st.session_state["globo_auth_source"] = ""
            st.rerun()
    if st.button("Atualizar mercado", use_container_width=True, type="primary"):
        with st.spinner("Buscando mercado do Cartola..."):
            active_access_token = gm_token.strip()
            if active_access_token and globo_id_token.strip() and globo_refresh_token.strip():
                source_marker = globo_refresh_token.strip()
                if st.session_state.get("globo_auth_source") != source_marker:
                    st.session_state["globo_auth"] = {
                        "access_token": active_access_token,
                        "id_token": globo_id_token.strip(),
                        "refresh_token": source_marker,
                    }
                    st.session_state["globo_auth_source"] = source_marker
            if st.session_state.get("globo_auth"):
                try:
                    st.session_state["globo_auth"] = refresh_globo_tokens(**st.session_state["globo_auth"])
                    save_globo_auth(st.session_state["globo_auth"], get_remote_auth_config())
                    active_access_token = st.session_state["globo_auth"]["access_token"]
                    st.caption("Token renovado e salvo automaticamente pela Globo.")
                except Exception as exc:
                    st.warning(f"Não foi possível renovar o token; tentando o access token informado. Detalhe: {exc}")
            try:
                st.session_state["market_data"] = fetch_market_snapshot(active_access_token or None)
            except Exception as exc:
                st.session_state["market_data"] = pd.DataFrame()
                st.error(
                    "Não foi possível acessar a API do Cartola. Verifique a conexão com a internet "
                    f"e tente novamente. Detalhe: {exc}"
                )
        if not st.session_state["market_data"].empty:
            st.success(f'{len(st.session_state["market_data"])} atletas carregados.')

datasets = get_excel_data(
    uploaded_excel.getvalue() if uploaded_excel else None,
    uploaded_excel.name if uploaded_excel else None,
)
analyzer = ScoutAnalyzer(datasets["POR_JOGO"], rounds_data, photo_index)
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
    for profile_name in POSITION_CONFIG[position_key]["profiles"]:
        st.session_state[f"profile_{position_key}_{profile_name}"] = False
    st.session_state[f"pending_reset_{position_key}"] = False

tab_quick, tab_editor, tab_preview = st.tabs(["Seleção rápida", "Editor detalhado", "Visualização"])

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
                position_names = set(POSITION_CONFIG[quick_position]["market_positions"])
                quick_df = market_df[market_df["posicao_norm"].isin(position_names)].copy()
                if status_filter:
                    quick_df = quick_df[quick_df["status"].isin(status_filter)]
                selected_ids = {p.get("athlete_id") for p in st.session_state[position_storage_key(quick_position)]}
                quick_df.insert(0, "Indicar", quick_df["atleta_id"].isin(selected_ids))
                edited = st.data_editor(
                    quick_df[["Indicar", "atleta_id", "nome", "time", "status", "preco", "minimo_valorizar"]],
                    hide_index=True,
                    disabled=["atleta_id", "nome", "time", "status", "preco", "minimo_valorizar"],
                    column_config={
                        "Indicar": st.column_config.CheckboxColumn("Indicar"),
                        "atleta_id": None,
                        "nome": "Jogador", "time": "Clube", "status": "Status",
                        "preco": st.column_config.NumberColumn("Preço", format="C$ %.2f"),
                        "minimo_valorizar": st.column_config.NumberColumn("MPV", format="%.2f"),
                    },
                    use_container_width=True,
                    key=f"quick_grid_{quick_position}",
                )
                if st.button("Aplicar seleção", key=f"apply_quick_{quick_position}", type="primary", use_container_width=True):
                    chosen_ids = set(edited.loc[edited["Indicar"], "atleta_id"].tolist())
                    chosen_rows = quick_df[quick_df["atleta_id"].isin(chosen_ids)]
                    current = st.session_state[position_storage_key(quick_position)]
                    visible_ids = set(quick_df["atleta_id"].tolist())
                    current[:] = [p for p in current if p.get("athlete_id") not in visible_ids or p.get("athlete_id") in chosen_ids]
                    for _, row in chosen_rows.iterrows():
                        add_player_to_position(quick_position, market_row_to_player(row.to_dict()))
                    st.success(f"Lista atualizada: {len(current)} indicado(s).")

        st.divider()
        st.subheader("Indicadores dos selecionados")
        st.caption("Edite os indicadores mais usados em lote. Os perfis específicos continuam no editor detalhado.")
        for edit_position in POSITION_CONFIG:
            players = st.session_state[position_storage_key(edit_position)]
            if not players:
                continue
            with st.expander(f"{edit_position} ({len(players)})"):
                profile_options = POSITION_CONFIG[edit_position]["profiles"]
                column_widths = [2.4, 0.8, 0.8, 0.9, 0.8] + [1.0] * len(profile_options)
                header_labels = ["Jogador", "Conf.", "Unân.", "Capitão", "Bom RL"] + [
                    display_profile_label(profile) for profile in profile_options
                ]
                header_columns = st.columns(column_widths)
                for column, label in zip(header_columns, header_labels):
                    column.caption(label)

                pending_indicators: list[dict] = []
                with st.form(f"indicator_form_{edit_position}"):
                    for idx, player in enumerate(players):
                        row_columns = st.columns(column_widths)
                        row_columns[0].markdown(f'**{player["name"]}**  \n{player["team"]}')
                        confidence_value = player.get("confidence", "A")
                        confidence = row_columns[1].selectbox(
                            f"Confiança de {player['name']}",
                            options=["A", "B", "C", "D"],
                            index=["A", "B", "C", "D"].index(confidence_value) if confidence_value in ["A", "B", "C", "D"] else 0,
                            key=f"quick_conf_{edit_position}_{idx}",
                            label_visibility="collapsed",
                        )
                        unanimity = row_columns[2].checkbox(
                            f"Unanimidade - {player['name']}",
                            value=bool(player.get("badges", {}).get("unanimidade", False)),
                            key=f"quick_una_{edit_position}_{idx}",
                            label_visibility="collapsed",
                        )
                        captain = row_columns[3].checkbox(
                            f"Bom capitão - {player['name']}",
                            value=bool(player.get("badges", {}).get("bom_capitao", False)),
                            key=f"quick_cap_{edit_position}_{idx}",
                            label_visibility="collapsed",
                        )
                        good_rl = row_columns[4].checkbox(
                            f"Bom RL - {player['name']}",
                            value=bool(player.get("badges", {}).get("bom_rl", False)),
                            key=f"quick_rl_{edit_position}_{idx}",
                            label_visibility="collapsed",
                        )
                        selected_profiles = []
                        for profile_idx, profile in enumerate(profile_options):
                            if row_columns[5 + profile_idx].checkbox(
                                f"{display_profile_label(profile)} - {player['name']}",
                                value=profile in player.get("profiles", []),
                                key=f"quick_profile_{edit_position}_{idx}_{profile}",
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
                                },
                            }
                        )
                    submitted = st.form_submit_button("Salvar indicadores", use_container_width=True, type="primary")
                if submitted:
                    for player, values in zip(players, pending_indicators):
                        player.update(values)
                    st.success("Confianças, destaques e perfis salvos.")

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
        b1, b2, b3 = st.columns(3)
        badge_unanimity = b1.checkbox("Unanimidade", key=f"una_{position_key}")
        badge_captain = b2.checkbox("Bom Capitão", key=f"cap_{position_key}")
        badge_rl = b3.checkbox("Bom RL", key=f"rl_{position_key}")

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
                        },
                    },
                )
                reset_form(position_key)
                st.rerun()

    st.divider()
    st.subheader("Lista atual")
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
        st.caption("O CSV consolida todas as indicacoes montadas no editor e preserva a ordem manual de cada posicao.")

with tab_preview:
    st.subheader(f"Prévia de {position_key}")
    st.caption("A visualização gera o painel completo da posição. O download recomendado agora é feito pelo servidor para maior confiabilidade.")

    if st.button("Gerar visualização", type="primary", use_container_width=True):
        rendered_cards = build_cards_for_position(analyzer, position_key, target_round, window_n, filter_mode)
        st.session_state["preview_cards"] = rendered_cards
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
                last_error = None
                with st.spinner("Gerando PNG em alta qualidade..."):
                    for scale in [4, 3, 2]:
                        try:
                            png_bytes = export_html_to_png_bytes(export_html, scale=scale)
                            st.session_state["preview_png_bytes"] = png_bytes
                            st.session_state["preview_png_scale"] = scale
                            st.session_state["preview_png_name"] = (
                                f'indicacoes_{preview_context["position_key"].lower()}_rodada_{preview_context["target_round"]}.png'
                            )
                            last_error = None
                            break
                        except Exception as exc:
                            last_error = exc
                    if last_error and not st.session_state.get("preview_png_bytes"):
                        error_text = str(last_error).strip() or repr(last_error)
                        st.error(f"Não consegui gerar o PNG no servidor: {error_text}")
                    elif st.session_state.get("preview_png_bytes"):
                        st.success(f'PNG pronto. Exportação concluída em {st.session_state["preview_png_scale"]}x.')
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
                    generated_pngs: list[bytes] = []
                    included_positions: list[str] = []
                    last_error = None
                    failed_position = None
                    with st.spinner("Gerando PDF consolidado com todas as posições..."):
                        for pos in positions_with_cards:
                            cards = build_cards_for_position(analyzer, pos, target_round, window_n, filter_mode)
                            if not cards:
                                continue
                            html = build_position_preview_html(
                                position_name=pos,
                                target_round=target_round,
                                window_n=window_n,
                                filter_mode=filter_mode,
                                cards=cards,
                            )
                            png_bytes = None
                            for scale in [4, 3, 2]:
                                try:
                                    png_bytes = export_html_to_png_bytes(html, scale=scale)
                                    break
                                except Exception as exc:
                                    last_error = exc
                                    png_bytes = None
                            if not png_bytes:
                                failed_position = pos
                                break
                            generated_pngs.append(png_bytes)
                            included_positions.append(pos)

                        if generated_pngs and not failed_position:
                            try:
                                st.session_state["preview_pdf_bytes"] = combine_pngs_to_pdf_bytes(generated_pngs)
                                st.session_state["preview_pdf_name"] = (
                                    f'indicacoes_completas_rodada_{target_round}.pdf'
                                )
                                st.success(
                                    "PDF pronto com: " + ", ".join(included_positions) + "."
                                )
                            except Exception as exc:
                                error_text = str(exc).strip() or repr(exc)
                                st.error(f"Não consegui montar o PDF final: {error_text}")
                        else:
                            error_text = str(last_error).strip() if last_error else "Falha ao gerar as páginas do PDF."
                            if failed_position:
                                st.error(f"Não consegui gerar o PDF consolidado na posição {failed_position}: {error_text}")
                            else:
                                st.error(f"Não consegui gerar o PDF consolidado: {error_text}")
        if st.button("Gerar pacote com todos os PNGs", use_container_width=True, type="secondary"):
            positions_with_cards = [
                pos for pos in POSITION_CONFIG
                if st.session_state.get(position_storage_key(pos))
            ]
            if not positions_with_cards:
                st.error("Não há jogadores adicionados para gerar o pacote.")
            else:
                png_files: list[tuple[str, bytes]] = []
                failed_position = None
                last_error = None
                with st.spinner("Gerando um PNG por posição e montando o ZIP..."):
                    for pos in positions_with_cards:
                        cards = build_cards_for_position(analyzer, pos, target_round, window_n, filter_mode)
                        html = build_position_preview_html(pos, target_round, window_n, filter_mode, cards)
                        png_bytes = None
                        for scale in [4, 3, 2]:
                            try:
                                png_bytes = export_html_to_png_bytes(html, scale=scale)
                                break
                            except Exception as exc:
                                last_error = exc
                        if not png_bytes:
                            failed_position = pos
                            break
                        png_files.append((f"indicacoes_{pos.lower()}_rodada_{target_round}.png", png_bytes))
                if failed_position:
                    st.error(f"Falha ao gerar {failed_position}: {last_error}")
                else:
                    st.session_state["all_pngs_zip_bytes"] = combine_files_to_zip_bytes(png_files)
                    st.session_state["all_pngs_zip_name"] = f"indicacoes_png_rodada_{target_round}.zip"
                    st.success(f"Pacote pronto com {len(png_files)} PNG(s).")
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
