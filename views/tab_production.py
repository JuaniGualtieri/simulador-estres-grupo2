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
from sim.estadistica import validar_generador_arribos
from utils import charts
from views.theme import PALETA, bloque_validacion, tarjeta_kpi

# Claves de session_state usadas por esta pestania (persistencia multivariable, req. 7).
K_OPERARIOS = "prod_operarios"
K_HORNO = "prod_horno"
K_REPLICAS = "prod_replicas"
K_COSTO_MP = "prod_costo_mp"
K_PRECIO = "prod_precio"
K_COSTO_OP = "prod_costo_op"
K_INVERSION = "prod_inversion"
K_RESULT = "prod_result"   # ProductionAggregated


def _inicializar_estado() -> None:
    st.session_state.setdefault(K_OPERARIOS, prod.SLIDER_DEFAULTS["operarios"])
    st.session_state.setdefault(K_HORNO, prod.SLIDER_DEFAULTS["horno"])
    st.session_state.setdefault(K_REPLICAS, prod.N_REPLICAS_DEFAULT)
    st.session_state.setdefault(K_COSTO_MP, prod.SLIDER_DEFAULTS["costo_mp_lote"])
    st.session_state.setdefault(K_PRECIO, prod.SLIDER_DEFAULTS["precio_venta"])
    st.session_state.setdefault(K_COSTO_OP, prod.SLIDER_DEFAULTS["costo_operario"])
    st.session_state.setdefault(K_INVERSION, prod.SLIDER_DEFAULTS["inversion_inicial"])


def _panel_control() -> bool:
    """Panel lateral de configuracion de la cadena de produccion."""
    st.markdown("#### 1 · Recursos de cocina")
    st.slider("Cantidad de operarios", min_value=1, max_value=5, step=1, key=K_OPERARIOS,
              help="Operarios para la Etapa 1 (masa/relleno) y la Etapa 3 (ensamblado).")
    st.slider("Capacidad del horno (lotes simultaneos)", min_value=1, max_value=4, step=1,
              key=K_HORNO, help="Ranuras/bandejas que el horno puede cocinar en paralelo.")

    st.markdown("#### 2 · Parametros economicos (escenario de venta)")
    st.caption("Modela el emprendimiento: rentabilidad por jornada y recupero de inversion.")
    st.number_input("Costo materia prima por lote ($)", min_value=0.0, step=500.0,
                    key=K_COSTO_MP, format="%.0f",
                    help="Pollo, poroto alubia, masa integral y vegetales por bandeja.")
    st.number_input("Precio de venta por tartaleta ($)", min_value=0.0, step=100.0,
                    key=K_PRECIO, format="%.0f",
                    help="Precio sugerido al publico por unidad.")
    st.number_input("Costo por operario / jornada ($)", min_value=0.0, step=1000.0,
                    key=K_COSTO_OP, format="%.0f",
                    help="Costo fijo de mano de obra por operario y por jornada.")
    st.number_input("Inversion inicial en equipamiento ($)", min_value=0.0, step=10000.0,
                    key=K_INVERSION, format="%.0f",
                    help="Horno, mesada y utensilios (se recupera con la rentabilidad).")

    st.markdown("#### 3 · Experimento")
    st.select_slider("Replicas (corridas del experimento)", options=[1, 10, 20, 30],
                     key=K_REPLICAS,
                     help="Repeticiones independientes para promediar los KPIs con IC 95%.")

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
        costo_mp_lote=float(st.session_state[K_COSTO_MP]),
        precio_venta_unidad=float(st.session_state[K_PRECIO]),
        costo_operario_jornada=float(st.session_state[K_COSTO_OP]),
        inversion_inicial=float(st.session_state[K_INVERSION]),
    )
    n_rep = int(st.session_state[K_REPLICAS])
    barra = st.progress(0.0, text=f"Simulando {n_rep} jornada/s de produccion...")

    def _avance(rep: int, total: int) -> None:
        barra.progress(rep / total, text=f"Replica {rep} / {total}")

    agg = prod.correr_experimento(cfg, n_replicas=n_rep, progreso=_avance)
    barra.empty()
    st.session_state[K_RESULT] = agg


def _mostrar_kpis(agg: prod.ProductionAggregated) -> None:
    def ic(clave: str, dec: int = 1) -> str:
        # Formato cientifico unificado con la Pestania 1 (req. 2): 'media [inf - sup]'.
        if not agg.ic_disponible:
            return "1 corrida · sin IC (requiere ≥2)"
        inf, sup = agg.ic(clave)
        return f"IC95% [{inf:.{dec}f} - {sup:.{dec}f}]"

    if agg.ic_disponible:
        st.caption(f"Intervalos de Confianza del 95% calculados por **{agg.etiqueta_metodo_ic}** "
                   f"sobre {agg.n_replicas} réplicas.")
    else:
        st.warning("Ejecutaste **1 sola réplica**: no se puede estimar la variabilidad "
                   "ni construir Intervalos de Confianza. Usá 10, 20 o 30 réplicas.")

    fila1 = st.columns(2)
    tarjeta_kpi(fila1[0], "Tartaletas producidas",
                f"{agg.media('tartaletas_producidas'):.0f}",
                ic("tartaletas_producidas"), PALETA["verde"], "▣")
    tarjeta_kpi(fila1[1], "Tiempo prom. fabricacion lote",
                f"{agg.media('tiempo_fab_promedio'):.1f} min",
                ic("tiempo_fab_promedio"), PALETA["txt_suave"], "◔")

    fila2 = st.columns(2)
    color_espera = PALETA["rojo"] if agg.media("espera_maxima") > 5 else PALETA["ambar"]
    tarjeta_kpi(fila2[0], "Espera maxima por alimento",
                f"{agg.media('espera_maxima'):.1f} min",
                ic("espera_maxima"), color_espera, "▼")
    tarjeta_kpi(fila2[1], "Stock remanente al cierre",
                f"{agg.media('stock_remanente'):.0f}", ic("stock_remanente"),
                PALETA["verde"], "▲")

    # --- KPIs economico-financieros (req. 3) ---
    st.markdown("##### Viabilidad economica (escenario de venta)")
    fila3 = st.columns(2)
    rent = agg.media("rentabilidad")
    color_rent = PALETA["verde"] if rent > 0 else PALETA["rojo"]
    tarjeta_kpi(fila3[0], "Rentabilidad proyectada / jornada",
                f"$ {rent:,.0f}", ic("rentabilidad", 0), color_rent,
                "▲" if rent > 0 else "▼")
    payback = agg.payback_jornadas
    if payback == float("inf"):
        valor_pb, sub_pb, color_pb = "No recupera", "jornada no rentable", PALETA["rojo"]
    else:
        valor_pb = f"{payback:.1f} jornadas"
        sub_pb = f"para recuperar $ {agg.config.inversion_inicial:,.0f}"
        color_pb = PALETA["ambar"]
    tarjeta_kpi(fila3[1], "Recupero de inversion (payback)",
                valor_pb, sub_pb, color_pb, "◷")


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

        # Validacion y Verificacion del generador de arribos (req. 5).
        validacion = validar_generador_arribos(
            agg.interarribos, cfg.tasa_arribo_media, unidad="min")
        bloque_validacion(validacion)
