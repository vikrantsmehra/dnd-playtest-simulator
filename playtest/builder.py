"""The class builder: any character at any level, from their sheet (roster/sheets.json) or a short description
(roster/extra.json), played by their class's combat kit.

  build('Stock Cleric', 1)      the stock cleric at 1st level
  build('Stock Cleric', 7)      rescaled to 7th: proficiency, hit points, slots, attacks, an ASI to the main ability at
                                4th/8th/12th/16th/19th, and every combat feature the class gains on the way
  roster.party(['B Stock Cleric@7', 'B Stock Rogue@7'])   the same through the roster

What it models, per class (PHB core features plus the common subclass picks):
  barbarian  rage (+damage, resistance; Bear totem resists everything but psychic), reckless attack, danger sense,
             extra attack, brutal critical, Berserker frenzy
  bard       inspiration, cutting words (Lore), song of rest, font of inspiration, spells
  cleric     spells, turn/destroy undead, Life's bonus healing, divine strike, spiritual weapon, spirit guardians
  druid      spells (no wild shape)
  fighter    second wind, action surge, extra attacks, Champion crits, Battle Master manoeuvres, fighting styles
  monk       martial arts, flurry of blows, stunning strike, extra attack, evasion
  paladin    divine smite, lay on hands, aura of protection, improved smite, bless/shield of faith
  ranger     hunter's mark, colossus slayer, archery style, extra attack
  rogue      sneak attack, uncanny dodge, evasion
  sorcerer   spells, draconic resilience and elemental affinity
  warlock    pact slots, eldritch blast with agonizing blast, hex, armor of agathys
  wizard     spells, arcane recovery, potent cantrip
  artificer  spells, Artillerist cannon, Battle Smith defender
Races: stone's endurance, relentless endurance, lucky, breath weapons, hellish rebuke, damage resistances.

Everything a sheet doesn't say (prepared spells, subclass for a sheetless character, ability scores for one) is a
documented default in DEFAULT_SPELLS and roster/extra.json. Hand-built characters in roster/core.py stay as they are;
the builder is for everyone else and for any level.
"""
import os, re, json
from .pc import *
from .spells import SPELLS, option as spell_option, COND_VALUE
from . import hooks as H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HD = dict(barbarian=12, fighter=10, paladin=10, ranger=10, monk=8, rogue=8, cleric=8, druid=8, bard=8, warlock=8, artificer=8,
          sorcerer=6, wizard=6)
SAVES = dict(barbarian=('str', 'con'), bard=('dex', 'cha'), cleric=('wis', 'cha'), druid=('int', 'wis'), fighter=('str', 'con'),
             monk=('str', 'dex'), paladin=('wis', 'cha'), ranger=('str', 'dex'), rogue=('dex', 'int'), sorcerer=('con', 'cha'),
             warlock=('wis', 'cha'), wizard=('int', 'wis'), artificer=('con', 'int'))
CAST = dict(cleric='wis', druid='wis', ranger='wis', paladin='cha', bard='cha', sorcerer='cha', warlock='cha', wizard='int', artificer='int')
PRIMARY = dict(barbarian='str', fighter='str', paladin='str', ranger='dex', monk='dex', rogue='dex', cleric='wis', druid='wis',
               bard='cha', warlock='cha', sorcerer='cha', wizard='int', artificer='int')
FULL_SLOTS = {1: [2], 2: [3], 3: [4, 2], 4: [4, 3], 5: [4, 3, 2], 6: [4, 3, 3], 7: [4, 3, 3, 1], 8: [4, 3, 3, 2], 9: [4, 3, 3, 3, 1],
              10: [4, 3, 3, 3, 2], 11: [4, 3, 3, 3, 2, 1], 12: [4, 3, 3, 3, 2, 1], 13: [4, 3, 3, 3, 2, 1, 1], 14: [4, 3, 3, 3, 2, 1, 1],
              15: [4, 3, 3, 3, 2, 1, 1, 1], 16: [4, 3, 3, 3, 2, 1, 1, 1], 17: [4, 3, 3, 3, 2, 1, 1, 1, 1], 18: [4, 3, 3, 3, 3, 1, 1, 1, 1],
              19: [4, 3, 3, 3, 3, 2, 1, 1, 1], 20: [4, 3, 3, 3, 3, 2, 2, 1, 1]}
PACT = {1: (1, 1), 2: (2, 1), 3: (2, 2), 4: (2, 2), 5: (2, 3), 6: (2, 3), 7: (2, 4), 8: (2, 4), 9: (2, 5), 10: (2, 5),
        11: (3, 5), 12: (3, 5), 13: (3, 5), 14: (3, 5), 15: (3, 5), 16: (3, 5), 17: (4, 5), 18: (4, 5), 19: (4, 5), 20: (4, 5)}
SKILL = {'athletics': 'Ath', 'acrobatics': 'Acr', 'animal handling': 'Ani', 'arcana': 'Arc', 'deception': 'Dec', 'history': 'His',
         'insight': 'Ins', 'intimidation': 'Inti', 'investigation': 'Inv', 'medicine': 'Med', 'nature': 'Nat', 'perception': 'Perc',
         'performance': 'Perf', 'persuasion': 'Pers', 'religion': 'Rel', 'sleight of hand': 'Sle', 'stealth': 'Ste', 'survival': 'Sur'}
SKILL_AB = dict(Ath='str', Acr='dex', Sle='dex', Ste='dex', Arc='int', His='int', Inv='int', Nat='int', Rel='int', Ani='wis',
                Ins='wis', Med='wis', Perc='wis', Sur='wis', Dec='cha', Inti='cha', Perf='cha', Pers='cha')
