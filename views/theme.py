# -*- coding: utf-8 -*-
"""
================================================================================
 views/theme.py  ::  PALETA Y COMPONENTES VISUALES COMPARTIDOS (Streamlit)
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Centraliza la paleta verde/naranja acordada y los pequenios componentes de UI
reutilizables (tarjetas de KPI premium) para que ambas pestanias compartan estetica
sin duplicar CSS.
"""

from __future__ import annotations

import streamlit as st

# ---- Paleta premium interdisciplinaria ----
PALETA = {
    "verde": "#2E7D32",
    "verde_hover": "#256628",
    "verde_profundo": "#1B5E20",
    "verde_suave": "#EAF3E2",
    "naranja": "#E67E22",
    "ambar": "#B9770E",
    "rojo": "#C0392B",
    "card": "#FFFFFF",
    "borde": "#E0E6D7",
    "txt": "#23311C",
    "txt_suave": "#5B6A4C",
    "bg": "#F7FAF4",
}


def inyectar_css() -> None:
    """Inyecta el CSS premium global (tarjetas, tabs y botones estilizados)."""
    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: {PALETA['bg']}; }}
        .bloque-titulo {{
            background: linear-gradient(95deg, {PALETA['verde']} 0%, {PALETA['verde_profundo']} 100%);
            padding: 18px 26px; border-radius: 16px; color: #FFFFFF;
            margin-bottom: 8px;
        }}
        .bloque-titulo h1 {{ color:#FFFFFF; font-size: 1.65rem; margin: 0; }}
        .bloque-titulo p {{ color:#E7F1DF; margin: 4px 0 0 0; font-size: 0.95rem; }}
        /* Tarjetas de KPI */
        .kpi-card {{
            background: {PALETA['card']}; border: 1px solid {PALETA['borde']};
            border-radius: 16px; padding: 16px 18px; height: 100%;
            box-shadow: 0 1px 3px rgba(35,49,28,0.06);
        }}
        .kpi-head {{ font-size: 0.82rem; color: {PALETA['txt_suave']}; font-weight: 600; }}
        .kpi-val  {{ font-size: 1.9rem; font-weight: 800; line-height: 1.1; margin-top: 4px; }}
        .kpi-sub  {{ font-size: 0.78rem; color: {PALETA['txt_suave']}; margin-top: 2px; }}
        /* Pestanias */
        .stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
        .stTabs [data-baseweb="tab"] {{
            background: {PALETA['verde_suave']}; border-radius: 10px 10px 0 0;
            padding: 10px 18px; font-weight: 600;
        }}
        .stTabs [aria-selected="true"] {{
            background: {PALETA['verde']}; color: #FFFFFF;
        }}
        div.stButton > button[kind="primary"] {{
            background: {PALETA['verde']}; border: none; font-weight: 700;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def tarjeta_kpi(col, titulo: str, valor: str, sub: str = "", color: str | None = None,
                icono: str = "") -> None:
    """Renderiza una tarjeta de KPI premium dentro de la columna `col`."""
    color = color or PALETA["verde"]
    cabecera = f"{icono}&nbsp;&nbsp;{titulo}" if icono else titulo
    sub_html = f"<div class='kpi-sub'>{sub}</div>" if sub else ""
    col.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-head">{cabecera}</div>
            <div class="kpi-val" style="color:{color};">{valor}</div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def bloque_validacion(validacion, titulo_evento: str = "los comensales") -> None:
    """Expander de Validacion y Verificacion (V&V) del generador de arribos (req. 5).

    Recibe un `ValidacionArribos` (sim.estadistica) y contrasta, en tiempo real, el
    tiempo medio entre arribos EMPIRICO (medido sobre la simulacion) contra el TEORICO
    esperado de la Exponencial, certificando que los generadores estan calibrados.
    """
    u = validacion.unidad
    with st.expander("🔬 Validación y Verificación (V&V) del modelo", expanded=False):
        st.markdown(
            "**Contraste del generador de arribos.** Se compara el *Tiempo Medio "
            "Entre Arribos* que NumPy/SimPy generaron durante la simulación contra el "
            "valor teórico esperado de la distribución Exponencial:")
        st.latex(r"E(X) = \frac{\text{Ventana de arribos}}{\text{Cantidad de comensales}}")

        color = PALETA["verde"] if validacion.validado else PALETA["rojo"]
        signo = "+" if validacion.desvio_pct >= 0 else ""
        tabla = (
            "| Métrica | Valor |\n"
            "|---|---|\n"
            f"| Tiempo medio entre arribos **teórico** E(X) | {validacion.media_teorica:.3f} {u} |\n"
            f"| Tiempo medio entre arribos **empírico** (medido) | {validacion.media_empirica:.3f} {u} |\n"
            f"| Desvío porcentual (empírico vs teórico) | {signo}{validacion.desvio_pct:.2f} % |\n"
            f"| Desvío estándar empírico (≈ media en una Exp.) | {validacion.desvio_empirico:.3f} {u} |\n"
            f"| Muestras de interarribos observadas | {validacion.n_muestras} |\n")
        st.markdown(tabla)

        st.markdown(
            f"<div style='background:{PALETA['verde_suave']};border-left:6px solid {color};"
            f"border-radius:8px;padding:10px 14px;font-size:0.86rem;color:{PALETA['txt']};'>"
            f"<b>Veredicto:</b> {validacion.mensaje}</div>",
            unsafe_allow_html=True)
        st.caption(
            "En una distribución Exponencial la media y el desvío estándar coinciden "
            "teóricamente; su cercanía es una verificación adicional del generador.")
