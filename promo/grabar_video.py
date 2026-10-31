"""Graba un video de presentación del sitio (1920x1080) recorriéndolo solo.

Sirve docs/ en local, maneja el navegador con Playwright y captura cuadros con
el screencast de Chrome. Los textos, el cursor y las placas de inicio/cierre se
dibujan dentro de la misma página, así el video sale de una sola toma.

Uso:  python promo/grabar_video.py   ->  promo/como-voto-caba.mp4
"""

from __future__ import annotations

import base64
import functools
import http.server
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent
DOCS = BASE.parent / "docs"
FRAMES = BASE / "frames"
SALIDA = BASE / "como-voto-caba.mp4"
FFMPEG = shutil.which("ffmpeg") or str(
    next(Path.home().glob("AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin/ffmpeg.exe"), "ffmpeg")
)
PUERTO = 8790
LEGISLADORA = 30942  # Bárbara Rossen

OVERLAY = r"""
(() => {
  const css = `
  #pv-cap{position:fixed;left:50%;bottom:26px;transform:translate(-50%,20px);opacity:0;z-index:9999;
    background:rgba(17,20,27,.92);color:#fff;font:600 22px/1.3 system-ui,"Segoe UI",sans-serif;
    padding:14px 28px;border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,.25);transition:all .45s ease;
    max-width:900px;text-align:center;letter-spacing:-.01em}
  #pv-cap.on{opacity:1;transform:translate(-50%,0)}
  #pv-cap b{color:#f5c400}
  #pv-cur{position:fixed;left:0;top:0;width:28px;height:28px;z-index:10000;pointer-events:none;
    transition:transform .8s cubic-bezier(.45,.05,.25,1);filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}
  #pv-cur.clk::after{content:"";position:absolute;left:-14px;top:-14px;width:28px;height:28px;border-radius:50%;
    background:rgba(245,196,0,.55);animation:pvc .45s ease-out}
  @keyframes pvc{from{transform:scale(.3);opacity:1}to{transform:scale(1.6);opacity:0}}
  #pv-card{position:fixed;inset:0;z-index:9998;display:flex;flex-direction:column;align-items:center;justify-content:center;
    background:#11141b;color:#fff;font-family:system-ui,"Segoe UI",sans-serif;text-align:center;transition:opacity .7s ease;padding:40px}
  #pv-card.off{opacity:0;pointer-events:none}
  #pv-card .logo{display:flex;align-items:center;gap:18px;font-weight:800;font-size:24px;color:#9aa3b5;margin-bottom:28px}
  #pv-card .logo i{width:30px;height:30px;border-radius:8px;background:#f5c400;display:inline-block}
  #pv-card h1{font-size:60px;line-height:1.08;margin:0 0 26px;letter-spacing:-.03em;max-width:900px}
  #pv-card h1 em{font-style:normal;color:#f5c400}
  #pv-card p{font-size:25px;color:#c9cfdb;margin:0 0 12px;max-width:820px;line-height:1.35}
  #pv-card .url{margin-top:26px;font-size:36px;font-weight:800;color:#fff;background:#1d2330;border:2px solid #f5c400;
    padding:12px 34px;border-radius:16px}
  #pv-card .by{margin-top:30px;font-size:18px;color:#9aa3b5}
  #pv-card .by b{color:#fff}`;
  const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
  const cap = document.createElement("div"); cap.id = "pv-cap"; document.body.appendChild(cap);
  const cur = document.createElement("div"); cur.id = "pv-cur";
  cur.innerHTML = '<svg viewBox="0 0 24 24" width="28" height="28"><path d="M4 2l15 10-6.5 1.4L16 21l-3 1.4-3.6-7.7L4 19z" fill="#fff" stroke="#11141b" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  cur.style.transform = "translate(512px,330px)";
  document.body.appendChild(cur);
  const card = document.createElement("div"); card.id = "pv-card"; card.className = "off"; document.body.appendChild(card);
  window.pv = {
    cap(html) { cap.classList.remove("on"); setTimeout(() => { cap.innerHTML = html; if (html) cap.classList.add("on"); }, html && cap.innerHTML ? 250 : 0); },
    move(x, y, ms) { cur.style.transitionDuration = (ms || 800) + "ms"; cur.style.transform = `translate(${x}px,${y}px)`; },
    click() { cur.classList.remove("clk"); void cur.offsetWidth; cur.classList.add("clk"); },
    card(html) {
      cur.style.opacity = html ? 0 : 1;
      if (html) { card.innerHTML = html; card.classList.remove("off"); } else card.classList.add("off");
    },
  };
})();
"""

INICIO = """
<div class="logo"><i></i>¿Cómo votó? · Legislatura porteña</div>
<h1>¿Cómo votó tu <em>legislador/a</em> porteño/a?</h1>
<p>Todas las votaciones nominales de la Legislatura de la Ciudad de Buenos Aires, desde 2016.</p>
"""

CIERRE = """
<div class="logo"><i></i>¿Cómo votó? · Legislatura porteña</div>
<h1>Datos <em>oficiales</em>,<br>actualizados todos los días.</h1>
<p>Presentismo · afinidad política · más de 2.000 votaciones</p>
<div class="url">comovotocaba.com.ar</div>
<div class="by">Hecho por <b>Lucas Gomez</b> · inspirado en comovoto.dev.ar de Rodrigo Quiroga</div>
"""


