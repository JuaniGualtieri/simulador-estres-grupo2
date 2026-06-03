# -*- coding: utf-8 -*-
"""
================================================================================
 views/tab_production.py  ::  VISTA WEB - PESTANIA 2 (CADENA DE PRODUCCION & STOCK)
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Interfaz Streamlit de la cadena de produccion de tartaletas: sliders de operarios y
capacidad del horno, tarjetas de KPI de stock y el grafico de evolucion del nivel de
stock (con zona roja de faltante). NO contiene matematica: delega en
sim/production_sim.py (motor) y utils/charts.py (visualizacion).
"""

from __future__ import annotations

import streamlit as st

from sim import production_sim as prod
from utils import charts
from views.theme import PALETA, tarjeta_kpi

# Claves de session_state usadas por esta pestania.
K_OPERARIOS = "prod_operarios"
K_HORNO = "prod_horno"
K_REPLICAS = "prod_replicas"
K_RESULT = "prod_result"   # ProductionAggregated


def _inicializar_estado() -> None:
    st.session_state.setdefault(K_OPERARIOS, prod.SLIDER_DEFAULTS["operarios"])
    st.session_state.setdefault(K_HORNO, prod.SLIDER_DEFAULTS["horno"])
    st.session_state.setdefault(K_REPLICAS, prod.N_REPLICAS_DEFAULT)


def _panel_control() -> bool:
    """Panel lateral de configuracion de la cadena de produccion."""
    st.markdown("#### 1 · Recursos de cocina")
    st.slider("Cantidad de operarios", min_value=1, max_value=5, step=1, key=K_OPERARIOS,
              help="Operarios para la Etapa 1 (masa/relleno) y la Etapa 3 (ensamblado).")
    st.slider("Capacidad del horno (lotes simultaneos)", min_value=1, max_value=4, step=1,
              key=K_HORNO, help="Ranuras/bandejas que el horno puede cocinar en paralelo.")

    st.markdown("#### 2 · Experimento")
    st.select_slider("Replicas (corridas del experimento)", options=[1, 10, 20, 30],
                     key=K_REPLICAS,
                     help="Repeticiones independientes para promediar los KPIs de stock.")

    st.info(
        f"Cada lote rinde **{prod.TARTALETAS_POR_LOTE}** tartaletas. "
        f"Etapa 1: Normal({prod.MASA_MEDIA:.0f}, {prod.MASA_DESVIO:.0f}) min · "
        f"Etapa 2: horno fijo {prod.HORNEADO_FIJO:.0f} min · "
        f"Etapa 3: Uniforme[{prod.ENSAMBLE_MIN:.0f}-{prod.ENSAMBLE_MAX:.0f}] min. "
        f"Consumo: {prod.N_COMENSALES} comensales (arribos exponenciales en "
        f"{prod.VENTANA_ARRIBOS_MIN:.0f} min, igual que la Pestania 1).")

    st.markdown("")
    return st.button("►  Simular produccion", type="primary", width="stretch")


def _ejecutar() -> None:
    cfg = prod.ProductionConfig(
        operarios=int(st.session_state[K_OPERARIOS]),
        horno_slots=int(st.session_state[K_HORNO]),
    )
    n_rep = int(st.session_state[K_REPLICAS])
    barra = st.progress(0.0, text=f"Simulando {n_rep} jornada/s de produccion...")

    def _avance(rep: int, total: int) -> None:
        barra.progress(rep / total, text=f"Replica {rep} / {total}")

    agg = prod.correr_experimento(cfg, n_replicas=n_rep, progreso=_avance)
    barra.empty()
    st.session_state[K_RESULT] = agg


def _mostrar_kpis(agg: prod.ProductionAggregated) -> None:
    fila1 = st.columns(2)
    tarjeta_kpi(fila1[0], "Tartaletas producidas",
                f"{agg.media('tartaletas_producidas'):.0f}",
                f"{agg.media('lotes_producidos'):.1f} lotes", PALETA["verde"], "▣")
    tarjeta_kpi(fila1[1], "Tiempo prom. fabricacion lote",
                f"{agg.media('tiempo_fab_promedio'):.1f} min",
                "Etapas 1+2+3", PALETA["txt_suave"], "◔")

    fila2 = st.columns(2)
    color_espera = PALETA["rojo"] if agg.media("espera_maxima") > 5 else PALETA["ambar"]
    tarjeta_kpi(fila2[0], "Espera maxima por alimento",
                f"{agg.media('espera_maxima'):.1f} min",
                f"{agg.media('comensales_en_espera'):.0f} comensales esperaron",
                color_espera, "▼")
    tarjeta_kpi(fila2[1], "Stock remanente al cierre",
                f"{agg.media('stock_remanente'):.0f}", "tartaletas en mostrador",
                PALETA["verde"], "▲")


def render() -> None:
    """Punto de entrada de la Pestania 2, invocado desde main.py."""
    _inicializar_estado()
    st.markdown(
        "<div class='bloque-titulo'><h1>Cadena de Produccion &amp; Abastecimiento</h1>"
        "<p>Fabricacion de tartaletas en la cocina de la Planta Piloto: tasa de "
        "produccion contra ritmo de consumo de los comensales.</p></div>",
        unsafe_allow_html=True)

    col_ctrl, col_res = st.columns([1, 2.4], gap="large")
    with col_ctrl:
        ejecutar = _panel_control()
    if ejecutar:
        with col_res:
            _ejecutar()

    with col_res:
        if K_RESULT not in st.session_state:
            st.info("Configura los recursos de cocina y ejecuta la simulacion de produccion.")
            return
        agg = st.session_state[K_RESULT]
        cfg = agg.config
        st.subheader(
            f"Resultados · {cfg.operarios} operario/s · horno x{cfg.horno_slots} · "
            f"{agg.n_replicas} replica/s")
        _mostrar_kpis(agg)
        st.markdown("")
        st.markdown("##### Evolucion temporal del stock")
        st.pyplot(charts.figura_stock(agg, figsize=(8.0, 3.8)), width="stretch")
        with st.expander("Diagnostico de viabilidad organizacional", expanded=True):
            st.code(prod.generar_diagnostico(agg), language=None)
