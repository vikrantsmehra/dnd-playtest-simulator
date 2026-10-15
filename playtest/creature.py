"""Creatures, saves, checks, damage and healing.

Abstractions (no grid):
  * Each PC is 'front' (melee) or 'back' (ranged/caster). Melee monsters attack front-liners
    first; area effects catch front-liners more often than back-liners.
  * Every attack, save, check, death save and damage roll is rolled.
"""
from .dice import *
from .dice import DICE, LAST_D20
from . import hooks as H

PHYS = ('bludgeoning', 'piercing', 'slashing')

# Rules switches. 'helpless_fail_str_dex': paralyzed, stunned and sleeping creatures fail Str and Dex saves (RAW).
# The original Arbiter's Grounds simulator didn't apply it to paralysis; set it False to play that way.
RULES = dict(helpless_fail_str_dex=True)
DURATION_CONDS = ('restrained', 'frightened', 'poisoned', 'paralyzed', 'stunned', 'blinded', 'baned', 'slowed', 'incap')

class Creature:
    def __init__(s, name, side, hp, ac, saves, **kw):
        s.name, s.side = name, side
        s.base_maxhp = hp; s.maxhp = hp; s.hp = hp
        s.ac_base = ac
        s.saves = dict(saves)
        s.skills = kw.pop('skills', {})
        s.res = set(kw.pop('res', ())); s.imm = set(kw.pop('imm', ())); s.vul = set(kw.pop('vul', ()))
        s.res_nonmag = kw.pop('res_nonmag', False)
        s.cond_imm = set(kw.pop('cond_imm', ()))
        s.tags = set(kw.pop('tags', ()))
        s.init_mod = kw.pop('init', 0)
        s.role = kw.pop('role', 'front')
        s.temp = 0; s.agathys = 0
        s.dead = False; s.down = False; s.stable = False
        s.fails = 0; s.succ = 0
        s.cond = {}
        s.conc = None
        s.reaction = True
        s.exh = 0
        s.rot = False                 # cursed so it can't regain hit points (mummy rot and the like)
        s.drained = 0
        s.lucky = kw.pop('lucky', False)
        s.uses = dict(kw.pop('uses', {}))
        s.max_uses = dict(s.uses)
        s.__dict__.update(kw)
    # ----- derived -----
    @property
    def up(s): return not s.dead and not s.down
    @property
    def ac(s):
        a = s.ac_base + s.cond.get('ac_bonus', 0) + (2 if s.cond.get('shield_of_faith') else 0)
        a += getattr(s, 'cloak', 0)
        return a
    def save_mod(s, ab): return s.saves.get(ab, 0) + (getattr(s, 'cloak', 0))
    def __repr__(s): return f"{s.name}[{s.hp}/{s.maxhp}]"

# ---------- saves / checks ----------
def make_save(c, ab, dc, adv=0, magic=False, enc=None, lr_ok=True):
    if c.dead: return True
    if c.down and ab in ('str', 'dex'): return False
    if ab in ('str', 'dex') and RULES['helpless_fail_str_dex'] and (c.cond.get('paralyzed') or c.cond.get('stunned') or c.cond.get('asleep')):
        return False
    if 'danger_sense' in c.tags and ab == 'dex' and not c.cond.get('incap'): adv += 1
    if c.cond.get('rage') and ab == 'str': adv += 1
    if 'magic_resistance' in c.tags and magic: adv += 1
    if c.exh >= 3: adv -= 1
    if c.cond.get('restrained') and ab == 'dex': adv -= 1
    if c.cond.get('unsettled'): bonus = -c.cond.pop('unsettled')
    else: bonus = 0
    if c.cond.get('bless'): bonus += roll('1d4')
    if c.cond.get('baned'): bonus -= roll('1d4')
    src = getattr(c, 'aura_src', None)
    if c.side == 'pc' and src is not None and src.up: bonus += getattr(src, 'aura', 1) or 1   # Aura of Protection
    r = d20(net(adv), c.lucky)
    tot = r + c.save_mod(ab) + bonus
    ok = tot >= dc
    if VERBOSE[0]: log(f"        {c.name} {ab.upper()} save: d20 {LAST_D20[0]} {c.save_mod(ab):+d}{f' {bonus:+d}' if bonus else ''} = {tot} vs DC {dc} → {'success' if ok else 'FAIL'}")
    if not ok and c.side == 'pc' and enc is not None:
        ok = inspire_rescue(c, tot, dc, enc)
    if not ok and c.side == 'mon' and lr_ok and c.uses.get('lr', 0) > 0:
        c.uses['lr'] -= 1; ok = True; log(f"    {c.name} uses Legendary Resistance")
    return ok

def inspire_rescue(c, tot, dc, enc):
    """A bard ally adds Bardic Inspiration (pre-granted model: spent reactively if it turns failure to success)."""
    if dc - tot > 6: return False
    team = enc.team_of(c) if getattr(enc, 'pvp', False) else enc.pcs
    for a in team:
        if a.up and a.uses.get('inspo', 0) > 0 and a is not c:
            if dc - tot <= 3 or (dc - tot <= 5 and R.random() < 0.5):
                a.uses['inspo'] -= 1
                b = roll(getattr(a, 'inspo_die', '1d6'))
                log(f"    {a.name} inspires {c.name} (+{b})")
                return tot + b >= dc
    return False

