# -*- coding: utf-8 -*-
"""
================================================================================
 utils/charts.py  ::  VISUALIZACION INTERACTIVA (Plotly)
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Aisla la construccion de los graficos para que NO se duplique entre la vista web
(Streamlit -> st.plotly_chart) y el reporte PDF (reportlab -> PNG embebido via
fig.to_image / kaleido). Cada funcion `figura_*` recibe los datos crudos ya
calculados por los modulos `sim/` y devuelve una figura de Plotly (go.Figure)
100% interactiva: zoom, paneo, hover con el valor exacto del KPI y leyendas en
las que se puede ocultar/mostrar cada curva con un clic.

REGLA DE SEGURIDAD: aqui solo cambia el MOTOR DE RENDERIZADO (de estatico a
interactivo). Los arrays/dataframes de entrada provenientes de los motores SimPy y
del Monte Carlo se consumen tal cual, sin alterarlos.
"""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from sim.server_sim import POOLER_CAPACITY, AggregatedResult
from sim.production_sim import ProductionAggregated
from sim.sensorial_sim import (ATRIBUTOS_BOOL, ATRIBUTOS_SLIDER, ESCALA_MAX,
                               ETIQUETAS, UMBRAL_ACEPTACION, SensorialAggregated)

# ---- Paleta sincronizada con el sistema de disenio (views/theme.py) ----
VERDE = "#5B8A72"          # Salvia principal.
VERDE_CLARO = "#A8C3B4"    # Salvia claro (segunda serie).
SLATE = "#48637A"          # Azul slate (acento secundario).
ROJO = "#C25B52"           # Coral apagado (criticos / limites).
AMBAR = "#B0813F"          # Ambar apagado (umbrales).
NARANJA = "#C8895C"        # Terracota suave (sensibilidad / femenino).
TXT_TITULO = "#212529"     # Grafito (titulos).
TXT_TICK = "#6C757D"       # Gris medio (ejes y ticks).
GRILLA = "#EEF1F3"         # Grilla tenue.
BORDE = "#E9ECEF"          # Borde de ejes.

# Tintes translucidos para las areas bajo curva.
FILL_VERDE = "rgba(91,138,114,0.14)"
FILL_NARANJA = "rgba(200,137,92,0.13)"
FILL_ROJO = "rgba(194,91,82,0.14)"


# ===========================================================================
# LAYOUT COMUN (look & feel premium, template plotly_white)
# ===========================================================================
def _layout(fig: go.Figure, titulo: str, xlabel: str = "", ylabel: str = "",
            height: int = 380, leyenda: bool = True) -> go.Figure:
    """Aplica el estilo limpio y minimalista comun a todas las figuras."""
    fig.update_layout(
        template="plotly_white",
        height=height,
        title=dict(text=titulo, font=dict(size=15, color=TXT_TITULO), x=0.012,
                   xanchor="left", y=0.96),
        margin=dict(l=62, r=26, t=58, b=50),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(color=TXT_TICK, size=12),
        hoverlabel=dict(bgcolor="white", bordercolor=BORDE, font_size=12,
                        font_color=TXT_TITULO),
        showlegend=leyenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0,
                    bgcolor="rgba(255,255,255,0.65)", bordercolor=BORDE, borderwidth=1,
                    font=dict(size=11)),
    )
    fig.update_xaxes(title_text=xlabel, gridcolor=GRILLA, zeroline=False,
                     showline=True, linecolor=BORDE, ticks="outside",
                     tickcolor=BORDE, title_font=dict(color=TXT_TITULO, size=12))
    fig.update_yaxes(title_text=ylabel, gridcolor=GRILLA, zeroline=False,
                     showline=True, linecolor=BORDE, ticks="outside",
                     tickcolor=BORDE, title_font=dict(color=TXT_TITULO, size=12))
    return fig


