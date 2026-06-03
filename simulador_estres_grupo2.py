# -*- coding: utf-8 -*-
"""
================================================================================
 SIMULADOR 1 - ESTRES DE SERVIDOR (Connection Pooler de Supabase)  ::  v2.0 FINAL
 Trabajo Practico Integrador Intercatedra - Grupo 2
 Asignatura: Modelos y Simulacion - 4to Anio - Ingenieria en Sistemas de Informacion
 Articulacion: Modelos y Simulacion / Ingenieria de Software III / TCyRS  -  Inter
               carrera con Licenciatura en Nutricion.
 Evento real modelado: Analisis sensorial de una tartaleta vegetal sustentable en
                       la Planta Piloto, jueves 11 de junio de 2026, >= 50 jueces
                       no entrenados.
================================================================================

OBJETIVO DEL MODELO
-------------------
Modelar mediante SIMULACION DE EVENTOS DISCRETOS (libreria SimPy) el comportamiento
del sistema web estatico (deployado en Vercel) que se conecta de forma DIRECTA
(Client-to-Cloud) a una base de datos PostgreSQL alojada en Supabase, atravesando su
"Connection Pooler". El fin es PREDECIR el comportamiento del pooler frente a rafagas
de comensales concurrentes y estimar la PROBABILIDAD de errores de timeout (HTTP 504)
provocados por la red Wi-Fi inestable de la Planta Piloto.

AUDITORIA DEL SISTEMA REAL (codigo de 3er anio - carpeta Trabajo-Nutric-main)
----------------------------------------------------------------------------
* js/supabase.js : un unico cliente global `createClient(URL, ANON_KEY)`. La pagina
  estatica abre la conexion DIRECTAMENTE contra la API REST de Supabase (PostgREST),
  que internamente consume cupos del Connection Pooler. No hay backend intermedio.
* js/encuesta.js : la encuesta posee EXACTAMENTE 24 preguntas de analisis sensorial
  sobre escala hedonica afectiva de 1 a 10, agrupadas en descriptores de COLOR/
  APARIENCIA, OLOR, TEMPERATURA/TEXTURA y SABOR, mas 1 comentario libre. El envio se
  materializa en UNA sola peticion `db.from('encuestas').insert([datos])` por comensal.
  Mover 24 sliders + escribir el comentario JUSTIFICA el tiempo de llenado de 45-90 s.

DEFINICION FORMAL DEL SISTEMA
-----------------------------
* ENTIDADES ........ Comensales virtuales (jueces no entrenados) que usan la web.
* RECURSOS ......... Canales del Connection Pooler de Supabase. Limite ESTRICTO del
                     plan gratuito = 60 conexiones concurrentes -> simpy.Resource(60).
* VARIABLES DE ESTADO  Conexiones HTTP activas, tamanio de la cola hacia la BD,
                       cantidad de peticiones rechazadas/caidas (504 y de red).
* EVENTOS .......... (1) Arribo del comensal, (2) inicio del llenado del formulario,
                     (3) click en enviar -> peticion HTTP (toma cupo del pooler),
                     (4) persistencia/confirmacion de escritura en PostgreSQL.

DISTRIBUCIONES ESTADISTICAS (segun consigna de catedra)
-------------------------------------------------------
* Tasa de Arribos ......... EXPONENCIAL (llegada de los comensales en la jornada).
* Tiempo de Llenado ....... UNIFORME(45, 90) s (justificado por los 24 inputs).
* Tiempo de Respuesta /
  retencion de conexion .... NORMAL(media, desvio) por escenario (latencia hacia
                             Supabase). El "Esperado" usa NORMAL(0,25 s; 0,05 s) tal
                             como pide la consigna.

MODELO DEL CUELLO DE BOTELLA (corregido en la v2.0)
---------------------------------------------------
En las corridas previas el pico de conexiones daba muy bajo (5/60) porque la latencia
de Supabase es minima frente a lo que tarda el usuario en llenar la encuesta: las
conexiones se liberaban casi al instante y nunca se acumulaban. Para representar el
RIESGO REAL de la Planta Piloto (Wi-Fi inestable/saturada) se incorpora el fenomeno de
las CONEXIONES COLGADAS:
  - Bajo Wi-Fi degradada, una fraccion de las peticiones sufre retransmisiones TCP que
    EXTIENDEN EXPONENCIALMENTE el tiempo de retencion del socket HTTP.
  - El cliente percibe el HTTP 504 al cumplirse GATEWAY_TIMEOUT segundos y REINTENTA
    (abriendo OTRA conexion), pero el socket original NO se libera: sigue ocupando un
    cupo del pooler hasta que las retransmisiones se agotan (tiempo "restante").
  - Asi, conexiones colgadas + reintentos se SUPERPONEN y la curva de conexiones
    ocupadas crece de forma dinamica y realista, justificando matematicamente los
    timeouts y la eventual saturacion del pool.

USO
---
    python simulador_estres_grupo2.py            # Interfaz grafica premium (GUI).
    python simulador_estres_grupo2.py --cli       # Corre los 3 escenarios por consola.

Autores: Grupo 2 - ISI 4to.  QA / Simulacion: Juan Ignacio Gualtieri.
================================================================================
"""

from __future__ import annotations

import argparse
import os
import statistics
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import simpy

