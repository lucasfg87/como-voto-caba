/* ¿Cómo votó? · Legislatura porteña
 * SPA estática: lee los JSON de data/ generados por generate_site.py.
 */
(() => {
  "use strict";

  const VOTO = { A: "Afirmativo", N: "Negativo", B: "Abstención", X: "No votó" };
  const VOTO_COLOR = { A: "var(--v-a)", N: "var(--v-n)", B: "var(--v-b)", X: "var(--v-x)" };
  const LEG_URL = "https://www.legislatura.gob.ar/";
  const DOC_URL = "https://parlamentaria.legislatura.gob.ar/pages/download.aspx?IdDoc=";
  const PAGE = 50;
  const POCOS = 20; // menos votaciones divididas que esto: "pocos datos"

  const S = { meta: null, legs: null, legById: null, vots: null, votById: null, legCache: {}, votosAnio: {} };
  const app = document.getElementById("app");
  const tip = document.getElementById("tip");

  // ---------------------------------------------------------------- utils
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const norm = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const fdate = (iso) => { const [y, m, d] = iso.split("-"); return `${d}/${m}/${y}`; };
  const pct = (a, t) => (t ? Math.round((100 * a) / t) : null);
  const getJSON = (url) => fetch(url).then((r) => { if (!r.ok) throw new Error(url); return r.json(); });
  const coal = (c) => S.meta.coaliciones[c] || S.meta.coaliciones.OTROS || { nombre: c, color: "#888" };
  const chip = (c) => `<span class="chip" style="--c:${coal(c).color}"><i></i>${esc(coal(c).nombre)}</span>`;
  const vtag = (v) => `<span class="v v-${v}">${VOTO[v]}</span>`;
  const initials = (n) => n.split(" ").filter(Boolean).map((p) => p[0]).slice(0, 2).join("");
  const avatar = (l, cls = "") => {
    const c = coal(l.c).color;
    return l.f
      ? `<img class="avatar ${cls}" style="--c:${c}" src="fotos/${l.id}.jpg" alt="" loading="lazy">`
      : `<div class="avatar ${cls}" style="--c:${c}">${esc(initials(l.n))}</div>`;
  };
  const resBar = (r) => {
    const t = r[0] + r[1] + r[2] + r[3] || 1;
    return `<div class="res" title="${r[0]} afirmativos, ${r[1]} negativos, ${r[2]} abstenciones, ${r[3]} no votaron">${["A", "N", "B", "X"]
      .map((k, i) => `<span style="width:${(100 * r[i]) / t}%;background:${VOTO_COLOR[k]}"></span>`)
      .join("")}</div>`;
  };
  const votosAnio = async (y) => (S.votosAnio[y] ||= await getJSON(`data/votos/${y}.json`));
  const legDetail = async (id) => (S.legCache[id] ||= await getJSON(`data/leg/${id}.json`));

  function setNav(key) {
    document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("on", a.dataset.nav === key));
  }

  // Tooltip para elementos con data-tip
  document.addEventListener("mouseover", (e) => {
    const t = e.target.closest("[data-tip]");
    if (!t) { tip.hidden = true; return; }
    tip.innerHTML = t.dataset.tip;
    tip.hidden = false;
  });
  document.addEventListener("mousemove", (e) => {
    if (tip.hidden) return;
    const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = x + "px";
    tip.style.top = e.clientY + 16 + "px";
  });

  // Paginador genérico
  function pager(container, total, page, onPage) {
    const pages = Math.ceil(total / PAGE);
    if (pages <= 1) { container.innerHTML = ""; return; }
    container.innerHTML = `<button data-p="${page - 1}" ${page <= 0 ? "disabled" : ""}>← Anterior</button>
      <span>Página ${page + 1} de ${pages}</span>
      <button data-p="${page + 1}" ${page >= pages - 1 ? "disabled" : ""}>Siguiente →</button>`;
    container.querySelectorAll("button").forEach((b) => (b.onclick = () => onPage(+b.dataset.p)));
  }

  // ---------------------------------------------------------- legisladores
  function viewLegisladores() {
    setNav("legisladores");
    const m = S.meta;
    app.innerHTML = `
      <h1>¿Cómo votó tu legislador/a porteño/a?</h1>
      <p class="sub">${m.votaciones.toLocaleString("es-AR")} votaciones nominales de la Legislatura de la Ciudad de Buenos Aires,
        del ${fdate(m.desde)} al ${fdate(m.hasta)}.</p>
      <div class="controls">
        <input type="search" id="q" placeholder="Buscar por nombre o bloque…" autofocus>
        <select id="fc"><option value="">Todas las coaliciones</option>${Object.entries(m.coaliciones)
          .map(([k, c]) => `<option value="${k}">${esc(c.nombre)}</option>`).join("")}</select>
        <label class="chk"><input type="checkbox" id="act" checked> Solo en ejercicio</label>
        <span class="count" id="cnt"></span>
      </div>
      <div class="grid" id="grid"></div>`;
    const q = app.querySelector("#q"), fc = app.querySelector("#fc"), act = app.querySelector("#act");
    const render = () => {
      const nq = norm(q.value);
      const list = S.legs.filter((l) =>
        (!act.checked || l.act) && (!fc.value || l.c === fc.value) && (!nq || norm(l.n + " " + l.b).includes(nq)));
      app.querySelector("#cnt").textContent = `${list.length} legisladores`;
      app.querySelector("#grid").innerHTML = list.map((l) => `
        <a class="leg-card" href="#/legislador/${l.id}">
          ${avatar(l)}
          <div><div class="nm">${esc(l.n)}</div><div class="bl">${esc(l.b)}</div>
          <div class="bl">${l.y0 === l.y1 ? l.y0 : l.y0 + "–" + l.y1} · ${l.pr}% presentismo</div></div>
        </a>`).join("") || `<p class="note">No hay resultados.</p>`;
    };
    [q, fc, act].forEach((e) => (e.oninput = render));
    render();
  }

  // ------------------------------------------------------------- legislador
  async function viewLegislador(id) {
    setNav("legisladores");
    const base = S.legById[id];
    if (!base) { app.innerHTML = `<p>No encontramos ese legislador.</p>`; return; }
    app.innerHTML = `<p class="loading">Cargando…</p>`;
    const L = await legDetail(id);
    const afin = S.meta.afinidad;
    const nVotos = L.votos.length;
    const emit = L.votos.filter((v) => v[1] !== "X").length;
    const divs = L.votos.filter((v) => S.votById[v[0]]?.dv).length;

    const afinTiles = afin.map((c) => {
      const [a, t] = L.al[c] || [0, 0];
      const [ca, ct] = (L.co || {})[c] || [0, 0];
      const p = pct(a, t), pc = pct(ca, ct);
      return `<div class="tile pick" data-c="${c}" style="--c:${coal(c).color}" role="button" tabindex="0" title="Ver las votaciones"><div class="k">Con ${esc(coal(c).nombre)}</div>
        <div class="n">${p === null ? "—" : p + "%"}${t && t < POCOS ? ' <span class="badge-few" title="Menos de ' + POCOS + ' votaciones divididas: el porcentaje puede cambiar mucho">pocos datos</span>' : ""}</div>
        <div class="s">en divididas (${a} de ${t})</div>
        <div class="bar"><span style="width:${p || 0}%;background:${coal(c).color}"></span></div>
        <div class="s co">Coincidencia general: <b>${pc === null ? "—" : pc + "%"}</b> (${ca} de ${ct})</div></div>`;
    }).join("");

    const bloquesHist = L.bloques.map((b) =>
      `<li>${chip(b.c)} <b>${esc(b.b)}</b> <span class="note">${fdate(b.desde)} – ${fdate(b.hasta)}</span></li>`).join("");

    app.innerHTML = `
      <div class="stack">
        <div class="card profile">
          ${avatar(base, "lg")}
          <div>
            <h1>${esc(L.n)}</h1>
            <div>${chip(L.c)} <span class="meta">${esc(L.b)}</span></div>
            <div class="meta">Votaciones registradas: ${L.y0 === L.y1 ? L.y0 : L.y0 + "–" + L.y1}
              ${L.mandato && L.mandato[1] ? ` · Mandato actual hasta ${esc(L.mandato[1])}` : ""}
              ${L.url ? ` · <a href="${LEG_URL + encodeURI(L.url)}" target="_blank" rel="noopener">Ficha oficial</a>` : ""}</div>
          </div>
        </div>
        <div class="tiles">
          <div class="tile"><div class="k">Votaciones nominales</div><div class="n">${nVotos}</div><div class="s">${divs} divididas</div></div>
          <div class="tile"><div class="k">Presentismo</div><div class="n">${L.pr}%</div><div class="s">votó en ${emit} de ${nVotos}</div>
            <div class="bar"><span style="width:${L.pr}%;background:var(--v-a)"></span></div></div>
        </div>
        <div class="card"><h2>Afinidad política</h2>
          <p class="note" style="margin-top:-6px">El número grande es la <b>afinidad en votaciones divididas</b>: de las votaciones en que
            las principales coaliciones votaron distinto, en qué % votó igual que la mayoría de cada una. La <b>coincidencia general</b>
            cuenta todas las votaciones, incluidas las casi unánimes, por eso suele ser mucho más alta.</p>
          <div class="tiles">${afinTiles}</div>
          <p class="note" style="margin-bottom:0">Hacé clic en una coalición para ver en qué votaciones coincidió y en cuáles no.</p>
          <div id="afp"></div>
        </div>
        <div class="two">
          <div class="card"><h2>Afinidad por año</h2><div id="ch-al"></div>
            <div class="legend">${afin.map((c) => `<span style="--c:${coal(c).color}"><i></i>${esc(coal(c).nombre)}</span>`).join("")}</div>
            <p class="note">% de votaciones divididas del año en que votó igual que la mayoría de cada coalición.</p></div>
          <div class="card"><h2>Votos por año</h2><div id="ch-yr"></div>
            <div class="legend">${["A", "N", "B", "X"].map((k) => `<span style="--c:${VOTO_COLOR[k]}"><i></i>${VOTO[k]}</span>`).join("")}</div></div>
        </div>
        <div class="card"><h2>Mapa de votos</h2>
          <p class="note">Cada cuadrado es una votación (pasá el mouse para ver cuál). Con borde: votaciones divididas.</p>
          <div id="waffle"></div></div>
        ${L.bloques.length > 1 ? `<div class="card"><h2>Bloques</h2><ul class="prose" style="list-style:none;padding:0;margin:0">${bloquesHist}</ul></div>` : ""}
        <div class="card"><h2>Historial de votaciones</h2>
          <div class="controls">
            <input type="search" id="hq" placeholder="Buscar en títulos o expediente…">
            <select id="hy"><option value="">Todos los años</option>${Object.keys(L.anual).reverse().map((y) => `<option>${y}</option>`).join("")}</select>
            <select id="hv"><option value="">Todos los votos</option>${Object.entries(VOTO).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
            <label class="chk"><input type="checkbox" id="hd"> Solo divididas</label>
          </div>
          <div class="tbl-wrap"><table><thead><tr><th>Fecha</th><th>Votación</th><th>Voto</th>${afin.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody id="hb"></tbody></table></div>
          <div class="pager" id="hp"></div></div>
      </div>`;

    app.querySelector("#ch-al").innerHTML = lineChart(L.al_anual, afin);
    app.querySelector("#ch-yr").innerHTML = stackedYears(L.anual);
    renderWaffle(L);
    afinPanel(L);

    const hq = app.querySelector("#hq"), hy = app.querySelector("#hy"), hv = app.querySelector("#hv"), hd = app.querySelector("#hd");
    const rows = L.votos.map(([vid, v]) => ({ v, x: S.votById[vid] })).filter((r) => r.x).reverse();
    let page = 0;
    const render = () => {
      const nq = norm(hq.value);
      const list = rows.filter((r) =>
        (!hy.value || r.x.d.startsWith(hy.value)) && (!hv.value || r.v === hv.value) && (!hd.checked || r.x.dv) &&
        (!nq || norm(r.x.t + " " + r.x.ex + " " + r.x.as).includes(nq)));
      page = Math.min(page, Math.max(0, Math.ceil(list.length / PAGE) - 1));
      app.querySelector("#hb").innerHTML = list.slice(page * PAGE, page * PAGE + PAGE).map((r) => `
        <tr class="row-link" data-href="#/votacion/${r.x.id}">
          <td>${fdate(r.x.d)}</td>
          <td><div class="vt">${esc(r.x.t)}${r.x.dv ? '<span class="badge-dv">dividida</span>' : ""}</div>
            <div class="vt-sub">${esc([r.x.tp, r.x.ex || r.x.as].filter(Boolean).join(" · "))}</div></td>
          <td>${vtag(r.v)}</td>
          ${afin.map((c) => { const m = r.x.m[c]; return `<td>${m ? `<span class="v v-${m}" title="Mayoría ${esc(coal(c).nombre)}">${m === r.v ? "=" : "≠"} ${VOTO[m].slice(0, 3)}</span>` : '<span class="note">—</span>'}</td>`; }).join("")}
        </tr>`).join("") || `<tr><td colspan="9" class="note">Sin resultados.</td></tr>`;
      pager(app.querySelector("#hp"), list.length, page, (p) => { page = p; render(); });
    };
    [hq, hy, hv, hd].forEach((e) => (e.oninput = () => { page = 0; render(); }));
    render();
  }

  // Panel que lista, para la coalición elegida, las votaciones en que coincidió o no con su mayoría
  function afinPanel(L) {
    const box = app.querySelector("#afp");
    const st = { c: null, igual: false, todas: false, page: 0 };
    // Mismo criterio que generate_site.py: votó y la coalición tuvo mayoría
    const base = L.votos.map(([vid, v]) => ({ v, x: S.votById[vid] }))
      .filter((r) => r.x && r.v !== "X").reverse();

    const render = () => {
      app.querySelectorAll(".tile.pick").forEach((t) => t.classList.toggle("on", t.dataset.c === st.c));
      if (!st.c) { box.innerHTML = ""; return; }
      const c = st.c, col = coal(c);
      const scope = base.filter((r) => r.x.m[c] && (st.todas || r.x.dv));
      const dist = scope.filter((r) => r.v !== r.x.m[c]);
      const igu = scope.filter((r) => r.v === r.x.m[c]);
      const list = st.igual ? igu : dist;
      const pages = Math.max(1, Math.ceil(list.length / PAGE));
      st.page = Math.min(st.page, pages - 1);
      box.innerHTML = `
        <div class="afp" style="--c:${col.color}">
          <div class="afp-head">
            <h3>${esc(L.n)} y ${esc(col.nombre)}</h3>
            <button class="afp-x" data-act="close" aria-label="Cerrar">✕</button>
          </div>
          <div class="controls" style="margin-bottom:10px">
            <div class="seg">
              <button data-act="dist" class="${st.igual ? "" : "on"}">Votó distinto (${dist.length})</button>
              <button data-act="igual" class="${st.igual ? "on" : ""}">Votó igual (${igu.length})</button>
            </div>
            <div class="seg">
              <button data-act="div" class="${st.todas ? "" : "on"}">Divididas</button>
              <button data-act="todas" class="${st.todas ? "on" : ""}">Todas</button>
            </div>
          </div>
          ${list.length ? `<div class="tbl-wrap"><table><thead><tr><th>Fecha</th><th>Votación</th><th>Su voto</th><th>Mayoría ${esc(c)}</th></tr></thead><tbody>
            ${list.slice(st.page * PAGE, st.page * PAGE + PAGE).map((r) => `
              <tr class="row-link" data-href="#/votacion/${r.x.id}">
                <td>${fdate(r.x.d)}</td>
                <td><div class="vt">${esc(r.x.t)}${r.x.dv ? '<span class="badge-dv">dividida</span>' : ""}</div>
                  <div class="vt-sub">${esc([r.x.tp, r.x.ex || r.x.as].filter(Boolean).join(" · "))}</div></td>
                <td>${vtag(r.v)}</td><td>${vtag(r.x.m[c])}</td>
              </tr>`).join("")}</tbody></table></div><div class="pager" id="afp-pg"></div>`
            : `<p class="note">${st.igual ? "No votó igual que" : "No votó distinto de"} la mayoría de ${esc(col.nombre)} en ${st.todas ? "ninguna votación" : "ninguna votación dividida"}.</p>`}
        </div>`;
      const pg = box.querySelector("#afp-pg");
      if (pg) pager(pg, list.length, st.page, (p) => { st.page = p; render(); });
    };

    box.onclick = (e) => {
      const b = e.target.closest("button[data-act]");
      if (!b) return;
      const a = b.dataset.act;
      if (a === "close") st.c = null;
      else if (a === "dist" || a === "igual") st.igual = a === "igual";
      else st.todas = a === "todas";
      st.page = 0;
      render();
    };
    app.querySelectorAll(".tile.pick").forEach((t) => {
      const pick = () => {
        st.c = st.c === t.dataset.c ? null : t.dataset.c;
        st.igual = false; st.page = 0;
        render();
        if (st.c) box.scrollIntoView({ behavior: "smooth", block: "nearest" });
      };
      t.onclick = pick;
      t.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } };
    });
  }

  function renderWaffle(L) {
    const byYear = {};
    L.votos.forEach(([vid, v]) => {
      const x = S.votById[vid];
      if (!x) return;
      (byYear[x.d.slice(0, 4)] ||= []).push({ x, v });
    });
    app.querySelector("#waffle").innerHTML = Object.keys(byYear).sort().reverse().map((y) => `
      <div class="waffle-year"><div class="yr">${y}</div><div class="waffle">${byYear[y].map(({ x, v }) =>
        `<a href="#/votacion/${x.id}" class="w-${v}${x.dv ? " dv" : ""}" data-tip="<b>${VOTO[v]}</b> · ${fdate(x.d)}<br>${esc(esc(x.t))}"></a>`).join("")}</div></div>`).join("");
  }

  // Gráfico de líneas de afinidad por año (SVG)
  function lineChart(data, keys) {
    const years = Object.keys(data).sort();
    if (!years.length) return `<p class="note">Sin votaciones divididas.</p>`;
    const W = 480, H = 200, P = { l: 34, r: 10, t: 10, b: 24 };
    const x = (i) => P.l + (years.length === 1 ? (W - P.l - P.r) / 2 : (i * (W - P.l - P.r)) / (years.length - 1));
    const y = (v) => P.t + (1 - v / 100) * (H - P.t - P.b);
    let g = [0, 25, 50, 75, 100].map((v) => `<line class="gl" x1="${P.l}" x2="${W - P.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${P.l - 6}" y="${y(v) + 4}" text-anchor="end">${v}%</text>`).join("");
    g += years.map((yr, i) => `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${yr}</text>`).join("");
    keys.forEach((c) => {
      const pts = years.map((yr, i) => {
        const [a, t] = (data[yr] || {})[c] || [0, 0];
        return t >= 3 ? { i, p: (100 * a) / t, a, t, yr } : null;
      });
      const color = coal(c).color;
      let path = "", pen = false;
      pts.forEach((p) => { if (!p) { pen = false; return; } path += `${pen ? "L" : "M"}${x(p.i)},${y(p.p)}`; pen = true; });
      g += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2.5"/>`;
      g += pts.filter(Boolean).map((p) => `<circle cx="${x(p.i)}" cy="${y(p.p)}" r="4" fill="${color}" data-tip="${esc(coal(c).nombre)} ${p.yr}: <b>${Math.round(p.p)}%</b> (${p.a}/${p.t})"/>`).join("");
    });
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Afinidad por año">${g}</svg>`;
  }

  // Barras apiladas de votos por año (SVG)
  function stackedYears(anual) {
    const years = Object.keys(anual).sort();
    const W = 480, H = 200, P = { l: 34, r: 10, t: 10, b: 24 };
    const max = Math.max(...years.map((y) => Object.values(anual[y]).reduce((s, n) => s + n, 0)), 1);
    const bw = Math.min(36, ((W - P.l - P.r) / years.length) * 0.7);
    const step = (W - P.l - P.r) / years.length;
    const y = (v) => P.t + (1 - v / max) * (H - P.t - P.b);
    let g = [0, 0.5, 1].map((f) => `<line class="gl" x1="${P.l}" x2="${W - P.r}" y1="${y(max * f)}" y2="${y(max * f)}"/><text x="${P.l - 6}" y="${y(max * f) + 4}" text-anchor="end">${Math.round(max * f)}</text>`).join("");
    years.forEach((yr, i) => {
      let acc = 0;
      const cx = P.l + step * i + step / 2;
      ["A", "N", "B", "X"].forEach((k) => {
        const n = anual[yr][k] || 0;
        if (!n) return;
        g += `<rect x="${cx - bw / 2}" width="${bw}" y="${y(acc + n)}" height="${y(acc) - y(acc + n)}" fill="${VOTO_COLOR[k]}" data-tip="${yr} · ${VOTO[k]}: <b>${n}</b>"/>`;
        acc += n;
      });
      g += `<text x="${cx}" y="${H - 6}" text-anchor="middle">${yr}</text>`;
    });
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Votos por año">${g}</svg>`;
  }

  // ------------------------------------------------------------ votaciones
  function viewVotaciones(params) {
    setNav("votaciones");
    const afin = S.meta.afinidad;
    const tipos = [...new Set(S.vots.map((v) => v.tp).filter(Boolean))].sort();
    app.innerHTML = `
      <h1>Votaciones nominales</h1>
      <p class="sub">${S.meta.divididas.toLocaleString("es-AR")} de ${S.meta.votaciones.toLocaleString("es-AR")} fueron <b>divididas</b>
        (las principales coaliciones votaron distinto).</p>
      <div class="controls">
        <input type="search" id="q" placeholder="Buscar por tema o expediente…" value="${esc(params.get("q") || "")}">
        <select id="fy"><option value="">Todos los años</option>${[...S.meta.anios].reverse().map((y) => `<option>${y}</option>`).join("")}</select>
        <select id="ft"><option value="">Todos los tipos</option>${tipos.map((t) => `<option>${esc(t)}</option>`).join("")}</select>
        <label class="chk"><input type="checkbox" id="fd" ${params.get("div") ? "checked" : ""}> Solo divididas</label>
        <span class="count" id="cnt"></span>
      </div>
      <div class="card"><div class="tbl-wrap"><table>
        <thead><tr><th>Fecha</th><th>Votación</th><th>Resultado</th>${afin.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
        <tbody id="tb"></tbody></table></div><div class="pager" id="pg"></div></div>`;
    const q = app.querySelector("#q"), fy = app.querySelector("#fy"), ft = app.querySelector("#ft"), fd = app.querySelector("#fd");
    const all = [...S.vots].reverse();
    let page = 0;
    const render = () => {
      const nq = norm(q.value);
      const list = all.filter((v) => (!fy.value || v.d.startsWith(fy.value)) && (!ft.value || v.tp === ft.value) &&
        (!fd.checked || v.dv) && (!nq || norm(v.t + " " + v.ex + " " + v.as).includes(nq)));
      app.querySelector("#cnt").textContent = `${list.length.toLocaleString("es-AR")} votaciones`;
      app.querySelector("#tb").innerHTML = list.slice(page * PAGE, page * PAGE + PAGE).map((v) => `
        <tr class="row-link" data-href="#/votacion/${v.id}">
          <td>${fdate(v.d)}</td>
          <td><div class="vt">${esc(v.t)}${v.dv ? '<span class="badge-dv">dividida</span>' : ""}</div>
            <div class="vt-sub">${esc([v.tp, v.ex || v.as].filter(Boolean).join(" · "))}</div></td>
          <td>${resBar(v.r)}<div class="vt-sub">${v.r[0]} · ${v.r[1]} · ${v.r[2]}</div></td>
          ${afin.map((c) => `<td>${v.m[c] ? vtag(v.m[c]) : '<span class="note">—</span>'}</td>`).join("")}
        </tr>`).join("") || `<tr><td colspan="8" class="note">Sin resultados.</td></tr>`;
      pager(app.querySelector("#pg"), list.length, page, (p) => { page = p; render(); window.scrollTo(0, 0); });
    };
    [q, fy, ft, fd].forEach((e) => (e.oninput = () => { page = 0; render(); }));
    render();
  }

  async function viewVotacion(id) {
    setNav("votaciones");
    const v = S.votById[id];
    if (!v) { app.innerHTML = `<p>No encontramos esa votación.</p>`; return; }
    app.innerHTML = `<p class="loading">Cargando…</p>`;
    const rows = (await votosAnio(v.d.slice(0, 4)))[id] || [];
    const bloques = S.meta.bloques;

    // Agregado por bloque
    const porBloque = {};
    rows.forEach(([lid, cod, bi]) => {
      const b = (porBloque[bi] ||= { b: bloques[bi], A: 0, N: 0, B: 0, X: 0, n: 0 });
      b[cod]++; b.n++;
    });
    const bl = Object.values(porBloque).sort((a, b) => b.n - a.n);
    const legName = (lid) => S.legById[lid]?.n || `#${lid}`;
    const col = (k) => {
      const list = rows.filter((r) => r[1] === k).sort((a, b) => legName(a[0]).localeCompare(legName(b[0])));
      return `<div><h2>${VOTO[k]} <span class="note">(${list.length})</span></h2><ul>${list.map(([lid, , bi]) =>
        `<li style="--c:${coal(bloques[bi].c).color}"><i></i><a href="#/legislador/${lid}">${esc(legName(lid))}</a> <span class="note">${esc(bloques[bi].n)}</span></li>`).join("")}</ul></div>`;
    };
    app.innerHTML = `
      <div class="stack">
        <div class="card">
          <div class="note">${fdate(v.d)} · ${esc([v.tp, v.ex, v.as].filter(Boolean).join(" · "))}${v.dv ? ' <span class="badge-dv">dividida</span>' : ""}</div>
          <h1 style="margin-top:6px">${esc(v.t)}</h1>
          <p class="note"><a href="https://www.legislatura.gob.ar/InfoSesion/${v.s}" target="_blank" rel="noopener">Ver sesión en legislatura.gob.ar</a>
            ${v.doc && v.doc !== "0" ? ` · <a href="${DOC_URL + v.doc}" target="_blank" rel="noopener">Texto del expediente</a>` : ""}</p>
          <div class="tiles" style="margin-top:12px">${["A", "N", "B", "X"].map((k, i) => `<div class="tile"><div class="k">${VOTO[k]}</div><div class="n" style="color:${k === "X" ? "inherit" : VOTO_COLOR[k]}">${v.r[i]}</div></div>`).join("")}</div>
        </div>
        <div class="card"><h2>Por bloque</h2><div class="tbl-wrap"><table>
          <thead><tr><th>Bloque</th><th>Coalición</th><th></th><th class="num">Afirm.</th><th class="num">Neg.</th><th class="num">Abst.</th><th class="num">No votó</th></tr></thead>
          <tbody>${bl.map((b) => `<tr><td>${esc(b.b.n)}</td><td>${chip(b.b.c)}</td><td>${resBar([b.A, b.N, b.B, b.X])}</td>
            <td class="num">${b.A}</td><td class="num">${b.N}</td><td class="num">${b.B}</td><td class="num">${b.X}</td></tr>`).join("")}</tbody>
        </table></div></div>
        <div class="card vote-cols">${["A", "N", "B", "X"].map(col).join("")}</div>
      </div>`;
  }

  // --------------------------------------------------------------- ranking
  function viewRanking() {
    setNav("ranking");
    const afin = S.meta.afinidad;
    const cols = [
      { k: "n", t: "Legislador/a", get: (l) => l.n },
      { k: "tv", t: "Votaciones", get: (l) => l.tv, num: 1 },
      { k: "pr", t: "Presentismo", get: (l) => l.pr, num: 1 },
      ...afin.map((c) => ({ k: "al_" + c, t: "Afin. " + c, num: 1, get: (l) => { const [a, t] = l.al[c] || [0, 0]; return t >= 10 ? (100 * a) / t : -1; } })),
    ];
    let sort = { k: "pr", dir: -1 };
    app.innerHTML = `
      <h1>Ranking de legisladores</h1>
      <p class="sub">Presentismo y afinidad con cada coalición <b>en votaciones divididas</b> (se muestra si votó en al menos 10;
        en gris y cursiva si son menos de ${POCOS}, porque el porcentaje todavía es poco estable).</p>
      <div class="controls">
        <input type="search" id="q" placeholder="Filtrar por nombre o bloque…">
        <select id="fc"><option value="">Todas las coaliciones</option>${Object.entries(S.meta.coaliciones).map(([k, c]) => `<option value="${k}">${esc(c.nombre)}</option>`).join("")}</select>
        <label class="chk"><input type="checkbox" id="act" checked> Solo en ejercicio</label>
      </div>
      <div class="card"><div class="tbl-wrap"><table><thead><tr>${cols.map((c) => `<th class="sort ${c.num ? "num" : ""}" data-k="${c.k}">${esc(c.t)}</th>`).join("")}</tr></thead><tbody id="tb"></tbody></table></div></div>`;
    const q = app.querySelector("#q"), fc = app.querySelector("#fc"), act = app.querySelector("#act");
    const render = () => {
      const col = cols.find((c) => c.k === sort.k);
      const nq = norm(q.value);
      const list = S.legs.filter((l) => (!act.checked || l.act) && (!fc.value || l.c === fc.value) && (!nq || norm(l.n + " " + l.b).includes(nq)))
        .sort((a, b) => { const x = col.get(a), y = col.get(b); return (typeof x === "string" ? x.localeCompare(y) : x - y) * sort.dir; });
      app.querySelectorAll("th.sort").forEach((th) => (th.textContent = cols.find((c) => c.k === th.dataset.k).t + (th.dataset.k === sort.k ? (sort.dir > 0 ? " ↑" : " ↓") : "")));
      app.querySelector("#tb").innerHTML = list.map((l) => `
        <tr class="row-link" data-href="#/legislador/${l.id}">
          <td><b>${esc(l.n)}</b><div class="vt-sub">${chip(l.c)} ${esc(l.b)}</div></td>
          <td class="num">${l.tv}</td><td class="num">${l.pr}%</td>
          ${afin.map((c) => {
            const [a, t] = l.al[c] || [0, 0];
            const few = t < POCOS;
            return `<td class="num mini-pct${few ? " few" : ""}" title="${a} de ${t} votaciones divididas${few ? " (pocos datos)" : ""}">${t >= 10 ? Math.round((100 * a) / t) + "%" : '<span class="note">—</span>'}</td>`;
          }).join("")}
        </tr>`).join("");
    };
    app.querySelectorAll("th.sort").forEach((th) => (th.onclick = () => {
      sort = sort.k === th.dataset.k ? { k: sort.k, dir: -sort.dir } : { k: th.dataset.k, dir: th.dataset.k === "n" ? 1 : -1 };
      render();
    }));
    [q, fc, act].forEach((e) => (e.oninput = render));
    render();
  }

  // ---------------------------------------------------------------- acerca
  function viewAcerca() {
    setNav("acerca");
    const m = S.meta;
    app.innerHTML = `<div class="card prose">
      <h1>Metodología</h1>
      <p>Este sitio replica para la <b>Legislatura de la Ciudad Autónoma de Buenos Aires</b> la idea de
        <a href="https://comovoto.dev.ar" target="_blank" rel="noopener">¿Cómo Votó?</a>, creado por Rodrigo Quiroga para el Congreso Nacional.</p>
      <h2>Datos</h2>
      <ul>
        <li>Fuente: votaciones nominales publicadas por la Legislatura en <a href="https://www.legislatura.gob.ar/InfoSesion/" target="_blank" rel="noopener">Información de Sesiones</a>
          (servicio web de parlamentaria.legislatura.gob.ar). Se actualiza automáticamente.</li>
        <li>Cobertura: ${m.votaciones.toLocaleString("es-AR")} votaciones en ${m.sesiones} sesiones, del ${fdate(m.desde)} al ${fdate(m.hasta)}.
          Antes de agosto de 2016 la Legislatura no publica votos nominales en formato de datos.</li>
        <li>Solo se incluyen votaciones <b>nominales</b> (electrónicas). Las votaciones a mano alzada no registran el voto de cada legislador.</li>
        <li>"No votó" agrupa a quienes estaban ausentes o presentes sin emitir voto (por ejemplo, quien preside la sesión).</li>
      </ul>
      <h2>Métricas</h2>
      <ul>
        <li><b>Coaliciones:</b> cada bloque se asigna a un espacio (${Object.values(m.coaliciones).map((c) => esc(c.nombre)).join(", ")}).
          La asignación es editable en <code>data/coaliciones.json</code>.</li>
        <li><b>Mayoría de una coalición:</b> el voto más frecuente entre sus legisladores en esa votación.</li>
        <li><b>Votación dividida:</b> las mayorías de ${m.disputa.map((c) => esc(coal(c).nombre)).join(", ")} no coinciden.</li>
        <li><b>Afinidad:</b> % de votaciones divididas en las que el legislador votó igual que la mayoría de cada coalición (solo cuenta cuando votó).
          Con menos de ${POCOS} votaciones divididas se marca como "pocos datos".</li>
        <li><b>Coincidencia general:</b> lo mismo, pero sobre todas las votaciones. Como la mayoría de lo que se vota sale casi por unanimidad,
          suele ser alta para casi todos: sirve de contexto, pero no muestra posicionamiento político.</li>
        <li><b>Presentismo:</b> % de votaciones nominales en las que emitió voto.</li>
      </ul>
      <p class="note">Datos generados el ${fdate(m.generado)}. Si encontrás un error, avisá.</p>
    </div>`;
  }

  // ---------------------------------------------------------------- router
  document.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-href]");
    if (tr && !e.target.closest("a")) location.hash = tr.dataset.href;
  });

  // Estadísticas de visitas (GoatCounter, sin cookies). El sitio navega por #hash,
  // así que cada sección se cuenta a mano como una página distinta.
  let visitaPendiente = null;
  function contarVisita(parts) {
    const leg = parts[0] === "legislador" && S.legById[+parts[1]];
    const visita = { path: "/" + parts.join("/"), title: leg ? leg.n : document.title };
    if (window.goatcounter && window.goatcounter.count) window.goatcounter.count(visita);
    else visitaPendiente = visita;
  }
  document.getElementById("gc")?.addEventListener("load", () => {
    if (visitaPendiente && window.goatcounter?.count) window.goatcounter.count(visitaPendiente);
    visitaPendiente = null;
  });

  function route() {
    tip.hidden = true;
    const [path, query] = location.hash.slice(1).split("?");
    const params = new URLSearchParams(query || "");
    const parts = path.split("/").filter(Boolean);
    window.scrollTo(0, 0);
    contarVisita(parts);
    if (parts[0] === "legislador") return viewLegislador(+parts[1]);
    if (parts[0] === "votaciones") return viewVotaciones(params);
    if (parts[0] === "votacion") return viewVotacion(+parts[1]);
    if (parts[0] === "ranking") return viewRanking();
    if (parts[0] === "acerca") return viewAcerca();
    return viewLegisladores();
  }

  Promise.all([getJSON("data/meta.json"), getJSON("data/legisladores.json"), getJSON("data/votaciones.json")])
    .then(([meta, legs, vots]) => {
      Object.assign(S, { meta, legs, vots });
      S.legById = Object.fromEntries(legs.map((l) => [l.id, l]));
      S.votById = Object.fromEntries(vots.map((v) => [v.id, v]));
      document.getElementById("foot-meta").textContent = `Actualizado: ${fdate(meta.generado)}.`;
      window.addEventListener("hashchange", route);
      route();
    })
    .catch((err) => {
      app.innerHTML = `<p>No se pudieron cargar los datos (${esc(err.message)}). Generalos con <code>python generate_site.py</code>
        y serví la carpeta <code>docs/</code> con un servidor local.</p>`;
    });
})();
