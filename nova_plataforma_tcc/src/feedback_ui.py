"""Aba "Feedback da rodada" do Streamlit."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from .brand import BRAND
from .utils import position_storage_key
from .exporter import combine_files_to_zip_bytes, combine_pngs_to_pdf_bytes, export_htmls_to_png
from .feedback import (
    POSITION_ORDER,
    build_snapshot,
    enrich_snapshot,
    evaluate_snapshot,
    fetch_market_status,
    fetch_round_results,
    missing_history_rounds,
)
from .feedback_render import build_all_arts
from .indications_import import parse_indications_csv
from .indications_store import (
    archive_latest_round,
    archive_most_escalated,
    load_most_escalated,
    list_saved_rounds,
    load_archive,
    load_results,
    load_snapshot,
    save_results,
    save_snapshot,
)

PROJECT = BRAND.key


def _saved_rounds(remote_config, refresh: bool = False) -> list[int]:
    if refresh or "fb_saved_rounds" not in st.session_state:
        st.session_state["fb_saved_rounds"] = list_saved_rounds(PROJECT, remote_config)
    return st.session_state["fb_saved_rounds"]


def _most_escalated(round_number: int, remote_config) -> dict | None:
    """Mais escalados guardados da rodada; se faltar e o mercado ainda estiver fechado nela, captura agora."""
    try:
        stored = load_most_escalated(round_number, remote_config)
        if stored:
            return stored
        if archive_most_escalated(remote_config) == round_number:
            return load_most_escalated(round_number, remote_config)
    except Exception:
        pass
    return None


def _format_saved_at(snapshot: dict) -> str:
    try:
        return datetime.fromisoformat(snapshot["saved_at"]).astimezone().strftime("%d/%m/%Y %H:%M")
    except (KeyError, ValueError):
        return "data desconhecida"


def _show_evaluation(analyzer, evaluation: dict) -> None:
    """Prévia das artes + downloads (PNG, PDF e ZIP)."""
    demo = bool(evaluation.get("demo"))
    arts = build_all_arts(evaluation, analyzer.get_player_photo)
    s = evaluation["summary"]
    if demo:
        st.warning(
            "MODO EXEMPLO: as indicações atuais foram cruzadas com a pontuação mais recente do Cartola só para você "
            "conferir o visual. Estas artes saem marcadas como exemplo e não podem ser baixadas."
        )
    st.success(
        f"Rodada {evaluation['round']}: {s['played']} de {s['indicated']} indicados jogaram, "
        f"{s['above_average']} acima da média, {len(s['mitou'])} mitaram, "
        f"aproveitamento de {s['check_rate']}% nos critérios. Total de {len(arts)} arte(s)."
    )
    if not evaluation.get("most_escalated"):
        st.info(
            "Os mais escalados desta rodada não foram guardados (só dá para capturar com o mercado fechado). "
            "O resumo sai com minha seleção x seleção da rodada."
        )
    tabs = st.tabs([art["label"] for art in arts])
    for tab, art in zip(tabs, arts):
        with tab:
            st.components.v1.html(art["html"], height=1100, scrolling=True)

    if demo:
        return

    st.markdown("### Baixar as artes (PNG e PDF)")
    st.caption(
        f"{len(arts)} arte(s): o resumo e os painéis por posição. Posições com muitos jogadores são divididas "
        "em mais de uma arte para o texto continuar grande o bastante para ler no celular."
    )
    if st.button("Gerar PNGs e PDF em alta resolução", use_container_width=True, type="primary"):
        with st.spinner("Gerando as imagens e o PDF (pode levar alguns minutos)..."):
            try:
                exports = export_htmls_to_png([art["html"] for art in arts], 3)
                round_number = evaluation["round"]
                files = [
                    (f"feedback_rodada_{round_number}_{index:02d}_{art['slug']}.png", export.png)
                    for index, (art, export) in enumerate(zip(arts, exports), start=1)
                ]
                st.session_state["fb_pngs"] = {
                    "round": round_number,
                    "files": files,
                    "labels": [art["label"] for art in arts],
                    "pdf": combine_pngs_to_pdf_bytes([export.png for export in exports]),
                }
                reduced = [art["label"] for art, e in zip(arts, exports) if e.scale_reduced]
                if reduced:
                    st.info("Escala reduzida automaticamente para não deformar: " + ", ".join(reduced))
                broken = [art["label"] for art, e in zip(arts, exports) if e.broken_images]
                if broken:
                    st.warning("Alguma imagem não carregou em: " + ", ".join(broken) + ". Gere novamente.")
            except Exception as exc:
                st.error(f"Não consegui gerar os arquivos: {exc}")

    pngs = st.session_state.get("fb_pngs")
    if pngs and pngs["round"] == evaluation["round"]:
        first, second = st.columns(2)
        first.download_button(
            "Baixar PDF (todas as artes)",
            data=pngs["pdf"],
            file_name=f"feedback_rodada_{pngs['round']}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
        second.download_button(
            "Baixar PNGs (.zip)",
            data=combine_files_to_zip_bytes(pngs["files"]),
            file_name=f"feedback_rodada_{pngs['round']}_pngs.zip",
            mime="application/zip",
            use_container_width=True,
        )
        columns = st.columns(min(3, len(pngs["files"])))
        for index, ((file_name, data), label) in enumerate(zip(pngs["files"], pngs["labels"])):
            columns[index % len(columns)].download_button(
                f"PNG - {label}",
                data=data,
                file_name=file_name,
                mime="image/png",
                key=f"fb_dl_{file_name}",
                use_container_width=True,
            )


@st.fragment
def render_feedback_tab(analyzer, players_by_position, target_round: int, window_n: int, filter_mode: str, remote_config) -> None:
    st.subheader(f"Feedback da rodada ({'TCC' if BRAND.key == 'tcc' else BRAND.key.title()})")
    st.caption(
        "Depois que a rodada termina, a plataforma cruza as indicações que você fechou com a pontuação real do Cartola "
        "e gera as artes: um resumo com as seleções e painéis de resultado por posição (em PNG e PDF)."
    )

    # arquiva sozinho a pontuação da última rodada finalizada (a API só guarda a mais recente)
    if not st.session_state.get("fb_archived_checked"):
        st.session_state["fb_archived_checked"] = True
        try:
            archived = archive_latest_round(PROJECT, remote_config)
            if archived:
                st.toast(f"Pontuação da rodada {archived} arquivada para o histórico.")
        except Exception:
            pass
        try:
            captured = archive_most_escalated(remote_config)
            if captured:
                st.toast(f"Mais escalados da rodada {captured} guardados.")
        except Exception:
            pass

    with st.expander("Histórico de pontuações (arquivo da API)"):
        archived_rounds = (
            sorted(r for r in range(1, 39) if load_results(PROJECT, r, remote_config))
            if st.session_state.get("fb_show_archive")
            else []
        )
        if st.button("Atualizar/arquivar pontuação e mais escalados agora", use_container_width=True):
            try:
                archived = archive_latest_round(PROJECT, remote_config)
                captured = archive_most_escalated(remote_config)
                if captured:
                    st.success(f"Mais escalados da rodada {captured} guardados (números finais de escalações).")
                if archived:
                    st.success(f"Pontuação da rodada {archived} arquivada.")
                elif not captured:
                    market = fetch_market_status()
                    st.info(
                        "Nada novo para arquivar: a pontuação da rodada só é liberada quando o mercado reabre, e os mais escalados só são guardados com o mercado fechado "
                        f"(situação agora: rodada {market.get('rodada_atual')}, mercado "
                        f"{'aberto' if market.get('status_mercado') == 1 else 'fechado'}), ou ela já está arquivada."
                    )
            except Exception as exc:
                st.error(f"Não consegui consultar o Cartola: {exc}")
        if st.button("Ver rodadas arquivadas", use_container_width=True):
            st.session_state["fb_show_archive"] = True
            st.rerun(scope="fragment")
        if archived_rounds:
            st.write("Rodadas arquivadas: " + ", ".join(map(str, archived_rounds)))
        st.caption(
            "A planilha de scouts cobre as rodadas anteriores; as rodadas novas vêm da API (por número de rodada) e são "
            "arquivadas automaticamente (aqui e pelo robô do GitHub) para completar o histórico das médias."
        )

    # ---- importar indicações de um CSV (ex.: rodada que já passou) ----
    with st.expander("Importar indicações de um arquivo CSV (rodada que já foi montada)"):
        st.caption(
            "Aceita o mesmo CSV do botão 'Baixar CSV das indicações' (colunas posicao, nome, clube, confianca, perfis, "
            "unanimidade, bom_capitao, bom_rl). Substitui as listas atuais. Depois escolha a rodada-alvo na barra lateral "
            "e clique em 'Salvar indicações desta rodada'. Carregue o mercado antes para casar nomes e preços."
        )
        uploaded = st.file_uploader("CSV de indicações", type=["csv"], key="fb_import_csv")
        if uploaded is not None and st.button("Importar para as listas", use_container_width=True):
            try:
                imported, warnings = parse_indications_csv(uploaded.getvalue(), st.session_state.get("market_data"))
                for position_key, items in imported.items():
                    st.session_state[position_storage_key(position_key)][:] = items
                st.session_state["fb_imported"] = True
                st.success("Importado: " + ", ".join(f"{k} {len(v)}" for k, v in imported.items() if v) + ". Reabra a página se as listas não atualizarem.")
                for warning in warnings:
                    st.warning(warning)
                st.rerun()
            except Exception as exc:
                st.error(f"Não consegui importar: {exc}")

    # ---- 1) fechar indicações ----
    st.markdown("### 1. Fechar as indicações da rodada")
    counts = {pos: len(players_by_position.get(pos, [])) for pos in POSITION_ORDER}
    total = sum(counts.values())
    st.write(
        f"Rodada-alvo selecionada: **{target_round}** — {total} indicados ("
        + ", ".join(f"{k} {v}" for k, v in counts.items() if v)
        + ")"
    )
    if st.button("Salvar indicações desta rodada", type="primary", use_container_width=True, disabled=total == 0):
        try:
            previous = load_snapshot(PROJECT, target_round, remote_config)
            sheet_last_round = int(analyzer.df_games["RODADA"].max())
            archive = load_archive(PROJECT, list(range(sheet_last_round + 1, target_round)), remote_config)
            snapshot = build_snapshot(
                analyzer, players_by_position, target_round, window_n, filter_mode, PROJECT, archive
            )
            save_snapshot(snapshot, remote_config)
            _saved_rounds(remote_config, refresh=True)
            gaps = missing_history_rounds(analyzer, archive, target_round)
            message = f"Indicações da rodada {target_round} salvas ({len(snapshot['players'])} jogadores)."
            if previous:
                message += f" O registro anterior ({_format_saved_at(previous)}) foi substituído."
            st.success(message)
            if archive:
                st.caption(f"Histórico completado com a pontuação arquivada das rodadas: {', '.join(map(str, sorted(archive)))}.")
            if gaps:
                st.warning(
                    f"A planilha de scouts vai até a rodada {sheet_last_round} e não há pontuação arquivada das rodadas "
                    f"{', '.join(map(str, gaps))}. As médias de 'boa fase' ficam defasadas: suba a planilha atualizada "
                    "e salve as indicações de novo."
                )
        except Exception as exc:
            st.error(f"Não consegui salvar as indicações: {exc}")

    # ---- 2) resultado ----
    st.divider()
    st.markdown("### 2. Gerar o feedback depois da rodada")
    rounds = _saved_rounds(remote_config)
    chosen_round = None
    if rounds:
        col_round, col_reload = st.columns([3, 1])
        chosen_round = col_round.selectbox("Rodada salva", rounds, format_func=lambda r: f"Rodada {r}")
        if col_reload.button("Recarregar lista", use_container_width=True):
            _saved_rounds(remote_config, refresh=True)
            st.rerun(scope="fragment")

        if st.button("Buscar pontuação no Cartola e gerar feedback", type="primary", use_container_width=True):
            snapshot = load_snapshot(PROJECT, chosen_round, remote_config)
            if not snapshot:
                st.error("Não encontrei o registro desta rodada.")
            else:
                results = None
                with st.spinner("Buscando pontuação no Cartola..."):
                    try:
                        results = fetch_round_results(chosen_round)
                        save_results(PROJECT, results, remote_config)
                        market = fetch_market_status()
                        if market.get("bola_rolando") or (
                            market.get("status_mercado") == 2 and market.get("rodada_atual") == chosen_round
                        ):
                            st.warning("A rodada parece ainda em andamento: os pontos são parciais. Gere de novo quando ela terminar.")
                    except Exception as exc:
                        st.warning(f"Não consegui buscar a pontuação agora ({exc}); tentando o resultado já guardado.")
                        results = load_results(PROJECT, chosen_round, remote_config)
                        if results:
                            st.info("Usando a pontuação desta rodada que já estava guardada.")
                        else:
                            st.error(f"Não encontrei a pontuação da rodada {chosen_round}. Tente de novo em alguns minutos.")
                if results:
                    sheet_last = int(analyzer.df_games["RODADA"].max())
                    archive = load_archive(PROJECT, list(range(sheet_last + 1, snapshot["round"])), remote_config)
                    snapshot = enrich_snapshot(analyzer, snapshot, archive)
                    st.session_state["fb_eval"] = evaluate_snapshot(
                        snapshot, results, _most_escalated(chosen_round, remote_config)
                    )
                    st.session_state["fb_pngs"] = None
    else:
        st.info("Ainda não há rodadas salvas. Feche as indicações acima antes da rodada começar.")

    # ---- exemplo para conferir o visual ----
    with st.expander("Conferir o visual com um exemplo (sem esperar a rodada acabar)"):
        st.caption(
            "Usa as indicações que estão montadas agora e a pontuação mais recente do Cartola, só para você ver como as "
            "artes ficam. A arte sai marcada como EXEMPLO e não pode ser baixada."
        )
        if st.button("Gerar exemplo", use_container_width=True, disabled=total == 0):
            try:
                live = fetch_round_results()
                snapshot = build_snapshot(analyzer, players_by_position, target_round, window_n, filter_mode, PROJECT)
                evaluation = evaluate_snapshot(snapshot, live, _most_escalated(live["round"], remote_config))
                evaluation["demo"] = True
                evaluation["round"] = live["round"]
                st.session_state["fb_eval"] = evaluation
                st.session_state["fb_pngs"] = None
            except Exception as exc:
                st.error(f"Não consegui gerar o exemplo: {exc}")
        if total == 0:
            st.info("Monte algumas indicações primeiro (Seleção rápida) para gerar o exemplo.")

    evaluation = st.session_state.get("fb_eval")
    if evaluation and (evaluation.get("demo") or evaluation["round"] == chosen_round):
        _show_evaluation(analyzer, evaluation)
