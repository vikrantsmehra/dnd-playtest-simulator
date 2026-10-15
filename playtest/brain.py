"""A stat block's brain: turns a spec from playtest.statblock into a Creature that fights sensibly.

Each turn the monster rolls its recharges, lists what it could do (each multiattack plan, each single action, each spell
it has a slot or a use for), scores every option by expected damage plus the value of any condition it inflicts, and
takes the best. Then a bonus action if it has one worth taking. Legendary actions go off after PCs' turns.

Targeting: clever monsters (Int 8+) focus whoever they can hurt most and finish off the wounded; mindless ones hit the
nearest front-liner. Melee attackers mostly can't reach the back rank while the front rank stands.
"""
from .monster import *
from .spells import SPELLS, option as spell_option, COND_VALUE
from .statblock import mod, ABIL

def hp_for(spec, mode='avg'):
    if mode == 'avg' or not spec.get('hit_dice'): return spec['hp']
    return max(1, roll(spec['hit_dice']))

def build(spec, name=None, hp_mode='avg'):
    s = spec
    kw = s.get('kw', {})
    uses = {}
    if kw.get('lr'): uses['lr'] = kw['lr']
    if kw.get('parry'): uses['parry'] = 1
    m = Creature(name or s['name'], 'mon', hp_for(s, hp_mode), s['ac'], dict(s['saves']), skills=dict(s['skills']),
                 res=set(s['res']), imm=set(s['imm']), vul=set(s['vul']), res_nonmag=s.get('res_nonmag', False),
                 cond_imm=set(s['cond_imm']), tags=set(s.get('tags', [])), init=mod(s['abilities']['dex']), cr=s.get('cr', 0),
                 uses=uses)
    m.spec = s; m.xp = s.get('xp', 0)
    m.mods = {a: mod(v) for a, v in s['abilities'].items()}
    m.int_score = s['abilities']['int']
    m.darkvision = bool(s.get('darkvision'))
    if s.get('nonmag_immune'): m.imm_nonmag = True
    if kw.get('parry'): m.parry_bonus = kw['parry']
    if kw.get('uncanny'): m.uncanny_mon = True
    if kw.get('retaliate'): m.retaliate = kw['retaliate']
    if kw.get('death_burst'): m.on_death = _death_burst.__get__(m)
    if kw.get('stench_dc'): m.stench_dc = kw['stench_dc']
    if kw.get('regen'):
        m.regen = kw['regen']; m.regen_stop = kw.get('regen_stop', [])
        m.down_turn = _regen_down_turn.__get__(m)
    m.actions = {a['name']: dict(a) for a in s['actions'] if a.get('kind') in ('attack', 'save', 'heal')}
    for a in m.actions.values():
        if a.get('recharge') or a.get('per_day'): a['ready'] = True; a['left'] = a.get('per_day', 0)
    m.plans = [p for p in (s.get('multiattack') or []) if all(n in m.actions for n, _ in p)]
    m.bonus_actions = [dict(a) for a in s.get('bonus', []) if a.get('kind') in ('attack', 'save', 'heal')]
    # spellcasting
    m.spell_opts = []; m.slots = {}; m.spell_dc = 10
    for sc in s.get('spellcasting', []):
        dc = sc.get('dc') or 10; atk = sc.get('attack') or (dc - 8); lvl = sc.get('level') or max(1, int(s.get('cr', 1)))
        m.spell_dc = max(m.spell_dc, dc)
        for l, n in sc.get('slots', {}).items(): m.slots[int(l)] = m.slots.get(int(l), 0) + n
        abil = max(m.mods.values())
        for l, names in sc.get('spells', {}).items():
            for nm in names:
                o = spell_option(nm, atk, dc, lvl, mod=abil)
                if o: m.spell_opts.append(o)
        for nm in sc.get('at_will', []):
            o = spell_option(nm, atk, dc, lvl, mod=abil)
            if o: o.pop('cost', None); m.spell_opts.append(o)
        for nm, n in sc.get('per_day', {}).items():
            o = spell_option(nm, atk, dc, lvl, mod=abil)
            if o: o['cost'] = ('day', nm); m.uses['day:' + nm] = n; m.max_uses['day:' + nm] = n; m.spell_opts.append(o)
    m.max_slots = dict(m.slots)
    if any('shield' == n for sc in s.get('spellcasting', []) for l in sc.get('spells', {}).values() for n in l) and m.slots.get(1):
        m.uses['shield_slots'] = min(2, m.slots[1]); m.max_uses['shield_slots'] = m.uses['shield_slots']   # reaction shield
    if s.get('legendary'):
        m.leg_n = s['legendary'].get('n', 3); m.leg = m.leg_n
        m.leg_opts = [a for a in s['legendary']['actions'] if a.get('kind') in ('attack', 'save', 'heal', 'ref', 'cantrip')]
        m.legendary = _legendary.__get__(m)
    m.martial_adv = kw.get('martial_adv'); m.sneak = kw.get('sneak'); m.charge = kw.get('charge')
    melee = [a for a in m.actions.values() if a.get('kind') == 'attack' and a.get('melee')]
    ranged = [a for a in m.actions.values() if a.get('kind') == 'attack' and a.get('ranged') and not a.get('melee')]
    casts = any(o['kind'] in ('atk', 'save', 'auto', 'cond') for o in m.spell_opts)
    if any(o['kind'] == 'cond' and o['level'] >= 2 for o in m.spell_opts) or m.leg_n if hasattr(m, 'leg_n') else False:
        m.tags.add('priority')                     # a controller or a legendary: the party should go for it
    m.role = 'back' if (ranged and not melee) or casts else 'front'
    names = {n for sc in s.get('spellcasting', []) for l in sc.get('spells', {}).values() for n in l}
    if 'mage armor' in names and m.ac_base <= 10 + m.mods['dex'] + 2:
        m.ac_base = 13 + m.mods['dex']                      # cast in the morning
        if m.slots.get(1): m.slots[1] -= 1; m.max_slots = dict(m.slots)
    m.smart = m.int_score >= 8
    m.turn = _turn.__get__(m)
    return m

