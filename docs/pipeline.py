#!/usr/bin/env python3
"""One diagram, two files: docs/pipeline.drawio (editable in draw.io) and docs/pipeline.svg
(what README shows). Both come from the NODES / EDGES tables below, so they cannot drift apart
the way a hand-exported picture and its source do. Re-run after changing the pipeline.

    python3 docs/pipeline.py
"""
import os, re, html

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Numbers that describe the code are read from the code, the way S6 / S7 read them for README and
# CLAUDE.md: this diagram said "15 faults" and "14 constants" for days after the table held 42 and
# rebuild.py derived 44 (2026-09-13).
def _read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()
N_FAULTS = len(re.findall(r'^\s*\("[A-Z]\d+",\s*"', _read(".claude/skills/workspace-checks/scripts/selftest.py"), re.M))
N_CONSTS = len(set(re.findall(r'out\["(\w+)"\]', _read(".claude/skills/update-dashboard/scripts/rebuild.py"))))

# ---- palette: DESIGN.md §2-3 ---------------------------------------------------------------
INK, MUTED, PAGE, CARD, LINE = "#1c1c1a", "#6b6f6c", "#f9f9f7", "#fcfcfb", "#d8dcd9"
BLUE, GREEN, YELLOW, PURPLE, ORANGE, TEAL = "#2a78d6", "#008300", "#eda100", "#4a3aa7", "#eb6834", "#1baf7a"

W = 1400
LANE_X, LANE_W, LABEL_W = 20, 1360, 140
LANE_H, LANE_GAP, TOP = 118, 12, 30
COL0, COL_STEP, NODE_W, NODE_H = 175, 200, 182, 76

LANES = [("you",     "You"),
         ("guard",   "Guards"),
         ("skill",   "update.py ·\none local run"),
         ("files",   "Files"),
         ("checks",  "Checks ·\nworkspace-checks")]
H = TOP + len(LANES) * (LANE_H + LANE_GAP) + 18

# id, lane, column, text, accent colour, dashed border?
NODES = [
 ("you_drop","you",0,"Drop the month's statements and broker exports into inbox/",INK,False),
 ("you_say","you",1,"Say “update dashboards”",INK,False),
 ("you_read","you",5,"Claude reads the summary — never the rows — and asks you only what a program cannot decide; the report is the record read out",INK,False),
 ("sched","guard",0,"Scheduled task · 26th 09:00 — readiness check only, writes nothing",MUTED,True),
 ("pre","guard",1,"preflight.py — names every inbox file, hashes inbox/ + findata/, flags anything over 30 days",BLUE,False),
 ("ver","guard",3,"--verify before every write · --reseed after your own",BLUE,True),
 ("parse","skill",2,"Steps 1–2 · parsers read each statement, reconcile it (documents[].reconcile), categorise via merchants.json",PURPLE,False),
 ("write","skill",3,"Step 3 · writes the ledgers, spending.csv, banks.json and the registry copies",PURPLE,False),
 ("reb","skill",4,f"Step 4 · rebuild.py — {N_CONSTS} dashboard constants recomputed from findata/",PURPLE,False),
 ("arch","skill",5,"Steps 6–7 · archives as YYYYMMDD_<tag>_<name>, appends the update record",PURPLE,False),
 ("inbox","files",0,"inbox/",YELLOW,False),
 ("fd","files",3,"findata/ — accounts.json registry, ledgers, holdings, funds, merchants",YELLOW,False),
 ("dash","files",4,"dashboards/finance_dashboard.html — one self-contained page, no server",YELLOW,False),
 ("archv","files",5,"archive/",YELLOW,False),
 ("self_","checks",1,f"selftest.py — plants {N_FAULTS} faults; every checker must fire",GREEN,True),
 ("hook","checks",3,"PostToolUse hook → check_data.py: balance chains, rules, registry, copies",GREEN,False),
 ("cdes","checks",4,"check_design.py (DESIGN.md) · check_render.py (headless Chromium, 3 widths)",GREEN,False),
]

# source, target, label, dashed?
EDGES = [
 ("you_drop","inbox","",False), ("inbox","pre","",False), ("you_say","pre","",False),
 ("sched","pre","runs",True), ("pre","parse","",False), ("parse","write","",False),
 ("ver","write","gate",True), ("write","fd","",False), ("fd","reb","",False),
 ("reb","dash","",False), ("write","hook","every Edit / Write",True), ("dash","cdes","",False),
 ("reb","arch","",False), ("arch","archv","",False), ("cdes","you_read","",False),
 ("self_","hook","checks the checkers",True),
]

