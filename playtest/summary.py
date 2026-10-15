"""The top of the report: what happened in plain words, and what a designer should look at first.

Everything here is worked out from the results by fixed rules, so it reads the same way every time:
  High    the party dies too often (or more than the brief allows), one room ends a big share of runs, a fight kills,
          the finish rate misses the brief's target
  Medium  content most parties never see, a setting that swings the result, a decision strongly tied to the outcome
  Low     fights that never threaten anyone, a personality the module rewards or punishes
"""
import statistics as st
from collections import Counter, defaultdict
from .mapsvg import place_of
from .brief import target_range

P = lambda x: f"{100 * x:.0f}%"

def _name(module, k):
    if k in module.nodes: return module.nodes[k].name
    return (module.places or {}).get(k, (0, 0, k))[2] if k != 'other' else 'elsewhere'

def facts(module, rows):
    n = len(rows)
    f = dict(n=n, finish=sum(r['complete'] for r in rows) / n,
             wipe=sum(1 for r in rows if r['outcome'].startswith('wiped')) / n,
             deaths=st.mean(len(r['dead']) for r in rows))
    f['ended'] = Counter(place_of(module, r['fail_loc']) for r in rows if not r['complete'] and r['fail_loc'])
    f['reached'] = {k: sum(1 for r in rows if k in r['route']) / n for k in module.nodes}
    enc = defaultdict(Counter)
    for r in rows:
        for name, e in r['enc'].items():
            enc[name]['runs'] += 1
            for k, v in e.items(): enc[name][k] += v
    f['enc'] = {k: dict(met=v['runs'] / n, won=v.get('won', 0) / max(1, v['n']), deaths=v['deaths'] / max(1, v['n']),
                        drops=v['drops'] / max(1, v['n']), rounds=v['rounds'] / max(1, v['n']), tries=v['n'])
                for k, v in enc.items() if v['runs'] >= max(5, 0.02 * n)}
    return f

def decisions(rows):
    n = len(rows); by = defaultdict(lambda: defaultdict(list))
    for r in rows:
        seen = set()
        for point, pick, _ in r['decisions']:
            if (point, pick) in seen or point.startswith('before'): continue
            seen.add((point, pick)); by[point][pick].append(r['complete'])
    out = []
    for point, picks in by.items():
        if 'where next' in point: continue                   # routes follow the dungeon's gates more than the party's judgement
        big = {k: v for k, v in picks.items() if len(v) >= max(40, 0.03 * n)}
        if len(big) < 2: continue
        rates = sorted(((sum(v) / len(v), k, len(v)) for k, v in big.items()), reverse=True)
        if rates[0][0] - rates[-1][0] >= 0.15: out.append((point, rates[0], rates[-1]))
    return sorted(out, key=lambda x: -(x[1][0] - x[2][0]))

