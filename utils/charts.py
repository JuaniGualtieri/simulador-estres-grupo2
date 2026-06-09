# -*- coding: utf-8 -*-
"""
================================================================================
 utils/charts.py  ::  PRIMITIVAS DE VISUALIZACION CIENTIFICA (matplotlib)
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Aisla el dibujo de los graficos para que NO se duplique entre la vista web
(Streamlit -> st.pyplot) y el reporte PDF (reportlab -> PNG embebido). Cada funcion
recibe un `ax` de matplotlib y los datos crudos ya calculados por los modulos `sim/`,
respetando la paleta verde/naranja agroecologica acordada.
"""

from __future__ import annotations

from typing import List

import matplotlib
matplotlib.use("Agg")  # Backend sin ventana: valido para web y para PDF.
from matplotlib.figure import Figure

from sim.server_sim import POOLER_CAPACITY, AggregatedResult
from sim.production_sim import ProductionAggregated
from sim.sensorial_sim import (DESCRIPTORES, ESCALA_MAX, UMBRAL_ACEPTACION,
                               SensorialAggregated)

# ---- Paleta premium interdisciplinaria (verde agroecologico + ambar) ----
VERDE = "#2E7D32"
VERDE_CLARO = "#9DB089"
ROJO = "#C0392B"
AMBAR = "#B9770E"
NARANJA = "#E67E22"
TXT_TITULO = "#23311C"
TXT_EJE = "#3A4A30"
TXT_TICK = "#5B6A4C"
GRILLA = "#9DB089"
BORDE_EJE = "#C4CFB6"


def _estilizar_ejes(ax, titulo: str, xlabel: str, ylabel: str) -> None:
    """Aplica el estilo premium comun (sin marcos superior/derecho, grilla tenue)."""
    ax.set_title(titulo, fontsize=11, fontweight="bold", color=TXT_TITULO, pad=10)
    ax.set_xlabel(xlabel, fontsize=10, color=TXT_EJE)
    ax.set_ylabel(ylabel, fontsize=10, color=TXT_EJE)
    ax.grid(True, alpha=0.25, linewidth=0.8, color=GRILLA)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(BORDE_EJE)
    ax.tick_params(colors=TXT_TICK, labelsize=8)


# ===========================================================================
# PESTANIA 1 - GRAFICO A: curva temporal de conexiones ocupadas
# ===========================================================================
def dibujar_curva_conexiones(ax, agg: AggregatedResult) -> None:
    """Curva de conexiones ocupadas en el tiempo (corrida representativa).

    Linea verde suavizada con area sombreada, limite del pool en rojo y pico en ambar.
    """
    pool = agg.pool_capacity or POOLER_CAPACITY
    ax.clear()
    if agg.serie_t:
        t_min = [t / 60.0 for t in agg.serie_t]  # segundos -> minutos.
        ax.fill_between(t_min, agg.serie_conexiones, step="post",
                        color=VERDE, alpha=0.16, zorder=1)
        ax.step(t_min, agg.serie_conexiones, where="post", color=VERDE,
                linewidth=2.0, solid_capstyle="round", solid_joinstyle="round",
                label="Conexiones ocupadas", zorder=3)
        pico = agg.media("pico_conexiones")
        ax.axhline(pico, color=AMBAR, linestyle=":", linewidth=1.4,
                   label=f"Pico ~{pico:.0f}", zorder=2)

    ax.axhline(pool, color=ROJO, linestyle="--", linewidth=1.4,
               label=f"Limite del pooler ({pool})", zorder=2)

    tope = max(pool + 6, agg.media("pico_conexiones") + 6)
    ax.set_ylim(0, tope)
    ax.set_xlim(left=0)
    _estilizar_ejes(ax, f"Conexiones ocupadas  -  Escenario {agg.escenario}",
                    "Tiempo de la jornada (min)", "Conexiones concurrentes")
    ax.legend(loc="upper right", fontsize=8, frameon=True, fancybox=True, framealpha=0.9)


