#!/usr/bin/env python3
"""Build the platform status diagram from components.json.

Writes, beside this script:
  status-light.svg, status-dark.svg   for Markdown (GitHub picks one per reader theme)
  index.html                          interactive: hover details, filters, links, table view

Update the status:  edit components.json, then run  python3 _generate.py
Standard library only.
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

HERE = Path(__file__).parent

# --------------------------------------------------------------------------
# Geometry (a 1200 px canvas reads well at GitHub's content width)
# --------------------------------------------------------------------------
W = 1200
M = 24                     # outer margin
LBL = 150                  # lane label column
RG = 104                   # right gutter for the long flows
COLS = 4
GAP = 12                   # between chips
CHIP_H = 54
ROW_GAP = 10
LANE_PAD = 16
LANE_GAP = 30              # between lanes (room for the short flows)
HEADER_H = 164
FOOTER_H = 36

X0 = M + LBL                                 # chips start
CHIPS_RIGHT = W - M - RG                     # chips end
CHIP_W = (CHIPS_RIGHT - X0 - (COLS - 1) * GAP) / COLS
BAND_RIGHT = CHIPS_RIGHT + 12

STATUS_ORDER = ["done", "partial", "todo", "external"]

THEMES = {
    "light": {
        "page": "#f9f9f7", "band": "#f1f0ec", "card": "#ffffff",
        "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
        "hair": "rgba(11,11,11,0.10)", "track": "#e1e0d9",
        "good": "#0ca30c", "warn": "#fab219", "todo": "#898781",
    },
    "dark": {
        "page": "#0d0d0d", "band": "#1a1a19", "card": "#242422",
        "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#898781",
        "hair": "rgba(255,255,255,0.10)", "track": "#2c2c2a",
        "good": "#0ca30c", "warn": "#fab219", "todo": "#898781",
    },
}


def chars_for(width: float, px_per_char: float) -> int:
    return max(4, int(width // px_per_char))


def fit(text: str, width: float, px_per_char: float) -> str:
    """Trim with an ellipsis when the estimated width overflows."""
    n = chars_for(width, px_per_char)
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def wrap(text: str, width: float, px_per_char: float) -> list[str]:
    n = chars_for(width, px_per_char)
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if len(candidate) <= n:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def css_vars(theme: dict) -> str:
    return ";".join(f"--{k}:{v}" for k, v in theme.items())


STYLE = """
.t{font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
.title{font-size:24px;font-weight:650;fill:var(--ink)}
.sub{font-size:13px;fill:var(--ink2)}
.small{font-size:11.5px;fill:var(--muted)}
.lane-title{font-size:13.5px;font-weight:650;fill:var(--ink)}
.lane-sub{font-size:11px;fill:var(--muted)}
.name{font-size:12px;font-weight:600;fill:var(--ink)}
.owner{font-size:10.5px;fill:var(--muted)}
.tile-v{font-size:26px;font-weight:650;fill:var(--ink)}
.tile-l{font-size:12px;fill:var(--ink2)}
.flow-l{font-size:11px;fill:var(--ink2);paint-order:stroke;stroke:var(--page);stroke-width:4px;stroke-linejoin:round}
.band{fill:var(--band)}
.card{fill:var(--card);stroke:var(--hair);stroke-width:1}
.s-todo .card,.s-external .card{stroke-dasharray:4 3;stroke:var(--muted);stroke-opacity:.55}
.s-todo .name,.s-external .name{fill:var(--ink2)}
.accent{fill:var(--todo)}
.s-done .accent{fill:var(--good)}
.s-partial .accent{fill:var(--warn)}
.flow{fill:none;stroke:var(--muted);stroke-width:1.6;stroke-dasharray:5 5;animation:dash 1.1s linear infinite}
.pulse{fill:none;stroke:var(--warn);stroke-width:2;transform-box:fill-box;transform-origin:center;animation:pulse 2.2s ease-out infinite}
.grow{transform-box:fill-box;transform-origin:left center;animation:grow 1.4s cubic-bezier(.2,.7,.2,1)}
@keyframes dash{to{stroke-dashoffset:-10}}
@keyframes pulse{0%{transform:scale(1);opacity:.6}80%{transform:scale(2.2);opacity:0}100%{opacity:0}}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@media (prefers-reduced-motion:reduce){.flow,.pulse,.grow{animation:none}}
"""


def icon(status: str, cx: float, cy: float) -> str:
    if status == "done":
        return (f'<circle cx="{cx}" cy="{cy}" r="9" fill="var(--good)"/>'
                f'<path d="M{cx-3.8},{cy+0.2} L{cx-1.1},{cy+3} L{cx+4},{cy-2.8}" fill="none" '
                f'stroke="#ffffff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>')
    if status == "partial":
        return (f'<circle class="pulse" cx="{cx}" cy="{cy}" r="8"/>'
                f'<circle cx="{cx}" cy="{cy}" r="8" fill="var(--card)" stroke="var(--warn)" stroke-width="2"/>'
                f'<path d="M{cx},{cy-8} A8,8 0 0 1 {cx},{cy+8} Z" fill="var(--warn)"/>')
    if status == "todo":
        return (f'<circle cx="{cx}" cy="{cy}" r="7.5" fill="none" stroke="var(--todo)" '
                f'stroke-width="1.6" stroke-dasharray="2.6 2.4"/>')
    return (f'<circle cx="{cx}" cy="{cy}" r="7.5" fill="none" stroke="var(--muted)" stroke-width="1.6"/>'
            f'<circle cx="{cx}" cy="{cy}" r="2.2" fill="var(--muted)"/>')


def layout(data: dict) -> tuple[list[dict], float]:
    """Position every lane and chip; return the lanes with geometry, and the canvas height."""
    y = HEADER_H
    lanes = []
    for lane in data["lanes"]:
        rows = max(1, -(-len(lane["components"]) // COLS))
        h = 2 * LANE_PAD + rows * CHIP_H + (rows - 1) * ROW_GAP
        chips = []
        for i, c in enumerate(lane["components"]):
            r, col = divmod(i, COLS)
            chips.append({**c,
                          "x": X0 + col * (CHIP_W + GAP),
                          "y": y + LANE_PAD + r * (CHIP_H + ROW_GAP)})
        lanes.append({**lane, "top": y, "h": h, "chips": chips})
        y += h + LANE_GAP
    return lanes, y - LANE_GAP + FOOTER_H


def counts(data: dict) -> dict:
    c = {s: 0 for s in STATUS_ORDER}
    for lane in data["lanes"]:
        for comp in lane["components"]:
            c[comp["status"]] += 1
    return c


def render_svg(data: dict, theme_name: str | None, interactive: bool = False) -> str:
    lanes, H = layout(data)
    by_id = {l["id"]: (i, l) for i, l in enumerate(lanes)}
    c = counts(data)
    tracked = c["done"] + c["partial"] + c["todo"]
    out = []
    root_cls = "t viz" + (f" {theme_name}" if theme_name else "")
    style_vars = f' style="{css_vars(THEMES[theme_name])}"' if theme_name else ""
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H:.0f}" width="{W}" '
               f'height="{H:.0f}" class="{root_cls}"{style_vars} role="img" aria-labelledby="t d">')
    out.append(f'<title id="t">{escape(data["title"])}</title>')
    out.append(f'<desc id="d">{c["done"]} done, {c["partial"]} partial, {c["todo"]} not started, '
               f'of {tracked} components, as of {escape(data["updated"])}.</desc>')
    out.append(f"<style>{STYLE}</style>")
    out.append('<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" '
               'markerHeight="7" orient="auto-start-reverse"><path d="M0,1 L9,5 L0,9 Z" '
               'fill="var(--muted)"/></marker></defs>')
    out.append(f'<rect width="{W}" height="{H:.0f}" fill="var(--page)"/>')

    # ---- header: title, subtitle, legend --------------------------------
    out.append(f'<text class="title" x="{M}" y="50">{escape(data["title"])}</text>')
    out.append(f'<text class="sub" x="{M}" y="76">Status as of {escape(data["updated"])} · '
               f'{tracked} components</text>')
    lx = M
    for s in STATUS_ORDER:
        label = data["statuses"][s]["label"]
        out.append(f'<g class="s-{s}">{icon(s, lx + 9, 106)}'
                   f'<text class="tile-l" x="{lx + 24}" y="110">{escape(label)}</text></g>')
        lx += 34 + len(label) * 6.9
    out.append(f'<text class="small" x="{M}" y="138">Arrows show who drives whom. '
               f'A pulsing marker is work in progress.</text>')

    # ---- header: stat tiles + segmented progress bar --------------------
    tile_w = 132
    tiles = [("done", c["done"]), ("partial", c["partial"]), ("todo", c["todo"])]
    tile_label = {"done": "Done", "partial": "In progress", "todo": "Not started"}
    tx = W - M - tile_w * len(tiles)
    for s, v in tiles:
        out.append(f'<g class="s-{s}">{icon(s, tx + 10, 44)}'
                   f'<text class="tile-l" x="{tx + 26}" y="48">{tile_label[s]}</text>'
                   f'<text class="tile-v" x="{tx}" y="86">{v}</text></g>')
        tx += tile_w
    bar_x, bar_w, bar_y = W - M - tile_w * len(tiles), tile_w * len(tiles) - 8, 104
    seg_x = bar_x
    colors = {"done": "var(--good)", "partial": "var(--warn)", "todo": "var(--track)"}
    parts = [(s, c[s]) for s in ("done", "partial", "todo") if c[s]]
    gaps = 2 * (len(parts) - 1)
    for i, (s, v) in enumerate(parts):
        w = (bar_w - gaps) * v / tracked
        out.append(f'<rect class="grow" x="{seg_x:.1f}" '
                   f'y="{bar_y}" width="{w:.1f}" height="8" rx="4" fill="{colors[s]}"/>')
        seg_x += w + 2
    pct = round(100 * c["done"] / tracked) if tracked else 0
    out.append(f'<text class="small" x="{bar_x}" y="{bar_y + 28}">{pct}% done · '
               f'{c["done"]} of {tracked}</text>')

    # ---- lanes and chips -----------------------------------------------
    for lane in lanes:
        top, h = lane["top"], lane["h"]
        out.append(f'<rect class="band" x="{M}" y="{top}" width="{BAND_RIGHT - M}" height="{h}" rx="12"/>')
        title_lines = wrap(lane["title"], LBL - 28, 7.6)[:2]
        for j, line in enumerate(title_lines):
            out.append(f'<text class="lane-title" x="{M + 16}" y="{top + 28 + j * 17}">{escape(line)}</text>')
        sub_y = top + 46 + (len(title_lines) - 1) * 17
        for j, line in enumerate(wrap(lane["subtitle"], LBL - 30, 5.9)[:3]):
            out.append(f'<text class="lane-sub" x="{M + 16}" y="{sub_y + j * 14}">{escape(line)}</text>')
        for ch in lane["chips"]:
            x, y, s = ch["x"], ch["y"], ch["status"]
            label = data["statuses"][s]["label"]
            attrs = ""
            if interactive:
                attrs = (f' tabindex="0" data-name="{escape(ch["name"])}" data-status="{s}" '
                         f'data-label="{escape(label)}" data-owner="{escape(ch.get("owner", ""))}" '
                         f'data-note="{escape(ch.get("note", ""))}" data-link="{escape(ch.get("link", ""))}"')
            out.append(f'<g class="chip s-{s}"{attrs}>')
            out.append(f'<title>{escape(ch["name"])} · {escape(label)}\n{escape(ch.get("note", ""))}</title>')
            out.append(f'<rect class="card" x="{x:.1f}" y="{y}" width="{CHIP_W:.1f}" height="{CHIP_H}" rx="9"/>')
            out.append(f'<rect class="accent" x="{x:.1f}" y="{y + 10}" width="3" height="{CHIP_H - 20}" rx="1.5"/>')
            out.append(icon(s, x + 22, y + CHIP_H / 2))
            text_w = CHIP_W - 44
            out.append(f'<text class="name" x="{x + 40:.1f}" y="{y + 23}">{escape(fit(ch["name"], text_w, 6.7))}</text>')
            owner = ch.get("owner", "").removeprefix("team-redbull/")
            out.append(f'<text class="owner" x="{x + 40:.1f}" y="{y + 40}">'
                       f'{escape(fit(owner, text_w, 5.9))}</text>')
            out.append("</g>")

    # ---- flows: adjacent lanes on the left, the rest on the right -------
    long_flows = []
    for f in data["flows"]:
        (ia, a), (ib, b) = by_id[f["from"]], by_id[f["to"]]
        if abs(ia - ib) == 1:
            upper, lower = (a, b) if ia < ib else (b, a)
            x = M + 22
            y1, y2 = upper["top"] + upper["h"] + 3, lower["top"] - 3
            if ia > ib:
                y1, y2 = y2, y1
            out.append(f'<path class="flow" d="M{x},{y1} L{x},{y2}" marker-end="url(#arrow)"/>')
            out.append(f'<text class="flow-l" x="{x + 12}" y="{(y1 + y2) / 2 + 4:.1f}">{escape(f["label"])}</text>')
        else:
            long_flows.append((abs(ia - ib), f, a, b))
    long_flows.sort(key=lambda t: t[0])
    ports: dict[str, int] = {}
    port_total: dict[str, int] = {}
    for _, f, a, b in long_flows:
        port_total[a["id"]] = port_total.get(a["id"], 0) + 1
        port_total[b["id"]] = port_total.get(b["id"], 0) + 1

    def port_y(lane: dict) -> float:
        k = ports.get(lane["id"], 0)
        ports[lane["id"]] = k + 1
        n = port_total[lane["id"]]
        return lane["top"] + lane["h"] * (k + 1) / (n + 1)

    for k, (_, f, a, b) in enumerate(long_flows):
        xk = BAND_RIGHT + 22 + k * 28
        ya, yb = port_y(a), port_y(b)
        sign = 1 if yb > ya else -1
        r = 10
        d = (f"M{BAND_RIGHT + 2},{ya:.1f} L{xk - r},{ya:.1f} Q{xk},{ya:.1f} {xk},{ya + sign * r:.1f} "
             f"L{xk},{yb - sign * r:.1f} Q{xk},{yb:.1f} {xk - r},{yb:.1f} L{BAND_RIGHT + 4},{yb:.1f}")
        out.append(f'<path class="flow" d="{d}" marker-end="url(#arrow)"/>')
        mid = (ya + yb) / 2
        out.append(f'<text class="flow-l" text-anchor="middle" transform="translate({xk + 4},{mid:.1f}) '
                   f'rotate(-90)">{escape(f["label"])}</text>')

    out.append(f'<text class="small" x="{M}" y="{H - 14:.0f}">Edit docs/implementation-status/components.json, then run '
               f'python3 docs/implementation-status/_generate.py</text>')
    out.append("</svg>")
    return "\n".join(out)


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{color-scheme:light;__LIGHT__}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;__DARK__}}
:root[data-theme="dark"]{color-scheme:dark;__DARK__}
:root[data-theme="light"]{color-scheme:light;__LIGHT__}
body{margin:0;background:var(--page);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1240px;margin:0 auto;padding:20px}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 12px}
.bar .lbl{color:var(--ink2);font-size:13px;margin-right:4px}
button{font:inherit;font-size:13px;border:1px solid var(--hair);background:var(--card);color:var(--ink);
  border-radius:999px;padding:5px 12px;cursor:pointer}
button[aria-pressed="false"]{opacity:.45}
button.theme{margin-left:auto}
svg.viz{width:100%;height:auto;display:block}
.chip{cursor:pointer;transition:opacity .15s}
.chip:focus{outline:none}.chip:focus .card,.chip:hover .card{stroke:var(--ink2);stroke-width:1.5}
.chip.dim{opacity:.18}
#tip{position:fixed;pointer-events:none;max-width:320px;background:var(--card);color:var(--ink);
  border:1px solid var(--hair);border-radius:10px;padding:10px 12px;font-size:13px;line-height:1.4;
  box-shadow:0 6px 24px rgba(0,0,0,.18);display:none;z-index:10}
#tip b{display:block;font-size:13.5px}#tip .st{color:var(--ink2);font-size:12px;margin:2px 0 6px}
#tip .ow{color:var(--muted);font-size:12px;margin-top:6px}
details{margin-top:18px;font-size:13px}summary{cursor:pointer;color:var(--ink2)}
table{border-collapse:collapse;width:100%;margin-top:10px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--hair);vertical-align:top}
th{color:var(--ink2);font-weight:600}td a{color:inherit}
</style>
</head>
<body>
<main>
<div class="bar">
  <span class="lbl">Show</span>
  __FILTERS__
  <button class="theme" id="theme" type="button">Theme</button>
</div>
__SVG__
<details><summary>Table view</summary>
<table><thead><tr><th>Component</th><th>Area</th><th>Status</th><th>Owner</th><th>Note</th></tr></thead>
<tbody>__ROWS__</tbody></table></details>
</main>
<div id="tip" role="tooltip"></div>
<script>
const tip=document.getElementById("tip");
const chips=[...document.querySelectorAll(".chip")];
function show(el,x,y){
  const d=el.dataset;
  tip.innerHTML="<b></b><div class=st></div><div class=nt></div><div class=ow></div>";
  tip.querySelector("b").textContent=d.name;
  tip.querySelector(".st").textContent=d.label;
  tip.querySelector(".nt").textContent=d.note;
  tip.querySelector(".ow").textContent=d.owner+(d.link?"  ·  click to open":"");
  tip.style.display="block";
  const r=tip.getBoundingClientRect();
  tip.style.left=Math.min(x+14,innerWidth-r.width-8)+"px";
  tip.style.top=Math.min(y+14,innerHeight-r.height-8)+"px";
}
chips.forEach(el=>{
  el.addEventListener("mousemove",e=>show(el,e.clientX,e.clientY));
  el.addEventListener("mouseleave",()=>tip.style.display="none");
  el.addEventListener("focus",()=>{const r=el.getBoundingClientRect();show(el,r.left,r.bottom);});
  el.addEventListener("blur",()=>tip.style.display="none");
  const open=()=>{if(el.dataset.link)window.open(el.dataset.link,"_blank","noopener");};
  el.addEventListener("click",open);
  el.addEventListener("keydown",e=>{if(e.key==="Enter")open();});
});
const on=new Set(["done","partial","todo","external"]);
document.querySelectorAll("button[data-s]").forEach(b=>b.addEventListener("click",()=>{
  const s=b.dataset.s; on.has(s)?on.delete(s):on.add(s);
  b.setAttribute("aria-pressed",on.has(s));
  chips.forEach(el=>el.classList.toggle("dim",!on.has(el.dataset.status)));
}));
document.getElementById("theme").addEventListener("click",()=>{
  const r=document.documentElement;
  const dark=r.dataset.theme?r.dataset.theme==="dark":matchMedia("(prefers-color-scheme:dark)").matches;
  r.dataset.theme=dark?"light":"dark";
});
</script>
</body>
</html>
"""


def render_html(data: dict) -> str:
    svg = render_svg(data, None, interactive=True)
    c = counts(data)
    filters = "".join(
        f'<button type="button" data-s="{s}" aria-pressed="true">{escape(data["statuses"][s]["label"])} '
        f'({c[s]})</button>' for s in STATUS_ORDER)
    rows = []
    for lane in data["lanes"]:
        for comp in lane["components"]:
            name = escape(comp["name"])
            if comp.get("link"):
                name = f'<a href="{escape(comp["link"])}">{name}</a>'
            rows.append(f'<tr><td>{name}</td><td>{escape(lane["title"])}</td>'
                        f'<td>{escape(data["statuses"][comp["status"]]["label"])}</td>'
                        f'<td>{escape(comp.get("owner", ""))}</td><td>{escape(comp.get("note", ""))}</td></tr>')
    return (HTML.replace("__TITLE__", escape(data["title"]))
                .replace("__LIGHT__", css_vars(THEMES["light"]))
                .replace("__DARK__", css_vars(THEMES["dark"]))
                .replace("__FILTERS__", filters)
                .replace("__SVG__", svg)
                .replace("__ROWS__", "".join(rows)))


def main() -> None:
    data = json.loads((HERE / "components.json").read_text(encoding="utf-8"))
    for lane in data["lanes"]:
        for comp in lane["components"]:
            if comp["status"] not in STATUS_ORDER:
                raise SystemExit(f'{comp["name"]}: unknown status {comp["status"]!r}')
    for theme in ("light", "dark"):
        (HERE / f"status-{theme}.svg").write_text(render_svg(data, theme), encoding="utf-8")
    (HERE / "index.html").write_text(render_html(data), encoding="utf-8")
    c = counts(data)
    print(f"wrote status-light.svg, status-dark.svg, index.html  "
          f"({c['done']} done, {c['partial']} partial, {c['todo']} not started, {c['external']} external)")


if __name__ == "__main__":
    main()
