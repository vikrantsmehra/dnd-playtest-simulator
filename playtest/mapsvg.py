"""The room map: one panel per study, every room coloured by the share of runs that ended there, with PC deaths.

Rooms are placed by the module's node coordinates (x, y), or laid out by distance from the start if it has none.
A module's extra places (the road there, a session break) can be listed in MODULE.places as {label: (x, y, name)}.
"""
import re
from collections import Counter
from xml.sax.saxutils import escape

def place_of(module, label):
    """Which room (or extra place) a run's location label belongs to."""
    if not label: return None
    label = str(label)
    if label in module.nodes: return label
    low = {k.lower(): k for k in module.nodes}
    if label.lower() in low: return low[label.lower()]
    for k, v in (module.places or {}).items():
        if label.lower().startswith(k.lower()): return k
    for nid, n in module.nodes.items():
        rl = getattr(n, 'revisit_label', None)
        if rl and label.lower().startswith(rl.split(' (')[0].lower()): return nid
    head = re.split(r'[\s:(]', label)[0]
    if head in module.nodes: return head
    return 'other'

def positions(module):
    pos = {}
    if all(n.x is not None for n in module.nodes.values()):
        for nid, n in module.nodes.items(): pos[nid] = (n.x, n.y)
    else:                                                 # layered by distance from the start
        dist = {module.start: 0}; todo = [module.start]
        while todo:
            a = todo.pop(0)
            for e in module.adj(a):
                b = e.other(a)
                if b not in dist: dist[b] = dist[a] + 1; todo.append(b)
        layers = {}
        for nid in module.nodes:
            layers.setdefault(dist.get(nid, max(dist.values()) + 1), []).append(nid)
        for d, ns in layers.items():
            for i, nid in enumerate(ns): pos[nid] = (d * 120, i * 70)
    for k, (x, y, _) in (module.places or {}).items(): pos[k] = (x, y)
    return pos

def color(share, mx):
    if share <= 0: return '#F3F1EA', '#2C2C2A'
    t = min(1.0, share / mx) ** 0.6 if mx else 0
    stops = [(0.0, (250, 236, 200)), (0.45, (242, 166, 90)), (0.75, (214, 92, 60)), (1.0, (150, 30, 40))]
    c = stops[-1][1]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if t <= b:
            u = (t - a) / (b - a); c = tuple(round(ca[i] + (cb[i] - ca[i]) * u) for i in range(3)); break
    lum = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    return '#%02X%02X%02X' % c, ('#FFFFFF' if lum < 140 else '#2C2C2A')

