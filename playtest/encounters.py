"""Declarative rooms: what the director does in a room that has no script of its own.

In order: the room's checks (traps, hazards, skill checks), then its encounter, then its loot, then a rest if the
party needs one. Fields on MODULE.node(...):

  encounter   'goblin x4, bugbear'; '{n}' is the party size, so 'goblin x{n+1}' scales with the table
  importance  'minor' | 'normal' | 'major' | 'boss'; by default worked out from the DMG difficulty for this party
  stealth     dict(dc=None) the party sneaks up: a group Stealth check (half must pass) against the best passive
              Perception among the monsters (or dc). Success means the monsters are surprised; no attempt if alarmed.
  morale      dict(flee_at=0.5, after=1, ally_dies=False, alarm=True): monsters break off at that fraction of HP
              (1.0 = as soon as they're hurt) from round 'after'. With alarm, fled monsters warn the next room:
              no surprise there, and they join its fight in round 2.
  optional    a fight the party can walk away from (retreats don't force a rematch)
  checks      list of dicts, run before the fight:
                trap:  dict(kind='trap', name=, detect=('Perc', 12), disarm=('tools', 10), save=('dex', 15),
                            dmg='1d8', type='slashing', who='one'|'all', small_safe=False)
                check: dict(kind='check', skill='Sur', dc=10, who='best'|'all', fail=dict(dmg=, type=, flag=),
                            success=dict(flag=), tries=1)
                flag:  dict(kind='flag', flag='secret_door', chance=0.6)   (something happens, or not)
  loot        dict(potions=2, gold='2d20+10', flag='bess_rescued')
  after       'rest' (default), 'boss' (rest as if a boss is next) or None
"""
import re
from .pc import *
from . import bestiary as B

def fmt(text, run):
    n = len(run.alive)
    return re.sub(r'\{([^}]*)\}', lambda m: str(int(eval(m.group(1), {'n': n}))), text)

def best_at(run, skill):
    return max([p for p in run.alive if p.up] or run.alive, key=lambda p: p.skills.get(skill, -5))

def do_check(run, c):
    k = c.get('kind', 'check')
    if k == 'flag':
        if R.random() < c.get('chance', 1.0): run.flags[c['flag']] = True
        return
    if k == 'trap':
        spotted = False
        if c.get('detect'):
            sk, dc = c['detect']
            spotted = check(best_at(run, sk), sk, dc=dc)
        if spotted and c.get('disarm'):
            sk, dc = c['disarm']
            pickers = [p for p in run.alive if getattr(p, 'thieves_tools', None) is not None]
            if sk == 'tools' and pickers:
                p = max(pickers, key=lambda p: p.thieves_tools)
                if d20() + p.thieves_tools >= dc: run.events.append(f"disarmed {c.get('name', 'a trap')}"); return
            elif sk == 'tools' and c.get('blade_ok'):
                p = max(run.alive, key=lambda p: p.mods['dex'])
                if d20(-1) + p.mods['dex'] >= dc: run.events.append(f"disarmed {c.get('name', 'a trap')} with a blade"); return
            elif sk != 'tools' and check(best_at(run, sk), sk, dc=dc): return
        if spotted and c.get('avoidable', True) and not c.get('disarm'): return
        who = [p for p in run.alive if not (c.get('small_safe') and getattr(p, 'size', 'Medium') == 'Small')]
        if not who: return
        tg = who if c.get('who') == 'all' else [who[0] if not spotted else R.choice(who)]
        ab, dc = c.get('save', ('dex', 10))
        for p in tg:
            ok = make_save(p, ab, dc)
            amt = roll(c['dmg']); amt = (amt // 2 if c.get('half') else 0) if ok else amt
            if amt: apply_dmg(p, amt, c.get('type', 'piercing'))
            if not ok and c.get('cond'): p.lasting[c['cond']] = 600
            if p.hp <= 0 and not p.dead: p.hp = 0; p.down = False; p.ko = True
        run.recover_ko()
        run.events.append(f"triggered {c.get('name', 'a trap')}")
        return
    sk, dc = c['skill'], c['dc']
    ok = False
    for _ in range(c.get('tries', 1)):
        if c.get('who') == 'all': ok = sum(check(p, sk, dc=dc) for p in run.alive) * 2 >= len(run.alive)
        else: ok = check(best_at(run, sk), sk, dc=dc)
        if ok: break
    res = c.get('success' if ok else 'fail') or {}
    if res.get('flag'): run.flags[res['flag']] = True
    if res.get('dmg'):
        for p in (run.alive if res.get('all') else [best_at(run, sk)]): apply_dmg(p, roll(res['dmg']), res.get('type', 'bludgeoning'))
        run.recover_ko()
    if res.get('exh'):
        for p in run.alive: p.exh += res['exh']

def surprise(run, node, mons):
    st = getattr(node, 'stealth', None)
    if st is None or run.alarmed or not mons: return False
    dc = st.get('dc') or max(10 + m.skills.get('perception', m.mods.get('wis', 0) if hasattr(m, 'mods') else 0) for m in mons)
    ok = sum(check(p, 'Ste', dc=dc) for p in run.alive if p.up)
    return ok * 2 >= len([p for p in run.alive if p.up])

def run_room(d, run, node):
    for c in node.checks: do_check(run, c)
    if run.outcome: return False
    res = 'win'
    if node.encounter and getattr(node, 'skip_if_alarmed', False) and run.alarmed:
        run.events.append(f"{node.name}: nobody here, they ran to warn the others")
    elif node.encounter:
        mons = B.group(fmt(node.encounter, run))
        mo = getattr(node, 'morale', None)
        if mo:
            for m in mons:
                m.flee_at = mo.get('flee_at', 0.5); m.flee_after = mo.get('after', 0); m.flee_if_ally_dies = mo.get('ally_dies', False)
        env = dict(getattr(node, 'env', {}) or {})
        arrivals = []
        if run.alarm:
            back = run.alarm; run.alarm = []
            for m in back:
                m.dead = False; m.down = False; m.fled = False; m.flee_at = 0; m.cond = {}
                if '(warned' not in m.name: m.name += ' (warned the room)'
            arrivals.append((2, back))
        surprised = surprise(run, node, mons)
        run.metrics.setdefault('surprised', {})[node.id] = surprised
        if surprised:
            def pre(enc, mons=mons):
                for m in mons: m.cond['lost_turn'] = True
            env['pre'] = pre
        label, adj, imp = B.difficulty(mons, run.alive)
        res = run.fight(node.name, mons, node.importance or imp, env=env, arrivals=arrivals, optional=getattr(node, 'optional', False))
        fled = [m for m in mons if getattr(m, 'fled', False)]
        if fled and mo and mo.get('alarm', True):
            run.alarm = fled; run.alarmed = True
            run.events.append(f"{len(fled)} fled from {node.name} to raise the alarm")
        if res != 'win': return False
    for k, v in (node.loot or {}).items():
        if k == 'potions': run.potions += v
        elif k == 'gold': run.metrics['gold'] = run.metrics.get('gold', 0) + (roll(v) if isinstance(v, str) else v)
        elif k == 'flag': run.flags[v] = True
        else: run.metrics[k] = v
    if node.after == 'rest': run.after_room()
    elif node.after == 'boss': run.after_room(before_boss=True)
    return None
