"""Stat blocks in, monster specs out.

Three ways in, one spec out:
  from_srd(entry)     an entry of the 5e SRD monster JSON (monsters/srd/5e-SRD-Monsters.json)
  from_text(text)     a stat block as text: copied from a PDF, pasted from D&D Beyond, or written in an Obsidian note
                      (**AC** 14 · **HP** 66 ..., ***Trait.*** text). One block per call.
  variant(base, ...)  'use the skeleton stat block, with these changes'

A spec is a plain dict (name, ac, hp, abilities, saves, damage modifiers, cr, traits, actions, legendary, spellcasting).
Each action's text is read for what the engine needs: to-hit, damage and damage type, the save and DC, a condition on a
failed save or a hit, the area, recharge and uses per day. playtest.brain turns a spec into a fighting Creature.
"""
import re, copy

ABIL = ['str', 'dex', 'con', 'int', 'wis', 'cha']
ABNAME = {'strength': 'str', 'dexterity': 'dex', 'constitution': 'con', 'intelligence': 'int', 'wisdom': 'wis', 'charisma': 'cha',
          'str': 'str', 'dex': 'dex', 'con': 'con', 'int': 'int', 'wis': 'wis', 'cha': 'cha'}
NUM = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'twice': 2, 'thrice': 3}
CR_XP = {0: 10, 0.125: 25, 0.25: 50, 0.5: 100, 1: 200, 2: 450, 3: 700, 4: 1100, 5: 1800, 6: 2300, 7: 2900, 8: 3900, 9: 5000,
         10: 5900, 11: 7200, 12: 8400, 13: 10000, 14: 11500, 15: 13000, 16: 15000, 17: 18000, 18: 20000, 19: 22000,
         20: 25000, 21: 33000, 22: 41000, 23: 50000, 24: 62000, 25: 75000, 26: 90000, 27: 105000, 28: 120000, 29: 135000, 30: 155000}
DTYPES = ('acid', 'bludgeoning', 'cold', 'fire', 'force', 'lightning', 'necrotic', 'piercing', 'poison', 'psychic', 'radiant',
          'slashing', 'thunder')
CONDS = {'paralyzed': 'paralyzed', 'poisoned': 'poisoned', 'frightened': 'frightened', 'stunned': 'stunned',
         'restrained': 'restrained', 'blinded': 'blinded', 'charmed': 'incap', 'incapacitated': 'incap', 'petrified': 'paralyzed',
         'unconscious': 'asleep', 'deafened': None}

def mod(score): return (score - 10) // 2
def dice_clean(d): return re.sub(r'\s+', '', d.replace('−', '-').replace('–', '-'))

def blank(name):
    return dict(name=name, size='Medium', type='', ac=10, hp=1, hit_dice='', speed={}, abilities={a: 10 for a in ABIL},
                saves={}, skills={}, vul=[], res=[], imm=[], res_nonmag=False, cond_imm=[], cr=0, xp=0, prof=2,
                traits=[], actions=[], bonus=[], reactions=[], legendary=None, spellcasting=[], multiattack=None, notes=[])

# ---------------------------------------------------------------- reading an action's text
def aoe_estimate(desc):
    """How many PCs an area usually catches, out of a party of four to six with no battle map."""
    m = re.search(r'(\d+)[- ](?:foot|ft\.?)(?:-long)?(?:[- ]wide)?[- ]?(cone|line|cube|sphere|radius|emanation|cylinder)', desc)
    if m:
        size, shape = int(m.group(1)), m.group(2)
        if shape == 'cone': return 2 if size <= 15 else 2.5 if size <= 30 else 3
        if shape == 'line': return 2 if size <= 60 else 2.5
        if shape == 'cube': return 1.5 if size <= 10 else 2.5
        return 2 if size <= 10 else 3 if size <= 20 else 3.5
    m = re.search(r'within (\d+) (?:feet|ft\.?)', desc)
    if m and re.search(r'\beach\b|\bany\b|creatures? of', desc):
        d = int(m.group(1))
        return 2 if d <= 10 else 2.5 if d <= 20 else 4
    m = re.match(r'\s*(one|two|three|four) (?:creatures|targets)', desc)
    if m: return NUM[m.group(1)]
    if re.search(r'\beach creature\b|\ball creatures\b', desc): return 2.5
    return 1