# =============================================================================
# DOS NUMEROS QUE NO HAY QUE CONFUNDIR (aclaracion para la catedra)
# -----------------------------------------------------------------------------
# * POOLER_CAPACITY = 60  -> LIMITE FISICO / DE HARDWARE. Es la cantidad MAXIMA de
#   conexiones SIMULTANEAS que el Connection Pooler de Supabase (plan gratuito)
#   acepta EN UN MISMO INSTANTE del tiempo simulado. Se modela como el recurso
#   simpy.Resource(capacity=60); cuando se agota, las nuevas peticiones hacen COLA.
#   Es una restriccion del sistema real.
#
# * N_REPLICAS (p. ej. 30) -> CANTIDAD DE EXPERIMENTOS. Es cuantas veces se REPITE
#   COMPLETA la simulacion del dia del evento, cada vez con otra semilla aleatoria,
#   para PROMEDIAR los KPIs y reducir la varianza estadistica (Ley de los Grandes
#   Numeros). NO son usuarios ni conexiones: son corridas independientes del modelo.
#   Mas replicas => promedios mas estables, NO un sistema mas/menos cargado.
# =============================================================================
POOLER_CAPACITY = 60          # LIMITE de conexiones simultaneas (hardware del pool).
GATEWAY_TIMEOUT = 8.0         # seg. Umbral de timeout del gateway/HTTP -> dispara 504.
N_PREGUNTAS_ENCUESTA = 24     # Auditado en js/encuesta.js (24 sliders hedonicos).
FILL_TIME_MIN = 45.0          # seg. Tiempo minimo de llenado (Uniforme).
FILL_TIME_MAX = 90.0          # seg. Tiempo maximo de llenado (Uniforme).
BACKOFF_MIN = 0.8             # seg. Espera minima del comensal antes de reintentar.
BACKOFF_MAX = 3.0             # seg. Espera maxima del comensal antes de reintentar.
SEED_BASE = 2026              # Semilla base (anio del evento) para reproducibilidad.
N_REPLICAS_DEFAULT = 30       # Replicas por defecto para estabilizar promedios.

# Etiquetas de resultado de un intento de envio.
EXITO = "EXITO"
ERR_504_POOL = "ERR_504_POOL"      # 504 por SATURACION del pooler (no hubo cupo a tiempo).
ERR_504_LATENCIA = "ERR_504_LAT"   # 504 por conexion COLGADA (Wi-Fi inestable).
ERR_RED = "ERR_RED"                # Error de red puntual (probabilidad base).

# Datos institucionales del Grupo 2 (para el reporte PDF).
GRUPO_INFO = {
    "institucion": "Universidad - Facultad de Ingenieria, Tecnologia y Agrimensura (Sede Corrientes)",
    "carrera": "Ingenieria en Sistemas de Informacion",
    "tpi": "Trabajo Practico Integrador Intercatedra e Intercarrera",
    "catedras": "Modelos y Simulacion - Ingenieria de Software III - Tecnologia, Ciencia y Responsabilidad Social",
    "docentes": "Jaquelina E. Escalante - Gilda Romero - Silvina Podesta",
    "grupo": "Grupo 2",
    "equipo_isi4": "ISI 4to: Ignacio Rosales (PM/Scrum Master) - Juan Ignacio Gualtieri (QA Manager/Simulacion)",
    "equipo_isi3": "ISI 3ro: Desarrollo del sistema web (HTML/JS + Supabase, deploy en Vercel)",
    "equipo_nutri": "Licenciatura en Nutricion: Diseno del producto y de las pruebas de analisis sensorial",
    "evento": "Analisis sensorial - tartaleta vegetal sustentable - Planta Piloto - jueves 11/06/2026",
}


# ---------------------------------------------------------------------------
# CONFIGURACION DE ESCENARIOS
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScenarioConfig:
    """Parametros que definen un escenario de simulacion."""
    nombre: str
    descripcion: str
    n_comensales: int           # Cantidad de jueces que envian encuesta.
    ventana_arribos_seg: float  # Ventana temporal en la que llegan los arribos (seg).
    latencia_media: float       # Media de la NORMAL de respuesta cloud (seg).
    latencia_desvio: float      # Desvio de la NORMAL de respuesta cloud (seg).
    prob_cuelgue: float         # Prob. de que la conexion se "cuelgue" (cola pesada).
    cuelgue_media: float        # Media de la EXPONENCIAL del cuelgue extra (seg).
    prob_error_red: float       # Prob. base de error de red por intento.
    max_reintentos: int         # Reintentos del comensal ante un fallo.

    @property
    def tasa_arribo_media(self) -> float:
        """Media de la EXPONENCIAL de tiempos entre arribos (seg)."""
        return self.ventana_arribos_seg / self.n_comensales


# Los tres escenarios obligatorios de la consigna.
SCENARIOS: Dict[str, ScenarioConfig] = {
    "Optimista": ScenarioConfig(
        nombre="Optimista",
        descripcion=(
            "Arribos espaciados a lo largo de una jornada de ~5 h. Wi-Fi de alta "
            "velocidad (latencia ~100 ms) y 0% de errores. El pooler trabaja holgado."
        ),
        n_comensales=50,
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
            "Transito fluido en lotes normales durante ~2,5 h. Internet promedio: "
            "NORMAL(0,25 s; 0,05 s) como pide la catedra. Pooler estable con fallos "
            "esporadicos que los reintentos recuperan."
        ),
        n_comensales=50,
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
            "Concurrencia masiva destructiva: los 50 comensales envian dentro de una "
            "ventana critica de 2 minutos por aglomeracion. Wi-Fi degradada: las "
            "conexiones se CUELGAN (retransmisiones TCP) y se acumulan en el pooler -> "
            "rafaga dinamica de timeouts 504."
        ),
        n_comensales=50,
        ventana_arribos_seg=120,          # 2 minutos.
        latencia_media=0.90,              # Wi-Fi degradada.
        latencia_desvio=0.30,
        prob_cuelgue=0.80,                # 80% de las conexiones se cuelgan.
        cuelgue_media=18.0,               # retencion extra EXPONENCIAL de media 18 s.
        prob_error_red=0.05,
        max_reintentos=3,
    ),
}


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
    """KPIs agregados (media y desvio) sobre N replicas + serie representativa."""
    escenario: str
    n_replicas: int
    medias: Dict[str, float] = field(default_factory=dict)
    desvios: Dict[str, float] = field(default_factory=dict)
    serie_t: List[float] = field(default_factory=list)
    serie_conexiones: List[int] = field(default_factory=list)
    serie_cola: List[int] = field(default_factory=list)

    def media(self, clave: str) -> float:
        return self.medias.get(clave, 0.0)

    def desvio(self, clave: str) -> float:
        return self.desvios.get(clave, 0.0)


