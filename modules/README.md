---
type: reference
tags: [toolbox, simulation]
created: 2026-10-14
status: active
summary: How to write a module for the Playtest Simulator, from a quick declarative one to a fully scripted one, with the checklist for turning a module PDF or prep note into a module file.
---
A module is one folder here, `modules/<slug>/`, with an `__init__.py` that defines `MODULE`. Modules come in three styles:

| Style | Use it for | Example |
|---|---|---|
| Almost all data | Most published adventures: rooms with encounters, stealth, morale and alarms, traps, loot | `delian_tomb` |
| Data plus a few scripts | A complex trap, a parley that ends a fight, a puzzle that changes the map | `script=` on a room (below) |
| Fully scripted, with its own rules | Hand-written bosses, module-wide rules through hooks, travel, session breaks, sequence breaks | write hooks against `playtest/hooks.py` |

## The skeleton

```python
from playtest.module import Module
from playtest.decisions import choose, traits
from playtest import bestiary as B

MODULE = Module('my_module', 'My Module', levels=(3, 4), party_size=(4, 5), source='path or PDF',
                config=dict(potions_bought=1, max_short_rests=2, wipe='death'))
m = MODULE

m.node('1', name='1 Gatehouse', encounter='goblin x{n}', stealth=dict(), x=0, y=0)
m.node('2', name='2 Chapel', encounter='ghoul x2, ghast', prepare=True, loot=dict(potions=1), x=120, y=0)
m.node('3', name='3 Crypt', encounter='wight, zombie x4', importance='boss', loot=dict(flag='relic'), x=240, y=0)
m.node('Out', name='Back to town', goal=True, x=0, y=80)
m.edge('1', '2'); m.edge('2', '3', lock=dict(dc=15, side='2'), label='the iron door')
m.edge('1', 'Out')
m.goal_ready = lambda run: run.flags.get('relic', False)
m.study('stock', 'stock', 2000, 1, desc='The stock party at 3rd level')
m.study('tight', 'stock@3x3', 2000, 1, desc='Three PCs instead of four')
```

Then:

```bash
python3 -m playtest validate my_module
python3 -m playtest brief my_module        # say what you want to learn
python3 -m playtest run my_module all
python3 -m playtest report my_module
```

## Rooms (`m.node`)