# ---------------------------------------------------------------- scoring
def pc_mult(t, typ, magic=True):
    if typ in t.imm: return 0
    x = 1.0
    if typ in t.vul: x *= 2
    if typ in t.res or (t.cond.get('rage') and typ in PHYS) or t.cond.get('raven_res'): x *= 0.5
    if t.cond.get('warding') == typ: return 0
    return x

def rider_value(a, t):
    r = a.get('rider') or {}
    v = 0.0
    if r.get('cond') and r['cond'] not in t.cond_imm:
        pf = 1 - p_save(t.saves.get(r['save'], 0), r['dc']) if r.get('save') else 1.0
        v += pf * COND_VALUE.get(r['cond'], 3) * (2 if r.get('repeat') or r.get('dur', 1) > 1 else 1)
    if r.get('dmg'):
        pf = 1 - p_save(t.saves.get(r['save'], 0), r['dc']) if r.get('save') else 1.0
        v += (pf + (1 - pf) * (0.5 if r.get('half') else 0)) * avg(r['dmg']) * pc_mult(t, r['type'])
    if r.get('rot'): v += 6
    if r.get('drain'): v += 3
    return v

def reach(m, enc, a, t):
    """Whether this attack can be made at all: melee needs the gap closed, the ledge climbed, a place in the line."""
    if not enc.terrain or not a.get('melee'): return True
    return enc.terrain.can_melee(enc, m, t) or a.get('ranged', False)

def attack_ev(m, enc, a, t):
    if not reach(m, enc, a, t): return 0
    adv = attack_adv(enc, m, t, a)
    p = p_hit(a['hit'], t.ac, adv)
    d = avg(a['dmg']) * pc_mult(t, a['type'], a.get('magic', False))
    for e in a.get('extra', ()): d += avg(e['dmg']) * pc_mult(t, e['type'])
    v = p * d + p * rider_value(a, t)
    if a.get('melee') and not a.get('ranged') and t.role == 'back' and any(x.up and x.role == 'front' for x in enc.pcs if x is not t):
        v *= 0.35                      # has to get past the front rank first
    return v

def save_ev(m, enc, a, t, aoe=None):
    aoe = aoe if aoe is not None else a.get('aoe', 1)
    pf = 1 - p_save(t.saves.get(a['save'], 0) + (1 if t.cond.get('bless') else 0), a['dc'])
    v = 0.0
    if a.get('dmg') and a['dmg'] != '0':
        d = avg(a['dmg']) + (avg(a['dmg2']) if a.get('dmg2') else 0)
        v += (pf + (1 - pf) * (0.5 if a.get('half', True) else 0)) * d * pc_mult(t, a['type'])
    c = a.get('cond')
    if c and c not in t.cond_imm and not t.cond.get(c):
        v += pf * COND_VALUE.get(c, 3) * (2 if a.get('repeat') else 1)
    n_up = len(enc.enemies(m))
    return v * min(aoe, max(1, n_up))

