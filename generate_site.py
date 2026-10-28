"""Genera los JSON que consume el sitio (docs/data) a partir de data/.

Métricas (misma idea que comovoto.dev.ar):
  - Mayoría de coalición: voto más frecuente (afirmativo/negativo/abstención)
    entre los legisladores de esa coalición en una votación.
  - Votación dividida: las mayorías de las coaliciones listadas en
    "disputa" (data/coaliciones.json) no coinciden.
  - Afinidad con X: % de votaciones divididas en las que el legislador votó
    igual que la mayoría de X (solo cuando votó).
  - Coincidencia general con X: lo mismo pero sobre todas las votaciones
    (incluye las casi unánimes, por eso suele ser alta).
  - Presentismo: % de votaciones nominales en las que emitió voto.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "docs" / "data"
FOTOS_DIR = BASE_DIR / "docs" / "fotos"

VOTO_CODIGO = {"AFIRMATIVO": "A", "NEGATIVO": "N", "ABSTENCIÓN": "B", "ABSTENCION": "B"}
EMITIDOS = ("A", "N", "B")
TIPOS = {"RESOLUCION": "Resolución", "DECLARACION": "Declaración", "LEY": "Ley", "DECRETO": "Decreto"}

# Palabras que, en minúscula, convierten un sumario en mayúscula sostenida a
# algo legible sin perder siglas comunes.
SIGLAS = {"caba", "gcba", "ccaba", "ley", "pba", "afip", "arba", "agip", "ysrl", "sbase", "ausa", "iva", "ii", "iii", "iv"}


def load_json(path: Path, default=None):
    if path.exists():
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))


def codigo_voto(voto: str) -> str:
    return VOTO_CODIGO.get(voto.strip().upper(), "X")  # X = no votó / ausente


def titulo_legible(texto: str) -> str:
    texto = " ".join(texto.split())
    if not texto or not texto.isupper():
        return texto
    palabras = []
    for i, palabra in enumerate(texto.lower().split(" ")):
        limpia = palabra.strip(".,;:()\"'")
        if limpia in SIGLAS and limpia != "ley":
            palabra = palabra.upper()
        elif i == 0:
            palabra = palabra[:1].upper() + palabra[1:]
        palabras.append(palabra)
    return " ".join(palabras)


def nombre_legible(apellido: str, nombre: str) -> str:
    def cap(s: str) -> str:
        return " ".join(p[:1].upper() + p[1:].lower() for p in s.split())

    return f"{cap(nombre)} {cap(apellido)}".strip()


class Clasificador:
    """Asigna coalición a cada bloque según data/coaliciones.json."""

    def __init__(self, config: dict):
        self.bloques = config.get("bloques", {})
        # Las reglas matchean desde el inicio de una palabra ("peronis" -> "peronista")
        self.reglas = [(re.compile(r"\b" + re.escape(k.lower())), c) for k, c in config.get("reglas", [])]
        self.sin_clasificar: Counter = Counter()

    def __call__(self, bloque: str, fecha: str) -> str:
        valor = self.bloques.get(bloque)
        if isinstance(valor, str):
            return valor
        if isinstance(valor, list):
            # [["desde AAAA-MM-DD", "COALICION"], ...] ordenado por fecha
            elegido = "OTROS"
            for desde, coal in valor:
                if fecha >= desde:
                    elegido = coal
            return elegido
        low = bloque.lower()
        for clave, coal in self.reglas:
            if clave.search(low):
                return coal
        self.sin_clasificar[bloque] += 1
        return "OTROS"


def mayoria(votos: list[tuple[str, str]], coalicion: str) -> str | None:
    """Voto mayoritario de una coalición; None si no votó nadie o hay empate."""
    cuenta = Counter(v for coal, v in votos if coal == coalicion and v in EMITIDOS)
    if not cuenta:
        return None
    top = cuenta.most_common(2)
    if len(top) > 1 and top[0][1] == top[1][1]:
        return None
    return top[0][0]


def main() -> None:
    config = load_json(DATA_DIR / "coaliciones.json")
    if not config:
        sys.exit("Falta data/coaliciones.json")
    clasificar = Clasificador(config)
    afinidad = config["afinidad"]
    disputa = config["disputa"]
    excluir = [p.lower() for p in config.get("excluir_asuntos", [])]

    expedientes = load_json(DATA_DIR / "expedientes.json", {})
    datos_leg = load_json(DATA_DIR / "legisladores.json", {})
    sesiones = [load_json(p) for p in sorted((DATA_DIR / "sesiones").glob("*.json"))]
    sesiones.sort(key=lambda s: (s["fecha"], s["id"]))

    bloques: list[dict] = []
    bloque_idx: dict[str, int] = {}
    votaciones_out = []
    votos_por_anio: dict[str, dict] = defaultdict(dict)
    legs: dict[int, dict] = {}
    nombres: dict[int, str] = {}

    for sesion in sesiones:
        fecha = sesion["fecha"]
        anio = fecha[:4]
        for vot in sesion.get("votaciones", []):
            if not vot.get("votos"):
                continue
            exp = expedientes.get(str(vot.get("id_expediente")), {}) or {}
            asunto = vot.get("asunto", "")
            titulo = titulo_legible(exp.get("sumario", "")) or asunto
            procedimental = any(p in (asunto + " " + titulo).lower() for p in excluir)

            filas = []
            for v in vot["votos"]:
                bloque = v["bloque"] or "Sin bloque"
                coal = clasificar(bloque, fecha)
                if bloque not in bloque_idx:
                    bloque_idx[bloque] = len(bloques)
                    bloques.append({"n": bloque, "c": coal})
                filas.append((v["id_legislador"], codigo_voto(v["voto"]), bloque, coal))
                nombres[v["id_legislador"]] = nombre_legible(v["apellido"], v["nombre"])

            pares = [(coal, cod) for _, cod, _, coal in filas]
            mayorias = {c: mayoria(pares, c) for c in afinidad}
            en_disputa = {mayoria(pares, c) for c in disputa} - {None}
            dividida = len(en_disputa) > 1 and not procedimental

            cuenta = Counter(cod for _, cod, _, _ in filas)
            vid = vot["id"]
            votaciones_out.append(
                {
                    "id": vid,
                    "s": sesion["id"],
                    "d": fecha,
                    "t": titulo[:300],
                    "as": asunto,
                    "tp": TIPOS.get(exp.get("tipo", "").upper(), exp.get("tipo", "").capitalize()),
                    "ex": exp.get("nro", ""),
                    "doc": exp.get("doc", ""),
                    "r": [cuenta["A"], cuenta["N"], cuenta["B"], cuenta["X"]],
                    "m": {c: m for c, m in mayorias.items() if m},
                    "dv": 1 if dividida else 0,
                }
            )
            votos_por_anio[anio][vid] = [[lid, cod, bloque_idx[b]] for lid, cod, b, _ in filas]

            for lid, cod, bloque, coal in filas:
                leg = legs.setdefault(
                    lid,
                    {
                        "votos": [],
                        "anual": defaultdict(Counter),
                        "al": defaultdict(lambda: [0, 0]),
                        "co": defaultdict(lambda: [0, 0]),  # coincidencia en todas las votaciones
                        "al_anual": defaultdict(lambda: defaultdict(lambda: [0, 0])),
                        "bloques": [],
                        "nombre": "",
                    },
                )
                leg["nombre"] = nombres[lid]
                leg["votos"].append([vid, cod])
                leg["anual"][anio][cod] += 1
                if not leg["bloques"] or leg["bloques"][-1]["b"] != bloque:
                    leg["bloques"].append({"b": bloque, "c": coal, "desde": fecha, "hasta": fecha})
                else:
                    leg["bloques"][-1]["hasta"] = fecha
                if cod in EMITIDOS:
                    for c, m in mayorias.items():
                        if m:
                            leg["co"][c][1] += 1
                            leg["co"][c][0] += cod == m
                if dividida and cod in EMITIDOS:
                    for c, m in mayorias.items():
                        if m:
                            leg["al"][c][1] += 1
                            leg["al_anual"][anio][c][1] += 1
                            if cod == m:
                                leg["al"][c][0] += 1
                                leg["al_anual"][anio][c][0] += 1

    if not votaciones_out:
        sys.exit("No hay votaciones en data/sesiones. Corré primero: python scraper.py")

    ultima_fecha = votaciones_out[-1]["d"]
    hoy = date.today().isoformat()

    # Salida -----------------------------------------------------------------
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    legisladores_out = []
    for lid, leg in legs.items():
        info = datos_leg.get(str(lid), {}) or {}
        nombre = nombre_legible(info["apellido"], info["nombre"]) if info.get("apellido") else leg["nombre"]
        total = len(leg["votos"])
        emitidos = sum(1 for _, c in leg["votos"] if c in EMITIDOS)
        actual = leg["bloques"][-1]
        fin = info.get("fin_mandato", "")
        # Cada votación lista a todos los integrantes del cuerpo (votaran o no)
        en_ejercicio = actual["hasta"] == ultima_fecha
        resumen = {
            "id": lid,
            "n": nombre,
            "f": 1 if (FOTOS_DIR / f"{lid}.jpg").exists() else 0,
            "b": actual["b"],
            "c": actual["c"],
            "y0": leg["bloques"][0]["desde"][:4],
            "y1": actual["hasta"][:4],
            "act": 1 if en_ejercicio else 0,
            "tv": total,
            "pr": round(100 * emitidos / total, 1) if total else 0,
            "al": {c: v for c, v in leg["al"].items()},
            "co": {c: v for c, v in leg["co"].items()},
        }
        legisladores_out.append(resumen)
        write_json(
            OUT_DIR / "leg" / f"{lid}.json",
            {
                **resumen,
                "mandato": [info.get("inicio_mandato", ""), fin],
                "url": info.get("url", ""),
                "bloques": leg["bloques"],
                "anual": {a: dict(c) for a, c in sorted(leg["anual"].items())},
                "al_anual": {
                    a: {c: v for c, v in d.items()} for a, d in sorted(leg["al_anual"].items())
                },
                "votos": leg["votos"],
            },
        )
    legisladores_out.sort(key=lambda l: l["n"])
    write_json(OUT_DIR / "legisladores.json", legisladores_out)
    write_json(OUT_DIR / "votaciones.json", votaciones_out)
    for anio, data in votos_por_anio.items():
        write_json(OUT_DIR / "votos" / f"{anio}.json", data)

    anios = sorted(votos_por_anio)
    write_json(
        OUT_DIR / "meta.json",
        {
            "generado": hoy,
            "desde": votaciones_out[0]["d"],
            "hasta": ultima_fecha,
            "sesiones": len({v["s"] for v in votaciones_out}),
            "votaciones": len(votaciones_out),
            "divididas": sum(v["dv"] for v in votaciones_out),
            "legisladores": len(legisladores_out),
            "anios": anios,
            "coaliciones": config["coaliciones"],
            "afinidad": afinidad,
            "disputa": disputa,
            "bloques": bloques,
        },
    )

    print(
        f"OK: {len(votaciones_out)} votaciones ({sum(v['dv'] for v in votaciones_out)} divididas), "
        f"{len(legisladores_out)} legisladores, {anios[0]}-{anios[-1]}"
    )
    if clasificar.sin_clasificar:
        print("\nBloques sin coalición asignada (quedan como OTROS); agregalos en data/coaliciones.json:")
        for bloque, n in clasificar.sin_clasificar.most_common():
            print(f"  {n:6d}  {bloque}")


if __name__ == "__main__":
    main()