DEFAULT_SPELLS = {
    'cleric': {0: ['sacred flame', 'toll the dead'], 1: ['bless', 'cure wounds', 'guiding bolt', 'healing word', 'shield of faith'],
               2: ['spiritual weapon', 'aid', 'hold person'], 3: ['spirit guardians', 'mass healing word', 'revivify'],
               4: ['banishment', 'death ward'], 5: ['flame strike', 'mass cure wounds'], 6: ['harm', 'heal']},
    'druid': {0: ['produce flame', 'thorn whip'], 1: ['cure wounds', 'healing word', 'entangle', 'thunderwave', 'faerie fire'],
              2: ['moonbeam', 'flaming sphere'], 3: ['call lightning', 'erupting earth'], 4: ['ice storm', 'polymorph'],
              5: ['insect plague', 'mass cure wounds']},
    'wizard': {0: ['fire bolt', 'ray of frost'], 1: ['magic missile', 'shield', 'burning hands', 'sleep'], 2: ['scorching ray', 'shatter', 'web'],
               3: ['fireball', 'hypnotic pattern', 'counterspell'], 4: ['ice storm', 'banishment'], 5: ['cone of cold'], 6: ['chain lightning']},
    'sorcerer': {0: ['fire bolt', 'ray of frost'], 1: ['magic missile', 'shield'], 2: ['scorching ray'], 3: ['fireball'], 4: ['ice storm'],
                 5: ['cone of cold']},
    'bard': {0: ['vicious mockery'], 1: ['healing word', 'dissonant whispers', 'faerie fire'], 2: ['shatter', 'hold person'],
             3: ['hypnotic pattern', 'fear'], 4: ['polymorph'], 5: ['hold monster', 'mass cure wounds']},
    'warlock': {0: ['eldritch blast'], 1: ['hex', 'armor of agathys'], 2: ['shatter', 'hold person'], 3: ['fear'], 4: ['blight'],
                5: ['hold monster']},
    'paladin': {1: ['bless', 'cure wounds', 'shield of faith', 'divine favor'], 2: ['aid', 'magic weapon'], 3: ['revivify'], 4: ['banishment']},
    'ranger': {1: ["hunter's mark", 'cure wounds'], 2: ['spike growth'], 3: [], 4: []},
    'artificer': {0: ['fire bolt'], 1: ['cure wounds', 'faerie fire'], 2: ['heat metal', 'web'], 3: ['fireball'], 4: [], 5: []},
}
SUB_SPELLS = {'life': {1: ['bless', 'cure wounds'], 2: ['spiritual weapon'], 3: ['revivify', 'beacon of hope'], 5: ['mass cure wounds']},
              'light': {1: ['burning hands'], 2: ['flaming sphere'], 3: ['fireball'], 5: ['flame strike']},
              'war': {1: ['divine favor', 'shield of faith'], 2: ['magic weapon', 'spiritual weapon']},
              'artillerist': {1: ['shield', 'thunderwave'], 2: ['scorching ray', 'shatter'], 3: ['fireball']},
              'celestial': {1: ['cure wounds', 'guiding bolt'], 2: ['flaming sphere'], 3: ['revivify'], 4: ['wall of fire'], 5: ['flame strike']},
              'fiend': {1: ['burning hands'], 2: ['scorching ray'], 3: ['fireball'], 4: ['fire shield'], 5: ['flame strike']}}
RACE_RES = {'tiefling': ['fire'], 'dwarf': ['poison'], 'dragonborn-black': ['acid'], 'dragonborn-blue': ['lightning'],
            'dragonborn-green': ['poison'], 'dragonborn-red': ['fire'], 'dragonborn-white': ['cold'], 'dragonborn-silver': ['cold'],
            'dragonborn-gold': ['fire'], 'dragonborn-copper': ['acid'], 'dragonborn-brass': ['fire'], 'dragonborn-bronze': ['lightning'],
            'goliath': ['cold'], 'tortle': [], 'shadar-kai': ['necrotic'], 'genasi': []}

def m_(score): return (score - 10) // 2
def prof_at(level): return 2 + (level - 1) // 4

def load_sources():
    src = {}
    for fn in ('sheets.json', 'extra.json', 'stock.json'):
        p = os.path.join(ROOT, 'roster', fn)
        if os.path.exists(p): src.update(json.load(open(p)))
    return src

def find_source(name):
    src = load_sources()
    if name in src: return src[name]
    for k, v in src.items():
        if k.lower().startswith(name.lower()) or v.get('sheet_name', '').lower() == name.lower(): return v
    raise KeyError(f"no sheet or roster/extra.json entry for '{name}'")

def rescale(d, level):
    """Return (classes, abilities) at the target total level. Levels go to or come off the highest class."""
    classes = [dict(c) for c in d['classes']]
    base = d.get('level') or sum(c['level'] or 0 for c in classes)
    ab = dict(d['abilities'])
    if not level or level == base: return classes, ab, base
    main = max(classes, key=lambda c: c['level'] or 0)
    prim = PRIMARY[main['class']]
    old_main = main['level']
    if level > base: main['level'] += level - base
    else:                                                           # take levels off the smaller classes first
        cut = base - level
        for c in sorted(classes, key=lambda c: (c is main, c['level'])):
            take = min(cut, c['level'] - (1 if c is main else 0)); c['level'] -= take; cut -= take
        classes = [c for c in classes if c['level'] > 0]
    for x in (4, 8, 12, 16, 19):                                   # ability score improvements gained or lost
        if old_main < x <= main['level']: ab[prim] = min(20, ab[prim] + 2)
        if main['level'] < x <= old_main: ab[prim] = ab[prim] - 2
    return classes, ab, level

