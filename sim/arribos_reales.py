# -*- coding: utf-8 -*-
"""
================================================================================
 sim/arribos_reales.py  ::  HORARIOS REALES DE ARRIBO DEL STAND (Caso Real)
 Trabajo Practico Integrador Intercatedra - Grupo 2
================================================================================

Marcas de tiempo REALES de los 64 comensales atendidos en el stand de la Planta
Piloto el jueves 11/06/2026, de 08:19:08 a 09:42:25 (jornada de 83,28 min).
Fuente: planilla "horas.xlsx" (columna hora_ajustada); ver tambien
horas_ajustadas.csv en la raiz del repo para trazabilidad.

ARRIBOS_MIN contiene el MINUTO RELATIVO de cada arribo medido desde el primer
comensal (t = 0.0 = 08:19:08). Esta es la agenda de llegadas que conduce la
simulacion de la cadena de produccion (Pestania 2): los comensales NO se generan
con una exponencial sintetica sino que arriban exactamente cuando lo hicieron en
la realidad. El inter-arribo medio empirico es 1,322 min, coherente con la
Exponencial teorica de media 1,32 min (lo que valida el ajuste del modelo).

Modulo de DATOS puro: sin logica de simulacion ni de renderizado.
"""

from __future__ import annotations

# Minuto relativo de cada uno de los 64 arribos reales (t=0 -> primer comensal).
ARRIBOS_MIN = [
    0.0000, 0.4000, 0.4333, 1.7000, 3.3167, 4.4333, 4.7667, 9.3167,
    13.4833, 15.5000, 19.3333, 20.3667, 20.4667, 21.3000, 21.5000, 22.0500,
    24.1667, 26.4000, 26.6500, 27.3833, 27.8167, 27.9167, 29.4667, 29.5333,
    32.0833, 33.1167, 33.1333, 33.7000, 36.4833, 39.2000, 39.3500, 40.1000,
    41.7000, 42.5667, 42.9333, 43.0667, 44.2333, 44.3833, 44.6667, 47.9500,
    50.7333, 52.2000, 52.2000, 52.2000, 54.7667, 55.6333, 56.5167, 57.4500,
    61.7333, 64.8000, 65.2833, 65.4333, 68.4333, 68.4333, 72.3333, 73.2167,
    73.9333, 74.5000, 74.8667, 75.5000, 77.6500, 78.3333, 78.5000, 83.2833,
]

# Cantidad de comensales reales y duracion observada de la jornada (min).
N_ARRIBOS_REALES = len(ARRIBOS_MIN)
DURACION_JORNADA_MIN = ARRIBOS_MIN[-1] - ARRIBOS_MIN[0]


def interarribos_min() -> list[float]:
    """Tiempos entre arribos consecutivos (min), para la validacion V&V del modelo."""
    return [ARRIBOS_MIN[i] - ARRIBOS_MIN[i - 1] for i in range(1, len(ARRIBOS_MIN))]
