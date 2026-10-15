"""Combat spells as options the engine can score and cast, for monsters and for builder-made PCs.

Each entry: level, kind, and the numbers. kind is
  'atk'   spell attack (n = beams/rays)         'save'  saving throw (aoe = how many it usually catches)
  'auto'  automatic hit (magic missile)         'heal'  healing (target: 'one' or 'all')
  'cond'  a save-or-suffer condition, no damage 'buff'  a party buff the caster's brain may use
  'aura'  concentration damage around the caster each round (spirit guardians)
cond: the condition on a failed save; 'repeat' means a new save at the end of each turn.
scale: cantrip dice grow at 5th/11th/17th level. up: extra dice per slot level above the spell's own.
Spells not listed here (utility, travel, social) are ignored in combat.
"""
from .dice import avg

def S(level, kind, **kw):
    d = dict(level=level, kind=kind); d.update(kw); return d

SPELLS = {
    # ---------------- cantrips ----------------
    'fire bolt': S(0, 'atk', dmg='1d10', type='fire', scale=True),
    'ray of frost': S(0, 'atk', dmg='1d8', type='cold', scale=True),
    'chill touch': S(0, 'atk', dmg='1d8', type='necrotic', scale=True),
    'eldritch blast': S(0, 'atk', dmg='1d10', type='force', beams=True),
    'produce flame': S(0, 'atk', dmg='1d8', type='fire', scale=True),
    'thorn whip': S(0, 'atk', dmg='1d6', type='piercing', scale=True),
    'shocking grasp': S(0, 'atk', dmg='1d8', type='lightning', scale=True, melee=True),
    'primal savagery': S(0, 'atk', dmg='1d10', type='acid', scale=True, melee=True),
    'sacred flame': S(0, 'save', save='dex', dmg='1d8', type='radiant', half=False, scale=True),
    'toll the dead': S(0, 'save', save='wis', dmg='1d12', type='necrotic', half=False, scale=True),
    'vicious mockery': S(0, 'save', save='wis', dmg='1d4', type='psychic', half=False, scale=True, mock=True),
    'poison spray': S(0, 'save', save='con', dmg='1d12', type='poison', half=False, scale=True),
    'acid splash': S(0, 'save', save='dex', dmg='1d6', type='acid', half=False, scale=True, aoe=2),
    'frostbite': S(0, 'save', save='con', dmg='1d6', type='cold', half=False, scale=True),
    'mind sliver': S(0, 'save', save='int', dmg='1d6', type='psychic', half=False, scale=True),
    'infestation': S(0, 'save', save='con', dmg='1d6', type='poison', half=False, scale=True),
    'word of radiance': S(0, 'save', save='con', dmg='1d6', type='radiant', half=False, scale=True, aoe=2),
    'sword burst': S(0, 'save', save='dex', dmg='1d6', type='force', half=False, scale=True, aoe=2),
    # ---------------- 1st ----------------
    'magic missile': S(1, 'auto', dmg='1d4+1', type='force', n=3, up_n=1),
    'burning hands': S(1, 'save', save='dex', dmg='3d6', type='fire', aoe=2.5, up='1d6'),
    'thunderwave': S(1, 'save', save='con', dmg='2d8', type='thunder', aoe=2, up='1d8'),
    'guiding bolt': S(1, 'atk', dmg='4d6', type='radiant', up='1d6', guided=True),
    'inflict wounds': S(1, 'atk', dmg='3d10', type='necrotic', up='1d10', melee=True),
    'chromatic orb': S(1, 'atk', dmg='3d8', type='fire', up='1d8'),
    'ice knife': S(1, 'save', save='dex', dmg='2d6+1d10', type='cold', aoe=2, up='1d6'),
    'witch bolt': S(1, 'atk', dmg='1d12', type='lightning', up='1d12'),
    'dissonant whispers': S(1, 'save', save='wis', dmg='3d6', type='psychic', up='1d6'),
    'arms of hadar': S(1, 'save', save='str', dmg='2d6', type='necrotic', aoe=2.5, up='1d6'),
    'earth tremor': S(1, 'save', save='dex', dmg='1d6', type='bludgeoning', aoe=2.5, up='1d6', cond='prone'),
    'catapult': S(1, 'save', save='dex', dmg='3d8', type='bludgeoning', half=False, up='1d8'),
    'hellish rebuke': S(1, 'reaction'),
    'cure wounds': S(1, 'heal', dice='1d8', up='1d8', target='one', touch=True),
    'healing word': S(1, 'heal', dice='1d4', up='1d4', target='one', bonus=True),
    'bless': S(1, 'buff', conc=True),
    'bane': S(1, 'cond', save='cha', cond='baned', aoe=2.5, conc=True),
    'shield': S(1, 'reaction'),
    'command': S(1, 'cond', save='wis', cond='lost_turn'),
    'sleep': S(1, 'sleep', dice='5d8', up='2d8'),
    'faerie fire': S(1, 'cond', save='dex', cond='faerie', aoe=2, conc=True),
    'entangle': S(1, 'cond', save='str', cond='restrained', repeat='str', aoe=2.5, conc=True),
    "tasha's hideous laughter": S(1, 'cond', save='wis', cond='incap', repeat='wis', conc=True),
    'hex': S(1, 'buff', conc=True, bonus=True),
    "hunter's mark": S(1, 'buff', conc=True, bonus=True),
    'shield of faith': S(1, 'buff', conc=True, bonus=True),
    'divine favor': S(1, 'buff', conc=True, bonus=True),
    'armor of agathys': S(1, 'buff'),
    'false life': S(1, 'buff'),
    'mage armor': S(1, 'prep'),
    'sanctuary': S(1, 'buff', bonus=True),
    'heroism': S(1, 'buff', conc=True),
    'protection from evil and good': S(1, 'buff', conc=True),
    'ray of sickness': S(1, 'atk', dmg='2d8', type='poison', up='1d8'),
    # ---------------- 2nd ----------------
    'scorching ray': S(2, 'atk', dmg='2d6', type='fire', n=3, up_n=1),
    'shatter': S(2, 'save', save='con', dmg='3d8', type='thunder', aoe=2.5, up='1d8'),
    "aganazzar's scorcher": S(2, 'save', save='dex', dmg='3d8', type='fire', aoe=2, up='1d8'),
    'hold person': S(2, 'cond', save='wis', cond='paralyzed', repeat='wis', conc=True, humanoid=True),
    'spiritual weapon': S(2, 'spirit', dmg='1d8', type='force', bonus=True),
    'moonbeam': S(2, 'save', save='con', dmg='2d10', type='radiant', conc=True, up='1d10'),
    'cloud of daggers': S(2, 'auto', dmg='4d4', type='slashing', conc=True, n=1),
    'flaming sphere': S(2, 'save', save='dex', dmg='2d6', type='fire', conc=True, up='1d6'),
    "melf's acid arrow": S(2, 'atk', dmg='4d4+2d4', type='acid', up='1d4'),
    'web': S(2, 'cond', save='dex', cond='restrained', repeat='str', aoe=2.5, conc=True),
    'blindness/deafness': S(2, 'cond', save='con', cond='blinded', repeat='con'),
    'phantasmal force': S(2, 'save', save='int', dmg='1d6', type='psychic', half=False, conc=True),
    'heat metal': S(2, 'auto', dmg='2d8', type='fire', conc=True, n=1),
    'ray of enfeeblement': S(2, 'cond', save='con', cond='enfeebled', conc=True),
    'mirror image': S(2, 'buff'),
    'blur': S(2, 'buff', conc=True),
    'invisibility': S(2, 'buff', conc=True),
    'misty step': S(2, 'none', bonus=True),
    'suggestion': S(2, 'cond', save='wis', cond='incap', conc=True),
    'crown of madness': S(2, 'cond', save='wis', cond='incap', repeat='wis', conc=True),
    'aid': S(2, 'prep'),
    'magic weapon': S(2, 'buff', conc=True, bonus=True),
    'see invisibility': S(2, 'buff'),
    'spike growth': S(2, 'auto', dmg='2d4', type='piercing', conc=True, n=2),
    'prayer of healing': S(2, 'none'),
    'darkness': S(2, 'none', conc=True),
    'silence': S(2, 'none', conc=True),
    # ---------------- 3rd ----------------
    'fireball': S(3, 'save', save='dex', dmg='8d6', type='fire', aoe=3.5, up='1d6'),
    'lightning bolt': S(3, 'save', save='dex', dmg='8d6', type='lightning', aoe=2.5, up='1d6'),
    'spirit guardians': S(3, 'aura', save='wis', dmg='3d8', type='radiant', conc=True, up='1d8'),
    'call lightning': S(3, 'save', save='dex', dmg='3d10', type='lightning', aoe=1.5, conc=True, up='1d10'),
    'erupting earth': S(3, 'save', save='dex', dmg='3d12', type='bludgeoning', aoe=2, up='1d12'),
    'vampiric touch': S(3, 'atk', dmg='3d6', type='necrotic', melee=True, conc=True, up='1d6', drain=True),
    'hypnotic pattern': S(3, 'cond', save='wis', cond='incap', aoe=3, conc=True, wake=True),
    'fear': S(3, 'cond', save='wis', cond='feared', repeat='wis', aoe=3, conc=True),
    'slow': S(3, 'cond', save='wis', cond='slowed', repeat='wis', aoe=3, conc=True),
    'stinking cloud': S(3, 'cond', save='con', cond='incap', aoe=2.5, conc=True),
    'bestow curse': S(3, 'cond', save='wis', cond='baned', conc=True),
    'mass healing word': S(3, 'heal', dice='1d4', up='1d4', target='all', bonus=True),
    'revivify': S(3, 'none'),
    'counterspell': S(3, 'reaction'),
    'dispel magic': S(3, 'none'),
    'haste': S(3, 'buff', conc=True),
    'fly': S(3, 'none', conc=True),
    'animate dead': S(3, 'none'),
    'beacon of hope': S(3, 'buff', conc=True),
    # ---------------- 4th ----------------
    'blight': S(4, 'save', save='con', dmg='8d8', type='necrotic', up='1d8'),
    'ice storm': S(4, 'save', save='dex', dmg='2d8+4d6', type='cold', aoe=3, up='1d8'),
    'wall of fire': S(4, 'save', save='dex', dmg='5d8', type='fire', aoe=2.5, conc=True, up='1d8'),
    "evard's black tentacles": S(4, 'save', save='dex', dmg='3d6', type='bludgeoning', aoe=2.5, conc=True, cond='restrained', repeat='str'),
    'phantasmal killer': S(4, 'save', save='wis', dmg='4d10', type='psychic', conc=True, up='1d10'),
    'banishment': S(4, 'cond', save='cha', cond='banished', conc=True),
    'polymorph': S(4, 'cond', save='wis', cond='banished', conc=True),
    'confusion': S(4, 'cond', save='wis', cond='incap', repeat='wis', aoe=3, conc=True),
    'greater invisibility': S(4, 'buff', conc=True),
    'stoneskin': S(4, 'buff', conc=True),
    'fire shield': S(4, 'buff'),
    'dimension door': S(4, 'none'),
    'death ward': S(4, 'buff'),
    # ---------------- 5th ----------------
    'cone of cold': S(5, 'save', save='con', dmg='8d8', type='cold', aoe=3.5, up='1d8'),
    'flame strike': S(5, 'save', save='dex', dmg='4d6+4d6', type='fire', aoe=2, up='1d6'),
    'insect plague': S(5, 'save', save='con', dmg='4d10', type='piercing', aoe=3, conc=True, up='1d10'),
    'cloudkill': S(5, 'save', save='con', dmg='5d8', type='poison', aoe=3, conc=True, up='1d8'),
    'destructive wave': S(5, 'save', save='con', dmg='5d6+5d6', type='thunder', aoe=3),
    'hold monster': S(5, 'cond', save='wis', cond='paralyzed', repeat='wis', conc=True),
    'dominate person': S(5, 'cond', save='wis', cond='banished', conc=True, humanoid=True),
    'mass cure wounds': S(5, 'heal', dice='3d8', up='1d8', target='all'),
    'contagion': S(5, 'atk', dmg='0', type='necrotic', melee=True, cond='poisoned'),
    'telekinesis': S(5, 'none', conc=True),
    # ---------------- 6th and up ----------------
    'chain lightning': S(6, 'save', save='dex', dmg='10d8', type='lightning', aoe=4),
    'disintegrate': S(6, 'save', save='dex', dmg='10d6+40', type='force', half=False),
    'circle of death': S(6, 'save', save='con', dmg='8d6', type='necrotic', aoe=4, up='2d6'),
    'harm': S(6, 'save', save='con', dmg='14d6', type='necrotic'),
    'heal': S(6, 'heal', dice='70', target='one'),
    'globe of invulnerability': S(6, 'buff', conc=True),
    'finger of death': S(7, 'save', save='con', dmg='7d8+30', type='necrotic'),
    'fire storm': S(7, 'save', save='dex', dmg='7d10', type='fire', aoe=4),
    'power word stun': S(8, 'cond', save='con', cond='stunned', repeat='con'),
    'sunburst': S(8, 'save', save='con', dmg='12d6', type='radiant', aoe=4, cond='blinded'),
    'power word kill': S(9, 'save', save='con', dmg='100', type='psychic', half=False),
    'meteor swarm': S(9, 'save', save='dex', dmg='20d6+20d6', type='fire', aoe=4),
}

