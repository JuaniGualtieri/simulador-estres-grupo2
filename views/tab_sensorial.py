# -*- coding: utf-8 -*-
"""
================================================================================
 views/tab_sensorial.py  ::  VISTA WEB - PESTANIA 3 (ACEPTACION SENSORIAL MONTE CARLO)
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Interfaz Streamlit del modelo Monte Carlo de aceptacion sensorial: un slider de
"Calidad de Preparacion en Cocina", tarjetas de KPI (tasa de aceptacion global con IC
95% y puntaje por descriptor) y dos graficos cientificos (puntaje por descriptor +
analisis de sensibilidad del Sabor). NO contiene matematica: delega en
sim/sensorial_sim.py (motor Monte Carlo) y utils/charts.py (visualizacion).
"""

from __future__ import annotations

import streamlit as st

from sim import sensorial_sim as sens
from utils import charts
from views.theme import PALETA, tarjeta_kpi

# Claves de session_state usadas por esta pestania (persistencia multivariable, req. 7).
K_CALIDAD = "sens_calidad"
K_ITERS = "sens_iters"
K_RESULT = "sens_result"   # SensorialAggregated


def _inicializar_estado() -> None:
    st.session_state.setdefault(K_CALIDAD, sens.SLIDER_DEFAULTS["calidad_cocina"])
    st.session_state.setdefault(K_ITERS, sens.N_ITERS_DEFAULT)


def _panel_control() -> bool:
    """Panel lateral de configuracion del experimento Monte Carlo."""
    st.markdown("#### 1 · Calidad de preparacion")
    st.slider("Calidad de Preparacion en Cocina", min_value=1, max_value=10, step=1,
              key=K_CALIDAD,
              help="Gobierna la media de las distribuciones de puntaje: a mejor "
                   "preparacion, mejores notas esperadas de los jueces.")

    st.markdown("#### 2 · Experimento Monte Carlo")
    st.select_slider("Iteraciones (eventos simulados)", options=[10, 30, 100, 500],
                     key=K_ITERS,
                     help="Cantidad de eventos simulados para promediar la aceptacion "
                          "y construir el IC 95%.")

    st.info(
        f"Se simulan **{sens.N_COMENSALES} comensales** respondiendo "
        f"**{sens.N_PREGUNTAS} preguntas** (escala hedonica {sens.ESCALA_MIN}-"
        f"{sens.ESCALA_MAX}) agrupadas en 4 descriptores: "
        f"{', '.join(sens.DESCRIPTORES)}. Un comensal *acepta* el producto si su "
        f"puntaje promedio es ≥ {sens.UMBRAL_ACEPTACION}.")

    st.markdown("")
    return st.button("►  Simular aceptacion (Monte Carlo)", type="primary", width="stretch")


def _ejecutar() -> None:
    cfg = sens.SensorialConfig(calidad_cocina=int(st.session_state[K_CALIDAD]))
    n_iter = int(st.session_state[K_ITERS])
    barra = st.progress(0.0, text=f"Corriendo {n_iter} eventos Monte Carlo...")

    def _avance(it: int, total: int) -> None:
        barra.progress(it / total, text=f"Evento {it} / {total}")

    agg = sens.correr_experimento(cfg, n_iteraciones=n_iter, progreso=_avance)
    barra.empty()
    st.session_state[K_RESULT] = agg


def _mostrar_kpis(agg: sens.SensorialAggregated) -> None:
    def ic(clave: str, dec: int = 1) -> str:
        if not agg.ic_disponible:
            return "1 iteracion · sin IC (requiere ≥2)"
        inf, sup = agg.ic(clave)
        return f"IC95% [{inf:.{dec}f} - {sup:.{dec}f}]"

    if agg.ic_disponible:
        st.caption(f"Intervalos de Confianza del 95% calculados por **{agg.etiqueta_metodo_ic}** "
                   f"sobre {agg.n_iteraciones} iteraciones.")
    else:
        st.warning("Ejecutaste **1 sola iteracion**: no se puede estimar la variabilidad. "
                   "Usá 10, 30, 100 o 500 iteraciones para el IC 95%.")

    tasa = agg.media("tasa_aceptacion")
    color_tasa = (PALETA["verde"] if tasa >= 80 else
                  PALETA["ambar"] if tasa >= 60 else PALETA["rojo"])
    fila1 = st.columns(2)
    tarjeta_kpi(fila1[0], "Tasa de Aceptacion Global",
                f"{tasa:.1f} %", ic("tasa_aceptacion"), color_tasa,
                "▲" if tasa >= 60 else "▼")
    tarjeta_kpi(fila1[1], "Puntaje global medio",
                f"{agg.media('puntaje_global'):.2f} / 9", ic("puntaje_global", 2),
                PALETA["verde"], "★")

    fila2 = st.columns(4)
    for col, d in zip(fila2, sens.DESCRIPTORES):
        valor = agg.media_descriptor(d)
        color = PALETA["verde"] if valor >= sens.UMBRAL_ACEPTACION else PALETA["ambar"]
        tarjeta_kpi(col, d, f"{valor:.2f}", ic(f"desc_{d}", 2), color, "◍")


def render() -> None:
    """Punto de entrada de la Pestania 3, invocado desde main.py."""
    _inicializar_estado()
    st.markdown(
        "<div class='bloque-titulo'><h1>Aceptacion Sensorial (Monte Carlo)</h1>"
        "<p>Simulacion estocastica de la prueba afectiva/descriptiva: 50 jueces, "
        "24 preguntas, 4 descriptores y analisis de sensibilidad del Sabor.</p></div>",
        unsafe_allow_html=True)

    col_ctrl, col_res = st.columns([1, 2.4], gap="large")
    with col_ctrl:
        ejecutar = _panel_control()
    if ejecutar:
        with col_res:
            _ejecutar()

    with col_res:
        if K_RESULT not in st.session_state:
            st.info("Ajustá la calidad de preparacion y ejecutá la simulacion Monte Carlo.")
            return
        agg = st.session_state[K_RESULT]
        cfg = agg.config
        st.subheader(
            f"Resultados · Calidad de cocina {cfg.calidad_cocina}/10 · "
            f"{agg.n_iteraciones} iteraciones")
        _mostrar_kpis(agg)
        st.markdown("")
        st.markdown("##### Visualizacion cientifica")
        st.pyplot(charts.figura_descriptores(agg, figsize=(8.0, 3.2)), width="stretch")
        st.pyplot(charts.figura_sensibilidad(agg, figsize=(8.0, 3.2)), width="stretch")
        with st.expander("Diagnostico sensorial y recomendaciones", expanded=True):
            st.code(sens.generar_diagnostico(agg), language=None)
