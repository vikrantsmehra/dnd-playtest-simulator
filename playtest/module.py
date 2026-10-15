"""How a module describes itself: a map of rooms (nodes) joined by doors and passages (edges), plus wandering
monsters, triggers, a goal and the rules the module adds to the engine.

A module lives in modules/<slug>/__init__.py and defines MODULE = Module(...). Rooms can be declarative (an encounter
list, a few checks and some loot) or carry a script function when the room does something unusual. See
modules/README.md for the full format and modules/delian_tomb for a worked example.
"""
from .dice import R

class Node:
    """A room or area.

    script(d, run, node)      first visit. Return False if the room isn't cleared (the party backed off).
    revisit(d, run, node)     later visits (default: nothing beyond any wandering monsters).
    roll                      when entering rolls for wandering monsters: 'first' (first visit only), 'always', 'never',
                              or a function(run, first) -> bool when it depends on the run's settings.
    patrol                    'join' (a wandering result joins the room's first fight in round 2) or 'first' (fought on
                              arrival, before the room's own business).
    prepare                   the party can tell something big is ahead and rests first if its resources are low.
    blocks                    an uncleared room blocks passage beyond it (a guarded door, a boss).
    appeal(run, d)            the module's own (score, reason) for heading here next, or None for the default.
    goal                      reaching this room ends the adventure (once Module.goal_ready says so).
    encounter, importance, after, loot, checks: the declarative form, used when there's no script.
    """
    def __init__(s, id, name='', script=None, revisit=None, roll='first', patrol='join', prepare=False, blocks=True,
                 appeal=None, goal=False, encounter=None, importance=None, after='rest', loot=None, checks=None,
                 x=None, y=None, label=None, wing=None, notes='', retry=None, safe_rest=False, **extra):
        s.id = id; s.name = name or id; s.script = script; s.revisit = revisit
        s.roll = roll; s.patrol = patrol; s.prepare = prepare; s.blocks = blocks
        s.appeal = appeal; s.goal = goal
        s.encounter = encounter; s.importance = importance; s.after = after
        s.loot = loot or {}; s.checks = checks or []
        s.x = x; s.y = y; s.label = label or id; s.wing = wing; s.notes = notes
        s.retry = retry; s.safe_rest = safe_rest
        s.__dict__.update(extra)

class Edge:
    """A way between two rooms.

    gate(run) -> bool         open only when this is true (a key found, a lever pulled, four judges dead).
    lock                      dict(dc=15, side='a'): a locked door the party tries to open from that side
                              (thieves' tools, one attempt each); 'side' None means both sides are locked.
    oneway                    passable from a to b only.
    detour(run) -> (go, go_reason, stay, stay_reason) or None
                              a side trip the party weighs when it first becomes available. None means it isn't a
                              detour right now (just a normal way through).
    """
    def __init__(s, a, b, gate=None, lock=None, oneway=False, detour=None, label=''):
        s.a = a; s.b = b; s.gate = gate; s.lock = lock; s.oneway = oneway; s.detour = detour; s.label = label
    def other(s, n): return s.b if n == s.a else s.a

class Wandering:
    """A wandering-monster rule: roll d<die>, a hit on chance(run) or under, then d<table_die> on the table.
    table: {result: function(run) -> [monsters]} (an empty list means the result does nothing right now).
    rest_rolls: rolls during a long rest somewhere unsafe."""
    def __init__(s, table, die=12, chance=lambda run: 1, table_die=None, rest_rolls=3, names=None):
        s.table = table; s.die = die; s.chance = chance; s.table_die = table_die or len(table); s.rest_rolls = rest_rolls
        s.names = names or {}
    def roll(s, run, where):
        from .dice import log
        x = R.randint(1, s.die)
        c = s.chance(run)
        if x <= c:
            t = R.randint(1, s.table_die)
            log(f"    wandering roll d{s.die}={x} ≤ {c} → MONSTERS (d{s.table_die}={t})")
            return t
        return None
    def monsters(s, run, t):
        return s.table[t](run)

class Trigger:
    """when(run) -> bool, checked after every room; do(d, run) runs once (or every time if once=False)."""
    def __init__(s, name, when, do, once=True):
        s.name = name; s.when = when; s.do = do; s.once = once

class Study:
    """A batch the module ships with: who plays, how many runs, which settings."""
    def __init__(s, name, parties, n, seed, cfg=None, desc='', label=None):
        s.name = name; s.parties = parties; s.n = n; s.seed = seed; s.cfg = cfg or {}; s.desc = desc
        s.label = label or name

class Module:
    def __init__(s, slug, title, levels=None, party_size=(4, 4), config=None, source=''):
        s.slug = slug; s.title = title; s.levels = levels; s.party_size = party_size; s.source = source
        s.nodes = {}; s.edges = []; s.triggers = []; s.studies = {}
        s.config = dict(config or {})
        s.wandering = None
        s.start = None
        s.prologue = None              # function(run) -> False to end the run (travel, an opening scene)
        s.goal_ready = lambda run: True
        s.hooks = []                   # (name, fn) pairs registered with playtest.hooks before running
        s.metrics = None               # function(run) -> dict of extra numbers for the results rows
        s.places = {}                  # extra map places that aren't rooms: {label prefix: (x, y, name)}
        s.map_groups = None            # [(title, subtitle, [study, ...])]: map panels; default one per study
        s.report = None                # function(rows) -> Markdown lines for the report's module section
    # ---------- building ----------
    def node(s, id, **kw):
        n = Node(id, **kw); s.nodes[id] = n
        if s.start is None: s.start = id
        return n
    def edge(s, a, b, **kw):
        e = Edge(a, b, **kw); s.edges.append(e); return e
    def trigger(s, name, when, do, once=True):
        s.triggers.append(Trigger(name, when, do, once))
    def on(s, name, fn):
        s.hooks.append((name, fn))
    def study(s, name, parties, n, seed, cfg=None, desc='', label=None):
        s.studies[name] = Study(name, parties, n, seed, cfg, desc, label)
    # ---------- using ----------
    def register(s):
        from . import hooks as H
        H.clear()
        for name, fn in s.hooks: H.on(name, fn)
    def adj(s, n):
        return [e for e in s.edges if e.a == n or (e.b == n and not e.oneway)]
    def validate(s):
        """Problems a module author should fix: dangling edges, unreachable rooms, no goal."""
        out = []
        for e in s.edges:
            for x in (e.a, e.b):
                if x not in s.nodes: out.append(f"edge {e.a}–{e.b} names unknown room '{x}'")
        if not any(n.goal for n in s.nodes.values()): out.append('no room is marked goal=True')
        seen = {s.start}; todo = [s.start]
        while todo:
            n = todo.pop()
            for e in s.adj(n):
                o = e.other(n)
                if o in s.nodes and o not in seen: seen.add(o); todo.append(o)
        for n in s.nodes:
            if n not in seen: out.append(f"room '{n}' can't be reached from the start, even with every door open")
        for n in s.nodes.values():
            if n.script is None and n.encounter is None and not n.loot and not n.checks and not n.goal:
                out.append(f"room '{n.id}' has nothing in it (fine for a corridor; check it isn't missing its contents)")
        return out