def servir() -> http.server.ThreadingHTTPServer:
    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    handler = functools.partial(Silencioso, directory=str(DOCS))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PUERTO), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Grabadora:
    """Guarda los cuadros del screencast de Chrome con su marca de tiempo."""

    def __init__(self, page):
        self.cuadros: list[tuple[float, Path]] = []
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._cuadro)

    def _cuadro(self, ev):
        ruta = FRAMES / f"{len(self.cuadros):05d}.jpg"
        ruta.write_bytes(base64.b64decode(ev["data"]))
        self.cuadros.append((ev["metadata"]["timestamp"], ruta))
        self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})

    def empezar(self):
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080})

    def terminar(self):
        self.cdp.send("Page.stopScreencast")


def main() -> None:
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)
    srv = servir()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1024, "height": 576}, device_scale_factor=1.875, color_scheme="light")
        page = ctx.new_page()
        page.goto(f"http://127.0.0.1:{PUERTO}/#/")
        page.wait_for_selector(".leg-card img")
        page.evaluate(OVERLAY)
        page.evaluate(f"pv.card({INICIO!r})")
        page.wait_for_timeout(600)

        rec = Grabadora(page)
        rec.empezar()
        espera = page.wait_for_timeout
        js = page.evaluate

        def centro(sel):
            b = page.locator(sel).first.bounding_box()
            return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

        def ir(sel, ms=800):
            x, y = centro(sel)
            js(f"pv.move({x},{y},{ms})")
            espera(ms + 80)
            page.mouse.move(x, y)
            return x, y

        def clic(sel, ms=800):
            x, y = ir(sel, ms)
            js("pv.click()")
            page.mouse.click(x, y)

        def scroll(sel, bloque="center", ms=900):
            js(f"document.querySelector({sel!r}).scrollIntoView({{behavior:'smooth', block:'{bloque}'}})")
            espera(ms)

        # 1. Placa de inicio
        espera(3200)
        js("pv.card('')")
        espera(700)

        # 2. Buscar una legisladora
        js("pv.cap('Buscá a cualquier <b>legislador/a</b> de la Ciudad')")
        clic("#q")
        espera(300)
        page.keyboard.type("Rossen", delay=140)
        espera(900)
        clic(f'a[href="#/legislador/{LEGISLADORA}"]')
        page.wait_for_selector(".tile.pick")
        espera(1400)

        # 3. Perfil y afinidad
        js("pv.cap('Presentismo, votos por año y <b>afinidad</b> con cada espacio político')")
        espera(1800)
        scroll(".tile.pick", "center", 1200)
        espera(2200)

        # 4. Panel de votaciones de una coalición
        js("pv.cap('Clic en una coalición: en qué votaciones votó <b>distinto</b> y en cuáles <b>igual</b>')")
        espera(600)
        clic('.tile.pick[data-c="LLA"]')
        espera(900)
        scroll(".afp", "start", 1200)
        espera(2400)
        clic('.afp [data-act="todas"]')
        espera(1200)
        clic('.afp [data-act="igual"]')
        espera(2200)

        # 5. Mapa de votos
        js("pv.cap('Cada cuadrado es una votación: <b>verde</b> afirmativo, <b>rojo</b> negativo')")
        scroll("#waffle", "center", 1200)
        cuadros = page.locator("#waffle a")
        n = cuadros.count()
        for i in (n - 3, n - 9, n - 16):
            b = cuadros.nth(max(i, 0)).bounding_box()
            if b:
                x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
                js(f"pv.move({x},{y},500)")
                espera(520)
                page.mouse.move(x, y)
                espera(900)

        # 6. Votaciones
        js("pv.cap('')")
        clic('nav a[data-nav="votaciones"]')
        page.wait_for_selector("#tb tr")
        js("pv.cap('Más de <b>2.000 votaciones</b> con el voto de cada legislador/a')")
        espera(1200)
        clic("#fd")
        espera(1300)
        clic("#tb tr.row-link")
        espera(1600)
        js("window.scrollBy({top:380,behavior:'smooth'})")
        espera(2600)

        # 7. Ranking
        js("pv.cap('')")
        clic('nav a[data-nav="ranking"]')
        page.wait_for_selector("#tb tr")
        js("pv.cap('Ranking de <b>presentismo</b> y afinidad de los 60 legisladores')")
        espera(1800)
        js("window.scrollBy({top:300,behavior:'smooth'})")
        espera(2400)

        # 8. Placa de cierre
        js("pv.cap('')")
        js(f"pv.card({CIERRE!r})")
        espera(4800)

        rec.terminar()
        espera(300)
        browser.close()
    srv.shutdown()

    # Armar el MP4 respetando el tiempo real entre cuadros
    cuadros = rec.cuadros
    lista = FRAMES / "lista.txt"
    with open(lista, "w", encoding="utf-8") as f:
        for (t, ruta), (t2, _) in zip(cuadros, cuadros[1:] + [(cuadros[-1][0] + 0.5, None)]):
            f.write(f"file '{ruta.name}'\nduration {max(t2 - t, 0.001):.4f}\n")
        f.write(f"file '{cuadros[-1][1].name}'\n")
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
         "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p",
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-movflags", "+faststart", str(SALIDA)],
        check=True,
    )
    shutil.rmtree(FRAMES)
    dur = cuadros[-1][0] - cuadros[0][0]
    print(f"OK: {SALIDA} ({len(cuadros)} cuadros, {dur:.1f} s)")


if __name__ == "__main__":
    sys.exit(main())
