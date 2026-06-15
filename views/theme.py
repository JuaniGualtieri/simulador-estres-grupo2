# -*- coding: utf-8 -*-
"""
================================================================================
 views/theme.py  ::  SISTEMA DE DISENIO PREMIUM (Streamlit + CSS inyectado)
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Centraliza el SISTEMA DE DISENIO de la suite: una paleta moderna y sobria que
unifica Sistemas y Nutricion (verde salvia + azul slate, neutros grises de alto
contraste y tipografia grafito) y el CSS premium que convierte la interfaz en un
dashboard limpio, animado y de nivel profesional (tipografia Inter, micro-
interacciones, tarjetas con relieve y transiciones suaves).

Solo ESTILO: ninguna funcion matematica, motor de simulacion ni estado de sesion
vive aqui. Los componentes (tarjetas de KPI, sub-secciones, expander de V&V) se
exponen para que las tres pestanias compartan estetica sin duplicar CSS.

NOTA TECNICA: la paleta se publica como VARIABLES CSS en :root (un unico f-string
pequenio) y el resto del CSS es texto plano que las consume con var(--token). Asi
se evita duplicar llaves dentro de un f-string gigante y el codigo queda legible.
"""

from __future__ import annotations

import streamlit as st

# =============================================================================
# PALETA MODERNA E INTERDISCIPLINARIA (verde salvia + azul slate + neutros)
# -----------------------------------------------------------------------------
# Fondos limpios de alto contraste, grises suaves para contenedores, verde salvia
# como acento principal (Nutricion / agroecologia), azul slate como acento serio
# (Sistemas) y tipografia grafito #212529 para maxima legibilidad. Las claves se
# mantienen estables porque las consumen las vistas, los graficos y el reporte PDF.
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
    "bg": "#F6F8F7",             # Fondo limpio con un matiz salvia casi imperceptible.
}

# URL de la familia tipografica (Inter): se importa al inicio del <style>.
_FONT_IMPORT = ("@import url('https://fonts.googleapis.com/css2?"
                "family=Inter:wght@400;500;600;700;800;900&display=swap');")


def _root_vars() -> str:
    """Publica la paleta y los tokens de diseno como variables CSS en :root."""
    p = PALETA
    return f"""
    :root {{
        --verde: {p['verde']};
        --verde-hover: {p['verde_hover']};
        --verde-profundo: {p['verde_profundo']};
        --verde-suave: {p['verde_suave']};
        --slate: {p['slate']};
        --slate-profundo: {p['slate_profundo']};
        --slate-suave: {p['slate_suave']};
        --naranja: {p['naranja']};
        --ambar: {p['ambar']};
        --rojo: {p['rojo']};
        --card: {p['card']};
        --borde: {p['borde']};
        --txt: {p['txt']};
        --txt-suave: {p['txt_suave']};
        --bg: {p['bg']};
        /* Tokens compuestos */
        --radius: 16px;
        --radius-sm: 11px;
        --radius-xs: 8px;
        --ring: 0 0 0 3px rgba(91,138,114,0.16);
        --shadow-sm: 0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06);
        --shadow-md: 0 2px 6px rgba(16,24,40,0.05), 0 12px 28px -14px rgba(16,24,40,0.18);
        --shadow-lg: 0 8px 18px rgba(16,24,40,0.08), 0 28px 56px -24px rgba(16,24,40,0.28);
        --grad-header: linear-gradient(120deg, #3C5E4E 0%, #45637A 58%, #37485A 100%);
        --grad-verde: linear-gradient(135deg, #6A9A82 0%, #5B8A72 55%, #4C7661 100%);
        --font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }}
    """


