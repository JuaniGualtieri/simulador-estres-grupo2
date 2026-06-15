# -*- coding: utf-8 -*-
"""
================================================================================
 sim/production_sim.py  ::  MOTOR MATEMATICO PURO - PESTANIA 2 (PRODUCCION & STOCK)
 Trabajo Practico Integrador Intercatedra - Grupo 2
 Asignatura: Modelos y Simulacion - 4to Anio - Ingenieria en Sistemas de Informacion
================================================================================

OBJETIVO DEL MODELO 2 (CADENA DE PRODUCCION DE UNA FERIA / STAND REAL)
---------------------------------------------------------------------
Modelar mediante SIMULACION DE EVENTOS DISCRETOS (SimPy) el funcionamiento REAL de
un stand de feria que vende la tartaleta vegetal: la cocina abre con un STOCK INICIAL
de pre-produccion (algunas bandejas ya horneadas y calientes) y va REPONIENDO por
demanda a medida que los comensales compran. NO se hornean 64 tartaletas de golpe:
se sigue una politica de reorden por punto critico, como en un local de verdad.

DEFINICION TEORICA
------------------
* ENTIDADES ........... Comensales (compran 1 tartaleta ENTERA c/u) y Ordenes de
                        horneado (cada lote = 8 tartaletas ENTERAS).
* RECURSOS ............ Operarios de cocina (simpy.Resource) y ranuras del Horno
                        (simpy.Resource = lotes maximos en paralelo).
* VARIABLE DE ESTADO .. Stock de tartaletas listas en el mostrador (simpy.Container)
                        + comensales en la fila de espera (bloqueo de Container.get).

FLUJO REAL (POLITICA DE REORDEN POR PUNTO CRITICO)
--------------------------------------------------
1. La jornada ABRE (t = 0, 08:15) con `stock_inicial_lotes` bandejas ya listas
   (por defecto 2 lotes = 16 tartaletas calientes de pre-produccion).
2. Los 64 comensales ARRIBAN segun las marcas de tiempo REALES del stand
   (sim/arribos_reales.py, derivadas de horas.xlsx). Cada uno retira 1 tartaleta
   ENTERA: si hay stock, su espera es 0; si no, entra a la fila hasta que salga
   una nueva bandeja del horno.
3. Cuando la POSICION DE INVENTARIO (stock + lo que ya se esta horneando) cae a/por
   debajo del PUNTO DE REORDEN (8 unidades), la cocina dispara una nueva orden de
   horneado de un lote de 8, siempre que no se haya comprometido ya toda la demanda.

Cada lote recorre tres etapas de la Planta Piloto (tiempos de receta con una leve
variabilidad operativa realista, lo que ademas da dispersion entre replicas para el
IC 95%): Etapa 1 Coccion del Relleno ~30 min (operario) -> Etapa 2 Horneado de la
Masa ~15 min (horno) -> Etapa 3 Armado y Gratinado ~10 min (horno, armado solapado).

REGLA DE DESPACHO ENTERO
------------------------
Cada comensal consume estrictamente UNA (1) tartaleta ENTERA (sin fraccionar): la
demanda total es de 64 tartaletas completas para los 64 comensales.
================================================================================
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

import numpy as np
import simpy

from sim.arribos_reales import ARRIBOS_MIN, DURACION_JORNADA_MIN, interarribos_min
from sim.estadistica import cuantil_ic95, intervalo_confianza_95

# ---------------------------------------------------------------------------
# PARAMETROS DEL MODELO DE PRODUCCION (tiempos en MINUTOS)
# ---------------------------------------------------------------------------
N_COMENSALES = len(ARRIBOS_MIN)     # 64 comensales reales (cada uno compra 1 tartaleta ENTERA).
MEDIA_ARRIBO_MIN = 79.3 / 60.0      # 1,32 min: media TEORICA de la Exponencial de arribos (V&V).
DEMANDA_TARTALETAS = N_COMENSALES   # Regla de despacho ENTERO: 64 tartaletas completas para 64 comensales.

# --- Lote/tanda FIJO y tiempos de las tres etapas (medias de la Planta Piloto) ---
TARTALETAS_POR_LOTE = 8        # Cada bandeja/lote rinde 8 tartaletas ENTERAS.
TIEMPO_RELLENO = 30.0          # Etapa 1: Coccion del Relleno ~30 min (requiere operario).
TIEMPO_HORNEADO_MASA = 15.0    # Etapa 2: Horneado de la Masa ~15 min (requiere horno).
TIEMPO_GRATINADO = 10.0        # Etapa 3: Armado y Gratinado ~10 min (horno; armado solapado dentro).
TIEMPO_CICLO_LOTE = (TIEMPO_RELLENO + TIEMPO_HORNEADO_MASA
                     + TIEMPO_GRATINADO)  # 55 min: camino critico de UNA bandeja sin contienda.
SIGMA_ETAPA_PCT = 0.07         # Variabilidad operativa (+/-7%) de cada etapa: realismo + dispersion para IC.

# --- Politica de inventario del stand (reorden por punto critico) ---
STOCK_INICIAL_LOTES = 2        # Pre-produccion al abrir: 2 lotes = 16 tartaletas calientes.
UMBRAL_REORDEN = TARTALETAS_POR_LOTE  # Punto de reorden: al caer a <=8 listas, se hornea otra bandeja.

SEED_BASE = 2026             # Semilla base (anio del evento) para reproducibilidad.
N_REPLICAS_DEFAULT = 20      # Replicas para estabilizar los KPIs escalares.

# ---------------------------------------------------------------------------
# PARAMETROS ECONOMICO-FINANCIEROS (escenario de emprendimiento, en pesos ARS)
# ---------------------------------------------------------------------------
COSTO_MP_LOTE = 7200.0          # Costo de materia prima por bandeja de 8 unidades (~$900 c/u).
PRECIO_VENTA_UNIDAD = 3000.0    # Precio de venta sugerido por tartaleta al publico.
COSTO_OPERARIO_JORNADA = 15000.0  # Costo fijo por operario por jornada de produccion.
INVERSION_INICIAL = 500000.0    # Inversion inicial en equipamiento de cocina (horno, mesada, utensilios).

# Valores por defecto de los sliders/campos de la Pestania 2.
SLIDER_DEFAULTS = {
    "operarios": 2,             # Rango [1 - 5].
    "horno": 2,                 # Rango [1 - 4] lotes simultaneos.
    "stock_inicial_lotes": STOCK_INICIAL_LOTES,  # Rango [0 - 4] bandejas pre-horneadas.
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
    stock_inicial_lotes: int = STOCK_INICIAL_LOTES  # Bandejas de pre-produccion al abrir (SLIDER [0-4]).
    n_comensales: int = N_COMENSALES
    # --- Parametros economico-financieros (escenario de emprendimiento) ---
    costo_mp_lote: float = COSTO_MP_LOTE          # Costo materia prima por lote.
    precio_venta_unidad: float = PRECIO_VENTA_UNIDAD  # Precio de venta por tartaleta.
    costo_operario_jornada: float = COSTO_OPERARIO_JORNADA  # Costo fijo por operario/jornada.
    inversion_inicial: float = INVERSION_INICIAL  # Inversion inicial en equipamiento.

    @property
    def stock_inicial_unidades(self) -> int:
        return self.stock_inicial_lotes * TARTALETAS_POR_LOTE

    @property
    def tasa_arribo_media(self) -> float:
        """Media TEORICA de la Exponencial de arribos (min), para la validacion V&V."""
        return MEDIA_ARRIBO_MIN


# ---------------------------------------------------------------------------
# ESTRUCTURAS DE RESULTADOS
# ---------------------------------------------------------------------------
@dataclass
class ProductionReplicaResult:
    """KPIs y serie de stock de UNA corrida de la cadena de produccion."""
    tartaletas_producidas: int = 0       # Unidades horneadas durante la jornada (sin contar stock inicial).
    lotes_producidos: int = 0            # Bandejas horneadas durante la jornada.
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
class _ContenedorMonitoreado(simpy.Container):
    """simpy.Container que registra su nivel en CADA cambio REAL (put/get exitoso).

    Interceptar `_do_put` / `_do_get` (los unicos puntos donde el nivel cambia de
    verdad en SimPy) garantiza capturar cada transicion en el instante exacto en que
    ocurre: el +8 cuando una bandeja sale del horno y el -1 de cada compra. Asi la
    serie reconstruye una ESCALERA fiel del stock, sin perder los picos de reposicion.
    La logica del modelo (esperas, servidos, KPIs) no se altera: solo se agrega el
    efecto colateral de muestreo.
    """

    def __init__(self, env: simpy.Environment, registrar: "Callable[[], None]",
                 *args, **kwargs):
        super().__init__(env, *args, **kwargs)
        self._registrar = registrar

    def _do_put(self, event):
        ok = super()._do_put(event)
        if ok:
            self._registrar()
        return ok

    def _do_get(self, event):
        ok = super()._do_get(event)
        if ok:
            self._registrar()
        return ok


class StockMonitor:
    """Envuelve el Container del stock y registra su nivel en cada cambio.

    Reconstruye la serie temporal (tiempo, nivel) que alimenta el grafico de evolucion
    del stock, pintando en rojo los tramos en que el mostrador queda en cero (faltante).
    """

    def __init__(self, env: simpy.Environment, resultado: ProductionReplicaResult,
                 stock_inicial: int):
        self.env = env
        self.resultado = resultado
        self.container = _ContenedorMonitoreado(
            env, self._registrar, init=stock_inicial, capacity=float("inf"))
        self._registrar()  # Nivel inicial en t=0.

    def _registrar(self) -> None:
        self.resultado.serie_t.append(self.env.now)
        self.resultado.serie_stock.append(int(self.container.level))

    def reponer(self, cantidad: int):
        """Incorpora una bandeja recien horneada al mostrador (el Container registra el nivel)."""
        yield self.container.put(cantidad)

    def retirar_una(self):
        """El comensal compra 1 tartaleta (se bloquea si el stock esta en 0)."""
        yield self.container.get(1)


# ---------------------------------------------------------------------------
# PROCESOS GENERADORES SimPy
# ---------------------------------------------------------------------------
def _tiempo_etapa(rng: np.random.Generator, media: float) -> float:
    """Duracion de una etapa: media de receta con una leve variabilidad operativa."""
    return max(0.5, float(rng.normal(media, media * SIGMA_ETAPA_PCT)))


def proceso_lote(env: simpy.Environment, monitor: StockMonitor,
                 operarios: simpy.Resource, horno: simpy.Resource,
                 cfg: ProductionConfig, rng: np.random.Generator, estado: dict,
                 reordenar: "Callable[[], None]"):
    """Ciclo de horneado de UNA bandeja de 8 tartaletas por las tres etapas.

    La dinamica entre corridas proviene de la contienda por los recursos (operarios y
    horno) y de la leve variabilidad de los tiempos de receta.
    """
    resultado = monitor.resultado
    t_inicio = env.now

    # Etapa 1 (Coccion del Relleno): requiere un operario (~30 min).
    with operarios.request() as op:
        yield op
        yield env.timeout(_tiempo_etapa(rng, TIEMPO_RELLENO))

    # Etapa 2 (Horneado de la Masa): requiere una ranura del horno (~15 min).
    with horno.request() as ranura:
        yield ranura
        yield env.timeout(_tiempo_etapa(rng, TIEMPO_HORNEADO_MASA))

    # Etapa 3 (Armado y Gratinado del Queso): requiere el horno (~10 min, armado solapado).
    with horno.request() as ranura:
        yield ranura
        yield env.timeout(_tiempo_etapa(rng, TIEMPO_GRATINADO))

    # Bandeja terminada: se reponen 8 tartaletas ENTERAS al mostrador de despacho.
    yield from monitor.reponer(TARTALETAS_POR_LOTE)
    resultado.tartaletas_producidas += TARTALETAS_POR_LOTE
    resultado.lotes_producidos += 1
    resultado.tiempos_fabricacion.append(env.now - t_inicio)
    estado["en_produccion"] -= 1
    reordenar()  # Al liberar capacidad, evalua si conviene hornear otra bandeja.


def proceso_comensal(env: simpy.Environment, monitor: StockMonitor,
                     resultado: ProductionReplicaResult, t_arribo: float,
                     reordenar: "Callable[[], None]"):
    """Comensal que arriba en su instante REAL e intenta comprar una tartaleta.

    Si hay stock, la retira al instante (espera 0); si no, queda en la fila de espera
    (bloqueo del Container.get) hasta que una bandeja reponga el mostrador. Tras
    comprar, dispara la evaluacion de la politica de reorden de la cocina.
    """
    yield env.timeout(t_arribo)            # Llega en su marca de tiempo real.
    t0 = env.now
    yield from monitor.retirar_una()
    resultado.esperas.append(env.now - t0)
    resultado.servidos += 1
    reordenar()                            # Revisa si hay que hornear otra bandeja.


# ---------------------------------------------------------------------------
# CORRIDA DE UNA REPLICA Y AGREGACION DE EXPERIMENTOS
# ---------------------------------------------------------------------------
def correr_replica(cfg: ProductionConfig, semilla: int) -> ProductionReplicaResult:
    """Ejecuta UNA jornada completa del stand (politica de reorden) y devuelve sus KPIs."""
    rng = np.random.default_rng(semilla)
    env = simpy.Environment()
    resultado = ProductionReplicaResult()
    stock_inicial = cfg.stock_inicial_unidades
    monitor = StockMonitor(env, resultado, stock_inicial)
    operarios = simpy.Resource(env, capacity=cfg.operarios)
    horno = simpy.Resource(env, capacity=cfg.horno_slots)
    demanda = cfg.n_comensales

    # Estado de la politica de reorden: unidades comprometidas (stock inicial + lo que
    # ya se mando a hornear) y bandejas actualmente en el horno.
    estado = {"committed": stock_inicial, "en_produccion": 0}

    def _lanzar_lote() -> None:
        estado["committed"] += TARTALETAS_POR_LOTE
        estado["en_produccion"] += 1
        env.process(proceso_lote(env, monitor, operarios, horno, cfg, rng, estado,
                                 _quizas_reordenar))

    def _quizas_reordenar() -> None:
        # Politica de reorden (s, S) por demanda: cuando el stock disponible cae al
        # punto critico (<= UMBRAL_REORDEN), la cocina manda a hornear las bandejas que
        # falten para cubrir la demanda total -sin sobreproducir-, manteniendo a la vez
        # el pipeline lleno hasta la capacidad de los recursos (operarios + horno). Los
        # propios recursos limitan cuantas bandejas avanzan en paralelo, asi que mas
        # operarios u horno mas grande aceleran la reposicion (y bajan las esperas).
        cap_pipeline = cfg.operarios + cfg.horno_slots
        while (estado["committed"] < demanda
               and monitor.container.level <= UMBRAL_REORDEN
               and estado["en_produccion"] < cap_pipeline):
            _lanzar_lote()

    # Arranque: si abrimos con poco stock, ya disparamos las primeras bandejas.
    _quizas_reordenar()
    # Comensales con sus marcas de tiempo REALES (primeros `demanda` arribos).
    for t_arribo in ARRIBOS_MIN[:demanda]:
        env.process(proceso_comensal(env, monitor, resultado, t_arribo, _quizas_reordenar))

    env.run()  # Corre hasta servir a todos y terminar todas las bandejas en curso.

    resultado.tiempo_total = env.now
    resultado.stock_remanente = int(monitor.container.level)
    resultado.interarribos = interarribos_min()  # Gaps reales para la V&V del modelo.
    # Punto final para cerrar la curva escalonada del stock.
    resultado.serie_t.append(env.now)
    resultado.serie_stock.append(int(monitor.container.level))
    return resultado


def _finanzas_replica(r: ProductionReplicaResult, cfg: ProductionConfig) -> Dict[str, float]:
    """Indicadores economicos (ARS) de UNA jornada simulada (escenario de venta).

    Se venden las tartaletas efectivamente retiradas por los comensales. El costo de
    materia prima se imputa sobre TODAS las bandejas que existieron en la jornada: las
    horneadas en vivo MAS las de pre-produccion (stock inicial), porque ambas
    consumieron insumos.
    """
    unidades_vendidas = float(r.servidos)
    ingresos = unidades_vendidas * cfg.precio_venta_unidad
    lotes_totales = r.lotes_producidos + cfg.stock_inicial_lotes
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
    """Ejecuta N replicas de la jornada del stand, agrega los KPIs (media + IC 95%)
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
    agg.interarribos = list(replicas[0].interarribos)

    rep0 = replicas[0]
    agg.serie_t = rep0.serie_t
    agg.serie_stock = rep0.serie_stock
    return agg


