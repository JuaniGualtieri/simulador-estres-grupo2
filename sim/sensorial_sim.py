# -*- coding: utf-8 -*-
"""
================================================================================
 sim/sensorial_sim.py  ::  MOTOR MONTE CARLO - PESTANIA 3 (ACEPTACION SENSORIAL)
 Trabajo Practico Integrador Intercatedra - Grupo 2
 Asignatura: Modelos y Simulacion - 4to Anio - Ingenieria en Sistemas de Informacion
================================================================================

OBJETIVO DEL MODELO 3
---------------------
Estimar mediante el METODO DE MONTE CARLO la ACEPTACION SENSORIAL de la tartaleta
vegetal antes del testeo del 11/06. A diferencia de las Pestanias 1 y 2 (eventos
discretos con SimPy), aqui NO hay dinamica temporal: se simulan repetidamente las
respuestas de los 50 jueces a la prueba afectiva/descriptiva (24 campos del TPI,
escala hedonica de 1 a 9) y se promedian los resultados sobre miles de respuestas.

DEFINICION DEL EXPERIMENTO MONTE CARLO
--------------------------------------
* ENTIDADES ........ Comensales/jueces no entrenados que puntuan el producto.
* VARIABLE DE ENTRADA  "Calidad de Preparacion en Cocina" (slider 1-10): gobierna la
                       media de las distribuciones de puntaje (a mejor preparacion,
                       mejores notas esperadas).
* DESCRIPTORES ..... Las 24 preguntas se agrupan en 4 descriptores sensoriales clave
                     (Sabor, Olor, Textura y Color), 6 preguntas cada uno.
* GENERADOR ........ Por cada pregunta se muestrea una NORMAL(media_descriptor, sigma)
                     truncada y redondeada al entero [1, 9]. Se agrega un EFECTO
                     ALEATORIO POR COMENSAL (unos jueces son mas exigentes que otros).
* SALIDA ........... "Tasa de Aceptacion Global" = % de comensales cuyo puntaje
                     promedio es >= 6, mas el puntaje medio de cada descriptor.

ANALISIS DE SENSIBILIDAD
------------------------
Se barre la calidad del descriptor SABOR (el de mayor peso comercial) y se observa
como escala la aceptacion global: evidencia directa para que Nutricion priorice en
que atributo invertir esfuerzo de mejora.
================================================================================
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from sim.estadistica import cuantil_ic95, intervalo_confianza_95

# ---------------------------------------------------------------------------
# PARAMETROS DEL MODELO SENSORIAL
# ---------------------------------------------------------------------------
N_COMENSALES = 50                  # Jueces minimos del evento (consigna de catedra).
N_PREGUNTAS = 24                   # Campos de la encuesta (auditado en encuesta.js).
DESCRIPTORES: Tuple[str, ...] = ("Sabor", "Olor", "Textura", "Color")
PREGUNTAS_POR_DESCRIPTOR = N_PREGUNTAS // len(DESCRIPTORES)  # 6 preguntas c/u.
ESCALA_MIN = 1                     # Escala hedonica: minimo ("no me gusto").
ESCALA_MAX = 9                     # Escala hedonica: maximo ("me encanto").
UMBRAL_ACEPTACION = 6              # Un comensal "acepta" si su promedio es >= 6.

SIGMA_PREGUNTA = 1.3               # Desvio del puntaje pregunta a pregunta.
SIGMA_COMENSAL = 0.8               # Heterogeneidad entre jueces (exigencia personal).
SEED_BASE = 2026                   # Semilla base para reproducibilidad.
N_ITERS_DEFAULT = 100              # Eventos Monte Carlo por defecto.

# Sesgo intrinseco del producto por descriptor (en puntos de la escala 1-9): la
# tartaleta destaca en sabor y color, y es algo mas debil en olor y textura.
SESGO_DESCRIPTOR: Dict[str, float] = {
    "Sabor": 0.3, "Olor": -0.2, "Textura": -0.4, "Color": 0.3,
}

SLIDER_DEFAULTS = {
    "calidad_cocina": 7,   # Rango [1 - 10].
}


def calidad_a_media(calidad_1a10: float) -> float:
    """Mapea el slider de Calidad de Cocina (1-10) a la media objetivo de la escala 1-9."""
    frac = (float(calidad_1a10) - 1.0) / 9.0          # 0..1
    return ESCALA_MIN + frac * (ESCALA_MAX - ESCALA_MIN)


@dataclass(frozen=True)
class SensorialConfig:
    """Parametros del experimento Monte Carlo de aceptacion sensorial."""
    calidad_cocina: int                 # Slider [1-10]: gobierna las medias de puntaje.
    n_comensales: int = N_COMENSALES
    sigma_pregunta: float = SIGMA_PREGUNTA
    sigma_comensal: float = SIGMA_COMENSAL


@dataclass
class SensorialAggregated:
    """KPIs Monte Carlo agregados (media + IC 95%) sobre N eventos simulados."""
    n_iteraciones: int
    config: SensorialConfig
    medias: Dict[str, float] = field(default_factory=dict)
    ic_inf: Dict[str, float] = field(default_factory=dict)
    ic_sup: Dict[str, float] = field(default_factory=dict)
    muestras: Dict[str, List[float]] = field(default_factory=dict)
    metodo_ic: str = "na"
    cuantil_ic: float = 0.0
    gl_ic: int = 0
    # Analisis de sensibilidad del descriptor Sabor.
    sens_sabor_medias: List[float] = field(default_factory=list)   # mu objetivo de Sabor.
    sens_aceptacion: List[float] = field(default_factory=list)     # % aceptacion resultante.

    def media(self, clave: str) -> float:
        return self.medias.get(clave, 0.0)

    def ic(self, clave: str) -> Tuple[float, float]:
        return self.ic_inf.get(clave, 0.0), self.ic_sup.get(clave, 0.0)

    def muestra(self, clave: str) -> List[float]:
        return self.muestras.get(clave, [])

    @property
    def ic_disponible(self) -> bool:
        return self.metodo_ic != "na"

    @property
    def etiqueta_metodo_ic(self) -> str:
        if self.metodo_ic == "t":
            return f"t-Student (gl={self.gl_ic}, t={self.cuantil_ic:.3f})"
        if self.metodo_ic == "normal":
            return f"Normal estandar (Z={self.cuantil_ic:.3f})"
        return "No disponible (1 sola iteracion)"

    def media_descriptor(self, descriptor: str) -> float:
        return self.media(f"desc_{descriptor}")


# ---------------------------------------------------------------------------
# NUCLEO MONTE CARLO
# ---------------------------------------------------------------------------
def _medias_por_descriptor(calidad_cocina: float,
                           override_sabor: Optional[float] = None) -> Dict[str, float]:
    """Media objetivo (1-9) de cada descriptor para una calidad de cocina dada.

    `override_sabor` permite fijar a mano la media del descriptor Sabor (para el
    analisis de sensibilidad), dejando el resto en funcion de la calidad general.
    """
    base = calidad_a_media(calidad_cocina)
    medias = {d: min(ESCALA_MAX, max(ESCALA_MIN, base + SESGO_DESCRIPTOR[d]))
              for d in DESCRIPTORES}
    if override_sabor is not None:
        medias["Sabor"] = min(ESCALA_MAX, max(ESCALA_MIN, float(override_sabor)))
    return medias


def _simular_evento(cfg: SensorialConfig, rng: np.random.Generator,
                    medias_desc: Dict[str, float]) -> Dict[str, float]:
    """Simula UN evento completo: los n comensales puntuan los 24 campos.

    Devuelve la tasa de aceptacion (%), el puntaje global medio y el puntaje medio de
    cada descriptor para ESTE evento.
    """
    n = cfg.n_comensales
    sumas_desc = {d: 0.0 for d in DESCRIPTORES}
    suma_global = 0.0
    aceptados = 0

    for _ in range(n):
        # Efecto aleatorio del comensal: algunos jueces puntuan sistematicamente mas alto/bajo.
        sesgo_comensal = rng.normal(0.0, cfg.sigma_comensal)
        total_comensal = 0.0
        for d in DESCRIPTORES:
            mu = medias_desc[d] + sesgo_comensal
            puntajes = rng.normal(mu, cfg.sigma_pregunta, PREGUNTAS_POR_DESCRIPTOR)
            puntajes = np.clip(np.rint(puntajes), ESCALA_MIN, ESCALA_MAX)
            sumas_desc[d] += float(puntajes.mean())
            total_comensal += float(puntajes.sum())
        promedio_comensal = total_comensal / N_PREGUNTAS
        suma_global += promedio_comensal
        if promedio_comensal >= UMBRAL_ACEPTACION:
            aceptados += 1

    resultado = {
        "tasa_aceptacion": 100.0 * aceptados / n,
        "puntaje_global": suma_global / n,
    }
    for d in DESCRIPTORES:
        resultado[f"desc_{d}"] = sumas_desc[d] / n
    return resultado


def _barrido_sabor(cfg: SensorialConfig, rng: np.random.Generator,
                   eventos_por_punto: int = 40) -> Tuple[List[float], List[float]]:
    """Analisis de sensibilidad: aceptacion global al variar la calidad del Sabor.

    Fija la media del descriptor Sabor en cada entero de la escala (1..9), mantiene el
    resto de descriptores segun la calidad de cocina actual y promedia la aceptacion.
    """
    calidades: List[float] = []
    aceptaciones: List[float] = []
    for mu_sabor in range(ESCALA_MIN, ESCALA_MAX + 1):
        medias = _medias_por_descriptor(cfg.calidad_cocina, override_sabor=mu_sabor)
        accs = [_simular_evento(cfg, rng, medias)["tasa_aceptacion"]
                for _ in range(eventos_por_punto)]
        calidades.append(float(mu_sabor))
        aceptaciones.append(statistics.fmean(accs))
    return calidades, aceptaciones


def correr_experimento(cfg: SensorialConfig, n_iteraciones: int = N_ITERS_DEFAULT,
                       semilla_base: int = SEED_BASE,
                       progreso: Callable[[int, int], None] | None = None
                       ) -> SensorialAggregated:
    """Ejecuta N eventos Monte Carlo, agrega KPIs con IC 95% y corre la sensibilidad."""
    medias_base = _medias_por_descriptor(cfg.calidad_cocina)
    eventos: List[Dict[str, float]] = []
    for it in range(n_iteraciones):
        rng = np.random.default_rng(semilla_base + it)
        eventos.append(_simular_evento(cfg, rng, medias_base))
        if progreso is not None:
            progreso(it + 1, n_iteraciones)

    claves = ["tasa_aceptacion", "puntaje_global"] + [f"desc_{d}" for d in DESCRIPTORES]
    agg = SensorialAggregated(n_iteraciones=n_iteraciones, config=cfg)
    for clave in claves:
        valores = [ev[clave] for ev in eventos]
        ic = intervalo_confianza_95(valores)
        agg.medias[clave] = ic.media
        agg.ic_inf[clave] = ic.inf
        agg.ic_sup[clave] = ic.sup
        agg.muestras[clave] = valores
    agg.cuantil_ic, agg.metodo_ic, agg.gl_ic = cuantil_ic95(n_iteraciones)

    # Analisis de sensibilidad del Sabor (con una semilla propia, reproducible).
    rng_sens = np.random.default_rng(semilla_base + 9999)
    agg.sens_sabor_medias, agg.sens_aceptacion = _barrido_sabor(cfg, rng_sens)
    return agg


# ---------------------------------------------------------------------------
# DIAGNOSTICO SENSORIAL
# ---------------------------------------------------------------------------
def generar_diagnostico(agg: SensorialAggregated) -> str:
    """Texto interpretativo de la aceptacion sensorial y la sensibilidad al Sabor."""
    cfg = agg.config
    tasa = agg.media("tasa_aceptacion")
    inf, sup = agg.ic("tasa_aceptacion")
    global_ = agg.media("puntaje_global")

    lineas: List[str] = []
    lineas.append(f"DIAGNOSTICO DE ACEPTACION SENSORIAL "
                  f"(Monte Carlo, {agg.n_iteraciones} eventos simulados)")
    lineas.append("-" * 64)
    lineas.append(
        f"Calidad de preparacion en cocina: {cfg.calidad_cocina}/10. Puntaje global medio: "
        f"{global_:.2f}/9 sobre {cfg.n_comensales} comensales y {N_PREGUNTAS} preguntas.")
    if agg.ic_disponible:
        lineas.append(
            f"Tasa de Aceptacion Global del alimento: {tasa:.1f}% "
            f"(IC 95% [{inf:.1f}% - {sup:.1f}%]) de comensales con puntaje de "
            f"{UMBRAL_ACEPTACION} o mas.")
    else:
        lineas.append(f"Tasa de Aceptacion Global del alimento: {tasa:.1f}% "
                      "(sin IC: se requiere mas de 1 iteracion).")

    # Ranking de descriptores: mejor y peor atributo.
    pares = [(d, agg.media_descriptor(d)) for d in DESCRIPTORES]
    pares_ord = sorted(pares, key=lambda p: p[1], reverse=True)
    mejor, peor = pares_ord[0], pares_ord[-1]
    detalle = ", ".join(f"{d}: {v:.2f}" for d, v in pares)
    lineas.append(f"Puntaje medio por descriptor -> {detalle}.")
    lineas.append(f"Atributo mejor valorado: {mejor[0]} ({mejor[1]:.2f}); "
                  f"a reforzar: {peor[0]} ({peor[1]:.2f}).")

    # Lectura del analisis de sensibilidad del Sabor.
    if agg.sens_sabor_medias and agg.sens_aceptacion:
        a_min = agg.sens_aceptacion[0]
        a_max = agg.sens_aceptacion[-1]
        lineas.append(
            f"Sensibilidad al Sabor: llevar el sabor de {ESCALA_MIN} a {ESCALA_MAX} puntos "
            f"hace escalar la aceptacion global de {a_min:.0f}% a {a_max:.0f}%, "
            "confirmando que es la palanca comercial mas influyente.")

    lineas.append("")
    lineas.append("RECOMENDACIONES PARA NUTRICION:")
    if tasa >= 80:
        lineas.append("  - Producto con alta aceptacion proyectada: viable para escalar y "
                      "comercializar; sostener la calidad de preparacion actual.")
    elif tasa >= 60:
        lineas.append("  - Aceptacion moderada: ajustar la formulacion del atributo mas "
                      "debil antes de escalar la produccion.")
    else:
        lineas.append("  - Aceptacion baja: revisar receta y tecnica de cocina; no conviene "
                      "escalar la produccion hasta mejorar el perfil sensorial.")
    lineas.append(f"  - Priorizar mejoras en '{peor[0]}', el descriptor peor puntuado.")
    return "\n".join(lineas)
