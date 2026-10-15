"""Read every MPMB character sheet in a folder into roster/sheets.json, for the class builder.

Usage: python3 tools/read_sheets.py "<folder of MPMB character sheet PDFs>"
Needs pypdf. Takes per character: class and subclass with levels, race, ability scores, saving throw and skill
proficiencies (with expertise), armour class parts, weapon attacks, spell slots, chosen cantrips and spells, and the
limited-use features. Hit points aren't stored on these sheets; the builder works them out from class and Con.
"""
import sys, os, re, json, glob
import pypdf

ABIL = ['Str', 'Dex', 'Con', 'Int', 'Wis', 'Cha']
SKILLS = {'Acr': 'acrobatics', 'Ani': 'animal handling', 'Arc': 'arcana', 'Ath': 'athletics', 'Dec': 'deception', 'His': 'history',
          'Ins': 'insight', 'Inti': 'intimidation', 'Inv': 'investigation', 'Med': 'medicine', 'Nat': 'nature', 'Perc': 'perception',
          'Perf': 'performance', 'Pers': 'persuasion', 'Rel': 'religion', 'Sle': 'sleight of hand', 'Ste': 'stealth', 'Sur': 'survival'}
CLASSES = ['barbarian', 'bard', 'cleric', 'druid', 'fighter', 'monk', 'paladin', 'ranger', 'rogue', 'sorcerer', 'warlock', 'wizard', 'artificer']
# sheets that name only the subclass
SUBCLASS_OF = {'berserker': 'barbarian', 'battle master': 'fighter', 'champion': 'fighter', 'eldritch knight': 'fighter',
               'runeguard': 'fighter', 'rune knight': 'fighter', 'samurai': 'fighter', 'artillerist': 'artificer',
               'battle smith': 'artificer', 'armorer': 'artificer', 'alchemist': 'artificer', 'arcane trickster': 'rogue',
               'assassin': 'rogue', 'mastermind': 'rogue', 'thief': 'rogue', 'swashbuckler': 'rogue', 'inquisitive': 'rogue',
               'illusionist': 'wizard', 'evoker': 'wizard', 'abjurer': 'wizard', 'necromancer': 'wizard', 'diviner': 'wizard'}

def num(x, d=0):
    m = re.search(r'-?\d+', str(x or ''))
    return int(m.group()) if m else d

def classes_of(text, total=None):
    """'Cleric (Life Domain) 2, Warlock (the Fiend) 11' -> [{'class': 'cleric', 'sub': 'Life Domain', 'level': 2}, ...]"""
    out = []
    for sub, cls in SUBCLASS_OF.items():
        m = re.search(r'\b' + sub + r'\b\s*(\d+)?', text, re.I)
        if m and not re.search(r'\b' + cls + r'\b', text, re.I):
            out.append({'class': cls, 'sub': sub.title(), 'level': int(m.group(1)) if m.group(1) else total})
    for m in re.finditer(r'(' + '|'.join(CLASSES) + r')\s*(?:\(([^)]*)\))?\s*(\d+)?', text, re.I):
        out.append(dict(**{'class': m.group(1).lower()}, sub=(m.group(2) or '').strip(), level=int(m.group(3)) if m.group(3) else None))
    if len(out) == 1 and out[0]['level'] is None: out[0]['level'] = total
    return out

def read(path):
    r = pypdf.PdfReader(path)
    f = {k: str(v.get('/V')) for k, v in (r.get_fields() or {}).items() if isinstance(v, dict) and v.get('/V') not in (None, '', '/Off')}
    name = re.sub(r'\s*-?\s*Editable\.pdf$', '', os.path.basename(path)).strip()
    cls_txt = f.get('AdvLog.Class and Levels') or f.get('Class and Levels') or ''
    total = sum(map(int, re.findall(r'\b(\d+)\b', cls_txt))) or num(f.get('Character Level'), 0) or None
    spells = f.get('CurrentSpells.Stringified', '')
    def lst(key):
        out = []
        for m in re.finditer(key + r':\[([^\]]*)\]', spells):
            out += [x.strip().strip('"\'') for x in m.group(1).split(',') if x.strip().strip('"\'')]
        return out
    atks = []
    for i in range(1, 6):
        w = f.get(f'Attack.{i}.Weapon')
        if not w: continue
        atks.append(dict(name=w, hit=num(f.get(f'Attack.{i}.To Hit')), dmg=re.sub(r'\s+', '', f.get(f'Attack.{i}.Damage', '')),
                         type=f.get(f'Attack.{i}.Damage Type', '').strip().lower(), range=f.get(f'Attack.{i}.Range', ''),
                         desc=f.get(f'Attack.{i}.Description', '')))
    limited = []
    for i in range(1, 9):
        n = f.get(f'Limited Feature {i}')
        if n: limited.append(dict(name=n, uses=num(f.get(f'Limited Feature Max Usages {i}'), 1), recovery=f.get(f'Limited Feature Recovery {i}', '')))
    return dict(
        name=name, sheet_name=f.get('PC Name', name), classes=classes_of(cls_txt, total), class_text=cls_txt.strip(), level=total,
        race=f.get('Race Remember', ''), abilities={a.lower(): num(f.get(a), 10) for a in ABIL},
        save_prof=[a.lower() for a in ABIL if f.get(a + ' ST Prof')],
        skill_prof={SKILLS[k]: (2 if f.get(k + ' Exp') else 1) for k in SKILLS if f.get(k + ' Prof') or f.get(k + ' Exp')},
        ac=dict(armor=num(f.get('AC Armor Bonus'), 10), dex=num(f.get('AC Dexterity Modifier')), shield=num(f.get('AC Shield Bonus')),
                misc=num(f.get('AC Misc Mod 1')) + num(f.get('AC Misc Mod 2')), armor_name=f.get('AC Armor Description', '')),
        attacks=atks, slots={int(l): num(f.get(f'SpellSlots.CheckboxesSet.lvl{l}')) for l in range(1, 10) if num(f.get(f'SpellSlots.CheckboxesSet.lvl{l}'))},
        cantrips=lst('selectCa'), spells=lst('selectSp'), always=lst('extra'), bonus_spells=lst('selectBo'),
        spell_dc=num(re.search(r'dc:(\d+)', spells).group(1)) if re.search(r'dc:(\d+)', spells) else None,
        spell_attack=num(re.search(r'attack:(-?\d+)', spells).group(1)) if re.search(r'attack:(-?\d+)', spells) else None,
        limited=limited, speed=num(f.get('Speed'), 30),
        resist=[f.get(f'Resistance Damage Type {i}', '').strip().lower() for i in range(1, 7) if f.get(f'Resistance Damage Type {i}', '').strip()])

def main(folder):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = {}
    for p in sorted(glob.glob(os.path.join(folder, '*.pdf'))):
        try: d = read(p)
        except Exception as e: print('could not read', p, e); continue
        out[d['name']] = d
        print(f"{d['name']:22s} {d['class_text'][:46]:46s} {d['race'][:18]:18s} AC {d['ac']['armor'] + d['ac']['dex'] + d['ac']['shield'] + d['ac']['misc']:2d}  {len(d['attacks'])} attacks, {len(d['cantrips'])} cantrips, {len(d['spells'])} spells")
    json.dump(out, open(os.path.join(here, 'roster', 'sheets.json'), 'w'), indent=1)
    print(f"{len(out)} sheets -> roster/sheets.json")

if __name__ == '__main__':
    main(sys.argv[1])
