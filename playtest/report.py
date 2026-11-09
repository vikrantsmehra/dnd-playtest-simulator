"""The Obsidian report for a module, built from its saved results (results/<module>/*.json).

  python3 -m playtest report <module>

Writes Reports/<title> — Simulation Data.md and Reports/<title> — Runs Map.svg in this folder. The data note is
generated in full each time: headline outcomes per study, where runs ended room by room, every encounter, every party
decision, personality, characters, the module's own numbers (MODULE.report), and standout runs with the command to
replay each one roll by roll. Write the interpretation in a separate note that links to it, so a rerun never
overwrites your words.
"""
import os, json, glob, re, statistics as st, time
from collections import Counter, defaultdict
from .mapsvg import build as build_map, place_of

P = lambda x: f"{100 * x:.1f}%"

def load_rows(slug):
    out = {}
    for f in sorted(glob.glob(os.path.join('results', slug, '*.json'))):
        d = json.load(open(f))
        if 'meta' in d: out[d['meta']['study']] = d
    return out

def pct_table(head, rows):
    out = ['| ' + ' | '.join(head) + ' |', '|' + '|'.join(['---'] * len(head)) + '|']
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return out

def outcome_class(r):
    o = r['outcome']
    if r['complete']: return 'finished'
    if o.startswith('wiped'): return 'wiped'
    if o.startswith('abandoned'): return 'abandoned'
    if o.startswith('gave up'): return 'gave up'
    return o

def encounter_table(rows):
    n = len(rows)
    agg = defaultdict(lambda: Counter())
    for r in rows:
        for name, e in r['enc'].items():
            a = agg[name]; a['runs'] += 1
            for k, v in e.items(): a[k] += v
    lines = []
    for name, a in sorted(agg.items(), key=lambda kv: -kv[1]['runs']):
        if a['runs'] < max(5, n * 0.01): continue
        tries = a['n']
        lines.append([name, P(a['runs'] / n), P(a.get('won', 0) / max(1, tries)), f"{a['rounds'] / max(1, tries):.1f}",
                      f"{a['drops'] / max(1, tries):.2f}", f"{a['deaths'] / max(1, tries):.2f}", a.get('retreats', 0)])
    return pct_table(['Encounter', 'Runs that met it', 'Won (of tries)', 'Rounds', 'Drops per fight', 'Deaths per fight', 'Retreats'], lines)

def decision_table(rows):
    n = len(rows)
    by = defaultdict(lambda: defaultdict(list))
    for r in rows:
        seen = set()
        for point, pick, _ in r['decisions']:
            if (point, pick) in seen: continue
            seen.add((point, pick)); by[point][pick].append(r['complete'])
    lines = []
    for point, picks in sorted(by.items(), key=lambda kv: -sum(len(v) for v in kv[1].values())):
        tot = sum(len(v) for v in picks.values())
        if tot < max(10, n * 0.02) or len(picks) < 2 and not point.startswith('before'): continue
        for pick, vals in sorted(picks.items(), key=lambda kv: -len(kv[1])):
            lines.append([point, pick, P(len(vals) / tot), len(vals), P(sum(vals) / len(vals))])
    return pct_table(['Decision point', 'Choice', 'Share', 'Runs', 'Finished when chosen'], lines)

def trait_table(rows):
    lines = []
    for t in ('caution', 'curiosity', 'boldness'):
        vals = [(r['traits'].get(t, 0.5), r['complete']) for r in rows if r['traits']]
        if not vals: continue
        lo = [c for v, c in vals if v < 0.37]; mid = [c for v, c in vals if 0.37 <= v < 0.63]; hi = [c for v, c in vals if v >= 0.63]
        lines.append([t, P(sum(lo) / max(1, len(lo))), P(sum(mid) / max(1, len(mid))), P(sum(hi) / max(1, len(hi)))])
    return pct_table(['Trait', 'Low', 'Middle', 'High'], lines)

SOLO = re.compile(r"^(?P<who>[^,:]+), (?P<trait>caution|curiosity|boldness) (?P<v>[0-9.]+): ")

def _nick(name):
    try:
        from roster import NICKNAMES
    except ImportError:
        NICKNAMES = {}
    return NICKNAMES.get(name, name)