def parse_rider(desc):
    """The save and what a failed save does: damage, a condition, a grapple, a drained hit point maximum."""
    r = {}
    m = re.search(r'DC (\d+) (Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) sav(?:ing throw|e)', desc, re.I)
    if m: r['dc'] = int(m.group(1)); r['save'] = ABNAME[m.group(2).lower()]
    m = re.search(r'tak(?:e|es|ing) (?:\d+ )?\(?(\d+d\d+(?:\s*[+−-]\s*\d+)?)\)? (\w+) damage(?: on a failed save)?', desc)
    if m and 'save' in r and m.group(2).lower() in DTYPES:
        r['dmg'] = dice_clean(m.group(1)); r['type'] = m.group(2).lower()
        r['half'] = bool(re.search(r'half as much', desc))
        m2 = re.search(r'damage(?: on a failed save)?,? (?:plus|and) (?:\d+ )?\(?(\d+d\d+(?:\s*[+−-]\s*\d+)?)\)? (\w+) damage', desc)
        if m2 and m2.group(2).lower() in DTYPES:
            r['dmg2'] = dice_clean(m2.group(1)); r['type2'] = m2.group(2).lower()
    if 'save' in r and 'dmg' not in r:
        f = re.search(r'Failure:\s*(?:\d+\s*)?\(?(\d+d\d+(?:\s*[+−-]\s*\d+)?)\)?\s*(\w+)(?: damage)?(?:\s*(?:\+|plus|and)\s*(?:\d+\s*)?\(?(\d+d\d+(?:\s*[+−-]\s*\d+)?)\)?\s*(\w+))?', desc)
        if f and f.group(2).lower() in DTYPES:
            r['dmg'] = dice_clean(f.group(1)); r['type'] = f.group(2).lower()
            if f.group(3) and f.group(4) and f.group(4).lower() in DTYPES: r['dmg2'] = dice_clean(f.group(3)); r['type2'] = f.group(4).lower()
            r['half'] = bool(re.search(r'[Ss]uccess:\s*half', desc))
    if re.search(r'knocked prone|be (?:knocked )?prone|falls? prone', desc): r['cond'] = 'prone'
    for word, c in CONDS.items():
        if c and re.search(r'(?:be|become|becomes|is|are|remains?|or) (?:magically )?' + word, desc):
            r['cond'] = c; break
    g = re.search(r'grappled \(escape DC (\d+)\)', desc)
    if g:
        r['grapple'] = int(g.group(1))
        if re.search(r'grapple ends,? the (?:target|creature) is restrained', desc): r['cond'] = 'restrained'; r['grapple_restrains'] = True
    if re.search(r'repeat the saving throw at the end of each of its turns', desc): r['repeat'] = r.get('save', 'con')
    elif re.search(r'until (?:the )?end of (?:its|the target\'s|their)? ?next turn|until the start of', desc): r['dur'] = 1
    elif re.search(r'for (?:1|one) minute|for (?:1|one) hour|for 24 hours', desc): r['dur'] = 10
    if re.search(r'hit point maximum is reduced', desc): r['drain'] = True
    if re.search(r"can't regain hit points", desc): r['rot'] = True
    if re.search(r'swallowed', desc): r['swallow'] = True
    return r

