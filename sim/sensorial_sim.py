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
respuestas de los 50 comensales a la NUEVA ENCUESTA REAL de 12 preguntas y se
promedian los resultados sobre miles de respuestas.

ESQUEMA LITERAL DE LA ENCUESTA (12 preguntas, ver capturas)
-----------------------------------------------------------
* Datos Generales .. ano_nacimiento (desplegable) y sexo [Masculino/Femenino].
* Vista ............ apariencia (1-10), intensidad de color (1-10) y si se
                     distinguen los ingredientes (Si/No).
* Olfato ........... intensidad del olor (1-10) y si se percibe el olor a las
                     verduras del relleno (Si/No).
* Tacto y Oido ..... temperatura al recibir (1-10) y crocancia de la masa (1-10).
* Gusto y Boca ..... integracion de los sabores (1-10).
* Sabor ............ sabor general en boca (1-10) y persistencia del sabor (1-10).
* Cierre ........... comentario_libre (texto opcional).

En total: 8 sliders numericos (1-10), 2 preguntas Si/No y 2 campos demograficos.

DEFINICION DEL EXPERIMENTO MONTE CARLO
--------------------------------------
* ENTIDADES ........ Comensales/jueces no entrenados que completan la encuesta web.
* VARIABLE DE ENTRADA  "Calidad de Preparacion en Cocina" (slider 1-10): gobierna la
                       media de las distribuciones de cada atributo (a mejor
                       preparacion, mejores notas y mas respuestas "Si" esperadas).
* GENERADOR ........ Cada slider se muestrea de una NORMAL(media_atributo, sigma)
                     truncada y redondeada al entero [1, 10]; cada Si/No de una
                     BERNOULLI cuya probabilidad de "Si" crece con la calidad. Se
                     agrega un EFECTO ALEATORIO POR COMENSAL (jueces mas/menos
                     exigentes que correlaciona todas sus respuestas).
* SALIDA ........... "Tasa de Aceptacion Global" = % de comensales cuyo
                     'sabor_general' simulado es >= 6, mas la media de cada atributo
                     y el % de "Si" de cada pregunta dicotomica.

ANALISIS DE SENSIBILIDAD
------------------------
Se barre la media objetivo del atributo SABOR GENERAL (palanca comercial directa de
la aceptacion) y se observa como escala la aceptacion global: evidencia directa para
que Nutricion priorice donde invertir esfuerzo de mejora.
================================================================================
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from sim.estadistica import cuantil_ic95, intervalo_confianza_95

# ---------------------------------------------------------------------------
# PARAMETROS GENERALES DEL MODELO SENSORIAL
# ---------------------------------------------------------------------------
N_COMENSALES = 50                  # Jueces minimos del evento (consigna de catedra).
N_PREGUNTAS_TOTAL = 12             # Campos obligatorios de la encuesta real (auditado).
ANIO_REFERENCIA = 2026             # Anio del evento (para convertir ano_nacimiento -> edad).
ESCALA_MIN = 1                     # Minimo de los sliders ("ni me gusta ni me disgusta").
ESCALA_MAX = 10                    # Maximo de los sliders ("me gusta mucho").
UMBRAL_ACEPTACION = 6              # Un comensal "acepta" si su 'sabor_general' es >= 6.

SIGMA_PREGUNTA = 1.3               # Desvio del puntaje atributo a atributo.
SIGMA_COMENSAL = 0.8               # Heterogeneidad entre jueces (exigencia personal).
SEED_BASE = 2026                   # Semilla base para reproducibilidad.
N_ITERS_DEFAULT = 100              # Eventos Monte Carlo por defecto.
PROB_COMENTARIO = 0.4              # Fraccion de comensales que dejan comentario libre.

# --- Los 8 sliders numericos (1-10) de la encuesta, en orden de aparicion ---
ATRIBUTOS_SLIDER: Tuple[str, ...] = (
    "vista_apariencia",
    "vista_intensidad_color",
    "olfato_intensidad",
    "tacto_temperatura",
    "tacto_crocancia",
    "boca_integracion_sabores",
    "sabor_general",
    "sabor_persistencia",
)

