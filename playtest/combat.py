"""Attack resolution, reactions, area effects and the encounter loop."""
from .creature import *
from . import hooks as H

# ---------------- attack resolution ----------------
def attack_adv(enc, a, t, atk):
    adv = 0
    melee = atk.get('melee', False)
    if H.HOOKS.get('attack_adv'): adv += H.total('attack_adv', enc, a, t, atk)
    if t.cond.get('invisible') and not t.cond.get('faerie'): adv -= 1
    if a.cond.get('invisible'): adv += 1
    if t.cond.get('restrained') or t.cond.get('quicksand') or t.cond.get('paralyzed') or t.cond.get('incap') or t.cond.get('faerie') or t.cond.get('guided'):
        adv += 1
    if t.cond.get('stunned') or t.cond.get('blinded') or t.cond.get('asleep'): adv += 1
    if a.cond.get('blinded'): adv -= 1
    if t.down: adv += 1 if melee else -1
    if t.cond.get('prone'): adv += 1 if melee else -1
    if a.cond.get('frightened') or a.cond.get('poisoned') or a.cond.get('restrained') or a.cond.get('quicksand') or a.cond.get('prone'):
        adv -= 1
    if a.exh >= 3: adv -= 1
    if a.cond.get('reckless') and melee: adv += 1
    if t.cond.get('reckless'): adv += 1
    if a.cond.get('vow') is t: adv += 1
    if t.cond.get('grovel_round', -1) >= enc.round and a.side == 'pc': adv += 1
    if t.cond.get('pfeg') and 'undead' in a.tags: adv -= 1
    if t.cond.get('blur'): adv -= 1
    if t.cond.get('dodge'): adv -= 1
    if a.cond.get('mocked'): adv -= 1; a.cond.pop('mocked')
    if atk.get('adv_first') and not t.cond.get('acted'): adv += 1
    if atk.get('ranged_disadv'): adv -= 1
    if 'pack_tactics' in a.tags and a.side == 'mon' and any(m is not a and m.up for m in enc.mons): adv += 1
    if enc.terrain: adv += enc.terrain.adv(enc, a, t)
    return net(adv)

