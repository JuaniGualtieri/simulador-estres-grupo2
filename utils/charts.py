# -*- coding: utf-8 -*-
"""
================================================================================
 utils/charts.py  ::  VISUALIZACION INTERACTIVA (Plotly) - CAPA PREMIUM
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Aisla la construccion de los graficos para que NO se duplique entre la vista web
(Streamlit -> st.plotly_chart) y el reporte PDF (reportlab -> PNG embebido via
fig.to_image / kaleido). Cada funcion `figura_*` recibe los datos crudos ya
calculados por los modulos `sim/` y devuelve una figura de Plotly (go.Figure)
100% interactiva: zoom con scroll, paneo, hover con guias (spikelines) y leyendas
en las que se puede ocultar/mostrar cada serie con un clic.

ACABADO VISUAL: tipografia Inter, rellenos con GRADIENTE, suavizado spline en las
curvas continuas, markers con halo blanco, transiciones animadas y una barra de
herramientas (modebar) depurada compartida por todas las figuras (`CHART_CONFIG`).

REGLA DE SEGURIDAD: aqui solo cambia el MOTOR DE RENDERIZADO (estilo + interaccion).
Los arrays/dataframes de entrada provenientes de los motores SimPy y del Monte Carlo
se consumen tal cual, sin alterar la matematica.
"""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go

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
SPIKE = "#B8C0C6"          # Guia (spikeline) en hover.

# Tipografia coherente con el resto del dashboard (Inter, cargada por theme.py).
FONT_FAMILY = "Inter, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

# Componentes RGB para construir rellenos translucidos y gradientes.
_RGB = {
    "verde": (91, 138, 114),
    "verde_claro": (168, 195, 180),
    "naranja": (200, 137, 92),
    "rojo": (194, 91, 82),
    "slate": (72, 99, 122),
    "ambar": (176, 129, 63),
}


def _rgba(nombre: str, alpha: float) -> str:
    r, g, b = _RGB[nombre]
    return f"rgba({r},{g},{b},{alpha})"


def _grad(nombre: str, top: float = 0.30, bot: float = 0.015) -> dict:
    """Gradiente vertical translucido (mas intenso cerca de la curva, se desvanece
    hacia el eje) para los rellenos de area: aporta profundidad sin saturar."""
    return dict(type="vertical",
                colorscale=[[0.0, _rgba(nombre, bot)], [1.0, _rgba(nombre, top)]])


# Tintes translucidos planos (compatibilidad: usados como respaldo / en el PDF).
FILL_VERDE = _rgba("verde", 0.14)
FILL_NARANJA = _rgba("naranja", 0.13)
FILL_ROJO = _rgba("rojo", 0.14)

# ---------------------------------------------------------------------------
# CONFIG COMPARTIDA DE LA MODEBAR (barra de herramientas Plotly depurada).
# Las vistas la pasan como `st.plotly_chart(fig, config=CHART_CONFIG)`.
# ---------------------------------------------------------------------------
CHART_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": True,                 # Zoom con la rueda del mouse (segun caption de las vistas).
    "doubleClick": "reset",
    "modeBarButtonsToRemove": [
        "select2d", "lasso2d", "zoomIn2d", "zoomOut2d", "autoScale2d",
    ],
    "toImageButtonOptions": {
        "format": "png", "scale": 2, "filename": "grafico_simulacion_grupo2",
    },
}