# --- Las 2 preguntas dicotomicas Si/No de la encuesta ---
ATRIBUTOS_BOOL: Tuple[str, ...] = (
    "vista_distingue_ingredientes",
    "olfato_olor_verduras",
)

# Etiquetas legibles (UI y reporte PDF) con la dimension sensorial entre parentesis.
ETIQUETAS: Dict[str, str] = {
    "vista_apariencia": "Apariencia general (Vista)",
    "vista_intensidad_color": "Intensidad de color (Vista)",
    "olfato_intensidad": "Intensidad de olor (Olfato)",
    "tacto_temperatura": "Temperatura al recibir (Tacto)",
    "tacto_crocancia": "Crocancia de la masa (Tacto y Oido)",
    "boca_integracion_sabores": "Integracion de sabores (Boca)",
    "sabor_general": "Sabor general (Sabor)",
    "sabor_persistencia": "Persistencia del sabor (Sabor)",
    "vista_distingue_ingredientes": "Distingue los ingredientes a la vista",
    "olfato_olor_verduras": "Percibe el olor a las verduras",
}

# Agrupacion por dimension (para titulos y diagnostico), respetando la encuesta real.
DIMENSIONES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Vista", ("vista_apariencia", "vista_intensidad_color",
               "vista_distingue_ingredientes")),
    ("Olfato", ("olfato_intensidad", "olfato_olor_verduras")),
    ("Tacto y Oido", ("tacto_temperatura", "tacto_crocancia")),
    ("Gusto y Boca", ("boca_integracion_sabores",)),
    ("Sabor", ("sabor_general", "sabor_persistencia")),
)

# Sesgo intrinseco del producto por atributo (en puntos de la escala 1-10): la tartaleta
# destaca en sabor y apariencia, y es algo mas debil en olor, temperatura y crocancia.
SESGO_ATRIBUTO: Dict[str, float] = {
    "vista_apariencia": 0.3,
    "vista_intensidad_color": 0.2,
    "olfato_intensidad": -0.2,
    "tacto_temperatura": -0.3,
    "tacto_crocancia": -0.4,
    "boca_integracion_sabores": 0.1,
    "sabor_general": 0.4,
    "sabor_persistencia": -0.1,
}

# Penalizacion critica cuando la cocina trabaja mal (calidad <= 4): ciertos atributos se
# desploman mas que otros. La apariencia y el sabor acusan de inmediato una mala
# preparacion; la temperatura cae si el relleno sale frio; en cambio la crocancia puede
# SOSTENERSE o incluso subir porque una masa pasada de coccion endurece (desvio realista).
PENALIZACION_BAJA_CALIDAD: Dict[str, float] = {
    "vista_apariencia": -1.3,
    "vista_intensidad_color": -0.8,
    "olfato_intensidad": -0.6,
    "tacto_temperatura": -1.1,
    "tacto_crocancia": 0.5,        # la sobrecoccion endurece: la crocancia no cae.
    "boca_integracion_sabores": -1.1,
    "sabor_general": -1.4,
    "sabor_persistencia": -0.7,
}

# Ajuste por atributo de la probabilidad base de responder "Si" (las dos cualitativas
# rondan la misma probabilidad, gobernada por la calidad, con un leve matiz propio).
OFFSET_BOOL: Dict[str, float] = {
    "vista_distingue_ingredientes": 0.05,
    "olfato_olor_verduras": -0.05,
}

SLIDER_DEFAULTS = {
    "calidad_cocina": 7,   # Rango [1 - 10].
}

