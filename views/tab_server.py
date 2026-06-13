# -*- coding: utf-8 -*-
"""
================================================================================
 views/tab_server.py  ::  VISTA WEB - PESTANIA 1 (INFRAESTRUCTURA WEB & CONCURRENCIA)
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Interfaz Streamlit del estres de servidor: panel de sliders parametricos con presets
de escenario (incluido el Preset OFICIAL "Caso Real: Stand Facultad"), tarjetas de KPI
con Intervalos de Confianza del 95% y los graficos interactivos de Plotly (curva
temporal de conexiones + boxplot de Encuestas Perdidas). NO contiene matematica:
delega en sim/server_sim.py (motor) y utils/charts.py (visualizacion).
"""

from __future__ import annotations

import streamlit as st

from sim import server_sim as srv
from sim.estadistica import validar_generador_arribos
from utils import charts
from views.theme import PALETA, bloque_validacion, sub_seccion, tarjeta_kpi

# Claves de session_state usadas por esta pestania.
K_PRESET = "srv_preset"
K_COMENSALES = "srv_comensales"
K_POOL = "srv_pool"
K_LAT = "srv_lat"
K_REPLICAS = "srv_replicas"
K_RESULT = "srv_result"   # (AggregatedResult, ScenarioConfig)

# Presets contrafacticos (el Caso Real se ofrece aparte, como preset oficial).
PRESETS_CONTRAFACTICOS = ("Optimista", "Esperado", "Pesimista")


def _inicializar_estado() -> None:
    """Carga los valores por defecto de los sliders (preset oficial Caso Real) una vez."""
    st.session_state.setdefault(K_PRESET, srv.PRESET_CASO_REAL)
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


def _panel_control() -> bool:
    """Dibuja el panel lateral de configuracion parametrica (presets + sliders)."""
    sub_seccion("1 · Preset de escenario")
    st.caption("El **Caso Real** reproduce los registros del stand; los demás son "
               "contrafácticos (mismos 64 comensales bajo otras condiciones de red).")
    if st.button("🎯  Caso Real: Stand Facultad", width="stretch"):
        _aplicar_preset(srv.PRESET_CASO_REAL)
    cols = st.columns(3)
    for col, nombre in zip(cols, PRESETS_CONTRAFACTICOS):
        if col.button(nombre, width="stretch"):
            _aplicar_preset(nombre)

    preset = st.session_state[K_PRESET]
    st.info(f"**{preset}** · {srv.PRESETS[preset].descripcion}")

    sub_seccion("2 · Parámetros dinámicos")
    st.slider("Comensales virtuales", min_value=10, max_value=150, step=1, key=K_COMENSALES,
              help="Jueces que envían la encuesta (entidades del modelo). El Caso Real "
                   "registró 64 comensales en el stand.")
    st.slider("Límite del pool de Supabase", min_value=10, max_value=200, step=1, key=K_POOL,
              help="Conexiones simultáneas que admite el Connection Pooler (hardware).")
    st.slider("Latencia media de red (ms)", min_value=50, max_value=5000, step=10, key=K_LAT,
              help="Media de la Normal de respuesta cloud. 250 ms = red del campus (Caso Real).")

    sub_seccion("3 · Rigor estadístico")
    st.select_slider(
        "Réplicas (corridas del experimento)", options=[1, 10, 30, 50], key=K_REPLICAS,
        help="Repeticiones independientes para promediar KPIs y calcular el IC 95%.")

    st.markdown("")
    return st.button("►  Ejecutar simulación", type="primary", width="stretch")


def _ejecutar() -> None:
    """Construye el config desde los sliders y corre el experimento con barra de progreso."""
    cfg = srv.construir_config(
        preset=st.session_state[K_PRESET],
        n_comensales=st.session_state[K_COMENSALES],
        pool_capacity=st.session_state[K_POOL],
        latencia_ms=st.session_state[K_LAT],
    )
    n_rep = int(st.session_state[K_REPLICAS])
    barra = st.progress(0.0, text=f"Corriendo {n_rep} réplica/s de '{cfg.nombre}'...")

    def _avance(rep: int, total: int) -> None:
        barra.progress(rep / total, text=f"Réplica {rep} / {total}")

    agg = srv.correr_experimento(cfg, n_replicas=n_rep, progreso=_avance)
    barra.empty()
    st.session_state[K_RESULT] = (agg, cfg)


