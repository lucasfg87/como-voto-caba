"""Genera la miniatura del video y la imagen de vista previa de links.

  promo/miniatura.png  1920x1080 (miniatura del video de LinkedIn)
  docs/og.png          1200x630  (vista previa al compartir el link)

Uso:  python promo/miniatura.py
"""

from __future__ import annotations

import base64

from playwright.sync_api import sync_playwright

from grabar_video import BASE, DOCS, LEGISLADORA, PUERTO, servir

PLANTILLA = """<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0}
body{width:%(w)spx;height:%(h)spx;overflow:hidden;background:#11141b;color:#fff;
  font-family:system-ui,"Segoe UI",sans-serif;display:flex;align-items:center;gap:%(gap)spx;padding:0 %(pad)spx;position:relative}
body::before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 85%% 30%%,rgba(245,196,0,.16),transparent 55%%)}
.txt{flex:1 1 0;position:relative;z-index:1}
.logo{display:flex;align-items:center;gap:.5em;font-weight:800;font-size:%(logo)spx;color:#9aa3b5;margin-bottom:.9em}
.logo i{width:1.1em;height:1.1em;border-radius:.28em;background:#f5c400;display:inline-block}
h1{font-size:%(h1)spx;line-height:1.04;letter-spacing:-.035em;margin-bottom:.38em}
h1 em{font-style:normal;color:#f5c400}
p{font-size:%(p)spx;color:#c9cfdb;line-height:1.35}
.url{display:inline-block;margin-top:1.1em;font-size:%(url)spx;font-weight:800;border:3px solid #f5c400;border-radius:.4em;padding:.25em .7em;background:#1d2330}
.shot{flex:0 0 %(shot)spx;position:relative;z-index:1}
.shot img{width:100%%;display:block;border-radius:18px;box-shadow:0 30px 70px rgba(0,0,0,.55);border:1px solid #2c3340;transform:rotate(-1.5deg)}
</style></head><body>
<div class="txt">
  <div class="logo"><i></i>Legislatura porteña</div>
  <h1>¿Cómo votó tu <em>legislador/a</em>?</h1>
  <p>Presentismo, afinidad política y más de 2.000 votaciones desde 2016.</p>
  <div class="url">comovotocaba.com.ar</div>
</div>
<div class="shot"><img src="data:image/png;base64,%(img)s"></div>
</body></html>"""

FORMATOS = [
    (BASE / "miniatura.png", dict(w=1920, h=1080, gap=70, pad=110, logo=34, h1=104, p=38, url=46, shot=900)),
    (DOCS / "og.png", dict(w=1200, h=630, gap=44, pad=64, logo=22, h1=64, p=24, url=28, shot=560)),
]


def main() -> None:
    srv = servir()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1100, "height": 900}, device_scale_factor=2, color_scheme="light")
        page = ctx.new_page()
        page.goto(f"http://127.0.0.1:{PUERTO}/#/legislador/{LEGISLADORA}")
        page.wait_for_selector(".tile.pick")
        page.wait_for_function("[...document.images].every(i => i.complete)")
        # Captura: encabezado del perfil + tarjeta de afinidad
        caja = page.evaluate("""() => {
          const a = document.querySelector('.card.profile').getBoundingClientRect();
          const b = document.querySelector('.tile.pick').closest('.card').getBoundingClientRect();
          return {x: a.x - 12, y: a.y - 12, width: a.width + 24, height: b.bottom - a.y + 24};
        }""")
        captura = base64.b64encode(page.screenshot(clip=caja)).decode()

        for destino, f in FORMATOS:
            pg = browser.new_page(viewport={"width": f["w"], "height": f["h"]})
            pg.set_content(PLANTILLA % {**f, "img": captura})
            pg.wait_for_timeout(300)
            pg.screenshot(path=str(destino))
            pg.close()
            print("OK:", destino)
        browser.close()
    srv.shutdown()


if __name__ == "__main__":
    main()