# Pool de comentarios libres realistas para la simulacion de 'comentario_libre'.
COMENTARIOS_POSITIVOS: Tuple[str, ...] = (
    "Muy rica, se nota la frescura de las verduras del relleno.",
    "La masa quedo bien crocante y el relleno muy sabroso.",
    "Excelente presentacion y muy buen sabor, la volveria a comprar.",
    "Buena integracion de sabores, ni muy salada ni desabrida.",
    "El color y el aroma invitan a comerla, me encanto.",
    "Producto muy logrado para ser una opcion vegetal y sustentable.",
)
COMENTARIOS_NEGATIVOS: Tuple[str, ...] = (
    "La masa estaba algo blanda para mi gusto.",
    "Le falto sabor, la senti bastante desabrida.",
    "Estaba un poco fria cuando la recibi.",
    "Se sentia demasiado la cebolla, tapaba al resto de los ingredientes.",
    "La apariencia no me llamo la atencion.",
    "El sabor no perdura en boca, se va enseguida.",
)
COMENTARIOS_NEUTROS: Tuple[str, ...] = (
    "Esta bien, sin nada que destaque demasiado.",
    "Cumple, aunque podria mejorar un poco la sazon.",
    "Un producto correcto para servir en el evento.",
)


def calidad_a_media(calidad_1a10: float) -> float:
    """Mapea el slider de Calidad de Cocina (1-10) a la media objetivo de la escala 1-10.

    Como la escala de la encuesta tambien es 1-10, el mapeo es practicamente la
    identidad; se deja parametrizado para poder recalibrar la dureza del jurado.
    """
    frac = (float(calidad_1a10) - 1.0) / 9.0          # 0..1
    return ESCALA_MIN + frac * (ESCALA_MAX - ESCALA_MIN)


def _clip(valor: float, lo: float = ESCALA_MIN, hi: float = ESCALA_MAX) -> float:
    return min(hi, max(lo, valor))


@dataclass(frozen=True)
class SensorialConfig:
    """Parametros del experimento Monte Carlo de aceptacion sensorial."""
    calidad_cocina: int                 # Slider [1-10]: gobierna las medias de puntaje.
    n_comensales: int = N_COMENSALES
    sigma_pregunta: float = SIGMA_PREGUNTA
    sigma_comensal: float = SIGMA_COMENSAL


@dataclass
class RespuestaComensal:
    """Encuesta completa (12 campos + comentario) de UN comensal del panel representativo."""
    ano_nacimiento: int
    edad: int
    sexo: str                           # "Masculino" / "Femenino".
    sliders: Dict[str, int]             # Los 8 atributos numericos (1-10).
    cualitativas: Dict[str, bool]       # Las 2 preguntas Si/No (True = "Si").
    comentario: str                     # 'comentario_libre' (puede ser "").
    acepta: bool                        # True si su sabor_general >= UMBRAL_ACEPTACION.


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
    # Analisis de sensibilidad del atributo Sabor general.
    sens_sabor_medias: List[float] = field(default_factory=list)   # mu objetivo de sabor.
    sens_aceptacion: List[float] = field(default_factory=list)     # % aceptacion resultante.
    # Panel representativo de comensales (un evento) para demografia/cualitativas/comentarios.
    panel: List[RespuestaComensal] = field(default_factory=list)

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

    def prop_si(self, atributo: str) -> float:
        """% de respuestas 'Si' (medio Monte Carlo) de una pregunta dicotomica."""
        return self.media(f"prop_{atributo}")


# ---------------------------------------------------------------------------
# PERFILES DE DISTRIBUCION SEGUN LA CALIDAD DE COCINA
# ---------------------------------------------------------------------------
def _medias_por_atributo(calidad_cocina: float,
                         override_sabor: Optional[float] = None) -> Dict[str, float]:
    """Media objetivo (1-10) de cada slider para una calidad de cocina dada.

    Suma al nivel base (gobernado por la calidad) el sesgo intrinseco de cada atributo y,
    cuando la calidad es baja (<=4), una penalizacion critica diferenciada. `override_sabor`
    fija a mano la media de 'sabor_general' (usado por el analisis de sensibilidad).
    """
    base = calidad_a_media(calidad_cocina)
    # factor_bajo: 1.0 en calidad=1, decrece linealmente y vale 0 a partir de calidad>=5.
    factor_bajo = max(0.0, (5.0 - float(calidad_cocina)) / 4.0)
    medias = {}
    for attr in ATRIBUTOS_SLIDER:
        m = base + SESGO_ATRIBUTO[attr] + factor_bajo * PENALIZACION_BAJA_CALIDAD[attr]
        medias[attr] = _clip(m)
    if override_sabor is not None:
        medias["sabor_general"] = _clip(float(override_sabor))
    return medias


