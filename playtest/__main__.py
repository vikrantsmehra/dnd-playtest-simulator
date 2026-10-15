"""Command line. Run from the Playtest Simulator folder:

  python3 -m playtest list                                  modules and their studies
  python3 -m playtest validate <module>                     check a module's map and contents
  python3 -m playtest brief <module>                        make the playtest brief: what you want to learn, and the targets
  python3 -m playtest run <module>                          run what the brief asks for (stock party by default)
  python3 -m playtest run <module> <study> [<study> ...]    run studies (all with 'all'); results land in results/<module>/
  python3 -m playtest run <module> --party stock@5x6        the stock party at 5th level, six strong
  python3 -m playtest run <module> --party A --n 500        a saved party, or comma-separated names
  python3 -m playtest replay <module> <study> <seed>        one run again, roll by roll, into results/<module>/replays/
  python3 -m playtest report <module>                       the Obsidian report and room map from the saved results
  python3 -m playtest fight <module> --party A --monsters "ghoul x3, ghast"   one fight in isolation, 500 times
  python3 -m playtest pdf <file.pdf>                        a module PDF's text, for drafting a new module

Settings: add --set key=value (repeatable) to override a module setting, e.g. --set tpk_s2=sentence.
"""
import sys, os, json, argparse
sys.path.insert(0, os.getcwd())

def parse_sets(sets):
    out = {}
    for s in sets or []:
        k, _, v = s.partition('=')
        try: out[k] = json.loads(v)
        except ValueError: out[k] = v
    return out

def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m playtest', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('list')
    v = sub.add_parser('validate'); v.add_argument('module')
    r = sub.add_parser('run'); r.add_argument('module'); r.add_argument('studies', nargs='*')
    r.add_argument('--party'); r.add_argument('--n', type=int); r.add_argument('--seed', type=int); r.add_argument('--jobs', type=int)
    r.add_argument('--set', action='append'); r.add_argument('--out')
    p = sub.add_parser('replay'); p.add_argument('module'); p.add_argument('study'); p.add_argument('seed', type=int)
    p.add_argument('--party'); p.add_argument('--set', action='append')
    rp = sub.add_parser('report'); rp.add_argument('module'); rp.add_argument('--out')
    f = sub.add_parser('fight'); f.add_argument('module'); f.add_argument('--party', required=True); f.add_argument('--monsters', required=True)
    f.add_argument('--n', type=int, default=500); f.add_argument('--importance', default=None); f.add_argument('--log', action='store_true')
    f.add_argument('--terrain', help='JSON, e.g. \'{"distance": 60, "elevated": "monsters", "light": "dark"}\''); f.add_argument('--level', type=int)
    pdf = sub.add_parser('pdf'); pdf.add_argument('file'); pdf.add_argument('--out')
    bf = sub.add_parser('brief'); bf.add_argument('module')
    a = ap.parse_args(argv)

    if a.cmd == 'list':
        import pkgutil, importlib, modules
        for m in pkgutil.iter_modules(modules.__path__):
            mod = importlib.import_module(f'modules.{m.name}').MODULE
            print(f"{m.name}: {mod.title}")
            for s in mod.studies.values(): print(f"    {s.name:6s} {s.n:6d} runs  {s.desc}")
    elif a.cmd == 'validate':
        from playtest.batch import load
        probs = load(a.module).validate()
        print('\n'.join(probs) if probs else 'no problems found')
    elif a.cmd == 'run':
        from playtest.batch import run_batch, load
        cfg = parse_sets(a.set)
        if a.party:
            party = a.party if ',' not in a.party else [x.strip() for x in a.party.split(',')]
            run_batch(a.module, party=party, n=a.n, seed=a.seed, cfg=cfg, jobs=a.jobs, out=a.out or 'custom')
        elif not a.studies:                                      # no study and no party: the brief decides
            from playtest.brief import load as load_brief, create
            mod = load(a.module)
            br = load_brief(mod)
            if br is None or not br.get('question'):
                p, made = create(mod)
                print(f"{'Made' if made else 'Fill in'} the playtest brief first: {p}\n"
                      f"Say what you want to learn and the targets, then run this again. (Or name a study: python3 -m playtest run {a.module} all)")
                return
            party = br.get('party') or 'stock'
            if isinstance(party, str) and ',' in party: party = [x.strip() for x in party.split(',')]
            if br.get('level'): cfg.setdefault('level', int(br['level']))
            run_batch(a.module, party=party, n=a.n or int(br.get('runs') or 2000), seed=a.seed, cfg=cfg, jobs=a.jobs, out='brief')
        else:
            names = a.studies
            if names == ['all']: names = list(load(a.module).studies)
            for s in names: run_batch(a.module, study=s, n=a.n, seed=a.seed, cfg=cfg, jobs=a.jobs, out=a.out)
    elif a.cmd == 'replay':
        from playtest.batch import replay
        folder = os.path.join('results', a.module, 'replays'); os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f'replay_{a.study}_{a.seed}.log')
        party = (a.party.split(',') if a.party and ',' in a.party else a.party)
        run, _ = replay(a.module, None if a.party else a.study, a.seed, party=party, cfg=parse_sets(a.set), path=path)
        print(f"{run.outcome} -> {path}")
    elif a.cmd == 'report':
        from playtest.report import write_report
        print(write_report(a.module, a.out))
    elif a.cmd == 'fight':
        from playtest.isolate import isolate
        party = a.party.split(',') if ',' in a.party else a.party
        isolate(a.module, party, a.monsters, a.n, a.importance, a.log, cfg={'level': a.level} if a.level else None,
                terrain=json.loads(a.terrain) if a.terrain else None)
    elif a.cmd == 'brief':
        from playtest.batch import load
        from playtest.brief import create
        p, made = create(load(a.module))
        print(f"{'Made' if made else 'Already there'}: {p}")
    elif a.cmd == 'pdf':
        from tools.pdf_text import extract
        text = extract(a.file)
        if a.out: open(a.out, 'w').write(text); print(f"{len(text):,} characters -> {a.out}")
        else: print(text)
    else:
        ap.print_help()

if __name__ == '__main__':
    main()