def attack(enc, a, t, atk, adv_extra=0):
    """Returns (hit, crit, dealt). atk keys: name, hit, dmg, type, magic, melee, extra(list), crit_range."""
    if t.dead: return (False, False, 0)
    if 'among_dead' in t.tags and 'undead' in a.tags and a.side == 'mon':
        saved = t.__dict__.setdefault('ad_saved', set())
        if id(a) not in saved:
            if make_save(a, 'wis', getattr(t, 'ad_dc', 14)): saved.add(id(a))
            else:
                log(f"      {a.name} can't bring itself to attack {t.name} (Among the Dead)"); return (False, False, 0)
    adv = net(attack_adv(enc, a, t, atk) + adv_extra)
    nat = d20(adv, a.lucky)
    natstr = LAST_D20[0]
    crit_range = atk.get('crit_range', 20)
    if t.cond.get('guided'): t.cond.pop('guided')
    if nat == 1:
        if VERBOSE[0]: log(f"      {a.name} {atk.get('name','attack')} → {t.name}: d20 {natstr} = natural 1, miss")
        return (False, False, 0)
    bl = roll('1d4') if a.cond.get('bless') else 0
    if a.cond.get('baned'): bl -= roll('1d4')
    bonus = atk['hit'] + bl
    tot = nat + bonus
    auto_crit = (atk.get('melee') and (t.cond.get('paralyzed') or t.cond.get('asleep') or t.down))
    crit = nat >= crit_range
    if enc.terrain:
        if atk.get('melee'): enc.terrain.note_melee(a)
        else: tot -= enc.terrain.ranged_cover(t)          # cover adds to AC against ranged attacks
    hit = crit or tot >= t.ac
    # target-side reactions that change hit
    if hit and not crit and t.side == 'pc':
        hit = pc_hit_reactions(enc, a, t, tot)
    if hit and not crit and t.side == 'mon':
        if t.uses.get('parry', 0) and atk.get('melee') and tot < t.ac + getattr(t, 'parry_bonus', 3):
            t.uses['parry'] = 0; hit = False
        elif t.uses.get('shield_slots', 0) and t.reaction and tot < t.ac + 5:
            t.uses['shield_slots'] -= 1; t.reaction = False; t.cond['ac_bonus'] = 5; hit = False
    if hit and t.side == 'mon' and t.cond.get('ac_bonus') and tot < t.ac:
        hit = False
    if not hit:
        if VERBOSE[0]: log(f"      {a.name} {atk.get('name','attack')} → {t.name}: d20 {natstr} {atk['hit']:+d}{f' +{bl} bless' if bl else ''} = {tot} vs AC {t.ac} → miss")
        if t.side == 'pc' and atk.get('melee'): pc_on_missed(enc, a, t)
        return (False, False, 0)
    crit = crit or bool(auto_crit)
    DICE.clear()
    dmg = roll(atk['dmg'], crit)
    if a.cond.get('enfeebled') and atk.get('weapon', a.side == 'mon'): dmg //= 2
    parts = [(dmg, atk['type'], atk.get('magic', False))]
    for e in atk.get('extra', ()):
        parts.append((roll(e['dmg'], crit), e['type'], True))
    if a.side == 'pc':
        parts += a.on_hit(enc, t, atk, crit)
    # damage-reducing reactions
    if t.side == 'pc':
        parts = pc_dmg_reactions(enc, a, t, atk, parts)
    elif getattr(t, 'uncanny_mon', False) and t.reaction and sum(p[0] for p in parts) >= 8:
        t.reaction = False; parts = [(p[0] // 2, p[1], p[2]) for p in parts]
    dealt = 0
    if VERBOSE[0]:
        log(f"      {a.name} {atk.get('name','attack')} → {t.name}: d20 {natstr} {atk['hit']:+d}{f' +{bl} bless' if bl else ''} = {tot} vs AC {t.ac} → {'CRIT' if crit else 'hit'}; damage {' + '.join(DICE)} = " +
            ', '.join(f"{amt} {typ}{'' if mg else ' (nonmagical)'}" for amt, typ, mg in parts))
    a.adjacent_crit = crit and atk.get('melee')
    for amt, typ, mg in parts:
        t.last_hit_type = typ; t.last_crit = crit; t.last_amt = amt
        dealt += apply_dmg(t, amt, typ, mg, a, enc, from_attack=True)
    a.adjacent_crit = False
    rt = getattr(t, 'retaliate', None)
    if rt and atk.get('melee') and not a.dead:                 # a body that shocks or burns whoever hits it
        apply_dmg(a, roll(rt['dmg']), rt['type'], True, t, enc)
    after_damage(enc, t, dealt)
    if a.side == 'pc': enc.dmg_by[a.name] = enc.dmg_by.get(a.name, 0) + dealt
    if a.side == 'mon' and atk.get('on_hit'): atk['on_hit'](enc, a, t, dealt, crit)
    return (True, crit, dealt)

def after_damage(enc, t, dealt):
    if dealt <= 0 or t.dead: return
    if H.HOOKS.get('after_damage'): H.each('after_damage', enc, t, dealt)
    if t.cond.get('turned'): t.cond.pop('turned')
    w = t.cond.pop('wake_on_hurt', None)
    if w: t.cond.pop(w, None)
    if t.cond.get('incap') and t.cond.get('laugh_dc'):
        if make_save(t, 'wis', t.cond['laugh_dc'], adv=1, magic=True): end_effect(enc, t, 'laugh')

def end_effect(enc, t, eff):
    if eff == 'laugh':
        t.cond.pop('incap', None); src = t.cond.pop('laugh_src', None); t.cond.pop('laugh_dc', None)
        if src and src.conc == 'laughter': src.conc = None

def pc_hit_reactions(enc, a, t, tot):
    """Shield spell, Cutting Words (ally bard). Return whether attack still hits."""
    if t.reaction and 'shield' in t.spells and tot < t.ac + 5 and t.slots_avail(1):
        t.spend_slot(1); t.reaction = False; t.cond['ac_bonus'] = 5
        log(f"    {t.name} casts shield")
        return tot >= t.ac
    for b in (enc.team_of(t) if getattr(enc, 'pvp', False) else enc.pcs):
        if b.up and b.reaction and getattr(b, 'cutting_words', False) and b.uses.get('inspo', 0) > 0 and tot - t.ac < 4:
            b.uses['inspo'] -= 1; b.reaction = False
            tot -= roll(getattr(b, 'inspo_die', '1d6'))
            log(f"    {b.name} Cutting Words")
            return tot >= t.ac
    return True

def pc_dmg_reactions(enc, a, t, atk, parts):
    total = sum(p[0] for p in parts)
    if not t.reaction or total <= 0: return parts
    if t.uses.get('rebuke', 0) > 0 and (a.side == 'mon' or getattr(enc, 'pvp', False)) and a is not t and a.up and total >= 6:
        t.uses['rebuke'] -= 1; t.reaction = False
        log(f"    {t.name} casts hellish rebuke")
        save_effect(enc, t, [a], 'dex', getattr(t, 'rebuke_dc', 12), '3d10', 'fire')
        return parts
    if t.uses.get('tomb', 0) > 0 and total >= t.hp + t.temp:      # Tomb of Levistus: 10 temp HP per warlock level
        t.uses['tomb'] -= 1; t.reaction = False; t.temp += 110; t.cond['lost_turn'] = True
        log(f"    {t.name} entombs himself in ice (Tomb of Levistus, 110 temp HP)")
        return parts
    if getattr(t, 'uncanny', False) and total >= 8:
        t.reaction = False; return [(p[0] // 2, p[1], p[2]) for p in parts]
    if getattr(t, 'parry_man', False) and atk.get('melee') and t.uses.get('sup', 0) > 0 and total >= 10:
        t.uses['sup'] -= 1; t.reaction = False
        red = roll('1d8') + 4
        return reduce_parts(parts, red)
    if t.uses.get('stone', 0) > 0 and total >= 12:
        t.uses['stone'] -= 1; t.reaction = False
        return reduce_parts(parts, roll('1d12') + getattr(t, 'stone_bonus', 2))
    return parts

def reduce_parts(parts, red):
    out = []
    for amt, typ, mg in parts:
        r = min(amt, red); red -= r; out.append((amt - r, typ, mg))
    return out

def pc_on_missed(enc, a, t):
    if getattr(t, 'riposte', False) and t.reaction and t.uses.get('sup', 0) > 0 and t.up and a.up:
        t.uses['sup'] -= 1; t.reaction = False
        atk = dict(t.melee_attack); atk['extra'] = list(atk.get('extra', [])) + [dict(dmg='1d8', type=atk['type'])]
        attack(enc, t, a, atk)

def save_effect(enc, src, targets, ab, dc, dmg, typ, half=True, magic=True, spell=True):
    tot = 0
    DICE.clear()
    rolled = roll(dmg)
    if VERBOSE[0]: log(f"      {src.name} area effect: {dmg} = {' + '.join(DICE)} = {rolled} {typ}, DC {dc} {ab.upper()} save")
    for t in targets:
        if t.dead: continue
        ok = make_save(t, ab, dc, magic=spell, enc=enc, lr_ok=avg(dmg) >= 10)
        amt = (rolled // 2 if half else 0) if ok else rolled
        if ab == 'dex' and half and 'evasion' in t.tags and not t.cond.get('incap'): amt = 0 if ok else rolled // 2
        if t.side == 'mon': t.last_hit_type = typ; t.last_crit = False; t.last_amt = amt
        tot += apply_dmg(t, amt, typ, magic, src, enc)
        if amt: after_damage(enc, t, amt)
    if src.side == 'pc': enc.dmg_by[src.name] = enc.dmg_by.get(src.name, 0) + tot
    return tot

# ---------------- encounter ----------------
class Encounter:
    """One fight. env carries the room's extras: 'objectives' (special actions PCs try before attacking), 'lair'
    (monsters with a lair_action act at the top of each round), 'retreat_ok', 'retreat_frac', 'pre' (a setup
    function), and anything a module's hooks need. reveal: the fight is lit by something that strips invisibility."""
    def __init__(s, pcs, mons, name, room='', reveal=False, importance='normal', arrivals=None, quicksand=0.0,
                 env=None):
        s.pcs = pcs; s.mons = list(mons); s.name = name; s.room = room
        s.reveal = reveal; s.importance = importance
        s.arrivals = arrivals or []            # list of (round, [monsters])
        s.quicksand = quicksand                # chance per round a front PC gets shoved into sinking sand
        s.env = env or {}
        s.round = 0; s.dmg_by = {}; s.drops = []; s.deaths = []
        s.order = []
        tr = s.env.get('terrain')
        if tr:
            from .terrain import Terrain
            s.terrain = Terrain(tr)
        else: s.terrain = None
        if H.HOOKS.get('encounter_init'): H.each('encounter_init', s)
        if reveal:
            for m in s.mons: m.cond.pop('invisible', None)
            for _, ms in s.arrivals:
                for m in ms: m.cond.pop('invisible', None)
    def note_drop(s, c): s.drops.append((s.room, c.name))
    def note_death(s, c): s.deaths.append((s.room, c.name))
    def enemies(s, c): return [m for m in (s.mons if c.side == 'pc' else s.pcs) if m.up and not m.cond.get('banished')]
    def foes_alive(s): return [m for m in s.mons if (m.up and not m.cond.get('banished')) or (m.down and not m.dead)]
    def over(s):
        oc = s.env.get('over')                     # a room's own end conditions: an objective done, a parley
        if oc:
            r = oc(s)
            if r == 'continue': return None
            if r: return r
        if H.HOOKS.get('encounter_over'):
            r = H.first('encounter_over', s)
            if r: return r
        if not s.foes_alive() and not any(r > s.round for r, _ in s.arrivals): return 'win'
        if not any(p.up for p in s.pcs): return 'lose'
        return None

def roll_init(enc, c):
    adv = 1 if 'nat_explorer' in c.tags else 0
    return d20(adv) + c.init_mod + R.random() * 0.01

def watch(enc):
    """Monsters that react to the state of the fight after every turn (a boss's bloodied phase, for example)."""
    for m in enc.mons:
        w = getattr(m, 'watch', None)
        if w: w(enc)

def run_encounter(enc, max_rounds=30):
    for c in enc.pcs: c.reaction = True; c.cond.pop('acted', None)
    for m in enc.mons: m.cond.pop('acted', None)
    enc.order = sorted(enc.pcs + enc.mons, key=lambda c: -roll_init(enc, c))
    log(f"  ⚔ {enc.name} [{', '.join(m.name for m in enc.mons)}] party in: " + ', '.join(f"{p.name.split()[0]} {p.hp}/{p.maxhp}" for p in enc.pcs if not p.dead))
    for p in enc.pcs:
        if p.up: p.encounter_start(enc)
    if enc.env.get('pre'): enc.env['pre'](enc)
    if enc.terrain: enc.terrain.setup(enc)
    while enc.round < max_rounds:
        enc.round += 1
        for rnd, ms in enc.arrivals:
            if rnd == enc.round:
                for m in ms:
                    enc.mons.append(m)
                    pos = R.randint(0, len(enc.order)); enc.order.insert(pos, m)
                log(f"    ++ arrives: {', '.join(m.name for m in ms)}")
        if enc.env.get('lair'):
            for m in list(enc.mons):
                la = getattr(m, 'lair_action', None)
                if la: la(enc)
        rs = enc.env.get('round_start')             # hazards and traps acting at the top of the round
        if rs: rs(enc)
        if enc.terrain: enc.terrain.round_hazard(enc)
        if enc.over(): break
        for c in list(enc.order):
            if enc.over(): break
            take_turn(enc, c)
            watch(enc)
            for m in enc.mons:
                if m.up and m is not c and hasattr(m, 'legendary'): m.legendary(enc, c)
            watch(enc)
        if enc.over(): break
        if enc.env.get('retreat_ok') and enc.round >= 2 and should_retreat(enc):
            enc.retreated = True; break
    res = 'retreat' if getattr(enc, 'retreated', False) else (enc.over() or 'timeout')
    if res not in ('win', 'lose', 'retreat', 'timeout'): enc.special = res
    log("    foes left: " + ', '.join(f"{m.name} {m.hp}" for m in enc.mons if not m.dead))
    log(f"  → {res} in {enc.round} rds | " + ', '.join(f"{p.name} {'DEAD' if p.dead else ('down' if p.down else f'{p.hp}/{p.maxhp}')}" for p in enc.pcs))
    if H.HOOKS.get('encounter_end'): H.each('encounter_end', enc, res)
    cleanup_after(enc, res)
    return res

def should_retreat(enc):
    alive = [p for p in enc.pcs if not p.dead]
    up = [p for p in alive if p.up]
    if not up: return False
    down = len(alive) - len(up)
    hp_up = sum(p.hp for p in up) / max(1, sum(p.maxhp for p in up))
    boss = [m for m in enc.mons if m.up and ('boss' in m.tags or 'lieutenant' in m.tags)]
    if not boss: return False
    bfrac = min(m.hp / m.maxhp for m in boss)
    if bfrac < 0.25 or H.first('retreat_veto', enc): return False
    return down >= enc.env.get('retreat_frac', 0.5) * len(alive) or (hp_up < 0.25 and len(up) <= 2)

def cleanup_after(enc, res):
    for p in enc.pcs:
        end_conc(p, enc)
        keep = {k: v for k, v in p.cond.items() if k in ('aid',)}
        p.cond = keep
        if res == 'win' and p.down and not p.dead:
            p.stable = True
            if not p.rot: p.down = False; p.hp = 0; p.ko = True   # stabilised by allies, 0 HP
        p.agathys = 0
        if p.temp and not getattr(p, 'keep_temp', False): p.temp = 0

def take_turn(enc, c):
    if c.dead: return
    if c.side == 'pc':
        if c.down:
            if c.stable: return
            r = d20(0, c.lucky)
            if r == 20: c.down = False; c.hp = 1; c.fails = c.succ = 0; log(f"    {c.name} nat 20 death save, up"); return
            if r == 1: c.fails += 2
            elif r >= 10: c.succ += 1
            else: c.fails += 1
            if c.fails >= 3: c.dead = True; log(f"    ✝ {c.name} fails death saves"); enc.note_death(c)
            elif c.succ >= 3: c.stable = True
            return
    else:
        if c.down:
            dt = getattr(c, 'down_turn', None)
            if dt: dt(enc)
            else: H.each('monster_down_turn', enc, c)
            return
    if not c.up: return
    # ---- start of turn ----
    c.reaction = True
    for k in [k for k in c.cond if k.startswith('src_')]:       # a condition held by someone's concentration
        src, spell, cond = c.cond[k]
        if not src.up or src.conc != spell: c.cond.pop(k); c.cond.pop(cond, None)
    for k in ('withdrawn', 'withdraw_used', 'reckless', 'raven_res', 'dodge', 'ac_bonus', 'prone', 'poisoned_stench'):
        c.cond.pop(k, None)
    if c.side == 'mon':
        c.uses['parry'] = c.max_uses.get('parry', 0)
        for p in enc.pcs:
            if p.up and p.conc == 'moonbeam' and getattr(p, 'moon_target', None) is c:
                save_effect(enc, p, [c], 'con', p.spell_dc, '2d10', 'radiant')
                if not c.up: return
        for p in enc.pcs:
            if p.up and p.conc == 'spirit guardians' and R.random() < 0.6:
                save_effect(enc, p, [c], 'wis', p.spell_dc, '3d8', 'radiant')
                if not c.up: return
    if c.cond.get('lost_turn'):
        c.cond.pop('lost_turn'); c.cond['acted'] = True; log(f"    {c.name} loses its turn"); return
    if c.cond.get('turned') or c.cond.get('incap') or c.cond.get('paralyzed') or c.cond.get('feared') or \
            c.cond.get('stunned') or c.cond.get('asleep') or c.cond.get('banished'):
        end_of_turn(enc, c); c.cond['acted'] = True; return
    if c.cond.get('slowed') and R.random() < 0.5:            # slow: one action or the other, never both
        end_of_turn(enc, c); c.cond['acted'] = True; return
    if c.side == 'pc':
        for m in enc.mons:                                      # a monster's spirit guardians
            if m.side == 'mon' and m.up and m.conc == 'spirit guardians' and c.role == 'front' and R.random() < 0.6:
                save_effect(enc, m, [c], 'wis', m.spell_dc, m.aura_dmg, m.aura_type)
                if not c.up: return
        stench = [m for m in enc.mons if m.up and 'stench' in m.tags]
        if stench and c.role == 'front' and not c.cond.get('stench_immune'):
            if make_save(c, 'con', getattr(stench[0], 'stench_dc', 10)): c.cond['stench_immune'] = True
            else: c.cond['poisoned'] = 1
        if enc.quicksand and c.role == 'front' and R.random() < enc.quicksand and any(m.up for m in enc.mons):
            if not make_save(c, 'str', 12): c.cond['quicksand'] = True; log(f"    {c.name} shoved into quicksand")
    if enc.terrain and enc.terrain.climb(enc, c):          # the turn goes on getting up to the high ground
        c.cond['acted'] = True; end_of_turn(enc, c); return
    c.turn(enc)
    c.cond['acted'] = True
    end_of_turn(enc, c)

def end_of_turn(enc, c):
    for k in list(c.cond):
        v = c.cond[k]
        if isinstance(v, tuple) and v and v[0] == 'save':
            _, dc, ab = v
            if make_save(c, ab, dc, magic=True):
                c.cond.pop(k)
        elif k in DURATION_CONDS and isinstance(v, int) and not isinstance(v, bool):
            c.cond[k] = v - 1
            if c.cond[k] <= 0: c.cond.pop(k)
    if c.cond.get('incap') and c.cond.get('laugh_dc'):
        if make_save(c, 'wis', c.cond['laugh_dc'], magic=True): end_effect(enc, c, 'laugh')
