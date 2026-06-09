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
from sim.production_sim import (ProductionAggregated, STOCK_INICIAL_LOTES,
                               TARTALETAS_POR_LOTE, VENTANA_ARRIBOS_MIN)
from sim.production_sim import generar_diagnostico as diagnostico_produccion
from sim.sensorial_sim import (ATRIBUTOS_BOOL, ATRIBUTOS_SLIDER, ETIQUETAS,
                               N_COMENSALES as SENS_N_COMENSALES,
                               N_PREGUNTAS_TOTAL, SensorialAggregated, UMBRAL_ACEPTACION)
from sim.sensorial_sim import generar_diagnostico as diagnostico_sensorial
from sim.sensorial_sim import resumen_demografico
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
    """Estilo de tabla segun Normas APA 7a ed.: SIN grilla, fondo blanco inmaculado y
    solo TRES lineas horizontales negras (borde superior, bajo el encabezado y borde
    inferior del cuerpo). Tipografia Times, encabezado en negrita."""
    from reportlab.platypus import TableStyle
    negro = colors.black
    return TableStyle([
        # Tipografia y fondo (negro sobre blanco, sin relleno de color).
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (-1, -1), negro),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        # Las TRES unicas lineas horizontales permitidas por APA 7.
        ("LINEABOVE", (0, 0), (-1, 0), 1.0, negro),     # Borde superior de la tabla.
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, negro),    # Bajo la fila de encabezado.
        ("LINEBELOW", (0, -1), (-1, -1), 1.0, negro),   # Borde inferior del cuerpo.
        # Alineacion y espaciado.
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])


def _png_temporal(fig, etiqueta: str) -> str:
    """Renderiza una figura matplotlib a un PNG temporal y devuelve su ruta."""
    ruta = os.path.join(tempfile.gettempdir(),
                        f"_g2_{etiqueta}_{os.getpid()}.png")
    fig.savefig(ruta, dpi=150, facecolor="white")
    return ruta


def _ic_txt(agg, clave: str, dec: int = 1) -> str:
    """Formatea 'media [inf - sup]' con el IC del 95% de un KPI.

    Sirve para cualquier agregado con metodos .media()/.ic() (servidor, produccion o
    sensorial); si la corrida fue de 1 sola replica, omite el intervalo.
    """
    media = agg.media(clave)
    if not getattr(agg, "ic_disponible", True):
        return f"{media:.{dec}f}  (sin IC)"
    inf, sup = agg.ic(clave)
    return f"{media:.{dec}f}  [{inf:.{dec}f} - {sup:.{dec}f}]"


