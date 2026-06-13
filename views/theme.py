# -*- coding: utf-8 -*-
"""
================================================================================
 views/theme.py  ::  SISTEMA DE DISENIO PREMIUM (Streamlit + CSS inyectado)
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Centraliza el SISTEMA DE DISENIO de la suite: una paleta moderna y sobria que
unifica Sistemas y Nutricion (verde salvia + azul slate, neutros grises de alto
contraste y tipografia grafito) y el CSS premium que convierte la interfaz en un
dashboard limpio y minimalista de nivel profesional.

Solo ESTILO: ninguna funcion matematica, motor de simulacion ni estado de sesion
vive aqui. Los componentes (tarjetas de KPI, expander de V&V) se exponen para que
las tres pestanias compartan estetica sin duplicar CSS.
"""

from __future__ import annotations

import streamlit as st

# =============================================================================
# PALETA MODERNA E INTERDISCIPLINARIA (verde salvia + azul slate + neutros)
# -----------------------------------------------------------------------------
# Fondos limpios de alto contraste, grises suaves para contenedores, verde salvia
# como acento principal (Nutricion / agroecologia), azul slate como acento serio
# (Sistemas) y tipografia grafito #212529 para maxima legibilidad.
# =============================================================================
PALETA = {
    # --- Acento principal: verde salvia elegante ---
    "verde": "#5B8A72",          # Salvia principal (KPIs positivos, botones, tabs activas).
    "verde_hover": "#4C7661",    # Salvia en hover.
    "verde_profundo": "#3C5E4E", # Salvia profundo (gradiente de cabecera, titulos).
    "verde_suave": "#EAF1ED",    # Tinte salvia muy claro (cajas de info, fondos suaves).
    # --- Acento secundario: azul slate sobrio ---
    "slate": "#48637A",          # Slate elegante (acento secundario, datos neutros).
    "slate_profundo": "#37485A", # Slate profundo (gradiente de cabecera).
    "slate_suave": "#F1F3F5",    # Gris azulado suave (contenedores secundarios).
    # --- Acentos calidos y semaforicos (apagados, sofisticados) ---
    "naranja": "#C8895C",        # Terracota suave (acento calido, demografia femenina).
    "ambar": "#B0813F",          # Ambar apagado (advertencias suaves).
    "rojo": "#C25B52",           # Coral apagado (errores, valores criticos).
    # --- Neutros de alto contraste ---
    "card": "#FFFFFF",           # Tarjetas blancas inmaculadas.
    "borde": "#E9ECEF",          # Borde ultrafino y sutil.
    "txt": "#212529",            # Grafito principal (maxima legibilidad).
    "txt_suave": "#6C757D",      # Gris medio para subtitulos y leyendas.
    "bg": "#F8F9FA",             # Fondo limpio de alto contraste.
}


