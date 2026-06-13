# -*- coding: utf-8 -*-
"""
================================================================================
 sim/server_sim.py  ::  MOTOR MATEMATICO PURO - PESTANIA 1 (ESTRES DE SERVIDOR)
 Trabajo Practico Integrador Intercatedra - Grupo 2
 Asignatura: Modelos y Simulacion - 4to Anio - Ingenieria en Sistemas de Informacion
================================================================================

OBJETIVO DEL MODELO
-------------------
Modelar mediante SIMULACION DE EVENTOS DISCRETOS (libreria SimPy) el comportamiento
del sistema web estatico (deployado en Vercel) que se conecta de forma DIRECTA
(Client-to-Cloud) a una base de datos PostgreSQL alojada en Supabase, atravesando su
"Connection Pooler". El fin es PREDECIR el comportamiento del pooler frente a rafagas
de comensales concurrentes y estimar la PROBABILIDAD de errores de timeout (HTTP 504)
provocados por la red Wi-Fi inestable de la Planta Piloto.

REGLA CRITICA DE PRESERVACION
-----------------------------
Este modulo AISLA el motor matematico original (antes monolito CustomTkinter). Las
distribuciones estadisticas, la logica de retransmision TCP / Wi-Fi degradado (conexion
"zombie"), el calculo de Intervalos de Confianza del 95% y los diagnosticos NO se
modifican: solo se parametrizan (capacidad del pool, comensales y latencia llegan por
slider) y se exponen como funciones puras que retornan datos crudos para la vista web.

DEFINICION FORMAL DEL SISTEMA
-----------------------------
* ENTIDADES ........ Comensales virtuales (jueces no entrenados) que usan la web.
* RECURSOS ......... Canales del Connection Pooler de Supabase. Limite del plan
                     gratuito = 60 conexiones concurrentes (parametrizable por slider)
                     -> simpy.Resource(pool_capacity).
* VARIABLES DE ESTADO  Conexiones HTTP activas, tamanio de la cola hacia la BD,
                       cantidad de peticiones rechazadas/caidas (504 y de red).
* EVENTOS .......... (1) Arribo del comensal, (2) inicio del llenado del formulario,
                     (3) click en enviar -> peticion HTTP (toma cupo del pooler),
                     (4) persistencia/confirmacion de escritura en PostgreSQL.

DISTRIBUCIONES ESTADISTICAS (segun consigna de catedra)
-------------------------------------------------------
* Tasa de Arribos ......... EXPONENCIAL (llegada de los comensales en la jornada).
* Tiempo de Llenado ....... UNIFORME(45, 90) s (justificado por las 12 preguntas de la encuesta).
* Tiempo de Respuesta /
  retencion de conexion .... NORMAL(media, desvio) por escenario (latencia hacia
                             Supabase). El "Esperado" usa NORMAL(0,25 s; 0,05 s).

MODELO DEL CUELLO DE BOTELLA (CONEXIONES COLGADAS)
--------------------------------------------------
Bajo Wi-Fi degradada una fraccion de las peticiones sufre retransmisiones TCP que
EXTIENDEN EXPONENCIALMENTE el tiempo de retencion del socket. El cliente percibe el
HTTP 504 al cumplirse GATEWAY_TIMEOUT y REINTENTA (abre otra conexion), pero el socket
original NO se libera: sigue ocupando un cupo del pooler hasta agotar las
retransmisiones (proceso "zombie"). Asi, conexiones colgadas + reintentos se superponen
y la curva de conexiones ocupadas crece de forma dinamica y realista.
================================================================================
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

import numpy as np
import simpy

from sim.estadistica import (cuantil_ic95, intervalo_confianza_95)

# =============================================================================
# DOS NUMEROS QUE NO HAY QUE CONFUNDIR (aclaracion para la catedra)
# -----------------------------------------------------------------------------
# * POOLER_CAPACITY = 60  -> LIMITE FISICO / DE HARDWARE. Cantidad MAXIMA de
#   conexiones SIMULTANEAS que el Connection Pooler de Supabase (plan gratuito)
#   acepta en un mismo instante. Se modela como simpy.Resource(capacity); cuando se
#   agota, las nuevas peticiones hacen COLA. Ahora es PARAMETRIZABLE por slider
#   (rango 10-200), pero su valor por defecto sigue siendo 60.
#
# * N_REPLICAS (p. ej. 30) -> CANTIDAD DE EXPERIMENTOS. Cuantas veces se REPITE
#   COMPLETA la simulacion del dia del evento, cada vez con otra semilla, para
#   PROMEDIAR los KPIs y reducir la varianza (Ley de los Grandes Numeros). NO son
#   usuarios ni conexiones: son corridas independientes del modelo.
# =============================================================================
POOLER_CAPACITY = 60          # LIMITE por defecto de conexiones simultaneas (hardware).
GATEWAY_TIMEOUT = 8.0         # seg. Umbral de timeout del gateway/HTTP -> dispara 504.
N_PREGUNTAS_ENCUESTA = 12     # Campos obligatorios de la encuesta real (8 sliders + 2 Si/No + 2 datos).
FILL_TIME_MIN = 45.0          # seg. Tiempo minimo de llenado (Uniforme).
FILL_TIME_MAX = 90.0          # seg. Tiempo maximo de llenado (Uniforme).
BACKOFF_MIN = 0.8             # seg. Espera minima del comensal antes de reintentar.
BACKOFF_MAX = 3.0             # seg. Espera maxima del comensal antes de reintentar.
SEED_BASE = 2026              # Semilla base (anio del evento) para reproducibilidad.
N_REPLICAS_DEFAULT = 30       # Replicas por defecto para estabilizar promedios.
# El cuantil del IC 95% (t-Student para n<30, Normal Z=1,96 para n>=30) y su seleccion
# automatica viven en sim/estadistica.py para no duplicar la matematica del muestreo.

# =============================================================================
# CASO REAL: REGISTROS DEL STAND EN LA FACULTAD (jornada del 11/06/2026)
# -----------------------------------------------------------------------------
# Parametros medidos en el stand: 64 comensales reales atendidos entre las 08:19:08
# y las 09:42:25 (duracion total = 83,3 min). El analisis de los timestamps de arribo
# arrojo una EXPONENCIAL con media de 1,32 min (79,3 s) entre llegadas, respaldada por
# un desvio estandar empirico de 79,1 s (que en una Exponencial debe coincidir con la
# media, lo que valida el ajuste). El generador se calibra con la media: como la
# propiedad tasa_arribo_media = ventana / comensales, fijamos la ventana en
# 79,3 s x 64 = 5075,2 s para que E(X) sea exactamente 79,3 s = 1,32 min.
# =============================================================================
CASO_REAL_N_COMENSALES = 64                                   # Comensales reales del stand.
CASO_REAL_MEDIA_ARRIBO_SEG = 79.3                             # Media Exponencial empirica (s) = 1,32 min.
CASO_REAL_DESVIO_ARRIBO_SEG = 79.1                            # Desvio estandar empirico (s) (≈ media).
CASO_REAL_DURACION_MIN = 83.3                                 # Duracion real (08:19:08 -> 09:42:25).
CASO_REAL_VENTANA_SEG = CASO_REAL_MEDIA_ARRIBO_SEG * CASO_REAL_N_COMENSALES  # 5075,2 s.

# Etiquetas de resultado de un intento de envio.
EXITO = "EXITO"
ERR_504_POOL = "ERR_504_POOL"      # 504 por SATURACION del pooler (no hubo cupo a tiempo).
ERR_504_LATENCIA = "ERR_504_LAT"   # 504 por conexion COLGADA (Wi-Fi inestable).
ERR_RED = "ERR_RED"                # Error de red puntual (probabilidad base).


# ---------------------------------------------------------------------------
# CONFIGURACION DE ESCENARIOS / PRESETS
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScenarioConfig:
    """Parametros que definen una corrida de simulacion del servidor."""
    nombre: str
    descripcion: str
    n_comensales: int           # Cantidad de jueces que envian encuesta (SLIDER).
    pool_capacity: int          # Limite de conexiones simultaneas del pooler (SLIDER).
    ventana_arribos_seg: float  # Ventana temporal en la que llegan los arribos (seg).
    latencia_media: float       # Media de la NORMAL de respuesta cloud (seg) (SLIDER ms).
    latencia_desvio: float      # Desvio de la NORMAL de respuesta cloud (seg).
    prob_cuelgue: float         # Prob. de que la conexion se "cuelgue" (cola pesada).
    cuelgue_media: float        # Media de la EXPONENCIAL del cuelgue extra (seg).
    prob_error_red: float       # Prob. base de error de red por intento.
    max_reintentos: int         # Reintentos del comensal ante un fallo.

    @property
    def tasa_arribo_media(self) -> float:
        """Media de la EXPONENCIAL de tiempos entre arribos (seg)."""
        return self.ventana_arribos_seg / self.n_comensales


# Presets de la consigna. El boton "Caso Real" reproduce los registros del stand; los
# botones "Optimista / Esperado / Pesimista" son escenarios contrafacticos (mismos 64
# comensales reales bajo otras condiciones de red) que reubican los sliders en una
# configuracion logica; el usuario luego puede ajustarlos a mano.
PRESET_CASO_REAL = "Caso Real: Stand Facultad"
PRESETS: Dict[str, ScenarioConfig] = {
    PRESET_CASO_REAL: ScenarioConfig(
        nombre=PRESET_CASO_REAL,
        descripcion=(
            "Preset OFICIAL calibrado con los registros del stand en la Facultad "
            "(11/06/2026, de 08:19:08 a 09:42:25 = 83,3 min). Los 64 comensales reales "
            "arribaron segun una EXPONENCIAL de media 1,32 min (79,3 s) entre llegadas, "
            "respaldada por un desvio estandar empirico de 79,1 s. Wi-Fi del campus "
            "estable con microcortes esporadicos que los reintentos recuperan."
        ),
        n_comensales=CASO_REAL_N_COMENSALES,
        pool_capacity=POOLER_CAPACITY,
        ventana_arribos_seg=CASO_REAL_VENTANA_SEG,  # E(X) = 79,3 s = 1,32 min exactos.
        latencia_media=0.25,              # 250 ms medidos en el campus.
        latencia_desvio=0.05,
        prob_cuelgue=0.03,
        cuelgue_media=2.0,
        prob_error_red=0.01,
        max_reintentos=2,
    ),
    "Optimista": ScenarioConfig(
        nombre="Optimista",
        descripcion=(
            "Contrafactico: los 64 comensales reales arribando espaciados a lo largo de "
            "una jornada de ~5 h. Wi-Fi de alta velocidad (latencia ~100 ms) y 0% de "
            "errores. El pooler trabaja holgado."
        ),
        n_comensales=CASO_REAL_N_COMENSALES,
        pool_capacity=POOLER_CAPACITY,
        ventana_arribos_seg=5 * 3600,     # 5 horas.
        latencia_media=0.10,              # 100 ms.
        latencia_desvio=0.02,
        prob_cuelgue=0.0,
        cuelgue_media=0.0,
        prob_error_red=0.0,
        max_reintentos=1,
    ),
    "Esperado": ScenarioConfig(
        nombre="Esperado",
        descripcion=(
            "Contrafactico: 64 comensales con transito fluido durante ~2,5 h. Internet "
            "promedio NORMAL(0,25 s; 0,05 s) como pide la catedra. Pooler estable con "
            "fallos esporadicos que los reintentos recuperan."
        ),
        n_comensales=CASO_REAL_N_COMENSALES,
        pool_capacity=POOLER_CAPACITY,
        ventana_arribos_seg=int(2.5 * 3600),  # 2,5 horas.
        latencia_media=0.25,                  # 250 ms (consigna).
        latencia_desvio=0.05,
        prob_cuelgue=0.03,
        cuelgue_media=2.0,
        prob_error_red=0.01,
        max_reintentos=2,
    ),
    "Pesimista": ScenarioConfig(
        nombre="Pesimista",
        descripcion=(
            "Contrafactico destructivo: los 64 comensales envian dentro de una ventana "
            "critica de 2 minutos por aglomeracion. Wi-Fi degradada: las conexiones se "
            "CUELGAN (retransmisiones TCP) y se acumulan en el pooler -> rafaga dinamica "
            "de timeouts 504."
        ),
        n_comensales=CASO_REAL_N_COMENSALES,
        pool_capacity=POOLER_CAPACITY,
        ventana_arribos_seg=120,          # 2 minutos.
        latencia_media=0.90,              # Wi-Fi degradada.
        latencia_desvio=0.30,
        prob_cuelgue=0.80,                # 80% de las conexiones se cuelgan.
        cuelgue_media=18.0,               # retencion extra EXPONENCIAL de media 18 s.
        prob_error_red=0.05,
        max_reintentos=3,
    ),
}

# Valores por defecto de los sliders (coinciden con el preset oficial "Caso Real").
SLIDER_DEFAULTS = {
    "n_comensales": CASO_REAL_N_COMENSALES,   # 64 comensales reales. Rango [10 - 150].
    "pool_capacity": 60,                      # Rango [10 - 200].
    "latencia_ms": 250,                       # Rango [50 - 5000] ms (Caso Real / Esperado).
}


def construir_config(preset: str, n_comensales: int, pool_capacity: int,
                     latencia_ms: float) -> ScenarioConfig:
    """Crea un ScenarioConfig a partir del PRESET base y los valores de los sliders.

    El preset define el "regimen" de red (ventana de arribos, probabilidad y media de
    cuelgue por retransmision TCP, errores de red y reintentos). Los tres sliders
    sobrescriben los parametros expuestos al usuario: cantidad de comensales, limite del
    pool y latencia media (en ms -> seg). Asi la matematica original queda intacta pero
    el escenario se vuelve dinamico.
    """
    base = PRESETS[preset]
    return ScenarioConfig(
        nombre=base.nombre,
        descripcion=base.descripcion,
        n_comensales=int(n_comensales),
        pool_capacity=int(pool_capacity),
        ventana_arribos_seg=base.ventana_arribos_seg,
        latencia_media=max(0.001, float(latencia_ms) / 1000.0),
        latencia_desvio=base.latencia_desvio,
        prob_cuelgue=base.prob_cuelgue,
        cuelgue_media=base.cuelgue_media,
        prob_error_red=base.prob_error_red,
        max_reintentos=base.max_reintentos,
    )


# ---------------------------------------------------------------------------
# ESTRUCTURAS DE RESULTADOS
# ---------------------------------------------------------------------------
@dataclass
class ReplicaResult:
    """KPIs y series temporales de UNA corrida (replica) de la simulacion."""
    exitos: int = 0
    err_504_pool: int = 0
    err_504_latencia: int = 0
    err_red: int = 0
    encuestas_perdidas: int = 0          # No guardadas tras agotar reintentos.
    reintentos: int = 0
    espera_cola_total: float = 0.0       # Suma de esperas para promediar.
    espera_cola_n: int = 0               # Cantidad de esperas registradas.
    max_cola: int = 0                    # Tamanio maximo de la cola de la BD.
    pico_conexiones: int = 0             # Maximo de conexiones concurrentes.
    tiempo_total: float = 0.0            # Duracion simulada (seg).
    # Series temporales (solo se conservan para la corrida representativa).
    serie_t: List[float] = field(default_factory=list)
    serie_conexiones: List[int] = field(default_factory=list)
    serie_cola: List[int] = field(default_factory=list)
    # Tiempos entre arribos generados por la Exponencial (validacion V&V del generador).
    interarribos: List[float] = field(default_factory=list)

    @property
    def total_504(self) -> int:
        return self.err_504_pool + self.err_504_latencia

    @property
    def espera_cola_promedio(self) -> float:
        if self.espera_cola_n == 0:
            return 0.0
        return self.espera_cola_total / self.espera_cola_n


@dataclass
class AggregatedResult:
    """KPIs agregados (media, desvio e IC 95%) sobre N replicas + serie representativa."""
    escenario: str
    n_replicas: int
    pool_capacity: int = POOLER_CAPACITY
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
    interarribos: List[float] = field(default_factory=list)  # V&V del generador.
    serie_t: List[float] = field(default_factory=list)
    serie_conexiones: List[int] = field(default_factory=list)
    serie_cola: List[int] = field(default_factory=list)

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

    def media(self, clave: str) -> float:
        return self.medias.get(clave, 0.0)

    def desvio(self, clave: str) -> float:
        return self.desvios.get(clave, 0.0)

    def ic(self, clave: str) -> Tuple[float, float]:
        """Devuelve (limite_inferior, limite_superior) del IC 95% de un KPI."""
        return self.ic_inf.get(clave, 0.0), self.ic_sup.get(clave, 0.0)

    def muestra(self, clave: str) -> List[float]:
        return self.muestras.get(clave, [])


# ---------------------------------------------------------------------------
# MOTOR DE SIMULACION (EVENTOS DISCRETOS - SimPy)
# ---------------------------------------------------------------------------
class PoolerMonitor:
    """Envuelve el simpy.Resource del pooler y registra las variables de estado.

    Cada vez que cambia la ocupacion del pooler o el tamanio de la cola se toma una
    muestra (tiempo, conexiones_ocupadas, cola) para reconstruir luego la curva del
    cuello de botella. La capacidad del recurso es cfg.pool_capacity (60 por defecto),
    el limite fisico del plan gratuito de Supabase.
    """

    def __init__(self, env: simpy.Environment, cfg: ScenarioConfig,
                 resultado: ReplicaResult, guardar_series: bool):
        self.env = env
        self.recurso = simpy.Resource(env, capacity=cfg.pool_capacity)
        self.resultado = resultado
        self.guardar_series = guardar_series
        self._muestrear()  # Estado inicial en t=0.

    def _muestrear(self) -> None:
        ocupadas = self.recurso.count
        en_cola = len(self.recurso.queue)
        if ocupadas > self.resultado.pico_conexiones:
            self.resultado.pico_conexiones = ocupadas
        if en_cola > self.resultado.max_cola:
            self.resultado.max_cola = en_cola
        if self.guardar_series:
            self.resultado.serie_t.append(self.env.now)
            self.resultado.serie_conexiones.append(ocupadas)
            self.resultado.serie_cola.append(en_cola)

    def registrar(self) -> None:
        """Punto de muestreo publico para los procesos de comensal/zombie."""
        self._muestrear()


def _muestrear_retencion(cfg: ScenarioConfig, rng: np.random.Generator) -> float:
    """Tiempo (seg) que la conexion HTTP queda retenida (= tiempo de respuesta cloud).

    Es una NORMAL(media, desvio) y, bajo Wi-Fi degradada, se le suma una cola pesada
    EXPONENCIAL que modela las retransmisiones TCP (conexiones colgadas). Esa suma
    exponencial es la que, al superar GATEWAY_TIMEOUT, genera los 504 y mantiene el
    cupo ocupado mucho mas tiempo del normal.
    """
    retencion = rng.normal(cfg.latencia_media, cfg.latencia_desvio)
    retencion = max(0.01, retencion)
    if cfg.prob_cuelgue > 0.0 and rng.random() < cfg.prob_cuelgue:
        retencion += rng.exponential(cfg.cuelgue_media)
    return retencion


def _conexion_zombie(env: simpy.Environment, monitor: PoolerMonitor,
                     solicitud, restante: float):
    """Conexion HTTP 'colgada': el cliente ya recibio el 504 al cumplirse el
    GATEWAY_TIMEOUT, pero el socket sigue ocupando un cupo del pooler hasta que las
    retransmisiones TCP se agotan (`restante` segundos mas). ESTE es el fenomeno que
    hace que las conexiones se acumulen y el pool pueda llegar a saturarse."""
    try:
        yield env.timeout(restante)
    finally:
        monitor.recurso.release(solicitud)
        monitor.registrar()


def _intento_envio(env: simpy.Environment, monitor: PoolerMonitor,
                   cfg: ScenarioConfig, rng: np.random.Generator):
    """Un unico intento de POST a la API (toma un cupo del pooler).

    Devuelve (via SimPy) una etiqueta EXITO / ERR_504_* / ERR_RED. Implementa el
    patron de "reneging": si no consigue cupo antes de GATEWAY_TIMEOUT, abandona la
    cola con un 504 por saturacion. Si lo consigue pero la red cuelga la conexion,
    el socket se delega a un proceso zombie que lo mantiene ocupado.
    """
    resultado = monitor.resultado
    t_pedido = env.now
    solicitud = monitor.recurso.request()
    monitor.registrar()  # La cola pudo haber crecido.

    # Espera un cupo del pooler o vence el timeout del gateway (lo que ocurra antes).
    espera = env.timeout(GATEWAY_TIMEOUT)
    yield solicitud | espera

    if not solicitud.triggered:
        # No se obtuvo conexion a tiempo -> 504 por SATURACION del pooler (sin socket).
        solicitud.cancel()
        monitor.recurso.release(solicitud)
        monitor.registrar()
        return ERR_504_POOL

    # Cupo obtenido: registramos la espera en cola y la ocupacion.
    espera_en_cola = env.now - t_pedido
    resultado.espera_cola_total += espera_en_cola
    resultado.espera_cola_n += 1
    monitor.registrar()

    retencion = _muestrear_retencion(cfg, rng)

    if retencion <= GATEWAY_TIMEOUT:
        # Respuesta dentro del timeout: se retiene la conexion durante la escritura.
        yield env.timeout(retencion)
        monitor.recurso.release(solicitud)
        monitor.registrar()
        if rng.random() < cfg.prob_error_red:
            return ERR_RED
        return EXITO

    # Conexion COLGADA: el cliente percibe el 504 al cumplirse el timeout...
    yield env.timeout(GATEWAY_TIMEOUT)
    # ...pero el socket queda colgado (zombie) el tiempo restante de retransmisiones.
    env.process(_conexion_zombie(env, monitor, solicitud, retencion - GATEWAY_TIMEOUT))
    return ERR_504_LATENCIA


def proceso_comensal(env: simpy.Environment, idx: int, monitor: PoolerMonitor,
                     cfg: ScenarioConfig, rng: np.random.Generator):
    """Ciclo de vida de un comensal: llenar el formulario y enviar (con reintentos)."""
    resultado = monitor.resultado

    # Evento 2: llenado del formulario (12 preguntas) -> UNIFORME(45, 90) s.
    yield env.timeout(rng.uniform(FILL_TIME_MIN, FILL_TIME_MAX))

    # Eventos 3 y 4: click en enviar -> peticion -> persistencia, con reintentos.
    for intento in range(cfg.max_reintentos + 1):
        etiqueta = yield from _intento_envio(env, monitor, cfg, rng)

        if etiqueta == EXITO:
            resultado.exitos += 1
            return

        # Contabilizamos el tipo de fallo de este intento.
        if etiqueta == ERR_504_POOL:
            resultado.err_504_pool += 1
        elif etiqueta == ERR_504_LATENCIA:
            resultado.err_504_latencia += 1
        elif etiqueta == ERR_RED:
            resultado.err_red += 1

        if intento < cfg.max_reintentos:
            # El comensal reintenta tras un backoff (como permite el boton real).
            resultado.reintentos += 1
            yield env.timeout(rng.uniform(BACKOFF_MIN, BACKOFF_MAX))
        else:
            # Agoto los reintentos: la encuesta se pierde.
            resultado.encuestas_perdidas += 1
            return


def _generador_arribos(env: simpy.Environment, monitor: PoolerMonitor,
                       cfg: ScenarioConfig, rng: np.random.Generator):
    """Evento 1: arribos de comensales segun una EXPONENCIAL de tiempos entre llegadas."""
    for idx in range(cfg.n_comensales):
        env.process(proceso_comensal(env, idx, monitor, cfg, rng))
        dt = rng.exponential(cfg.tasa_arribo_media)
        monitor.resultado.interarribos.append(dt)  # Muestra para la validacion V&V.
        yield env.timeout(dt)


def correr_replica(cfg: ScenarioConfig, semilla: int,
                   guardar_series: bool = False) -> ReplicaResult:
    """Ejecuta UNA corrida completa del modelo y devuelve sus KPIs.

    Una "replica" es una repeticion independiente del experimento (otra semilla);
    NO tiene que ver con las conexiones del pool (ver nota al inicio del archivo).
    """
    rng = np.random.default_rng(semilla)
    env = simpy.Environment()
    resultado = ReplicaResult()
    monitor = PoolerMonitor(env, cfg, resultado, guardar_series)
    env.process(_generador_arribos(env, monitor, cfg, rng))
    env.run()  # Corre hasta agotar los eventos (comensales + conexiones zombie).
    resultado.tiempo_total = env.now
    if guardar_series:
        # Punto final para cerrar la curva escalonada.
        resultado.serie_t.append(env.now)
        resultado.serie_conexiones.append(monitor.recurso.count)
        resultado.serie_cola.append(len(monitor.recurso.queue))
    return resultado


def correr_experimento(cfg: ScenarioConfig, n_replicas: int = N_REPLICAS_DEFAULT,
                       semilla_base: int = SEED_BASE,
                       progreso: Callable[[int, int], None] | None = None
                       ) -> AggregatedResult:
    """Ejecuta N replicas del escenario, agrega KPIs (media, desvio e IC 95%) y conserva
    la serie temporal de la primera corrida como corrida representativa para graficar.

    `progreso(rep_actual, total)` es un callback opcional para refrescar una barra de
    progreso en la GUI web sin acoplar el motor a Streamlit.
    """
    replicas: List[ReplicaResult] = []
    for rep in range(n_replicas):
        guardar = (rep == 0)  # Solo la corrida 1 conserva la serie para graficar.
        replicas.append(correr_replica(cfg, semilla_base + rep, guardar_series=guardar))
        if progreso is not None:
            progreso(rep + 1, n_replicas)

    def _serie(extractor) -> List[float]:
        return [extractor(r) for r in replicas]

    metricas = {
        "exitos": _serie(lambda r: r.exitos),
        "total_504": _serie(lambda r: r.total_504),
        "err_504_pool": _serie(lambda r: r.err_504_pool),
        "err_504_latencia": _serie(lambda r: r.err_504_latencia),
        "err_red": _serie(lambda r: r.err_red),
        "encuestas_perdidas": _serie(lambda r: r.encuestas_perdidas),
        "reintentos": _serie(lambda r: r.reintentos),
        "espera_cola_promedio": _serie(lambda r: r.espera_cola_promedio),
        "max_cola": _serie(lambda r: r.max_cola),
        "pico_conexiones": _serie(lambda r: r.pico_conexiones),
        "tiempo_total": _serie(lambda r: r.tiempo_total),
    }

    agg = AggregatedResult(escenario=cfg.nombre, n_replicas=n_replicas,
                           pool_capacity=cfg.pool_capacity)
    for clave, valores in metricas.items():
        ic = intervalo_confianza_95(valores)   # t-Student o Normal segun n (req. 1).
        agg.medias[clave] = ic.media
        agg.desvios[clave] = statistics.pstdev(valores) if len(valores) > 1 else 0.0
        agg.ic_inf[clave] = ic.inf
        agg.ic_sup[clave] = ic.sup
        agg.muestras[clave] = valores

    # Trazabilidad del metodo de IC (mismo n para todos los KPIs de la corrida).
    agg.cuantil_ic, agg.metodo_ic, agg.gl_ic = cuantil_ic95(n_replicas)
    agg.n_muestral = n_replicas

    # Muestra de interarribos de TODAS las replicas para la validacion del generador.
    agg.interarribos = [dt for r in replicas for dt in r.interarribos]

    rep0 = replicas[0]
    agg.serie_t = rep0.serie_t
    agg.serie_conexiones = rep0.serie_conexiones
    agg.serie_cola = rep0.serie_cola
    return agg


# ---------------------------------------------------------------------------
# DIAGNOSTICO / RECOMENDACIONES (basado en evidencia simulada)
# ---------------------------------------------------------------------------
def generar_diagnostico(agg: AggregatedResult, cfg: ScenarioConfig) -> str:
    """Construye un texto interpretativo con recomendaciones para el equipo."""
    pool = cfg.pool_capacity
    exitos = agg.media("exitos")
    perdidas = agg.media("encuestas_perdidas")
    total_504 = agg.media("total_504")
    e504_pool = agg.media("err_504_pool")
    e504_lat = agg.media("err_504_latencia")
    pico = agg.media("pico_conexiones")
    max_cola = agg.media("max_cola")
    tasa_exito = 100.0 * exitos / cfg.n_comensales if cfg.n_comensales else 0.0

    lineas: List[str] = []
    lineas.append(f"DIAGNOSTICO DEL ESCENARIO '{agg.escenario.upper()}' "
                  f"(promedio de {agg.n_replicas} corrida/s)")
    lineas.append("-" * 64)
    lineas.append(
        f"Pico de conexiones concurrentes: {pico:.0f} de {pool} "
        f"({100.0 * pico / pool:.0f}% del pooler).")

    # Diagnostico de la saturacion del pooler.
    if max_cola < 1 and pico < pool:
        lineas.append(
            "El Connection Pooler NO se satura: queda cupo libre y la cola de la BD se "
            f"mantiene en 0. El limite de {pool} conexiones no es, por si solo, el cuello "
            "de botella dominante en este escenario.")
    else:
        lineas.append(
            f"El Connection Pooler SE SATURA: la cola llego a {max_cola:.0f} peticiones "
            f"en espera y hubo {e504_pool:.0f} caidas 504 por falta de cupos. El limite "
            f"de {pool} conexiones se vuelve el cuello de botella.")

    # Diagnostico de la red.
    if e504_lat >= 1:
        lineas.append(
            f"La Wi-Fi inestable es la causa principal de fallos: {e504_lat:.0f} "
            "timeouts 504 por conexiones colgadas (retransmisiones TCP que superan los "
            f"{GATEWAY_TIMEOUT:.0f} s del gateway) que ademas inflan la ocupacion del pool.")
    else:
        lineas.append("La red se comporto de forma estable: sin timeouts por cuelgue.")

    lineas.append("")
    lineas.append(f"RESULTADO: {exitos:.0f}/{cfg.n_comensales} encuestas guardadas "
                  f"({tasa_exito:.1f}% de exito). Encuestas perdidas tras reintentos: "
                  f"{perdidas:.1f}. Total de errores 504: {total_504:.1f}.")
    lineas.append("")
    lineas.append("RECOMENDACIONES:")
    if tasa_exito >= 99.5 and total_504 < 1:
        lineas.append("  - Escenario seguro: mantener la configuracion actual del evento.")
    if e504_lat >= 1 or agg.escenario == "Pesimista":
        lineas.append("  - Reforzar la conectividad: red cableada o un router/AP dedicado "
                      "en la Planta Piloto; no depender solo de la Wi-Fi general.")
        lineas.append("  - Implementar reintentos con backoff exponencial y guardado "
                      "local (offline-first) para no perder encuestas si cae la red.")
        lineas.append("  - Escalonar los envios en tandas/turnos para evitar la rafaga "
                      "concurrente de los comensales en pocos minutos.")
    if pico >= pool or max_cola >= 1:
        lineas.append("  - Evaluar un plan de Supabase con mayor limite de conexiones o "
                      "el pooler en modo 'transaction' para multiplexar cupos.")
    if perdidas >= 1:
        lineas.append("  - Disponer una planilla de carga manual de respaldo para las "
                      "encuestas que el sistema no logre persistir.")
    return "\n".join(lineas)