# ===========================================================================
# LAYOUT COMUN (look & feel premium, template plotly_white)
# ===========================================================================
def _layout(fig: go.Figure, titulo: str, xlabel: str = "", ylabel: str = "",
            height: int = 380, leyenda: bool = True, subtitulo: str = "",
            spikes: bool = True, hovermode: str | bool = "closest") -> go.Figure:
    """Aplica el estilo limpio, animado y minimalista comun a todas las figuras."""
    titulo_txt = titulo
    margen_top = 60
    if subtitulo:
        titulo_txt = (f"{titulo}<br><span style='font-size:12px;color:{TXT_TICK};"
                      f"font-weight:400;'>{subtitulo}</span>")
        margen_top = 78
    fig.update_layout(
        template="plotly_white",
        height=height,
        title=dict(text=titulo_txt, font=dict(size=16, color=TXT_TITULO, family=FONT_FAMILY),
                   x=0.012, xanchor="left", y=0.96, yanchor="top"),
        margin=dict(l=64, r=28, t=margen_top, b=52),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TXT_TICK, size=12, family=FONT_FAMILY),
        hovermode=hovermode,
        hoverlabel=dict(bgcolor="white", bordercolor=BORDE, font_size=12,
                        font_color=TXT_TITULO, font_family=FONT_FAMILY),
        showlegend=leyenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0,
                    bgcolor="rgba(255,255,255,0.72)", bordercolor=BORDE, borderwidth=1,
                    font=dict(size=11), itemclick="toggle", itemdoubleclick="toggleothers"),
        transition=dict(duration=420, easing="cubic-in-out"),
    )
    fig.update_xaxes(title_text=xlabel, gridcolor=GRILLA, zeroline=False,
                     showline=True, linecolor=BORDE, ticks="outside",
                     tickcolor=BORDE, title_font=dict(color=TXT_TITULO, size=12),
                     showspikes=spikes, spikethickness=1, spikedash="dot",
                     spikecolor=SPIKE, spikemode="across")
    fig.update_yaxes(title_text=ylabel, gridcolor=GRILLA, zeroline=False,
                     showline=True, linecolor=BORDE, ticks="outside",
                     tickcolor=BORDE, title_font=dict(color=TXT_TITULO, size=12))
    return fig


# ===========================================================================
# PESTANIA 1 - GRAFICO A: curva temporal de conexiones ocupadas
# ===========================================================================
def figura_conexiones(agg: AggregatedResult, height: int = 380) -> go.Figure:
    """Curva escalonada de conexiones ocupadas en el tiempo (corrida representativa).

    La unica referencia es el LIMITE DINAMICO del pooler (= tamanio real configurado del
    pool), dibujado como linea de capacidad; no hay lineas de pico hardcodeadas que se
    confundan con un techo. El pico real es visible en la propia curva.
    """
    pool = agg.pool_capacity or POOLER_CAPACITY
    fig = go.Figure()
    t_min = [t / 60.0 for t in agg.serie_t] if agg.serie_t else []
    if t_min:
        fig.add_trace(go.Scatter(
            x=t_min, y=agg.serie_conexiones, mode="lines",
            line=dict(color=VERDE, width=2.6, shape="hv"),
            fill="tozeroy", fillgradient=_grad("verde", 0.26),
            name="Conexiones ocupadas",
            hovertemplate="Conexiones = %{y}<extra></extra>"))
        # Linea de CAPACIDAD dinamica = tamanio real del pool (shape, sin hover fantasma).
        fig.add_hline(
            y=pool, line=dict(color=ROJO, width=1.8, dash="dash"),
            annotation_text=f"Capacidad del pooler = {pool}",
            annotation_position="top right", annotation_font_color=ROJO,
            annotation_font_size=11)
        pico_serie = max(agg.serie_conexiones) if agg.serie_conexiones else 0
        tope = max(pool, pico_serie) * 1.12 + 2
        fig.update_yaxes(range=[0, tope])
        fig.update_xaxes(rangemode="tozero")
    _layout(fig, "Conexiones ocupadas en el tiempo",
            "Tiempo de la jornada (min)", "Conexiones concurrentes", height,
            subtitulo=f"Escenario {agg.escenario}", leyenda=False, hovermode="x unified")
    return fig


