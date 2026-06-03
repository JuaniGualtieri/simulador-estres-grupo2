# Simulador de Estrés — Connection Pooler de Supabase

Simulador de **eventos discretos** (SimPy) que modela el comportamiento del sistema web
de análisis sensorial frente a ráfagas de comensales concurrentes, para **predecir
errores de timeout (HTTP 504)** sobre el *Connection Pooler* de Supabase causados por la
red Wi-Fi inestable de la Planta Piloto.

> **TPI Intercátedra e Intercarrera — Grupo 2**
> Ingeniería en Sistemas de Información (4° año) · Modelos y Simulación ·
> Ingeniería de Software III · Tecnología, Ciencia y Responsabilidad Social.
> En articulación con la Licenciatura en Nutrición.
> Evento modelado: análisis sensorial de una tartaleta vegetal sustentable, Planta
> Piloto, jueves 11/06/2026 (≥ 50 jueces no entrenados).

---

## ¿Qué hace?

- Modela el sistema real: una web estática (HTML/JS en Vercel) que escribe **directo**
  (client-to-cloud) a PostgreSQL en Supabase a través de su Connection Pooler
  (**límite del plan gratuito = 60 conexiones concurrentes**).
- Simula **3 escenarios**: Optimista, Esperado y Pesimista.
- Corre **múltiples réplicas** (experimentos independientes) para promediar KPIs.
- Interfaz gráfica **premium** (customtkinter) con gráfico de matplotlib embebido.
- **Exporta un reporte PDF** (estilo Normas APA 7°) con portada, parámetros, KPIs,
  diagnóstico y la curva de conexiones como anexo.

### Modelo del cuello de botella

Bajo Wi-Fi degradada, una fracción de las peticiones sufre **retransmisiones TCP** que
extienden exponencialmente la retención de la conexión HTTP: el cliente percibe el 504
al cumplirse el *timeout* de gateway (8 s), pero el socket sigue ocupando un cupo del
pooler (conexión "colgada") hasta agotar las retransmisiones. Conexiones colgadas +
reintentos se superponen y la curva de conexiones ocupadas crece de forma dinámica.

---

## Requisitos

- Python 3.11+
- Dependencias (ver `requirements.txt`):

```bash
pip install -r requirements.txt
```

## Uso

```bash
# Interfaz gráfica (recomendado)
python simulador_estres_grupo2.py

# Validación por consola (3 escenarios)
python simulador_estres_grupo2.py --cli --replicas 30

# Generar el PDF de un escenario sin abrir la GUI
python simulador_estres_grupo2.py --test-pdf Pesimista
```

---

## Definición formal del sistema

| Elemento | Descripción |
|---|---|
| **Entidades** | Comensales virtuales (jueces no entrenados) que usan la web. |
| **Recursos** | Canales del Connection Pooler de Supabase (`simpy.Resource`, capacidad 60). |
| **Variables de estado** | Conexiones HTTP activas, tamaño de la cola, peticiones caídas. |
| **Eventos** | Arribo · inicio de llenado · click en enviar (petición) · persistencia en BD. |

### Distribuciones estadísticas

- **Arribos:** Exponencial.
- **Tiempo de llenado:** Uniforme(45, 90) s (justificado por las 24 preguntas de la encuesta real).
- **Respuesta cloud / retención:** Normal(media, desvío) por escenario (Esperado = Normal(0,25 s; 0,05 s)).

---

## Equipo (Grupo 2)

- **ISI 4°:** Ignacio Rosales (PM / Scrum Master) · Juan Ignacio Gualtieri (QA Manager / Simulación)
- **ISI 3°:** Desarrollo del sistema web (HTML/JS + Supabase, deploy en Vercel)
- **Lic. en Nutrición:** Diseño del producto y de las pruebas de análisis sensorial
