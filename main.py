# -*- coding: utf-8 -*-
"""
================================================================================
 main.py  ::  PUNTO DE ENTRADA DE LA SUITE DE SIMULACION WEB (Streamlit)
 Trabajo Practico Integrador Intercatedra e Intercarrera - Grupo 2
 Universidad de la Cuenca del Plata (Sede Corrientes)
================================================================================

Aplicacion web multipestania que unifica dos modelos de Simulacion de Eventos
Discretos (SimPy) bajo una arquitectura modular (principios SOLID / Clean Code):

  * Pestania 1 - "Infraestructura Web & Concurrencia"  (views/tab_server.py)
        Estres del Connection Pooler de Supabase frente a la rafaga de comensales.
  * Pestania 2 - "Cadena de Produccion & Abastecimiento"  (views/tab_production.py)
        Fabricacion de tartaletas vs. consumo de los comensales en la Planta Piloto.

El motor matematico vive aislado en sim/ (server_sim.py, production_sim.py); la
visualizacion en utils/charts.py y el reporte formal en utils/pdf_generator.py.

USO:
    streamlit run main.py
================================================================================
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from views import tab_production, tab_sensorial, tab_server
from views.theme import PALETA, inyectar_css
from utils import pdf_generator

st.set_page_config(
    page_title="Simulador de Eventos Discretos - Grupo 2",
    page_icon="🥧",
    layout="wide",
    initial_sidebar_state="expanded",
)
inyectar_css()


def _panel_reporte() -> None:
    """Barra lateral: ficha del proyecto y compilacion/descarga del reporte PDF."""
    with st.sidebar:
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:11px;margin-bottom:2px;">
              <div style="width:38px;height:38px;border-radius:11px;flex:0 0 auto;
                   background:{PALETA['verde']};display:flex;align-items:center;
                   justify-content:center;font-size:1.2rem;
                   box-shadow:0 8px 18px -8px rgba(76,118,97,0.8);">🥧</div>
              <div style="line-height:1.15;">
                <div style="font-weight:800;font-size:1.05rem;color:{PALETA['txt']};">
                   Simulador Intercátedra</div>
                <div style="font-size:0.74rem;color:{PALETA['txt_suave']};
                   text-transform:uppercase;letter-spacing:0.5px;font-weight:600;">
                   Grupo 2 · Modelos y Simulación</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style="background:{PALETA['verde_suave']};border-radius:14px;
            padding:14px 16px;font-size:0.82rem;color:{PALETA['txt_suave']};
            border:1px solid {PALETA['borde']};margin-top:12px;
            box-shadow:0 1px 2px rgba(16,24,40,0.04);">
            <b style="color:{PALETA['verde']};">Sistema real modelado · Caso Real</b><br>
            · 64 comensales · 11/06/2026 · jornada de 83,3 min<br>
            · 60 conexiones (plan gratuito Supabase)<br>
            · 12 preguntas sensoriales (5 dimensiones, escala 1-10)<br>
            · Tandas de 8 tartaletas (relleno 30′ · masa 15′ · gratinado 10′)<br>
            · Conexión directa Client-to-Cloud
            </div>
            """,
            unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### Reporte PDF (Normas APA 7)")

        tiene_srv = tab_server.K_RESULT in st.session_state
        tiene_prod = tab_production.K_RESULT in st.session_state
        tiene_sens = tab_sensorial.K_RESULT in st.session_state

        if not (tiene_srv and tiene_prod and tiene_sens):
            faltan = []
            if not tiene_srv:
                faltan.append("Pestania 1 (servidor)")
            if not tiene_prod:
                faltan.append("Pestania 2 (produccion)")
            if not tiene_sens:
                faltan.append("Pestania 3 (sensorial)")
            st.caption("Ejecuta las tres simulaciones para habilitar el reporte bifocal. "
                       "Falta: " + ", ".join(faltan) + ".")
            return

        if st.button("Compilar reporte PDF", type="primary", width="stretch"):
            agg_srv, cfg_srv = st.session_state[tab_server.K_RESULT]
            agg_prod = st.session_state[tab_production.K_RESULT]
            agg_sens = st.session_state[tab_sensorial.K_RESULT]
            with st.spinner("Compilando reporte unificado..."):
                st.session_state["pdf_bytes"] = pdf_generator.generar_reporte_pdf(
                    agg_srv, cfg_srv, agg_prod, agg_sens)
            st.success("Reporte compilado.")

        if "pdf_bytes" in st.session_state:
            nombre = "Reporte_Simulacion_Estres_Grupo2.pdf"
            st.download_button(
                "Descargar PDF", data=st.session_state["pdf_bytes"],
                file_name=nombre, mime="application/pdf",
                width="stretch")


def main() -> None:
    st.markdown(
        "<div class='bloque-titulo'><h1>Simulador de Eventos Discretos</h1>"
        "<p>Universidad de la Cuenca del Plata · TPI Intercátedra e Intercarrera · "
        "Grupo 2 · Tartaleta vegetal sustentable (Planta Piloto, 11/06/2026)</p></div>",
        unsafe_allow_html=True)

    _panel_reporte()

    tab1, tab2, tab3 = st.tabs([
        "🌐  Infraestructura Web & Concurrencia",
        "🍳  Cadena de Produccion & Abastecimiento",
        "🥗  Aceptacion Sensorial",
    ])
    with tab1:
        tab_server.render()
    with tab2:
        tab_production.render()
    with tab3:
        tab_sensorial.render()

    st.caption(
        f"Generado por el Simulador Intercátedra · Grupo 2 · "
        f"{datetime.now().strftime('%d/%m/%Y')}")


if __name__ == "__main__":
    main()
