"""Finding monsters by name: the module's own stat blocks first, then the 5e SRD.

  spec('ghoul')                       the SRD ghoul's spec
  spawn('Storm-Kept Skeleton', 3)     three Creatures, numbered, from the module's bestiary or the SRD
  parse_group('skeleton x4, ghast')   [('skeleton', 4), ('ghast', 1)]
  difficulty(monsters, party)         the DMG's easy / medium / hard / deadly for this party, and the engine importance

A module adds stat blocks with add_text() (an Obsidian or PDF stat block), add_variant() ('use the X stat block, with
these changes') or add_spec(). Names match without case, articles or plurals.
"""
import os, re, json
from .statblock import from_srd, from_text, variant, split_blocks, CR_XP
from .brain import build

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRD_PATH = os.path.join(HERE, 'monsters', 'srd', '5e-SRD-Monsters.json')
# A campaign's own stat blocks: every note in this folder that reads as a stat block is available to every module.
# Set it in local.json ({"statblocks": "/path/to/folder"}, kept out of git) or the PLAYTEST_STATBLOCKS variable.
def _local():
    p = os.path.join(HERE, 'local.json')
    return json.load(open(p)) if os.path.exists(p) else {}
CAMPAIGN = os.environ.get('PLAYTEST_STATBLOCKS') or _local().get('statblocks', '')
_SRD = None
_CAMP = None
LOCAL = {}          # name key -> spec, filled by the active module

def key(name):
    k = name.lower().strip()
    k = re.sub(r'^(the|a|an)\s+', '', k)
    k = re.sub(r"[^a-z0-9' ]", ' ', k)
    return re.sub(r'\s+', ' ', k).strip()

def _srd():
    global _SRD
    if _SRD is None:
        _SRD = {}
        if os.path.exists(SRD_PATH):
            for js in json.load(open(SRD_PATH)):
                _SRD[key(js['name'])] = js
                _SRD.setdefault(key(js['index'].replace('-', ' ')), js)
    return _SRD

def load_folder(folder):
    """Every Markdown note in a folder that parses as a stat block, keyed by its title, the part of the title before
    a comma, and the file name."""
    out = {}
    if not os.path.isdir(folder): return out
    for f in sorted(os.listdir(folder)):
        if not f.endswith('.md'): continue
        text = open(os.path.join(folder, f), encoding='utf-8').read()
        if not re.search(r'(?:Armor Class|\*\*AC\*\*|\bAC\b)', text): continue
        try: s = from_text(text)
        except Exception: continue
        if s['hp'] <= 1: continue
        stem = re.sub(r'\s*\(.*?\)\s*$', '', f[:-3])
        for nm in {s['name'], s['name'].split(',')[0], stem}: out[key(nm)] = s
    return out

def campaign():
    global _CAMP
    if _CAMP is None: _CAMP = load_folder(CAMPAIGN)
    return _CAMP

def find(name):
    k = key(name)
    for cand in (k, k[:-1] if k.endswith('s') else None, k[:-2] if k.endswith('es') else None, k.replace('ves', 'f')):
        if not cand: continue
        if cand in LOCAL: return LOCAL[cand]
        if cand in campaign(): return campaign()[cand]
        js = _srd().get(cand)
        if js is not None:
            if '_spec' not in js: js['_spec'] = from_srd(js)
            return js['_spec']
    return None

def spec(name):
    s = find(name)
    if s is None:
        raise KeyError(f"no stat block for '{name}': add it to the module (add_text / add_variant), or check the spelling"
                       + ('' if os.path.exists(SRD_PATH) else ' (the SRD file monsters/srd/5e-SRD-Monsters.json is missing)'))
    return s

def add_spec(s, name=None):
    LOCAL[key(name or s['name'])] = s; return s

def add_text(text, name=None):
    """One or more stat blocks as text. Returns the specs."""
    out = []
    for blk in split_blocks(text) if name is None else [text]:
        s = from_text(blk, name)
        out.append(add_spec(s))
    return out

def add_variant(base, name, **changes):
    return add_spec(variant(spec(base), name, **changes))

def clear_local():
    LOCAL.clear()

def parse_group(text):
    """'skeleton x4, 2 ghouls, ghast' -> [('skeleton', 4), ('ghoul', 2), ('ghast', 1)]"""
    out = []
    items = text if isinstance(text, (list, tuple)) else re.split(r',|;|\band\b', text)
    for it in items:
        if isinstance(it, tuple): out.append(it); continue
        it = it.strip()
        if not it: continue
        m = re.match(r'(.+?)\s*[x×]\s*(\d+)$', it) or re.match(r'(\d+)\s*[x×]?\s+(.+)$', it)
        if m:
            a, b = m.groups()
            out.append((b, int(a)) if a.isdigit() else (a, int(b)))
        else:
            out.append((it, 1))
    return out

def spawn(name, n=1, hp_mode='avg'):
    s = spec(name)
    if n == 1: return [build(s, s['name'], hp_mode)]
    return [build(s, f"{s['name']} {i + 1}", hp_mode) for i in range(n)]

def group(text, hp_mode='avg'):
    out = []
    for nm, n in parse_group(text): out += spawn(nm, n, hp_mode)
    return out

# ---------------- encounter difficulty (DMG chapter 3) ----------------
THRESH = {1: (25, 50, 75, 100), 2: (50, 100, 150, 200), 3: (75, 150, 225, 400), 4: (125, 250, 375, 500), 5: (250, 500, 750, 1100),
          6: (300, 600, 900, 1400), 7: (350, 750, 1100, 1700), 8: (450, 900, 1400, 2100), 9: (550, 1100, 1600, 2400),
          10: (600, 1200, 1900, 2800), 11: (800, 1600, 2400, 3600), 12: (1000, 2000, 3000, 4500), 13: (1100, 2200, 3400, 5100),
          14: (1250, 2500, 3800, 5700), 15: (1400, 2800, 4300, 6400), 16: (1600, 3200, 4800, 7200), 17: (2000, 3900, 5900, 8800),
          18: (2100, 4200, 6300, 9500), 19: (2400, 4900, 7300, 10900), 20: (2800, 5700, 8500, 12700)}
MULT = [(1, 1), (2, 1.5), (6, 2), (10, 2.5), (14, 3), (999, 4)]
STEPS = [0.5, 1, 1.5, 2, 2.5, 3, 4, 5]

def difficulty(mons, pcs):
    """Returns (label, adjusted XP, importance) for these monsters against these PCs."""
    xp = sum(getattr(m, 'xp', 0) or CR_XP.get(getattr(m, 'cr', 0), 0) for m in mons)
    n = len(mons)
    i = next(j for j, (cap, _) in enumerate(MULT) if n <= cap)
    if len(pcs) < 3: i = min(i + 1, len(MULT) - 1)
    mult = MULT[i][1]
    if len(pcs) >= 6: mult = STEPS[max(0, STEPS.index(mult) - 1)]
    adj = xp * mult
    th = [sum(THRESH[min(20, max(1, p.level))][k] for p in pcs) for k in range(4)]
    label = 'trivial' if adj < th[0] else 'easy' if adj < th[1] else 'medium' if adj < th[2] else 'hard' if adj < th[3] else 'deadly'
    boss = any(getattr(m, 'leg_n', 0) for m in mons) or (n <= 2 and label == 'deadly')
    imp = 'boss' if boss else {'trivial': 'minor', 'easy': 'minor', 'medium': 'normal', 'hard': 'major', 'deadly': 'major'}[label]
    if boss:
        for m in mons:
            if getattr(m, 'leg_n', 0) or n == 1: m.tags.add('boss')
    return label, adj, imp
