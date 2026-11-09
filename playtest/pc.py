"""The player-character base class: resources, rests, option scoring and the turn.

A PC subclass lists its options (attacks, spells as attack/save/auto-hit entries) and overrides the hooks it needs:
heal_action, buff_action, bonus_act, bonus_heal, on_hit, rider_ev. The base class picks the best option each turn by
expected damage against every foe, and spends slots according to how important the fight is.
"""
from .combat import *
from . import hooks as H

STATS = {}          # saves, ability modifiers and skills per character, keyed by name; filled by the roster
IMP = {'minor': 0, 'normal': 1, 'major': 2, 'boss': 3}
ORD = {1: '1st', 2: '2nd', 3: '3rd', 4: '4th', 5: '5th'}
# self-range cones, cubes and lines: in PvP these need you to close the distance, like melee
CLOSE_RANGE = {'burning hands', 'thunderwave', 'cold breath', 'acid breath', 'fire breath', "aganazzar's scorcher"}

class PC(Creature):
    def __init__(s, key, name, hp, ac, level, hd_die, role, slots=None, uses=None, spells=(), **kw):
        st = key if isinstance(key, dict) else STATS[key]
        super().__init__(name, 'pc', hp, ac, st['saves'], skills=st['skills'], role=role, uses=uses or {}, **kw)
        s.mods = st['mods']; s.level = level; s.hd_die = hd_die; s.hd = level; s.hd_max = level
        s.max_slots = dict(slots or {}); s.slots = dict(s.max_slots)
        s.pact = kw.get('pact', {}); s.max_pact = dict(s.pact)
        s.spells = set(spells)
        s.sr_keys = set(kw.get('sr_keys', ()))
        s.lamp_carrier = False; s.light_source = False
        s.potions = 0; s.ko = False
        s.prof = 2 + (level - 1) // 4
        s.sw_active = False
        s.periapt = False; s.cloak = 0
        s.lasting = {}                  # conditions that outlast a fight until the next long rest (poisoned for an hour)
        s.melee_attack = dict(name='dagger', kind='atk', hit=s.prof + max(s.mods['str'], s.mods['dex']), dmg=f"1d4+{max(s.mods['str'], s.mods['dex'])}",
                              type='piercing', melee=True, weapon=True, finesse=True)
    # ---------- resources ----------
    def slots_avail(s, lvl=1):
        return any(n > 0 for l, n in s.slots.items() if l >= lvl) or any(n > 0 for l, n in s.pact.items() if l >= lvl)
    def spend_slot(s, lvl=1, prefer_high=False):
        """Spend the lowest slot >= lvl (pact slots first since they recover on a short rest). Returns the level used."""
        for l in sorted(s.pact):
            if l >= lvl and s.pact[l] > 0: s.pact[l] -= 1; return l
        ls = sorted([l for l, n in s.slots.items() if l >= lvl and n > 0], reverse=prefer_high)
        if not ls: return 0
        s.slots[ls[0]] -= 1; return ls[0]
    def total_slots(s): return sum(s.slots.values()) + sum(s.pact.values())
    def may_spend(s, enc, lvl=1, purpose='damage'):
        imp = IMP[enc.importance]
        if purpose == 'heal': return True
        hp_frac = sum(p.hp for p in enc.pcs if not p.dead) / max(1, sum(p.maxhp for p in enc.pcs if not p.dead))
        reserve = getattr(s, 'heal_reserve', 0)
        left = s.total_slots()
        if imp >= 3: return left > (reserve // 2)
        if imp == 2: return left > reserve and (lvl == 1 or hp_frac < 0.6 or enc.round >= 3)
        if imp == 1: return left > reserve + 1 and hp_frac < 0.45
        return False
    # ---------- rests ----------
    def long_rest(s):
        s.drained = 0
        s.lasting = {}
        s.cond = {}
        s.maxhp = s.base_maxhp
        if not s.rot: s.hp = s.maxhp
        s.slots = dict(s.max_slots); s.pact = dict(s.max_pact)
        for k, v in s.max_uses.items(): s.uses[k] = v
        s.hd = min(s.hd_max, s.hd + max(1, s.hd_max // 2))
        s.exh = max(0, s.exh - 1)
        s.down = False; s.stable = False; s.ko = False
        if s.rot and s.hp <= 0: s.down = True; s.stable = True      # cursed: no HP back, still unconscious
        s.temp = 0; s.sw_active = False
    def short_rest(s, song=None, recover=True):
        """An hour's rest. recover=False skips Arcane Recovery (the 'arcane_recovery' setting)."""
        s.pact = dict(s.max_pact)
        if recover: s.arcane_recovery()
        for k in s.sr_keys:
            if k in s.max_uses: s.uses[k] = s.max_uses[k]
        if s.rot: return
        if s.down and not s.dead: s.down = False; s.hp = 0
        while s.hd > 0 and s.hp < s.maxhp * 0.85:
            s.hd -= 1
            h = roll(f'1{s.hd_die}') + s.mods['con']
            if s.periapt: h *= 2
            s.hp = min(s.maxhp, s.hp + max(1, h))
        if song and s.hp < s.maxhp: s.hp = min(s.maxhp, s.hp + roll(song))
        s.temp = 0; s.sw_active = False
    def arcane_recovery(s, dry=False):
        """Once a day, on a short rest: spent wizard slots back, lowest first, whose levels add up to no more than
        half the wizard level (rounded up), none of 6th level or higher. Returns the levels regained; dry=True only
        says what it would regain."""
        wiz = getattr(s, 'classes', {}).get('wizard', 0)
        if not wiz or s.uses.get('ar', 0) <= 0: return []
        budget = -(-wiz // 2); got = []; slots = dict(s.slots)
        for l in sorted(s.max_slots):
            while l <= 5 and budget >= l and slots.get(l, 0) < s.max_slots[l]:
                slots[l] = slots.get(l, 0) + 1; budget -= l; got.append(l)
        if got and not dry:
            s.slots = slots; s.uses['ar'] -= 1
            log(f"    {s.name} Arcane Recovery: regains " + ', '.join(f'a {ORD[l]}-level slot' for l in got))
        return got
    # ---------- helpers ----------
    def allies(s, enc): return [p for p in enc.pcs if not p.dead]
    def downed(s, enc): return [p for p in enc.pcs if p.down and not p.dead and not p.rot]
    def foes(s, enc): return [m for m in enc.mons if m.up]
    def piles(s, enc): return [m for m in enc.mons if m.down and not m.dead and ('rejoin' in m.tags or getattr(m, 'regen', 0))]
    def encounter_start(s, enc):
        s.sneak_used = False
        if s.lasting: s.cond.update(s.lasting)
    # ---------- option evaluation ----------
    def mult(s, t, typ, magic):
        if typ in t.imm: return 0
        if getattr(t, 'imm_nonmag', False) and not magic and typ in PHYS: return 0
        m = 1.0
        if typ in t.vul: m *= 2
        if typ in t.res or (t.res_nonmag and not magic and typ in PHYS): m *= 0.5
        return m
    def ev(s, enc, opt, t):
        if t.down:                      # a downed foe that will get back up unless it's finished off
            if getattr(t, 'regen', 0) and 'rejoin' not in t.tags:
                return 8.0 if opt['type'] in getattr(t, 'regen_stop', ()) and not (t.cond.get('took', set()) & set(t.regen_stop)) else 0
            v = H.first('ev_down_target', s, enc, opt, t)
            return v or 0
        if opt.get('melee') and 'flying' in t.tags and hasattr(t, 'reach_p') and R.random() > t.reach_p: return 0
        pvp_mult = 1.0
        close = opt.get('melee') or opt.get('name') in CLOSE_RANGE
        if getattr(enc, 'pvp', False) and close:
            if enc.round == 1: return 0                  # 60 ft of difficult sand between the teams
            if t.role == 'back' and any(x.up and x.role == 'front' for x in enc.mons): pvp_mult = 0.3
        if opt.get('needs_sight') and H.first('unseen', enc, s, t): return 0
        if enc.terrain and (opt.get('melee') or opt.get('name') in CLOSE_RANGE) and not enc.terrain.can_melee(enc, s, t): return 0
        typ, magic = opt['type'], opt.get('magic', False)
        if s.cond.get('magic_weapon') and opt.get('weapon'): magic = True
        m = s.mult(t, typ, magic)
        if opt['kind'] == 'atk':
            atk = dict(opt); adv = attack_adv(enc, s, t, atk)
            p = p_hit(opt['hit'] + (2.5 if s.cond.get('bless') else 0), t.ac, adv)
            per = avg(opt['dmg']) * m + s.rider_ev(enc, t, opt, p)
            val = opt.get('n', 1) * p * per
        elif opt['kind'] == 'save':
            ps = p_save(t.saves.get(opt['save'], 0), opt['dc'], 1 if ('magic_resistance' in t.tags) else 0)
            val = (1 - ps + (ps * 0.5 if opt.get('half') else 0)) * avg(opt['dmg']) * m
            if opt.get('aoe', 1) > 1:
                others = [x for x in s.foes(enc) if x is not t][:int(round(opt['aoe'])) - 1]
                val += sum((1 - p_save(x.saves.get(opt['save'], 0), opt['dc'])) * avg(opt['dmg']) * s.mult(x, typ, magic) for x in others) * (0.45 if getattr(enc, 'pvp', False) else 0.8)
        else:  # auto-hit (magic missile)
            val = avg(opt['dmg']) * m * opt.get('n', 1)
        val = min(val, t.hp + 4) * pvp_mult
        if 'priority' in t.tags: val *= 1.25
        if t.cond.get('turned'): val *= 0.1
        return val
    def rider_ev(s, enc, t, opt, p):
        return 0
    def pile_rider(s, opt):
        return 0
    def options(s, enc):
        return []
    def usable(s, enc, opt, bonus_cast=False):
        c = opt.get('cost')
        if bonus_cast and c and c[0] == 'slot': return False     # only cantrips after a bonus-action spell
        if not c: return True
        if c[0] == 'slot': return s.slots_avail(c[1]) and s.may_spend(enc, c[1])
        if c[0] == 'use': return s.uses.get(c[1], 0) > 0
        return True
    def best(s, enc, bonus_cast=False, opts=None, include_piles=True):
        opts = opts if opts is not None else [o for o in s.options(enc) if not o.get('bonus')]
        targets = s.foes(enc) + (s.piles(enc) if include_piles else [])
        bestv, bo, bt = 0, None, None
        for o in opts:
            ok = s.usable(enc, o, bonus_cast)
            for t in targets:
                if not ok:
                    c = o.get('cost')
                    if not (t.down and c and c[0] == 'slot' and not bonus_cast and s.slots_avail(c[1]) and c[1] <= 2): continue
                v = s.ev(enc, o, t)
                if o.get('cost') and o['cost'][0] == 'slot': v *= 0.8  # mild thrift
                if v > bestv: bestv, bo, bt = v, o, t
        return bo, bt, bestv
    def execute(s, enc, o, t):
        c = o.get('cost')
        if c:
            if c[0] == 'slot': s.spend_slot(c[1])
            elif c[0] == 'use': s.uses[c[1]] -= 1
        if o.get('conc'): end_conc(s, enc); s.conc = o['name']
        if t.down and getattr(t, 'regen', 0) and 'rejoin' not in t.tags:      # burning a downed regenerator
            if o['type'] in t.regen_stop and (o['kind'] != 'atk' or d20() + o['hit'] >= t.ac):
                t.cond.setdefault('took', set()).add(o['type']); log(f"    {s.name} burns the downed {t.name}")
            return
        if t.down and H.first('strike_down_target', s, enc, o, t): return
        if o['kind'] == 'atk':
            n = o.get('n', 1)
            for i in range(n):
                if not t.up:
                    nb = [x for x in s.foes(enc)]
                    if not nb: return
                    t = max(nb, key=lambda x: s.ev(enc, dict(o, n=1, cost=None), x))
                atk = dict(o)
                if s.cond.get('magic_weapon') and o.get('weapon'):
                    atk['magic'] = True; atk['hit'] = o['hit'] + 1; atk['dmg'] = o['dmg'] + '+1'
                h, cr, dl = attack(enc, s, t, atk)
                if h and o.get('after'): o['after'](enc, s, t)
        elif o['kind'] == 'save':
            k = int(round(o.get('aoe', 1)))
            tg = [t] + [x for x in s.foes(enc) if x is not t][:max(0, k - 1)] if k > 1 else [t]
            if k > 1:
                spread = 0.45 if getattr(enc, 'pvp', False) else 0.7      # PCs spread out more than monsters do
                if enc.terrain: spread = min(1.0, spread * enc.terrain.aoe_scale())
                tg = [t] + [x for x in s.foes(enc) if x is not t and R.random() < spread][:k - 1]
            save_effect(enc, s, tg, o['save'], o['dc'], o['dmg'], o['type'], half=o.get('half', True))
            if o.get('after'):
                for x in tg: o['after'](enc, s, x)
        else:
            for _ in range(o.get('n', 1)):
                if not t.up:
                    nb = s.foes(enc)
                    if not nb: return
                    t = R.choice(nb)
                dl = apply_dmg(t, roll(o['dmg']), o['type'], True, s, enc)
                after_damage(enc, t, dl)
                enc.dmg_by[s.name] = enc.dmg_by.get(s.name, 0) + dl
    # ---------- turn ----------
    def turn(s, enc):
        s.sneak_used = False; s.cs_used = False
        s.bonus_cast = False; s.bonus_used = False
        if s.cond.get('quicksand'):
            if check(s, 'Ath', dc=13): s.cond.pop('quicksand')
            s.bonus(enc); return
        if s.objective(enc): s.bonus(enc); return
        s.bonus(enc, pre=True)
        if not s.heal_action(enc):
            if not s.buff_action(enc):
                o, t, v = s.best(enc, bonus_cast=s.bonus_cast)
                if o: s.execute(enc, o, t)
                elif s.potions and any(p.down for p in enc.pcs): s.give_potion(enc)
        s.bonus(enc)
    def bonus(s, enc, pre=False):
        if s.bonus_used: return
        if s.bonus_heal(enc): s.bonus_used = True; return
        if s.bonus_act(enc, pre): s.bonus_used = True
    def bonus_heal(s, enc): return False
    def bonus_act(s, enc, pre): return False
    def heal_action(s, enc): return False
    def buff_action(s, enc): return False
    def give_potion(s, enc):
        d_ = s.downed(enc)
        if d_ and s.potions:
            s.potions -= 1; heal(d_[0], roll('2d4+2'), enc); return True
        return False
    def on_hit(s, enc, t, atk, crit):
        parts = []
        if s.cond.get('hm_target') is t and atk.get('weapon'): parts.append((roll('1d6', crit), atk['type'], True))
        if s.cond.get('hex_target') is t: parts.append((roll('1d6', crit), 'necrotic', True))
        if s.cond.get('divine_favor') and atk.get('weapon'): parts.append((roll('1d4', crit), 'radiant', True))
        return parts
    # objectives (room-specific actions)
    def objective(s, enc):
        for f in enc.env.get('objectives', ()):
            if f(enc, s): return True
        return False

# ---------- shared feature helpers ----------
def heal_target(enc, s, frac=0.3):
    d_ = [p for p in enc.pcs if p.down and not p.dead and not p.rot]
    if d_: return max(d_, key=lambda p: p.fails)
    hurt = [p for p in enc.pcs if p.up and not p.rot and p.hp < p.maxhp * frac]
    return min(hurt, key=lambda p: p.hp / p.maxhp) if hurt else None

def turn_undead(enc, s, dc, destroy_cr=0):
    n = 0
    for m in s.foes(enc):
        if 'undead' in m.tags and not m.cond.get('turned') and 'turn_immune' not in m.tags:
            if not make_save(m, 'wis', dc, adv=1 if 'turn_resist' in m.tags else 0, magic=False):
                if getattr(m, 'cr', 9) <= destroy_cr and 'rejoin' not in m.tags:
                    m.dead = True; log(f"    {m.name} destroyed by Destroy Undead")
                else: m.cond['turned'] = True
                n += 1
    log(f"    {s.name} Turn Undead: {n} turned")

def worth_turning(enc, s):
    und = [m for m in s.foes(enc) if 'undead' in m.tags and not m.cond.get('turned')]
    hp = sum(m.hp for m in und)
    return (len(und) >= 3 and hp >= 50) or (len(und) >= 2 and enc.importance in ('major', 'boss') and hp >= 60 and enc.round <= 2)

def potion_obj(enc, pc):
    """A front-liner pours a potion into a downed ally when no healer with a slot is standing."""
    dn = [p for p in enc.pcs if p.down and not p.dead and not p.rot]
    if dn and pc.potions and pc.role == 'front' and not any(getattr(p, 'healer', False) and p.up and p.slots_avail(1) for p in enc.pcs):
        pc.potions -= 1; heal(dn[0], roll('2d4+2'), enc); return True
    return False
