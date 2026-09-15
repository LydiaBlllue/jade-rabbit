#!/usr/bin/env python3
"""产品流程图,一份数据两个文件:docs/zh/product_flow.drawio(可在 draw.io 里改)和
docs/zh/product_flow.svg(向导里展示的那张)。两者都由下面的 PHASES / NODES / EDGES 表生成,
所以不会像手工导出的图和它的源文件那样各走各的。改了流程就重跑:

    python3 docs/zh/product_flow.py

它和 docs/pipeline.py 是两张图:那张画的是数据怎么流过脚本和检查器(工程视角),
这张画的是一个人从试用到每个月怎么用它(产品视角)。
"""
import os, re, html, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- 调色板:DESIGN.md §2-3 ----------------------------------------------------------------
INK, MUTED, PAGE, CARD, LINE = "#1c1c1a", "#6b6f6c", "#f9f9f7", "#fcfcfb", "#d8dcd9"
BLUE, PURPLE, AMBER, RED = "#2a78d6", "#4a3aa7", "#c98500", "#d03b3b"

# ---- 版式:三列(你 / Jade Toad / 页面)自上而下,四个阶段是横向色带 ----------------------
W = 1180
GUTTER_L, LABEL_W = 20, 120          # 左侧阶段标签
COL_X0, COL_W, COL_GAP = 170, 300, 30
TOP, HEAD_H = 24, 44                 # 顶部列标题
ROW_GAP, PHASE_GAP, PHASE_PAD = 22, 28, 18
FONT, LINE_H, PAD_V = 12.5, 16, 12

COLS = [("you",  "你",           INK),
        ("jr",   "Jade Toad",    PURPLE),
        ("page", "页面",         BLUE)]

# key, 标题, 副标题
PHASES = [
 ("try",   "试用",  "1 分钟,不装任何东西"),
 ("setup", "建立",  "约 20 分钟,只做一次"),
 ("month", "每月",  "导入日,默认 26 号"),
 ("always","随时",  "每周、每季、工具更新时"),
]

# id, phase, row(阶段内从 0 起), col, 文字, 虚线边框?(自动发生或可选的步骤)
NODES = [
 ("t_open", "try",0,"you","克隆仓库,双击打开 dashboards/finance_dashboard.html。",False),
 ("t_demo", "try",0,"page","Emma Roy 的一年:19 页,全部合成数据,余额链照样闭合。",False),

 ("s_drop", "setup",0,"you","把上个月的文件丢进 inbox/:银行对账单、券商的持仓和活动导出、海外账户截图。文件名不改。",False),
 ("s_say",  "setup",1,"you","说「set this up」。",False),
 ("s_draft","setup",1,"jr","逐份读文件,起草账户表、每月文件表和第一版计划;列出文件答不了的问题。",False),
 ("s_ans",  "setup",2,"you","对着表格改错处,回答约 12 个问题:显示的名字、出生年、日常额度、投资桶、海外资产……",False),
 ("s_write","setup",3,"jr","问题没清零就拒绝写入。清零后生成 findata/register/,账本留空,重建页面。",False),
 ("s_page", "setup",4,"page","名字、账户、计划已就位;历史为空,每一页都说明「还没有导入」,而不是显得坏了。",False),

 ("m_remind","month",0,"jr","导入日早上提醒:哪些文件到了,哪些还缺。只读不写。",True),
 ("m_drop", "month",0,"you","从各银行下载本月对账单和导出,丢进 inbox/。",False),
 ("m_say",  "month",1,"you","说「update dashboards」。",False),
 ("m_run",  "month",1,"jr","一条本地命令做完:认出每份文件、按内容查重 → 解析器逐份读,对平了才写 → 商户分类 → 写数据 → 重建页面 → 归档原件。模型只看摘要。",False),
 ("m_report","month",2,"page","Records → Updates 就是报告:变了什么 · 问你什么 · 注意到什么 · 替你决定了什么 · 收到哪些文件。页头一句话:数据到哪、缺什么、几项待答。",False),
 ("m_read", "month",2,"you","读报告;回答待确认项:新商户、没有署名的 e-Transfer、解析器读不了的文件。",False),
 ("m_file", "month",3,"jr","一句话即归档:答案写回商户表和账本的类型列,页面重建。",False),

 ("a_look", "always",0,"you","每周看 This month:额度还剩多少。每季过一遍 Investing → Rules 和 Checkpoints。",False),
 ("a_dots", "always",0,"page","侧边栏圆点:琥珀 = 看一眼,红 = 规则被破。四个检查器过不去,页面根本建不出来。",False),
 ("a_sync", "always",1,"jr","工具更新时:sync.py 推入技能和模板,migrate.py 把数据形状逐步升级;你的数据一个字节不碰。",True),
]

