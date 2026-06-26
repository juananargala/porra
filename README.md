# Porra WRC + F1

Gestión semiautomática de la porra de pronósticos (podio 1º-2º-3º) de WRC y F1 entre un grupo de amigos por WhatsApp.

Filosofía del proyecto: **simplicidad por encima de todo**. Ficheros JSON estáticos en vez de fuentes de datos dinámicas, librería estándar de Python en vez de dependencias de terceros, y un único paso manual al final (enviar el mensaje por WhatsApp) en vez de perseguir una automatización imposible por las limitaciones propias de esa app.

---

## Cómo funciona, de un vistazo

```
   LUNES                    MIÉRCOLES 21:30
┌──────────────┐         ┌────────────────────┐
│ GitHub Action│         │ Automatización iOS  │
│ check_porra. │  ───►   │ comprueba week.json │
│ py genera    │  week   │ si hay carrera,     │
│ week.json    │  .json  │ lanza Shortcut PORRA│
│ + notifica   │         └─────────┬──────────┘
└──────────────┘                   │
                                    ▼
                         ┌─────────────────────┐
                         │ Shortcut PORRA:      │
                         │ pide podio por       │
                         │ carrera, crea alarmas│
                         │ 21:55 / 21:58,       │
                         │ abre "Compartir"      │
                         └─────────┬───────────┘
                                    │
                                    ▼
                          Tú: tocas WhatsApp,
                          eliges el grupo, envías
```

---

## Estructura del repositorio

```
porra/
├── .github/workflows/
│   └── check-porra.yml        # Workflow semanal (cron + workflow_dispatch)
├── scripts/
│   ├── check_porra.py         # Script semanal: lee datos estáticos, genera week.json, notifica
│   └── setup_season.py        # Script de SETUP: se ejecuta a mano una vez por temporada
└── data/
    ├── calendar.json          # Calendario de la temporada (WRC + F1)
    ├── drivers_wrc.json       # Pilotos Rally1 vigentes
    ├── drivers_f1.json        # Pilotos F1 vigentes
    └── week.json              # Generado automáticamente cada lunes (no editar a mano)
```

---

## Los ficheros de datos

### `data/calendar.json`

```json
{
  "wrc": [
    {"round": 1, "name": "Rallye Monte-Carlo", "country": "Monaco", "flag": "🇲🇨", "start": "2026-01-22", "end": "2026-01-25"}
  ],
  "f1": [
    {"round": 1, "name": "Australian Grand Prix", "country": "Australia", "flag": "🇦🇺", "start": "2026-03-06", "end": "2026-03-08", "sprint": false}
  ]
}
```

- `start` / `end`: rango de fechas del evento (el domingo de carrera debe caer dentro de ese rango)
- `sprint`: solo en F1, indica si ese fin de semana tiene formato sprint (informativo, no afecta a la lógica)

### `data/drivers_wrc.json` y `data/drivers_f1.json`

```json
[
  {"code": "EVA", "name": "Elfyn Evans", "team": "Toyota Gazoo Racing WRT", "country": "United Kingdom"}
]
```

- `code`: código de 3 letras, es lo que se usa en el podio y en los mensajes de WhatsApp (más compacto que el nombre completo)
- Incluye **todos** los pilotos con presencia habitual, aunque alguno tenga programa parcial — el Shortcut no distingue esto, simplemente te deja elegir entre todos

### `data/week.json` (generado, no tocar a mano)

Lo escribe `check_porra.py` cada lunes. Contiene las carreras de esa semana con sus pilotos disponibles. El Shortcut PORRA lo lee desde:
```
https://raw.githubusercontent.com/juananargala/porra/main/data/week.json
```

---

## Scripts

### `scripts/check_porra.py` — ejecución semanal automática

- Se ejecuta vía GitHub Actions, sin dependencias externas (solo librería estándar, `urllib` en vez de `requests`)
- Calcula el domingo siguiente y comprueba qué carreras de `calendar.json` caen esa semana
- Genera `data/week.json` y notifica por **ntfy.sh** si hay alguna carrera
- **Guarda anti-duplicados**: el workflow dispara dos cron en UTC (para cubrir CET/CEST sin tocar el workflow dos veces al año), pero el script solo actúa si la hora local de Madrid es la correcta — el cron "equivocado" para la estación actual no hace nada
- **Modo de prueba**: con la variable de entorno `FORCE_RUN=true` (o el input `force` del `workflow_dispatch`), se salta esa guarda — útil para lanzar el workflow manualmente sin esperar al lunes

### `scripts/setup_season.py` — ejecución manual, una vez por temporada