def parse_action(name, desc, js=None):
    """One action, bonus action, reaction or legendary action, read from its name and text (and SRD fields when given)."""
    a = dict(name=re.sub(r'\s*\(.*?\)\s*$', '', name).strip(), raw_name=name, desc=desc)
    low = desc.lower()
    m = re.search(r'\(Recharge (\d)(?:\s*[–-]\s*6)?\)', name)
    if m: a['recharge'] = int(m.group(1))
    m = re.search(r'\((\d+)/Day\)', name, re.I)
    if m: a['per_day'] = int(m.group(1))
    if re.search(r'Recharges after a (?:Short|Long)', name): a['per_day'] = 1
    m = re.search(r'\(Costs (\d) Actions\)', name)
    a['cost'] = int(m.group(1)) if m else 1
    if js and js.get('usage'):
        u = js['usage']
        if u.get('type') == 'recharge on roll': a['recharge'] = u.get('min_value', 6)
        elif u.get('type') == 'per day': a['per_day'] = u.get('times', 1)
        elif u.get('type') == 'recharge after rest': a['per_day'] = 1
    atk = re.search(r'(Melee or Ranged|Melee|Ranged) (Weapon|Spell) Attack:?\s*\+?\s*(\d+) to hit', desc, re.I)
    bare = None if atk else re.match(r'\s*\+(\d+) to hit', desc)
    if atk or bare or (js and js.get('attack_bonus') is not None):
        a['kind'] = 'attack'
        a['hit'] = int(atk.group(3)) if atk else int(bare.group(1)) if bare else js['attack_bonus']
        if atk: how = atk.group(1).lower()
        elif re.search(r'\breach\b', desc) and re.search(r'\brange\b', desc): how = 'melee or ranged'
        elif re.search(r'\brange\b', desc): how = 'ranged'
        else: how = 'melee'
        a['melee'] = how.startswith('melee'); a['ranged'] = 'ranged' in how
        a['weapon'] = not (atk and atk.group(2).lower() == 'spell')
        m = re.search(r'reach (\d+) ft', desc); a['reach'] = int(m.group(1)) if m else 5
        dm = []
        if js and js.get('damage'):
            for d in js['damage']:
                if 'damage_dice' in d and 'damage_type' in d:
                    dm.append((dice_clean(d['damage_dice']), d['damage_type']['index']))
                elif 'from' in d:                     # a choice of damage types: take the first
                    opts = d['from'].get('options', [])
                    if opts and 'damage_dice' in opts[0]: dm.append((dice_clean(opts[0]['damage_dice']), opts[0]['damage_type']['index']))
        if not dm:
            h = desc.split('Hit:', 1)[1] if 'Hit:' in desc else desc
            for x in re.finditer(r'(\d+)\s*\(([0-9d+\s−–-]+)\)\s*(\w+)(?: damage)?|(?<![(\d])(\d+) (\w+) damage', h):
                if x.group(2):
                    if x.group(3).lower() in DTYPES: dm.append((dice_clean(x.group(2)), x.group(3).lower()))
                elif x.group(5) and x.group(5).lower() in DTYPES: dm.append((x.group(4), x.group(5).lower()))
                if re.match(r'\s*(?:,|\.)?\s*or ', h[x.end():x.end() + 6]):    # versatile: keep the first
                    pass
            # drop the versatile two-handed alternative
            if len(dm) >= 2 and re.search(r'damage,? or \d+ \(', h): dm = [dm[0]] + dm[2:]
        if dm:
            a['dmg'], a['type'] = dm[0]; a['extra'] = [dict(dmg=d, type=t) for d, t in dm[1:]]
        else:
            a['dmg'], a['type'], a['extra'] = '0', 'bludgeoning', []
        rider = parse_rider(desc.split('Hit:', 1)[1] if 'Hit:' in desc else desc)
        if rider: a['rider'] = rider
        if re.search(r'\bmagical\b|\bmagic weapon\b', low) or not a['weapon']: a['magic'] = True
        return a
    if a['name'].lower() == 'multiattack':
        a['kind'] = 'multi'; return a
    r = parse_rider(desc)
    if js and js.get('dc'):
        r.setdefault('dc', js['dc']['dc_value']); r.setdefault('save', js['dc']['dc_type']['index'])
        if js['dc'].get('success_type') == 'half': r['half'] = True
        if js.get('damage'):
            d = js['damage'][0]
            if 'damage_dice' in d: r['dmg'] = dice_clean(d['damage_dice']); r['type'] = d['damage_type']['index']
    if 'save' in r and ('dmg' in r or 'cond' in r):
        a['kind'] = 'save'; a.update(r); a['aoe'] = aoe_estimate(low)
        if a['aoe'] == 1 and re.search(r'\bone (?:creature|target)\b', low): a['aoe'] = 1
        return a
    hm = re.search(r'(?:regains?|heals?) (?:\d+ )?\(?(\d+d\d+(?:\s*[+−-]\s*\d+)?)\)? hit points', desc)
    if hm: a['kind'] = 'heal'; a['dice'] = dice_clean(hm.group(1)); return a
    m = re.search(r'makes (?:a|one) (\w[\w ]*?) attack', desc) or re.search(r'uses (?:its|their) ([\w ]+?)(?:\.|,| or)', desc)
    if m: a['kind'] = 'ref'; a['ref'] = m.group(1).strip(); return a      # legendary 'makes a tail attack' / 'uses its Paralyzing Touch'
    if re.search(r'casts? a cantrip', desc): a['kind'] = 'cantrip'; return a
    a['kind'] = 'other'
    return a

def parse_multi(desc, actions):
    """Multiattack text into one or more plans: [[(action name, count), ...], ...]."""
    names = [x['name'] for x in actions if x.get('kind') in ('attack', 'save')]
    low = desc.lower()
    plans = []
    for part in re.split(r'\.\s*or\b|;\s*or\b|, or it makes|\bor it makes\b|\. alternatively', low):
        plan = []
        for m in re.finditer(r'(one|two|three|four|five|six|twice|thrice|a|an)\s+(?:attacks?\s+)?with\s+(?:its|their|his|her)\s+([\w\' -]+?)(?=,| and|\.|$| or)', part):
            nm = next((n for n in names if n.lower() in m.group(2) or m.group(2).rstrip('s') in n.lower()), None)
            if nm: plan.append((nm, NUM.get(m.group(1), 1)))
        if not plan:
            for m in re.finditer(r'\b(one|two|three|four)\s+([\w\'-]+(?: [\w\'-]+)?)\b', part):
                nm = next((n for n in names if n.lower() == m.group(2) or n.lower() == m.group(2).rstrip('s') or n.lower().rstrip('s') == m.group(2).rstrip('s')), None)
                if nm: plan.append((nm, NUM[m.group(1)]))
            if not plan:
                m = re.search(r'\b(one|two|three|four|five|six)\s+([\w\' -]+?)\s+attacks?', part)
                if m:
                    nm = next((n for n in names if n.lower() in m.group(2) or m.group(2).rstrip('s') in n.lower()), None)
                    if nm: plan.append((nm, NUM[m.group(1)]))
        if not plan:
            m = re.search(r'makes (one|two|three|four|five|six) (\w[\w ]*?) attacks?', part)
            if m:
                cnt = NUM.get(m.group(1), 2)
                kind = m.group(2)
                nm = next((n for n in names if n.lower() in kind or kind.rstrip('s') in n.lower()), None)
                if nm is None:
                    melee = 'ranged' not in kind
                    cand = [x for x in actions if x.get('kind') == 'attack' and (x.get('melee') if melee else x.get('ranged'))]
                    nm = cand[0]['name'] if cand else (names[0] if names else None)
                if nm: plan.append((nm, cnt))
        if not plan:
            m = re.search(r'(\w+) (?:\w+ )?attacks?', part)
            if m and m.group(1) in NUM and names: plan.append((names[0], NUM[m.group(1)]))
        uses = [x['name'] for x in actions if x.get('kind') in ('save', 'other') and x['name'].lower() in part and x['name'] not in [p[0] for p in plan]]
        for u in uses: plan.insert(0, (u, 1))
        if plan: plans.append(plan)
    return plans or None