def voices_lines(rows):
    """Per-member personalities (voices='loudest' or 'average'): whose voice set each party trait, how often the party
    split and the leader settled it, finish rate by leader, and who acted alone at each individual decision."""
    rs = [r for r in rows if r.get('member_traits')]
    if not rs: return []
    n = len(rs); out = [f"Each member has their own traits (rule: `{rs[0].get('voices')}`)."
                        + (" The member furthest from 0.5 speaks for the party, unless the rest clearly lean the other way; then the leader decides." if rs[0].get('voices') == 'loudest' else ''), '']
    lines = []
    for t in ('caution', 'curiosity', 'boldness'):
        how = Counter(r['voice'].get(t, {}).get('how') for r in rs)
        over = sum(1 for r in rs if r['voice'].get(t, {}).get('how') == 'leader' and r['voice'][t].get('who') != r['voice'][t].get('over'))
        lines.append([t, P(how.get('loudest', 0) / n), P((how.get('leader', 0) + how.get('split, averaged', 0)) / n), P(over / n)])
    out += pct_table(['Trait', 'Set by the loudest voice', 'Split', 'Leader overruled the loudest'], lines) + ['']
    lead = defaultdict(list)
    for r in rs:
        if r.get('leader'): lead[_nick(r['leader'])].append(r)
    if lead:
        ll = []
        for nm, g in sorted(lead.items(), key=lambda kv: -len(kv[1])):
            splits = sum(1 for r in g for v in r['voice'].values() if v.get('how') == 'leader')
            ll.append([nm, len(g), P(sum(r['complete'] for r in g) / len(g)), f"{splits / len(g):.2f}"])
        out += ['**Finished, by who led:**', ''] + pct_table(['Leader', 'Runs', 'Finished', 'Splits settled per run'], ll) + ['']
    solo = defaultdict(lambda: defaultdict(list))
    for r in rs:
        for point, pick, why in r['decisions']:
            m = SOLO.match(why or '')
            if m: solo[point][(m['who'], pick)].append(r['complete'])
    for point, d in solo.items():
        tot = sum(len(v) for v in d.values())
        sl = [[who, pick, len(v), P(len(v) / tot), P(sum(v) / len(v))] for (who, pick), v in sorted(d.items(), key=lambda kv: -len(kv[1]))]
        out += [f"**Who decided alone: {point}**", ''] + pct_table(['Who', 'Choice', 'Runs', 'Share', 'Finished'], sl) + ['']
    return out

def character_lines(rows):
    teams = Counter(tuple(r['team']) for r in rows)
    if len(teams) < 4: return []
    names = sorted({n for r in rows for n in r['team']})
    base = sum(r['complete'] for r in rows) / len(rows)
    lines = []
    for nm in names:
        w = [r['complete'] for r in rows if nm in r['team']]; wo = [r['complete'] for r in rows if nm not in r['team']]
        if len(w) < 30 or len(wo) < 30: continue
        lines.append([nm, len(w), P(sum(w) / len(w)), P(sum(wo) / len(wo)), f"{100 * (sum(w) / len(w) - sum(wo) / len(wo)):+.1f}"])
    out = ['**With and without each character:**', ''] + pct_table(['Character', 'Runs with', 'Finished with', 'Without', 'Difference (points)'],
                                                                     sorted(lines, key=lambda l: -float(l[4])))
    comp = defaultdict(list)
    for r in rows: comp[' + '.join(sorted(r['team']))].append(r['complete'])
    comp = {k: v for k, v in comp.items() if len(v) >= 25}
    if comp:
        ranked = sorted(comp.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))
        out += ['', f"**Best party:** {ranked[0][0]}, {P(sum(ranked[0][1]) / len(ranked[0][1]))} over {len(ranked[0][1])} runs.  ",
                f"**Worst party:** {ranked[-1][0]}, {P(sum(ranked[-1][1]) / len(ranked[-1][1]))} over {len(ranked[-1][1])} runs."]
    return out

def standouts(slug, study, rows, k=4):
    """Runs far from the average: a win against the odds, an early collapse, the bloodiest finish, the longest grind."""
    picks = []
    done = [r for r in rows if r['complete']]
    lost = [r for r in rows if not r['complete']]
    if done:
        r = max(done, key=lambda r: (len(r['dead']) + r['captures'] + r['retreats'], -r['seed']))
        picks.append(('Finished the hard way', r, f"{len(r['dead'])} dead, {r['captures']} captures, {r['retreats']} retreats along the way"))
        r = min(done, key=lambda r: (sum(x[1] for x in []) + len(r['drops']), r['seed']))
        picks.append(('The cleanest finish', r, f"{len(r['drops'])} PC drops in the whole run"))
    if lost:
        r = min(lost, key=lambda r: (len(r['route']), r['seed']))
        picks.append(('The earliest collapse', r, f"ended at {r['fail']} after {len(r['route'])} rooms"))
    if rows:
        r = max(rows, key=lambda r: (sum(e.get('rounds', 0) for e in r['enc'].values()), -r['seed']))
        picks.append(('The longest grind', r, f"{sum(e.get('rounds', 0) for e in r['enc'].values())} rounds of combat, {r['outcome']}"))
    out = []
    for title, r, why in picks[:k]:
        out += [f"- **{title}** ({why}). Party: {', '.join(r['team'])}. Seed {r['seed']}: "
                f"`python3 -m playtest replay {slug} {study} {r['seed']}`"]
    return out

