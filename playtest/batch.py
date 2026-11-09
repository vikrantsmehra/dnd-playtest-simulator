"""Many playthroughs: seeds, parallel workers and the results rows.

Run i of a batch with seed S uses R.seed(S * 100000 + i), set before the party is drawn, so any single run can be
replayed exactly with `python3 -m playtest replay` as long as the code hasn't changed since.
"""
import os, json, time, importlib, concurrent.futures as cf
from .dice import R, VERBOSE, LOG
from .director import play

def load(slug):
    mod = importlib.import_module(f'modules.{slug}').MODULE
    mod.register()
    return mod

def resolve_party(spec, module=None, cfg=None):
    """'stock' (the default: fighter, cleric, rogue, wizard at the module's level, or the 'level' setting),
    'stock@5x6', a saved party key ('A'), a list of names, or a function that draws one (called after seeding)."""
    import roster
    if callable(spec): spec = spec()
    if spec is None: spec = 'stock'
    level = (cfg or {}).get('level') or (module.levels[0] if module and module.levels else 1)
    return list(roster.names_for(spec, level))

def row(module, run, team, seed):
    comp = bool(run.outcome and run.outcome.startswith('complete'))
    r = dict(seed=seed, team=team, outcome=run.outcome or 'incomplete', complete=comp,
             deaths=run.deaths, drops=run.drops, dead=[p.name for p in run.pcs if p.dead],
             fail=run.fail_room, fail_loc=(run.room if run.fail_room else None),
             captures=run.captures, retreats=getattr(run, 'retreats', 0), revived=getattr(run, 'revived', 0),
             rot=[p.name for p in run.pcs if p.rot], events=run.events, decisions=getattr(run, 'decisions', []),
             route=getattr(run, 'route', []), traits=getattr(run, 'traits', {}), wanders=len(run.wanders),
             voices=getattr(run, 'voices', 'party'), member_traits=getattr(run, 'member_traits', {}),
             leader=getattr(run, 'leader', None), voice=getattr(run, 'voice', {}),
             enc={k: dict(v) for k, v in run.enc_stats.items()}, locks=run.metrics.get('locks', {}),
             extra={k: v for k, v in run.metrics.items() if k != 'locks'})
    if module.metrics: r['m'] = module.metrics(run)
    return r

def one(module, spec, cfg, seed, verbose=False):
    R.seed(seed)
    team = resolve_party(spec, module, cfg)
    import roster
    run = play(module, roster.party(team), cfg, verbose=verbose)
    return run, team

def _worker(args):
    slug, study, spec, cfg, seeds = args
    module = load(slug)
    if study is not None: spec = module.studies[study].parties
    out = []
    for s in seeds:
        run, team = one(module, spec, cfg, s)
        out.append(row(module, run, team, s))
    return out

def run_batch(slug, study=None, party=None, n=None, seed=None, cfg=None, jobs=None, out=None, quiet=False):
    """Run a study (or an ad-hoc party) and write results/<slug>/<name>.json. Returns the rows."""
    module = load(slug)
    st = module.studies.get(study) if study else None
    if study and st is None: raise SystemExit(f"no study '{study}' in {slug}; try: {', '.join(module.studies)}")
    n = n or (st.n if st else 1000)
    seed = seed if seed is not None else (st.seed if st else 1)
    c = dict(module.config); c.update(st.cfg if st else {}); c.update(cfg or {})
    seeds = [seed * 100000 + i for i in range(n)]
    jobs = jobs or os.cpu_count() or 4
    chunk = max(1, -(-n // (jobs * 4)))
    parts = [seeds[i:i + chunk] for i in range(0, n, chunk)]
    t = time.time(); rows = []
    spec = None if st else party
    with cf.ProcessPoolExecutor(jobs) as ex:
        for res in ex.map(_worker, [(slug, study if st else None, spec, c, p) for p in parts]):
            rows.extend(res)
    name = out or (study if st else 'custom')
    folder = os.path.join(os.getcwd(), 'results', slug); os.makedirs(folder, exist_ok=True)
    who = party if isinstance(party, str) else ', '.join(party or [])
    meta = dict(module=slug, study=name, label=(st.label if st else ('Your brief' if name == 'brief' else name)),
                desc=(st.desc if st else f"party {who}" + (f" at level {c['level']}" if c.get('level') else '')), n=n, seed=seed, cfg=c,
                seconds=round(time.time() - t, 1), when=time.strftime('%Y-%m-%d %H:%M'))
    json.dump(dict(meta=meta, rows=rows), open(os.path.join(folder, f'{name}.json'), 'w'), default=str)
    if not quiet:
        done = sum(r['complete'] for r in rows)
        print(f"{slug} {name}: {n} runs in {meta['seconds']}s, finished {100 * done / n:.1f}%  -> results/{slug}/{name}.json")
    return rows

def members(run):
    """Replay header lines: each member's own traits, the leader, and how each party trait was settled."""
    from .decisions import nick
    mt = getattr(run, 'member_traits', {})
    if not mt: return []
    by = {p.name: p for p in run.pcs}
    out = [f"  {nick(by[n])}{' (leader)' if n == getattr(run, 'leader', None) else ''}: " + ', '.join(f'{k} {v:.2f}' for k, v in t.items())
           for n, t in mt.items()]
    for t, v in getattr(run, 'voice', {}).items():
        who = nick(by[v['who']]) if v.get('who') in by else None
        over = nick(by[v['over']]) if v.get('over') in by else None
        if v['how'] == 'loudest': out.append(f"  {t}: {who}'s voice ({v['value']:.2f})")
        elif v['how'] == 'leader': out.append(f"  {t}: split; {who} decided ({v['value']:.2f}; {over} wanted {v['wanted']:.2f}, the rest {v['rest']:.2f})")
        else: out.append(f"  {t}: {v['how']} ({v['value']:.2f})")
    return out

def replay(slug, study=None, seed=None, party=None, cfg=None, path=None):
    """Play one run again with the full roll-by-roll log."""
    module = load(slug)
    st = module.studies.get(study) if study else None
    c = dict(module.config); c.update(st.cfg if st else {}); c.update(cfg or {})
    run, team = one(module, st.parties if st else party, c, seed, verbose=True)
    head = [f"# {module.title}: replay of seed {seed}" + (f" ({study})" if study else ''),
            f"Party: {', '.join(team)}", f"Traits: " + ', '.join(f'{k} {v:.2f}' for k, v in run.traits.items())
            + (f" (voices: {run.voices})" if getattr(run, 'voices', 'party') != 'party' else '')] + members(run) + [

            f"Outcome: {run.outcome}" + (f" at {run.fail_room}" if run.fail_room else ''), '']
    text = '\n'.join(head + LOG)
    if path: open(path, 'w').write(text)
    return run, text