# CSS principal (texto plano: consume las variables de :root con var(--token)).
_CSS = """
/* ===== Tipografia global ===== */
html, body, [class*="css"], .stApp, button, input, textarea, select {
    font-family: var(--font);
}
.stApp {
    background:
        radial-gradient(1200px 520px at 88% -8%, rgba(91,138,114,0.07), transparent 60%),
        radial-gradient(1000px 480px at -6% 4%, rgba(72,99,122,0.06), transparent 55%),
        var(--bg);
    color: var(--txt);
}
.block-container { padding-top: 2.0rem; padding-bottom: 3.2rem; max-width: 1500px; }
::selection { background: rgba(91,138,114,0.22); }

/* ===== Animaciones ===== */
@keyframes g2FadeUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }
@keyframes g2Fade   { from { opacity: 0; } to { opacity: 1; } }
@keyframes g2Pop    { from { opacity: 0; transform: translateY(8px) scale(.985); } to { opacity: 1; transform: none; } }
@keyframes g2Sheen  { 0% { background-position: 0% 50%; } 100% { background-position: 140% 50%; } }

/* ===== Cabecera / bloque de titulo ===== */
.bloque-titulo {
    position: relative; overflow: hidden;
    background: var(--grad-header);
    padding: 26px 30px; border-radius: var(--radius); color: #FFFFFF;
    margin-bottom: 18px; box-shadow: var(--shadow-md);
    animation: g2FadeUp .55s cubic-bezier(.22,1,.36,1) both;
    border: 1px solid rgba(255,255,255,0.10);
}
.bloque-titulo::before {
    content: ""; position: absolute; inset: 0;
    background: linear-gradient(115deg, transparent 30%, rgba(255,255,255,0.10) 48%, transparent 66%);
    background-size: 240% 100%; animation: g2Sheen 7s ease-in-out infinite alternate;
    pointer-events: none;
}
.bloque-titulo::after {
    content: ""; position: absolute; right: -60px; top: -60px; width: 220px; height: 220px;
    background: radial-gradient(circle, rgba(255,255,255,0.16), transparent 68%);
    pointer-events: none;
}
.bloque-titulo h1 {
    color: #FFFFFF; font-size: 1.7rem; margin: 0; font-weight: 800;
    letter-spacing: -0.3px; position: relative; z-index: 1;
}
.bloque-titulo p {
    color: #E8EFEB; margin: 8px 0 0 0; font-size: 0.95rem; line-height: 1.5;
    position: relative; z-index: 1; max-width: 980px;
}

/* ===== Tarjetas de KPI (HTML propio) ===== */
.kpi-card {
    --accent: var(--verde);
    position: relative; background: var(--card); border: 1px solid var(--borde);
    border-radius: var(--radius-sm); padding: 17px 19px 16px; height: 100%;
    box-shadow: var(--shadow-sm); overflow: hidden;
    transition: transform .22s cubic-bezier(.22,1,.36,1), box-shadow .22s ease, border-color .22s ease;
    animation: g2Pop .5s cubic-bezier(.22,1,.36,1) both;
}
.kpi-card::before {
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
    background: var(--accent); opacity: .9;
    transform: scaleY(.45); transform-origin: top; transition: transform .25s ease;
}
.kpi-card:hover {
    transform: translateY(-4px);
    box-shadow: var(--shadow-lg);
    border-color: #D7DEE3;
}
.kpi-card:hover::before { transform: scaleY(1); }
.kpi-top { display: flex; align-items: center; gap: 9px; margin-bottom: 9px; }
.kpi-icon {
    flex: 0 0 auto; width: 30px; height: 30px; border-radius: 9px;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 0.92rem; color: var(--accent);
    background: color-mix(in srgb, var(--accent) 14%, white);
    border: 1px solid color-mix(in srgb, var(--accent) 22%, white);
}
.kpi-head {
    font-size: 0.74rem; color: var(--txt-suave); font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.5px; line-height: 1.2;
}
.kpi-help {
    position: absolute; top: 12px; right: 13px;
    width: 18px; height: 18px; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 800; cursor: help;
    color: var(--txt-suave); background: var(--slate-suave);
    border: 1px solid var(--borde); transition: all .18s ease;
}
.kpi-help:hover { color: #fff; background: var(--verde); border-color: var(--verde); }
.kpi-val {
    font-size: 1.95rem; font-weight: 800; line-height: 1.12; margin-top: 2px;
    letter-spacing: -0.5px; font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: 0.78rem; color: var(--txt-suave); margin-top: 5px; line-height: 1.35; }

/* ===== st.metric estilizado como tarjeta ===== */
[data-testid="stMetric"] {
    background: var(--card); border: 1px solid var(--borde);
    border-radius: var(--radius-sm); padding: 14px 18px;
    box-shadow: var(--shadow-sm);
    transition: transform .2s ease, box-shadow .2s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px); box-shadow: var(--shadow-md);
}
[data-testid="stMetricLabel"] p { color: var(--txt-suave); font-weight: 600; }

/* ===== Contenedores con borde (st.container(border=True)) como cards ===== */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: var(--radius); border: 1px solid var(--borde) !important;
    box-shadow: var(--shadow-sm); background: var(--card);
}

/* ===== Pestanias ===== */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px; border-bottom: 1px solid var(--borde); padding-bottom: 2px;
}
.stTabs [data-baseweb="tab"] {
    background: var(--slate-suave); border-radius: 12px 12px 0 0;
    padding: 12px 22px; font-weight: 700; color: var(--txt-suave);
    border: 1px solid transparent; border-bottom: none;
    transition: background .2s ease, color .2s ease, transform .2s ease;
}
.stTabs [data-baseweb="tab"]:hover {
    background: #E9EEF1; color: var(--verde-profundo); transform: translateY(-1px);
}
.stTabs [aria-selected="true"] {
    background: var(--grad-verde); color: #FFFFFF !important;
    box-shadow: 0 6px 16px -8px rgba(76,118,97,0.7);
}
.stTabs [aria-selected="true"]:hover { color: #FFFFFF !important; }
.stTabs [data-baseweb="tab-highlight"] { background: transparent; }
.stTabs [data-baseweb="tab-panel"] { animation: g2Fade .45s ease both; padding-top: 6px; }

/* ===== Botones ===== */
div.stButton > button, div.stDownloadButton > button {
    border-radius: var(--radius-xs); border: 1px solid var(--borde);
    font-weight: 700; transition: all .2s cubic-bezier(.22,1,.36,1);
    background: var(--card); color: var(--txt);
}
div.stButton > button:hover, div.stDownloadButton > button:hover {
    border-color: var(--verde); color: var(--verde-profundo);
    transform: translateY(-1px);
    box-shadow: 0 6px 16px -8px rgba(91,138,114,0.55);
}
div.stButton > button:active, div.stDownloadButton > button:active { transform: translateY(0); }
div.stButton > button[kind="primary"], div.stDownloadButton > button[kind="primary"] {
    background: var(--grad-verde); border: none; color: #FFFFFF; font-weight: 800;
    box-shadow: 0 8px 20px -10px rgba(76,118,97,0.85);
}
div.stButton > button[kind="primary"]:hover, div.stDownloadButton > button[kind="primary"]:hover {
    filter: brightness(1.05); color: #FFFFFF; transform: translateY(-2px);
    box-shadow: 0 12px 26px -10px rgba(76,118,97,0.95);
}
button:focus-visible { outline: none !important; box-shadow: var(--ring) !important; }

/* ===== Expander (incl. bloque de Validacion V&V) ===== */
[data-testid="stExpander"] {
    border: 1px solid var(--borde); border-radius: var(--radius-sm);
    box-shadow: var(--shadow-sm); overflow: hidden; background: var(--card);
    transition: box-shadow .2s ease;
}
[data-testid="stExpander"]:hover { box-shadow: var(--shadow-md); }
[data-testid="stExpander"] summary { font-weight: 700; color: var(--txt); }
[data-testid="stExpander"] summary:hover { color: var(--verde); }

/* ===== Tablas markdown refinadas ===== */
[data-testid="stMarkdownContainer"] table {
    border-collapse: separate; border-spacing: 0; width: 100%;
    border: 1px solid var(--borde); border-radius: var(--radius-sm);
    overflow: hidden; font-size: 0.88rem; box-shadow: var(--shadow-sm);
}
[data-testid="stMarkdownContainer"] thead th {
    background: var(--slate-suave); color: var(--txt); font-weight: 700;
    text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--borde);
}
[data-testid="stMarkdownContainer"] tbody td {
    padding: 9px 14px; border-top: 1px solid var(--borde); color: var(--txt);
}
[data-testid="stMarkdownContainer"] tbody tr { transition: background .15s ease; }
[data-testid="stMarkdownContainer"] tbody tr:nth-child(even) { background: var(--bg); }
[data-testid="stMarkdownContainer"] tbody tr:hover { background: var(--verde-suave); }

/* ===== DataFrame / Table nativas ===== */
[data-testid="stDataFrame"], [data-testid="stTable"] {
    border: 1px solid var(--borde); border-radius: var(--radius-sm); overflow: hidden;
}

/* ===== Bloques de codigo (diagnosticos) ===== */
[data-testid="stCode"], pre {
    border-radius: var(--radius-sm) !important; border: 1px solid var(--borde);
    box-shadow: var(--shadow-sm);
}
code { font-feature-settings: "liga" 0; }

/* ===== Alertas (info / success / warning) mas suaves ===== */
[data-testid="stAlert"] {
    border-radius: var(--radius-sm); border: 1px solid var(--borde);
    box-shadow: var(--shadow-sm); animation: g2Fade .4s ease both;
}

/* ===== Sliders y selects: acento salvia ===== */
[data-testid="stSlider"] [role="slider"] {
    border-color: var(--verde); box-shadow: 0 0 0 3px rgba(91,138,114,0.14);
}
[data-testid="stSlider"] [data-baseweb="slider"] div[style*="background"] { }

/* ===== Inputs numericos / selects ===== */
[data-testid="stNumberInput"] input, [data-baseweb="input"] input {
    border-radius: var(--radius-xs);
}
[data-baseweb="input"]:focus-within, [data-testid="stNumberInput"] div:focus-within {
    box-shadow: var(--ring);
}

/* ===== Graficos Plotly: relieve y encuadre ===== */
[data-testid="stPlotlyChart"] {
    background: var(--card); border: 1px solid var(--borde);
    border-radius: var(--radius); padding: 8px 10px 4px;
    box-shadow: var(--shadow-sm); animation: g2Pop .5s cubic-bezier(.22,1,.36,1) both;
    transition: box-shadow .25s ease, transform .25s ease;
}
[data-testid="stPlotlyChart"]:hover { box-shadow: var(--shadow-md); }

/* ===== Barra de progreso y spinner ===== */
[data-testid="stProgress"] [role="progressbar"] > div { background: var(--grad-verde); }
[data-testid="stSpinner"] svg { color: var(--verde); }

/* ===== Barra lateral ===== */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FFFFFF 0%, #FBFCFB 100%);
    border-right: 1px solid var(--borde);
}
[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }

/* ===== Separador elegante ===== */
hr { border: none; border-top: 1px solid var(--borde); margin: 1.15rem 0; }

/* ===== Subtitulos / encabezados de la app ===== */
h2, h3 { letter-spacing: -0.2px; }
.sub-seccion {
    display: flex; align-items: center; gap: 9px;
    font-size: 0.98rem; font-weight: 800; color: var(--txt);
    margin: 14px 0 4px 0; animation: g2Fade .5s ease both;
}
.sub-seccion::before {
    content: ""; width: 4px; height: 18px; border-radius: 4px;
    background: var(--grad-verde); box-shadow: 0 2px 6px -2px rgba(91,138,114,0.7);
}

/* ===== Scrollbar refinada ===== */
::-webkit-scrollbar { width: 11px; height: 11px; }
::-webkit-scrollbar-thumb {
    background: #CFD6DA; border-radius: 9px; border: 3px solid transparent;
    background-clip: padding-box;
}
::-webkit-scrollbar-thumb:hover { background: #B6BFC5; background-clip: padding-box; }
::-webkit-scrollbar-track { background: transparent; }
"""


