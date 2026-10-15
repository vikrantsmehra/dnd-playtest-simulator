"""Terrain: where the fight happens, in zones rather than squares.

A room (or one fight) can declare terrain=dict(...). Nothing here applies unless it does, so fights without terrain
play exactly as before. Fields:

  distance   feet between the two sides when the fight starts (default 0: already in reach). Melee can't connect
             until the gap is closed; each side that wants melee closes it at its speed, halved on difficult ground.
             A melee creature that can't reach spends its turn moving; anyone with a ranged option uses it.
  difficult  True, or 'party' / 'monsters' for one side only: halves closing speed (waist-deep water, sand, rubble)
  elevated   'monsters' or 'party': that side holds a ledge, gallery or rooftop. Melee from below needs a climb first
             (an Athletics check against climb_dc, default 12, using the turn); ranged attacks work as normal.
  chokepoint how many creatures per side can be in melee at once (a corridor, a doorway, a bridge)
  cover      dict(party=2, monsters=5): AC bonus against ranged attacks for that side (half cover 2, three-quarters 5)
  light      'bright' (default), 'dim' or 'dark'. In the dark with no light on either side (party_light, default True;
             monster_light), a creature without darkvision attacks with disadvantage and is attacked with advantage
  space      'cramped' (area effects catch more of a group) or 'open' (fewer); default 'normal'
  hazard     dict(chance=0.2, save=('str', 12), dmg='1d6', type='bludgeoning', cond='prone', who='front'): each round,
             each creature it applies to has that chance of having to save against it
"""
import math
from .dice import R, roll, log

DARKVISION_RACES = ('dwarf', 'elf', 'half-orc', 'orc', 'tiefling', 'gnome', 'half-elf', 'tabaxi', 'kobold', 'drow',
                    'genasi', 'goblin', 'hobgoblin', 'bugbear', 'aasimar', 'changeling', 'shadar-kai', 'warforged')

class Terrain:
    def __init__(s, spec):
        s.spec = dict(spec or {})
        g = s.spec.get
        s.distance = g('distance', 0); s.difficult = g('difficult', False); s.elevated = g('elevated')
        s.climb_dc = g('climb_dc', 12); s.choke = g('chokepoint'); s.cover = g('cover', {}) or {}
        s.light = g('light', 'bright'); s.party_light = g('party_light', True); s.monster_light = g('monster_light', False)
        s.space = g('space', 'normal'); s.hazard = g('hazard')
        s.engage_round = 1
        s.engaged = {'pc': set(), 'mon': set()}

    def setup(s, enc):
        """Work out when melee can first connect: both sides that want melee close the gap at their speed."""
        if not s.distance: return
        def closes(side):
            cs = enc.pcs if side == 'pc' else enc.mons
            if not any(c.role == 'front' for c in cs if not c.dead): return 0
            sp = 30
            if s.difficult is True or s.difficult == ('party' if side == 'pc' else 'monsters'): sp //= 2
            return sp
        per_round = closes('pc') + closes('mon')
        one = max(closes('pc'), closes('mon'))           # a creature can move this far and still attack in the same turn
        if not per_round: s.engage_round = 99
        elif s.distance <= one: s.engage_round = 1
        else: s.engage_round = 1 + math.ceil((s.distance - one) / per_round)
        log(f"    terrain: {s.distance} ft apart, melee from round {s.engage_round}")

    def side_name(s, c): return 'party' if c.side == 'pc' else 'monsters'

    def can_melee(s, enc, a, t):
        if enc.round < s.engage_round: return False
        if s.elevated and s.side_name(t) == s.elevated and s.side_name(a) != s.elevated and not a.cond.get('climbed'):
            return False
        if s.choke:
            mine = s.engaged[a.side]
            live = {x for x in mine if x.up}
            if a not in live and len(live) >= s.choke: return False
        return True

    def note_melee(s, a):
        if s.choke: s.engaged[a.side].add(a)

    def ranged_cover(s, t):
        return s.cover.get(s.side_name(t), 0)

    def sees(s, c):
        """A light on either side lights the fight for everyone in it; in true darkness only darkvision sees."""
        if s.light != 'dark' or s.party_light or s.monster_light: return True
        return getattr(c, 'darkvision', False)

    def adv(s, enc, a, t):
        """Advantage tally from the light."""
        if s.light != 'dark': return 0
        return (0 if s.sees(a) else -1) + (0 if s.sees(t) else 1)

    def aoe_scale(s):
        return 1.3 if s.space == 'cramped' else 0.75 if s.space == 'open' else 1.0

    def climb(s, enc, c):
        """A melee creature below a held ledge spends its turn climbing. Returns True if it used the turn."""
        if not s.elevated or s.side_name(c) == s.elevated or c.cond.get('climbed') or c.role != 'front': return False
        from .creature import check
        foes = enc.enemies(c)
        if not foes or any(s.can_melee(enc, c, f) for f in foes): return False
        if c.side == 'pc':
            ranged = [o for o in c.options(enc) if o.get('kind') == 'atk' and not o.get('melee')] if hasattr(c, 'options') else []
            if ranged and max(o.get('n', 1) * o['hit'] for o in ranged) >= max((o.get('n', 1) * o['hit'] for o in c.options(enc) if o.get('melee')), default=0):
                return False
        if check(c, 'Ath', ab='str', dc=s.climb_dc): c.cond['climbed'] = True; log(f"    {c.name} climbs up to the high ground")
        else: log(f"    {c.name} fails to climb")
        return True

    def round_hazard(s, enc):
        h = s.hazard
        if not h: return
        from .creature import make_save, apply_dmg
        who = h.get('who', 'front')
        for c in list(enc.pcs) + list(enc.mons):
            if not c.up or (who == 'front' and c.role != 'front') or (who in ('party', 'monsters') and s.side_name(c) != who): continue
            if R.random() >= h.get('chance', 0.25): continue
            ab, dc = h.get('save', ('dex', 12))
            if not make_save(c, ab, dc, enc=enc):
                if h.get('dmg'): apply_dmg(c, roll(h['dmg']), h.get('type', 'bludgeoning'), True, None, enc)
                if h.get('cond') and h['cond'] not in c.cond_imm: c.cond[h['cond']] = True if h['cond'] == 'prone' else 1
                log(f"    {c.name} is caught by the {h.get('name', 'hazard')}")