# ---------------------------------------------------------------------------
# MOTOR DE SIMULACION (EVENTOS DISCRETOS - SimPy)
# ---------------------------------------------------------------------------
class PoolerMonitor:
    """Envuelve el simpy.Resource del pooler y registra las variables de estado.

    Cada vez que cambia la ocupacion del pooler o el tamanio de la cola se toma una
    muestra (tiempo, conexiones_ocupadas, cola) para reconstruir luego la curva del
    cuello de botella. La capacidad del recurso es POOLER_CAPACITY (60), el limite
    fisico del plan gratuito de Supabase.
    """

    def __init__(self, env: simpy.Environment, resultado: ReplicaResult,
                 guardar_series: bool):
        self.env = env
        self.recurso = simpy.Resource(env, capacity=POOLER_CAPACITY)
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

    # Evento 2: llenado del formulario (24 sliders) -> UNIFORME(45, 90) s.
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
        yield env.timeout(rng.exponential(cfg.tasa_arribo_media))


def correr_replica(cfg: ScenarioConfig, semilla: int,
                   guardar_series: bool = False) -> ReplicaResult:
    """Ejecuta UNA corrida completa del modelo y devuelve sus KPIs.

    Una "replica" es una repeticion independiente del experimento (otra semilla);
    NO tiene que ver con las 60 conexiones del pool (ver nota al inicio del archivo).
    """
    rng = np.random.default_rng(semilla)
    env = simpy.Environment()
    resultado = ReplicaResult()
    monitor = PoolerMonitor(env, resultado, guardar_series)
    env.process(_generador_arribos(env, monitor, cfg, rng))
    env.run()  # Corre hasta agotar los eventos (comensales + conexiones zombie).
    resultado.tiempo_total = env.now
    if guardar_series:
        # Punto final para cerrar la curva escalonada.
        resultado.serie_t.append(env.now)
        resultado.serie_conexiones.append(monitor.recurso.count)
        resultado.serie_cola.append(len(monitor.recurso.queue))
    return resultado


def correr_experimento(nombre_escenario: str, n_replicas: int = N_REPLICAS_DEFAULT,
                       semilla_base: int = SEED_BASE) -> AggregatedResult:
    """Ejecuta N replicas del escenario, agrega KPIs (media y desvio) y conserva la
    serie temporal de la primera corrida como corrida representativa para graficar."""
    cfg = SCENARIOS[nombre_escenario]
    replicas: List[ReplicaResult] = []
    for rep in range(n_replicas):
        guardar = (rep == 0)  # Solo la corrida 1 conserva la serie para graficar.
        replicas.append(correr_replica(cfg, semilla_base + rep, guardar_series=guardar))

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

    agg = AggregatedResult(escenario=nombre_escenario, n_replicas=n_replicas)
    for clave, valores in metricas.items():
        agg.medias[clave] = statistics.fmean(valores)
        agg.desvios[clave] = statistics.pstdev(valores) if len(valores) > 1 else 0.0

    rep0 = replicas[0]
    agg.serie_t = rep0.serie_t
    agg.serie_conexiones = rep0.serie_conexiones
    agg.serie_cola = rep0.serie_cola
    return agg


# ---------------------------------------------------------------------------
# DIAGNOSTICO / RECOMENDACIONES (basado en evidencia simulada)
# ---------------------------------------------------------------------------
def generar_diagnostico(agg: AggregatedResult) -> str:
    """Construye un texto interpretativo con recomendaciones para el equipo."""
    cfg = SCENARIOS[agg.escenario]
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
        f"Pico de conexiones concurrentes: {pico:.0f} de {POOLER_CAPACITY} "
        f"({100.0 * pico / POOLER_CAPACITY:.0f}% del pooler).")

    # Diagnostico de la saturacion del pooler.
    if max_cola < 1 and pico < POOLER_CAPACITY:
        lineas.append(
            "El Connection Pooler NO se satura: queda cupo libre y la cola de la BD se "
            "mantiene en 0. El limite de 60 conexiones no es, por si solo, el cuello "
            "de botella dominante en este escenario.")
    else:
        lineas.append(
            f"El Connection Pooler SE SATURA: la cola llego a {max_cola:.0f} peticiones "
            f"en espera y hubo {e504_pool:.0f} caidas 504 por falta de cupos. El limite "
            "de 60 conexiones se vuelve el cuello de botella.")

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
                      "concurrente de los 50 comensales en pocos minutos.")
    if pico >= POOLER_CAPACITY or max_cola >= 1:
        lineas.append("  - Evaluar un plan de Supabase con mayor limite de conexiones o "
                      "el pooler en modo 'transaction' para multiplexar cupos.")
    if perdidas >= 1:
        lineas.append("  - Disponer una planilla de carga manual de respaldo para las "
                      "encuestas que el sistema no logre persistir.")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# GRAFICO COMPARTIDO (lo usan la GUI y el reporte PDF -> evita duplicar codigo)
# ---------------------------------------------------------------------------
def dibujar_curva_conexiones(ax, agg: AggregatedResult, *, premium: bool = True) -> None:
    """Dibuja sobre `ax` la curva de conexiones ocupadas en el tiempo.

    Estilo premium: linea verde suavizada con area sombreada, limite del pool en rojo
    y pico en ambar, grilla tenue y sin marcos superior/derecho.
    """
    verde = "#2E7D32"
    rojo = "#C0392B"
    ambar = "#B9770E"

    ax.clear()
    if agg.serie_t:
        t_min = [t / 60.0 for t in agg.serie_t]  # segundos -> minutos.
        ax.fill_between(t_min, agg.serie_conexiones, step="post",
                        color=verde, alpha=0.16, zorder=1)
        ax.step(t_min, agg.serie_conexiones, where="post", color=verde,
                linewidth=2.0, solid_capstyle="round", solid_joinstyle="round",
                label="Conexiones ocupadas", zorder=3)
        pico = agg.media("pico_conexiones")
        ax.axhline(pico, color=ambar, linestyle=":", linewidth=1.4,
                   label=f"Pico ~{pico:.0f}", zorder=2)

    ax.axhline(POOLER_CAPACITY, color=rojo, linestyle="--", linewidth=1.4,
               label=f"Limite del pooler ({POOLER_CAPACITY})", zorder=2)

    tope = max(POOLER_CAPACITY + 6, agg.media("pico_conexiones") + 6)
    ax.set_ylim(0, tope)
    ax.set_xlim(left=0)
    ax.set_title(f"Conexiones ocupadas  ·  Escenario {agg.escenario}",
                 fontsize=11, fontweight="bold", color="#23311C", pad=10)
    ax.set_xlabel("Tiempo de la jornada (min)", fontsize=10, color="#3A4A30")
    ax.set_ylabel("Conexiones concurrentes", fontsize=10, color="#3A4A30")
    ax.legend(loc="upper right", fontsize=8, frameon=True, fancybox=True,
              framealpha=0.9)
    ax.grid(True, alpha=0.25, linewidth=0.8, color="#9DB089")
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color("#C4CFB6")
    ax.tick_params(colors="#5B6A4C", labelsize=8)