def _mostrar_kpis(agg: srv.AggregatedResult, cfg: srv.ScenarioConfig) -> None:
    """Tarjetas de KPI con el formato riguroso 'Promedio [Lim.Inf - Lim.Sup]'."""
    def ic(clave: str, dec: int = 1) -> str:
        # Con 1 sola corrida NO hay dispersion estimable: se oculta el IC (req. 1).
        if not agg.ic_disponible:
            return "1 corrida · sin IC (requiere ≥2)"
        inf, sup = agg.ic(clave)
        return f"IC95% [{inf:.{dec}f} - {sup:.{dec}f}]"

    if agg.ic_disponible:
        st.caption(f"Intervalos de Confianza del 95% calculados por **{agg.etiqueta_metodo_ic}** "
                   f"sobre {agg.n_replicas} réplicas.")
    else:
        st.warning("Ejecutaste **1 sola réplica**: no es posible estimar la variabilidad "
                   "ni construir Intervalos de Confianza. Usá 10, 30 o 50 réplicas para "
                   "el análisis estadístico (t-Student / Normal).")

    tasa = 100.0 * agg.media("exitos") / cfg.n_comensales if cfg.n_comensales else 0.0
    fila1 = st.columns(3)
    tarjeta_kpi(fila1[0], "Encuestas guardadas",
                f"{agg.media('exitos'):.0f} / {cfg.n_comensales}",
                f"Tasa de éxito {tasa:.1f}%", PALETA["verde"], "✓")
    tarjeta_kpi(fila1[1], "Errores 504 / caídas",
                f"{agg.media('total_504'):.1f}", ic("total_504"), PALETA["rojo"], "✕")
    tarjeta_kpi(fila1[2], "Encuestas perdidas",
                f"{agg.media('encuestas_perdidas'):.1f}", ic("encuestas_perdidas"),
                PALETA["ambar"], "▼")

    fila2 = st.columns(3)
    tarjeta_kpi(fila2[0], "Espera prom. en cola",
                f"{agg.media('espera_cola_promedio'):.2f} s",
                ic("espera_cola_promedio", 2), PALETA["slate"], "◔")
    tarjeta_kpi(fila2[1], "Tamaño máx. cola BD",
                f"{agg.media('max_cola'):.1f}", ic("max_cola"), PALETA["slate"], "▤")
    tarjeta_kpi(fila2[2], f"Pico conexiones / {cfg.pool_capacity}",
                f"{agg.media('pico_conexiones'):.0f}", ic("pico_conexiones"),
                PALETA["verde"], "▲")


def _mostrar_graficos(agg: srv.AggregatedResult) -> None:
    """Doble grafico interactivo: curva de conexiones + boxplot de Encuestas Perdidas."""
    sub_seccion("Visualización interactiva")
    st.caption("Zoom con scroll, paneo arrastrando y clic en la leyenda para ocultar curvas.")
    st.plotly_chart(charts.figura_conexiones(agg), width="stretch")
    st.plotly_chart(charts.figura_boxplot(agg), width="stretch")


def render() -> None:
    """Punto de entrada de la Pestania 1, invocado desde main.py."""
    _inicializar_estado()
    st.markdown(
        "<div class='bloque-titulo'><h1>Infraestructura Web &amp; Concurrencia</h1>"
        "<p>Estrés del Connection Pooler de Supabase frente a la ráfaga de 64 comensales "
        "del stand (conexión directa Client-to-Cloud, plan gratuito).</p></div>",
        unsafe_allow_html=True)

    col_ctrl, col_res = st.columns([1, 2.4], gap="large")
    with col_ctrl:
        ejecutar = _panel_control()
    if ejecutar:
        with col_res:
            _ejecutar()

    with col_res:
        if K_RESULT not in st.session_state:
            st.info("Configurá un escenario en el panel izquierdo y ejecutá la simulación.")
            return
        agg, cfg = st.session_state[K_RESULT]
        st.subheader(f"Resultados · Escenario {agg.escenario}  ·  {agg.n_replicas} réplica/s")
        _mostrar_kpis(agg, cfg)
        st.divider()
        _mostrar_graficos(agg)
        with st.expander("📋 Diagnóstico y recomendaciones", expanded=True):
            st.code(srv.generar_diagnostico(agg, cfg), language=None)

        # Validacion y Verificacion del generador de arribos (req. 5).
        validacion = validar_generador_arribos(
            agg.interarribos, cfg.tasa_arribo_media, unidad="s")
        bloque_validacion(validacion)