def option_ev(m, enc, o, t):
    k = o['kind']
    if k == 'atk':
        a = dict(o, melee=o.get('melee', False))
        return o.get('n', 1) * attack_ev(m, enc, a, t) + (6 if o.get('guided') else 0)
    if k == 'save':
        return save_ev(m, enc, o, t)
    if k == 'cond':
        return save_ev(m, enc, dict(o, dmg='0'), t)
    if k == 'auto':
        return avg(o['dmg']) * o.get('n', 1) * pc_mult(t, o['type'])
    if k == 'aura':
        if m.conc: return 0
        return avg(o['dmg']) * 0.6 * sum(1 for x in enc.pcs if x.up and x.role == 'front') * 2.5
    if k == 'spirit':
        return 0 if getattr(m, 'spirit', None) else p_hit(o['hit'], t.ac) * avg(o['dmg']) * 3
    return 0

def usable(m, o):
    c = o.get('cost')
    if not c: return True
    if c[0] == 'slot': return any(n > 0 for l, n in m.slots.items() if l >= c[1])
    if c[0] == 'day': return m.uses.get('day:' + c[1], 0) > 0
    return True

def spend(m, o):
    c = o.get('cost')
    if not c: return
    if c[0] == 'slot':
        l = min(l for l, n in m.slots.items() if l >= c[1] and n > 0); m.slots[l] -= 1
    elif c[0] == 'day': m.uses['day:' + c[1]] -= 1

def pick_target(m, enc, score):
    ts = enc.enemies(m)
    if not ts: return None
    f = getattr(m, 'focus', None)                  # a module can tell a monster who to go for
    if f:
        ft = f(enc)
        if ft in ts and R.random() < 0.75: return ft
    if not m.smart:
        p = pick_front(enc, m)
        return p
    sc = [(score(t) * (1 + 0.4 * (1 - t.hp / max(1, t.maxhp))), t) for t in ts]
    best = max(v for v, _ in sc)
    top = [t for v, t in sc if v >= best * 0.85] or [t for _, t in sc]
    return R.choice(top)

def area_targets(m, enc, primary, aoe):
    if enc.terrain: aoe = 1 + (aoe - 1) * enc.terrain.aoe_scale()
    ts = [t for t in enc.enemies(m) if t is not primary]
    if aoe <= 1 or not ts: return [primary]
    k = aoe - 1
    out = [primary]
    for t in ts:
        p = min(1.0, k / len(ts) * (1.25 if t.role == primary.role else 0.75))
        if R.random() < p: out.append(t)
    return out