# source, target, 标签, 虚线?
EDGES = [
 ("t_open","t_demo","",False),
 ("t_demo","s_drop","觉得值得,就做成自己的",False),
 ("s_drop","s_say","",False), ("s_say","s_draft","",False), ("s_draft","s_ans","草稿按表格给你看",False),
 ("s_ans","s_write","",False), ("s_write","s_page","",False), ("s_page","m_say","同一批文件就是第一次导入:直接说「update dashboards」",False),
 ("m_remind","m_drop","",True), ("m_drop","m_say","",False), ("m_say","m_run","",False),
 ("m_run","m_report","",False), ("m_report","m_read","",False), ("m_read","m_file","一句话",False),
 ("m_file","m_drop","下个月",True),
 ("m_report","a_dots","",False), ("a_dots","a_look","",False),
]

# ---- 排版 ----------------------------------------------------------------------------------
def cjk_w(ch):
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1

def wrap(text, units=44):
    """按显示宽度折行:一个汉字算 2,一个西文字符算 1。汉字逐字折;连续的西文(单词、路径)当一个整体,
    放不下就整体换行,只有它自己就超宽时才硬拆。"""
    tokens = re.findall(r"[^\u3000-\u9fff\uff00-\uffef ]+ ?|.", text)
    lines, cur, w = [], "", 0
    for tok in tokens:
        tw = sum(cjk_w(c) for c in tok)
        if w + tw > units and cur and tok[0] in ",.;:)!?。,、;:)」":   # 标点跟着前一行走
            cur += tok[0]; tok, tw = tok[1:], tw - cjk_w(tok[0])
            if not tok: continue
        if w + tw > units and cur:
            lines.append(cur.rstrip()); cur, w = "", 0
            if tok == " ": continue
        while tw > units:                      # 一个西文串本身就超过一行
            cut = units - w if w else units
            lines.append(cur + tok[:cut]); tok, tw = tok[cut:], tw - cut; cur, w = "", 0
        cur += tok; w += tw
    if cur.strip(): lines.append(cur.rstrip())
    return lines

COL_IDX = {k: i for i, (k, _, _) in enumerate(COLS)}
def col_x(c): return COL_X0 + COL_IDX[c] * (COL_W + COL_GAP)

LINES = {n[0]: wrap(n[4]) for n in NODES}
def node_h(nid): return PAD_V * 2 + LINE_H * len(LINES[nid])

# 每个阶段:行高由该行最高的节点决定
BOX, PHASE_Y = {}, {}
y = TOP + HEAD_H
for pk, _, _ in PHASES:
    rows = {}
    for n in NODES:
        if n[1] == pk: rows.setdefault(n[2], []).append(n)
    py0 = y
    y += PHASE_PAD
    for r in sorted(rows):
        rh = max(node_h(n[0]) for n in rows[r])
        for n in rows[r]:
            h = node_h(n[0])
            BOX[n[0]] = (col_x(n[3]), y + (rh - h) / 2, COL_W, h)
        y += rh + ROW_GAP
    y += PHASE_PAD - ROW_GAP
    PHASE_Y[pk] = (py0, y - py0)
    y += PHASE_GAP
H = y + 12 - PHASE_GAP

