"""Legenda pronta para o Telegram: balanço da rodada em poucas linhas, com emojis.

Usa a marcação que o Telegram entende ao colar na caixa de mensagem: **negrito** e __itálico__.
"""
from __future__ import annotations

from .brand import BRAND
from .feedback import GOOD_SCORE


def _n(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{decimals}f}".replace(".", ",")


def _nome(player: dict) -> str:
    return str(player["name"]).strip()


def _lista(names: list[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " e " + names[-1]


def _clima(rate: int) -> tuple[str, str]:
    if rate >= 65:
        return "🔥", "rodada de ouro"
    if rate >= 50:
        return "👏", "rodada boa"
    if rate >= 35:
        return "⚖️", "rodada de altos e baixos"
    return "🌧️", "rodada dura"


def build_caption(evaluation: dict) -> str:
    summary = evaluation["summary"]
    round_number = evaluation["round"]
    mine = (evaluation.get("my_team") or {}).get("default") or {}
    best_team = (evaluation.get("my_team") or {}).get("best") or {}
    escalated = evaluation.get("most_escalated")
    cartola = evaluation.get("cartola_team") or {}
    players = evaluation["players"]
    played = summary["played"]
    good = summary["above_average"]
    mitou = summary["mitou"]
    rate = summary["check_rate"]
    emoji, clima = _clima(rate)

    lines: list[str] = []
    lines.append(f"📊 **BALANÇO DA RODADA {round_number}** {emoji}")
    lines.append(f"__Como foram as minhas indicações — {clima}!__")
    lines.append("")

    # ---- rendimento ----
    lines.append("✅ **Rendimento das indicações**")
    lines.append(f"• {played} dos {summary['indicated']} indicados entraram em campo")
    lines.append(f"• **{good} de {played}** tiveram boa pontuação pelo critério de cada posição")
    if mitou:
        extra = f" (+{len(mitou) - 4})" if len(mitou) > 4 else ""
        lines.append(f"• 🚀 Mitaram (+10 pts): **{_lista([_nome(p) for p in mitou[:4]])}**{extra}")
    lines.append(f"• Aproveitamento nos critérios que marquei: **{rate}%**")
    lines.append("")

    # ---- placar ----
    if mine:
        lines.append("🏟️ **Placar das seleções**")
        cap_txt = ""
        if mine.get("captain_id") is not None:
            cap = next((p for p in mine["players"] if p["athlete_id"] == mine["captain_id"]), None)
            if cap:
                cap_txt = f" (capitão {_nome(cap)} já incluso 👑)"
        lines.append(f"• Minha seleção — os melhores entre os meus indicados ({mine['formation']}): **{_n(mine['total'])} pts**{cap_txt}")
        if escalated:
            lines.append(f"• Mais escalados: **{_n(escalated['total'])} pts**")
        lines.append(f"• Seleção da rodada do Cartola: **{_n(cartola.get('total'))} pts**")
        if escalated:
            diff = mine["total"] - escalated["total"]
            if diff >= 0:
                lines.append(f"👉 As indicações **venceram os mais escalados** por {_n(diff)} pts! 💪")
            else:
                lines.append(f"👉 Os mais escalados levaram essa por {_n(-diff)} pts — faz parte do jogo. 🤝")
        gap = (cartola.get("total") or 0) - mine["total"]
        if gap > 0:
            lines.append(f"👉 Para a seleção perfeita da rodada faltaram {_n(gap)} pts.")
        if best_team and best_team.get("formation") != mine.get("formation") and best_team["total"] > mine["total"]:
            lines.append(f"🧠 Com os mesmos indicados, o **{best_team['formation']}** renderia {_n(best_team['total'] - mine['total'])} pts a mais.")
        lines.append("")

    # ---- unanimidades ----
    una = [p for p in players if p.get("badges", {}).get("unanimidade")]
    una_played = [p for p in una if p["played"]]
    if una:
        ok = sum(1 for p in una_played if any(c["key"] == "unanimidade" and c["status"] == "ok" for c in p["checks"]))
        destaque = max(una_played, key=lambda p: p["points"], default=None)
        lines.append(f"⭐ **Unanimidades:** {ok} de {len(una_played)} corresponderam"
                     + (f" — destaque para **{_nome(destaque)}** ({_n(destaque['points'])} pts)" if destaque and destaque["points"] > 0 else ""))
        lines.append("")

    # ---- na seleção do Cartola ----
    in_team = [p for p in players if p.get("in_cartola_team")]
    if in_team:
        lines.append(f"🏅 **{len(in_team)} indicados entraram na seleção da rodada:** {_lista([_nome(p) for p in in_team])}")
        lines.append("")

    # ---- reservas mais escalados ----
    reserves = [x for x in (evaluation.get("reserves") or []) if x["played"]][:4]
    if reserves:
        lines.append("🪑 **Reservas mais escalados:** " + " · ".join(f"{_nome(x)} {_n(x['points'])}" for x in reserves))
        lines.append("")

    # ---- destaques ----
    best = summary["best"][:3]
    worst = summary["worst"][:2]
    if best:
        lines.append("🔝 **Melhores indicações:** " + " · ".join(f"{_nome(p)} {_n(p['points'])}" for p in best))
    if worst:
        lines.append("📉 **Não foi dessa vez:** " + " · ".join(f"{_nome(p)} {_n(p['points'])}" for p in worst))
    lines.append("")

    # ---- como ler ----
    lines.append("📖 **Como ler as artes**")
    lines.append("✅ confirmou · ❌ não confirmou · ≈ só referência (médias)")
    gs, za, la, ma, te = GOOD_SCORE["Goleiros"], GOOD_SCORE["Zagueiros"], GOOD_SCORE["Laterais"], GOOD_SCORE["Meias"], GOOD_SCORE["Técnicos"]
    lines.append(
        f"__Boa pontuação:__ goleiro e zagueiro {_n(gs[0], 0)} pts ({_n(gs[1], 0)} sem SG) · lateral {_n(la[0], 0)} pts ({_n(la[1])} sem SG) · "
        f"meia e atacante {_n(ma[0], 0)} pts · técnico {_n(te[0], 0)} pts"
    )
    lines.append("")
    tag = "#VIPGuardiola" if BRAND.key == "guardiola" else "#TCC #TreinandoCampeõesDeCartola"
    lines.append(f"Resultado completo nas artes acima 👆  {tag}")
    return "\n".join(lines).strip()