# ---------------------------------------------------------------- acting
def apply_rider(enc, m, t, r, dealt=0):
    if t.dead: return
    if r.get('save'):
        if r.get('dmg') and not r.get('cond') and not r.get('rot') and not r.get('drain'):
            ok = make_save(t, r['save'], r['dc'], enc=enc)
            amt = roll(r['dmg']); amt = (amt // 2 if r.get('half') else 0) if ok else amt
            if amt: apply_dmg(t, amt, r['type'], True, m, enc); after_damage(enc, t, amt)
            return
        if make_save(t, r['save'], r['dc'], enc=enc):
            if r.get('dmg') and r.get('half'): apply_dmg(t, roll(r['dmg']) // 2, r['type'], True, m, enc)
            return
        if r.get('dmg'): apply_dmg(t, roll(r['dmg']), r['type'], True, m, enc)
    if t.dead: return
    c = r.get('cond')
    if c and c not in t.cond_imm:
        if c == 'prone': t.cond['prone'] = True
        elif r.get('grapple'): t.cond[c] = ('save', r['grapple'], 'str')
        elif r.get('repeat'): t.cond[c] = ('save', r['dc'], r['repeat'])
        else: t.cond[c] = r.get('dur', 1) if r.get('dur', 1) > 1 else 1
        log(f"    {t.name} is {c}")
    if r.get('rot'):
        t.rot = True; log(f"    {t.name} is cursed: can't regain hit points")
    if r.get('drain') and dealt:
        t.drained += dealt; t.maxhp = max(1, t.maxhp - dealt); t.hp = min(t.hp, t.maxhp)

def do_attack(m, enc, a, t):
    melee_ok = not enc.terrain or enc.terrain.can_melee(enc, m, t)
    if a.get('melee') and not melee_ok and not a.get('ranged'): return (False, False, 0)
    atk = dict(name=a['name'], hit=a['hit'], dmg=a['dmg'], type=a['type'],
               melee=a.get('melee', False) and melee_ok and not (a.get('ranged') and t.role == 'back'),
               magic=a.get('magic', False), extra=list(a.get('extra', [])))
    if m.martial_adv and not m.cond.get('ma_used') and any(x is not m and x.up for x in enc.mons):
        atk['extra'].append(dict(dmg=m.martial_adv, type=a['type'])); m.cond['ma_used'] = True
    if m.sneak and not m.cond.get('ma_used') and (any(x is not m and x.up for x in enc.mons) or attack_adv(enc, m, t, atk) > 0):
        atk['extra'].append(dict(dmg=m.sneak, type=a['type'])); m.cond['ma_used'] = True
    if m.charge and enc.round == 1 and not m.cond.get('charged') and atk['melee']:
        atk['extra'].append(dict(dmg=m.charge, type=a['type'])); m.cond['charged'] = True
    if a.get('rider'):
        r = a['rider']
        atk['on_hit'] = lambda enc_, m_, t_, dealt, crit: apply_rider(enc_, m_, t_, r, dealt)
    return attack(enc, m, t, atk)

def do_save(m, enc, a, t):
    tg = area_targets(m, enc, t, a.get('aoe', 1))
    log(f"    {m.name} uses {a['name']} on {', '.join(x.name for x in tg)}")
    if a.get('dmg') and a['dmg'] != '0':
        dmg = a['dmg'] + ('+' + a['dmg2'] if a.get('dmg2') else '')
        DICE.clear(); rolled = roll(dmg)
        for x in tg:
            if x.dead: continue
            ok = make_save(x, a['save'], a['dc'], magic=a.get('spell', False), enc=enc)
            amt = (rolled // 2 if a.get('half', True) else 0) if ok else rolled
            if a['save'] == 'dex' and a.get('half', True) and 'evasion' in x.tags: amt = 0 if ok else rolled // 2
            apply_dmg(x, amt, a['type'], True, m, enc)
            if amt: after_damage(enc, x, amt)
            if not ok and a.get('cond') and not x.dead: apply_cond(m, x, a)
    else:
        for x in tg:
            if x.dead: continue
            if not make_save(x, a['save'], a['dc'], magic=a.get('spell', False), enc=enc): apply_cond(m, x, a)

def apply_cond(m, x, a):
    c = a['cond']
    if c in x.cond_imm: return
    if c == 'prone': x.cond['prone'] = True
    elif c == 'lost_turn': x.cond['lost_turn'] = True
    elif a.get('repeat'): x.cond[c] = ('save', a['dc'], a['repeat'])
    else: x.cond[c] = 10 if c in ('incap', 'feared', 'banished', 'faerie', 'baned', 'slowed', 'enfeebled', 'blinded') else 1
    if a.get('conc'): x.cond['src_' + c] = (m, a['name'], c)
    if a.get('wake'): x.cond['wake_on_hurt'] = c
    log(f"    {x.name} is {c} ({a['name']})")

def do_spell(m, enc, o, t):
    spend(m, o)
    if o.get('conc'):
        end_conc(m, enc); m.conc = o['name']
    k = o['kind']
    log(f"    {m.name} casts {o['name']}")
    if k == 'atk':
        for _ in range(o.get('n', 1)):
            if not t.up:
                ts = enc.enemies(m)
                if not ts: return
                t = R.choice(ts)
            h, c, d = attack(enc, m, t, dict(name=o['name'], hit=o['hit'], dmg=o['dmg'], type=o['type'], magic=True, melee=o.get('melee', False)))
            if h and o.get('guided') and t.up: t.cond['guided'] = True
    elif k in ('save', 'cond'):
        do_save(m, enc, dict(o, name=o['name'], spell=True), t)
    elif k == 'auto':
        for _ in range(o.get('n', 1)):
            if not t.up:
                ts = enc.enemies(m)
                if not ts: return
                t = R.choice(ts)
            dl = apply_dmg(t, roll(o['dmg']), o['type'], True, m, enc); after_damage(enc, t, dl)
    elif k == 'aura':
        m.aura_dmg = o['dmg']; m.aura_type = o['type']; m.spell_dc = o['dc']
    elif k == 'spirit':
        m.spirit = dict(name='spiritual weapon', hit=o['hit'], dmg=o['dmg'], type=o['type'], magic=True)

def heal_option(m, enc):
    hurt = [x for x in enc.mons if x.up and x.hp < x.maxhp * 0.5]
    if not hurt: return None
    best = None
    for o in m.spell_opts:
        if o['kind'] == 'heal' and usable(m, o):
            v = avg(o['dice']) * (len(hurt) if o['target'] == 'all' else 1)
            if best is None or v > best[0]: best = (v, o)
    for a in m.actions.values():
        if a.get('kind') == 'heal' and (not a.get('per_day') or a.get('left', 0) > 0):
            v = avg(a['dice'])
            if best is None or v > best[0]: best = (v, dict(a, kind='heal_action'))
    return best

def do_heal(m, enc, o):
    hurt = sorted([x for x in enc.mons if x.up and x.hp < x.maxhp], key=lambda x: x.hp / x.maxhp)
    if o['kind'] == 'heal_action':
        if o.get('per_day'): m.actions[o['name']]['left'] -= 1
        heal(m if not hurt else hurt[0], roll(o['dice']), enc); return
    spend(m, o)
    for x in (hurt if o['target'] == 'all' else hurt[:1]):
        heal(x, roll(o['dice']), enc)
    log(f"    {m.name} casts {o['name']}")

def _plans(m, enc):
    """Everything the monster could do this turn: (label, steps). A step is ('act', action) or ('spell', option)."""
    out = []
    for p in m.plans:
        steps = []
        for n, c in p:
            a = m.actions[n]
            if (a.get('recharge') or a.get('per_day')) and not _ready(a): continue
            steps += [('act', a)] * c
        if steps: out.append(('multiattack', steps))
    for a in m.actions.values():
        if a.get('kind') in ('attack', 'save') and _ready(a): out.append((a['name'], [('act', a)]))
    for o in m.spell_opts:
        if o['kind'] in ('atk', 'save', 'cond', 'auto', 'aura', 'spirit') and not o.get('bonus') and usable(m, o):
            out.append((o['name'], [('spell', o)]))
    return out

def _ready(a):
    if a.get('recharge'): return a.get('ready', True)
    if a.get('per_day'): return a.get('left', 0) > 0
    return True

def _step_ev(m, enc, kind, x, t):
    if kind == 'act':
        if x['kind'] == 'attack': return attack_ev(m, enc, x, t)
        if x['kind'] == 'save': return save_ev(m, enc, x, t)
        return 0
    v = option_ev(m, enc, x, t)
    c = x.get('cost')
    if c and c[0] == 'slot': v *= 0.9 if 'boss' in m.tags else 0.8
    if c and c[0] == 'day': v *= 0.85
    if x.get('conc') and m.conc: v *= 0.5
    return v

def _plan_ev(m, enc, steps):
    ts = enc.enemies(m)
    if not ts: return 0, []
    total = 0; chosen = []
    for kind, x in steps:
        t = pick_target(m, enc, lambda t: _step_ev(m, enc, kind, x, t)) if m.smart else max(ts, key=lambda t: _step_ev(m, enc, kind, x, t) * (1.3 if t.role == 'front' else 1))
        total += _step_ev(m, enc, kind, x, t); chosen.append((kind, x, t))
    return total, chosen

def _turn(self, enc):
    m = self
    m.cond.pop('ma_used', None)
    fa = getattr(m, 'flee_at', 0)
    buddy = getattr(m, 'flee_if_ally_dies', False) and any(x.dead and not getattr(x, 'fled', False) for x in enc.mons if x is not m)
    if (fa and (fa >= 2 or (m.hp < m.maxhp if fa >= 1 else m.hp <= m.maxhp * fa)) or buddy) and enc.round >= getattr(m, 'flee_after', 0):   # morale
        m.fled = True; m.dead = True; log(f"    {m.name} breaks off and flees ({m.hp} HP)"); return
    if 'reckless' in m.tags and any(t.role == 'front' for t in enc.enemies(m)): m.cond['reckless'] = True
    if getattr(m, 'leg_n', 0): m.leg = m.leg_n
    if getattr(m, 'regen', 0) and m.hp < m.maxhp:
        if not (m.cond.get('took', set()) & set(m.regen_stop)): m.hp = min(m.maxhp, m.hp + m.regen)
    m.cond.pop('took', None)
    for a in m.actions.values():
        if a.get('recharge') and not a.get('ready') and R.randint(1, 6) >= a['recharge']: a['ready'] = True
    if not enc.enemies(m): return
    h = heal_option(m, enc)
    if h and h[0] >= 8 and R.random() < 0.7:
        do_heal(m, enc, h[1]); _bonus(m, enc); return
    best = None
    for label, steps in _plans(m, enc):
        v, chosen = _plan_ev(m, enc, steps)
        v *= R.uniform(0.9, 1.1)
        if best is None or v > best[0]: best = (v, label, chosen)
    if best:
        for kind, x, t in best[2]:
            if not t.up:
                ts = enc.enemies(m)
                if not ts: break
                t = pick_target(m, enc, lambda t: _step_ev(m, enc, kind, x, t)) if m.smart else pick_front(enc, m)
                if t is None: break
            if kind == 'act':
                if x.get('recharge'): x['ready'] = False
                if x.get('per_day'): x['left'] -= 1
                if x['kind'] == 'attack': do_attack(m, enc, x, t)
                else: do_save(m, enc, x, t)
            else:
                do_spell(m, enc, x, t)
    _bonus(m, enc)

def _bonus(m, enc):
    ts = enc.enemies(m)
    if not ts: return
    sp = getattr(m, 'spirit', None)
    if sp:
        t = pick_target(m, enc, lambda t: p_hit(sp['hit'], t.ac) * avg(sp['dmg'])) if m.smart else R.choice(ts)
        attack(enc, m, t, sp); return
    for o in m.spell_opts:
        if o.get('bonus') and o['kind'] in ('spirit',) and usable(m, o) and not sp:
            do_spell(m, enc, o, ts[0]); return
        if o.get('bonus') and o['kind'] == 'heal' and usable(m, o):
            hurt = [x for x in enc.mons if x.up and x.hp < x.maxhp * 0.4]
            if hurt: do_heal(m, enc, o); return
    for a in m.bonus_actions:
        if a['kind'] == 'attack' and _ready(a):
            t = pick_target(m, enc, lambda t: attack_ev(m, enc, a, t)) if m.smart else pick_front(enc, m)
            if t: do_attack(m, enc, a, t); return

def _legendary(self, enc, after):
    m = self
    if m.leg <= 0 or after.side != 'pc' or not m.up or m.cond.get('incap') or m.cond.get('paralyzed') or m.cond.get('stunned'): return
    if R.random() < 0.35: return
    ts = enc.enemies(m)
    if not ts: return
    best = None
    for a in m.leg_opts:
        if a['cost'] > m.leg: continue
        x = a
        if a['kind'] == 'ref':
            x = m.actions.get(a.get('target'))
            if not x: continue
        if a['kind'] == 'cantrip':
            cs = [o for o in m.spell_opts if o.get('level') == 0 and o['kind'] in ('atk', 'save')]
            if not cs: continue
            x = max(cs, key=lambda o: max(option_ev(m, enc, o, t) for t in ts)); kind = 'spell'
        else:
            kind = 'act'
        v, chosen = _plan_ev(m, enc, [(kind, x)])
        v /= a['cost']
        if best is None or v > best[0]: best = (v, a, chosen)
    if not best or best[0] <= 0: return
    _, a, chosen = best
    m.leg -= a['cost']
    for kind, x, t in chosen:
        log(f"    {m.name} legendary action: {a['name']}")
        if kind == 'spell': do_spell(m, enc, x, t)
        elif x['kind'] == 'attack': do_attack(m, enc, x, t)
        else: do_save(m, enc, x, t)

def _death_burst(self, enc):
    b = self.spec['kw']['death_burst']
    near = [p for p in enc.pcs if p.up and p.role == 'front' and R.random() < 0.6]
    if near:
        log(f"    {self.name} bursts as it dies")
        save_effect(enc, self, near, b['save'], b['dc'], b['dmg'], b['type'], spell=False)

def _regen_down_turn(self, enc):
    if self.cond.get('took', set()) & set(self.regen_stop):
        self.dead = True; self.down = False; log(f"    ✗ {self.name} burns and stays down"); return
    self.down = False; self.hp = self.regen; self.cond.pop('took', None)
    log(f"    {self.name} regenerates and gets back up ({self.hp} HP)")