def generar_reporte_pdf(agg_server: AggregatedResult, cfg_server: ScenarioConfig,
                        agg_prod: ProductionAggregated,
                        agg_sensorial: Optional[SensorialAggregated] = None,
                        ruta: Optional[str] = None) -> bytes:
    """Compila el reporte bifocal (ingenieria + salud) de las tres pestanias y devuelve
    sus bytes. La seccion sensorial Monte Carlo se incluye si se pasa `agg_sensorial`.

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
    png_perfil = png_sino = png_demo = png_sens = None
    if agg_sensorial is not None:
        png_perfil = _png_temporal(charts.figura_perfil(agg_sensorial), "perfil")
        png_sino = _png_temporal(charts.figura_si_no(agg_sensorial), "sino")
        png_demo = _png_temporal(charts.figura_demografia(agg_sensorial), "demo")
        png_sens = _png_temporal(charts.figura_sensibilidad(agg_sensorial), "sens")
        pngs.extend([png_perfil, png_sino, png_demo, png_sens])

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
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(
        f"<i>Nota.</i> Intervalos de Confianza del 95% estimados por "
        f"{agg_server.etiqueta_metodo_ic} sobre {agg_server.n_replicas} replicas "
        "(t-Student para muestras menores a 30; Normal en caso contrario).", st_diag))

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
        ["Indicador", "Promedio [IC 95%]"],
        ["Operarios de cocina", f"{cfg_prod.operarios}"],
        ["Capacidad del horno (lotes simultaneos)", f"{cfg_prod.horno_slots}"],
        ["Comensales / ventana de arribos",
         f"{cfg_prod.n_comensales} en {VENTANA_ARRIBOS_MIN:.0f} min"],
        ["Tartaletas por lote", f"{TARTALETAS_POR_LOTE}"],
        ["Total de tartaletas producidas", _ic_txt(agg_prod, "tartaletas_producidas", 0)],
        ["Lotes producidos", _ic_txt(agg_prod, "lotes_producidos")],
        ["Tiempo promedio de fabricacion de un lote (min)",
         _ic_txt(agg_prod, "tiempo_fab_promedio")],
        ["Tiempo maximo de espera de un comensal (min)",
         _ic_txt(agg_prod, "espera_maxima")],
        ["Comensales que esperaron alimento", _ic_txt(agg_prod, "comensales_en_espera")],
        ["Stock remanente al cierre (tartaletas)", _ic_txt(agg_prod, "stock_remanente", 0)],
    ]
    tabla_prod = Table(datos_prod, colWidths=[9.5 * cm, 6.5 * cm])
    tabla_prod.setStyle(_estilo_tabla(colors))
    story.append(tabla_prod)
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(
        f"<i>Nota.</i> Intervalos de Confianza del 95% por {agg_prod.etiqueta_metodo_ic} "
        f"sobre {agg_prod.n_replicas} replicas.", st_diag))
    story.append(Spacer(1, 0.35 * cm))

    # 2.b) Tabla APA de viabilidad economico-financiera (escenario de venta).
    payback = agg_prod.payback_jornadas
    payback_txt = ("No se recupera (jornada no rentable)" if payback == float("inf")
                   else f"{payback:.1f} jornadas / eventos")
    story.append(Paragraph(
        "Tabla 3. <i>Viabilidad economico-financiera del escenario de venta.</i>", st_body))
    datos_fin = [
        ["Concepto", "Valor (ARS)"],
        ["Precio de venta por tartaleta", f"$ {cfg_prod.precio_venta_unidad:,.0f}"],
        ["Costo de materia prima por lote", f"$ {cfg_prod.costo_mp_lote:,.0f}"],
        ["Costo por operario / jornada", f"$ {cfg_prod.costo_operario_jornada:,.0f}"],
        ["Tartaletas vendidas (servidas)", _ic_txt(agg_prod, "unidades_vendidas", 0)],
        ["Ingresos de la jornada", _ic_txt(agg_prod, "ingresos", 0)],
        ["Costos totales de la jornada", _ic_txt(agg_prod, "costo_total", 0)],
        ["Rentabilidad proyectada por jornada", _ic_txt(agg_prod, "rentabilidad", 0)],
        ["Inversion inicial en equipamiento", f"$ {cfg_prod.inversion_inicial:,.0f}"],
        ["Recupero de la inversion (payback)", payback_txt],
    ]
    tabla_fin = Table(datos_fin, colWidths=[9.5 * cm, 6.5 * cm])
    tabla_fin.setStyle(_estilo_tabla(colors))
    story.append(tabla_fin)
    story.append(Spacer(1, 0.4 * cm))

    # 2.c) Grafico de evolucion de stock.
    story.append(Paragraph(
        "Figura 3. <i>Evolucion del nivel de stock (zona roja = faltante de alimento).</i>",
        st_body))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Image(png_stock, width=16.0 * cm, height=16.0 * cm * 4.0 / 7.2))

    # =====================================================================
    # SECCION 3 - ACEPTACION SENSORIAL DEL PRODUCTO (MONTE CARLO)
    # =====================================================================
    if agg_sensorial is not None:
        demo = resumen_demografico(agg_sensorial)
        story.append(PageBreak())
        story.append(Paragraph(
            "Seccion 3. Aceptacion sensorial del producto (simulacion Monte Carlo)",
            st_h2))
        story.append(Paragraph(
            "Se estimo por el metodo de Monte Carlo la aceptacion de la tartaleta vegetal "
            f"a partir de {SENS_N_COMENSALES} comensales que responden la encuesta real de "
            f"{N_PREGUNTAS_TOTAL} preguntas: ocho atributos en escala 1-10, dos preguntas "
            "dicotomicas (Si/No) y los datos demograficos (ano de nacimiento y sexo), "
            "agrupados en cinco dimensiones sensoriales (Vista, Olfato, Tacto y Oido, Gusto "
            "y Boca, Sabor). La calidad de preparacion en cocina gobierna las medias de las "
            "distribuciones, y un efecto aleatorio por comensal modela la exigencia "
            "individual de cada juez. Un comensal acepta el producto si su sabor general es "
            f"mayor o igual a {UMBRAL_ACEPTACION}.", st_body))
        story.append(Spacer(1, 0.3 * cm))

        # 3.a) Perfil demografico del panel.
        story.append(Paragraph(
            "Tabla 4. <i>Perfil demografico del panel de comensales.</i>", st_body))
        datos_demo = [
            ["Indicador", "Valor"],
            ["Comensales del panel", f"{demo.n}"],
            ["Sexo masculino", f"{demo.n_masculino} ({demo.pct_masculino:.0f} %)"],
            ["Sexo femenino", f"{demo.n_femenino} ({demo.pct_femenino:.0f} %)"],
            ["Edad media (anios)", f"{demo.edad_media:.1f}"],
            ["Rango de edades (anios)", f"{demo.edad_min} - {demo.edad_max}"],
        ]
        tabla_demo = Table(datos_demo, colWidths=[9.5 * cm, 6.5 * cm])
        tabla_demo.setStyle(_estilo_tabla(colors))
        story.append(tabla_demo)
        story.append(Spacer(1, 0.35 * cm))

        # 3.b) Aceptacion global y perfil de los 8 atributos numericos.
        story.append(Paragraph(
            "Tabla 5. <i>Aceptacion y perfil de atributos numericos (promedio e IC 95%).</i>",
            st_body))
        datos_sens = [["Indicador", "Promedio [IC 95%]"],
                      ["Calidad de preparacion en cocina (1-10)",
                       f"{agg_sensorial.config.calidad_cocina}"],
                      ["Tasa de Aceptacion Global (%)",
                       _ic_txt(agg_sensorial, "tasa_aceptacion")],
                      ["Puntaje global medio (1-10)",
                       _ic_txt(agg_sensorial, "puntaje_global", 2)]]
        for attr in ATRIBUTOS_SLIDER:
            datos_sens.append([f"{ETIQUETAS[attr]} (1-10)",
                               _ic_txt(agg_sensorial, attr, 2)])
        tabla_sens = Table(datos_sens, colWidths=[9.5 * cm, 6.5 * cm])
        tabla_sens.setStyle(_estilo_tabla(colors))
        story.append(tabla_sens)
        story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph(
            f"<i>Nota.</i> Intervalos de Confianza del 95% por "
            f"{agg_sensorial.etiqueta_metodo_ic} sobre {agg_sensorial.n_iteraciones} "
            "iteraciones Monte Carlo.", st_diag))
        story.append(Spacer(1, 0.35 * cm))

        # 3.c) Preguntas dicotomicas Si/No.
        story.append(Paragraph(
            "Tabla 6. <i>Preguntas cualitativas: porcentaje de 'Si' (promedio e IC 95%).</i>",
            st_body))
        datos_bool = [["Pregunta (Si / No)", "% Si [IC 95%]"]]
        for b in ATRIBUTOS_BOOL:
            datos_bool.append([ETIQUETAS[b], _ic_txt(agg_sensorial, f"prop_{b}")])
        tabla_bool = Table(datos_bool, colWidths=[9.5 * cm, 6.5 * cm])
        tabla_bool.setStyle(_estilo_tabla(colors))
        story.append(tabla_bool)
        story.append(Spacer(1, 0.35 * cm))

        # 3.d) Figuras del analisis sensorial.
        story.append(PageBreak())
        story.append(Paragraph(
            "Figura 4. <i>Perfil sensorial: puntaje medio por atributo (umbral de aceptacion = 6).</i>",
            st_body))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Image(png_perfil, width=16.0 * cm, height=16.0 * cm * 3.6 / 7.2))
        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph(
            "Figura 5. <i>Preguntas cualitativas (Si / No) sobre el total de comensales.</i>",
            st_body))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Image(png_sino, width=16.0 * cm, height=16.0 * cm * 2.4 / 7.2))
        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph(
            "Figura 6. <i>Perfil demografico del panel: distribucion de edades y sexo.</i>",
            st_body))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Image(png_demo, width=16.0 * cm, height=16.0 * cm * 3.0 / 7.2))
        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph(
            "Figura 7. <i>Analisis de sensibilidad: aceptacion global vs Sabor general.</i>",
            st_body))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Image(png_sens, width=16.0 * cm, height=16.0 * cm * 3.2 / 7.2))

    # =====================================================================
    # BLOQUE DE DIAGNOSTICOS Y RECOMENDACIONES
    # =====================================================================
    story.append(PageBreak())
    story.append(Paragraph(
        "Diagnosticos y recomendaciones (ingenieria y salud)", st_h2))
    texto_diag = (diagnostico_servidor(agg_server, cfg_server) + "\n\n" +
                  diagnostico_produccion(agg_prod))
    if agg_sensorial is not None:
        texto_diag += "\n\n" + diagnostico_sensorial(agg_sensorial)
    for parrafo in texto_diag.split("\n"):
        texto = parrafo if parrafo.strip() else "&nbsp;"
        texto = texto.replace("  - ", "&bull;&nbsp;")
        story.append(Paragraph(texto, st_diag))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(
        "Reporte generado automaticamente por la Suite de Simulacion v4.0 - Grupo 2.",
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