def multi_from_srd(js, actions):
    plans = []
    if js.get('multiattack_type') == 'actions':
        cnt = lambda c: int(c) if str(c).isdigit() else 5          # the hydra's 'Number of Heads'
        plans.append([(a['action_name'], cnt(a.get('count', 1))) for a in js.get('actions', [])])
    elif js.get('multiattack_type') == 'action_options':
        for o in js['action_options']['from']['options']:
            cnt = lambda c: int(c) if str(c).isdigit() else 1
            if o.get('option_type') == 'multiple': plans.append([(i['action_name'], cnt(i.get('count', 1))) for i in o['items']])
            elif o.get('option_type') == 'action': plans.append([(o['action_name'], cnt(o.get('count', 1)))])
    names = {a['name'].lower(): a['name'] for a in actions}
    fixed = []
    for p in plans:
        q = [(names.get(n.lower(), n), c) for n, c in p if n.lower() in names]
        if q: fixed.append(q)
    return fixed or parse_multi(js.get('desc', ''), actions)

# ---------------------------------------------------------------- traits and spellcasting
def read_traits(spec):
    """Mechanics the engine models, from trait names and text."""
    tags = set(); kw = {}
    t = spec['type'].lower()
    for w in ('undead', 'construct', 'fiend', 'beast', 'humanoid', 'dragon', 'elemental', 'celestial', 'fey', 'aberration',
              'monstrosity', 'ooze', 'plant', 'giant'):
        if re.search(r'\b' + w + r'\b', t): tags.add(w)
    for tr in spec['traits']:
        n = tr['name'].lower(); d = tr['desc']; low = d.lower()
        im = re.search(r'immune to (?:the )?([\w, ]+?) conditions?', low)
        if im:
            for c in re.split(r',|\band\b|\bor\b', im.group(1)):
                c = c.strip()
                if c: spec['cond_imm'] = sorted(set(spec['cond_imm']) | {c})
        if 'magic resistance' in n: tags.add('magic_resistance')
        elif 'pack tactics' in n: tags.add('pack_tactics')
        elif 'undead fortitude' in n: tags.add('fortitude')
        elif 'legendary resistance' in n:
            m = re.search(r'\((\d)/Day\)', tr['name']); kw['lr'] = int(m.group(1)) if m else tr.get('times', 3)
        elif n.startswith('stench'):
            tags.add('stench'); m = re.search(r'DC (\d+)', d); kw['stench_dc'] = int(m.group(1)) if m else 10
        elif n.startswith('regeneration'):
            m = re.search(r'regains (\d+) hit points', d); kw['regen'] = int(m.group(1)) if m else 10
            kw['regen_stop'] = [x for x in DTYPES if x in low.split('regains')[1]] if 'regains' in low else []
        elif 'martial advantage' in n:
            m = re.search(r'\((\d+d\d+)\)', d); kw['martial_adv'] = m.group(1) if m else '2d6'
        elif n.startswith('sneak attack'):
            m = re.search(r'\((\d+d\d+)\)', d); kw['sneak'] = m.group(1) if m else '2d6'
        elif n in ('charge', 'pounce', 'trampling charge'):
            m = re.search(r'(\d+d\d+)\)? (\w+) damage', d); kw['charge'] = m.group(1) if m else '2d6'
        elif 'evasion' in n: tags.add('evasion')
        elif 'turn defiance' in n or 'turn resistance' in n: tags.add('turn_resist')
        elif 'turn immunity' in n: tags.add('turn_immune')
        elif n.startswith('rejuvenation'): tags.add('rejuvenation')
        elif 'incorporeal movement' in n: tags.add('incorporeal')
        elif 'aggressive' in n or 'rampage' in n: tags.add('aggressive')
        elif 'nimble escape' in n: tags.add('nimble')
        elif 'brave' in n: tags.add('brave')
        elif 'blood frenzy' in n: tags.add('blood_frenzy')
        elif 'avoidance' in n: tags.add('evasion')
        elif 'flyby' in n: tags.add('flyby')
        elif 'death burst' in n or (('dies' in low or 'on death' in low or 'when it dies' in low) and 'saving throw' in low):
            rr = parse_rider(d); m = re.search(r'(\d+d\d+(?:\s*[+−-]\s*\d+)?)\)? (\w+) damage', d)
            if m and m.group(2).lower() in DTYPES: kw['death_burst'] = dict(save=rr.get('save', 'dex'), dc=rr.get('dc', 10), dmg=dice_clean(m.group(1)), type=m.group(2).lower())
        elif re.search(r'(?:touches|hits) it with a melee attack', low):
            m = re.search(r'takes? (?:\d+ )?\(?(\d+d\d+(?:\s*[+−-]\s*\d+)?)\)? (\w+) damage', d)
            if m and m.group(2).lower() in DTYPES: kw['retaliate'] = dict(dmg=dice_clean(m.group(1)), type=m.group(2).lower())
        elif n.startswith('reckless') and 'reckless' not in tags: tags.add('reckless')
    for r in spec['reactions']:
        n = r['name'].lower()
        if n.startswith('parry'):
            m = re.search(r'adds (\d+) to its AC', r['desc']) or re.search(r'\+(\d+) AC', r['desc']); kw['parry'] = int(m.group(1)) if m else 2
        if n.startswith('uncanny dodge'): kw['uncanny'] = True
    if spec['speed'].get('fly'): tags.add('flying')
    return tags, kw