| Field | What it does |
|---|---|
| `encounter` | `'goblin x4, bugbear'`. `{n}` is the party size (`'goblin x{n+1}'`). Names are found in the module's own stat blocks, then your campaign's stat-block folder (set in `local.json`), then the 5e SRD |
| `importance` | `minor` / `normal` / `major` / `boss`. Leave it out and it's worked out from the DMG difficulty for the party. It decides how freely PCs spend slots and whether they can retreat |
| `stealth=dict()` | The party sneaks up: group Stealth against the monsters' best passive Perception (or `dc=`). Success means a surprise round |
| `morale=dict(flee_at=0.5, after=1, ally_dies=False, alarm=True)` | Monsters break off at that share of HP from round `after` (`1.0`: when hurt; `2`: on their first turn regardless). With `alarm`, they warn the next room: no surprise there, and they join its fight in round 2 |
| `skip_if_alarmed` | The room's monsters have already run off to warn the others |
| `checks` | A list run before the fight. `kind='trap'` (detect, disarm, save, damage, `small_safe`), `kind='check'` (a skill check with `success=`/`fail=` effects and `tries`), `kind='flag'` (something happens with a `chance`) |
| `loot` | `potions=2`, `gold='2d20+10'`, `flag='key'` |
| `after` | `'rest'` (default: the party decides whether to short-rest), `'boss'` (rest as if a boss is next), or `None` |
| `terrain` | The ground the room's fights are on, used by every fight there (including wandering monsters). See below |
| `prepare` | The party can tell something big is ahead and rests first if its resources are low |
| `optional` | A fight the party can walk away from |
| `appeal=lambda run, d: (score, reason)` | Why the party would head here next (signposting). Return `None` for the default (finish the area you're in, then the nearest room) |
| `roll` | Wandering monsters: `'first'` (first visit), `'always'`, `'never'`, or `lambda run, first: ...` when it depends on a setting |
| `patrol` | `'join'`: a wandering result joins the room's fight in round 2. `'first'`: fought on arrival |
| `script=fn(d, run, node)` | Do anything instead of the fields above. Return `False` if the room isn't cleared |
| `revisit=fn(d, run, node)` | What happens on later visits |
| `goal=True` | Reaching this room (once `m.goal_ready(run)` is true) ends the adventure |
| `x`, `y` | Where the room sits on the report's map |

## Doors (`m.edge`)

| Field | What it does |
|---|---|
| `gate=lambda run: ...` | Open only when true (a key, a lever, four judges dead) |
| `lock=dict(dc=15, side='2')` | Locked from that side. Anyone with `thieves_tools` gets one try |
| `oneway=True` | From `a` to `b` only |
| `detour=lambda run: (go, why, stay, why) or None` | A side trip the party weighs once, by personality and resources |

## The rest of the module

| Part | What it does |
|---|---|
| `m.wandering = Wandering({1: lambda run: [...], ...}, die=12, chance=lambda run: 1, rest_rolls=3)` | Wandering monsters |
| `m.prologue = fn(run)` | Before the first room (travel, an opening scene). Return `False` if the party didn't make it |
| `m.trigger('name', when=lambda run: ..., do=fn(d, run))` | Something that happens once a condition is true (a session break, a collapse) |
| `m.on('hook', fn)` | Module-wide rules plugged into the engine. The list is in `playtest/hooks.py` |
| `m.metrics = fn(run) -> dict` and `m.report = fn(rows) -> lines` | Extra numbers per run, and the module's own section of the report |
| `m.places`, `m.map_groups` | Extra map boxes (the road, a session break), and how studies are grouped into map panels |

## Decisions: group or individual?

Every party member has their own caution, curiosity and boldness. How they combine is the `voices` setting (see `playtest/decisions.py`): by default the loudest voice speaks for the party, and the run's leader settles it when the rest clearly disagree. `voices=party` plays the original single party personality.

- **A group choice** (where to go, whether to rest, a side trip) scores its options from `c, q, b = traits(run)`, the party's combined traits, and calls `choose(run, point, options)`. The leader is already folded into `traits(run)`, so a module never handles it.
- **A choice one person makes alone** (opening a sarcophagus, noticing a way past, stepping somewhere careless) names who acts, scores it with their own traits, and passes them to `choose` so the log names them:

```python
who = actor(run, 'curiosity')            # the most curious member, with a little noise; actor(run, 'caution', low=True) for the most careless
c, q, b = traits(run, who)
pick = choose(run, 'Tomb: open a sarcophagus?', {...}, who=who, trait='curiosity')
```

Under `voices=party`, `actor()` returns `None` and `traits(run, None)` is the party's, so the same code plays exactly as before.

## Terrain

Positioning is by zones, not a grid. Give a room `terrain=dict(...)` with any of:

| Field | What it does |
|---|---|
| `distance` | Feet between the sides when the fight starts. Melee can't connect until the gap closes (30 ft a round per side wanting melee, 15 on difficult ground); melee-only creatures spend those turns moving, everyone else shoots or casts |
| `difficult` | `True`, or `'party'` / `'monsters'` for one side: water, sand, rubble |
| `elevated` | `'monsters'` or `'party'` holds a ledge or gallery. Melee from below needs an Athletics check against `climb_dc` (default 12), which takes the turn |
| `chokepoint` | How many per side can fight in melee at once: a corridor, a doorway, a bridge |
| `cover` | `dict(monsters=2)` or `dict(party=5)`: AC against ranged attacks (half and three-quarters cover) |
| `light` | `'dark'` with `party_light=False` (and no `monster_light`): no darkvision means disadvantage to hit and advantage to be hit |
| `space` | `'cramped'` (area effects catch more) or `'open'` (fewer) |
| `hazard` | `dict(chance=0.2, save=('str', 12), dmg='1d6', type='bludgeoning', cond='prone', who='front', name='rockfall')`, each round |

A scripted fight can take its own: `run.fight(name, mons, env=dict(terrain=...))`.

## Monsters

- **By name:** anything in the SRD or the campaign's stat-block folder.
- **A module's own stat blocks:** `B.add_text(open('statblocks.md').read())` reads one or many (Obsidian, D&D Beyond or PDF style).
- **Variants:** `B.add_variant('skeleton', 'Storm-Kept Skeleton', ac=15, actions=['Scimitar. Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) slashing damage.'])`.
- **Bosses with real tactics:** write them by hand with `playtest.monster` (a constructor, targeting, and a turn function).

Check a fight on its own before running the module:

```bash
python3 -m playtest fight none --party stock --level 4 --monsters "owlbear, wolf x2" --log
```

## Turning a PDF or a prep note into a module

1. **Pull the text.** `python3 -m playtest pdf "<file>.pdf" --out notes.txt`. For stat blocks: `python3 tools/pdf_text.py "<file>.pdf" --statblocks modules/<slug>/statblocks.md`.
2. **List the rooms and the ways between them.** For each way, note any key, lock, secret or condition. Give rooms map coordinates.
3. **Fill in each room** with its encounter, traps, checks and loot. Anything a field can't say (a puzzle that changes the map, a choice, a parley) becomes a short script.
4. **Write down every guess** in the module's docstring: missing stat blocks, a number "a few" stood for, who says the password.
5. **Validate**, run one replay with `--log` and read it, then run the studies.
6. **Check against the source.** If something in the replay doesn't match what the text says should happen, the module is wrong, not the text.