# ===========================================================================
# PESTANIA 1 - GRAFICO B: boxplot de "Errores de Conexion" sobre N replicas
# ===========================================================================
def figura_boxplot(agg: AggregatedResult, height: int = 300) -> go.Figure:
    """Boxplot horizontal del KPI 'Errores de Conexion / Time-out de Red' a lo largo de
    las N replicas, con cada replica como punto (jitter) y la media + IC 95% destacados."""
    muestras = list(agg.muestra("errores_conexion"))
    fig = go.Figure()
    if len(muestras) < 2:
        fig.add_annotation(
            text="El boxplot requiere 2 o más réplicas<br>para mostrar la dispersión.",
            showarrow=False, font=dict(color=TXT_TICK, size=13, family=FONT_FAMILY),
            xref="paper", yref="paper", x=0.5, y=0.5)
        _layout(fig, "Distribución de Errores de Conexión",
                "Errores de conexión / time-outs", "", height, leyenda=False, spikes=False,
                subtitulo="N réplicas")
        fig.update_yaxes(showticklabels=False)
        return fig

    media = agg.media("errores_conexion")
    inf, sup = agg.ic("errores_conexion")
    # Banda translucida del IC 95% por detras del boxplot.
    fig.add_vrect(x0=inf, x1=sup, fillcolor=_rgba("verde", 0.10), line_width=0,
                  layer="below")
    fig.add_trace(go.Box(
        x=muestras, name="Errores de conexión", orientation="h",
        boxmean=True, boxpoints="all", jitter=0.5, pointpos=0.0,
        # Solo los puntos disparan el tooltip (no la caja con min/q1/mediana/q3/max), para
        # evitar los recuadros toscos al pasar el cursor por el cuerpo del boxplot.
        hoveron="points",
        marker=dict(color=AMBAR, size=7, opacity=0.75,
                    line=dict(color="white", width=1)),
        line=dict(color=VERDE, width=2.0), fillcolor=_rgba("verde", 0.18),
        whiskerwidth=0.6,
        hovertemplate="Réplica: %{x:.0f} errores de conexión<extra></extra>"))
    fig.add_vline(x=media, line=dict(color=NARANJA, width=1.8, dash="dash"),
                  annotation_text=f"Media {media:.1f}  ·  IC95% [{inf:.1f}–{sup:.1f}]",
                  annotation_position="top", annotation_font_color=TXT_TITULO,
                  annotation_font_size=11)
    _layout(fig, "Distribución de Errores de Conexión / Time-out",
            "Errores de conexión / time-outs", "", height, leyenda=False, spikes=False,
            subtitulo="Dispersión sobre las N réplicas")
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


def _escalonar_coincidentes(t, eps: float = 0.12):
    """Separa por un epsilon los puntos con el MISMO instante (solo para el dibujo).

    Cuando una bandeja sale del horno y hay fila de espera, el +8 y los -1 de los
    comensales en cola ocurren en el mismo instante de simulacion: dibujados tal cual se
    verian como un 'palo' vertical. Desplazando una fraccion de minuto cada punto
    coincidente, la reposicion y el consumo se ven como una escalera real. No altera los
    datos del modelo: es una transformacion exclusivamente visual del eje temporal.
    """
    out = []
    last = None
    for ti in t:
        ti_disp = last + eps if (last is not None and ti <= last) else ti
        out.append(ti_disp)
        last = ti_disp
    return out