# ===========================================================================
# PESTANIA 1 - GRAFICO A: curva temporal de conexiones ocupadas
# ===========================================================================
def figura_conexiones(agg: AggregatedResult, height: int = 380) -> go.Figure:
    """Curva escalonada de conexiones ocupadas en el tiempo (corrida representativa),
    con el limite del pooler y el pico medio como referencias toggleables."""
    pool = agg.pool_capacity or POOLER_CAPACITY
    fig = go.Figure()
    t_min = [t / 60.0 for t in agg.serie_t] if agg.serie_t else []
    if t_min:
        fig.add_trace(go.Scatter(
            x=t_min, y=agg.serie_conexiones, mode="lines",
            line=dict(color=VERDE, width=2.4, shape="hv"),
            fill="tozeroy", fillcolor=FILL_VERDE, name="Conexiones ocupadas",
            hovertemplate="t = %{x:.1f} min<br>Conexiones = %{y}<extra></extra>"))
        pico = agg.media("pico_conexiones")
        xmax = max(t_min)
        fig.add_trace(go.Scatter(
            x=[0, xmax], y=[pico, pico], mode="lines",
            line=dict(color=AMBAR, width=1.4, dash="dot"),
            name=f"Pico ~{pico:.0f}",
            hovertemplate=f"Pico de conexiones ~{pico:.0f}<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=[0, xmax], y=[pool, pool], mode="lines",
            line=dict(color=ROJO, width=1.6, dash="dash"),
            name=f"Límite del pooler ({pool})",
            hovertemplate=f"Límite del pooler = {pool}<extra></extra>"))
        tope = max(pool + 6, agg.media("pico_conexiones") + 6)
        fig.update_yaxes(range=[0, tope])
        fig.update_xaxes(rangemode="tozero")
    _layout(fig, f"Conexiones ocupadas · Escenario {agg.escenario}",
            "Tiempo de la jornada (min)", "Conexiones concurrentes", height)
    return fig


# ===========================================================================
# PESTANIA 1 - GRAFICO B: boxplot de "Encuestas Perdidas" sobre N replicas
# ===========================================================================
def figura_boxplot(agg: AggregatedResult, height: int = 300) -> go.Figure:
    """Boxplot horizontal del KPI 'Encuestas Perdidas' a lo largo de las N replicas,
    con cada replica como punto (jitter) y la media + IC 95% destacados."""
    muestras = list(agg.muestra("encuestas_perdidas"))
    fig = go.Figure()
    if len(muestras) < 2:
        fig.add_annotation(
            text="El boxplot requiere 2 o más réplicas<br>para mostrar la dispersión.",
            showarrow=False, font=dict(color=TXT_TICK, size=13),
            xref="paper", yref="paper", x=0.5, y=0.5)
        _layout(fig, "Distribución de Encuestas Perdidas (N réplicas)",
                "Encuestas perdidas", "", height, leyenda=False)
        fig.update_yaxes(showticklabels=False)
        return fig

    fig.add_trace(go.Box(
        x=muestras, name="Encuestas perdidas", orientation="h",
        boxmean=True, boxpoints="all", jitter=0.5, pointpos=0.0,
        marker=dict(color=AMBAR, size=6, opacity=0.7),
        line=dict(color=VERDE, width=1.8), fillcolor=FILL_VERDE,
        hovertemplate="Encuestas perdidas = %{x:.0f}<extra></extra>"))
    media = agg.media("encuestas_perdidas")
    inf, sup = agg.ic("encuestas_perdidas")
    fig.add_vline(x=media, line=dict(color=NARANJA, width=1.6, dash="dash"),
                  annotation_text=f"Media {media:.1f}  ·  IC95% [{inf:.1f}–{sup:.1f}]",
                  annotation_position="top", annotation_font_color=TXT_TITULO)
    _layout(fig, "Distribución de Encuestas Perdidas (N réplicas)",
            "Encuestas perdidas", "", height, leyenda=False)
    fig.update_yaxes(showticklabels=False)
    return fig


# ===========================================================================
# PESTANIA 2 - GRAFICO: evolucion temporal del nivel de stock de despacho
# ===========================================================================
def _zonas_agotado(t, stock):
    """Une los tramos contiguos en que el stock vale 0 en intervalos (t0, t1)."""
    zonas = []
    i = 0
    n = len(t)
    while i < n - 1:
        if stock[i] <= 0:
            j = i
            while j < n - 1 and stock[j] <= 0:
                j += 1
            zonas.append((t[i], t[j]))
            i = j
        else:
            i += 1
    return zonas


def figura_stock(agg: ProductionAggregated, height: int = 380) -> go.Figure:
    """Curva escalonada del nivel de stock de tartaletas enteras en el mostrador de
    despacho vs tiempo (min), con zonas rojas donde el stock cae a cero (faltante)."""
    t = list(agg.serie_t)
    stock = list(agg.serie_stock)
    fig = go.Figure()
    if t and stock:
        fig.add_trace(go.Scatter(
            x=t, y=stock, mode="lines",
            line=dict(color=VERDE, width=2.4, shape="hv"),
            fill="tozeroy", fillcolor=FILL_VERDE, name="Nivel de stock",
            hovertemplate="t = %{x:.1f} min<br>Stock = %{y} tartaletas<extra></extra>"))
        zonas = _zonas_agotado(t, stock)
        for (x0, x1) in zonas:
            fig.add_vrect(x0=x0, x1=x1, fillcolor=FILL_ROJO, line_width=0, layer="below")
        if zonas:
            # Entrada de leyenda (toggleable) para las zonas de faltante.
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode="markers",
                marker=dict(size=11, color="rgba(194,91,82,0.45)", symbol="square"),
                name="Stock agotado", hoverinfo="skip"))
        tope = max(stock + [1]) + 2
        fig.update_yaxes(range=[0, tope])
        fig.update_xaxes(rangemode="tozero")
    _layout(fig, "Evolución del stock de tartaletas en el mostrador de despacho",
            "Tiempo de simulación (min)", "Tartaletas enteras disponibles", height)
    return fig