# ---------------------------------------------------------------------------
# DIAGNOSTICO DE VIABILIDAD ORGANIZACIONAL
# ---------------------------------------------------------------------------
def generar_diagnostico(agg: ProductionAggregated) -> str:
    """Texto interpretativo sobre la viabilidad de la cadena de produccion del stand."""
    cfg = agg.config
    producidas = agg.media("tartaletas_producidas")
    espera_max = agg.media("espera_maxima")
    espera_prom = agg.media("espera_promedio")
    en_espera = agg.media("comensales_en_espera")
    remanente = agg.media("stock_remanente")
    fab = agg.media("tiempo_fab_promedio")
    ingresos = agg.media("ingresos")
    costo_total = agg.media("costo_total")
    rentabilidad = agg.media("rentabilidad")
    vendidas = agg.media("unidades_vendidas")
    payback = agg.payback_jornadas

    lineas: List[str] = []
    lineas.append(f"DIAGNOSTICO DE PRODUCCION DEL STAND (promedio de {agg.n_replicas} corrida/s)")
    lineas.append("-" * 64)
    lineas.append(
        f"Configuracion: {cfg.operarios} operario/s, horno de {cfg.horno_slots} "
        f"bandeja/s en paralelo y apertura con {cfg.stock_inicial_lotes} lote/s de "
        f"pre-produccion ({cfg.stock_inicial_unidades} tartaletas calientes).")
    lineas.append(
        f"Politica de reorden: se hornea una bandeja nueva de {TARTALETAS_POR_LOTE} "
        f"unidades cuando el stock disponible cae a {UMBRAL_REORDEN} o menos. Se "
        f"hornearon {producidas:.0f} tartaletas en vivo durante la jornada; tiempo "
        f"medio de ciclo de una bandeja: {fab:.1f} min.")
    lineas.append(
        f"Los {cfg.n_comensales} comensales arribaron segun los horarios reales del "
        f"stand (jornada de {DURACION_JORNADA_MIN:.0f} min).")

    if en_espera < 1 and espera_max < 1:
        lineas.append(
            "El stand ABASTECE con holgura: practicamente ningun comensal espera; el "
            "stock inicial y la reposicion alcanzan el ritmo de compra.")
    elif espera_max <= 5:
        lineas.append(
            f"El stand es VIABLE con tension leve: hasta {en_espera:.0f} comensales "
            f"esperan, con una espera maxima de {espera_max:.1f} min (tolerable) y una "
            f"espera promedio de {espera_prom:.1f} min.")
    else:
        lineas.append(
            f"CUELLO DE BOTELLA DE PRODUCCION: {en_espera:.0f} comensales hacen fila, "
            f"con una espera maxima de {espera_max:.1f} min (promedio {espera_prom:.1f} "
            "min). La cocina no acompania el ritmo de compra del pico.")

    lineas.append(f"Stock remanente al cierre: {remanente:.0f} tartaletas.")

    # Analisis economico-financiero (escenario de emprendimiento - Parte 2 del TPI).
    lineas.append("")
    lineas.append("ANALISIS ECONOMICO (escenario de venta):")
    lineas.append(
        f"Con {vendidas:.0f} tartaletas vendidas a ${cfg.precio_venta_unidad:,.0f} c/u, "
        f"los ingresos de la jornada son ${ingresos:,.0f} y los costos totales "
        f"${costo_total:,.0f} (materia prima de las bandejas + operarios).")
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
        lineas.append("  - Abrir con mas stock de pre-produccion para absorber el pico "
                      "inicial de compras de la feria.")
        lineas.append("  - Sumar operarios o ampliar la capacidad del horno para acelerar "
                      "la reposicion de bandejas.")
    if remanente > 2 * TARTALETAS_POR_LOTE:
        lineas.append("  - Hay sobreproduccion: reducir el stock inicial o algun recurso "
                      "para evitar desperdicio de alimento.")
    if en_espera < 1 and remanente <= 2 * TARTALETAS_POR_LOTE:
        lineas.append("  - Configuracion equilibrada: mantenerla para el evento real.")
    if rentabilidad <= 0:
        lineas.append("  - Revisar el modelo de negocio: subir el precio de venta sugerido, "
                      "comprar materia prima a escala o reducir el costo fijo de operarios.")
    elif payback > 0 and payback != float("inf"):
        lineas.append(f"  - Modelo de venta viable: con la demanda simulada, el "
                      f"emprendimiento recupera la inversion en ~{payback:.0f} jornadas.")
    return "\n".join(lineas)