# ---------------------------------------------------------------------------
# EXPORTACION A PDF (Reporte de Ingenieria, estilo Normas APA 7° ed.)
# ---------------------------------------------------------------------------
def exportar_reporte_pdf(agg: AggregatedResult,
                         ruta_pdf: str = "Reporte_Simulacion_Estres_Grupo2.pdf") -> str:
    """Compila un PDF formal con portada, parametros, KPIs, diagnostico y el grafico.

    Devuelve la ruta absoluta del PDF generado.
    """
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    cfg = SCENARIOS[agg.escenario]
    ruta_pdf = os.path.abspath(ruta_pdf)

    # --- 1) Generar el grafico de la curva como PNG estatico (anexo visual) ---
    fig = Figure(figsize=(7.2, 4.0), dpi=150, facecolor="white")
    ax = fig.add_subplot(111)
    dibujar_curva_conexiones(ax, agg)
    fig.tight_layout()
    tmp_png = os.path.join(tempfile.gettempdir(),
                           f"_curva_{agg.escenario}_{os.getpid()}.png")
    fig.savefig(tmp_png, dpi=150, facecolor="white")

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

    # --- 3) PORTADA FORMAL (estilo APA) ---
    story.append(Spacer(1, 2.2 * cm))
    story.append(Paragraph("Reporte de Simulacion de Eventos Discretos", st_titulo))
    story.append(Paragraph("Estres de Servidor - Connection Pooler de Supabase", st_sub))
    story.append(Spacer(1, 1.0 * cm))
    story.append(Paragraph(GRUPO_INFO["tpi"], st_portada))
    story.append(Paragraph(GRUPO_INFO["catedras"], st_portada))
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(f"<b>{GRUPO_INFO['grupo']}</b>", st_portada))
    story.append(Paragraph(GRUPO_INFO["carrera"], st_portada))
    story.append(Paragraph(GRUPO_INFO["institucion"], st_portada))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(GRUPO_INFO["equipo_isi4"], st_portada))
    story.append(Paragraph(GRUPO_INFO["equipo_isi3"], st_portada))
    story.append(Paragraph(GRUPO_INFO["equipo_nutri"], st_portada))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(f"Docentes: {GRUPO_INFO['docentes']}", st_portada))
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(GRUPO_INFO["evento"], st_portada))
    story.append(Paragraph(
        f"Escenario analizado: <b>{agg.escenario}</b>  |  "
        f"Replicas: {agg.n_replicas}", st_portada))
    story.append(Paragraph(
        "Fecha de emision del reporte: " + datetime.now().strftime("%d/%m/%Y %H:%M"),
        st_portada))
    story.append(PageBreak())

    # --- 4) CONFIGURACION DE PARAMETROS DEL ESCENARIO ACTUAL ---
    story.append(Paragraph("1. Configuracion del escenario simulado", st_h2))
    story.append(Paragraph(cfg.descripcion, st_body))
    story.append(Spacer(1, 0.3 * cm))
    datos_param = [
        ["Parametro", "Valor"],
        ["Escenario", cfg.nombre],
        ["Comensales (entidades)", f"{cfg.n_comensales}"],
        ["Ventana de arribos", f"{cfg.ventana_arribos_seg/60:.1f} min"],
        ["Distribucion de arribos", f"Exponencial (media {cfg.tasa_arribo_media:.1f} s)"],
        ["Tiempo de llenado", f"Uniforme({FILL_TIME_MIN:.0f}, {FILL_TIME_MAX:.0f}) s"],
        ["Latencia / respuesta cloud",
         f"Normal({cfg.latencia_media:.2f} s; {cfg.latencia_desvio:.2f} s)"],
        ["Modelo Wi-Fi (cuelgue)",
         f"P={cfg.prob_cuelgue:.0%} ; retencion extra Exponencial(media {cfg.cuelgue_media:.0f} s)"],
        ["Reintentos maximos", f"{cfg.max_reintentos}"],
        ["Limite del Connection Pooler", f"{POOLER_CAPACITY} conexiones simultaneas (hardware)"],
        ["Timeout de gateway (504)", f"{GATEWAY_TIMEOUT:.0f} s"],
        ["Replicas del experimento", f"{agg.n_replicas} (promedios estadisticos)"],
    ]
    tabla_param = Table(datos_param, colWidths=[7.0 * cm, 9.0 * cm])
    tabla_param.setStyle(_estilo_tabla(colors))
    story.append(tabla_param)

    # --- 5) KPIs CONSOLIDADOS ---
    story.append(Paragraph("2. Indicadores clave de desempenio (KPIs consolidados)", st_h2))
    tasa = 100.0 * agg.media("exitos") / cfg.n_comensales if cfg.n_comensales else 0.0
    datos_kpi = [
        ["KPI", "Valor (promedio de replicas)"],
        ["Encuestas guardadas con exito", f"{agg.media('exitos'):.1f} / {cfg.n_comensales}"],
        ["Tasa de exito", f"{tasa:.1f} %"],
        ["Errores 504 / caidas (total)", f"{agg.media('total_504'):.1f}"],
        ["   - 504 por saturacion del pool", f"{agg.media('err_504_pool'):.1f}"],
        ["   - 504 por Wi-Fi colgada", f"{agg.media('err_504_latencia'):.1f}"],
        ["Errores de red", f"{agg.media('err_red'):.1f}"],
        ["Encuestas perdidas (tras reintentos)", f"{agg.media('encuestas_perdidas'):.1f}"],
        ["Espera promedio en cola", f"{agg.media('espera_cola_promedio'):.3f} s"],
        ["Tamanio maximo de cola de BD", f"{agg.media('max_cola'):.1f}"],
        ["Pico de conexiones concurrentes", f"{agg.media('pico_conexiones'):.1f} / {POOLER_CAPACITY}"],
    ]
    tabla_kpi = Table(datos_kpi, colWidths=[9.0 * cm, 7.0 * cm])
    tabla_kpi.setStyle(_estilo_tabla(colors))
    story.append(tabla_kpi)

    # --- 6) DIAGNOSTICO Y RECOMENDACIONES ---
    story.append(Paragraph("3. Diagnostico y recomendaciones", st_h2))
    for parrafo in generar_diagnostico(agg).split("\n"):
        texto = parrafo if parrafo.strip() else "&nbsp;"
        texto = texto.replace("  - ", "&bull;&nbsp;").replace(" ", "&nbsp;", 0)
        story.append(Paragraph(texto, st_diag))

    # --- 7) ANEXO: GRAFICO DE LA CURVA DE CONEXIONES ---
    story.append(PageBreak())
    story.append(Paragraph("Anexo A. Curva de conexiones ocupadas en el tiempo", st_h2))
    story.append(Paragraph(
        "Corrida representativa del escenario. La curva muestra la evolucion de las "
        "conexiones HTTP activas en el Connection Pooler frente al limite fisico de "
        f"{POOLER_CAPACITY} conexiones del plan gratuito de Supabase.", st_body))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Image(tmp_png, width=16.0 * cm, height=16.0 * cm * 4.0 / 7.2))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "Reporte generado automaticamente por el Simulador de Estres v2.0 - Grupo 2.",
        st_pie))

    # --- 8) Construir el documento ---
    doc = SimpleDocTemplate(
        ruta_pdf, pagesize=A4,
        topMargin=2.2 * cm, bottomMargin=2.0 * cm,
        leftMargin=2.3 * cm, rightMargin=2.3 * cm,
        title="Reporte Simulacion de Estres - Grupo 2",
        author=GRUPO_INFO["grupo"])
    doc.build(story)

    # Limpieza del PNG temporal.
    try:
        os.remove(tmp_png)
    except OSError:
        pass
    return ruta_pdf


