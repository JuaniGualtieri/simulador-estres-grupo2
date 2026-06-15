# -*- coding: utf-8 -*-
"""
================================================================================
 views/tab_sensorial.py  ::  VISTA WEB - PESTANIA 3 (ACEPTACION SENSORIAL MONTE CARLO)
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Interfaz Streamlit del modelo Monte Carlo de aceptacion sensorial alineado con la
NUEVA ENCUESTA REAL de 12 preguntas (8 sliders 1-10, 2 preguntas Si/No y 2 campos
demograficos). Ofrece: un slider de "Calidad de Preparacion en Cocina", tarjetas de
KPI (tasa de aceptacion global con IC 95% y % de "Si"), panel demografico, perfil de
los 8 atributos (radar), barras Si/No 100% apiladas, comentarios simulados y analisis
de sensibilidad del Sabor. NO contiene matematica: delega en sim/sensorial_sim.py y
utils/charts.py (graficos Plotly interactivos).
"""

from __future__ import annotations

import streamlit as st

from sim import sensorial_sim as sens
from utils import charts
from views.theme import PALETA, sub_seccion, tarjeta_kpi

# Claves de session_state usadas por esta pestania (persistencia multivariable, req. 7).
K_CALIDAD = "sens_calidad"
K_ITERS = "sens_iters"
K_RESULT = "sens_result"   # SensorialAggregated


def _inicializar_estado() -> None:
    st.session_state.setdefault(K_CALIDAD, sens.SLIDER_DEFAULTS["calidad_cocina"])
    st.session_state.setdefault(K_ITERS, sens.N_ITERS_DEFAULT)


def _panel_control() -> bool:
    """Panel lateral de configuracion del experimento Monte Carlo."""
    sub_seccion("1 · Calidad de preparación")
    st.slider("Calidad de Preparación en Cocina", min_value=1, max_value=10, step=1,
              key=K_CALIDAD,
              help="Gobierna la media de las distribuciones de cada atributo: a mejor "
                   "preparación, mejores notas y más respuestas 'Sí' esperadas.")

    sub_seccion("2 · Experimento")
    st.select_slider("Cantidad de experimentos", options=[10, 20, 30, 40, 50],
                     key=K_ITERS,
                     help="Cantidad de experimentos simulados para promediar la aceptación "
                          "y construir el IC 95%.")

    st.info(
        f"Se simulan **{sens.N_COMENSALES} comensales** respondiendo la encuesta real de "
        f"**{sens.N_PREGUNTAS_TOTAL} preguntas**: 8 escalas 1-10, 2 preguntas Sí/No y los "
        f"datos demográficos (año de nacimiento y sexo), en 5 dimensiones sensoriales "
        f"(Vista, Olfato, Tacto y Oído, Gusto y Boca, Sabor). Un comensal *acepta* el "
        f"producto si su **sabor general** es ≥ {sens.UMBRAL_ACEPTACION}.")

    st.markdown("")
    return st.button("►  Simular aceptación sensorial", type="primary", width="stretch")


def _ejecutar() -> None:
    cfg = sens.SensorialConfig(calidad_cocina=int(st.session_state[K_CALIDAD]))
    n_iter = int(st.session_state[K_ITERS])
    barra = st.progress(0.0, text=f"Corriendo {n_iter} experimentos...")

    def _avance(it: int, total: int) -> None:
        barra.progress(it / total, text=f"Experimento {it} / {total}")

    agg = sens.correr_experimento(cfg, n_iteraciones=n_iter, progreso=_avance)
    barra.empty()
    st.session_state[K_RESULT] = agg


def _mostrar_kpis(agg: sens.SensorialAggregated) -> None:
    def ic(clave: str, dec: int = 1) -> str:
        if not agg.ic_disponible:
            return "1 experimento · sin IC (requiere ≥2)"
        inf, sup = agg.ic(clave)
        return f"IC95% [{inf:.{dec}f} - {sup:.{dec}f}]"

    if agg.ic_disponible:
        st.caption(f"Intervalos de Confianza del 95% calculados por **{agg.etiqueta_metodo_ic}** "
                   f"sobre {agg.n_iteraciones} experimentos.")
    else:
        st.warning("Ejecutaste **1 solo experimento**: no se puede estimar la variabilidad. "
                   "Usá 10, 20, 30, 40 o 50 experimentos para el IC 95%.")

    tasa = agg.media("tasa_aceptacion")
    color_tasa = (PALETA["verde"] if tasa >= 80 else
                  PALETA["ambar"] if tasa >= 60 else PALETA["rojo"])
    fila1 = st.columns(2)
    tarjeta_kpi(fila1[0], "Tasa de Aceptación Global",
                f"{tasa:.1f} %", ic("tasa_aceptacion"), color_tasa,
                "▲" if tasa >= 60 else "▼")
    tarjeta_kpi(fila1[1], "Puntaje global medio",
                f"{agg.media('puntaje_global'):.2f} / 10", ic("puntaje_global", 2),
                PALETA["verde"], "★")

    # Las dos preguntas dicotomicas como KPI de % de "Si".
    fila2 = st.columns(2)
    for col, b in zip(fila2, sens.ATRIBUTOS_BOOL):
        valor = agg.prop_si(b)
        color = PALETA["verde"] if valor >= 50 else PALETA["ambar"]
        tarjeta_kpi(col, sens.ETIQUETAS[b], f"{valor:.0f} % Sí",
                    ic(f"prop_{b}"), color, "◍")