# ---- draw.io -------------------------------------------------------------------------------
def drawio():
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    for pk, title, sub in PHASES:
        py, ph = PHASE_Y[pk]
        st = (f"rounded=1;whiteSpace=wrap;html=1;fillColor={PAGE};strokeColor={LINE};fontColor={MUTED};"
              "align=left;verticalAlign=top;spacingLeft=10;spacingTop=6;fontSize=12;")
        label = f"<b>{html.escape(title)}</b><br><font style='font-size:10px'>{html.escape(sub)}</font>"
        cells.append(f'<mxCell id="phase_{pk}" value="{html.escape(label)}" style="{st}" vertex="1" parent="1">'
                     f'<mxGeometry x="{GUTTER_L}" y="{py:.0f}" width="{W - 2*GUTTER_L}" height="{ph:.0f}" as="geometry"/></mxCell>')
    for ck, label, color in COLS:
        st = (f"text;html=1;align=center;verticalAlign=middle;fontStyle=1;fontSize=12;fontColor={color};")
        cells.append(f'<mxCell id="col_{ck}" value="{html.escape(label.upper())}" style="{st}" vertex="1" parent="1">'
                     f'<mxGeometry x="{col_x(ck)}" y="{TOP}" width="{COL_W}" height="{HEAD_H - 12}" as="geometry"/></mxCell>')
    for nid, _p, _r, col, text, dashed in NODES:
        x, yy, w, h = BOX[nid]
        color = dict((k, c) for k, _, c in COLS)[col]
        st = (f"rounded=1;whiteSpace=wrap;html=1;fillColor={CARD};strokeColor={color};strokeWidth=2;"
              f"fontColor={INK};fontSize=12;align=left;verticalAlign=middle;spacing=8;" + ("dashed=1;" if dashed else ""))
        cells.append(f'<mxCell id="{nid}" value="{html.escape(text)}" style="{st}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{yy:.0f}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    for i, (a, b, label, dashed) in enumerate(EDGES):
        st = (f"edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeColor={MUTED};"
              f"strokeWidth=1.5;fontColor={MUTED};fontSize=10;" + ("dashed=1;" if dashed else ""))
        cells.append(f'<mxCell id="e{i}" value="{html.escape(label)}" style="{st}" edge="1" parent="1" source="{a}" target="{b}">'
                     f'<mxGeometry relative="1" as="geometry"/></mxCell>')
    return ('<mxfile host="app.diagrams.net" agent="docs/zh/product_flow.py"><diagram id="product_flow" name="Product flow">'
            f'<mxGraphModel dx="{W}" dy="{H:.0f}" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
            f'fold="1" page="1" pageScale="1" pageWidth="{W}" pageHeight="{H:.0f}" math="0" shadow="0"><root>'
            + "".join(cells) + '</root></mxGraphModel></diagram></mxfile>\n')

# ---- svg -----------------------------------------------------------------------------------
def route(a, b):
    """正交连线:同列竖直,同行水平,否则从源底部出、到目标侧边入。回环单独画。"""
    ax, ay, aw, ah = BOX[a]; bx, by, bw, bh = BOX[b]
    acx, acy, bcx, bcy = ax + aw / 2, ay + ah / 2, bx + bw / 2, by + bh / 2
    if abs(acx - bcx) < 1:
        return [(acx, ay + ah), (bcx, by)] if by > ay else [(acx, ay), (bcx, by + bh)]
    if abs(acy - bcy) < 1 or (by < ay + ah and ay < by + bh):     # 同一行(或纵向重叠)
        return [(ax + aw, acy), (bx, bcy)] if bx > ax else [(ax, acy), (bx + bw, bcy)]
    sy = ay + ah if by > ay else ay
    tx = bx if bcx > acx else bx + bw
    return [(acx, sy), (acx, bcy), (tx, bcy)]

def loop_route(a, b):
    """回环:从 a 底部出,走左侧沟槽,回到上方 b 的左侧。"""
    ax, ay, aw, ah = BOX[a]; bx, by, bw, bh = BOX[b]
    gx, cx, dy = COL_X0 - 16, ax + aw / 2, ay + ah + 14
    return [(cx, ay + ah), (cx, dy), (gx, dy), (gx, by + bh / 2), (bx, by + bh / 2)]

def gap_route(a, b):
    """跨阶段:从 a 底部出,在 b 所在阶段第一行和第二行之间的缝里横穿,从 b 顶部偏右进入。"""
    ax, ay, aw, ah = BOX[a]; bx, by, bw, bh = BOX[b]
    phase, row = next((n[1], n[2]) for n in NODES if n[0] == b)
    above = [BOX[n[0]] for n in NODES if n[1] == phase and n[2] == row - 1]
    gap_y = max(y + h for _, y, _, h in above) + ROW_GAP / 2
    return [(ax + aw / 2, ay + ah), (ax + aw / 2, gap_y), (bx + bw * 0.7, gap_y), (bx + bw * 0.7, by)]

SPECIAL = {("m_file", "m_drop"): loop_route, ("s_page", "m_say"): gap_route}

def label_at(pts):
    """标签放在最长一段的中点。"""
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    (x1, y1), (x2, y2) = max(segs, key=lambda s: abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1]))
    return (x1 + x2) / 2, (y1 + y2) / 2, abs(x2 - x1) < 1