# ===========================================================================
# PESTANIA 1 - GRAFICO B: boxplot de "Encuestas Perdidas" sobre N replicas
# ===========================================================================
def dibujar_boxplot_perdidas(ax, agg: AggregatedResult) -> None:
    """Boxplot (caja y bigotes) del KPI 'Encuestas Perdidas' a lo largo de N replicas.

    Visualiza la dispersion del azar y los percentiles. Superpone los puntos crudos
    (stripplot con jitter) para que se vea cada replica.
    """
    import numpy as np
    muestras: List[float] = agg.muestra("encuestas_perdidas")
    ax.clear()

    if len(muestras) < 2:
        ax.text(0.5, 0.5,
                "El boxplot requiere 2 o mas replicas\npara mostrar la dispersion.",
                ha="center", va="center", fontsize=10, color=TXT_TICK,
                transform=ax.transAxes)
        _estilizar_ejes(ax, "Distribucion de Encuestas Perdidas (N replicas)",
                        "Encuestas perdidas", "")
        ax.set_yticks([])
        return

    caja = ax.boxplot(
        muestras, vert=False, widths=0.55, patch_artist=True,
        showmeans=True, meanline=True,
        boxprops=dict(facecolor="#EAF3E2", edgecolor=VERDE, linewidth=1.6),
        medianprops=dict(color=VERDE, linewidth=2.0),
        meanprops=dict(color=NARANJA, linewidth=1.8, linestyle="--"),
        whiskerprops=dict(color=VERDE, linewidth=1.4),
        capprops=dict(color=VERDE, linewidth=1.4),
        flierprops=dict(marker="o", markerfacecolor=ROJO, markersize=5, alpha=0.6,
                        markeredgecolor="none"),
    )

    # Puntos crudos de cada replica con un leve jitter vertical.
    rng = np.random.default_rng(7)
    jitter = 1.0 + (rng.random(len(muestras)) - 0.5) * 0.35
    ax.scatter(muestras, jitter, s=22, color=AMBAR, alpha=0.55, zorder=3,
               edgecolors="white", linewidths=0.5, label="Replicas")

    media = agg.media("encuestas_perdidas")
    inf, sup = agg.ic("encuestas_perdidas")
    ax.axvline(media, color=NARANJA, linestyle="--", linewidth=1.2,
               label=f"Media {media:.1f}  IC95% [{inf:.1f}-{sup:.1f}]")

    _estilizar_ejes(ax, "Distribucion de Encuestas Perdidas (N replicas)",
                    "Encuestas perdidas", "")
    ax.set_yticks([])
    ax.legend(loc="upper right", fontsize=8, frameon=True, framealpha=0.9)


# ===========================================================================
# PESTANIA 2 - GRAFICO: evolucion temporal del nivel de stock
# ===========================================================================
def dibujar_curva_stock(ax, agg: ProductionAggregated) -> None:
    """Curva del nivel de stock disponible vs tiempo (min).

    Pinta una zona sombreada ROJA en los tramos donde el stock cae a cero (faltante de
    alimento -> comensales en la cola de espera).
    """
    ax.clear()
    t = list(agg.serie_t)
    stock = list(agg.serie_stock)

    if t and stock:
        ax.fill_between(t, stock, step="post", color=VERDE, alpha=0.16, zorder=1)
        ax.step(t, stock, where="post", color=VERDE, linewidth=2.0,
                solid_capstyle="round", solid_joinstyle="round",
                label="Nivel de stock", zorder=3)

        # Zona roja: tramos [t[i], t[i+1]] en los que el stock vale 0 (faltante).
        primera_zona = True
        for i in range(len(t) - 1):
            if stock[i] <= 0:
                ax.axvspan(t[i], t[i + 1], color=ROJO, alpha=0.16, zorder=0,
                           label="Stock agotado" if primera_zona else None)
                primera_zona = False

    ax.axhline(0, color=ROJO, linestyle="--", linewidth=1.0, alpha=0.7, zorder=2)
    tope = max(stock + [1]) + 2
    ax.set_ylim(0, tope)
    ax.set_xlim(left=0)
    _estilizar_ejes(ax, "Evolucion del stock de tartaletas en el mostrador",
                    "Tiempo de simulacion (min)", "Tartaletas disponibles")
    ax.legend(loc="upper right", fontsize=8, frameon=True, framealpha=0.9)


