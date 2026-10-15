"""One fight in isolation, many times, from full resources: how a party fares against a group of monsters.

  python3 -m playtest fight <module|none> --party A --monsters "ghoul x3, ghast" [--n 500] [--importance major] [--log]
"""
import statistics
from collections import Counter
from .dice import R, VERBOSE, LOG
from .combat import Encounter, run_encounter
from .run import Run
from .pc import potion_obj
from . import bestiary as B, hooks as H

def isolate(slug, party, monsters, n=500, importance=None, show_log=False, cfg=None, seed=1, terrain=None):
    import roster
    module = None
    if slug and slug != 'none':
        from .batch import load
        module = load(slug)
    else:
        H.clear()
    wins = 0; rounds = []; drops = 0; deaths = 0; hp = []; dmg = Counter(); diff = None
    for i in range(n):
        R.seed(seed * 100000 + i)
        VERBOSE[0] = show_log and i == 0; LOG.clear()
        pcs = roster.party(party, (cfg or {}).get('level', 1))
        run = Run(pcs, dict(module.config if module else {}, **(cfg or {})), module)
        run.day_start(); run.give_potions()
        mons = B.group(monsters)
        label, adj, imp = B.difficulty(mons, pcs)
        diff = (label, adj)
        enc = Encounter(run.pcs, mons, monsters, importance=importance or imp, env={'objectives': [potion_obj], 'terrain': terrain})
        res = run_encounter(enc)
        if show_log and i == 0: print('\n'.join(LOG))
        wins += res == 'win'; rounds.append(enc.round); drops += len(enc.drops); deaths += len(enc.deaths)
        hp.append(run.hp_frac() if res == 'win' else 0)
        for k, v in enc.dmg_by.items(): dmg[k] += v
    print(f"{monsters} vs {party if isinstance(party, str) else ', '.join(party)}: {diff[0]} ({diff[1]:.0f} adjusted XP), "
          f"played as '{importance or imp}'")
    print(f"  win {wins / n:.0%}   rounds {statistics.mean(rounds):.1f}   drops/fight {drops / n:.2f}   deaths/fight {deaths / n:.2f}"
          f"   party HP left {statistics.mean(hp):.0%}")
    print('  damage per fight: ' + ', '.join(f"{k.replace('Stock ', '').split()[0]} {v / n:.0f}" for k, v in dmg.most_common()))
    return wins / n
