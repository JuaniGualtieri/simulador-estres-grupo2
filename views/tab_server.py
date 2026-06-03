# -*- coding: utf-8 -*-
"""
================================================================================
 views/tab_server.py  ::  VISTA WEB - PESTANIA 1 (INFRAESTRUCTURA WEB & CONCURRENCIA)
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Interfaz Streamlit del estres de servidor: panel de sliders parametricos con presets
de escenario, tarjetas de KPI con Intervalos de Confianza del 95% y el doble grafico
(curva temporal de conexiones + boxplot de Encuestas Perdidas). NO contiene matematica:
delega en sim/server_sim.py (motor) y utils/charts.py (visualizacion).
"""

from __future__ import annotations

import streamlit as st

from sim import server_sim as srv
from utils import charts
from views.theme import PALETA, tarjeta_kpi

# Claves de session_state usadas por esta pestania.
K_PRESET = "srv_preset"
K_COMENSALES = "srv_comensales"
K_POOL = "srv_pool"
K_LAT = "srv_lat"
K_REPLICAS = "srv_replicas"
K_RESULT = "srv_result"   # (AggregatedResult, ScenarioConfig)


def _inicializar_estado() -> None:
    """Carga los valores por defecto de los sliders (preset Esperado) una sola vez."""
    st.session_state.setdefault(K_PRESET, "Esperado")
    st.session_state.setdefault(K_COMENSALES, srv.SLIDER_DEFAULTS["n_comensales"])
    st.session_state.setdefault(K_POOL, srv.SLIDER_DEFAULTS["pool_capacity"])
    st.session_state.setdefault(K_LAT, srv.SLIDER_DEFAULTS["latencia_ms"])
    st.session_state.setdefault(K_REPLICAS, srv.N_REPLICAS_DEFAULT)


def _aplicar_preset(nombre: str) -> None:
    """Reubica los sliders en la configuracion logica del preset seleccionado."""
    base = srv.PRESETS[nombre]
    st.session_state[K_PRESET] = nombre
    st.session_state[K_COMENSALES] = base.n_comensales
    st.session_state[K_POOL] = base.pool_capacity
    st.session_state[K_LAT] = int(round(base.latencia_media * 1000))


def _panel_control() -> None:
    """Dibuja el panel lateral de configuracion parametrica (presets + sliders)."""
    st.markdown("#### 1 · Preset de escenario")
    st.caption("Reubica los sliders en una configuracion logica; luego ajustalos a mano.")
    c1, c2, c3 = st.columns(3)
    if c1.button("Optimista", width="stretch"):
        _aplicar_preset("Optimista")
    if c2.button("Esperado", width="stretch"):
        _aplicar_preset("Esperado")
    if c3.button("Pesimista", width="stretch"):
        _aplicar_preset("Pesimista")

    preset = st.session_state[K_PRESET]
    st.info(f"**{preset}** · {srv.PRESETS[preset].descripcion}")

    st.markdown("#### 2 · Parametros dinamicos")
    st.slider("Comensales virtuales", min_value=10, max_value=150, step=1, key=K_COMENSALES,
              help="Cantidad de jueces que envian la encuesta (entidades del modelo).")
    st.slider("Limite del pool de Supabase", min_value=10, max_value=200, step=1, key=K_POOL,
              help="Conexiones simultaneas que admite el Connection Pooler (hardware).")
    st.slider("Latencia media de red (ms)", min_value=50, max_value=5000, step=10, key=K_LAT,
              help="Media de la Normal de respuesta cloud. 250 ms = Escenario Esperado.")

    st.markdown("#### 3 · Rigor estadistico")
    st.select_slider(
        "Replicas (corridas del experimento)", options=[1, 10, 30, 50], key=K_REPLICAS,
        help="Repeticiones independientes para promediar KPIs y calcular el IC 95%.")

    st.markdown("")
    return st.button("►  Ejecutar simulacion", type="primary", width="stretch")