def inyectar_css() -> None:
    """Inyecta el sistema de estilos premium global (variables + componentes)."""
    st.markdown(
        f"<style>{_FONT_IMPORT}{_root_vars()}{_CSS}</style>",
        unsafe_allow_html=True,
    )


def sub_seccion(titulo: str) -> None:
    """Encabezado de sub-seccion con barra de acento salvia (look minimalista)."""
    st.markdown(f"<div class='sub-seccion'>{titulo}</div>", unsafe_allow_html=True)


def tarjeta_kpi(col, titulo: str, valor: str, sub: str = "", color: str | None = None,
                icono: str = "", ayuda: str = "") -> None:
    """Renderiza una tarjeta de KPI premium dentro de la columna `col`.

    `color` define el acento (barra lateral, glifo y valor); `icono` se muestra en un
    chip redondeado teñido con ese acento; `ayuda` (opcional) agrega un "?" arriba a la
    derecha con un tooltip explicativo al pasar el cursor. Firma estable y retro-
    compatible: la consumen las tres vistas.
    """
    color = color or PALETA["verde"]
    icono_html = f"<span class='kpi-icon'>{icono}</span>" if icono else ""
    sub_html = f"<div class='kpi-sub'>{sub}</div>" if sub else ""
    ayuda_html = ""
    if ayuda:
        ayuda_attr = ayuda.replace('"', "&quot;")
        ayuda_html = f"<span class='kpi-help' title=\"{ayuda_attr}\">?</span>"
    # HTML en UNA sola linea (sin saltos ni indentacion): si quedara una linea en blanco
    # -p. ej. cuando no hay tooltip- Streamlit interpretaria el resto como bloque de codigo
    # y mostraria el HTML como texto crudo.
    html = (
        f"<div class='kpi-card' style='--accent:{color};'>"
        f"{ayuda_html}"
        f"<div class='kpi-top'>{icono_html}<span class='kpi-head'>{titulo}</span></div>"
        f"<div class='kpi-val' style='color:{color};'>{valor}</div>"
        f"{sub_html}"
        f"</div>"
    )
    col.markdown(html, unsafe_allow_html=True)


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
            f"border-radius:12px;padding:13px 16px;font-size:0.86rem;color:{PALETA['txt']};"
            f"margin-top:10px;box-shadow:var(--shadow-sm);'>"
            f"<b>Veredicto:</b> {validacion.mensaje}</div>",
            unsafe_allow_html=True)
        st.caption(
            "En una distribución Exponencial la media y el desvío estándar coinciden "
            "teóricamente; su cercanía es una verificación adicional del generador.")
