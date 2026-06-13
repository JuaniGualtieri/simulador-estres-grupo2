# -*- coding: utf-8 -*-
"""
================================================================================
 sim/production_sim.py  ::  MOTOR MATEMATICO PURO - PESTANIA 2 (PRODUCCION & STOCK)
 Trabajo Practico Integrador Intercatedra - Grupo 2
 Asignatura: Modelos y Simulacion - 4to Anio - Ingenieria en Sistemas de Informacion
================================================================================

OBJETIVO DEL MODELO 2
---------------------
Modelar mediante SIMULACION DE EVENTOS DISCRETOS (SimPy) la cadena de suministro y
fabricacion fisica de las tartaletas vegetales en la cocina de la Planta Piloto,
cruzando la TASA DE PRODUCCION contra el RITMO DE CONSUMO de los comensales para
determinar la viabilidad organizacional y los cuellos de botella de stock.

DEFINICION TEORICA
------------------
* ENTIDADES ........... Tandas de horneado (cada tanda = lote FIJO de 8 tartaletas
                        ENTERAS) que recorren la cadena de produccion.
* RECURSOS ............ Operarios de cocina disponibles (simpy.Resource) y Capacidad
                        fisica del Horno = tandas maximas concurrentes (simpy.Resource).
* VARIABLES DE ESTADO   Stock actual de tartaletas enteras en el mostrador de despacho
                        (simpy.Container), estado del horno (ranuras ocupadas) y
                        comensales en la fila de despacho (espera por alimento).

FLUJO DEL PROCESO OPERATIVO (LOGICA SimPy) - MODELO MULTI-ETAPA DEL CASO REAL
-----------------------------------------------------------------------------
Cada TANDA de 8 tartaletas enteras recorre tres etapas de tiempos FIJOS medidos en la
Planta Piloto (sin variabilidad: son tiempos de receta controlados por el operario):
* Etapa 1 (Coccion del Relleno) ... 30 min FIJOS. Requiere un operario que cocina el
                                    relleno (pollo, alubia y vegetales) en la hornalla.
* Etapa 2 (Horneado de la Masa) ... 15 min FIJOS. Requiere una ranura libre del Horno.
* Etapa 3 (Armado y Gratinado) .... 10 min FIJOS. Requiere el Horno (gratinadora). El
                                    ARMADO de la tartaleta esta SOLAPADO dentro de estos
                                    10 min de gratinado final del queso, no se modela
                                    como un tiempo aparte.
Cada tanda terminada incorpora 8 tartaletas ENTERAS al mostrador. Para cubrir la
demanda entera de 64 comensales se encolan ceil(64 / 8) = 8 tandas de horneado.

REGLA DE DESPACHO ENTERO
------------------------
Cada comensal consume estrictamente UNA (1) tartaleta ENTERA. No existe fraccionamiento
en mitades ni cuartos: la demanda total es de 64 tartaletas completas para los 64
comensales (1 a 1).

ACOPLAMIENTO DINAMICO INTERCATEDRA (CONSUMO DE STOCK)
-----------------------------------------------------
La llegada de los comensales usa la MISMA distribucion EXPONENCIAL de arribos de la
Pestania 1 (media 1,32 min entre llegadas). Al llegar, cada comensal intenta retirar
una tartaleta ENTERA lista del mostrador de despacho:
  - Si hay stock disponible, el stock disminuye en 1 y el comensal pasa a responder la
    encuesta web (sale del sistema de cocina).
  - Si el stock es 0, el comensal entra a la "Fila de Despacho" (modelada con el bloqueo
    nativo de simpy.Container.get) reteniendo su tiempo hasta que una tanda finalice la
    Etapa 3 y reponga el mostrador.
================================================================================
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

import numpy as np
import simpy

from sim.estadistica import cuantil_ic95, intervalo_confianza_95

# ---------------------------------------------------------------------------
# PARAMETROS DEL MODELO DE PRODUCCION (tiempos en MINUTOS)
# ---------------------------------------------------------------------------
# Acoplamiento con el Caso Real (Pestania 1): 64 comensales reales que arriban segun
# una EXPONENCIAL de media 1,32 min (79,3 s). Como tasa_arribo_media = ventana / n,
# fijamos la ventana en 1,32 min x 64 para reproducir esa media exacta entre llegadas.
N_COMENSALES = 64              # Comensales reales del stand (cada uno consume 1 tartaleta ENTERA).
MEDIA_ARRIBO_MIN = 79.3 / 60.0  # 1,32 min: media de la Exponencial de arribos del Caso Real.
VENTANA_ARRIBOS_MIN = MEDIA_ARRIBO_MIN * N_COMENSALES  # Para que E(X) = ventana/n = 1,32 min.
DEMANDA_TARTALETAS = N_COMENSALES   # Regla de despacho ENTERO: 64 tartaletas completas para 64 comensales.

# --- Lote/tanda FIJO de produccion y tiempos FIJOS de las tres etapas (medidos en planta) ---
TARTALETAS_POR_LOTE = 8        # Tanda FIJA de 8 tartaletas ENTERAS por ciclo de horneado.
TIEMPO_RELLENO = 30.0          # Etapa 1: Coccion del Relleno = 30 min FIJOS (requiere operario).
TIEMPO_HORNEADO_MASA = 15.0    # Etapa 2: Horneado de la Masa = 15 min FIJOS (requiere horno).
TIEMPO_GRATINADO = 10.0        # Etapa 3: Armado y Gratinado del Queso = 10 min FIJOS (armado solapado dentro).
TIEMPO_CICLO_LOTE = (TIEMPO_RELLENO + TIEMPO_HORNEADO_MASA
                     + TIEMPO_GRATINADO)  # 55 min: camino critico de UNA tanda sin contienda de recursos.
STOCK_INICIAL_LOTES = 0        # Sin pre-coccion: las 64 tartaletas salen integras de la jornada.

SEED_BASE = 2026             # Semilla base (anio del evento) para reproducibilidad.
N_REPLICAS_DEFAULT = 20      # Replicas para estabilizar los KPIs escalares.

# ---------------------------------------------------------------------------
# PARAMETROS ECONOMICO-FINANCIEROS (escenario de emprendimiento, en pesos ARS)
# ---------------------------------------------------------------------------
# Modelan la pregunta de Nutricion de la Parte 2 del TPI: "si el producto se
# comercializara, cuanto se gana por jornada y en cuantas jornadas se recupera la
# inversion inicial". Son valores POR DEFECTO, totalmente parametrizables por la UI.
COSTO_MP_LOTE = 7200.0          # Costo de materia prima por tanda de 8 unidades (~$900 c/u).
PRECIO_VENTA_UNIDAD = 3000.0    # Precio de venta sugerido por tartaleta al publico.
COSTO_OPERARIO_JORNADA = 15000.0  # Costo fijo por operario por jornada de produccion.
INVERSION_INICIAL = 500000.0    # Inversion inicial en equipamiento de cocina (horno, mesada, utensilios).

# Valores por defecto de los sliders/campos de la Pestania 2.
SLIDER_DEFAULTS = {
    "operarios": 2,    # Rango [1 - 5].
    "horno": 2,        # Rango [1 - 4] lotes simultaneos.
    # Parametros economicos editables (number_input).
    "costo_mp_lote": COSTO_MP_LOTE,
    "precio_venta": PRECIO_VENTA_UNIDAD,
    "costo_operario": COSTO_OPERARIO_JORNADA,
    "inversion_inicial": INVERSION_INICIAL,
}


@dataclass(frozen=True)
class ProductionConfig:
    """Parametros configurables de la cadena de produccion (vienen de los sliders)."""
    operarios: int          # Cantidad de operarios de cocina (SLIDER [1-5]).
    horno_slots: int        # Capacidad del horno en lotes simultaneos (SLIDER [1-4]).
    n_comensales: int = N_COMENSALES
    ventana_arribos_min: float = VENTANA_ARRIBOS_MIN
    # --- Parametros economico-financieros (escenario de emprendimiento) ---
    costo_mp_lote: float = COSTO_MP_LOTE          # Costo materia prima por lote.
    precio_venta_unidad: float = PRECIO_VENTA_UNIDAD  # Precio de venta por tartaleta.
    costo_operario_jornada: float = COSTO_OPERARIO_JORNADA  # Costo fijo por operario/jornada.
    inversion_inicial: float = INVERSION_INICIAL  # Inversion inicial en equipamiento.

    @property
    def tasa_arribo_media(self) -> float:
        """Media de la EXPONENCIAL de tiempos entre arribos (min)."""
        return self.ventana_arribos_min / self.n_comensales


# ---------------------------------------------------------------------------
# ESTRUCTURAS DE RESULTADOS
# ---------------------------------------------------------------------------
@dataclass
class ProductionReplicaResult:
    """KPIs y serie de stock de UNA corrida de la cadena de produccion."""
    tartaletas_producidas: int = 0       # Unidades fabricadas (sin contar stock inicial).
    lotes_producidos: int = 0            # Lotes/bandejas completados.
    stock_remanente: int = 0             # Tartaletas sobrantes al cerrar la jornada.
    servidos: int = 0                    # Comensales que retiraron su tartaleta.
    tiempo_total: float = 0.0            # Duracion simulada (min).
    tiempos_fabricacion: List[float] = field(default_factory=list)  # Por lote (min).
    esperas: List[float] = field(default_factory=list)              # Por comensal (min).
    interarribos: List[float] = field(default_factory=list)         # V&V del generador (min).
    # Serie temporal del nivel de stock (para la corrida representativa).
    serie_t: List[float] = field(default_factory=list)
    serie_stock: List[int] = field(default_factory=list)

    @property
    def espera_maxima(self) -> float:
        return max(self.esperas) if self.esperas else 0.0

    @property
    def espera_promedio(self) -> float:
        return statistics.fmean(self.esperas) if self.esperas else 0.0

    @property
    def tiempo_fab_promedio(self) -> float:
        return statistics.fmean(self.tiempos_fabricacion) if self.tiempos_fabricacion else 0.0

    @property
    def comensales_en_espera(self) -> int:
        """Comensales que tuvieron que esperar alimento (espera > 0)."""
        return sum(1 for e in self.esperas if e > 1e-9)


@dataclass
class ProductionAggregated:
    """KPIs agregados (media + IC 95%) sobre N replicas + serie de stock representativa."""
    n_replicas: int
    config: ProductionConfig
    medias: Dict[str, float] = field(default_factory=dict)
    desvios: Dict[str, float] = field(default_factory=dict)
    ic_inf: Dict[str, float] = field(default_factory=dict)   # Limite inferior IC 95%.
    ic_sup: Dict[str, float] = field(default_factory=dict)   # Limite superior IC 95%.
    muestras: Dict[str, List[float]] = field(default_factory=dict)  # Valores crudos por KPI.
    # Trazabilidad del metodo de IC aplicado (t-Student vs Normal) segun n replicas.
    metodo_ic: str = "na"          # "t", "normal" o "na" (n<2).
    cuantil_ic: float = 0.0        # Valor critico aplicado (t o Z).
    gl_ic: int = 0                 # Grados de libertad (n-1).
    n_muestral: int = 0            # Cantidad de replicas (tamanio de la muestra).
    interarribos: List[float] = field(default_factory=list)  # V&V del generador (min).
    serie_t: List[float] = field(default_factory=list)
    serie_stock: List[int] = field(default_factory=list)

    def media(self, clave: str) -> float:
        return self.medias.get(clave, 0.0)

    def desvio(self, clave: str) -> float:
        return self.desvios.get(clave, 0.0)

    def ic(self, clave: str) -> Tuple[float, float]:
        """Devuelve (limite_inferior, limite_superior) del IC 95% de un KPI."""
        return self.ic_inf.get(clave, 0.0), self.ic_sup.get(clave, 0.0)

    def muestra(self, clave: str) -> List[float]:
        return self.muestras.get(clave, [])

    @property
    def ic_disponible(self) -> bool:
        """True si hubo >=2 replicas para estimar la variabilidad (hay IC)."""
        return self.metodo_ic != "na"

    @property
    def etiqueta_metodo_ic(self) -> str:
        """Descripcion legible del metodo de IC (para la UI y el reporte PDF)."""
        if self.metodo_ic == "t":
            return f"t-Student (gl={self.gl_ic}, t={self.cuantil_ic:.3f})"
        if self.metodo_ic == "normal":
            return f"Normal estandar (Z={self.cuantil_ic:.3f})"
        return "No disponible (1 sola corrida)"

    @property
    def payback_jornadas(self) -> float:
        """Cantidad de jornadas/eventos para recuperar la inversion inicial.

        Payback = Inversion / Rentabilidad media por jornada. Devuelve math.inf si la
        jornada no es rentable (rentabilidad <= 0): la inversion no se recupera.
        """
        rent = self.media("rentabilidad")
        if rent <= 0:
            return math.inf
        return self.config.inversion_inicial / rent


# ---------------------------------------------------------------------------
# MONITOR DEL STOCK (variable de estado: nivel del mostrador)
# ---------------------------------------------------------------------------
class StockMonitor:
    """Envuelve el simpy.Container del stock y registra su nivel en cada cambio.

    Reconstruye la serie temporal (tiempo, nivel) que alimenta el grafico de evolucion
    del stock, pintando en rojo los tramos en que el mostrador queda en cero (faltante).
    """

    def __init__(self, env: simpy.Environment, resultado: ProductionReplicaResult,
                 stock_inicial: int):
        self.env = env
        self.container = simpy.Container(env, init=stock_inicial, capacity=float("inf"))
        self.resultado = resultado
        self._registrar()  # Nivel inicial en t=0.

    def _registrar(self) -> None:
        self.resultado.serie_t.append(self.env.now)
        self.resultado.serie_stock.append(int(self.container.level))

    def reponer(self, cantidad: int):
        """Incorpora un lote terminado al mostrador."""
        yield self.container.put(cantidad)
        self._registrar()

    def retirar_una(self):
        """El comensal toma 1 tartaleta (se bloquea si el stock esta en 0)."""
        yield self.container.get(1)
        self._registrar()


# ---------------------------------------------------------------------------
# PROCESOS GENERADORES SimPy
# ---------------------------------------------------------------------------
def proceso_lote(env: simpy.Environment, monitor: StockMonitor,
                 operarios: simpy.Resource, horno: simpy.Resource,
                 cfg: ProductionConfig, rng: np.random.Generator):
    """Ciclo de fabricacion de UNA tanda de 8 tartaletas por las tres etapas FIJAS.

    Los tres tiempos son DETERMINISTAS (tiempos de receta controlados): no se muestrea
    ninguna distribucion, por eso `rng` no se usa aqui. Lo que introduce dinamica y
    diferencias entre corridas es la CONTIENDA por los recursos (operarios y horno)
    entre las 8 tandas que se lanzan en paralelo al inicio de la jornada.
    """
    resultado = monitor.resultado
    t_inicio = env.now

    # Etapa 1 (Coccion del Relleno): requiere un operario -> 30 min FIJOS.
    with operarios.request() as op:
        yield op
        yield env.timeout(TIEMPO_RELLENO)

    # Etapa 2 (Horneado de la Masa): requiere una ranura del horno -> 15 min FIJOS.
    with horno.request() as ranura:
        yield ranura
        yield env.timeout(TIEMPO_HORNEADO_MASA)

    # Etapa 3 (Armado y Gratinado del Queso): requiere el horno/gratinadora -> 10 min
    # FIJOS. El ARMADO de la tartaleta esta SOLAPADO dentro de estos 10 min de gratinado.
    with horno.request() as ranura:
        yield ranura
        yield env.timeout(TIEMPO_GRATINADO)

    # Tanda terminada: se reponen 8 tartaletas ENTERAS al mostrador de despacho.
    yield from monitor.reponer(TARTALETAS_POR_LOTE)
    resultado.tartaletas_producidas += TARTALETAS_POR_LOTE
    resultado.lotes_producidos += 1
    resultado.tiempos_fabricacion.append(env.now - t_inicio)


def lotes_objetivo(cfg: ProductionConfig, stock_inicial: int) -> int:
    """Cantidad de TANDAS de horneado de 8 unidades para satisfacer la demanda ENTERA.

    Por la regla de despacho entero, cada uno de los cfg.n_comensales consume 1 tartaleta
    ENTERA, asi que la demanda total es cfg.n_comensales unidades. Las tandas necesarias
    son el techo de (demanda - stock pre-cocido) / 8; con 64 comensales y sin pre-coccion
    da ceil(64 / 8) = 8 tandas exactas. Estas ordenes de trabajo se encolan al inicio de
    la jornada y los recursos (operarios y horno) las procesan EN PARALELO segun su
    capacidad, por lo que mas operarios u horno mas grande aceleran la reposicion.
    """
    faltante = max(0, cfg.n_comensales - stock_inicial)
    return math.ceil(faltante / TARTALETAS_POR_LOTE)


def lanzar_produccion(env: simpy.Environment, monitor: StockMonitor,
                      operarios: simpy.Resource, horno: simpy.Resource,
                      cfg: ProductionConfig, rng: np.random.Generator,
                      n_lotes: int):
    """Encola TODAS las ordenes de lote en t=0. Cada lote compite por los recursos; la
    capacidad de operarios y del horno limita cuantos avanzan en paralelo."""
    for _ in range(n_lotes):
        env.process(proceso_lote(env, monitor, operarios, horno, cfg, rng))


def proceso_comensal(env: simpy.Environment, monitor: StockMonitor,
                     resultado: ProductionReplicaResult):
    """Comensal que arriba e intenta retirar una tartaleta del mostrador.

    Si hay stock, lo retira al instante; si no, queda en la Cola de Espera por Alimento
    (bloqueo del Container.get) hasta que un lote reponga el mostrador.
    """
    t_arribo = env.now
    yield from monitor.retirar_una()
    resultado.esperas.append(env.now - t_arribo)
    resultado.servidos += 1
    # A partir de aqui el comensal pasaria a responder la encuesta web (Pestania 1).


def _generador_arribos(env: simpy.Environment, monitor: StockMonitor,
                       cfg: ProductionConfig, rng: np.random.Generator):
    """Arribos de comensales segun una EXPONENCIAL de tiempos entre llegadas (igual que
    la Pestania 1, garantizando el acoplamiento intercatedra)."""
    resultado = monitor.resultado
    for _ in range(cfg.n_comensales):
        env.process(proceso_comensal(env, monitor, resultado))
        dt = rng.exponential(cfg.tasa_arribo_media)
        resultado.interarribos.append(dt)   # Muestra para la validacion V&V.
        yield env.timeout(dt)


# ---------------------------------------------------------------------------
# CORRIDA DE UNA REPLICA Y AGREGACION DE EXPERIMENTOS
# ---------------------------------------------------------------------------
def correr_replica(cfg: ProductionConfig, semilla: int) -> ProductionReplicaResult:
    """Ejecuta UNA corrida completa de la cadena de produccion y devuelve sus KPIs."""
    rng = np.random.default_rng(semilla)
    env = simpy.Environment()
    resultado = ProductionReplicaResult()
    stock_inicial = STOCK_INICIAL_LOTES * TARTALETAS_POR_LOTE
    monitor = StockMonitor(env, resultado, stock_inicial)
    operarios = simpy.Resource(env, capacity=cfg.operarios)
    horno = simpy.Resource(env, capacity=cfg.horno_slots)

    n_lotes = lotes_objetivo(cfg, stock_inicial)
    env.process(_generador_arribos(env, monitor, cfg, rng))
    lanzar_produccion(env, monitor, operarios, horno, cfg, rng, n_lotes)
    env.run()  # Corre hasta servir a todos y terminar todos los lotes encolados.

    resultado.tiempo_total = env.now
    resultado.stock_remanente = int(monitor.container.level)
    # Punto final para cerrar la curva escalonada del stock.
    resultado.serie_t.append(env.now)
    resultado.serie_stock.append(int(monitor.container.level))
    return resultado


def _finanzas_replica(r: ProductionReplicaResult, cfg: ProductionConfig) -> Dict[str, float]:
    """Indicadores economicos (ARS) de UNA jornada simulada (escenario de venta).

    Las tartaletas vendidas son las efectivamente retiradas por los comensales. El costo
    variable se calcula sobre las tandas realmente horneadas (mas el stock pre-cocido si
    lo hubiera), ya que cada tanda de 8 unidades consume una porcion de materia prima.
    """
    unidades_vendidas = float(r.servidos)
    ingresos = unidades_vendidas * cfg.precio_venta_unidad
    lotes_totales = r.lotes_producidos + STOCK_INICIAL_LOTES
    costo_variable = lotes_totales * cfg.costo_mp_lote
    costo_fijo = cfg.operarios * cfg.costo_operario_jornada
    rentabilidad = ingresos - costo_variable - costo_fijo
    return {
        "unidades_vendidas": unidades_vendidas,
        "ingresos": ingresos,
        "costo_variable": costo_variable,
        "costo_fijo": costo_fijo,
        "costo_total": costo_variable + costo_fijo,
        "rentabilidad": rentabilidad,
    }


def correr_experimento(cfg: ProductionConfig, n_replicas: int = N_REPLICAS_DEFAULT,
                       semilla_base: int = SEED_BASE,
                       progreso: Callable[[int, int], None] | None = None
                       ) -> ProductionAggregated:
    """Ejecuta N replicas de la cadena de produccion, agrega los KPIs (media + IC 95%)
    y conserva la serie de stock de la primera corrida como corrida representativa."""
    replicas: List[ProductionReplicaResult] = []
    for rep in range(n_replicas):
        replicas.append(correr_replica(cfg, semilla_base + rep))
        if progreso is not None:
            progreso(rep + 1, n_replicas)

    def _serie(extractor) -> List[float]:
        return [extractor(r) for r in replicas]

    metricas = {
        "tartaletas_producidas": _serie(lambda r: r.tartaletas_producidas),
        "lotes_producidos": _serie(lambda r: r.lotes_producidos),
        "tiempo_fab_promedio": _serie(lambda r: r.tiempo_fab_promedio),
        "espera_maxima": _serie(lambda r: r.espera_maxima),
        "espera_promedio": _serie(lambda r: r.espera_promedio),
        "stock_remanente": _serie(lambda r: r.stock_remanente),
        "comensales_en_espera": _serie(lambda r: r.comensales_en_espera),
        "tiempo_total": _serie(lambda r: r.tiempo_total),
    }

    # KPIs economico-financieros por replica (req. 3): se agregan con el mismo IC 95%.
    finanzas = [_finanzas_replica(r, cfg) for r in replicas]
    for clave in ("unidades_vendidas", "ingresos", "costo_variable", "costo_fijo",
                  "costo_total", "rentabilidad"):
        metricas[clave] = [f[clave] for f in finanzas]

    agg = ProductionAggregated(n_replicas=n_replicas, config=cfg)
    for clave, valores in metricas.items():
        ic = intervalo_confianza_95(valores)   # t-Student o Normal segun n (req. 1 y 2).
        agg.medias[clave] = ic.media
        agg.desvios[clave] = statistics.pstdev(valores) if len(valores) > 1 else 0.0
        agg.ic_inf[clave] = ic.inf
        agg.ic_sup[clave] = ic.sup
        agg.muestras[clave] = valores

    # Trazabilidad del metodo de IC e interarribos para la validacion del generador.
    agg.cuantil_ic, agg.metodo_ic, agg.gl_ic = cuantil_ic95(n_replicas)
    agg.n_muestral = n_replicas
    agg.interarribos = [dt for r in replicas for dt in r.interarribos]

    rep0 = replicas[0]
    agg.serie_t = rep0.serie_t
    agg.serie_stock = rep0.serie_stock
    return agg


# ---------------------------------------------------------------------------
# DIAGNOSTICO DE VIABILIDAD ORGANIZACIONAL
# ---------------------------------------------------------------------------
def generar_diagnostico(agg: ProductionAggregated) -> str:
    """Texto interpretativo sobre la viabilidad de la cadena de produccion."""
    cfg = agg.config
    producidas = agg.media("tartaletas_producidas")
    espera_max = agg.media("espera_maxima")
    en_espera = agg.media("comensales_en_espera")
    remanente = agg.media("stock_remanente")
    fab = agg.media("tiempo_fab_promedio")
    ingresos = agg.media("ingresos")
    costo_total = agg.media("costo_total")
    rentabilidad = agg.media("rentabilidad")
    vendidas = agg.media("unidades_vendidas")
    payback = agg.payback_jornadas

    lineas: List[str] = []
    lineas.append(f"DIAGNOSTICO DE PRODUCCION (promedio de {agg.n_replicas} corrida/s)")
    lineas.append("-" * 64)
    lineas.append(
        f"Configuracion: {cfg.operarios} operario/s y horno de {cfg.horno_slots} "
        f"lote/s simultaneo/s. Cada lote rinde {TARTALETAS_POR_LOTE} tartaletas.")
    lineas.append(
        f"Se fabricaron {producidas:.0f} tartaletas para {cfg.n_comensales} comensales; "
        f"tiempo medio de fabricacion de un lote: {fab:.1f} min.")

    if en_espera < 1 and espera_max < 1:
        lineas.append(
            "La cadena ABASTECE con holgura: practicamente ningun comensal espera por "
            "alimento y siempre hay stock en el mostrador.")
    elif espera_max <= 5:
        lineas.append(
            f"La cadena es VIABLE con tension leve: hasta {en_espera:.0f} comensales "
            f"esperan, con una espera maxima de {espera_max:.1f} min (tolerable).")
    else:
        lineas.append(
            f"CUELLO DE BOTELLA DE PRODUCCION: {en_espera:.0f} comensales quedan en la "
            f"cola de espera por alimento y la espera maxima trepa a {espera_max:.1f} min. "
            "La cocina no acompania el ritmo de consumo.")

    lineas.append(f"Stock remanente al cierre: {remanente:.0f} tartaletas.")

    # Analisis economico-financiero (escenario de emprendimiento - Parte 2 del TPI).
    lineas.append("")
    lineas.append("ANALISIS ECONOMICO (escenario de venta):")
    lineas.append(
        f"Con {vendidas:.0f} tartaletas vendidas a ${cfg.precio_venta_unidad:,.0f} c/u, "
        f"los ingresos de la jornada son ${ingresos:,.0f} y los costos totales "
        f"${costo_total:,.0f} (materia prima + operarios).")
    if rentabilidad > 0:
        lineas.append(
            f"Rentabilidad proyectada por jornada: ${rentabilidad:,.0f} (POSITIVA). "
            f"La inversion inicial de ${cfg.inversion_inicial:,.0f} se recupera en "
            f"aproximadamente {payback:.1f} jornadas/eventos.")
    else:
        lineas.append(
            f"Rentabilidad proyectada por jornada: ${rentabilidad:,.0f} (NEGATIVA). "
            f"Con esta configuracion la jornada NO es rentable y la inversion de "
            f"${cfg.inversion_inicial:,.0f} no se recupera: revise precio, escala o costos.")

    lineas.append("")
    lineas.append("RECOMENDACIONES:")
    if espera_max > 5:
        lineas.append("  - Sumar operarios o ampliar la capacidad del horno para subir "
                      "la tasa de produccion por hora.")
        lineas.append("  - Pre-cocinar lotes antes de abrir el evento (stock inicial "
                      "mayor) para absorber el pico inicial de arribos.")
    if remanente > 2 * TARTALETAS_POR_LOTE:
        lineas.append("  - Hay sobreproduccion: se puede reducir un recurso o ajustar el "
                      "tamanio de lote para evitar desperdicio de alimento.")
    if en_espera < 1 and remanente <= 2 * TARTALETAS_POR_LOTE:
        lineas.append("  - Configuracion equilibrada: mantenerla para el evento real.")
    if rentabilidad <= 0:
        lineas.append("  - Revisar el modelo de negocio: subir el precio de venta sugerido, "
                      "comprar materia prima a escala o reducir el costo fijo de operarios "
                      "para volver rentable la jornada.")
    elif payback > 0 and payback != float("inf"):
        lineas.append(f"  - Modelo de venta viable: con la demanda simulada, el "
                      f"emprendimiento recupera la inversion en ~{payback:.0f} jornadas.")
    return "\n".join(lineas)