def slots_for(classes):
    """Multiclass spellcaster slots (PHB) plus warlock pact magic."""
    eff = 0
    for c in classes:
        k, l, sub = c['class'], c['level'], c.get('sub', '').lower()
        if k in ('cleric', 'druid', 'bard', 'sorcerer', 'wizard'): eff += l
        elif k in ('paladin', 'ranger'): eff += l // 2 if l >= 2 else 0
        elif k == 'artificer': eff += (l + 1) // 2
        elif sub in ('eldritch knight', 'arcane trickster') and l >= 3: eff += l // 3
    slots = {i + 1: n for i, n in enumerate(FULL_SLOTS[eff])} if eff else {}
    single = [c for c in classes if c['class'] in ('paladin', 'ranger')]
    if len(classes) == 1 and single:                               # half casters alone round down by their own table
        l = single[0]['level']
        slots = {i + 1: n for i, n in enumerate(FULL_SLOTS[(l + 1) // 2])} if l >= 2 else {}
    pact = {}
    for c in classes:
        if c['class'] == 'warlock':
            n, lv = PACT[c['level']]; pact = {lv: n}
    return slots, pact

class BuiltPC(PC):
    """A character played by its class kit. Options are its sheet attacks (rescaled) and its combat spells."""
    def __init__(s, d, level=None):
        classes, ab, lvl = rescale(d, level)
        s.classes = {c['class']: c['level'] for c in classes}
        s.subs = {c['class']: (c.get('sub') or '').lower() for c in classes}
        mods = {a: m_(v) for a, v in ab.items()}
        prof = prof_at(lvl)
        main = max(classes, key=lambda c: c['level'])['class']
        saves = {a: mods[a] + (prof if a in (d.get('save_prof') or SAVES[main]) else 0) for a in mods}
        skills = {}
        for long, short in SKILL.items():
            mult = (d.get('skill_prof') or {}).get(long, 0)
            skills[short] = mods[SKILL_AB[short]] + prof * mult
        st = dict(saves=saves, mods=mods, skills=skills)
        hp = 0; first = True
        for c in sorted(classes, key=lambda c: c['class'] != main):
            die = HD[c['class']]
            for i in range(c['level']):
                hp += (die if first else die // 2 + 1) + mods['con']; first = False
        race = (d.get('race') or '').lower()
        if 'hill dwarf' in race: hp += lvl
        if s.subs.get('sorcerer', '').startswith('draconic'): hp += s.classes['sorcerer']
        a = d.get('ac') or {}
        ac = d.get('ac_total') or (a.get('armor', 10) + a.get('dex', mods['dex']) + a.get('shield', 0) + a.get('misc', 0))
        if d.get('level') and lvl != d.get('level'):
            if 'monk' in s.classes and not a.get('armor', 10) > 10: ac = 10 + mods['dex'] + mods['wis']
            if 'barbarian' in s.classes and a.get('armor', 10) <= 10: ac = 10 + mods['dex'] + mods['con'] + a.get('shield', 0)
        role = 'front' if any(k in s.classes for k in ('barbarian', 'fighter', 'paladin', 'monk')) and \
            not (main == 'fighter' and mods['dex'] > mods['str'] and any('bow' in x['name'].lower() for x in d.get('attacks', []))) else 'back'
        if main in ('ranger',) and mods['dex'] >= mods['str']: role = 'back'
        atks = [x for x in d.get('attacks') or [] if re.match(r'\d+d\d+', x.get('dmg', '')) and 'breath' not in x['name'].lower()]
        if main == 'rogue' and atks:
            best = max(atks, key=lambda x: avg(x['dmg']) + x['hit'] * 0.5)
            if 'melee' in best.get('range', '').lower(): role = 'front'
        slots, pact = slots_for(classes)
        uses = {}; sr = set()
        super().__init__(st, d.get('sheet_name') or d['name'], hp, ac, lvl, f"d{HD[main]}", role, slots=slots, uses=uses,
                         pact=pact, spells=(), sr_keys=sr)
        s.name = d['name']
        s.src = d; s.race = race; s.ab = ab
        s.size = 'Small' if any(x in race for x in ('halfling', 'gnome', 'kobold', 'goblin')) else 'Medium'
        from .terrain import DARKVISION_RACES
        s.darkvision = any(x in race for x in DARKVISION_RACES)
        s.res |= set(d.get('resist') or [])
        for k, v in RACE_RES.items():
            if k in race: s.res |= set(v)
        s.cast_ab = CAST.get(main) or next((CAST[c] for c in s.classes if c in CAST), None)
        cm = mods[s.cast_ab] if s.cast_ab else 0
        s.spell_dc = 8 + prof + cm; s.spell_atk = prof + cm
        s.features(d, lvl, mods, prof)
        s.build_attacks(d, lvl, mods, prof)
        s.build_spells(d, lvl, mods, prof)
        s.max_uses = dict(s.uses)
        s.healer = any(o['kind'] == 'heal' for o in s.spell_opts) and main in ('cleric', 'druid', 'bard', 'paladin', 'artificer')
        if s.healer: s.heal_reserve = 2 if main in ('cleric', 'druid', 'bard') else 0
        s.max_slots = dict(s.slots); s.max_pact = dict(s.pact)
    # ------------------------------------------------------------ features
    def features(s, d, lvl, mods, prof):
        c = s.classes; sub = s.subs; u = s.uses
        s.rage_dmg = 0; s.extra_attacks = 1; s.crit_range = 20; s.sneak_dice = 0; s.martial = None
        if 'barbarian' in c:
            b = c['barbarian']
            u['rage'] = 2 if b < 3 else 3 if b < 6 else 4 if b < 12 else 5
            s.rage_dmg = 2 if b < 9 else 3 if b < 16 else 4
            if b >= 2: s.tags.add('danger_sense'); s.reckless_ok = True
            if b >= 5: s.extra_attacks = 2
            s.brutal = 1 if b >= 9 else 0
            s.bear = 'bear' in sub['barbarian'] or 'totem' in sub['barbarian']
            s.frenzy = 'berserker' in sub['barbarian']
        if 'fighter' in c:
            f = c['fighter']
            u['sw'] = 1; s.sr_keys.add('sw')
            if f >= 2: u['as'] = 1; s.sr_keys.add('as')
            if f >= 5: s.extra_attacks = max(s.extra_attacks, 2)
            if f >= 11: s.extra_attacks = 3
            if 'champion' in sub['fighter'] and f >= 3: s.crit_range = 19 if f < 15 else 18
            if 'battle master' in sub['fighter'] and f >= 3:
                u['sup'] = 4 if f < 7 else 5; s.sr_keys.add('sup'); s.sup_die = '1d8' if f < 10 else '1d10'
                s.parry_man = True; s.riposte = True
        if 'paladin' in c:
            p = c['paladin']
            u['loh'] = 5 * p
            if p >= 2: s.smite = True
            if p >= 5: s.extra_attacks = max(s.extra_attacks, 2)
            if p >= 6: s.aura = max(1, mods['cha'])
            if p >= 11: s.improved_smite = True
            if p >= 3: u['cd'] = 1; s.sr_keys.add('cd')
        if 'ranger' in c:
            r = c['ranger']
            if r >= 5: s.extra_attacks = max(s.extra_attacks, 2)
            if r >= 3 and ('hunter' in sub['ranger'] or not sub['ranger']): s.colossus = True
        if 'rogue' in c:
            r = c['rogue']
            s.sneak_dice = (r + 1) // 2
            if r >= 5: s.uncanny = True
            if r >= 7: s.tags.add('evasion')
        if 'monk' in c:
            k = c['monk']
            s.martial = '1d4' if k < 5 else '1d6' if k < 11 else '1d8' if k < 17 else '1d10'
            if k >= 2: u['ki'] = k; s.sr_keys.add('ki')
            if k >= 5: s.extra_attacks = max(s.extra_attacks, 2); s.stun = True
            if k >= 7: s.tags.add('evasion')
        if 'cleric' in c:
            k = c['cleric']
            if k >= 2: u['cd'] = 1 if k < 6 else 2 if k < 18 else 3; s.sr_keys.add('cd')
            s.destroy_cr = 0 if k < 5 else 0.5 if k < 8 else 1 if k < 11 else 2 if k < 14 else 3
            s.life = 'life' in sub['cleric']
            if k >= 8: s.divine_strike = '1d8' if k < 14 else '2d8'
        if 'bard' in c:
            k = c['bard']
            u['inspo'] = max(1, mods['cha']); s.inspo_die = '1d6' if k < 5 else '1d8' if k < 10 else '1d10'
            if k >= 5: s.sr_keys.add('inspo')
            if k >= 2: s.song_of_rest = '1d6' if k < 9 else '1d8'
            if k >= 3 and 'lore' in sub['bard']: s.cutting_words = True
        if 'warlock' in c:
            s.agonizing = c['warlock'] >= 2
            if 'celestial' in sub['warlock']: u['hl'] = 1 + c['warlock']; s.hl_cap = max(1, mods['cha'])
            if 'hexblade' in sub['warlock']: u['curse'] = 1; s.sr_keys.add('curse')
        if 'sorcerer' in c:
            if sub['sorcerer'].startswith('draconic') and not (d.get('ac') or {}).get('armor', 10) > 13:
                s.ac_base = max(s.ac_base, 13 + mods['dex'])
            if c['sorcerer'] >= 6 and sub['sorcerer'].startswith('draconic'): s.affinity = mods['cha']
        if 'wizard' in c:
            u['ar'] = 1
        if 'artificer' in c:
            a = c['artificer']
            if 'artillerist' in sub['artificer'] and a >= 3: u['cannon_free'] = 1; s.cannon_die = '2d8' if a < 15 else '3d8'
            if a >= 5 and 'battle smith' in sub['artificer']: s.extra_attacks = max(s.extra_attacks, 2)
        # race
        r = s.race
        if 'goliath' in r: u['stone'] = 1; s.sr_keys.add('stone'); s.stone_bonus = mods['con']
        if 'half-orc' in r or 'orc' in r: u['relentless'] = 1
        if 'halfling' in r: s.lucky = True
        if 'tiefling' in r: u['rebuke'] = 1; s.rebuke_dc = 8 + mods['cha'] + prof
        if 'dragonborn' in r: u['breath'] = 1; s.sr_keys.add('breath')
    # ------------------------------------------------------------ attacks
    def build_attacks(s, d, lvl, mods, prof):
        s.weapons = []
        dprof = prof - prof_at(d.get('level') or lvl)
        prim = PRIMARY[max(s.classes, key=s.classes.get)]
        dprim = m_(s.ab[prim]) - m_(d['abilities'][prim])
        for a in d.get('attacks') or []:
            nm = a['name'].lower()
            if 'breath' in nm:
                save = 'dex' if 'dex' in a.get('desc', '').lower() else 'con'
                tier = 1 + (lvl >= 6) + (lvl >= 11) + (lvl >= 16)
                s.breath_opt = dict(name='breath weapon', kind='save', save=save, dc=8 + mods['con'] + prof, dmg=f'{tier + 1}d6',
                                    type=a.get('type') or 'fire', aoe=2, cost=('use', 'breath'))
                continue
            if not re.match(r'\d+d\d+', a.get('dmg', '')): continue
            ranged = bool(re.search(r'\d+/\d+', a.get('range', ''))) and 'melee' not in a.get('range', '').lower()
            ab = 'dex' if (ranged or 'finesse' in a.get('desc', '').lower() and mods['dex'] >= mods['str']) else 'str'
            bump = dprim if ab == prim else 0
            dmg = re.sub(r'([+-]\d+)$', lambda x: f"{int(x.group(1)) + bump:+d}", a['dmg']) if bump else a['dmg']
            if not re.search(r'[+-]\d+$', dmg) and bump: dmg += f'+{bump}'
            typ = a.get('type') or 'bludgeoning'
            if typ not in ('bludgeoning', 'piercing', 'slashing', 'fire', 'cold', 'force', 'radiant', 'necrotic', 'acid', 'poison', 'lightning', 'thunder', 'psychic'):
                typ = 'slashing'
            w = dict(name=a['name'], kind='atk', hit=a['hit'] + dprof + bump, dmg=dmg, type=typ, weapon=True,
                     melee=not ranged, finesse='finesse' in a.get('desc', '').lower(),
                     magic=bool(re.search(r'\+\d|magic', a['name'] + a.get('desc', ''), re.I)))
            if 'reroll 1 or 2' in a.get('desc', '').lower().replace('-', '') or 'great weapon' in a.get('desc', '').lower(): w['gwf'] = True
            s.weapons.append(w)
        if not s.weapons:                                            # no sheet attacks: a class default
            k = max(s.classes, key=s.classes.get)
            st, dx = mods['str'], mods['dex']
            if k == 'barbarian': s.weapons = [dict(name='greataxe', kind='atk', hit=prof + st, dmg=f'1d12+{st}', type='slashing', weapon=True, melee=True),
                                              dict(name='javelin', kind='atk', hit=prof + st, dmg=f'1d6+{st}', type='piercing', weapon=True)]
            elif k in ('fighter', 'paladin'): s.weapons = [dict(name='longsword', kind='atk', hit=prof + st, dmg=f'1d8+{st}', type='slashing', weapon=True, melee=True)]
            elif k in ('ranger', 'rogue'): s.weapons = [dict(name='shortbow', kind='atk', hit=prof + dx, dmg=f'1d6+{dx}', type='piercing', weapon=True, finesse=k == 'rogue'),
                                                        dict(name='shortsword', kind='atk', hit=prof + dx, dmg=f'1d6+{dx}', type='piercing', weapon=True, melee=True, finesse=True)]
            elif k == 'monk': s.weapons = [dict(name='unarmed strike', kind='atk', hit=prof + dx, dmg=f'{s.martial}+{dx}', type='bludgeoning', weapon=True, melee=True)]
            else: s.weapons = [dict(name='dagger', kind='atk', hit=prof + max(st, dx), dmg=f'1d4+{max(st, dx)}', type='piercing', weapon=True, melee=True, finesse=True)]
        s._base_w = {w['name']: dict(hit=w['hit'], magic=w.get('magic', False)) for w in s.weapons}
        melee = [w for w in s.weapons if w['melee']]
        if melee: s.melee_attack = dict(max(melee, key=lambda w: avg(w['dmg'])))
        if getattr(s, 'martial', None):
            for w in s.weapons:
                if w['melee'] and avg(w['dmg']) < avg(f"{s.martial}+{mods['dex']}"):
                    w['dmg'] = f"{s.martial}+{mods['dex']}"; w['hit'] = prof + mods['dex']
    # ------------------------------------------------------------ spells
    def build_spells(s, d, lvl, mods, prof):
        maxlvl = max(list(s.slots) + list(s.pact) + [0])
        names = [x.lower() for x in (d.get('cantrips') or []) + (d.get('spells') or [])]
        for c, l in s.classes.items():
            sub = s.subs[c].split()[-1] if s.subs[c] else ''
            for k, sp in SUB_SPELLS.items():
                if k in s.subs[c]:
                    for sl, lst in sp.items():
                        if sl <= maxlvl: names += lst
            if c in DEFAULT_SPELLS and (not d.get('spells') or c in ('cleric', 'druid', 'paladin', 'artificer')):
                for sl, lst in DEFAULT_SPELLS[c].items():
                    if sl == 0 or sl <= maxlvl: names += lst
        if 'warlock' not in s.classes: names = [x for x in names if x != 'eldritch blast']
        if 'warlock' in s.classes and 'eldritch blast' not in names and (d.get('cantrips') or not d.get('attacks')): names.append('eldritch blast')
        seen = []
        for n in names:
            n = re.sub(r'-\w+$', '', n.strip())
            if n in SPELLS and n not in seen and SPELLS[n]['level'] <= maxlvl: seen.append(n)
        s.spells = set(seen)
        s.spell_opts = []
        cm = mods[s.cast_ab] if s.cast_ab else 0
        for n in seen:
            o = spell_option(n, s.spell_atk, s.spell_dc, lvl, mod=cm)
            if not o: continue
            if n == 'eldritch blast' and getattr(s, 'agonizing', False): o['dmg'] = f"1d10+{cm}"
            if getattr(s, 'affinity', 0) and o.get('type') == 'fire' and o['kind'] in ('atk', 'save'): o['dmg'] += f"+{s.affinity}"
            if o['kind'] == 'heal' and getattr(s, 'life', False) and o['dice'] != '70':
                o['dice'] += f"+{2 + o['level']}"
            s.spell_opts.append(o)
    # ------------------------------------------------------------ playing
    def options(s, enc):
        n = s.extra_attacks
        out = [dict(w, n=n, crit_range=s.crit_range) for w in s.weapons]
        if getattr(s, 'breath_opt', None) and s.uses.get('breath'): out.append(dict(s.breath_opt))
        out += [o for o in s.spell_opts if o['kind'] in ('atk', 'save', 'auto', 'cond')]
        return out
    def ev(s, enc, opt, t):
        k = opt['kind']
        if k == 'cond':
            if t.down or opt.get('cond') in t.cond_imm or t.cond.get(opt.get('cond')): return 0
            if opt.get('humanoid') and 'humanoid' not in t.tags: return 0
            pf = 1 - p_save(t.saves.get(opt['save'], 0), opt['dc'], 1 if 'magic_resistance' in t.tags else 0)
            v = pf * COND_VALUE.get(opt['cond'], 3) * (2 if opt.get('repeat') else 1) * (1 + t.maxhp / 60)
            aoe = opt.get('aoe', 1)
            if aoe > 1: v *= min(aoe, len(s.foes(enc))) * 0.8
            if 'boss' in t.tags and opt['cond'] in ('paralyzed', 'stunned', 'banished', 'incap'): v *= 1.5
            if opt.get('conc') and s.conc: v *= 0.4
            return v
        v = super().ev(enc, opt, t)
        if opt.get('conc') and s.conc: v *= 0.4
        return v
    def usable(s, enc, opt, bonus_cast=False):
        if opt.get('kind') == 'cond' and (bonus_cast or not s.slots_avail(opt['cost'][1]) or not s.may_spend(enc, opt['cost'][1])):
            return False
        return super().usable(enc, opt, bonus_cast)
    def execute(s, enc, o, t):
        if o['kind'] == 'cond':
            s.spend_slot(o['cost'][1])
            if o.get('conc'): end_conc(s, enc); s.conc = o['name']
            k = o.get('aoe', 1)
            tg = [t] + [x for x in s.foes(enc) if x is not t and R.random() < 0.7][:max(0, int(round(k)) - 1)] if k > 1 else [t]
            log(f"    {s.name} casts {o['name']}")
            for x in tg:
                if x.dead or o['cond'] in x.cond_imm: continue
                if not make_save(x, o['save'], o['dc'], magic=True, enc=enc):
                    c = o['cond']
                    x.cond[c] = ('save', o['dc'], o['repeat']) if o.get('repeat') else (True if c in ('prone', 'lost_turn') else 10)
                    if o.get('conc'): x.cond['src_' + c] = (s, o['name'], c)
                    if o.get('wake'): x.cond['wake_on_hurt'] = c
                    log(f"    {x.name} is {c}")
            return
        if o.get('mock'): o = dict(o, after=lambda enc_, s_, t_: t_.cond.__setitem__('mocked', True))
        if o.get('guided'): o = dict(o, after=lambda enc_, s_, t_: t_.cond.__setitem__('guided', True))
        super().execute(enc, o, t)
    def rider_ev(s, enc, t, opt, p):
        v = 0.0
        if not opt.get('weapon'): return v
        if s.rage_dmg and s.cond.get('rage') and opt.get('melee'): v += s.rage_dmg
        if s.sneak_dice and not s.sneak_used and (opt.get('finesse') or not opt.get('melee')):
            v += avg(f'{s.sneak_dice}d6') / max(1, opt.get('n', 1))
        if getattr(s, 'smite', False) and opt.get('melee') and s.will_smite(enc, t, False):
            v += 0.5 * avg('3d8') * s.mult(t, 'radiant', True)
        if getattr(s, 'improved_smite', False) and opt.get('melee'): v += avg('1d8')
        if getattr(s, 'colossus', False) and not s.cs_used and t.hp < t.maxhp: v += avg('1d8') / max(1, opt.get('n', 1))
        if opt.get('gwf'): v += 1.3
        return v
    def pile_rider(s, opt):
        return avg('3d8') if getattr(s, 'smite', False) and opt.get('melee') and s.slots_avail(1) else 0
    def will_smite(s, enc, t, crit):
        if not s.slots_avail(1): return False
        if crit or t.down: return True
        if enc.importance == 'boss': return True
        if enc.importance == 'major': return 'priority' in t.tags or t.hp > 30
        return False
    def on_hit(s, enc, t, atk, crit):
        parts = super().on_hit(enc, t, atk, crit)
        if not atk.get('weapon'): return parts
        if s.rage_dmg and s.cond.get('rage') and atk.get('melee'): parts.append((s.rage_dmg, atk['type'], atk.get('magic', False)))
        if getattr(s, 'brutal', 0) and crit and atk.get('melee'): parts.append((roll(re.match(r'\d+d\d+', atk['dmg']).group().replace(re.match(r'\d+', atk['dmg']).group(), '1', 1)), atk['type'], atk.get('magic', False)))
        if s.sneak_dice and not s.sneak_used and (atk.get('finesse') or not atk.get('melee')):
            s.sneak_used = True; parts.append((roll(f'{s.sneak_dice}d6', crit), atk['type'], atk.get('magic', False)))
        if getattr(s, 'smite', False) and atk.get('melee') and s.will_smite(enc, t, crit):
            lvl = s.spend_slot(1, prefer_high=crit or 'radiant' in t.vul)
            dice = 1 + lvl + (1 if ('undead' in t.tags or 'fiend' in t.tags) else 0)
            parts.append((roll(f'{min(5, dice)}d8', crit), 'radiant', True))
        if getattr(s, 'improved_smite', False) and atk.get('melee'): parts.append((roll('1d8', crit), 'radiant', True))
        if getattr(s, 'colossus', False) and not s.cs_used and t.hp < t.maxhp:
            s.cs_used = True; parts.append((roll('1d8', crit), atk['type'], atk.get('magic', False)))
        if getattr(s, 'divine_strike', None) and not getattr(s, 'ds_used', False):
            s.ds_used = True; parts.append((roll(s.divine_strike, crit), 'radiant', True))
        if atk.get('gwf'): parts.append((1, atk['type'], atk.get('magic', False)))
        if s.uses.get('sup', 0) > 1 and enc.importance in ('boss', 'major') and ('priority' in t.tags or crit or 'boss' in t.tags):
            s.uses['sup'] -= 1; parts.append((roll(getattr(s, 'sup_die', '1d8'), crit), atk['type'], atk.get('magic', False)))
        if getattr(s, 'stun', False) and atk.get('melee') and s.uses.get('ki', 0) > 0 and not t.cond.get('stunned') and \
                'stunned' not in t.cond_imm and (enc.importance in ('boss', 'major') or 'priority' in t.tags) and t.up:
            s.uses['ki'] -= 1
            if not make_save(t, 'con', 8 + s.prof + s.mods['wis']): t.cond['stunned'] = 1; log(f"    {s.name} stuns {t.name}")
        return parts
    def encounter_start(s, enc):
        super().encounter_start(enc); s.cannon = None; s.frenzied = False
        if s.cond.get('sacred') is None and getattr(s, '_sacred_bonus', None):
            pass
        for w in s.weapons: w.update(s._base_w.get(w['name'], {}))
        if getattr(s, 'aura', 0):
            for p in enc.pcs: p.aura_src = s; p.aura_bonus = s.aura
    def turn(s, enc):
        s.ds_used = False
        super().turn(enc)
        if s.up and s.uses.get('as') and enc.importance in ('boss', 'major') and s.foes(enc) and not s.cond.get('quicksand'):
            s.uses['as'] -= 1
            if not s.objective(enc):
                o, t, v = s.best(enc)
                if o: s.execute(enc, o, t)
    def heal_action(s, enc):
        if getattr(s, 'loh_ok', True) and s.uses.get('loh', 0) > 0:
            t = heal_target(enc, s, 0.25)
            if t and (t.down or t is s):
                amt = min(s.uses['loh'], 5 if t.down else max(1, t.maxhp // 2 - t.hp))
                s.uses['loh'] -= amt; heal(t, amt, enc); return True
        if not s.healer: return False
        dn = s.downed(enc)
        if len(dn) >= 1 and s.uses.get('cd', 0) and getattr(s, 'life', False) and 'cleric' in s.classes and s.classes['cleric'] >= 2:
            if len(dn) >= 2 or sum(1 for p in enc.pcs if p.up and p.hp < p.maxhp / 2) >= 1:
                s.uses['cd'] -= 1; pool = 5 * s.classes['cleric']
                for p in sorted([p for p in enc.pcs if not p.dead and not p.rot and p.hp < p.maxhp // 2], key=lambda p: p.hp):
                    give = min(pool, p.maxhp // 2 - p.hp)
                    if give > 0: heal(p, give, enc); pool -= give
                return True
        t = heal_target(enc, s, 0.3)
        if t and not t.down and enc.importance in ('major', 'boss'):
            o = s.heal_spell(bonus=False)
            if o: s.cast_heal(enc, o, t); return True
        return False
    def heal_spell(s, bonus):
        cands = [o for o in s.spell_opts if o['kind'] == 'heal' and bool(o.get('bonus')) == bonus and s.slots_avail(o['cost'][1])]
        return min(cands, key=lambda o: o['level']) if cands else None
    def cast_heal(s, enc, o, t):
        s.spend_slot(o['cost'][1])
        if o['target'] == 'all':
            for p in [p for p in enc.pcs if not p.dead and not p.rot][:6]:
                if p.down or p.hp < p.maxhp: heal(p, roll(o['dice']), enc)
        else: heal(t, roll(o['dice']), enc)
        log(f"    {s.name} casts {o['name']}")
    def bonus_heal(s, enc):
        if s.uses.get('hl', 0) > 0:                                   # Celestial Healing Light
            t = heal_target(enc, s, 0.3)
            if t:
                n = min(s.hl_cap, s.uses['hl']); s.uses['hl'] -= n; heal(t, roll(f'{n}d6'), enc); return True
        if not s.healer and not any(o['kind'] == 'heal' and o.get('bonus') for o in s.spell_opts): return False
        dn = s.downed(enc)
        mass = [o for o in s.spell_opts if o['name'] == 'mass healing word' and s.slots_avail(o['cost'][1])]
        if len(dn) >= 2 and mass:
            s.cast_heal(enc, mass[0], None); s.bonus_cast = True; return True
        t = heal_target(enc, s, 0.0)
        o = s.heal_spell(bonus=True)
        if t and o: s.cast_heal(enc, o, t); s.bonus_cast = True; return True
        return False
    def buff_action(s, enc):
        foes = s.foes(enc)
        if not foes: return False
        imp = enc.importance
        if s.conc is None and enc.round <= 2 and 'spirit guardians' in s.spells and s.slots.get(3, 0) + sum(n for l, n in s.slots.items() if l > 3) > 0 \
                and not s.downed(enc) and (imp in ('major', 'boss') or len(foes) >= 4) and s.role == 'front' or \
                (s.conc is None and enc.round <= 2 and 'spirit guardians' in s.spells and s.slots_avail(3) and imp in ('major', 'boss') and len(foes) >= 3):
            s.spend_slot(3); s.conc = 'spirit guardians'; log(f"    {s.name} casts spirit guardians"); return True
        if s.uses.get('cd') and 'cleric' in s.classes and worth_turning(enc, s) and not s.downed(enc):
            s.uses['cd'] -= 1; turn_undead(enc, s, s.spell_dc, destroy_cr=getattr(s, 'destroy_cr', 0)); return True
        if enc.round == 1 and imp == 'boss' and s.conc is None and 'bless' in s.spells and s.slots_avail(1) and not any(p.cond.get('bless') for p in enc.pcs):
            s.spend_slot(1); s.conc = 'bless'
            for p in sorted([p for p in enc.pcs if p.up], key=lambda p: -p.level)[:3]: p.cond['bless'] = ('conc', s)
            log(f"    {s.name} casts bless"); return True
        return False
    def bonus_act(s, enc, pre):
        foes = s.foes(enc)
        if not foes: return False
        imp = enc.importance
        if pre:
            if s.uses.get('rage') and not s.cond.get('rage') and imp in ('normal', 'major', 'boss') and s.role == 'front':
                s.uses['rage'] -= 1; s.cond['rage'] = True
                if getattr(s, 'frenzy', False) and imp in ('major', 'boss'): s.frenzied = True
                return True
            if s.cond.get('rage') and getattr(s, 'reckless_ok', False): s.cond['reckless'] = True
            psub = s.subs.get('paladin', '')
            if s.uses.get('cd') and 'paladin' in s.classes and imp in ('major', 'boss'):
                pri = [m for m in foes if 'priority' in m.tags or 'boss' in m.tags] or ([max(foes, key=lambda m: m.hp)] if imp == 'boss' else [])
                if 'vengeance' in psub and pri and 'vow' not in s.cond:
                    s.uses['cd'] -= 1; s.cond['vow'] = pri[0]; return True
                if 'devotion' in psub and not s.cond.get('sacred'):
                    s.uses['cd'] -= 1; s.cond['sacred'] = True
                    for w in s.weapons:
                        if w['melee']: w['hit'] += max(1, s.mods['cha']); w['magic'] = True
                    return True
            mark = next((n for n in ('hex', "hunter's mark") if n in s.spells), None)
            if mark and s.conc is None and imp in ('major', 'boss') and (s.slots_avail(1)) and s.may_spend(enc, 1):
                s.spend_slot(1); s.conc = 'hm'; t = max(foes, key=lambda m: m.hp)
                s.cond['hm_target' if mark == "hunter's mark" else 'hex_target'] = t; s.bonus_cast = True; return True
            if s.uses.get('curse') and s.cond.get('curse_target') is None:
                pri = [m for m in foes if 'priority' in m.tags or 'boss' in m.tags]
                if pri: s.uses['curse'] -= 1; s.cond['curse_target'] = pri[0]; return True
            sw = [o for o in s.spell_opts if o['kind'] == 'spirit']
            if sw and not s.sw_active and imp in ('major', 'boss') and s.slots_avail(2) and s.may_spend(enc, 2):
                s.spend_slot(2); s.sw_active = True; s.bonus_cast = True; s.sw_opt = sw[0]
            return False
        if s.sw_active:
            o = getattr(s, 'sw_opt', None) or dict(hit=s.spell_atk, dmg=f"1d8+{s.mods.get(s.cast_ab, 0)}")
            t = max(foes, key=lambda m: s.ev(enc, dict(kind='atk', hit=o['hit'], dmg=o['dmg'], type='force', magic=True), m))
            attack(enc, s, t, dict(name='spiritual weapon', hit=o['hit'], dmg=o['dmg'], type='force', magic=True)); return True
        if s.uses.get('sw') and s.hp < s.maxhp * 0.45 and 'fighter' in s.classes:
            s.uses['sw'] -= 1; heal(s, roll('1d10') + s.classes['fighter'], enc); return True
        if getattr(s, 'frenzied', False) and s.cond.get('rage'):
            t = min(foes, key=lambda m: m.hp)
            attack(enc, s, t, dict(s.melee_attack)); return True
        if getattr(s, 'martial', None) and s.uses.get('ki', 0) and imp in ('major', 'boss'):
            s.uses['ki'] -= 1
            for _ in range(2):
                f = s.foes(enc)
                if not f: break
                attack(enc, s, min(f, key=lambda m: m.hp), dict(s.melee_attack, n=1))
            return True
        if getattr(s, 'martial', None):
            attack(enc, s, min(foes, key=lambda m: m.hp), dict(s.melee_attack, n=1)); return True
        if s.uses.get('cannon_free') is not None and getattr(s, 'cannon', None) is None and imp != 'minor':
            if s.uses.get('cannon_free'): s.uses['cannon_free'] -= 1; s.cannon = 1
            elif s.slots_avail(1) and imp in ('major', 'boss'): s.spend_slot(1); s.cannon = 1
            return s.cannon is not None
        if getattr(s, 'cannon', None):
            t = max(foes, key=lambda m: s.ev(enc, dict(kind='atk', hit=s.spell_atk, dmg=s.cannon_die, type='force', magic=True), m))
            attack(enc, s, t, dict(name='force ballista', hit=s.spell_atk, dmg=s.cannon_die, type='force', magic=True)); return True
        return False

def build(name, level=None):
    d = find_source(name)
    p = BuiltPC(d, level)
    if d.get('thieves_tools') is not None: p.thieves_tools = d['thieves_tools']
    elif 'rogue' in p.classes or 'artificer' in p.classes:
        p.thieves_tools = p.mods['dex'] + p.prof * (2 if 'rogue' in p.classes and p.classes['rogue'] >= 1 else 1)
    return p

def describe(p):
    """A one-paragraph summary of what the builder made, for checking against the sheet."""
    cls = ', '.join(f"{k} {v}" + (f" ({p.subs[k]})" if p.subs[k] else '') for k, v in p.classes.items())
    w = '; '.join(f"{o['name']} +{o['hit']} {o['dmg']} {o['type']}" + (f" x{p.extra_attacks}" if p.extra_attacks > 1 and o.get('weapon') else '') for o in p.weapons)
    sp = ', '.join(sorted(p.spells))
    feats = [k for k in ('rage', 'loh', 'cd', 'sup', 'ki', 'inspo', 'as', 'sw', 'stone', 'relentless', 'breath', 'rebuke', 'curse', 'cannon_free') if k in p.uses]
    return (f"{p.name}: {cls}, level {p.level}. HP {p.maxhp}, AC {p.ac}, {p.role} rank. Saves "
            + ', '.join(f"{a} {v:+d}" for a, v in p.saves.items()) + f". Weapons: {w}. Slots {p.slots}{' pact ' + str(p.pact) if p.pact else ''}"
            + f", DC {p.spell_dc}, +{p.spell_atk}. Spells: {sp or 'none'}. Resources: {', '.join(f'{k} {p.uses[k]}' for k in feats) or 'none'}.")
