"""Party personality and choices.

Every party member has three traits (0-1): caution, curiosity, boldness. At each branch the party scores its options
from what it can know in-world (its resources, what a room shows on entry, what the module signposts) and takes the
best, with a little noise so near-ties go either way. Every choice is logged in run.decisions.

How the members' traits combine into the party's (setting `voices`):
  'loudest'  the member furthest from 0.5 speaks for the party, unless the rest clearly lean the other way (their
             average at least SPLIT past 0.5 on the far side). That's a split, and the leader settles it with their
             own score (setting `leader`: 'random', the default, draws one member per run; 'none' averages instead;
             or name a character). The default for the stock party and any party without personality profiles.
  'average'  the plain average of the members.
  'party'    the original behaviour: one draw for the whole party (or, when every member has a profile, their
             average, nudged a little each run). The default for a profiled party, and whenever `traits` is set to
             'random' or to fixed values. It uses the random stream exactly as before, so old seeds replay unchanged.

Group or individual? A group choice uses traits(run), the party's combined score. A choice one person makes alone
names who acts with actor() and scores it with traits(run, who); the log then names them. Under voices='party' an
individual choice falls back to the party's score, so nothing changes there.
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
TRAITS = ('caution', 'curiosity', 'boldness')
SPLIT = 0.15          # how far past 0.5 the rest of the party must lean, the other way, to overrule the loudest voice

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

# ---------- each member's own voice ----------
def nick(p):
    """What the write-up calls a stock character (Clarence, Orik, ...); anyone else by their own name."""
    try:
        from roster import NICKNAMES
    except ImportError:
        NICKNAMES = {}
    return NICKNAMES.get(p.name, p.name)

def voices_mode(run):
    """Which rule combines the members' traits. See the module docstring."""
    v = run.cfg.get('voices')
    if v: return v
    mode = run.cfg.get('traits', 'profile')
    if isinstance(mode, dict) or mode == 'random': return 'party'
    prof = profiles()
    if run.pcs and all(prof.get(p.name) or prof.get(getattr(p, 'sheet_key', '')) for p in run.pcs): return 'party'
    return 'loudest'

def member_traits(run):
    """Each member's own traits for this run: a profile nudged a little, or a fresh draw for anyone without one."""
    prof = profiles(); out = {}
    for p in run.pcs:
        pr = prof.get(p.name) or prof.get(getattr(p, 'sheet_key', ''))
        out[p.name] = ({k: clamp(pr[k] + R.gauss(0, 0.07), 0.05, 0.95) for k in TRAITS} if pr else draw_traits())
    return out

def combine(run):
    """Sets run.member_traits, run.leader and run.voice ({trait: how it was settled}); returns the party's traits."""
    mode = run.voices = voices_mode(run)
    run.member_traits = {}; run.leader = None; run.voice = {}
    if mode == 'party': return party_traits(run)
    mt = run.member_traits = member_traits(run)
    names = [p.name for p in run.pcs]
    lead = run.cfg.get('leader', 'random')
    if mode == 'loudest' and lead == 'random': run.leader = R.choice(names)
    elif mode == 'loudest' and lead not in ('none', None): run.leader = lead if lead in mt else next((p.name for p in run.pcs if nick(p) == lead), None)
    byname = {p.name: p for p in run.pcs}
    out = {}
    for t in TRAITS:
        vals = {n: mt[n][t] for n in names}
        avg = sum(vals.values()) / len(vals)
        if mode == 'average' or len(vals) == 1:
            out[t] = avg; run.voice[t] = dict(how='average', value=avg); continue
        loud = max(names, key=lambda n: abs(vals[n] - 0.5))
        rest = [vals[n] for n in names if n != loud]
        ra = sum(rest) / len(rest)
        split = (vals[loud] - 0.5) * (ra - 0.5) < 0 and abs(ra - 0.5) >= SPLIT
        if not split:
            out[t] = vals[loud]; run.voice[t] = dict(how='loudest', who=loud, value=vals[loud])
        elif run.leader:
            out[t] = vals[run.leader]
            run.voice[t] = dict(how='leader', who=run.leader, over=loud, value=vals[run.leader], wanted=vals[loud], rest=ra)
            if run.leader == loud: why = f"{nick(byname[loud])} led and held firm ({t} {vals[loud]:.2f}) against the rest ({ra:.2f})"
            else: why = f"{nick(byname[run.leader])} overruled {nick(byname[loud])} ({t} {vals[run.leader]:.2f}, not {vals[loud]:.2f})"
            log(f"  [voice] {t}: split; {why}")
        else:
            out[t] = avg; run.voice[t] = dict(how='split, averaged', over=loud, value=avg)
    return out

def actor(run, trait, low=False, pool=None):
    """Who acts alone at a moment like this: the member the trait points to most (lowest with low=True), with a little
    noise. None under voices='party', where there are no individual voices."""
    if getattr(run, 'voices', 'party') == 'party' or not run.member_traits: return None
    pool = [p for p in (pool or run.alive) if p.name in run.member_traits] or [p for p in run.alive if p.name in run.member_traits]
    if not pool: return None
    sign = -1 if low else 1
    return max(pool, key=lambda p: sign * run.member_traits[p.name][trait] + R.gauss(0, 0.08))

def choose(run, point, options, who=None, trait=None):
    """options: {name: (score, reason)}. Picks the best score after a little noise. who: the member deciding alone,
    named in the log along with the trait that put them forward."""
    scored = {k: v[0] + R.gauss(0, 0.08) for k, v in options.items()}
    pick = max(scored, key=scored.get)
    why = options[pick][1]
    if who is not None:
        tv = run.member_traits.get(who.name, {})
        why = f"{nick(who)}" + (f", {trait} {tv[trait]:.2f}" if trait and trait in tv else '') + f": {why}"
    run.decisions.append((point, pick, why))
    log(f"  [decision] {point}: {pick} ({why}; " + ', '.join(f'{k} {v[0]:.2f}' for k, v in options.items()) + ")")
    return pick

def traits(run, who=None):
    """The party's combined traits, or one member's own with who= (the party's under voices='party')."""
    t = run.traits
    if who is not None and getattr(run, 'member_traits', None) and who.name in run.member_traits: t = run.member_traits[who.name]
    return t['caution'], t['curiosity'], t['boldness']