def svg():
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H:.0f}" width="{W}" height="{H:.0f}" '
         f'font-family="system-ui, -apple-system, Segoe UI, PingFang SC, Noto Sans CJK SC, sans-serif" font-size="{FONT}">',
         '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
         f'<path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker></defs>',
         f'<rect width="{W}" height="{H:.0f}" fill="white"/>']
    for pk, title, sub in PHASES:
        py, ph = PHASE_Y[pk]
        o.append(f'<rect x="{GUTTER_L}" y="{py:.0f}" width="{W - 2*GUTTER_L}" height="{ph:.0f}" rx="8" fill="{PAGE}" stroke="{LINE}"/>')
        o.append(f'<text x="{GUTTER_L + 14}" y="{py + 30:.0f}" fill="{INK}" font-weight="700" font-size="15">{html.escape(title)}</text>')
        for j, ln in enumerate(wrap(sub, 20)):
            o.append(f'<text x="{GUTTER_L + 14}" y="{py + 50 + j*15:.0f}" fill="{MUTED}" font-size="10.5">{html.escape(ln)}</text>')
    for ck, label, color in COLS:
        o.append(f'<text x="{col_x(ck) + COL_W/2}" y="{TOP + 20}" text-anchor="middle" fill="{color}" font-weight="700" '
                 f'font-size="11" letter-spacing=".08em">{html.escape(label.upper())}</text>')
    for a, b, label, dashed in EDGES:
        pts = SPECIAL.get((a, b), route)(a, b)
        d = "M" + " L".join(f"{x:.0f},{y:.0f}" for x, y in pts)
        o.append(f'<path d="{d}" fill="none" stroke="{MUTED}" stroke-width="1.5" marker-end="url(#arr)"' + (' stroke-dasharray="5,4"' if dashed else "") + '/>')
        if label:
            mx, my, vertical = label_at(pts)
            if vertical:
                o.append(f'<text x="{mx:.0f}" y="{my:.0f}" text-anchor="middle" fill="{MUTED}" font-size="10.5" transform="rotate(90 {mx:.0f} {my:.0f})">{html.escape(label)}</text>')
                continue
            tw = sum(cjk_w(c) for c in label) * 5.5 + 10
            o.append(f'<rect x="{mx - tw/2:.0f}" y="{my-8:.0f}" width="{tw:.0f}" height="16" rx="3" fill="white"/>')
            o.append(f'<text x="{mx:.0f}" y="{my+3.5:.0f}" text-anchor="middle" fill="{MUTED}" font-size="10.5">{html.escape(label)}</text>')
    colors = {k: c for k, _, c in COLS}
    for nid, _p, _r, col, text, dashed in NODES:
        x, yy, w, h = BOX[nid]
        o.append(f'<rect x="{x}" y="{yy:.0f}" width="{w}" height="{h}" rx="9" fill="{CARD}" stroke="{colors[col]}" stroke-width="2"' + (' stroke-dasharray="6,4"' if dashed else "") + '/>')
        for j, ln in enumerate(LINES[nid]):
            o.append(f'<text x="{x + 14}" y="{yy + PAD_V + LINE_H * j + 12:.0f}" fill="{INK}">{html.escape(ln)}</text>')
    o.append('</svg>\n')
    return "\n".join(o)

if __name__ == "__main__":
    open(os.path.join(HERE, "product_flow.drawio"), "w", encoding="utf-8").write(drawio())
    open(os.path.join(HERE, "product_flow.svg"), "w", encoding="utf-8").write(svg())
    print(f"wrote docs/zh/product_flow.drawio and docs/zh/product_flow.svg — {len(NODES)} nodes, {len(EDGES)} edges, {W}x{H:.0f}")