def summarize(module, data, order, brief=None):
    """Returns (main study name, Markdown lines)."""
    main = None
    if brief and brief.get('main_study') and brief['main_study'] in data: main = brief['main_study']
    elif 'brief' in data: main = 'brief'
    else: main = order[0]
    rows = data[main]['rows']; label = data[main]['meta']['label']
    f = facts(module, rows)
    L = []
    if brief and brief.get('question'):
        L += ['## What you wanted to learn', '', f"> {brief['question']}", '',
              f"Answered from **{label}** ({f['n']:,} runs). The targets from the brief are checked under Priority items.", '']
    # ---- what happened
    top = f['ended'].most_common(3)
    s1 = (f"Across {f['n']:,} runs of *{label}*, the party finished {P(f['finish'])} of the time. {P(f['wipe'])} of runs "
          f"ended with the whole party dead, and on average {f['deaths']:.1f} PCs died per run.")
    s2 = ''
    if top:
        top = [(k, v) for k, v in top if v / f['n'] >= 0.01]
        parts = [f"{_name(module, k)}, {P(v / f['n'])} of all runs" for k, v in top]
        if parts: s2 = "Runs that failed mostly ended at " + ('; '.join(parts[:-1]) + '; and ' + parts[-1] if len(parts) > 1 else parts[0]) + '.'
    deadly = sorted(f['enc'].items(), key=lambda kv: -(1 - kv[1]['won']) * kv[1]['met'])
    s3 = ''
    if deadly and (1 - deadly[0][1]['won']) > 0.05:
        k, e = deadly[0]
        s3 = (f"The hardest fight was {k}: {P(e['met'])} of runs reached it and the party won {P(e['won'])} of its attempts, "
              f"with {e['drops']:.1f} PCs dropping per fight.")
    unseen = sorted(((k, v) for k, v in f['reached'].items() if v < 0.6 and not module.nodes[k].goal), key=lambda kv: kv[1])
    s4 = ''
    if unseen:
        s4 = 'Some content went unseen: ' + ', '.join(f"{_name(module, k)} was reached in {P(v)} of runs" for k, v in unseen[:3]) + '.'
    L += ['## What happened', '', ' '.join(x for x in (s1, s2, s3, s4) if x), '']
    # ---- priority items
    items = []
    if brief is not None and not brief.get('question'): brief = None      # an unfilled brief sets no targets
    rng = target_range(brief) if brief else None
    max_wipe = (brief.get('max_wipe') / 100) if brief and isinstance(brief.get('max_wipe'), (int, float)) else 0.20
    max_deaths = brief.get('max_deaths') if brief and isinstance(brief.get('max_deaths'), (int, float)) else None
    if rng and not (rng[0] <= f['finish'] <= rng[1]):
        side = 'too hard' if f['finish'] < rng[0] else 'too easy'
        items.append(('High', f"**Finish rate is outside your target.** Parties finished {P(f['finish'])}; the brief asks for "
                              f"{P(rng[0])}–{P(rng[1])}. The module plays {side} for this party."))
    if f['wipe'] > max_wipe:
        items.append(('High', f"**Total party kills: {P(f['wipe'])} of runs**, above the {P(max_wipe)} {'the brief allows' if brief else 'mark worth worrying about'}. "
                              f"Look at where they happen (below) before anything else."))
    if max_deaths is not None and f['deaths'] > max_deaths:
        items.append(('High', f"**{f['deaths']:.1f} PC deaths per run**, above the brief's {max_deaths}."))
    for k, v in f['ended'].most_common():
        if v / f['n'] >= 0.12:
            items.append(('High', f"**{_name(module, k)} ends {P(v / f['n'])} of all runs.** It's the single biggest wall in the module; "
                                  f"check whether that's the intended climax or an accident of numbers."))
    for k, e in f['enc'].items():
        if e['deaths'] >= 0.4 and e['tries'] >= 20:
            items.append(('High', f"**{k} kills.** {e['deaths']:.2f} PC deaths per attempt, won {P(e['won'])} of the time."))
    must = (brief or {}).get('must_see') or []
    share = ((brief or {}).get('must_see_share') or 70) / 100
    for k in must:
        if k in f['reached'] and f['reached'][k] < share:
            items.append(('High', f"**{_name(module, k)} is a must-see, but only {P(f['reached'][k])} of runs reach it** "
                                  f"(the brief asks for {P(share)}). Check what gates it."))
    for k in (brief or {}).get('focus') or []:
        if k in module.nodes:
            e_ = f['ended'].get(k, 0) / f['n']; rc = f['reached'].get(k, 0)
            items.append(('Focus', f"**{_name(module, k)}** (your focus): reached in {P(rc)} of runs, ended {P(e_)} of all runs."))
        else:
            hit = [(name, e) for name, e in f['enc'].items() if k.lower() in name.lower()]
            for name, e in hit[:2]:
                items.append(('Focus', f"**{name}** (your focus): met in {P(e['met'])} of runs, won {P(e['won'])} of attempts, "
                                       f"{e['drops']:.1f} drops and {e['deaths']:.2f} deaths per fight, {e['rounds']:.1f} rounds."))
    for k, v in sorted(f['reached'].items(), key=lambda kv: kv[1]):
        if v < 0.5 and k not in must and not module.nodes[k].goal:
            items.append(('Medium', f"**{_name(module, k)} is reached in only {P(v)} of runs.** If it matters to the story, signpost it or loosen what gates it."))
    levers = []
    for s in order:
        if s == main: continue
        other = data[s]['rows']; fo = sum(r['complete'] for r in other) / len(other)
        if abs(fo - f['finish']) >= 0.05: levers.append((fo - f['finish'], data[s]['meta']['label'], fo))
    if levers:
        levers.sort(key=lambda x: -abs(x[0]))
        items.append(('Medium', f"**Other studies move the finish rate** (from {P(f['finish'])} in {label}): " +
                                '; '.join(f"{lb} {P(fo)} ({100 * d:+.0f} points)" for d, lb, fo in levers[:6]) + '.'))
    for point, best, worst in decisions(rows)[:3]:
        items.append(('Medium', f"**{point}**: parties that chose '{best[1]}' finished {P(best[0])}, against {P(worst[0])} for "
                                f"'{worst[1]}'. Tied to the outcome, though not always the cause (a choice can follow from how the run was already going)."))
    easy = [k for k, e in f['enc'].items() if e['won'] >= 0.99 and e['drops'] < 0.1 and e['met'] >= 0.3]
    if easy:
        items.append(('Low', f"**Fights that never threaten the party:** {', '.join(easy[:4])}. Fine as breathers; trim them if pacing is tight."))
    tr = []
    for t in ('caution', 'curiosity', 'boldness'):
        lo = [r['complete'] for r in rows if r['traits'].get(t, 0.5) < 0.37]; hi = [r['complete'] for r in rows if r['traits'].get(t, 0.5) >= 0.63]
        if len(lo) >= 50 and len(hi) >= 50:
            d = sum(hi) / len(hi) - sum(lo) / len(lo)
            if abs(d) >= 0.10: tr.append((t, d, sum(lo) / len(lo), sum(hi) / len(hi)))
    for t, d, lo, hi in tr:
        items.append(('Low', f"**The module {'rewards' if d > 0 else 'punishes'} {t}.** Low-{t} parties finished {P(lo)}, high-{t} parties {P(hi)}."))
    order_ = {'High': 0, 'Focus': 1, 'Medium': 2, 'Low': 3}
    items.sort(key=lambda x: order_[x[0]])
    L += ['## Priority items', '']
    if not items: L += ['Nothing stands out: no wall, no wasted content, no lever bigger than ten points.', '']
    for sev, text in items: L.append(f"- **{sev}.** {text}")
    L.append('')
    return main, L