def inyectar_css() -> None:
    """Inyecta el sistema de estilos premium global (cards, tabs, metricas, expanders,
    tablas y botones) con `st.markdown(unsafe_allow_html=True)`."""
    p = PALETA
    st.markdown(
        f"""
        <style>
        /* ===== Lienzo general ===== */
        .stApp {{ background-color: {p['bg']}; }}
        .block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; }}
        html, body, [class*="css"] {{ color: {p['txt']}; }}

        /* ===== Cabecera / bloque de titulo ===== */
        .bloque-titulo {{
            background: linear-gradient(100deg, {p['verde_profundo']} 0%, {p['slate_profundo']} 100%);
            padding: 22px 28px; border-radius: 16px; color: #FFFFFF;
            margin-bottom: 14px; box-shadow: 0 4px 14px rgba(33,37,41,0.10);
        }}
        .bloque-titulo h1 {{ color:#FFFFFF; font-size: 1.6rem; margin: 0; font-weight: 700;
            letter-spacing: 0.2px; }}
        .bloque-titulo p {{ color:#E7EDEA; margin: 6px 0 0 0; font-size: 0.95rem; }}

        /* ===== Tarjetas de KPI (HTML propio) ===== */
        .kpi-card {{
            background: {p['card']}; border: 1px solid {p['borde']};
            border-radius: 12px; padding: 18px 20px; height: 100%;
            box-shadow: 0 4px 6px rgba(0,0,0,0.03);
            transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
        }}
        .kpi-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 12px 22px rgba(33,37,41,0.07);
            border-color: #D7DEE3;
        }}
        .kpi-head {{ font-size: 0.80rem; color: {p['txt_suave']}; font-weight: 600;
            text-transform: uppercase; letter-spacing: 0.4px; }}
        .kpi-val  {{ font-size: 1.9rem; font-weight: 800; line-height: 1.1; margin-top: 6px; }}
        .kpi-sub  {{ font-size: 0.78rem; color: {p['txt_suave']}; margin-top: 4px; }}

        /* ===== st.metric estilizado como tarjeta ===== */
        [data-testid="stMetric"] {{
            background: {p['card']}; border: 1px solid {p['borde']};
            border-radius: 12px; padding: 14px 18px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.03);
            transition: transform .18s ease, box-shadow .18s ease;
        }}
        [data-testid="stMetric"]:hover {{
            transform: translateY(-2px); box-shadow: 0 12px 22px rgba(33,37,41,0.07);
        }}
        [data-testid="stMetricLabel"] p {{ color: {p['txt_suave']}; font-weight: 600; }}

        /* ===== Contenedores con borde (st.container(border=True)) como cards ===== */
        [data-testid="stVerticalBlockBorderWrapper"] {{
            border-radius: 14px; border: 1px solid {p['borde']} !important;
            box-shadow: 0 4px 6px rgba(0,0,0,0.03); background: {p['card']};
        }}

        /* ===== Pestanias ===== */
        .stTabs [data-baseweb="tab-list"] {{ gap: 8px; border-bottom: 1px solid {p['borde']}; }}
        .stTabs [data-baseweb="tab"] {{
            background: {p['slate_suave']}; border-radius: 10px 10px 0 0;
            padding: 11px 20px; font-weight: 600; color: {p['txt_suave']};
        }}
        .stTabs [aria-selected="true"] {{
            background: {p['verde']}; color: #FFFFFF !important;
        }}

        /* ===== Botones ===== */
        div.stButton > button {{
            border-radius: 10px; border: 1px solid {p['borde']};
            font-weight: 600; transition: all .18s ease;
        }}
        div.stButton > button:hover {{
            border-color: {p['verde']}; color: {p['verde']};
            box-shadow: 0 4px 10px rgba(91,138,114,0.15);
        }}
        div.stButton > button[kind="primary"] {{
            background: {p['verde']}; border: none; color: #FFFFFF; font-weight: 700;
        }}
        div.stButton > button[kind="primary"]:hover {{
            background: {p['verde_hover']}; color: #FFFFFF;
        }}

        /* ===== Expander (incl. bloque de Validacion V&V) ===== */
        [data-testid="stExpander"] {{
            border: 1px solid {p['borde']}; border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.03); overflow: hidden;
            background: {p['card']};
        }}
        [data-testid="stExpander"] summary {{ font-weight: 600; color: {p['txt']}; }}
        [data-testid="stExpander"] summary:hover {{ color: {p['verde']}; }}

        /* ===== Tablas markdown refinadas ===== */
        [data-testid="stMarkdownContainer"] table {{
            border-collapse: collapse; width: 100%; border: 1px solid {p['borde']};
            border-radius: 10px; overflow: hidden; font-size: 0.88rem;
        }}
        [data-testid="stMarkdownContainer"] thead th {{
            background: {p['slate_suave']}; color: {p['txt']}; font-weight: 600;
            text-align: left; padding: 9px 13px; border-bottom: 1px solid {p['borde']};
        }}
        [data-testid="stMarkdownContainer"] tbody td {{
            padding: 8px 13px; border-top: 1px solid {p['borde']}; color: {p['txt']};
        }}
        [data-testid="stMarkdownContainer"] tbody tr:nth-child(even) {{
            background: {p['bg']};
        }}

        /* ===== DataFrame / Table nativas ===== */
        [data-testid="stDataFrame"], [data-testid="stTable"] {{
            border: 1px solid {p['borde']}; border-radius: 12px; overflow: hidden;
        }}

        /* ===== Alertas (info / success / warning) mas suaves ===== */
        [data-testid="stAlert"] {{ border-radius: 12px; border: 1px solid {p['borde']}; }}

        /* ===== Sliders y selects: acento salvia ===== */
        [data-testid="stSlider"] [role="slider"] {{ border-color: {p['verde']}; }}

        /* ===== Separador elegante ===== */
        hr {{ border: none; border-top: 1px solid {p['borde']}; margin: 1.1rem 0; }}

        /* ===== Subtitulos de seccion ===== */
        .sub-seccion {{
            font-size: 0.95rem; font-weight: 700; color: {p['txt']};
            margin: 6px 0 2px 0; padding-left: 10px;
            border-left: 3px solid {p['verde']};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def sub_seccion(titulo: str) -> None:
    """Encabezado de sub-seccion con barra de acento salvia (look minimalista)."""
    st.markdown(f"<div class='sub-seccion'>{titulo}</div>", unsafe_allow_html=True)


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
            f"border-radius:10px;padding:12px 16px;font-size:0.86rem;color:{PALETA['txt']};"
            f"margin-top:10px;'>"
            f"<b>Veredicto:</b> {validacion.mensaje}</div>",
            unsafe_allow_html=True)
        st.caption(
            "En una distribución Exponencial la media y el desvío estándar coinciden "
            "teóricamente; su cercanía es una verificación adicional del generador.")
