"""Party personality and choices.

Each run draws three traits (0-1): caution, curiosity, boldness. At each branch the party scores its options from what
it can know in-world (its resources, what a room shows on entry, what the module signposts) and takes the best, with a
little noise so near-ties go either way. Every choice is logged in run.decisions.
"""
import os, json
from .dice import R, log

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROFILES = None
def profiles():
    """Per-character personality (roster/personality.json): caution, curiosity, boldness from 0 to 1, with the
    backstory and play that justify them."""
    global _PROFILES
    if _PROFILES is None:
        p = os.path.join(ROOT, 'roster', 'personality.json')
        raw = json.load(open(p)) if os.path.exists(p) else {}
        _PROFILES = {}
        for k, v in raw.items():
            if k.startswith('_'): continue
            for name in [k] + v.get('aliases', []): _PROFILES[name] = v
    return _PROFILES

def clamp(x, lo=0.0, hi=1.0): return max(lo, min(hi, x))

def draw_traits():
    caution = R.uniform(0.1, 0.9)
    return dict(caution=caution, curiosity=R.uniform(0.1, 0.9), boldness=clamp(1 - caution + R.gauss(0, 0.15), 0.05, 0.95))

def party_traits(run):
    """The party's personality for this run.

    setting traits='profile' (default): if every PC has a profile, the party is the average of its members, nudged a
    little each run (a table's mood varies night to night). Otherwise, and with traits='random', each trait is drawn at
    random, which is what the stock party uses. traits={'caution': 0.8, ...} fixes them, for 'what if' studies."""
    mode = run.cfg.get('traits', 'profile')
    if isinstance(mode, dict):
        return {k: clamp(float(mode.get(k, 0.5))) for k in ('caution', 'curiosity', 'boldness')}
    prof = profiles()
    ps = [prof.get(p.name) or prof.get(getattr(p, 'sheet_key', '')) for p in run.pcs]
    if mode == 'random' or not ps or not all(ps):
        return draw_traits()
    out = {}
    for k in ('caution', 'curiosity', 'boldness'):
        out[k] = clamp(sum(x[k] for x in ps) / len(ps) + R.gauss(0, 0.07), 0.05, 0.95)
    return out

def res_score(run):
    """One number for how well supplied the party is: HP counts most, then spell slots, then hit dice."""
    hp, sl, hd = run.resources()
    return 0.5 * hp + 0.3 * sl + 0.2 * hd

def choose(run, point, options):
    """options: {name: (score, reason)}. Picks the best score after a little noise."""
    scored = {k: v[0] + R.gauss(0, 0.08) for k, v in options.items()}
    pick = max(scored, key=scored.get)
    run.decisions.append((point, pick, options[pick][1]))
    log(f"  [decision] {point}: {pick} ({options[pick][1]}; " + ', '.join(f'{k} {v[0]:.2f}' for k, v in options.items()) + ")")
    return pick

def traits(run):
    t = run.traits
    return t['caution'], t['curiosity'], t['boldness']
