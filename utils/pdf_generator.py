# -*- coding: utf-8 -*-
"""
================================================================================
 utils/pdf_generator.py  ::  COMPILACION DEL REPORTE FORMAL (reportlab, Normas APA 7)
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Modulo aislado que compila con reportlab un documento formal bajo Normas APA 7a ed.
unificando las dos pestanias de la suite:
  * Seccion 1 (Infraestructura Tecnologica) ... KPIs e Intervalos de Confianza 95% del
    estres de servidor + los dos graficos vectoriales de la Pestania 1.
  * Seccion 2 (Viabilidad Organizacional) ..... rendimiento de la cadena de produccion
    + el grafico de evolucion de stock de la Pestania 2.
  * Bloque de Diagnosticos y Recomendaciones de Ingenieria de Software.

Devuelve los bytes del PDF para descargarlo desde la web (st.download_button).
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from io import BytesIO
from typing import List, Optional

from sim.server_sim import (AggregatedResult, FILL_TIME_MAX, FILL_TIME_MIN,
                            GATEWAY_TIMEOUT, ScenarioConfig)
from sim.server_sim import generar_diagnostico as diagnostico_servidor
from sim.production_sim import (ProductionAggregated, TARTALETAS_POR_LOTE,
                               VENTANA_ARRIBOS_MIN)
from sim.production_sim import generar_diagnostico as diagnostico_produccion
from utils import charts

# Datos institucionales del Grupo 2 para la portada del reporte.
GRUPO_INFO = {
    "universidad": "Universidad de la Cuenca del Plata - Sede Corrientes",
    "facultades": "Facultad de Ingenieria y Tecnologia  -  Facultad de Ciencias de la Salud",
    "tpi": "Trabajo Practico Integrador Intercatedra e Intercarrera",
    "catedras": "Modelos y Simulacion - Ingenieria de Software III - Quimica de los Alimentos",
    "grupo": "Grupo 2",
    "equipo_isi4": "Ingenieria en Sistemas (4to nivel): Modelos y Simulacion / Ing. de Software III",
    "equipo_isi3": "Ingenieria en Sistemas (3er nivel): Desarrollo web (HTML/JS + Supabase, Vercel)",
    "equipo_nutri": "Licenciatura en Nutricion (2do nivel): Quimica de los Alimentos / analisis sensorial",
    "evento": "Analisis sensorial - tartaleta vegetal sustentable - Planta Piloto - jueves 11/06/2026",
}


def _estilo_tabla(colors):
    """Estilo visual reutilizable para las tablas APA del PDF."""
    from reportlab.platypus import TableStyle
    verde = colors.HexColor("#2E7D32")
    verde_suave = colors.HexColor("#EAF3E2")
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), verde),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, verde_suave]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C4CFB6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ])


def _png_temporal(fig, etiqueta: str) -> str:
    """Renderiza una figura matplotlib a un PNG temporal y devuelve su ruta."""
    ruta = os.path.join(tempfile.gettempdir(),
                        f"_g2_{etiqueta}_{os.getpid()}.png")
    fig.savefig(ruta, dpi=150, facecolor="white")
    return ruta


def _ic_txt(agg: AggregatedResult, clave: str, dec: int = 1) -> str:
    """Formatea 'media [inf - sup]' con el IC del 95% de un KPI."""
    media = agg.media(clave)
    inf, sup = agg.ic(clave)
    return f"{media:.{dec}f}  [{inf:.{dec}f} - {sup:.{dec}f}]"


def generar_reporte_pdf(agg_server: AggregatedResult, cfg_server: ScenarioConfig,
                        agg_prod: ProductionAggregated,
                        ruta: Optional[str] = None) -> bytes:
    """Compila el reporte unificado de ambas pestanias y devuelve sus bytes.

    Si se pasa `ruta`, ademas escribe el PDF en disco (uso CLI/pruebas).
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate,
                                    Spacer, Table)

    pool = cfg_server.pool_capacity

    # --- 1) Graficos como PNG estaticos (anexos vectoriales) ---
    pngs = [
        _png_temporal(charts.figura_conexiones(agg_server), "conex"),
        _png_temporal(charts.figura_boxplot(agg_server), "box"),
        _png_temporal(charts.figura_stock(agg_prod), "stock"),
    ]
    png_conex, png_box, png_stock = pngs

    # --- 2) Estilos (aproximacion a APA 7: Times New Roman, jerarquia clara) ---
    base = getSampleStyleSheet()
    VERDE = colors.HexColor("#2E7D32")
    GRIS = colors.HexColor("#4A4A4A")
    st_titulo = ParagraphStyle("titulo", parent=base["Title"], fontName="Times-Bold",
                               fontSize=20, leading=24, textColor=VERDE, alignment=TA_CENTER)
    st_sub = ParagraphStyle("sub", parent=base["Normal"], fontName="Times-Roman",
                            fontSize=12, leading=16, alignment=TA_CENTER, textColor=GRIS)
    st_portada = ParagraphStyle("portada", parent=base["Normal"], fontName="Times-Roman",
                                fontSize=12, leading=18, alignment=TA_CENTER)
    st_h2 = ParagraphStyle("h2", parent=base["Heading2"], fontName="Times-Bold",
                           fontSize=13, leading=16, textColor=VERDE, spaceBefore=10,
                           spaceAfter=6)
    st_body = ParagraphStyle("body", parent=base["Normal"], fontName="Times-Roman",
                             fontSize=10.5, leading=15, alignment=TA_JUSTIFY)
    st_diag = ParagraphStyle("diag", parent=base["Normal"], fontName="Times-Roman",
                             fontSize=10, leading=14, alignment=TA_LEFT)
    st_pie = ParagraphStyle("pie", parent=base["Normal"], fontName="Times-Italic",
                            fontSize=9, leading=12, alignment=TA_CENTER, textColor=GRIS)

    story: List = []

    # --- 3) PORTADA INSTITUCIONAL ---
    story.append(Spacer(1, 2.0 * cm))
    story.append(Paragraph("Reporte de Simulacion de Eventos Discretos", st_titulo))
    story.append(Paragraph("Suite Integrada: Infraestructura Web y Cadena de Produccion",
                           st_sub))
    story.append(Spacer(1, 1.0 * cm))
    story.append(Paragraph(f"<b>{GRUPO_INFO['universidad']}</b>", st_portada))
    story.append(Paragraph(GRUPO_INFO["facultades"], st_portada))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(GRUPO_INFO["tpi"], st_portada))
    story.append(Paragraph(GRUPO_INFO["catedras"], st_portada))
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(f"<b>{GRUPO_INFO['grupo']}</b>", st_portada))
    story.append(Paragraph(GRUPO_INFO["equipo_isi4"], st_portada))
    story.append(Paragraph(GRUPO_INFO["equipo_isi3"], st_portada))
    story.append(Paragraph(GRUPO_INFO["equipo_nutri"], st_portada))
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(GRUPO_INFO["evento"], st_portada))
    story.append(Paragraph(
        f"Escenario de servidor: <b>{agg_server.escenario}</b>  |  "
        f"Replicas servidor: {agg_server.n_replicas}  |  "
        f"Replicas produccion: {agg_prod.n_replicas}", st_portada))
    story.append(Paragraph(
        "Fecha de emision: " + datetime.now().strftime("%d/%m/%Y %H:%M"), st_portada))
    story.append(PageBreak())

    # =====================================================================
    # SECCION 1 - INFRAESTRUCTURA TECNOLOGICA
    # =====================================================================
    story.append(Paragraph("Seccion 1. Infraestructura tecnologica (estres de servidor)",
                           st_h2))
    story.append(Paragraph(
        "Se modelo mediante simulacion de eventos discretos el Connection Pooler de "
        "Supabase frente a la concurrencia de los comensales que envian la encuesta de "
        "analisis sensorial. El sistema web estatico se conecta de forma directa "
        "(Client-to-Cloud) a PostgreSQL, por lo que el limite del plan gratuito y la "
        "estabilidad de la red Wi-Fi de la Planta Piloto condicionan el exito de la "
        "captura de datos. " + cfg_server.descripcion, st_body))
    story.append(Spacer(1, 0.3 * cm))

    # 1.a) Parametros del escenario.
    datos_param = [
        ["Parametro", "Valor"],
        ["Escenario (preset)", cfg_server.nombre],
        ["Comensales (entidades)", f"{cfg_server.n_comensales}"],
        ["Ventana de arribos", f"{cfg_server.ventana_arribos_seg/60:.1f} min"],
        ["Distribucion de arribos", f"Exponencial (media {cfg_server.tasa_arribo_media:.1f} s)"],
        ["Tiempo de llenado", f"Uniforme({FILL_TIME_MIN:.0f}, {FILL_TIME_MAX:.0f}) s"],
        ["Latencia / respuesta cloud",
         f"Normal({cfg_server.latencia_media:.2f} s; {cfg_server.latencia_desvio:.2f} s)"],
        ["Modelo Wi-Fi (cuelgue)",
         f"P={cfg_server.prob_cuelgue:.0%} ; retencion extra Exp(media {cfg_server.cuelgue_media:.0f} s)"],
        ["Reintentos maximos", f"{cfg_server.max_reintentos}"],
        ["Limite del Connection Pooler", f"{pool} conexiones simultaneas (hardware)"],
        ["Timeout de gateway (504)", f"{GATEWAY_TIMEOUT:.0f} s"],
    ]
    tabla_param = Table(datos_param, colWidths=[7.0 * cm, 9.0 * cm])
    tabla_param.setStyle(_estilo_tabla(colors))
    story.append(tabla_param)
    story.append(Spacer(1, 0.3 * cm))

    # 1.b) Tabla APA de KPIs con Intervalos de Confianza 95%.
    story.append(Paragraph(
        "Tabla 1. <i>Indicadores de desempenio del servidor (promedio e IC 95%).</i>",
        st_body))
    tasa = 100.0 * agg_server.media("exitos") / cfg_server.n_comensales if cfg_server.n_comensales else 0.0
    datos_kpi = [
        ["KPI", "Promedio [IC 95%]"],
        ["Encuestas guardadas con exito",
         f"{agg_server.media('exitos'):.1f} / {cfg_server.n_comensales}"],
        ["Tasa de exito", f"{tasa:.1f} %"],
        ["Errores 504 / caidas (total)", _ic_txt(agg_server, "total_504")],
        ["   - 504 por saturacion del pool", _ic_txt(agg_server, "err_504_pool")],
        ["   - 504 por Wi-Fi colgada", _ic_txt(agg_server, "err_504_latencia")],
        ["Errores de red", _ic_txt(agg_server, "err_red")],
        ["Encuestas perdidas (tras reintentos)", _ic_txt(agg_server, "encuestas_perdidas")],
        ["Espera promedio en cola (s)", _ic_txt(agg_server, "espera_cola_promedio", 3)],
        ["Tamanio maximo de cola de BD", _ic_txt(agg_server, "max_cola")],
        ["Pico de conexiones concurrentes",
         f"{_ic_txt(agg_server, 'pico_conexiones')}  / {pool}"],
    ]
    tabla_kpi = Table(datos_kpi, colWidths=[8.0 * cm, 8.0 * cm])
    tabla_kpi.setStyle(_estilo_tabla(colors))
    story.append(tabla_kpi)

    # 1.c) Los dos graficos vectoriales de la Pestania 1.
    story.append(PageBreak())
    story.append(Paragraph("Figura 1. <i>Curva de conexiones ocupadas en el tiempo.</i>",
                           st_body))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Image(png_conex, width=16.0 * cm, height=16.0 * cm * 4.0 / 7.2))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(
        "Figura 2. <i>Distribucion de Encuestas Perdidas sobre las N replicas (boxplot).</i>",
        st_body))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Image(png_box, width=16.0 * cm, height=16.0 * cm * 3.2 / 7.2))

    # =====================================================================
    # SECCION 2 - VIABILIDAD ORGANIZACIONAL DE PRODUCCION
    # =====================================================================
    story.append(PageBreak())
    cfg_prod = agg_prod.config
    story.append(Paragraph(
        "Seccion 2. Viabilidad organizacional de la cadena de produccion", st_h2))
    story.append(Paragraph(
        "Se simulo la cocina de la Planta Piloto como una cadena de tres etapas (masa y "
        "relleno, horneado y ensamblado), con operarios y horno como recursos limitados. "
        "Los lotes terminados reponen el stock del mostrador, del que los comensales "
        "retiran su tartaleta segun la misma distribucion exponencial de arribos de la "
        "Seccion 1. El cruce entre la tasa de produccion y el ritmo de consumo determina "
        "la viabilidad operativa y los faltantes de alimento.", st_body))
    story.append(Spacer(1, 0.3 * cm))

    # 2.a) Tabla APA de rendimiento de stock.
    story.append(Paragraph(
        "Tabla 2. <i>Rendimiento de la cadena de produccion (promedio de replicas).</i>",
        st_body))
    datos_prod = [
        ["Indicador", "Valor"],
        ["Operarios de cocina", f"{cfg_prod.operarios}"],
        ["Capacidad del horno (lotes simultaneos)", f"{cfg_prod.horno_slots}"],
        ["Comensales / ventana de arribos",
         f"{cfg_prod.n_comensales} en {VENTANA_ARRIBOS_MIN:.0f} min"],
        ["Tartaletas por lote", f"{TARTALETAS_POR_LOTE}"],
        ["Total de tartaletas producidas", f"{agg_prod.media('tartaletas_producidas'):.0f}"],
        ["Lotes producidos", f"{agg_prod.media('lotes_producidos'):.1f}"],
        ["Tiempo promedio de fabricacion de un lote",
         f"{agg_prod.media('tiempo_fab_promedio'):.1f} min"],
        ["Tiempo maximo de espera de un comensal",
         f"{agg_prod.media('espera_maxima'):.1f} min"],
        ["Comensales que esperaron alimento",
         f"{agg_prod.media('comensales_en_espera'):.1f}"],
        ["Stock remanente al cierre", f"{agg_prod.media('stock_remanente'):.0f} tartaletas"],
    ]
    tabla_prod = Table(datos_prod, colWidths=[9.5 * cm, 6.5 * cm])
    tabla_prod.setStyle(_estilo_tabla(colors))
    story.append(tabla_prod)
    story.append(Spacer(1, 0.4 * cm))

    # 2.b) Grafico de evolucion de stock.
    story.append(Paragraph(
        "Figura 3. <i>Evolucion del nivel de stock (zona roja = faltante de alimento).</i>",
        st_body))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Image(png_stock, width=16.0 * cm, height=16.0 * cm * 4.0 / 7.2))

    # =====================================================================
    # BLOQUE DE DIAGNOSTICOS Y RECOMENDACIONES
    # =====================================================================
    story.append(PageBreak())
    story.append(Paragraph(
        "Diagnosticos y recomendaciones de Ingenieria de Software", st_h2))
    texto_diag = (diagnostico_servidor(agg_server, cfg_server) + "\n\n" +
                  diagnostico_produccion(agg_prod))
    for parrafo in texto_diag.split("\n"):
        texto = parrafo if parrafo.strip() else "&nbsp;"
        texto = texto.replace("  - ", "&bull;&nbsp;")
        story.append(Paragraph(texto, st_diag))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(
        "Reporte generado automaticamente por la Suite de Simulacion v3.0 - Grupo 2.",
        st_pie))

    # --- Construir el documento sobre un buffer en memoria ---
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2.2 * cm, bottomMargin=2.0 * cm,
        leftMargin=2.3 * cm, rightMargin=2.3 * cm,
        title="Reporte Simulacion Suite Integrada - Grupo 2",
        author=GRUPO_INFO["grupo"])
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    # Limpieza de los PNG temporales.
    for ruta_png in pngs:
        try:
            os.remove(ruta_png)
        except OSError:
            pass

    if ruta:
        with open(ruta, "wb") as fh:
            fh.write(pdf_bytes)

    return pdf_bytes