# ===========================================================================
# PESTANIA 3 - GRAFICO A: perfil sensorial (RADAR / POLAR de los 8 atributos)
# ===========================================================================
def figura_perfil(agg: SensorialAggregated, height: int = 440) -> go.Figure:
    """Radar (grafico polar) del puntaje medio (1-10) de los 8 atributos numericos,
    con el anillo del umbral de aceptacion y el IC 95% de cada atributo en el hover."""
    atributos = list(ATRIBUTOS_SLIDER)
    nombres = [ETIQUETAS[a].split(" (")[0] for a in atributos]   # Etiqueta corta para el radar.
    medias = [agg.media(a) for a in atributos]
    # Cerramos el poligono repitiendo el primer punto.
    theta = nombres + [nombres[0]]
    r = medias + [medias[0]]
    ic_low = [agg.ic(a)[0] for a in atributos]
    ic_high = [agg.ic(a)[1] for a in atributos]
    customdata = list(zip(ic_low + [ic_low[0]], ic_high + [ic_high[0]]))

    fig = go.Figure()
    # Anillo del umbral de aceptacion.
    fig.add_trace(go.Scatterpolar(
        r=[UMBRAL_ACEPTACION] * len(theta), theta=theta, mode="lines",
        line=dict(color=AMBAR, width=1.5, dash="dash"),
        name=f"Umbral de aceptación ({UMBRAL_ACEPTACION})", hoverinfo="skip"))
    # Poligono del perfil sensorial.
    if agg.ic_disponible:
        hovert = ("<b>%{theta}</b><br>Puntaje medio = %{r:.2f}/10<br>"
                  "IC95% [%{customdata[0]:.2f} – %{customdata[1]:.2f}]<extra></extra>")
    else:
        hovert = "<b>%{theta}</b><br>Puntaje medio = %{r:.2f}/10<extra></extra>"
    fig.add_trace(go.Scatterpolar(
        r=r, theta=theta, mode="lines+markers", fill="toself",
        fillcolor="rgba(91,138,114,0.22)", line=dict(color=VERDE, width=2.6),
        marker=dict(size=7, color=VERDE), name="Puntaje medio",
        customdata=customdata, hovertemplate=hovert))
    fig.update_layout(
        template="plotly_white", height=height, paper_bgcolor="white",
        title=dict(text="Perfil sensorial: puntaje medio por atributo (escala 1-10)",
                   font=dict(size=15, color=TXT_TITULO), x=0.012, xanchor="left", y=0.97),
        margin=dict(l=70, r=70, t=70, b=50),
        font=dict(color=TXT_TICK, size=12),
        hoverlabel=dict(bgcolor="white", bordercolor=BORDE, font_color=TXT_TITULO),
        legend=dict(orientation="h", yanchor="bottom", y=-0.08, xanchor="center", x=0.5,
                    font=dict(size=11)),
        polar=dict(
            bgcolor="white",
            radialaxis=dict(range=[0, ESCALA_MAX], tickvals=[2, 4, 6, 8, 10],
                            gridcolor=GRILLA, linecolor=BORDE, tickfont=dict(size=10)),
            angularaxis=dict(gridcolor=GRILLA, linecolor=BORDE,
                             tickfont=dict(size=10, color=TXT_TITULO))),
    )
    return fig


# ===========================================================================
# PESTANIA 3 - GRAFICO B: preguntas dicotomicas Si/No (barras 100% apiladas)
# ===========================================================================
def figura_si_no(agg: SensorialAggregated, height: int = 280) -> go.Figure:
    """Barras horizontales 100% apiladas con el % de 'Sí' / 'No' de las dos cualitativas
    (matriz tipo JAR), construidas con Plotly Express."""
    atributos = list(ATRIBUTOS_BOOL)
    nombres = [ETIQUETAS[a] for a in atributos]
    pct_si = [agg.prop_si(a) for a in atributos]
    pct_no = [100.0 - p for p in pct_si]

    fig = px.bar(
        x=pct_si + pct_no,
        y=nombres + nombres,
        color=["Sí"] * len(nombres) + ["No"] * len(nombres),
        orientation="h",
        color_discrete_map={"Sí": VERDE, "No": VERDE_CLARO},
        text=[f"{v:.0f}%" for v in (pct_si + pct_no)],
    )
    fig.update_traces(textposition="inside", insidetextanchor="middle",
                      textfont=dict(color="white", size=12),
                      hovertemplate="%{y}<br>%{fullData.name} = %{x:.1f}%<extra></extra>")
    fig.update_layout(barmode="stack", legend_title_text="")
    fig.update_xaxes(range=[0, 100], ticksuffix="%")
    _layout(fig, "Preguntas cualitativas (Sí / No) — barras 100% apiladas",
            "Porcentaje de comensales", "", height)
    return fig