def _estilo_tabla(colors):
    """Estilo visual reutilizable para las tablas del PDF."""
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


# ---------------------------------------------------------------------------
# MODO CONSOLA (validacion / verificacion del modelo)
# ---------------------------------------------------------------------------
def correr_cli(n_replicas: int = N_REPLICAS_DEFAULT) -> None:
    """Corre los tres escenarios por consola e imprime los KPIs agregados."""
    print("=" * 72)
    print(" SIMULADOR DE ESTRES - CONNECTION POOLER SUPABASE - GRUPO 2 (v2.0)")
    print(f" Recurso (hardware): {POOLER_CAPACITY} conexiones | Timeout 504: "
          f"{GATEWAY_TIMEOUT}s | Encuesta: {N_PREGUNTAS_ENCUESTA} preguntas")
    print(f" Replicas por escenario (experimentos estadisticos): {n_replicas}")
    print("=" * 72)
    for nombre in SCENARIOS:
        agg = correr_experimento(nombre, n_replicas=n_replicas)
        cfg = SCENARIOS[nombre]
        print(f"\n>> ESCENARIO {nombre.upper()}  "
              f"({cfg.n_comensales} comensales en {cfg.ventana_arribos_seg/60:.1f} min)")
        print(f"   Encuestas guardadas ....... {agg.media('exitos'):6.1f} / {cfg.n_comensales}")
        print(f"   Errores 504 (total) ....... {agg.media('total_504'):6.1f}  "
              f"(pool {agg.media('err_504_pool'):.1f} | wifi {agg.media('err_504_latencia'):.1f})")
        print(f"   Errores de red ............ {agg.media('err_red'):6.1f}")
        print(f"   Encuestas perdidas ........ {agg.media('encuestas_perdidas'):6.1f}")
        print(f"   Espera prom. en cola ...... {agg.media('espera_cola_promedio'):6.3f} s")
        print(f"   Tamanio maximo de cola .... {agg.media('max_cola'):6.1f}")
        print(f"   Pico de conexiones ........ {agg.media('pico_conexiones'):6.1f} / {POOLER_CAPACITY}")
    print("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# INTERFAZ GRAFICA PREMIUM (customtkinter + matplotlib embebido)
# ---------------------------------------------------------------------------
def lanzar_gui(auto_close_ms: Optional[int] = None) -> None:
    """Construye y ejecuta la interfaz grafica premium para el equipo de Nutricion.

    Si se indica `auto_close_ms`, dispara una corrida de prueba y cierra sola la
    ventana (usado por el smoke-test automatico; no por el usuario final).
    """
    import customtkinter as ctk
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    # ---- Paleta premium interdisciplinaria (verde agroecologico) ----
    BG_APP = "#EDF1E9"        # Fondo gris-verde claro premium.
    BG_SIDE = "#F7FAF4"       # Panel lateral apenas mas claro.
    CARD = "#FFFFFF"          # Tarjetas blancas.
    BORDE = "#E0E6D7"         # Bordes sutiles definidos.
    VERDE = "#2E7D32"         # Verde hoja (acento principal).
    VERDE_HOVER = "#256628"   # Hover boton principal.
    VERDE_PDF = "#1B5E20"     # Boton de exportacion (verde profundo).
    VERDE_PDF_HOVER = "#143F16"
    TXT = "#23311C"           # Texto principal.
    TXT_SUAVE = "#5B6A4C"     # Texto secundario / captions.
    ROJO = "#C0392B"
    AMBAR = "#B9770E"
    FUENTE = "Segoe UI"       # Tipografia estilizada (Windows).

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("green")

    class SimuladorApp(ctk.CTk):
        def __init__(self):
            super().__init__()
            self.title("Simulador de Estres - Connection Pooler Supabase  |  TPI Grupo 2")
            self.geometry("1320x880")
            self.minsize(1180, 800)
            self.configure(fg_color=BG_APP)
            self.grid_columnconfigure(1, weight=1)
            self.grid_rowconfigure(0, weight=1)

            self._escenario = ctk.StringVar(value="Esperado")
            self._replicas = ctk.StringVar(value="30")
            self._ejecutando = False
            self._ultimo_agg: Optional[AggregatedResult] = None
            self._tarjetas: Dict[str, ctk.CTkLabel] = {}

            self._fuente = lambda s, w="normal": ctk.CTkFont(family=FUENTE, size=s, weight=w)

            self._construir_sidebar(ctk)
            self._construir_contenido(ctk, Figure, FigureCanvasTkAgg)
            self._actualizar_descripcion()

            if auto_close_ms is not None:
                # Smoke-test: ejecuta una corrida y cierra la ventana automaticamente.
                self.after(300, self._on_ejecutar)
                self.after(auto_close_ms, self.destroy)

        # ---------- PANEL LATERAL ----------
        def _construir_sidebar(self, ctk):
            side = ctk.CTkFrame(self, width=370, corner_radius=0, fg_color=BG_SIDE)
            side.grid(row=0, column=0, sticky="nsew")
            side.grid_propagate(False)

            # Marca / cabecera.
            cab = ctk.CTkFrame(side, fg_color="transparent")
            cab.pack(fill="x", padx=28, pady=(28, 10))
            ctk.CTkLabel(cab, text="Simulador de Estres",
                         font=self._fuente(24, "bold"), text_color=VERDE).pack(anchor="w")
            ctk.CTkLabel(cab, text="Connection Pooler  ·  Supabase Cloud",
                         font=self._fuente(13), text_color=TXT_SUAVE).pack(anchor="w")
            ctk.CTkLabel(cab, text="TPI Modelos y Simulacion  ·  Grupo 2",
                         font=self._fuente(12), text_color=TXT_SUAVE).pack(anchor="w", pady=(2, 0))

            # Tarjeta de configuracion.
            conf = ctk.CTkFrame(side, corner_radius=16, fg_color=CARD,
                                border_width=1, border_color=BORDE)
            conf.pack(fill="x", padx=24, pady=12)

            ctk.CTkLabel(conf, text="1 ·  Escenario a simular",
                         font=self._fuente(15, "bold"), text_color=TXT).pack(
                anchor="w", padx=18, pady=(18, 8))
            seg = ctk.CTkSegmentedButton(
                conf, values=["Optimista", "Esperado", "Pesimista"],
                variable=self._escenario, command=lambda _=None: self._actualizar_descripcion(),
                font=self._fuente(13, "bold"), height=38,
                selected_color=VERDE, selected_hover_color=VERDE_HOVER,
                unselected_color="#E9EFE2", unselected_hover_color="#DCE6D0",
                text_color=TXT, corner_radius=10)
            seg.pack(fill="x", padx=18, pady=(0, 10))

            self._lbl_desc = ctk.CTkLabel(
                conf, text="", font=self._fuente(12), justify="left",
                wraplength=290, text_color=TXT_SUAVE, anchor="w")
            self._lbl_desc.pack(fill="x", padx=18, pady=(0, 12))

            ctk.CTkLabel(conf, text="2 ·  Replicas (corridas del experimento)",
                         font=self._fuente(15, "bold"), text_color=TXT).pack(
                anchor="w", padx=18, pady=(4, 6))
            ctk.CTkOptionMenu(
                conf, values=["1", "10", "30", "50"], variable=self._replicas,
                font=self._fuente(13), width=130, height=34,
                fg_color=VERDE, button_color=VERDE_HOVER, button_hover_color=VERDE_PDF,
                dropdown_font=self._fuente(12)).pack(anchor="w", padx=18, pady=(0, 6))
            ctk.CTkLabel(
                conf, text="Repeticiones independientes para promediar KPIs (no son\n"
                           "conexiones: el pool admite 60 simultaneas como maximo).",
                font=self._fuente(11), text_color=TXT_SUAVE, justify="left").pack(
                anchor="w", padx=18, pady=(0, 16))

            # Boton principal.
            self._btn = ctk.CTkButton(
                side, text="►  Ejecutar simulacion", height=50, corner_radius=14,
                font=self._fuente(16, "bold"), fg_color=VERDE, hover_color=VERDE_HOVER,
                command=self._on_ejecutar)
            self._btn.pack(fill="x", padx=24, pady=(8, 6))

            self._lbl_estado = ctk.CTkLabel(
                side, text="Listo para simular.", font=self._fuente(12),
                text_color=TXT_SUAVE)
            self._lbl_estado.pack(anchor="w", padx=28, pady=(2, 8))

            # Ficha del sistema real (al pie).
            ficha = ctk.CTkFrame(side, corner_radius=16, fg_color="#EEF4E7",
                                 border_width=1, border_color=BORDE)
            ficha.pack(fill="x", padx=24, pady=(10, 22), side="bottom")
            ctk.CTkLabel(ficha, text="Sistema real modelado",
                         font=self._fuente(12, "bold"), text_color=VERDE).pack(
                anchor="w", padx=16, pady=(12, 2))
            ctk.CTkLabel(
                ficha,
                text=(f"·  {POOLER_CAPACITY} conexiones (plan gratuito Supabase)\n"
                      f"·  {N_PREGUNTAS_ENCUESTA} preguntas sensoriales (escala hedonica)\n"
                      f"·  50 comensales  ·  11/06/2026  ·  Planta Piloto\n"
                      f"·  Conexion directa Client-to-Cloud (sin backend)"),
                font=self._fuente(11), justify="left", text_color=TXT_SUAVE).pack(
                anchor="w", padx=16, pady=(0, 14))

        # ---------- PANEL DE RESULTADOS ----------
        def _construir_contenido(self, ctk, Figure, FigureCanvasTkAgg):
            cont = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
            cont.grid(row=0, column=1, sticky="nsew", padx=24, pady=22)
            cont.grid_columnconfigure(0, weight=1)
            cont.grid_rowconfigure(2, weight=1)

            # Encabezado.
            enc = ctk.CTkFrame(cont, fg_color="transparent")
            enc.grid(row=0, column=0, sticky="ew")
            self._lbl_titulo = ctk.CTkLabel(
                enc, text="Resultados  ·  Escenario Esperado",
                font=self._fuente(22, "bold"), text_color=TXT)
            self._lbl_titulo.pack(anchor="w")
            self._lbl_subtitulo = ctk.CTkLabel(
                enc, text="Configura un escenario y ejecuta la simulacion.",
                font=self._fuente(13), text_color=TXT_SUAVE)
            self._lbl_subtitulo.pack(anchor="w", pady=(2, 0))

            # Tarjetas KPI (3 x 2).
            kpis = ctk.CTkFrame(cont, fg_color="transparent")
            kpis.grid(row=1, column=0, sticky="ew", pady=(16, 14))
            for c in range(3):
                kpis.grid_columnconfigure(c, weight=1, uniform="kpi")

            # Iconos: solo glifos BMP (Tcl/Tk 8.6 no soporta emojis fuera del BMP).
            definicion = [
                ("exitos", "Encuestas guardadas", VERDE, "✓"),
                ("total_504", "Errores 504 / caidas", ROJO, "✕"),
                ("encuestas_perdidas", "Encuestas perdidas", AMBAR, "▼"),
                ("espera_cola_promedio", "Espera prom. en cola", TXT_SUAVE, "◔"),
                ("max_cola", "Tamanio max. cola BD", TXT_SUAVE, "▤"),
                ("pico_conexiones", "Pico conexiones / 60", VERDE, "▲"),
            ]
            for i, (clave, titulo, color, icono) in enumerate(definicion):
                tarjeta = ctk.CTkFrame(kpis, corner_radius=16, fg_color=CARD,
                                       border_width=1, border_color=BORDE)
                tarjeta.grid(row=i // 3, column=i % 3, padx=8, pady=8, sticky="nsew")
                fila = ctk.CTkFrame(tarjeta, fg_color="transparent")
                fila.pack(fill="x", padx=18, pady=(16, 0))
                ctk.CTkLabel(fila, text=icono, font=self._fuente(15),
                             text_color=color).pack(side="left")
                ctk.CTkLabel(fila, text=titulo, font=self._fuente(12),
                             text_color=TXT_SUAVE).pack(side="left", padx=(8, 0))
                valor = ctk.CTkLabel(tarjeta, text="—",
                                     font=self._fuente(30, "bold"), text_color=color)
                valor.pack(anchor="w", padx=18, pady=(2, 16))
                self._tarjetas[clave] = valor

            # Zona inferior: grafico (izq) + diagnostico (der).
            inferior = ctk.CTkFrame(cont, fg_color="transparent")
            inferior.grid(row=2, column=0, sticky="nsew")
            inferior.grid_columnconfigure(0, weight=3, uniform="bot")
            inferior.grid_columnconfigure(1, weight=2, uniform="bot")
            inferior.grid_rowconfigure(0, weight=1)

            marco_g = ctk.CTkFrame(inferior, corner_radius=16, fg_color=CARD,
                                   border_width=1, border_color=BORDE)
            marco_g.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
            self._figura = Figure(figsize=(6.4, 4.0), dpi=100, facecolor=CARD)
            self._ax = self._figura.add_subplot(111)
            self._ax.set_facecolor(CARD)
            self._figura.subplots_adjust(left=0.11, right=0.97, top=0.88, bottom=0.14)
            self._render_grafico_inicial()
            self._canvas = FigureCanvasTkAgg(self._figura, master=marco_g)
            self._canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

            marco_d = ctk.CTkFrame(inferior, corner_radius=16, fg_color=CARD,
                                   border_width=1, border_color=BORDE)
            marco_d.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
            ctk.CTkLabel(marco_d, text="Diagnostico y recomendaciones",
                         font=self._fuente(15, "bold"), text_color=VERDE).pack(
                anchor="w", padx=16, pady=(16, 6))
            self._txt_diag = ctk.CTkTextbox(
                marco_d, font=ctk.CTkFont(family="Consolas", size=12), wrap="word",
                fg_color="#FAFCF7", border_width=0, text_color=TXT)
            self._txt_diag.pack(fill="both", expand=True, padx=16, pady=(0, 14))
            self._txt_diag.insert("1.0", "Ejecuta una simulacion para ver el diagnostico.")
            self._txt_diag.configure(state="disabled")

            # Boton de exportacion PDF (parte inferior, destacado).
            self._btn_pdf = ctk.CTkButton(
                cont, text="▣   Generar Reporte PDF para Informe", height=50,
                corner_radius=14, font=self._fuente(16, "bold"),
                fg_color=VERDE_PDF, hover_color=VERDE_PDF_HOVER,
                state="disabled", command=self._on_exportar_pdf)
            self._btn_pdf.grid(row=3, column=0, sticky="ew", pady=(16, 0))

        def _render_grafico_inicial(self):
            self._ax.clear()
            self._ax.axhline(POOLER_CAPACITY, color=ROJO, linestyle="--", linewidth=1.4,
                             label=f"Limite del pooler ({POOLER_CAPACITY})")
            self._ax.set_ylim(0, POOLER_CAPACITY + 6)
            self._ax.set_title("Conexiones ocupadas en el Pooler",
                               fontsize=12, fontweight="bold", color=TXT, pad=12)
            self._ax.set_xlabel("Tiempo de la jornada (min)", fontsize=10, color="#3A4A30")
            self._ax.set_ylabel("Conexiones concurrentes", fontsize=10, color="#3A4A30")
            self._ax.legend(loc="upper right", fontsize=8)
            self._ax.grid(True, alpha=0.25, color="#9DB089")
            for lado in ("top", "right"):
                self._ax.spines[lado].set_visible(False)

        # ---------- LOGICA ----------
        def _actualizar_descripcion(self):
            cfg = SCENARIOS[self._escenario.get()]
            self._lbl_desc.configure(text=cfg.descripcion)

        def _on_ejecutar(self):
            if self._ejecutando:
                return
            self._ejecutando = True
            escenario = self._escenario.get()
            replicas = int(self._replicas.get())
            self._btn.configure(state="disabled", text="Simulando...")
            self._btn_pdf.configure(state="disabled")
            self._lbl_estado.configure(
                text=f"Corriendo {replicas} replica/s de '{escenario}'...", text_color=AMBAR)
            threading.Thread(target=self._trabajo_simulacion,
                             args=(escenario, replicas), daemon=True).start()

        def _trabajo_simulacion(self, escenario: str, replicas: int):
            try:
                agg = correr_experimento(escenario, n_replicas=replicas)
                self.after(0, lambda: self._mostrar_resultados(agg))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda e=exc: self._reportar_error(e))

        def _reportar_error(self, exc: Exception):
            self._ejecutando = False
            self._btn.configure(state="normal", text="►  Ejecutar simulacion")
            self._lbl_estado.configure(text=f"Error: {exc}", text_color=ROJO)

        def _mostrar_resultados(self, agg: AggregatedResult):
            self._ultimo_agg = agg
            cfg = SCENARIOS[agg.escenario]
            self._lbl_titulo.configure(text=f"Resultados  ·  Escenario {agg.escenario}")
            tasa = 100.0 * agg.media("exitos") / cfg.n_comensales
            self._lbl_subtitulo.configure(
                text=f"{agg.n_replicas} replica/s  ·  tasa de exito {tasa:.1f}%  ·  "
                     f"pico {agg.media('pico_conexiones'):.0f}/{POOLER_CAPACITY} conexiones")

            def fmt(clave, dec=0):
                media, desvio = agg.media(clave), agg.desvio(clave)
                txt = f"{media:.{dec}f}"
                if agg.n_replicas > 1 and desvio > 0:
                    txt += f"  ±{desvio:.{dec}f}"
                return txt

            self._tarjetas["exitos"].configure(
                text=f"{agg.media('exitos'):.0f} / {cfg.n_comensales}")
            self._tarjetas["total_504"].configure(text=fmt("total_504", 1))
            self._tarjetas["encuestas_perdidas"].configure(text=fmt("encuestas_perdidas", 1))
            self._tarjetas["espera_cola_promedio"].configure(
                text=f"{agg.media('espera_cola_promedio'):.2f} s")
            self._tarjetas["max_cola"].configure(text=fmt("max_cola", 0))
            self._tarjetas["pico_conexiones"].configure(
                text=f"{agg.media('pico_conexiones'):.0f} / {POOLER_CAPACITY}")

            dibujar_curva_conexiones(self._ax, agg)
            self._figura.subplots_adjust(left=0.11, right=0.97, top=0.88, bottom=0.14)
            self._canvas.draw()

            self._txt_diag.configure(state="normal")
            self._txt_diag.delete("1.0", "end")
            self._txt_diag.insert("1.0", generar_diagnostico(agg))
            self._txt_diag.configure(state="disabled")

            self._ejecutando = False
            self._btn.configure(state="normal", text="►  Ejecutar simulacion")
            self._btn_pdf.configure(state="normal")
            self._lbl_estado.configure(text="Simulacion finalizada.", text_color=VERDE)

        def _on_exportar_pdf(self):
            if self._ultimo_agg is None:
                return
            self._btn_pdf.configure(state="disabled", text="Generando PDF...")
            self._lbl_estado.configure(text="Compilando reporte PDF...", text_color=AMBAR)
            threading.Thread(target=self._trabajo_pdf, daemon=True).start()

        def _trabajo_pdf(self):
            try:
                ruta = exportar_reporte_pdf(self._ultimo_agg)
                self.after(0, lambda: self._pdf_ok(ruta))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda e=exc: self._pdf_error(e))

        def _pdf_ok(self, ruta: str):
            self._btn_pdf.configure(state="normal",
                                    text="▣   Generar Reporte PDF para Informe")
            self._lbl_estado.configure(text="PDF generado correctamente.", text_color=VERDE)
            try:
                os.startfile(ruta)  # Abre el PDF en el visor por defecto (Windows).
            except Exception:  # noqa: BLE001
                pass

        def _pdf_error(self, exc: Exception):
            self._btn_pdf.configure(state="normal",
                                    text="▣   Generar Reporte PDF para Informe")
            self._lbl_estado.configure(text=f"Error al generar PDF: {exc}", text_color=ROJO)

    app = SimuladorApp()
    app.mainloop()


# ---------------------------------------------------------------------------
# PUNTO DE ENTRADA
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulador de estres del Connection Pooler de Supabase (Grupo 2).")
    parser.add_argument("--cli", action="store_true",
                        help="Corre los 3 escenarios por consola (sin interfaz grafica).")
    parser.add_argument("--replicas", type=int, default=N_REPLICAS_DEFAULT,
                        help="Cantidad de corridas por escenario en modo --cli.")
    parser.add_argument("--smoke-gui", action="store_true",
                        help="Abre la GUI, corre una simulacion y la cierra sola (test).")
    parser.add_argument("--test-pdf", type=str, default=None,
                        help="Genera un PDF del escenario indicado y sale (test).")
    args = parser.parse_args()

    if args.cli:
        correr_cli(n_replicas=args.replicas)
    elif args.test_pdf:
        agg = correr_experimento(args.test_pdf, n_replicas=args.replicas)
        ruta = exportar_reporte_pdf(agg)
        print(f"PDF generado en: {ruta}")
    elif args.smoke_gui:
        lanzar_gui(auto_close_ms=5000)
    else:
        lanzar_gui()


if __name__ == "__main__":
    main()