def parse_spellcasting(name, desc, js=None):
    """Spell lists with slots, or innate spells at will and per day."""
    sc = dict(dc=None, attack=None, slots={}, spells={}, per_day={}, at_will=[], level=1)
    m = re.search(r'spell save DC (\d+)', desc); sc['dc'] = int(m.group(1)) if m else None
    m = re.search(r'([+−-]\d+) to hit with spell attacks', desc) or re.search(r'([+−-]\d+) to hit', desc)
    sc['attack'] = int(m.group(1).replace('−', '-')) if m else None
    m = re.search(r'(\d+)(?:st|nd|rd|th)-level (?:\w+ )?spellcaster', desc); sc['level'] = int(m.group(1)) if m else 1
    if js and js.get('spellcasting'):
        s = js['spellcasting']
        sc['dc'] = s.get('dc', sc['dc']); sc['attack'] = s.get('modifier', sc['attack']); sc['level'] = s.get('level') or sc['level']
        sc['slots'] = {int(k): v for k, v in (s.get('slots') or {}).items()}
        for sp in s.get('spells', []):
            u = sp.get('usage') or {}
            nm = sp['name'].lower()
            if u.get('type') == 'at will': sc['at_will'].append(nm)
            elif u.get('type') == 'per day': sc['per_day'][nm] = u.get('times', 1)
            else: sc['spells'].setdefault(sp.get('level', 0), []).append(nm)
        return sc
    text = desc.replace('\n', ' ')
    text = re.sub(r'(Cantrips|\d(?:st|nd|rd|th))(?: level)?\s*\((at will|\d+ slots?)\)\s*[—–-]\s*', r'\1 (\2): ', text)
    text = re.sub(r'Cantrips\s*[—–-]\s*', 'Cantrips (at will): ', text)
    for m in re.finditer(r'(Cantrips|\d)(?:st|nd|rd|th)?(?: level)? \((at will|\d+ slots?)\):\s*(.+?)(?=(?:[;\s]*[-•]?\s*(?:Cantrips|\d(?:st|nd|rd|th)?(?: level)?)\s*\()|$)', text):
        lvl = 0 if m.group(1) == 'Cantrips' else int(m.group(1))
        if lvl and 'slot' in m.group(2): sc['slots'][lvl] = int(re.match(r'\d+', m.group(2)).group())
        sc['spells'].setdefault(lvl, []).extend(x.strip(' *._').lower() for x in re.split(r',|;', m.group(3)) if x.strip(' *._'))
    for m in re.finditer(r'At will:\s*(.+?)(?=\d+/day|$)', text, re.I):
        sc['at_will'].extend(x.strip(' *.').lower() for x in m.group(1).split(','))
    for m in re.finditer(r'(\d+)/day(?: each)?:\s*(.+?)(?=\d+/day|At will|$)', text, re.I):
        for x in re.split(r',|;', m.group(2)): sc['per_day'][x.strip(' *._').lower()] = int(m.group(1))
    for lvl in list(sc['spells']):
        sc['spells'][lvl] = [re.sub(r'[^a-z\' /-]', '', x).strip() for l in sc['spells'][lvl] for x in re.split(r';', l)]
    if not (sc['spells'] or sc['at_will'] or sc['per_day']):
        from .spells import SPELLS
        found = [nm for nm in SPELLS if re.search(r'\b' + re.escape(nm) + r'\b', text.lower())]
        m = re.search(r'\((\d+)/Day', name, re.I) or re.search(r'(\d+)/day', text, re.I)
        for nm in found:
            if m: sc['per_day'][nm] = int(m.group(1))
            else: sc['at_will'].append(nm)
    m = re.search(r'1/day each:\s*(.+?)(?:\.|$)', text, re.I)
    return sc

