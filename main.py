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

from views import tab_production, tab_server
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
        st.markdown(f"### Simulador Intercátedra")
        st.caption("TPI Intercatedra · Grupo 2 · Modelos y Simulacion")
        st.markdown(
            f"""
            <div style="background:{PALETA['verde_suave']};border-radius:12px;
            padding:12px 14px;font-size:0.82rem;color:{PALETA['txt_suave']};">
            <b style="color:{PALETA['verde']};">Sistema real modelado</b><br>
            · 60 conexiones (plan gratuito Supabase)<br>
            · 24 preguntas sensoriales (escala hedonica)<br>
            · 50 comensales · 11/06/2026 · Planta Piloto<br>
            · Conexion directa Client-to-Cloud
            </div>
            """,
            unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### Reporte PDF (Normas APA 7)")

        tiene_srv = tab_server.K_RESULT in st.session_state
        tiene_prod = tab_production.K_RESULT in st.session_state

        if not (tiene_srv and tiene_prod):
            faltan = []
            if not tiene_srv:
                faltan.append("Pestania 1 (servidor)")
            if not tiene_prod:
                faltan.append("Pestania 2 (produccion)")
            st.caption("Ejecuta ambas simulaciones para habilitar el reporte. "
                       "Falta: " + ", ".join(faltan) + ".")
            return

        if st.button("Compilar reporte PDF", type="primary", width="stretch"):
            agg_srv, cfg_srv = st.session_state[tab_server.K_RESULT]
            agg_prod = st.session_state[tab_production.K_RESULT]
            with st.spinner("Compilando reporte unificado..."):
                st.session_state["pdf_bytes"] = pdf_generator.generar_reporte_pdf(
                    agg_srv, cfg_srv, agg_prod)
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
        "<p>Universidad de la Cuenca del Plata · TPI Intercatedra e Intercarrera · "
        "Grupo 2 · Tartaleta vegetal sustentable (Planta Piloto, 11/06/2026)</p></div>",
        unsafe_allow_html=True)

    _panel_reporte()

    tab1, tab2 = st.tabs([
        "🌐  Infraestructura Web & Concurrencia",
        "🍳  Cadena de Produccion & Abastecimiento",
    ])
    with tab1:
        tab_server.render()
    with tab2:
        tab_production.render()

    st.caption(
        f"Generado por el Simulador Intercátedra · Grupo 2 · "
        f"{datetime.now().strftime('%d/%m/%Y')}")


if __name__ == "__main__":
    main()
