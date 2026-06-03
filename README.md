# Suite de Simulación de Eventos Discretos — Grupo 2 (v3.0)

Aplicación **web** (Streamlit) que unifica **dos modelos de simulación de eventos
discretos** (SimPy) en una interfaz multipestaña, bajo una arquitectura **modular**
(principios SOLID / Clean Code).

> **TPI Intercátedra e Intercarrera — Grupo 2**
> Universidad de la Cuenca del Plata (Sede Corrientes).
> Ingeniería en Sistemas de Información (4° nivel — Modelos y Simulación / Ing. de
> Software III; 3er nivel — Ing. de Software II) en articulación con la Licenciatura en
> Nutrición (2° nivel — Química de los Alimentos).
> Evento modelado: análisis sensorial de una tartaleta vegetal sustentable, Planta
> Piloto, jueves 11/06/2026 (≥ 50 jueces no entrenados).

---

## Las dos pestañas

### 🌐 Pestaña 1 — Infraestructura Web & Concurrencia
Estrés del **Connection Pooler de Supabase** (límite del plan gratuito = 60 conexiones)
frente a la ráfaga de comensales que envían la encuesta directo (client-to-cloud).

- **Panel paramétrico dinámico:** sliders de *comensales* `[10–150]`, *límite del pool*
  `[10–200]` y *latencia media de red* `[50–5000 ms]`. Los botones **Optimista /
  Esperado / Pesimista** son *presets* que reubican los sliders.
- **Rigor estadístico:** cada KPI se reporta como **`Promedio [IC 95%]`** calculado por
  la distribución Normal sobre las N réplicas (`media ± 1.96·s/√n`).
- **Doble gráfico:** curva temporal de conexiones ocupadas + **boxplot** de la
  dispersión de *Encuestas Perdidas* a lo largo de las réplicas.

#### Modelo del cuello de botella
Bajo Wi-Fi degradada, una fracción de las peticiones sufre **retransmisiones TCP** que
extienden exponencialmente la retención del socket: el cliente percibe el 504 al
cumplirse el *timeout* de gateway (8 s), pero el socket sigue ocupando un cupo del pooler
(conexión "colgada", proceso *zombie*) hasta agotar las retransmisiones. Conexiones
colgadas + reintentos se superponen y la curva de conexiones crece de forma dinámica.

### 🍳 Pestaña 2 — Cadena de Producción & Abastecimiento
Fabricación física de las tartaletas en la cocina de la Planta Piloto, cruzando la tasa
de producción contra el ritmo de consumo de los comensales.

- **Recursos:** *operarios* `[1–5]` y *capacidad del horno* `[1–4]` lotes simultáneos.
- **Flujo (3 etapas):** Etapa 1 Masa/Relleno `Normal(15, 2) min` (operario) → Etapa 2
  Horneado `20 min fijos` (horno) → Etapa 3 Ensamblado `Uniforme[3, 5] min` (operario).
  Cada lote rinde 6 tartaletas.
- **Acoplamiento intercátedra:** los comensales llegan con la **misma exponencial** que
  la Pestaña 1 y retiran 1 tartaleta del stock; si no hay, entran a la cola de espera por
  alimento hasta que un lote reponga el mostrador.
- **KPIs:** tartaletas producidas, tiempo medio de fabricación de un lote, espera máxima
  por alimento y stock remanente. **Gráfico** de evolución del stock con **zona roja**
  cuando cae a cero.

### 📄 Reporte PDF (Normas APA 7)
Botón en la barra lateral que compila un PDF formal (`reportlab`) con portada
institucional, Sección 1 (infraestructura + 2 gráficos + tabla de KPIs con IC 95%),
Sección 2 (producción + gráfico de stock) y un bloque de diagnósticos y recomendaciones.
Se descarga con `st.download_button`.

---

## Arquitectura modular

```
main.py                      Punto de entrada Streamlit (config global + pestañas).
views/
  theme.py                   Paleta verde/naranja y componentes de UI (tarjetas KPI).
  tab_server.py              Vista de la Pestaña 1 (sliders, KPIs con IC, doble gráfico).
  tab_production.py          Vista de la Pestaña 2 (sliders, KPIs de stock, gráfico).
sim/
  server_sim.py              Motor matemático puro: pooler Supabase + Wi-Fi inestable.
  production_sim.py          Motor matemático puro: cadena de producción + consumo.
utils/
  charts.py                  Primitivas matplotlib (compartidas por vistas y PDF).
  pdf_generator.py           Compilación del reporte APA y descarga.
.streamlit/config.toml       Tema premium de la app.
```

El **motor matemático** (`sim/`) es independiente del motor de renderizado: las
distribuciones, la lógica de retransmisión TCP/Wi-Fi, el cálculo de IC 95% y los
diagnósticos no dependen de Streamlit y se pueden ejecutar/testear de forma aislada.

---

## Requisitos y uso

- Python 3.11+

```bash
pip install -r requirements.txt

# Lanzar la aplicación web
streamlit run main.py
```

La app abre en `http://localhost:8501`.

---

## Definición formal del sistema (Pestaña 1)

| Elemento | Descripción |
|---|---|
| **Entidades** | Comensales virtuales (jueces no entrenados) que usan la web. |
| **Recursos** | Canales del Connection Pooler de Supabase (`simpy.Resource`, capacidad parametrizable, 60 por defecto). |
| **Variables de estado** | Conexiones HTTP activas, tamaño de la cola, peticiones caídas. |
| **Eventos** | Arribo · inicio de llenado · click en enviar (petición) · persistencia en BD. |

### Distribuciones estadísticas
- **Arribos:** Exponencial.
- **Tiempo de llenado:** Uniforme(45, 90) s (justificado por las 24 preguntas reales).
- **Respuesta cloud / retención:** Normal(media, desvío) por escenario
  (Esperado = Normal(0,25 s; 0,05 s)) + cola pesada Exponencial bajo Wi-Fi degradada.

---

## Equipo (Grupo 2)

- **ISI 4°:** Ignacio Rosales (PM / Scrum Master) · Juan Ignacio Gualtieri (QA Manager / Simulación)
- **ISI 3°:** Desarrollo del sistema web (HTML/JS + Supabase, deploy en Vercel)
- **Lic. en Nutrición:** Diseño del producto y de las pruebas de análisis sensorial