def _prob_si_por_atributo(calidad_cocina: float) -> Dict[str, float]:
    """Probabilidad de responder 'Si' en cada pregunta dicotomica segun la calidad.

    A mejor preparacion, mas comensales distinguen los ingredientes y perciben el aroma
    de las verduras (de ~12% en calidad 1 a ~95% en calidad 10).
    """
    frac = (float(calidad_cocina) - 1.0) / 9.0
    base = 0.12 + 0.83 * frac
    return {b: float(min(0.98, max(0.02, base + OFFSET_BOOL[b]))) for b in ATRIBUTOS_BOOL}


# ---------------------------------------------------------------------------
# NUCLEO MONTE CARLO (vectorizado por evento)
# ---------------------------------------------------------------------------
def _simular_evento(cfg: SensorialConfig, rng: np.random.Generator,
                    medias: Dict[str, float],
                    prob_si: Dict[str, float]) -> Dict[str, float]:
    """Simula UN evento completo: los n comensales responden la encuesta de 12 campos.

    Devuelve la media de cada slider, el % de 'Si' de cada dicotomica, la tasa de
    aceptacion (sabor_general >= umbral) y el puntaje global medio para ESTE evento.
    """
    n = cfg.n_comensales
    # Efecto aleatorio del comensal: correlaciona TODAS sus respuestas (juez exigente/blando).
    sesgo = rng.normal(0.0, cfg.sigma_comensal, n)

    valores: Dict[str, np.ndarray] = {}
    for attr in ATRIBUTOS_SLIDER:
        mu = medias[attr] + sesgo
        puntajes = rng.normal(mu, cfg.sigma_pregunta)
        valores[attr] = np.clip(np.rint(puntajes), ESCALA_MIN, ESCALA_MAX)

    resultado: Dict[str, float] = {}
    for attr in ATRIBUTOS_SLIDER:
        resultado[attr] = float(valores[attr].mean())

    sabor = valores["sabor_general"]
    resultado["tasa_aceptacion"] = 100.0 * float(np.mean(sabor >= UMBRAL_ACEPTACION))
    matriz = np.vstack([valores[a] for a in ATRIBUTOS_SLIDER])
    resultado["puntaje_global"] = float(matriz.mean())

    for b in ATRIBUTOS_BOOL:
        si = rng.random(n) < prob_si[b]
        resultado[f"prop_{b}"] = 100.0 * float(np.mean(si))
    return resultado


def _barrido_sabor(cfg: SensorialConfig, rng: np.random.Generator,
                   prob_si: Dict[str, float],
                   eventos_por_punto: int = 40) -> Tuple[List[float], List[float]]:
    """Analisis de sensibilidad: aceptacion global al variar la media del sabor general.

    Fija la media de 'sabor_general' en cada entero de la escala (1..10), mantiene el resto
    de atributos segun la calidad de cocina actual y promedia la aceptacion resultante.
    """
    calidades: List[float] = []
    aceptaciones: List[float] = []
    for mu_sabor in range(ESCALA_MIN, ESCALA_MAX + 1):
        medias = _medias_por_atributo(cfg.calidad_cocina, override_sabor=mu_sabor)
        accs = [_simular_evento(cfg, rng, medias, prob_si)["tasa_aceptacion"]
                for _ in range(eventos_por_punto)]
        calidades.append(float(mu_sabor))
        aceptaciones.append(statistics.fmean(accs))
    return calidades, aceptaciones


# ---------------------------------------------------------------------------
# PANEL REPRESENTATIVO (demografia + cualitativas + comentarios)
# ---------------------------------------------------------------------------
def _muestrear_edad(rng: np.random.Generator) -> int:
    """Edad de un comensal: Normal(32, 11) truncada a un rango realista [18, 70]."""
    return int(np.clip(round(rng.normal(32.0, 11.0)), 18, 70))