- **Sí** usa red (a diferencia de `check_porra.py`): llama a la API de **Jolpica** para F1, y hace scraping best-effort de `wrc.com` para WRC
- El scraping de WRC es deliberadamente frágil: la web puede cambiar de estructura de un año a otro, así que si no encuentra nada, avisa por consola en vez de fallar en silencio o inventar datos
- **Nunca sobrescribe** los ficheros que usa el bot semanal. Genera versiones paralelas para revisión:
  ```
  data/calendar_nueva_temporada.json
  data/drivers_wrc_nueva_temporada.json
  data/drivers_f1_nueva_temporada.json
  ```
- Tras revisar y corregir a mano esos ficheros, se renombran (quitando el sufijo `_nueva_temporada`) para sustituir a los originales

Uso:
```bash
python3 scripts/setup_season.py --year 2027
```

Flags opcionales: `--skip-f1`, `--skip-wrc` (para repetir solo la parte que falló o que quieras regenerar).

---

## GitHub Actions (`.github/workflows/check-porra.yml`)

- **Triggers**: dos `cron` semanales en UTC (19:30 y 20:30, para cubrir CET/CEST) + `workflow_dispatch` manual con input `force`
- **Permisos**: `contents: write`, necesario para el commit automático de `data/week.json`
- **Secret necesario**: `NTFY_TOPIC` (en `Settings → Secrets and variables → Actions`) — el nombre del topic de ntfy.sh al que está suscrito el iPhone

### Lanzar manualmente para pruebas
1. Pestaña **Actions** → workflow **"Check porra semanal"** → **Run workflow**
2. Marca el checkbox `force`
3. Run workflow

---

## Notificaciones (ntfy.sh)

- App **ntfy** instalada en el iPhone, suscrita al topic configurado en el secret `NTFY_TOPIC`
- El topic debe ser único e impredecible (ntfy.sh es público) — nada de nombres genéricos tipo `test` o `porra`
- Probar manualmente:
  ```bash
  curl -d "prueba" https://ntfy.sh/<NOMBRE_DEL_TOPIC>
  ```

---

## Shortcut de iOS — "PORRA"

Lee `week.json`, y por cada carrera de la semana:
1. Pide elegir 1º, 2º y 3º clasificado (con `Filtrar artículos` para no repetir piloto entre posiciones)
2. Construye una línea de texto con bandera, categoría, nombre de carrera y podio elegido
3. Acumula todas las carreras de la semana en un único mensaje, separadas por línea en blanco (usando `Combinar texto` con separador personalizado — `Añadir a variable` por sí solo no respeta saltos de línea extra dentro de cada elemento)
4. Calcula el miércoles de esa semana (domingo de carrera − 4 días) y crea dos alarmas, **21:55** y **21:58**
5. Muestra el mensaje final y abre la hoja de **Compartir** de iOS

### Automatización del miércoles 21:30
- Lee `week.json` directamente del repo (no depende del calendario ICS del iPhone)
- Si hay alguna carrera esa semana: crea una alarma a las 21:50 como aviso previo, reproduce un sonido, y ejecuta el Shortcut **PORRA**
- Si no hay carrera: no hace nada

### El único paso manual
WhatsApp no permite preseleccionar un grupo ni enviar un mensaje automáticamente desde fuera de la app (ni con `URL scheme`, ni con enlaces de invitación a grupo, que solo sirven para unirse). Por eso el flujo termina con la hoja de **Compartir**: tocas WhatsApp, eliges el grupo, envías. Es el único toque manual de todo el proceso.

---

## Actualización de temporada

Al empezar una temporada nueva (calendario y/o pilotos cambiados):

1. Ejecutar `scripts/setup_season.py --year YYYY`
2. Revisar y corregir a mano los 3 ficheros `*_nueva_temporada.json` generados en `data/`
3. Renombrarlos para sustituir a `calendar.json`, `drivers_wrc.json` y `drivers_f1.json`
4. Hacer commit y push a `main`
5. Lanzar el workflow manualmente (`force=true`) para confirmar que `check_porra.py` lee bien los datos nuevos

---

## Notas y decisiones de diseño

- **Por qué JSON estático en vez de APIs en tiempo real**: menos puntos de fallo (web de WRC caída, API de Jolpica caída, límites de rate, cambios de formato) a cambio de tener que actualizar manualmente una vez por temporada — compromiso aceptado conscientemente
- **Por qué `urllib` en vez de `requests`** en `check_porra.py`: cero dependencias que instalar en el workflow, ejecución más rápida y sin posibilidad de que una versión de `requests` rompa algo
- **Por qué el repo es público**: el Shortcut de iOS necesita leer `week.json` vía `raw.githubusercontent.com` sin autenticación; los datos (calendario, nombres de pilotos) no son sensibles