# ---------------------------------------------------------------- SRD JSON
def from_srd(js):
    s = blank(js['name'])
    s['size'] = js.get('size', 'Medium'); s['type'] = js.get('type', '')
    s['ac'] = js['armor_class'][0]['value'] if isinstance(js.get('armor_class'), list) else js.get('armor_class', 10)
    s['hp'] = js['hit_points']; s['hit_dice'] = js.get('hit_points_roll', js.get('hit_dice', ''))
    s['speed'] = {k: int(re.match(r'\d+', str(v)).group()) for k, v in js.get('speed', {}).items() if re.match(r'\d+', str(v))}
    names = dict(str='strength', dex='dexterity', con='constitution', int='intelligence', wis='wisdom', cha='charisma')
    s['abilities'] = {a: js[names[a]] for a in ABIL}
    s['saves'] = {a: mod(v) for a, v in s['abilities'].items()}
    for p in js.get('proficiencies', []):
        idx = p['proficiency']['index']
        if idx.startswith('saving-throw-'): s['saves'][idx.split('-')[-1]] = p['value']
        elif idx.startswith('skill-'): s['skills'][idx[6:]] = p['value']
    def dmglist(xs):
        out = []
        for x in xs:
            x = x.lower()
            if 'nonmagical' in x: s['res_nonmag'] = True; continue
            out += [t for t in DTYPES if t in x]
        return out
    s['vul'] = dmglist(js.get('damage_vulnerabilities', [])); s['res'] = dmglist(js.get('damage_resistances', []))
    imm = js.get('damage_immunities', [])
    if any('nonmagical' in x.lower() for x in imm): s['nonmag_immune'] = True
    s['imm'] = [t for t in DTYPES for x in imm if t in x.lower() and 'nonmagical' not in x.lower()]
    s['cond_imm'] = [c['index'] for c in js.get('condition_immunities', [])]
    s['darkvision'] = 'darkvision' in (js.get('senses') or {}) or 'blindsight' in (js.get('senses') or {}) or 'truesight' in (js.get('senses') or {})
    s['cr'] = js.get('challenge_rating', 0); s['xp'] = js.get('xp', CR_XP.get(s['cr'], 0)); s['prof'] = js.get('proficiency_bonus', 2)
    for t in js.get('special_abilities', []):
        if t['name'].lower().startswith('spellcasting') or t['name'].lower().startswith('innate spellcasting'):
            s['spellcasting'].append(parse_spellcasting(t['name'], t['desc'], t))
        else:
            tr = dict(name=t['name'], desc=t['desc'])
            if t.get('usage', {}).get('times'): tr['times'] = t['usage']['times']
            s['traits'].append(tr)
    s['actions'] = [parse_action(a['name'], a.get('desc', ''), a) for a in js.get('actions', [])]
    for a, src in zip(s['actions'], js.get('actions', [])):
        if a.get('kind') == 'multi': s['multiattack'] = multi_from_srd(src, s['actions'])
    s['bonus'] = [parse_action(a['name'], a.get('desc', ''), a) for a in js.get('bonus_actions', [])]
    s['reactions'] = [dict(name=a['name'], desc=a.get('desc', '')) for a in js.get('reactions', [])]
    if js.get('legendary_actions'):
        la = [parse_action(a['name'], a.get('desc', ''), a) for a in js['legendary_actions']]
        s['legendary'] = dict(n=3, actions=la)
    return finish(s)

def finish(s):
    tags, kw = read_traits(s)
    s['tags'] = sorted(tags); s['kw'] = kw
    if s['multiattack'] is None:
        m = next((a for a in s['actions'] if a.get('kind') == 'multi'), None)
        if m: s['multiattack'] = parse_multi(m['desc'], s['actions'])
    if s['legendary']:
        for a in s['legendary']['actions']:
            if a.get('kind') == 'ref':
                tgt = next((x for x in s['actions'] if x['name'].lower() == a['ref'].lower()), None) or \
                      next((x for x in s['actions'] if x['name'].lower().startswith(a['ref'].lower().split()[0])), None)
                if tgt: a['target'] = tgt['name']
    return s

# ---------------------------------------------------------------- text
SECTION = re.compile(r'\n\s*(Actions|Bonus Actions|Reactions|Legendary Actions|Lair Actions|Mythic Actions)\s*\n', re.I)
FIELD_END = r'(?=\s*(?:Armor Class|AC\b|Hit Points|HP\b|Speed|STR\b|Saving Throws|Skills|Damage Vulnerabilities|Damage Resistances|Damage Immunities|Condition Immunities|Senses|Languages|Challenge|Proficiency Bonus|\n|$))'