def write_report(slug, out=None):
    from .batch import load
    module = load(slug)
    data = load_rows(slug)
    if not data: return f"no results in results/{slug}/; run some studies first"
    order = [s for s in module.studies if s in data] + [s for s in data if s not in module.studies]
    folder = out or 'Reports'; os.makedirs(folder, exist_ok=True)
    title = module.title.split(' (')[0] if '(' in module.title and len(module.title) > 40 else module.title
    base = re.sub(r'[\\/:*?"<>|]', '', module.title)
    svg = f"{base} — Runs Map.svg"
    studies = [(data[s]['meta']['label'], data[s]['meta']['desc'], data[s]['rows']) for s in order]
    if module.map_groups:
        panels = [(t, sub, [r for s in ss if s in data for r in data[s]['rows']]) for t, sub, ss in module.map_groups]
        panels = [p for p in panels if p[2]]
    else: panels = studies
    build_map(module, panels, os.path.join(folder, svg))
    L = ['---', 'type: reference', 'tags: [simulation, dm-eyes-only, playtest]', f"created: {time.strftime('%Y-%m-%d')}", 'status: active',
         f"summary: Generated playtest data for {module.title}: {sum(len(s[2]) for s in studies):,} simulated runs across {len(studies)} studies. "
         'Regenerated by the Playtest Simulator; write interpretation in a separate note.', '---',
         '> [!warning] DM Eyes Only #dm-eyes-only',
         f"> Generated by `python3 -m playtest report {slug}` on {time.strftime('%Y-%m-%d %H:%M')}. Don't edit by hand: the next run replaces this note.",
         '', f"Source: {module.source}" if module.source else '', '']
    from .brief import load as load_brief
    from .summary import summarize
    br = load_brief(module, folder)
    main, top = summarize(module, data, order, br)
    L += top
    if not br: L += [f"*No playtest brief yet. `python3 -m playtest brief {slug}` makes one, so this report can answer a specific question.*", '']
    L += ['## Headline', '']
    rows = []
    for s in order:
        d = data[s]; rs = d['rows']; n = len(rs); oc = Counter(outcome_class(r) for r in rs)
        others = ', '.join(f"{k} {P(v / n)}" for k, v in oc.most_common() if k not in ('finished', 'wiped'))
        rows.append([f"**{d['meta']['label']}**", d['meta']['desc'], f"{n:,}", P(oc['finished'] / n), P(oc['wiped'] / n), others or '—',
                     f"{st.mean(len(r['dead']) for r in rs):.2f}"])
    L += pct_table(['Study', 'Who and what', 'Runs', 'Finished', 'Wiped', 'Other endings', 'PC deaths per run'], rows)
    L += ['', 'Treat differences under about 3 points as noise at 1,000 runs (2 points at 4,500).', '',
          '## Room by room', '', f"![[{svg}]]", '']
    places = list(module.nodes) + list((module.places or {}).keys())
    head = ['Room'] + [data[s]['meta']['label'] for s in order]
    trows = []
    for k in places + ['other']:
        cells = []; any_ = False
        for s in order:
            rs = data[s]['rows']; n = len(rs)
            e = sum(1 for r in rs if not r['complete'] and r['fail_loc'] and place_of(module, r['fail_loc']) == k)
            dd = sum(1 for r in rs for room, _ in r['deaths'] if place_of(module, room) == k)
            any_ = any_ or e or dd
            cells.append(f"{P(e / n)} / {dd:,}")
        if any_:
            nm = module.nodes[k].name if k in module.nodes else (module.places or {}).get(k, (0, 0, k))[2] if k != 'other' else 'elsewhere'
            trows.append([nm] + cells)
    L += ['Each cell: share of runs that ended there / PC deaths there (including deaths in runs that went on to finish).', '']
    L += pct_table(head, trows)
    for s in order:
        d = data[s]; rs = d['rows']
        L += ['', f"## {d['meta']['label']}", '', f"*{d['meta']['desc']}. {len(rs):,} runs, seed {d['meta']['seed']}, "
              f"settings: {', '.join(f'{k}={v}' for k, v in d['meta']['cfg'].items() if k in (module.studies[s].cfg if s in module.studies else {})) or 'the module as written'}.*", '']
        L += ['### Encounters', ''] + encounter_table(rs) + ['']
        dt = decision_table(rs)
        if len(dt) > 2: L += ['### Party decisions', ''] + dt + ['']
        L += ['### Personality', '', 'Share of runs finished, by the party\'s combined trait (low < 0.37 ≤ middle < 0.63 ≤ high).', ''] + trait_table(rs) + ['']
        vl = voices_lines(rs)
        if vl: L += ['### Voices, leaders and solo choices', ''] + vl
        ch = character_lines(rs)
        if ch: L += ['### Characters', ''] + ch + ['']
        if getattr(module, 'report', None):
            extra = module.report(rs)
            if extra: L += ['### Module numbers', ''] + extra + ['']
        L += ['### Standout runs', ''] + standouts(slug, s, rs) + ['']
    L += ['## Reproducing', '', '```bash', 'cd <the Playtest Simulator folder>',
          f"python3 -m playtest run {slug} all", f"python3 -m playtest report {slug}", '```', '',
          'Seeds reproduce runs only with the same code: once any file changes, the same seed plays out differently.']
    path = os.path.join(folder, f"{base} — Simulation Data.md")
    open(path, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return f"wrote {path} and {os.path.join(folder, svg)}"