# ===========================================================================
# PESTANIA 3 - GRAFICO A: puntaje medio por descriptor sensorial (barras)
# ===========================================================================
def dibujar_descriptores(ax, agg: SensorialAggregated) -> None:
    """Barras horizontales del puntaje medio (1-9) de cada descriptor sensorial.

    Marca el umbral de aceptacion (>= 6) con una linea ambar; las barras que lo superan
    se pintan verdes y las que no, ambar, con su IC 95% como barra de error.
    """
    ax.clear()
    nombres = list(DESCRIPTORES)
    medias = [agg.media_descriptor(d) for d in nombres]
    errores = [max(0.0, agg.media_descriptor(d) - agg.ic(f"desc_{d}")[0]) for d in nombres]
    colores = [VERDE if m >= UMBRAL_ACEPTACION else AMBAR for m in medias]

    y = list(range(len(nombres)))
    ax.barh(y, medias, color=colores, alpha=0.85, height=0.6, zorder=3,
            xerr=errores if agg.ic_disponible else None,
            error_kw=dict(ecolor=TXT_TICK, capsize=4, elinewidth=1.0))
    for yi, m in zip(y, medias):
        ax.text(m + 0.12, yi, f"{m:.2f}", va="center", fontsize=9, color=TXT_TITULO)

    ax.axvline(UMBRAL_ACEPTACION, color=NARANJA, linestyle="--", linewidth=1.4,
               label=f"Umbral de aceptacion ({UMBRAL_ACEPTACION})", zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels(nombres)
    ax.set_xlim(0, ESCALA_MAX + 0.6)
    ax.invert_yaxis()
    _estilizar_ejes(ax, "Puntaje medio por descriptor sensorial (escala 1-9)",
                    "Puntaje hedonico medio", "")
    ax.legend(loc="lower right", fontsize=8, frameon=True, framealpha=0.9)


# ===========================================================================
# PESTANIA 3 - GRAFICO B: analisis de sensibilidad del descriptor Sabor
# ===========================================================================
def dibujar_sensibilidad_sabor(ax, agg: SensorialAggregated) -> None:
    """Curva de aceptacion global (%) en funcion de la calidad del descriptor Sabor."""
    ax.clear()
    x = list(agg.sens_sabor_medias)
    y = list(agg.sens_aceptacion)
    if x and y:
        ax.fill_between(x, y, color=NARANJA, alpha=0.12, zorder=1)
        ax.plot(x, y, color=NARANJA, linewidth=2.2, marker="o", markersize=5,
                markerfacecolor="white", markeredgecolor=NARANJA, zorder=3,
                label="Aceptacion global proyectada")
        ax.axhline(UMBRAL_ACEPTACION * 0 + 80, color=VERDE, linestyle=":",
                   linewidth=1.2, alpha=0.8, label="Meta comercial (80%)", zorder=2)
    ax.set_ylim(0, 105)
    ax.set_xlim(min(x) if x else 1, max(x) if x else 9)
    _estilizar_ejes(ax, "Sensibilidad: aceptacion vs calidad del Sabor",
                    "Puntaje medio objetivo del Sabor (1-9)", "Aceptacion global (%)")
    ax.legend(loc="lower right", fontsize=8, frameon=True, framealpha=0.9)


# ===========================================================================
# FABRICAS DE FIGURAS (para PDF y para usos puntuales fuera de Streamlit)
# ===========================================================================
def figura_conexiones(agg: AggregatedResult, figsize=(7.2, 4.0), dpi=150) -> Figure:
    fig = Figure(figsize=figsize, dpi=dpi, facecolor="white")
    dibujar_curva_conexiones(fig.add_subplot(111), agg)
    fig.tight_layout()
    return fig


def figura_boxplot(agg: AggregatedResult, figsize=(7.2, 3.2), dpi=150) -> Figure:
    fig = Figure(figsize=figsize, dpi=dpi, facecolor="white")
    dibujar_boxplot_perdidas(fig.add_subplot(111), agg)
    fig.tight_layout()
    return fig


def figura_stock(agg: ProductionAggregated, figsize=(7.2, 4.0), dpi=150) -> Figure:
    fig = Figure(figsize=figsize, dpi=dpi, facecolor="white")
    dibujar_curva_stock(fig.add_subplot(111), agg)
    fig.tight_layout()
    return fig


def figura_descriptores(agg: SensorialAggregated, figsize=(7.2, 3.2), dpi=150) -> Figure:
    fig = Figure(figsize=figsize, dpi=dpi, facecolor="white")
    dibujar_descriptores(fig.add_subplot(111), agg)
    fig.tight_layout()
    return fig


def figura_sensibilidad(agg: SensorialAggregated, figsize=(7.2, 3.2), dpi=150) -> Figure:
    fig = Figure(figsize=figsize, dpi=dpi, facecolor="white")
    dibujar_sensibilidad_sabor(fig.add_subplot(111), agg)
    fig.tight_layout()
    return fig