def check(c, skill=None, ab=None, dc=10, adv=0):
    mod = c.skills.get(skill, None) if skill else None
    if mod is None: mod = c.mods.get(ab, 0) if hasattr(c, 'mods') else 0
    if c.exh >= 1: adv -= 1
    if c.cond.get('rage') and (ab == 'str' or skill == 'Ath'): adv += 1
    r = d20(net(adv), getattr(c, 'lucky', False))
    bonus = roll('1d4') if c.cond.get('guidance') else 0
    ok = r + mod + bonus >= dc
    if VERBOSE[0]: log(f"        {c.name} {skill or ab} check: d20 {LAST_D20[0]} {mod:+d} = {r+mod+bonus} vs DC {dc} → {'success' if ok else 'fail'}")
    return ok


# ---------- damage ----------
def apply_dmg(t, amt, typ, magical=True, src=None, enc=None, from_attack=False, note=''):
    if t.dead or amt <= 0: return 0
    if typ in t.imm: return 0
    if getattr(t, 'imm_nonmag', False) and not magical and typ in PHYS: return 0
    mult = 1.0
    if typ in t.vul: mult *= 2
    resisted = typ in t.res or (t.res_nonmag and not magical and typ in PHYS) or \
        (t.cond.get('rage') and (typ in PHYS or (getattr(t, 'bear', False) and typ != 'psychic'))) or t.cond.get('raven_res') or \
        (t.cond.get('warding') and typ == t.cond.get('warding'))
    if t.cond.get('warding') == typ: return 0
    if resisted: mult *= 0.5
    amt = int(amt * mult)
    if t.temp:
        a = min(t.temp, amt); t.temp -= a; amt -= a
        if t.agathys and src is not None and from_attack and src.side != t.side:
            apply_dmg(src, 5 * t.agathys, 'cold', True, t, enc)
        if t.temp == 0: t.agathys = 0
    if amt <= 0: return 0
    if t.cond.get('asleep'): t.cond.pop('asleep')
    if getattr(t, 'regen', None): t.cond.setdefault('took', set()).add(typ)
    if t.side == 'pc' and t.down and enc is not None and getattr(enc, 'pvp', False):
        return 0
    if t.side == 'pc' and t.down:
        t.fails += 2 if from_attack and getattr(src, 'adjacent_crit', False) else 1
        t.stable = False
        if t.fails >= 3: t.dead = True; log(f"    ✝ {t.name} DIES (death saves)"); enc and enc.note_death(t)
        return amt
    t.hp -= amt
    # concentration
    if t.conc and t.hp > 0:
        if not make_save(t, 'con', max(10, amt // 2)): end_conc(t, enc)
    if t.hp <= 0:
        overflow = -t.hp
        if t.side == 'pc' and enc is not None and getattr(enc, 'pvp', False):
            if t.uses.get('relentless', 0) > 0:
                t.uses['relentless'] -= 1; t.hp = 1; log(f"    {t.name} Relentless Endurance")
            else:
                t.hp = 0; t.down = True; t.stable = True; log(f"    ↓ {t.name} is knocked out ({amt} {typ})")
                enc.note_drop(t)
            end_conc(t, enc)
            t.cond.pop('rage', None)
        elif t.side == 'pc':
            if overflow >= t.maxhp:
                t.dead = True; t.hp = 0; log(f"    ✝ {t.name} KILLED OUTRIGHT ({amt} {typ}{note})"); enc and enc.note_death(t)
            elif t.uses.get('relentless', 0) > 0:
                t.uses['relentless'] -= 1; t.hp = 1; log(f"    {t.name} Relentless Endurance")
            else:
                t.hp = 0; t.down = True; t.fails = 0; t.succ = 0; t.stable = bool(getattr(t, 'periapt', False))
                log(f"    ↓ {t.name} drops ({amt} {typ}{note})")
                if enc: enc.note_drop(t)
            end_conc(t, enc)
            t.cond.pop('rage', None)
            H.each('pc_dropped', t)
        else:
            t.hp = 0
            monster_zero(t, enc)
    return amt

def monster_zero(m, enc):
    if H.first('monster_zero', enc, m): return
    if getattr(m, 'regen', 0) and not (m.cond.get('took', set()) & set(getattr(m, 'regen_stop', ()))):
        m.down = True; log(f"    {m.name} drops, but it will regenerate unless burned"); return
    if 'fortitude' in m.tags and getattr(m, 'last_hit_type', '') != 'radiant' and not getattr(m, 'last_crit', False) \
            and make_save(m, 'con', 5 + getattr(m, 'last_amt', 0)):
        m.hp = 1; log(f"    {m.name} Undead Fortitude")
    else:
        m.dead = True; log(f"    ✗ {m.name} destroyed")
        for p in (enc.pcs if enc else []):
            if p.cond.get('hm_target') is m: p.cond['hm_free'] = True
        od = getattr(m, 'on_death', None)
        if od and enc: od(enc)

def end_conc(c, enc):
    if not c.conc: return
    sp = c.conc; c.conc = None
    if enc is None: return
    for x in enc.pcs + enc.mons:
        for k in list(x.cond):
            v = x.cond[k]
            if isinstance(v, tuple) and len(v) == 2 and v[0] == 'conc' and v[1] is c: x.cond.pop(k)
    c.cond.pop('hm_target', None); c.cond.pop('hex_target', None)
    log(f"    {c.name} loses concentration ({sp})")

def heal(t, amt, enc=None):
    if t.dead or getattr(t, 'rot', False): return 0
    was_down = t.down
    if t.down:
        t.down = False; t.hp = 0; t.fails = t.succ = 0; t.stable = False
    before = t.hp
    t.hp = min(t.maxhp, t.hp + amt)
    if was_down: log(f"    ↑ {t.name} back up ({t.hp})")
    return t.hp - before