def figura_stock(agg: ProductionAggregated, height: int = 400) -> go.Figure:
    """Escalera (step/area) del nivel de stock de tartaletas listas en el mostrador del
    stand vs tiempo (min), con zonas rojas donde el mostrador queda en cero (faltante).

    La curva sube de golpe +8 cuando sale una bandeja del horno y baja un escalon -1 por
    cada comensal que compra (el monitoreo del Container captura cada transicion real).
    """
    stock = list(agg.serie_stock)
    t = _escalonar_coincidentes(list(agg.serie_t))   # Solo para el dibujo (escalera legible).
    stock_ini = agg.config.stock_inicial_unidades
    fig = go.Figure()
    if t and stock:
        # Zonas de faltante (stock = 0) por detras de la curva.
        zonas = _zonas_agotado(t, stock)
        for (x0, x1) in zonas:
            fig.add_vrect(x0=x0, x1=x1, fillcolor=_rgba("rojo", 0.10),
                          line_width=0, layer="below")
        # Escalera del stock con relleno en gradiente (line_shape "hv").
        fig.add_trace(go.Scatter(
            x=t, y=stock, mode="lines",
            line=dict(color=VERDE, width=2.6, shape="hv"),
            fill="tozeroy", fillgradient=_grad("verde", 0.28),
            name="Tartaletas listas",
            hovertemplate="Stock = %{y} tartaletas<extra></extra>"))
        # Referencia del stock inicial de pre-produccion (al abrir el stand).
        if stock_ini > 0:
            fig.add_hline(
                y=stock_ini, line=dict(color=SLATE, width=1.2, dash="dot"),
                annotation_text=f"Stock inicial ({stock_ini})",
                annotation_position="top right", annotation_font_color=SLATE,
                annotation_font_size=11)
        if zonas:
            # Entrada de leyenda (toggleable) para las zonas de faltante.
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode="markers",
                marker=dict(size=12, color=_rgba("rojo", 0.45), symbol="square"),
                name="Mostrador agotado (fila de espera)", hoverinfo="skip"))
        tope = max(stock + [stock_ini, 1]) + 2
        fig.update_yaxes(range=[0, tope], dtick=4)
        fig.update_xaxes(rangemode="tozero")
    _layout(fig, "Evolución del stock en el mostrador del stand",
            "Tiempo de la jornada (min)", "Tartaletas listas disponibles", height,
            subtitulo="Reposición por horneado (+8) vs. compra de los comensales (−1)",
            leyenda=bool(_zonas_agotado(t, stock)) if (t and stock) else False,
            hovermode="x unified")
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
        line=dict(color=AMBAR, width=1.6, dash="dash"),
        name=f"Umbral de aceptación ({UMBRAL_ACEPTACION})", hoverinfo="skip"))
    # Poligono del perfil sensorial.
    if agg.ic_disponible:
        hovert = ("<b>%{theta}</b><br>Puntaje medio = %{r:.2f}/10<br>"
                  "IC95% [%{customdata[0]:.2f} – %{customdata[1]:.2f}]<extra></extra>")
    else:
        hovert = "<b>%{theta}</b><br>Puntaje medio = %{r:.2f}/10<extra></extra>"
    fig.add_trace(go.Scatterpolar(
        r=r, theta=theta, mode="lines+markers", fill="toself",
        fillcolor=_rgba("verde", 0.24), line=dict(color=VERDE, width=2.8, shape="spline"),
        marker=dict(size=8, color=VERDE, line=dict(color="white", width=1.5)),
        name="Puntaje medio", customdata=customdata, hovertemplate=hovert))
    fig.update_layout(
        template="plotly_white", height=height + 30, paper_bgcolor="rgba(0,0,0,0)",
        title=dict(text="Perfil sensorial por atributo (escala 1-10)",
                   font=dict(size=16, color=TXT_TITULO, family=FONT_FAMILY),
                   x=0.012, xanchor="left", y=0.98),
        # Margenes amplios para que los 8 nombres de atributos no se taparen con el lienzo.
        margin=dict(l=95, r=95, t=70, b=92),
        font=dict(color=TXT_TICK, size=12, family=FONT_FAMILY),
        hoverlabel=dict(bgcolor="white", bordercolor=BORDE, font_color=TXT_TITULO,
                        font_family=FONT_FAMILY),
        # Leyenda bien por debajo del radar para no encimarse con los atributos inferiores.
        legend=dict(orientation="h", yanchor="top", y=-0.10, xanchor="center", x=0.5,
                    font=dict(size=11), bgcolor="rgba(255,255,255,0.0)"),
        transition=dict(duration=420, easing="cubic-in-out"),
        polar=dict(
            bgcolor="rgba(248,250,249,0.6)",
            domain=dict(x=[0.0, 1.0], y=[0.04, 0.96]),
            radialaxis=dict(range=[0, ESCALA_MAX], tickvals=[2, 4, 6, 8, 10],
                            gridcolor=GRILLA, linecolor=BORDE, tickfont=dict(size=9),
                            angle=90, tickangle=0),
            angularaxis=dict(gridcolor=GRILLA, linecolor=BORDE,
                             tickfont=dict(size=9.5, color=TXT_TITULO))),
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
                      textfont=dict(color="white", size=12, family=FONT_FAMILY),
                      marker=dict(line=dict(color="white", width=1.5)),
                      width=0.62,
                      hovertemplate="%{y}<br>%{fullData.name} = %{x:.1f}%<extra></extra>")
    fig.update_layout(barmode="stack", legend_title_text="", bargap=0.35)
    fig.update_xaxes(range=[0, 100], ticksuffix="%")
    _layout(fig, "Preguntas cualitativas (Sí / No)",
            "Porcentaje de comensales", "", height, spikes=False,
            subtitulo="Barras 100% apiladas (matriz tipo JAR)")
    return fig