def clean_markdown(text):
    t = text.replace('\r', '')
    t = re.sub(r'\A---\n.*?\n---\n', '', t, flags=re.S)             # YAML frontmatter
    t = re.sub(r'^\s*\|?\s*:?-{3,}.*$', '', t, flags=re.M)             # table separator rows
    t = re.sub(r'^\s*\|(.*)\|\s*$', lambda m: m.group(1).replace('|', ' '), t, flags=re.M)
    t = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]+)\]\]', r'\1', t)        # [[link|text]] -> text
    t = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', t)                    # [text](url) -> text
    t = t.replace('·', '\n').replace('•', '\n')
    t = re.sub(r'^\s*>\s?', '', t, flags=re.M)                        # callouts / blockquotes
    t = re.sub(r'^\s*[-*]\s+', '', t, flags=re.M)                     # bullets
    t = t.replace('***', '').replace('**', '').replace('__', '')
    t = re.sub(r'(?<!\w)\*(?!\s)|(?<!\s)\*(?!\w)', '', t)
    t = re.sub(r'^#+\s*', '', t, flags=re.M)
    t = t.replace('−', '-').replace('–', '-').replace('’', "'")
    return t

def entries(block):
    """Split 'Name. Text Name. Text' paragraphs into (name, text) pairs."""
    out = []
    pat = re.compile(r'(?:^|\n)\s*([A-Z][\w\'/ -]*(?:\s*\([^)]*\))?)\.\s+', re.M)
    ms = list(pat.finditer(block))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(block)
        name = m.group(1).strip()
        if len(name) > 60: continue
        out.append((name, block[m.end():end].strip().replace('\n', ' ')))
    return out