def _muestrear_comentario(rng: np.random.Generator, acepta: bool, sabor: int) -> str:
    """Comentario libre simulado: vacio en la mayoria de los casos; si lo hay, su tono
    se condice con la experiencia del comensal (positivo, neutro o critico)."""
    if rng.random() >= PROB_COMENTARIO:
        return ""                                   # La mayoria no deja comentario.
    if acepta and sabor >= 8:
        pool = COMENTARIOS_POSITIVOS
    elif not acepta:
        pool = COMENTARIOS_NEGATIVOS
    else:
        pool = COMENTARIOS_NEUTROS
    return str(rng.choice(pool))


def _generar_panel(cfg: SensorialConfig, rng: np.random.Generator,
                   medias: Dict[str, float],
                   prob_si: Dict[str, float]) -> List[RespuestaComensal]:
    """Genera un panel representativo de n comensales con TODOS los campos de la encuesta.

    Sirve para las analiticas que necesitan el detalle por comensal (demografia, % Si/No y
    comentarios), complementando los KPIs agregados del experimento Monte Carlo.
    """
    panel: List[RespuestaComensal] = []
    for _ in range(cfg.n_comensales):
        sesgo = rng.normal(0.0, cfg.sigma_comensal)
        sliders = {
            attr: int(np.clip(round(rng.normal(medias[attr] + sesgo, cfg.sigma_pregunta)),
                              ESCALA_MIN, ESCALA_MAX))
            for attr in ATRIBUTOS_SLIDER
        }
        cualitativas = {b: bool(rng.random() < prob_si[b]) for b in ATRIBUTOS_BOOL}
        edad = _muestrear_edad(rng)
        sexo = "Masculino" if rng.random() < 0.5 else "Femenino"
        acepta = sliders["sabor_general"] >= UMBRAL_ACEPTACION
        comentario = _muestrear_comentario(rng, acepta, sliders["sabor_general"])
        panel.append(RespuestaComensal(
            ano_nacimiento=ANIO_REFERENCIA - edad, edad=edad, sexo=sexo,
            sliders=sliders, cualitativas=cualitativas, comentario=comentario,
            acepta=acepta))
    return panel


# ---------------------------------------------------------------------------
# EXPERIMENTO COMPLETO
# ---------------------------------------------------------------------------
def correr_experimento(cfg: SensorialConfig, n_iteraciones: int = N_ITERS_DEFAULT,
                       semilla_base: int = SEED_BASE,
                       progreso: Callable[[int, int], None] | None = None
                       ) -> SensorialAggregated:
    """Ejecuta N eventos Monte Carlo, agrega KPIs con IC 95%, corre la sensibilidad del
    sabor y construye un panel representativo de comensales."""
    medias_base = _medias_por_atributo(cfg.calidad_cocina)
    prob_si = _prob_si_por_atributo(cfg.calidad_cocina)

    eventos: List[Dict[str, float]] = []
    for it in range(n_iteraciones):
        rng = np.random.default_rng(semilla_base + it)
        eventos.append(_simular_evento(cfg, rng, medias_base, prob_si))
        if progreso is not None:
            progreso(it + 1, n_iteraciones)

    claves = (list(ATRIBUTOS_SLIDER) + [f"prop_{b}" for b in ATRIBUTOS_BOOL]
              + ["tasa_aceptacion", "puntaje_global"])
    agg = SensorialAggregated(n_iteraciones=n_iteraciones, config=cfg)
    for clave in claves:
        valores = [ev[clave] for ev in eventos]
        ic = intervalo_confianza_95(valores)
        agg.medias[clave] = ic.media
        agg.ic_inf[clave] = ic.inf
        agg.ic_sup[clave] = ic.sup
        agg.muestras[clave] = valores
    agg.cuantil_ic, agg.metodo_ic, agg.gl_ic = cuantil_ic95(n_iteraciones)

    # Analisis de sensibilidad del sabor general (semilla propia, reproducible).
    rng_sens = np.random.default_rng(semilla_base + 9999)
    agg.sens_sabor_medias, agg.sens_aceptacion = _barrido_sabor(cfg, rng_sens, prob_si)

    # Panel representativo de comensales (semilla propia, reproducible).
    rng_panel = np.random.default_rng(semilla_base + 4242)
    agg.panel = _generar_panel(cfg, rng_panel, medias_base, prob_si)
    return agg