# ===========================================================================
# PESTANIA 3 - GRAFICO C: demografia del panel (edades + sexo)
# ===========================================================================
def figura_demografia(agg: SensorialAggregated, height: int = 350) -> go.Figure:
    """Histograma de edades + dona de distribucion por sexo (Masculino/Femenino/Otro).

    Se construye con dominios EXPLICITOS (sin make_subplots) para colocar el total de
    comensales perfectamente centrado en el orificio de la dona, sin superposiciones.
    """
    edades = [c.edad for c in agg.panel]
    n_masc = sum(1 for c in agg.panel if c.sexo == "Masculino")
    n_fem = sum(1 for c in agg.panel if c.sexo == "Femenino")
    n_otro = len(agg.panel) - n_masc - n_fem

    # Dominios: histograma a la izquierda, dona a la derecha (con su centro definido).
    dom_hist = [0.0, 0.50]
    dom_pie_x, dom_pie_y = [0.60, 1.0], [0.0, 0.84]
    centro_pie_x = sum(dom_pie_x) / 2
    centro_pie_y = sum(dom_pie_y) / 2

    fig = go.Figure()
    if edades:
        fig.add_trace(go.Histogram(
            x=edades, xbins=dict(start=15, end=75, size=5),
            marker=dict(color=VERDE, line=dict(color="white", width=1.5), opacity=0.92),
            name="Edades", showlegend=False,
            hovertemplate="Edad %{x} años<br>%{y} comensales<extra></extra>"))
    if agg.panel:
        # Solo se muestran los sexos con al menos un comensal (evita porciones vacias).
        sexos = [("Masculino", n_masc, SLATE), ("Femenino", n_fem, NARANJA),
                 ("Otro", n_otro, VERDE_CLARO)]
        labels = [s for s, v, _ in sexos if v > 0]
        valores = [v for _, v, _ in sexos if v > 0]
        colores = [c for _, v, c in sexos if v > 0]
        fig.add_trace(go.Pie(
            labels=labels, values=valores, domain=dict(x=dom_pie_x, y=dom_pie_y),
            marker=dict(colors=colores, line=dict(color="white", width=3)),
            hole=0.66, textinfo="percent", textposition="inside",
            insidetextorientation="horizontal", sort=False,
            textfont=dict(family=FONT_FAMILY, size=12, color="white"),
            hovertemplate="%{label}<br>%{value} comensales (%{percent})<extra></extra>"))
        # Total perfectamente centrado en el orificio de la dona (texto compacto que entra).
        fig.add_annotation(
            text=f"<b style='font-size:17px'>{len(agg.panel)}</b><br>"
                 f"<span style='font-size:9px;color:{TXT_TICK}'>comensales</span>",
            x=centro_pie_x, y=centro_pie_y, xref="paper", yref="paper", showarrow=False,
            align="center", font=dict(family=FONT_FAMILY, color=TXT_TITULO))
    # Titulos de cada panel (posicionados a mano sobre cada dominio).
    fig.add_annotation(text="<b>Distribución de edades</b>", x=sum(dom_hist) / 2, y=1.07,
                       xref="paper", yref="paper", showarrow=False,
                       font=dict(family=FONT_FAMILY, size=12.5, color=TXT_TITULO))
    fig.add_annotation(text="<b>Distribución por sexo</b>", x=centro_pie_x, y=1.07,
                       xref="paper", yref="paper", showarrow=False,
                       font=dict(family=FONT_FAMILY, size=12.5, color=TXT_TITULO))
    fig.update_layout(
        template="plotly_white", height=height, paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(color=TXT_TICK, size=12, family=FONT_FAMILY),
        margin=dict(l=54, r=20, t=58, b=52), bargap=0.06,
        hoverlabel=dict(bgcolor="white", bordercolor=BORDE, font_color=TXT_TITULO,
                        font_family=FONT_FAMILY),
        transition=dict(duration=420, easing="cubic-in-out"),
        legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="center",
                    x=centro_pie_x, font=dict(size=11)),
    )
    fig.update_xaxes(domain=dom_hist, title_text="Edad (años)", gridcolor=GRILLA,
                     showline=True, linecolor=BORDE, ticks="outside", tickcolor=BORDE)
    fig.update_yaxes(domain=[0.0, 0.84], title_text="Comensales", gridcolor=GRILLA,
                     showline=True, linecolor=BORDE)
    return fig


