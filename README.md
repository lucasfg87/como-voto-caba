# ¿Cómo votó? · Legislatura porteña

Cómo votan los legisladores y legisladoras de la Ciudad Autónoma de Buenos Aires: historial de
votaciones nominales, presentismo y afinidad con las principales coaliciones.

Adaptación para la Legislatura de CABA de [¿Cómo Votó?](https://comovoto.dev.ar) de Rodrigo Quiroga
([rquiroga7/como_voto](https://github.com/rquiroga7/como_voto), licencia MIT).

## Fuente de datos

La Legislatura publica las votaciones nominales en
[Información de Sesiones](https://www.legislatura.gob.ar/InfoSesion/). Esa página consume un web service
público (`https://parlamentaria.legislatura.gob.ar/webservices/Json.asmx/`, responde XML):

| Operación | Uso |
|---|---|
| `GetSesionesAvanzado(FechaDesde, FechaHasta)` | listado de sesiones |
| `GetVotacionesAsuntos(IdSesion, IdExpediente=0)` | votaciones nominales de una sesión |
| `GetVotaciones(IdVotacionAsunto)` | voto de cada legislador (bloque, voto, presencia) |
| `GetExpedienteDatosBasicos(IdExpediente)` | sumario y tipo del expediente votado |
| `GetDiputadoDatos(id_legislador)` | datos y foto del legislador |

Hay votos nominales desde agosto de 2016.

## Estructura

```
scraper.py              baja sesiones, votaciones, expedientes, legisladores y fotos
generate_site.py        calcula métricas y genera docs/data/*.json
data/
  coaliciones.json      bloques → coaliciones (editable a mano)
  sesiones/<id>.json    votaciones crudas por sesión
  expedientes.json      caché de expedientes
  legisladores.json     caché de legisladores
docs/                   sitio estático (GitHub Pages)
  index.html, app.js, style.css
  data/                 JSON generados
  fotos/                fotos de legisladores
.github/workflows/update-data.yml   actualización diaria automática
```

## Uso local

```bash
pip install -r requirements.txt
python scraper.py            # primera vez tarda ~30 min; después solo baja lo nuevo
python generate_site.py
python -m http.server 8000 -d docs
```

y abrir http://localhost:8000.

## Coaliciones

`data/coaliciones.json` define las coaliciones, qué bloque pertenece a cuál (se puede indicar un cambio
de coalición desde una fecha) y cuáles se usan para definir una votación "dividida".
`generate_site.py` lista los bloques que no matchean ninguna regla.

## Publicación

1. Subir el repo a GitHub.
2. Settings → Pages → Deploy from branch → `main` / `docs`.
3. La Action `update-data.yml` corre todos los días y commitea los datos nuevos.
