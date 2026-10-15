"""The playtest brief: what the designer wants to learn, filled in as Obsidian properties before a run.

  python3 -m playtest brief <module>      create Reports/<title> — Playtest Brief.md (if missing) and print its path

The brief's properties are the form. The report opens by restating the question and checking the results against
the targets; a plain 'python3 -m playtest run <module>' with no study uses the brief's party, level and run count.
"""
import os, re, time

FIELDS = [
    ('question', '""', 'What do you want to learn? One or two sentences, e.g. "Is the vault too deadly for a 4th-level party?"'),
    ('party', 'stock', "Who plays: 'stock' (fighter, cleric, rogue, wizard), 'stock@5x6' (level 5, six PCs), a saved party (A), or names separated by commas"),
    ('level', '""', "Party level for the stock party; blank uses the module's level"),
    ('runs', '2000', 'How many runs'),
    ('main_study', '""', "Which study answers the question; blank uses the brief's own run (or the module's first study)"),
    ('target_finish', '"50-80"', 'How often a party should get to the end, as a percentage range'),
    ('max_wipe', '20', 'The highest acceptable share of runs ending in a total party kill, in percent'),
    ('max_deaths', '1', 'The highest acceptable average PC deaths per run'),
    ('focus', '[]', 'Rooms or fights you are worried about, by room id or fight name, e.g. [T4, Docks]'),
    ('must_see', '[]', 'Rooms most parties should reach, e.g. [T4]'),
    ('must_see_share', '70', 'How many runs, in percent, should reach each must-see room'),
]

def path_for(module, folder='Reports'):
    base = re.sub(r'[\\/:*?"<>|]', '', module.title)
    return os.path.join(folder, f"{base} — Playtest Brief.md")

def create(module, folder='Reports'):
    os.makedirs(folder, exist_ok=True)
    p = path_for(module, folder)
    if os.path.exists(p): return p, False
    L = ['---', 'type: reference', 'tags: [simulation, playtest-brief, dm-eyes-only]', f"created: {time.strftime('%Y-%m-%d')}",
         'status: draft', f"summary: What the designer wants to learn from simulating {module.title}, and the targets the results are checked against."]
    for k, default, _ in FIELDS:
        if k == 'level' and module.levels: default = str(module.levels[0])
        L.append(f"{k}: {default}")
    L += ['---', '> [!question] Fill in the properties above, then run the simulation',
          f"> `python3 -m playtest run {module.slug}`, then `python3 -m playtest report {module.slug}`. The report opens with your question and checks the results against these targets.",
          '', '| Property | What to put |', '|---|---|']
    L += [f"| `{k}` | {help_} |" for k, _, help_ in FIELDS]
    open(p, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return p, True

def _val(v):
    v = v.strip()
    if v.startswith('[') and v.endswith(']'):
        return [x.strip().strip('"\'') for x in v[1:-1].split(',') if x.strip()]
    v = v.strip('"\'')
    try: return float(v) if '.' in v else int(v)
    except ValueError: return v

def load(module, folder='Reports'):
    """The brief's properties as a dict, or None if there's no brief or the question is blank."""
    p = path_for(module, folder)
    if not os.path.exists(p): return None
    t = open(p, encoding='utf-8').read()
    m = re.match(r'---\n(.*?)\n---', t, re.S)
    if not m: return None
    out = {}; key = None
    for line in m.group(1).split('\n'):
        if re.match(r'^\s+-\s', line) and key:                 # YAML list written one item per line (Obsidian does this)
            out.setdefault(key, [])
            if not isinstance(out[key], list): out[key] = []
            out[key].append(_val(line.split('-', 1)[1])); continue
        mm = re.match(r'^([\w]+):\s*(.*)$', line)
        if mm:
            key = mm.group(1); out[key] = _val(mm.group(2)) if mm.group(2).strip() else []
    return out

def target_range(b):
    t = str(b.get('target_finish') or '')
    m = re.match(r'\s*(\d+)\s*[-–]\s*(\d+)', t)
    return (int(m.group(1)) / 100, int(m.group(2)) / 100) if m else None