# ---------------------------------------------------------------------------
# RESUMEN DEMOGRAFICO (reutilizado por la UI web y el reporte PDF)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResumenDemografico:
    n: int
    n_masculino: int
    n_femenino: int
    edad_media: float
    edad_min: int
    edad_max: int

    @property
    def pct_masculino(self) -> float:
        return 100.0 * self.n_masculino / self.n if self.n else 0.0

    @property
    def pct_femenino(self) -> float:
        return 100.0 * self.n_femenino / self.n if self.n else 0.0


def resumen_demografico(agg: SensorialAggregated) -> ResumenDemografico:
    """Sintetiza la demografia del panel representativo (sexo y edades)."""
    panel = agg.panel
    n = len(panel)
    if n == 0:
        return ResumenDemografico(0, 0, 0, 0.0, 0, 0)
    n_masc = sum(1 for c in panel if c.sexo == "Masculino")
    edades = [c.edad for c in panel]
    return ResumenDemografico(
        n=n, n_masculino=n_masc, n_femenino=n - n_masc,
        edad_media=statistics.fmean(edades), edad_min=min(edades), edad_max=max(edades))


def comentarios_panel(agg: SensorialAggregated, limite: int = 8) -> List[str]:
    """Devuelve hasta `limite` comentarios libres no vacios del panel representativo."""
    comentarios = [c.comentario for c in agg.panel if c.comentario]
    return comentarios[:limite]


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
        f"{global_:.2f}/10 sobre {cfg.n_comensales} comensales y "
        f"{N_PREGUNTAS_TOTAL} preguntas de la encuesta.")
    if agg.ic_disponible:
        lineas.append(
            f"Tasa de Aceptacion Global del alimento: {tasa:.1f}% "
            f"(IC 95% [{inf:.1f}% - {sup:.1f}%]) de comensales con 'sabor general' de "
            f"{UMBRAL_ACEPTACION} o mas.")
    else:
        lineas.append(f"Tasa de Aceptacion Global del alimento: {tasa:.1f}% "
                      "(sin IC: se requiere mas de 1 iteracion).")

    # Ranking de atributos numericos: mejor y peor valorado.
    pares = [(attr, agg.media(attr)) for attr in ATRIBUTOS_SLIDER]
    pares_ord = sorted(pares, key=lambda p: p[1], reverse=True)
    mejor, peor = pares_ord[0], pares_ord[-1]
    lineas.append(f"Atributo mejor valorado: {ETIQUETAS[mejor[0]]} ({mejor[1]:.2f}/10); "
                  f"a reforzar: {ETIQUETAS[peor[0]]} ({peor[1]:.2f}/10).")

    # Lectura de las dos preguntas cualitativas (Si/No).
    for b in ATRIBUTOS_BOOL:
        lineas.append(f"{ETIQUETAS[b]}: {agg.prop_si(b):.0f}% de los comensales respondio 'Si'.")

    # Perfil demografico del panel.
    demo = resumen_demografico(agg)
    if demo.n:
        lineas.append(
            f"Panel: {demo.n} comensales ({demo.pct_masculino:.0f}% masculino / "
            f"{demo.pct_femenino:.0f}% femenino), edad media {demo.edad_media:.0f} anios "
            f"(rango {demo.edad_min}-{demo.edad_max}).")

    # Lectura del analisis de sensibilidad del sabor.
    if agg.sens_sabor_medias and agg.sens_aceptacion:
        a_min = agg.sens_aceptacion[0]
        a_max = agg.sens_aceptacion[-1]
        lineas.append(
            f"Sensibilidad al Sabor: llevar el sabor general de {ESCALA_MIN} a {ESCALA_MAX} "
            f"puntos hace escalar la aceptacion global de {a_min:.0f}% a {a_max:.0f}%, "
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
    lineas.append(f"  - Priorizar mejoras en '{ETIQUETAS[peor[0]]}', el atributo peor puntuado.")
    return "\n".join(lineas)