# ===========================================================================
# PESTANIA 3 - GRAFICO D: sensibilidad de la aceptacion a la calidad de cocina
# ===========================================================================
def figura_sensibilidad(agg: SensorialAggregated, height: int = 360) -> go.Figure:
    """Curva de aceptacion global (%) en funcion de la CALIDAD de preparacion (1-10).

    El punto de la calidad elegida por el usuario se resalta como "configuracion actual":
    al mover el slider, ese marcador se desplaza por la curva y la aceptacion proyectada
    cambia en tiempo real (el grafico ya no es estatico)."""
    x = list(agg.sens_calidades)
    y = list(agg.sens_aceptacion)
    fig = go.Figure()
    if x and y:
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers", fill="tozeroy",
            fillgradient=_grad("naranja", 0.24),
            line=dict(color=NARANJA, width=3.0, shape="spline"),
            marker=dict(size=8, color="white", line=dict(color=NARANJA, width=2.2)),
            name="Aceptación proyectada",
            hovertemplate="Calidad = %{x:.0f}/10<br>Aceptación = %{y:.1f}%<extra></extra>"))
        fig.add_hline(y=80, line=dict(color=VERDE, width=1.6, dash="dot"),
                      annotation_text="Meta comercial (80%)",
                      annotation_position="top left", annotation_font_color=VERDE,
                      annotation_font_size=11)
        # Punto de la configuracion actual (calidad elegida en el slider).
        cal_actual = int(agg.config.calidad_cocina)
        idx = max(0, min(len(y) - 1, cal_actual - 1))
        y_actual = y[idx]
        fig.add_vline(x=cal_actual, line=dict(color=SLATE, width=1.4, dash="dash"))
        fig.add_trace(go.Scatter(
            x=[cal_actual], y=[y_actual], mode="markers",
            marker=dict(size=16, color=NARANJA, line=dict(color="white", width=2.5),
                        symbol="circle"),
            name="Calidad actual",
            hovertemplate=f"<b>Configuración actual</b><br>Calidad = {cal_actual}/10<br>"
                          f"Aceptación = {y_actual:.1f}%<extra></extra>"))
        fig.add_annotation(
            x=cal_actual, y=y_actual, text=f"<b>{y_actual:.0f}%</b>", showarrow=True,
            arrowhead=0, arrowcolor=SLATE, ax=0, ay=-28,
            font=dict(family=FONT_FAMILY, size=12, color=TXT_TITULO),
            bgcolor="rgba(255,255,255,0.85)", bordercolor=BORDE, borderwidth=1)
        fig.update_yaxes(range=[0, 105], ticksuffix="%")
        fig.update_xaxes(range=[0.5, 10.5], dtick=1)
    _layout(fig, "Sensibilidad: aceptación global vs. Calidad de preparación",
            "Calidad de preparación en cocina (1-10)", "Aceptación global", height,
            leyenda=False, subtitulo="El punto marca la calidad elegida en el panel")
    return fig
