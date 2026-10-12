"""Identidade de cada plataforma. Todo o resto do código é compartilhado."""
from __future__ import annotations

import os
from dataclasses import dataclass

from .brand_setting import BRAND_KEY


@dataclass(frozen=True)
class Brand:
    key: str                 # usado para separar os registros no Supabase
    title: str
    logo_file: str
    logo_white_file: str
    has_md3: bool            # edição MD3 (listas e resumo do MD3)
    has_fora_dos_20: bool    # selo "Fora dos 20+" (exclusivo do Guardiola)
    card_layout: str         # "tcc" ou "guardiola"
    summary_theme: str       # tema do resumo por posição
    # cores das artes de feedback
    art_bg: str              # fundo da arte (css)
    art_card: str            # fundo dos cards/caixas
    art_text: str            # cor do texto sobre o fundo da arte
    art_accent: str          # destaque (bordas, selos)
    hero_note: str = ""


BRANDS = {
    "tcc": Brand(
        key="tcc",
        title="Central de Dicas TCC + MD3",
        logo_file="logo_tcc.png",
        logo_white_file="logo_tcc_branco.png",
        has_md3=True,
        has_fora_dos_20=False,
        card_layout="tcc",
        summary_theme="tcc",
        art_bg="image",
        art_card="#0f5d00",
        art_text="#0f5d00",
        art_accent="#ffc61e",
    ),
    "guardiola": Brand(
        key="guardiola",
        title="Plataforma Guardiola",
        logo_file="logo_guardiola.png",
        logo_white_file="logo_guardiola.png",
        has_md3=False,
        has_fora_dos_20=True,
        card_layout="guardiola",
        summary_theme="guardiola",
        art_bg="#f2e1bd",
        art_card="#000000",
        art_text="#000000",
        art_accent="#D4AF37",
        hero_note="Exclusivo · VIP Guardiola",
    ),
}

BRAND = BRANDS[os.environ.get("PLATFORM_BRAND", BRAND_KEY).strip().lower()]