def _mostrar_demografia(agg: sens.SensorialAggregated) -> None:
    demo = sens.resumen_demografico(agg)
    sub_seccion("Perfil demográfico del panel")
    cols = st.columns(4)
    tarjeta_kpi(cols[0], "Comensales", f"{demo.n}",
                f"Edad media {demo.edad_media:.0f} años", PALETA["verde"], "👥")
    tarjeta_kpi(cols[1], "Masculino", f"{demo.pct_masculino:.0f} %",
                f"{demo.n_masculino} comensales", PALETA["slate"], "♂")
    tarjeta_kpi(cols[2], "Femenino", f"{demo.pct_femenino:.0f} %",
                f"{demo.n_femenino} comensales", PALETA["naranja"], "♀")
    tarjeta_kpi(cols[3], "Otro", f"{demo.pct_otro:.0f} %",
                f"{demo.n_otro} comensales", PALETA["verde"], "⚧")
    st.plotly_chart(charts.figura_demografia(agg), width="stretch", config=charts.CHART_CONFIG)


def _mostrar_comentarios(agg: sens.SensorialAggregated) -> None:
    comentarios = sens.comentarios_panel(agg, limite=8)
    sub_seccion("Comentarios libres simulados")
    if not comentarios:
        st.caption("Ningún comensal del panel dejó un comentario en esta corrida.")
        return
    bloques = "".join(
        f"<div style='background:{PALETA['verde_suave']};border-left:4px solid "
        f"{PALETA['verde']};border-radius:10px;padding:9px 14px;margin-bottom:8px;"
        f"font-size:0.86rem;color:{PALETA['txt']};'>“{c}”</div>"
        for c in comentarios)
    st.markdown(bloques, unsafe_allow_html=True)


def render() -> None:
    """Punto de entrada de la Pestania 3, invocado desde main.py."""
    _inicializar_estado()
    st.markdown(
        "<div class='bloque-titulo'><h1>Aceptación Sensorial</h1>"
        "<p>Simulación estocástica de la encuesta real de 12 preguntas: 64 comensales, "
        "8 escalas 1-10, 2 preguntas Sí/No, datos demográficos y análisis de "
        "sensibilidad del Sabor.</p></div>",
        unsafe_allow_html=True)

    col_ctrl, col_res = st.columns([1, 2.4], gap="large")
    with col_ctrl:
        ejecutar = _panel_control()
    if ejecutar:
        with col_res:
            _ejecutar()

    with col_res:
        if K_RESULT not in st.session_state:
            st.info("Ajustá la calidad de preparación y ejecutá la simulación sensorial.")
            return
        agg = st.session_state[K_RESULT]
        cfg = agg.config
        st.subheader(
            f"Resultados · Calidad de cocina {cfg.calidad_cocina}/10 · "
            f"{agg.n_iteraciones} experimentos")
        _mostrar_kpis(agg)
        st.divider()
        _mostrar_demografia(agg)
        st.divider()
        sub_seccion("Visualización interactiva")
        st.caption("Radar del perfil, matriz Sí/No 100% apilada y sensibilidad del Sabor "
                   "(zoom, paneo y leyenda interactiva).")
        st.plotly_chart(charts.figura_perfil(agg), width="stretch", config=charts.CHART_CONFIG)
        st.plotly_chart(charts.figura_si_no(agg), width="stretch", config=charts.CHART_CONFIG)
        st.plotly_chart(charts.figura_sensibilidad(agg), width="stretch", config=charts.CHART_CONFIG)
        st.divider()
        _mostrar_comentarios(agg)
        with st.expander("📋 Diagnóstico sensorial y recomendaciones", expanded=True):
            st.code(sens.generar_diagnostico(agg), language=None)
