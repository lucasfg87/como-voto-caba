"""Scraper de votaciones nominales de la Legislatura de la Ciudad de Buenos Aires.

Usa el web service público que alimenta https://www.legislatura.gob.ar/InfoSesion/
(parlamentaria.legislatura.gob.ar/webservices/Json.asmx, responde XML).

Guarda:
  data/sesiones/<id_sesion>.json   votaciones nominales de cada sesión
  data/expedientes.json            sumario y tipo de cada expediente votado
  data/legisladores.json           datos y foto de cada legislador
  docs/fotos/<id_legislador>.jpg   fotos

Uso:
  python scraper.py                 actualiza (re-baja las sesiones de los últimos 90 días)
  python scraper.py --todo          re-baja todas las sesiones
  python scraper.py --sin-fotos
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import random
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SESIONES_DIR = DATA_DIR / "sesiones"
FOTOS_DIR = BASE_DIR / "docs" / "fotos"

WS = "https://parlamentaria.legislatura.gob.ar/webservices/Json.asmx/"
NS = "{http://tempuri.org/}"
FECHA_INICIO = "01/01/2016"  # antes de agosto 2016 la API no tiene votos nominales
REQUEST_DELAY = float(os.environ.get("COMO_VOTO_DELAY", "0.3"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("scraper")

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "ComoVotoCABA-Scraper/0.1 (proyecto educativo; basado en github.com/rquiroga7/como_voto)",
        "Accept-Language": "es-AR,es;q=0.9",
    }
)


# ---------------------------------------------------------------------------
# Web service
# ---------------------------------------------------------------------------

def _record(elem: ET.Element) -> dict:
    return {child.tag.replace(NS, ""): (child.text or "").strip() for child in elem}


def call(op: str, retries: int = 3, **params) -> list[dict]:
    """Llama una operación del web service y devuelve sus registros como dicts."""
    for attempt in range(retries):
        time.sleep(REQUEST_DELAY + random.uniform(0, REQUEST_DELAY * 0.25))
        try:
            resp = SESSION.post(WS + op, data=params, timeout=60)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            break
        except (requests.RequestException, ET.ParseError) as exc:
            log.warning(f"{op} {params} falló ({exc}); intento {attempt + 1}/{retries}")
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"No se pudo consultar {op} {params}")

    # Algunas operaciones envuelven el listado en <status>/<Listado>
    listado = root.find(f"{NS}Listado")
    container = listado if listado is not None else root
    return [_record(child) for child in container if child.tag != f"{NS}status"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)


def to_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_fecha(value: str) -> str:
    """'27/6/2019 00:00:00' o '2019-06-27' -> '2019-06-27'."""
    value = value.split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value


# ---------------------------------------------------------------------------
# Sesiones y votaciones
# ---------------------------------------------------------------------------

def fetch_sesiones() -> list[dict]:
    hasta = date.today().strftime("%d/%m/%Y")
    rows = call("GetSesionesAvanzado", FechaDesde=FECHA_INICIO, FechaHasta=hasta)
    sesiones = []
    for row in rows:
        sid = to_int(row.get("id_sesion_lp"))
        if sid is None:
            continue
        sesiones.append(
            {
                "id": sid,
                "fecha": parse_fecha(row.get("fch_sesion_lp", "")),
                "numero": row.get("nro_orden_lp", ""),
                "anio_parlamentario": row.get("ano_parlamentario", ""),
                "tipo": row.get("dsc_sesion_tipo", ""),
            }
        )
    sesiones.sort(key=lambda s: (s["fecha"], s["id"]))
    return sesiones


def scrape_sesion(sesion: dict) -> dict:
    asuntos = call("GetVotacionesAsuntos", IdExpediente="0", IdSesion=str(sesion["id"]))
    votaciones = []
    for asunto in asuntos:
        vid = to_int(asunto.get("id_votacion"))
        if vid is None or asunto.get("publicada", "true").lower() == "false":
            continue
        rows = call(
            "GetVotaciones",
            IdVotacionAsunto=str(vid),
            IdExpediente="",
            IdSesion="",
            IdLegislador="",
        )
        votos = [
            {
                "id_legislador": to_int(r.get("id_legislador")),
                "apellido": r.get("legislador_apellido", ""),
                "nombre": r.get("legislador_nombre", ""),
                "id_bloque": to_int(r.get("id_bloque")),
                "bloque": r.get("bloque_nombre", ""),
                "voto": r.get("votacion_tipo_descripcion", ""),
                "presente": r.get("presente_descripcion", ""),
            }
            for r in rows
            if r.get("id_legislador")
        ]
        extra = rows[0] if rows else {}
        votaciones.append(
            {
                "id": vid,
                "asunto": asunto.get("asunto", ""),
                "descripcion": asunto.get("descripcion", ""),
                "id_expediente": to_int(asunto.get("id_expediente_despacho"))
                or to_int(asunto.get("id_expediente")),
                "id_despacho": to_int(asunto.get("id_despacho")),
                "positivos": to_int(asunto.get("positivos")) or 0,
                "negativos": to_int(asunto.get("negativos")) or 0,
                "abstenciones": to_int(asunto.get("abstenciones")) or 0,
                "desc_sesion": extra.get("desc_sesion", ""),
                "votos": votos,
            }
        )
    return {**sesion, "votaciones": votaciones}


def update_sesiones(todo: bool, refresh_days: int) -> list[dict]:
    sesiones = fetch_sesiones()
    log.info(f"{len(sesiones)} sesiones desde {FECHA_INICIO}")
    limite = (date.today() - timedelta(days=refresh_days)).isoformat()
    nuevas = 0
    for sesion in sesiones:
        path = SESIONES_DIR / f"{sesion['id']}.json"
        if path.exists() and not todo and sesion["fecha"] < limite:
            continue
        data = scrape_sesion(sesion)
        save_json(path, data)
        nuevas += 1
        log.info(f"Sesión {sesion['id']} ({sesion['fecha']}): {len(data['votaciones'])} votaciones nominales")
    log.info(f"{nuevas} sesiones descargadas/actualizadas")
    return sesiones


# ---------------------------------------------------------------------------
# Expedientes
# ---------------------------------------------------------------------------

def iter_sesiones_guardadas():
    for path in sorted(SESIONES_DIR.glob("*.json")):
        yield load_json(path, {})


def update_expedientes() -> None:
    path = DATA_DIR / "expedientes.json"
    expedientes: dict = load_json(path, {})
    ids = {
        str(v["id_expediente"])
        for s in iter_sesiones_guardadas()
        for v in s.get("votaciones", [])
        if v.get("id_expediente")
    }
    faltan = sorted(ids - set(expedientes))
    log.info(f"Expedientes: {len(expedientes)} en caché, {len(faltan)} por bajar")
    for i, eid in enumerate(faltan, 1):
        rows = call(
            "GetExpedienteDatosBasicos",
            IdExpediente=eid,
            NumeroOrden="",
            AnoParlamentario="",
            IdExpedientes="",
        )
        if rows:
            r = rows[0]
            expedientes[eid] = {
                "nro": r.get("nro_de_expediente", ""),
                "sumario": r.get("sumario", ""),
                "tipo": r.get("proyecto_tipo_des", ""),
                "origen": r.get("proyecto_origen_tipo_des", ""),
                "autor": r.get("autor_des", "").strip(" ,"),
                "doc": r.get("urlDoc", ""),
            }
        else:
            expedientes[eid] = {}
        if i % 100 == 0:
            save_json(path, expedientes)
            log.info(f"  {i}/{len(faltan)} expedientes")
    save_json(path, expedientes)


# ---------------------------------------------------------------------------
# Legisladores y fotos
# ---------------------------------------------------------------------------

FOTO_PX = 240  # la Legislatura sirve originales de ~2000px y varios MB


def achicar_foto(data: bytes) -> bytes:
    """Recorta al cuadrado (priorizando la parte superior, donde está la cara) y achica."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    lado = min(img.size)
    left = (img.width - lado) // 2
    top = min((img.height - lado) // 4, img.height - lado)
    img = img.crop((left, top, left + lado, top + lado)).resize((FOTO_PX, FOTO_PX), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=82, optimize=True)
    return out.getvalue()


def download_photo(url: str, dest: Path) -> bool:
    if dest.exists() and 500 < dest.stat().st_size < 200_000:
        return True
    try:
        time.sleep(0.15)
        resp = SESSION.get(url, timeout=60)
        if resp.status_code == 200 and len(resp.content) > 500:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(achicar_foto(resp.content))
            return True
    except (requests.RequestException, OSError) as exc:
        log.warning(f"Foto {url}: {exc}")
    return False


def update_legisladores(fotos: bool) -> None:
    path = DATA_DIR / "legisladores.json"
    legisladores: dict = load_json(path, {})
    ids = {
        str(voto["id_legislador"])
        for s in iter_sesiones_guardadas()
        for v in s.get("votaciones", [])
        for voto in v.get("votos", [])
        if voto.get("id_legislador")
    }
    faltan = sorted(ids - set(legisladores))
    log.info(f"Legisladores: {len(legisladores)} en caché, {len(faltan)} por bajar")
    for lid in faltan:
        rows = call("GetDiputadoDatos", id_legislador=lid)
        r = rows[0] if rows else {}
        legisladores[lid] = {
            "apellido": r.get("apellido", ""),
            "nombre": r.get("nombre", ""),
            "sexo": r.get("sexo", ""),
            "url": r.get("url_legislador", ""),
            "inicio_mandato": r.get("fecha_inicio_mandato", ""),
            "fin_mandato": r.get("fecha_fin_mandato", ""),
            "foto_url": r.get("fotoM") or r.get("foto", ""),
        }
    save_json(path, legisladores)

    if fotos:
        ok = 0
        for lid, leg in legisladores.items():
            if leg.get("foto_url") and download_photo(leg["foto_url"], FOTOS_DIR / f"{lid}.jpg"):
                ok += 1
        log.info(f"Fotos: {ok}/{len(legisladores)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--todo", action="store_true", help="re-bajar todas las sesiones")
    parser.add_argument("--refresh-dias", type=int, default=90, help="re-bajar sesiones de los últimos N días")
    parser.add_argument("--sin-fotos", action="store_true")
    args = parser.parse_args()

    update_sesiones(args.todo, args.refresh_dias)
    update_expedientes()
    update_legisladores(fotos=not args.sin_fotos)


if __name__ == "__main__":
    main()