def cantrip_dice(dice, level):
    """Cantrip damage at a caster level: one die, two at 5th, three at 11th, four at 17th."""
    n = 1 + (level >= 5) + (level >= 11) + (level >= 17)
    d = dice.split('d')
    return f"{int(d[0]) * n}d{d[1]}"

def upcast(dmg, up, steps):
    if not up or steps <= 0: return dmg
    return dmg + ''.join(f'+{up}' for _ in range(steps))

def option(name, attack, dc, caster_level, slot=None, mod=0):
    """The engine option dict for a spell, or None if it has no combat use the engine models."""
    sp = SPELLS.get(name.lower())
    if not sp or sp['kind'] in ('reaction', 'none', 'prep'): return None
    lvl = sp['level']; slot = slot or lvl
    o = dict(name=name.lower(), spell=True, level=lvl, magic=True)
    if lvl: o['cost'] = ('slot', slot)
    if sp.get('conc'): o['conc'] = True
    if sp.get('bonus'): o['bonus'] = True
    k = sp['kind']
    if k in ('atk', 'save', 'auto', 'aura', 'spirit'):
        dmg = sp['dmg']
        if sp.get('scale'): dmg = cantrip_dice(dmg, caster_level)
        dmg = upcast(dmg, sp.get('up'), slot - lvl)
        o.update(dmg=dmg, type=sp['type'])
    if k == 'atk':
        o.update(kind='atk', hit=attack, melee=sp.get('melee', False))
        if sp.get('beams'): o['n'] = 1 + (caster_level >= 5) + (caster_level >= 11) + (caster_level >= 17)
        elif sp.get('n'): o['n'] = sp['n'] + sp.get('up_n', 0) * (slot - lvl)
        if sp.get('guided'): o['guided'] = True
    elif k == 'save':
        o.update(kind='save', save=sp['save'], dc=dc, half=sp.get('half', True), aoe=sp.get('aoe', 1))
        if sp.get('cond'): o['cond'] = sp['cond']; o['repeat'] = sp.get('repeat')
        if sp.get('mock'): o['mock'] = True
    elif k == 'auto':
        o.update(kind='auto', n=sp.get('n', 1) + sp.get('up_n', 0) * (slot - lvl))
    elif k == 'cond':
        o.update(kind='cond', save=sp['save'], dc=dc, cond=sp['cond'], repeat=sp.get('repeat'), aoe=sp.get('aoe', 1),
                 humanoid=sp.get('humanoid', False), type='none', dmg='0', wake=sp.get('wake', False))
    elif k == 'heal':
        dice = upcast(sp['dice'], sp.get('up'), slot - lvl)
        o.update(kind='heal', dice=f"{dice}+{mod}" if mod and not dice.isdigit() else dice, target=sp['target'], type='none', dmg='0')
    elif k == 'aura':
        o.update(kind='aura', save=sp['save'], dc=dc)
    elif k == 'spirit':
        o.update(kind='spirit', hit=attack, dmg=f"{o['dmg']}+{mod}")
    elif k == 'sleep':
        o.update(kind='sleep', dice=upcast(sp['dice'], sp.get('up'), slot - lvl), type='none', dmg='0')
    elif k == 'buff':
        o.update(kind='buff', type='none', dmg='0')
    else:
        return None
    return o

# How much a condition is worth, in hit points of damage, when it lands on a foe for about a round
COND_VALUE = {'paralyzed': 22, 'stunned': 20, 'banished': 18, 'incap': 14, 'lost_turn': 10, 'feared': 10, 'restrained': 8,
              'blinded': 8, 'slowed': 7, 'frightened': 6, 'faerie': 5, 'prone': 4, 'poisoned': 4, 'baned': 4, 'enfeebled': 5,
              'grappled': 2}