def lane_y(i): return TOP + i * (LANE_H + LANE_GAP)
LANE_IDX = {k: i for i, (k, _) in enumerate(LANES)}
def geom(n):
    _, lane, col, *_r = n
    return (COL0 + col * COL_STEP, lane_y(LANE_IDX[lane]) + (LANE_H - NODE_H) // 2, NODE_W, NODE_H)
BOX = {n[0]: geom(n) for n in NODES}

def wrap(text, width=26):
    out, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur: out.append(cur)
    return out

# ---- draw.io -------------------------------------------------------------------------------
def drawio():
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    for i, (k, label) in enumerate(LANES):
        st = (f"rounded=0;whiteSpace=wrap;html=1;fillColor={PAGE};strokeColor={LINE};fontColor={MUTED};"
              "align=left;verticalAlign=middle;spacingLeft=10;fontStyle=1;fontSize=12;")
        cells.append(f'<mxCell id="lane_{k}" value="{html.escape(label).replace(chr(10), "&lt;br&gt;")}" style="{st}" vertex="1" parent="1">'
                     f'<mxGeometry x="{LANE_X}" y="{lane_y(i)}" width="{LANE_W}" height="{LANE_H}" as="geometry"/></mxCell>')
    for n in NODES:
        nid, lane, col, text, color, dashed = n
        x, y, w, h = BOX[nid]
        st = (f"rounded=1;whiteSpace=wrap;html=1;fillColor={CARD};strokeColor={color};strokeWidth=2;"
              f"fontColor={INK};fontSize=12;align=center;verticalAlign=middle;spacing=6;" + ("dashed=1;" if dashed else ""))
        cells.append(f'<mxCell id="{nid}" value="{html.escape(text)}" style="{st}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    for i, (a, b, label, dashed) in enumerate(EDGES):
        st = (f"edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeColor={MUTED};"
              f"strokeWidth=1.5;fontColor={MUTED};fontSize=10;" + ("dashed=1;" if dashed else ""))
        cells.append(f'<mxCell id="e{i}" value="{html.escape(label)}" style="{st}" edge="1" parent="1" source="{a}" target="{b}">'
                     f'<mxGeometry relative="1" as="geometry"/></mxCell>')
    return ('<mxfile host="app.diagrams.net" agent="docs/pipeline.py"><diagram id="pipeline" name="Pipeline">'
            f'<mxGraphModel dx="{W}" dy="{H}" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
            f'fold="1" page="1" pageScale="1" pageWidth="{W}" pageHeight="{H}" math="0" shadow="0"><root>'
            + "".join(cells) + '</root></mxGraphModel></diagram></mxfile>\n')

# ---- svg -----------------------------------------------------------------------------------
def route(a, b):
    """Orthogonal path between two boxes: straight when aligned, one elbow otherwise."""
    ax, ay, aw, ah = BOX[a]; bx, by, bw, bh = BOX[b]
    acx, acy, bcx, bcy = ax + aw / 2, ay + ah / 2, bx + bw / 2, by + bh / 2
    if abs(acy - bcy) < 1:                              # same lane → horizontal
        return [(ax + aw, acy), (bx, bcy)] if bx > ax else [(ax, acy), (bx + bw, bcy)]
    if abs(acx - bcx) < 1:                              # same column → vertical
        return [(acx, ay + ah), (bcx, by)] if by > ay else [(acx, ay), (bcx, by + bh)]
    # elbow: leave vertically from the source, arrive horizontally at the target
    sy = ay + ah if by > ay else ay
    tx = bx if bcx > acx else bx + bw
    return [(acx, sy), (acx, bcy), (tx, bcy)]

def svg():
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         'font-family="system-ui, -apple-system, Segoe UI, sans-serif" font-size="12">',
         '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
         f'<path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker></defs>',
         f'<rect width="{W}" height="{H}" fill="white"/>']
    for i, (k, label) in enumerate(LANES):
        y = lane_y(i)
        o.append(f'<rect x="{LANE_X}" y="{y}" width="{LANE_W}" height="{LANE_H}" rx="6" fill="{PAGE}" stroke="{LINE}"/>')
        for j, ln in enumerate(label.split("\n")):
            o.append(f'<text x="{LANE_X+12}" y="{y + LANE_H/2 - 6*(label.count(chr(10))) + 4 + j*15}" fill="{MUTED}" font-weight="700" font-size="12" letter-spacing=".04em">{html.escape(ln.upper())}</text>')
    for a, b, label, dashed in EDGES:
        pts = route(a, b)
        d = "M" + " L".join(f"{x:.0f},{y:.0f}" for x, y in pts)
        o.append(f'<path d="{d}" fill="none" stroke="{MUTED}" stroke-width="1.5" marker-end="url(#arr)"' + (' stroke-dasharray="5,4"' if dashed else "") + '/>')
        if label:
            mx, my = pts[len(pts)//2] if len(pts) == 3 else ((pts[0][0]+pts[1][0])/2, (pts[0][1]+pts[1][1])/2)
            tw = len(label) * 6 + 8
            o.append(f'<rect x="{mx - tw/2:.0f}" y="{my-8:.0f}" width="{tw}" height="15" fill="white"/>')
            o.append(f'<text x="{mx:.0f}" y="{my+3:.0f}" text-anchor="middle" fill="{MUTED}" font-size="10">{html.escape(label)}</text>')
    for nid, lane, col, text, color, dashed in NODES:
        x, y, w, h = BOX[nid]
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{CARD}" stroke="{color}" stroke-width="2"' + (' stroke-dasharray="6,4"' if dashed else "") + '/>')
        lines = wrap(text)
        y0 = y + h / 2 - (len(lines) - 1) * 7.5
        for j, ln in enumerate(lines):
            o.append(f'<text x="{x + w/2}" y="{y0 + j*15 + 4:.0f}" text-anchor="middle" fill="{INK}">{html.escape(ln)}</text>')
    o.append('</svg>\n')
    return "\n".join(o)

if __name__ == "__main__":
    open(os.path.join(HERE, "pipeline.drawio"), "w", encoding="utf-8").write(drawio())
    open(os.path.join(HERE, "pipeline.svg"), "w", encoding="utf-8").write(svg())
    print(f"wrote docs/pipeline.drawio and docs/pipeline.svg — {len(NODES)} nodes, {len(EDGES)} edges")