# ===========================================================================
# PESTANIA 3 - GRAFICO C: demografia del panel (edades + sexo)
# ===========================================================================
def figura_demografia(agg: SensorialAggregated, height: int = 340) -> go.Figure:
    """Histograma de edades + dona de distribucion por sexo del panel de comensales."""
    edades = [c.edad for c in agg.panel]
    n_masc = sum(1 for c in agg.panel if c.sexo == "Masculino")
    n_fem = len(agg.panel) - n_masc

    fig = make_subplots(
        rows=1, cols=2, column_widths=[0.58, 0.42],
        specs=[[{"type": "xy"}, {"type": "domain"}]],
        subplot_titles=("Distribución de edades", "Distribución por sexo"))
    if edades:
        fig.add_trace(go.Histogram(
            x=edades, xbins=dict(start=15, end=75, size=5),
            marker=dict(color=VERDE, line=dict(color="white", width=1)),
            name="Edades", showlegend=False,
            hovertemplate="Edad %{x} años<br>%{y} comensales<extra></extra>"),
            row=1, col=1)
    if agg.panel:
        fig.add_trace(go.Pie(
            labels=["Masculino", "Femenino"], values=[n_masc, n_fem],
            marker=dict(colors=[SLATE, NARANJA], line=dict(color="white", width=2)),
            hole=0.5, textinfo="percent", sort=False,
            hovertemplate="%{label}<br>%{value} comensales (%{percent})<extra></extra>"),
            row=1, col=2)
    fig.update_layout(
        template="plotly_white", height=height, paper_bgcolor="white",
        plot_bgcolor="white", font=dict(color=TXT_TICK, size=12),
        margin=dict(l=50, r=20, t=56, b=44),
        hoverlabel=dict(bgcolor="white", bordercolor=BORDE, font_color=TXT_TITULO),
        legend=dict(orientation="h", yanchor="bottom", y=-0.12, xanchor="center", x=0.78,
                    font=dict(size=11)),
    )
    fig.update_xaxes(title_text="Edad (años)", gridcolor=GRILLA, showline=True,
                     linecolor=BORDE, row=1, col=1)
    fig.update_yaxes(title_text="Comensales", gridcolor=GRILLA, showline=True,
                     linecolor=BORDE, row=1, col=1)
    return fig


# ===========================================================================
# PESTANIA 3 - GRAFICO D: analisis de sensibilidad del Sabor general
# ===========================================================================
def figura_sensibilidad(agg: SensorialAggregated, height: int = 360) -> go.Figure:
    """Curva de aceptacion global (%) en funcion de la media objetivo del Sabor general."""
    x = list(agg.sens_sabor_medias)
    y = list(agg.sens_aceptacion)
    fig = go.Figure()
    if x and y:
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers", fill="tozeroy", fillcolor=FILL_NARANJA,
            line=dict(color=NARANJA, width=2.8),
            marker=dict(size=8, color="white", line=dict(color=NARANJA, width=2)),
            name="Aceptación global proyectada",
            hovertemplate="Sabor objetivo = %{x:.0f}/10<br>"
                          "Aceptación = %{y:.1f}%<extra></extra>"))
        fig.add_hline(y=80, line=dict(color=VERDE, width=1.4, dash="dot"),
                      annotation_text="Meta comercial (80%)",
                      annotation_position="top left", annotation_font_color=VERDE)
        fig.add_vline(x=UMBRAL_ACEPTACION, line=dict(color=AMBAR, width=1.4, dash="dash"),
                      annotation_text=f"Umbral ({UMBRAL_ACEPTACION})",
                      annotation_position="bottom right", annotation_font_color=AMBAR)
        fig.update_yaxes(range=[0, 105], ticksuffix="%")
        fig.update_xaxes(range=[min(x) - 0.3, max(x) + 0.3])
    _layout(fig, "Sensibilidad: aceptación global vs Sabor general",
            "Puntaje medio objetivo del Sabor general (1-10)", "Aceptación global", height,
            leyenda=False)
    return fig