def build(module, studies, path):
    """studies: [(title, subtitle, rows)]"""
    pos = positions(module)
    xs = [p[0] for p in pos.values()]; ys = [p[1] for p in pos.values()]
    W, H = 92, 38
    span_x = max(xs) - min(xs) + W + 20; span_y = max(ys) - min(ys) + H + 20
    sc = min(1.0, 980 / span_x)
    pw = span_x * sc; ph = span_y * sc + 50
    names = {nid: n.name for nid, n in module.nodes.items()}
    names.update({k: v[2] for k, v in (module.places or {}).items()})
    mx = 0
    tallies = []
    for title, sub, rows in studies:
        n = max(1, len(rows))
        ended = Counter(place_of(module, r['fail_loc']) for r in rows if r['fail_loc'] and not r['complete'])
        died = Counter(place_of(module, room) for r in rows for room, _ in r['deaths'])
        tallies.append((ended, died))
        if ended: mx = max(mx, max(ended.values()) / n)
    mx = min(max(mx, 0.05), 0.30)
    Wt = max(pw + 40, 640); Ht = 70 + ph * len(studies) + 60
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {Wt:.0f} {Ht:.0f}" width="{Wt:.0f}" height="{Ht:.0f}" '
         f'font-family="system-ui, -apple-system, Segoe UI, Helvetica, Arial, sans-serif">',
         f'<title>{escape(module.title)}: where simulated runs ended</title>',
         f'<rect width="{Wt:.0f}" height="{Ht:.0f}" fill="#FBFAF6"/>',
         f'<text x="15" y="24" font-size="15" font-weight="700" fill="#2C2C2A">{escape(module.title)}: where simulated runs ended</text>',
         '<text x="15" y="40" font-size="9" fill="#5F5E5A">Each box is a room. Colour = share of all runs that ended there (wiped, gave up, abandoned).</text>',
         '<text x="15" y="52" font-size="9" fill="#5F5E5A">"Deaths" counts every PC death in the room, including deaths in runs that went on to finish.</text>']
    for i, ((title, sub, rows), (ended, died)) in enumerate(zip(studies, tallies)):
        n = max(1, len(rows)); done = sum(r['complete'] for r in rows)
        oy = 80 + i * ph; ox = 20
        s.append(f'<g transform="translate({ox},{oy})">')
        s.append(f'<text x="0" y="-8" font-size="12" font-weight="600" fill="#2C2C2A">{escape(title)}</text>')
        s.append(f'<text x="0" y="5" font-size="8" fill="#5F5E5A">{escape(sub)} · {len(rows):,} runs · finished {done / n:.1%}</text>')
        def xy(k):
            x, y = pos[k]; return (x - min(xs)) * sc, 18 + (y - min(ys)) * sc
        for e in module.edges:
            if e.a not in pos or e.b not in pos: continue
            (x1, y1), (x2, y2) = xy(e.a), xy(e.b)
            dash = ' stroke-dasharray="3 2"' if (e.gate or e.lock) else ''
            s.append(f'<line x1="{x1 + W * sc / 2:.1f}" y1="{y1 + H * sc / 2:.1f}" x2="{x2 + W * sc / 2:.1f}" y2="{y2 + H * sc / 2:.1f}" '
                     f'stroke="#B8B4A8" stroke-width="0.8"{dash}/>')
        for k in pos:
            x, y = xy(k)
            e = ended.get(k, 0); d = died.get(k, 0)
            fill, ink = color(e / n, mx)
            label = escape(names.get(k, k))
            if len(label) > 26: label = label[:25] + '…'
            bh = H * sc; fs = min(6.6, bh / 4.3)
            s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{W * sc:.1f}" height="{bh:.1f}" rx="4" fill="{fill}" stroke="#8C887C" stroke-width="0.5"/>')
            s.append(f'<text x="{x + 3:.1f}" y="{y + bh * 0.31:.1f}" font-size="{fs:.1f}" font-weight="600" fill="{ink}">{label}</text>')
            s.append(f'<text x="{x + 3:.1f}" y="{y + bh * 0.60:.1f}" font-size="{fs:.1f}" fill="{ink}">ended {100 * e / n:.1f}%</text>')
            s.append(f'<text x="{x + 3:.1f}" y="{y + bh * 0.88:.1f}" font-size="{fs:.1f}" fill="{ink}">{d:,} deaths</text>')
        s.append('</g>')
    ly = Ht - 34
    s.append(f'<text x="20" y="{ly - 4}" font-size="8" fill="#5F5E5A">Share of runs ended in the room (dashed lines: doors that need a key, a lock or a condition)</text>')
    for j in range(6):
        sh = mx * j / 5
        f, _ = color(sh if j else 0, mx)
        s.append(f'<rect x="{20 + j * 52}" y="{ly}" width="50" height="12" fill="{f}" stroke="#8C887C" stroke-width="0.4"/>')
        s.append(f'<text x="{20 + j * 52 + 25}" y="{ly + 22}" font-size="7" text-anchor="middle" fill="#5F5E5A">{100 * sh:.0f}%{"+" if j == 5 else ""}</text>')
    s.append('</svg>')
    open(path, 'w', encoding='utf-8').write('\n'.join(s))
    return path
