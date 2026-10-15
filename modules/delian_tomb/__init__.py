"""The Delian Tomb (Matt Colville / MCDM), a first-level adventure, written as a declarative module.

Source: The Delian Tomb by Matt Colville / MCDM, the free first-level adventure (GM Binder edition). Parts 2-4: the tracks at the smithy, the
night in the Boar Wood, the goblin patrol, the tomb's entrance guards, the offering room (goblins equal to one more
than the party), the scythe trap, the bugbear and the goblin shaman in the Hall of the Oathkeeper, and the hidden tomb
of the Delian Order. The party wins by bringing Bess home.

This module is mostly data: every room but the tomb is fields on MODULE.node(). It's the worked example for
modules/README.md. Assumptions: the goblin shaman has no stat block in the adventure, so it's a goblin with a 2d6
necrotic spell attack; 'a number of potions' in the tomb is two; opening a sarcophagus raises one skeleton per PC.
"""
from playtest.module import Module
from playtest.decisions import choose, traits
from playtest import bestiary as B

MODULE = Module('delian_tomb', 'The Delian Tomb', levels=(1, 1), party_size=(3, 6),
                source='The Delian Tomb (Matt Colville / MCDM), free GM Binder edition',
                config=dict(potions_bought=1, max_short_rests=2, max_extra_long_rests=0, emergency_long_rest=False, wipe='death'))
m = MODULE
B.add_variant('goblin', 'Goblin Shaman', actions=[
    'Hex Bolt. Ranged Spell Attack: +4 to hit, range 60 ft., one target. Hit: 7 (2d6) necrotic damage.'])

def tomb(d, run, node):
    """Six sarcophagi and the Lord's. Opening one wakes righteous skeletons; a curious party may try it."""
    c, q, b = traits(run)
    run.potions += 2
    pick = choose(run, 'Tomb of the Delian Order: open a sarcophagus?',
                  {'open one': (0.2 + 0.6 * q, 'the Goblin Slayer and Delian mail are inside'), 'leave them be': (0.5 + 0.2 * c, 'it is a tomb')})
    if pick == 'open one':
        res = run.fight('Tomb: the righteous dead', B.group(f'skeleton x{len(run.alive)}'), 'normal', optional=True)
        if res == 'win': run.flags['goblin_slayer'] = True
    run.after_room()

L = lambda x, y: dict(x=x, y=y)
m.node('Smithy', name="Lars's smithy", checks=[dict(kind='check', skill='Sur', dc=10, tries=3, success=dict(flag='tracks'))], **L(0, 100))
m.node('Wood', name='The Boar Wood (night)', checks=[dict(kind='flag', flag='boar', chance=1 / 12)], **L(130, 100))
m.node('Patrol', name='Goblin patrol', encounter='goblin x2', stealth=dict(), after='rest',
       terrain=dict(distance=60, elevated='monsters', climb_dc=10),          # two goblins on the hilltop
       morale=dict(flee_at=1.0, after=2, ally_dies=True, alarm=True), **L(260, 100))
m.node('1', name='1 Entrance', encounter='goblin x2', stealth=dict(), skip_if_alarmed=True, terrain=dict(distance=30, cover=dict(monsters=2)),
       morale=dict(flee_at=2, after=1, alarm=True), **L(390, 100))
m.node('2', name='2 Offering Room', encounter='goblin x{n+1}', stealth=dict(), after='boss', terrain=dict(distance=20, light='dim'), **L(520, 100))
m.node('3', name='3 Pressure Plate Trap',
       checks=[dict(kind='trap', name='the scythe', detect=('Perc', 12), disarm=('tools', 10), blade_ok=True, save=('dex', 15),
                    dmg='1d8', type='slashing', small_safe=True)], after=None, **L(650, 100))
m.node('4', name='4 Hall of the Oathkeeper', encounter='bugbear, goblin shaman', importance='boss', prepare=True,
       terrain=dict(distance=20, cover=dict(monsters=2)),                  # the haze and the makeshift altar
       checks=[dict(kind='flag', flag='secret_door', chance=0.55)],
       loot=dict(potions=2, gold='2d20+10', flag='bess'), **L(780, 100))
m.node('5', name='5 Tomb of the Delian Order', script=tomb,
       appeal=lambda run, d: (0.3 + 0.5 * traits(run)[1], 'the statue opened a door'), **L(780, 0))
m.node('Home', name='Back to Villane with Bess', goal=True, **L(0, 0))

m.edge('Smithy', 'Wood'); m.edge('Wood', 'Patrol'); m.edge('Patrol', '1'); m.edge('1', '2'); m.edge('2', '3'); m.edge('3', '4')
m.edge('4', '5', gate=lambda run: run.flags.get('secret_door'), label='the secret door ("I give my word")')
m.edge('Smithy', 'Home', label='the road home')
m.goal_ready = lambda run: run.flags.get('bess', False)

def metrics(run):
    return dict(flags=dict(run.flags), alarmed=run.alarmed, gold=run.metrics.get('gold', 0), surprised=run.metrics.get('surprised', {}))
m.metrics = metrics

def report(rows):
    n = len(rows); P = lambda x: f"{100 * x:.1f}%"
    f = lambda k: sum(1 for r in rows if r['m']['flags'].get(k)) / n
    sur = lambda k: sum(1 for r in rows if r['m']['surprised'].get(k)) / n
    return ['| | |', '|---|---|', f"| Found the tracks (DC 10 Survival, three tries) | {P(f('tracks'))} |",
            f"| Surprised the patrol / the guards / the offering room | {P(sur('Patrol'))} / {P(sur('1'))} / {P(sur('2'))} |",
            f"| Goblins fled and raised the alarm | {P(sum(r['m']['alarmed'] for r in rows) / n)} |",
            f"| Rescued Bess | {P(f('bess'))} |", f"| Found the tomb / took the Goblin Slayer | {P(f('secret_door'))} / {P(f('goblin_slayer'))} |"]
m.report = report

m.study('stock', 'stock', 2000, 41, desc='The stock party: fighter, cleric, rogue, wizard at 1st level', label='Stock party')
m.study('three', 'stock@1x3', 2000, 41, desc='Fighter, cleric and rogue only: a three-player table', label='Three PCs')
m.study('five', 'stock@1x5', 2000, 41, desc='A five-player table (a second fighter)', label='Five PCs')
m.study('level2', 'stock@2', 2000, 41, desc='The stock party at 2nd level', label='Stock party, 2nd level')
