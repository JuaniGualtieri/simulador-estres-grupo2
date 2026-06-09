# -*- coding: utf-8 -*-
"""
================================================================================
 sim/estadistica.py  ::  RIGOR ESTADISTICO COMPARTIDO (IC y Validacion de Generadores)
 Trabajo Practico Integrador Intercatedra - Grupo 2
 Asignatura: Modelos y Simulacion - 4to Anio - Ingenieria en Sistemas de Informacion
================================================================================

Modulo TRANSVERSAL que centraliza dos piezas de rigor estadistico exigidas por la
catedra, evitando duplicar la matematica entre los motores de Pestania 1 (servidor),
Pestania 2 (produccion) y Pestania 3 (aceptacion sensorial Monte Carlo):

  1) INTERVALOS DE CONFIANZA DEL 95% CON CORRECCION PARA MUESTRAS PEQUENIAS.
     La eleccion del cuantil deja de ser un Z=1,96 estatico y respeta la teoria del
     muestreo:
         * n < 2  ........ NO se puede estimar la variabilidad -> IC no disponible.
         * 2 <= n < 30 ... Muestra PEQUENIA -> distribucion t de Student con n-1
                           grados de libertad (p. ej. n=10 -> gl=9 -> t=2,262).
         * n >= 30 ....... Muestra GRANDE -> Teorema Central del Limite -> Normal
                           estandar (Z=1,960), como en n=30 o n=50 replicas.

  2) VALIDACION DE LOS GENERADORES DE NUMEROS PSEUDOALEATORIOS (V&V).
     Contrasta el Tiempo Medio Entre Arribos EMPIRICO (medido sobre las muestras que
     NumPy genero durante la corrida) contra el valor TEORICO esperado de la
     Exponencial, E(X) = ventana_de_arribos / cantidad_de_comensales, certificando
     que el modelo reproduce el comportamiento del sistema real.
================================================================================
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Sequence, Tuple

# Cuantil de la Normal estandar para el IC del 95% (muestras grandes, n >= 30).
Z_95 = 1.959963984540054

# A partir de cuantas replicas se considera la muestra "grande" (TCL -> Normal).
UMBRAL_MUESTRA_GRANDE = 30

# -----------------------------------------------------------------------------
# Tabla de la distribucion t de Student (dos colas, nivel de confianza del 95%).
# Valor critico t_{0,975 ; gl} por grados de libertad (gl = n - 1). Es la misma
# tabla que se consulta en un examen de la materia; para gl >= 30 se usa la Normal.
# -----------------------------------------------------------------------------
T_STUDENT_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080,
    22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048,
    29: 2.045,
}


@dataclass(frozen=True)
class ICResult:
    """Resultado de un Intervalo de Confianza del 95% (con su trazabilidad teorica)."""
    media: float
    inf: float
    sup: float
    metodo: str          # "t" (t-Student), "normal" (Z) o "na" (no disponible, n<2).
    cuantil: float       # Valor critico aplicado (t o Z).
    gl: int              # Grados de libertad (n-1); 0 si no aplica.
    n: int               # Tamanio de la muestra (cantidad de replicas).
    desvio_muestral: float
    error_estandar: float

    @property
    def disponible(self) -> bool:
        """True si hubo al menos 2 replicas para estimar la dispersion."""
        return self.metodo != "na"

    @property
    def etiqueta_metodo(self) -> str:
        """Descripcion legible del metodo aplicado (para la UI y el reporte)."""
        if self.metodo == "t":
            return f"t-Student (gl={self.gl}, t={self.cuantil:.3f})"
        if self.metodo == "normal":
            return f"Normal estandar (Z={self.cuantil:.3f})"
        return "No disponible (se requiere mas de 1 replica)"

    def texto(self, dec: int = 1) -> str:
        """Formato cientifico 'media [inf - sup]' o un aviso si no hay IC."""
        if not self.disponible:
            return f"{self.media:.{dec}f}  (sin IC)"
        return f"{self.media:.{dec}f}  [{self.inf:.{dec}f} - {self.sup:.{dec}f}]"


def cuantil_ic95(n: int) -> Tuple[float, str, int]:
    """Devuelve (cuantil, metodo, grados_de_libertad) del IC 95% segun el tamanio n.

    Regla de muestreo: n>=30 -> Normal (Z); 2<=n<30 -> t-Student(gl=n-1); n<2 -> n/a.
    """
    if n < 2:
        return 0.0, "na", 0
    if n >= UMBRAL_MUESTRA_GRANDE:
        return Z_95, "normal", n - 1
    gl = n - 1
    # Para gl dentro de la tabla usamos t exacta; si faltara, caemos a la Normal.
    return T_STUDENT_95.get(gl, Z_95), "t", gl


def intervalo_confianza_95(valores: Sequence[float]) -> ICResult:
    """Calcula el IC del 95% de una muestra aplicando t-Student o Normal segun n.

    IC 95% = media +/- cuantil * (s / sqrt(n)), con s el desvio MUESTRAL (n-1) y el
    cuantil elegido por `cuantil_ic95`. Con n < 2 el intervalo no es estimable.
    """
    n = len(valores)
    media = statistics.fmean(valores) if n else 0.0
    cuantil, metodo, gl = cuantil_ic95(n)
    if metodo == "na":
        return ICResult(media, media, media, "na", 0.0, 0, n, 0.0, 0.0)
    s = statistics.stdev(valores)                 # Desvio muestral (denominador n-1).
    error_estandar = s / math.sqrt(n)
    margen = cuantil * error_estandar
    return ICResult(media, media - margen, media + margen, metodo, cuantil, gl, n,
                    s, error_estandar)


# =============================================================================
# VALIDACION Y VERIFICACION (V&V) DEL GENERADOR DE ARRIBOS
# =============================================================================
@dataclass(frozen=True)
class ValidacionArribos:
    """Contraste entre la media empirica de los interarribos y la media teorica."""
    media_teorica: float        # E(X) = ventana / comensales.
    media_empirica: float       # Promedio de los interarribos generados por NumPy.
    desvio_empirico: float      # Desvio de la muestra (para una Exp deberia ~= media).
    desvio_pct: float           # Desvio porcentual empirico vs teorico.
    n_muestras: int             # Cantidad de interarribos observados.
    unidad: str                 # Unidad de tiempo ("s" o "min").
    umbral_pct: float           # Tolerancia maxima aceptada para certificar el modelo.

    @property
    def validado(self) -> bool:
        """True si el desvio porcentual cae dentro de la tolerancia (modelo calibrado)."""
        return self.n_muestras >= 2 and abs(self.desvio_pct) <= self.umbral_pct

    @property
    def mensaje(self) -> str:
        """Veredicto formal de validacion para mostrar a la catedra."""
        if self.n_muestras < 2:
            return ("Muestra insuficiente: se necesitan al menos 2 arribos para validar "
                    "el generador.")
        if self.validado:
            return (f"GENERADOR VALIDADO: el tiempo medio entre arribos empirico difiere "
                    f"solo {abs(self.desvio_pct):.2f}% del valor teorico de la Exponencial "
                    f"(tolerancia {self.umbral_pct:.0f}%). Los generadores NumPy/SimPy "
                    f"reproducen fielmente el comportamiento del sistema real.")
        return (f"REVISAR: el desvio empirico ({abs(self.desvio_pct):.2f}%) supera la "
                f"tolerancia del {self.umbral_pct:.0f}%. Aumente la cantidad de replicas "
                f"o comensales para estabilizar la media muestral (Ley de los Grandes "
                f"Numeros).")


def validar_generador_arribos(muestras: Sequence[float], media_teorica: float,
                              unidad: str = "s",
                              umbral_pct: float = 5.0) -> ValidacionArribos:
    """Compara la media empirica de los interarribos contra la media teorica E(X).

    `muestras` son los tiempos entre arribos que el generador exponencial produjo a lo
    largo de TODAS las replicas; cuantos mas, mas estable es la media muestral.
    """
    n = len(muestras)
    media_emp = statistics.fmean(muestras) if n else 0.0
    desvio_emp = statistics.pstdev(muestras) if n > 1 else 0.0
    desvio_pct = (100.0 * (media_emp - media_teorica) / media_teorica
                  if media_teorica else 0.0)
    return ValidacionArribos(
        media_teorica=media_teorica, media_empirica=media_emp,
        desvio_empirico=desvio_emp, desvio_pct=desvio_pct, n_muestras=n,
        unidad=unidad, umbral_pct=umbral_pct)