def _ejecutar() -> None:
    """Construye el config desde los sliders y corre el experimento con barra de progreso."""
    cfg = srv.construir_config(
        preset=st.session_state[K_PRESET],
        n_comensales=st.session_state[K_COMENSALES],
        pool_capacity=st.session_state[K_POOL],
        latencia_ms=st.session_state[K_LAT],
    )
    n_rep = int(st.session_state[K_REPLICAS])
    barra = st.progress(0.0, text=f"Corriendo {n_rep} replica/s de '{cfg.nombre}'...")

    def _avance(rep: int, total: int) -> None:
        barra.progress(rep / total, text=f"Replica {rep} / {total}")

    agg = srv.correr_experimento(cfg, n_replicas=n_rep, progreso=_avance)
    barra.empty()
    st.session_state[K_RESULT] = (agg, cfg)


def _mostrar_kpis(agg: srv.AggregatedResult, cfg: srv.ScenarioConfig) -> None:
    """Tarjetas de KPI con el formato riguroso 'Promedio [Lim.Inf - Lim.Sup]'."""
    def ic(clave: str, dec: int = 1) -> str:
        inf, sup = agg.ic(clave)
        return f"IC95% [{inf:.{dec}f} - {sup:.{dec}f}]"

    tasa = 100.0 * agg.media("exitos") / cfg.n_comensales if cfg.n_comensales else 0.0
    fila1 = st.columns(3)
    tarjeta_kpi(fila1[0], "Encuestas guardadas",
                f"{agg.media('exitos'):.0f} / {cfg.n_comensales}",
                f"Tasa de exito {tasa:.1f}%", PALETA["verde"], "✓")
    tarjeta_kpi(fila1[1], "Errores 504 / caidas",
                f"{agg.media('total_504'):.1f}", ic("total_504"), PALETA["rojo"], "✕")
    tarjeta_kpi(fila1[2], "Encuestas perdidas",
                f"{agg.media('encuestas_perdidas'):.1f}", ic("encuestas_perdidas"),
                PALETA["ambar"], "▼")

    fila2 = st.columns(3)
    tarjeta_kpi(fila2[0], "Espera prom. en cola",
                f"{agg.media('espera_cola_promedio'):.2f} s",
                ic("espera_cola_promedio", 2), PALETA["txt_suave"], "◔")
    tarjeta_kpi(fila2[1], "Tamanio max. cola BD",
                f"{agg.media('max_cola'):.1f}", ic("max_cola"), PALETA["txt_suave"], "▤")
    tarjeta_kpi(fila2[2], f"Pico conexiones / {cfg.pool_capacity}",
                f"{agg.media('pico_conexiones'):.0f}", ic("pico_conexiones"),
                PALETA["verde"], "▲")


def _mostrar_graficos(agg: srv.AggregatedResult) -> None:
    """Doble grafico cientifico: curva de conexiones (arriba) + boxplot (abajo)."""
    st.markdown("##### Visualizacion cientifica")
    st.pyplot(charts.figura_conexiones(agg, figsize=(8.0, 3.6)), width="stretch")
    st.pyplot(charts.figura_boxplot(agg, figsize=(8.0, 2.8)), width="stretch")


def render() -> None:
    """Punto de entrada de la Pestania 1, invocado desde main.py."""
    _inicializar_estado()
    st.markdown(
        "<div class='bloque-titulo'><h1>Infraestructura Web &amp; Concurrencia</h1>"
        "<p>Estres del Connection Pooler de Supabase frente a la rafaga de comensales "
        "(conexion directa Client-to-Cloud, plan gratuito).</p></div>",
        unsafe_allow_html=True)

    col_ctrl, col_res = st.columns([1, 2.4], gap="large")
    with col_ctrl:
        ejecutar = _panel_control()
    if ejecutar:
        with col_res:
            _ejecutar()

    with col_res:
        if K_RESULT not in st.session_state:
            st.info("Configura un escenario en el panel izquierdo y ejecuta la simulacion.")
            return
        agg, cfg = st.session_state[K_RESULT]
        st.subheader(f"Resultados · Escenario {agg.escenario}  ·  {agg.n_replicas} replica/s")
        _mostrar_kpis(agg, cfg)
        st.markdown("")
        _mostrar_graficos(agg)
        with st.expander("Diagnostico y recomendaciones", expanded=True):
            st.code(srv.generar_diagnostico(agg, cfg), language=None)