def from_text(text, name=None):
    title = re.search(r'(?m)^#\s+(.+)$', text)
    if title:                                      # keep only the stat block: stop at the next top-level section
        rest = text[title.end():]
        cut = re.search(r'(?m)^#{1,2}\s+(?!Actions|Bonus Actions|Reactions|Legendary Actions|Lair Actions)\S', rest)
        if cut: text = text[:title.end() + cut.start()]
    t = clean_markdown(text)
    lines = [l.strip() for l in t.split('\n') if l.strip()]
    s = blank(name or re.sub(r'\s*\((?:combat stats|stat block)\)\s*$', '', lines[0] if lines else 'Monster', flags=re.I))
    head = t
    m = re.search(r'\b(Tiny|Small|Medium|Large|Huge|Gargantuan)\s+([\w ()]+?)(?:,|\n)', t)
    if m: s['size'] = m.group(1); s['type'] = m.group(2).strip()
    m = re.search(r'(?:Armor Class|\bAC)\s*(\d+)', t); s['ac'] = int(m.group(1)) if m else 10
    m = re.search(r'(?:Hit Points|\bHP)\s*(\d+)(?:\s*\(([^)]+)\))?', t)
    if m: s['hp'] = int(m.group(1)); s['hit_dice'] = dice_clean(m.group(2) or '')
    m = re.search(r'Speed\s*([^\n]+)', t)
    if m:
        sp = m.group(1)
        w = re.match(r'\s*(\d+)', sp); s['speed']['walk'] = int(w.group(1)) if w else 30
        for k in ('fly', 'swim', 'climb', 'burrow'):
            x = re.search(k + r'\s*(\d+)', sp)
            if x: s['speed'][k] = int(x.group(1))
    sc = re.findall(r'\b(STR|DEX|CON|INT|WIS|CHA)\b\s*(\d+)\s*\(([+-]?\d+)\)', t)
    if len(sc) >= 6:
        for ab, v, _ in sc[:6]: s['abilities'][ab.lower()] = int(v)
    else:
        nums = re.search(r'STR\s+DEX\s+CON\s+INT\s+WIS\s+CHA\s+' + r'\s+'.join([r'(\d+)\s*\([+-]?\d+\)'] * 6), t)
        if nums: s['abilities'] = {a: int(nums.group(i + 1)) for i, a in enumerate(ABIL)}
    s['saves'] = {a: mod(v) for a, v in s['abilities'].items()}
    m = re.search(r'Saving Throws\s*(.+?)' + FIELD_END, t)
    if m:
        for ab, v in re.findall(r'(Str|Dex|Con|Int|Wis|Cha)\w*\s*([+-]\d+)', m.group(1), re.I): s['saves'][ab.lower()[:3]] = int(v)
    m = re.search(r'Skills\s*(.+?)' + FIELD_END, t)
    if m:
        for sk, v in re.findall(r'([A-Z][a-z]+(?: [A-Z][a-z]+)?)\s*([+-]\d+)', m.group(1)): s['skills'][sk.lower()] = int(v)
    def dl(label):
        m = re.search(label + r'\s*(.+?)' + FIELD_END, t)
        return m.group(1).lower() if m else ''
    for key, label in (('vul', 'Damage Vulnerabilities'), ('res', 'Damage Resistances'), ('imm', 'Damage Immunities')):
        txt = dl(label)
        if 'nonmagical' in txt:
            if key == 'res': s['res_nonmag'] = True
            if key == 'imm': s['nonmag_immune'] = True
            txt = re.split(r';|bludgeoning, piercing,? and slashing from', txt)[0]
        s[key] = [x for x in DTYPES if re.search(r'\b' + x + r'\b', txt)]
    s['cond_imm'] = [c for c in CONDS if c in dl('Condition Immunities')] + (['exhaustion'] if 'exhaustion' in dl('Condition Immunities') else [])
    m = re.search(r'(?:Challenge|\bCR)\s*([\d/]+)(?:\s*\(([\d,]+) XP\))?', t)
    if m:
        c = m.group(1); s['cr'] = eval(c) if '/' in c else int(c)
        s['xp'] = int(m.group(2).replace(',', '')) if m.group(2) else CR_XP.get(s['cr'], 0)
    s['darkvision'] = bool(re.search(r'darkvision|blindsight|truesight', t, re.I))
    m = re.search(r'Proficiency Bonus\s*\+?(\d+)', t); s['prof'] = int(m.group(1)) if m else 2 + max(0, (int(s['cr']) - 1) // 4)
    # sections
    parts = SECTION.split('\n' + t + '\n')
    body = parts[0]
    m = None
    for m in re.finditer(r'(?:Challenge|Proficiency Bonus|Senses|Languages|Skills|Damage \w+|Condition Immunities|Saving Throws|STR\b[^\n]*|\bCR\b)[^\n]*\n', body): pass
    traits_txt = body[m.end():] if m else ''
    traits_txt = re.sub(r'^.*?(?:Proficiency Bonus[^\n]*\n)', '', traits_txt, flags=re.S) if 'Proficiency Bonus' in traits_txt else traits_txt
    for nm, d in entries(traits_txt):
        if nm.lower().startswith(('spellcasting', 'innate spellcasting')):
            s['spellcasting'].append(parse_spellcasting(nm, d))
        else:
            s['traits'].append(dict(name=nm, desc=d))
    secs = {parts[i].lower(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}
    s['actions'] = [parse_action(n, d) for n, d in entries(secs.get('actions', ''))]
    s['bonus'] = [parse_action(n, d) for n, d in entries(secs.get('bonus actions', ''))]
    s['reactions'] = [dict(name=n, desc=d) for n, d in entries(secs.get('reactions', ''))]
    if 'legendary actions' in secs:
        txt = secs['legendary actions']
        m = re.search(r'can take (\d+) legendary actions', txt)
        s['legendary'] = dict(n=int(m.group(1)) if m else 3, actions=[parse_action(n, d) for n, d in entries(txt) if not n.lower().startswith('the ')])
    for a in s['actions']:
        if a.get('kind') == 'multi': s['multiattack'] = parse_multi(a['desc'], s['actions'])
    return finish(s)

def split_blocks(text):
    """Several stat blocks in one file: each starts at a heading or a name line followed by a size/type line."""
    t = text.replace('\r', '')
    heads = [m.start() for m in re.finditer(r'(?m)^#{1,4}\s+\S.*\n(?=(?:\s*\n)*\s*[*_]?(?:Tiny|Small|Medium|Large|Huge|Gargantuan)\b)', t)]
    if not heads:
        heads = [m.start() for m in re.finditer(r'(?m)^[A-Z][^\n]{1,50}\n(?=\s*(?:Tiny|Small|Medium|Large|Huge|Gargantuan)\b)', t)]
    if not heads: return [t]
    return [t[a:b] for a, b in zip(heads, heads[1:] + [len(t)])]

# ---------------------------------------------------------------- variants
def variant(base, name=None, **changes):
    """'Use the <base> stat block, with these changes.' changes: ac, hp, any spec field, plus
    actions=[stat-block action text, ...] (replace by name, or add), drop=[action names], add_tags=[...], res/imm lists."""
    s = copy.deepcopy(base)
    if name: s['name'] = name
    acts = changes.pop('actions', [])
    for d in changes.pop('drop', []): s['actions'] = [a for a in s['actions'] if a['name'].lower() != d.lower()]
    for txt in acts:
        nm, _, desc = txt.partition('. ')
        a = parse_action(nm.strip(), desc.strip())
        s['actions'] = [x for x in s['actions'] if x['name'].lower() != a['name'].lower()] + [a]
    tags = changes.pop('add_tags', [])
    for k, v in changes.items(): s[k] = v
    s['multiattack'] = None if any(a.get('kind') == 'multi' for a in s['actions']) else s.get('multiattack')
    s = finish(s)
    s['tags'] = sorted(set(s['tags']) | set(tags))
    return s
