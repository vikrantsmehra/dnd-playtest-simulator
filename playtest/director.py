"""The director plays a module: it walks the party around the map, rolls wandering monsters, tries locked doors,
weighs detours, fires the module's triggers and decides where to go next until the party reaches the goal or fails.

Where to go next: every unexplored room the party can reach is a candidate. A module can give a room its own appeal
(a signposted route, a lamp that points the way); otherwise the party prefers to finish the area it's in, then the
nearest unexplored room. Once the goal is reachable, a curious party may still explore what's left first.
"""
from .run import *
from .decisions import draw_traits, party_traits, res_score, choose, traits
from .dice import R, VERBOSE, LOG, log
from . import hooks as H

class Director:
    def __init__(s, module, run):
        s.m = module; s.run = run
        s.visited = set(); s.cleared = set()
        s.lock_tried = set(); s.lock_open = set()
        s.detour_decided = {}           # edge index -> 'go' / 'stay'
        s.fired = set()
        s.at = None
        run.director = s
        run.route = []; run.decisions = []
    # ---------- the map ----------
    def edge_open(s, e, frm):
        if e.oneway and frm != e.a: return False
        if e.gate and not e.gate(s.run): return False
        i = s.m.edges.index(e)
        if e.lock and i not in s.lock_open:
            side = e.lock.get('side')
            if side is None or side == frm: return False
        if e.detour and s.detour_decided.get(i) == 'stay' and e.detour(s.run) is not None: return False
        return True
    def can_leave(s, n, to):
        node = s.m.nodes[n]
        return n in s.cleared or not node.blocks or to in s.visited
    def reach(s, frm=None):
        """Shortest paths from where the party stands, through rooms it has already visited.
        Returns {node: path} for every room it could walk into next."""
        frm = frm or s.at
        paths = {frm: [frm]}; todo = [frm]
        while todo:
            n = todo.pop(0)
            if n != frm and n not in s.visited: continue          # can't walk through an unexplored room
            for e in s.m.adj(n):
                o = e.other(n)
                if o in paths or not s.edge_open(e, n) or not s.can_leave(n, o): continue
                paths[o] = paths[n] + [o]; todo.append(o)
        return paths
    # ---------- moving ----------
    def enter(s, nid, label=None):
        run = s.run; node = s.m.nodes[nid]
        first = nid not in s.visited
        if first and node.prepare: s.prepare(node)
        run.room = label or (nid if first else getattr(node, 'revisit_label', None) or nid)
        run.room_terrain = getattr(node, 'terrain', None)
        run.route.append(nid)
        s.at = nid
        r = node.roll
        roll = r(run, first) if callable(r) else (r == 'always' or (r == 'first' and first))
        log(f"=== {run.room} ===")
        t = run.wander_roll(run.room) if roll else None
        run.pending_wander = t
        if t and node.patrol == 'first':
            run.pending_wander = None
            run.fight(f'{nid} wandering monsters', [], patrol=t)
        if first:
            s.visited.add(nid)
            res = node.script(s, run, node) if node.script else s.default_script(run, node)
            if res is not False: s.cleared.add(nid)
        elif node.revisit:
            res = node.revisit(s, run, node)
            if res is True: s.cleared.add(nid)
        s.flush_wander()
        s.try_locks(nid)
        s.fire_triggers()
    def flush_wander(s):
        t = s.run.pending_wander
        if t:
            s.run.pending_wander = None
            s.run.fight(f'{s.at} wandering monsters', [], patrol=t)
    def take_wander(s):
        t = s.run.pending_wander; s.run.pending_wander = None
        return t
    def walk_to(s, nid):
        """Walk to a room by the shortest known way, entering each room on the way."""
        if nid == s.at: return True
        path = s.reach().get(nid)
        if not path: return False
        for n in path[1:]:
            here = s.at
            s.enter(n)
            if s.run.outcome: return False
            if s.at != n: return False             # a trigger moved the party; plan again
        return True
    def prepare(s, node):
        """Before a room the party believes holds a judge or worse: rest if resources are short of a caution-based bar."""
        run = s.run; c = run.traits['caution']
        if res_score(run) < 0.6 + 0.3 * c:
            if run.maybe_short_rest(before_boss=True):
                run.decisions.append(('before ' + node.name, 'short rest', f'resources {res_score(run):.2f} below the caution bar'))
    # ---------- locks and triggers ----------
    def try_locks(s, nid):
        run = s.run
        for i, e in enumerate(s.m.edges):
            if not e.lock or i in s.lock_tried or nid not in (e.a, e.b): continue
            side = e.lock.get('side')
            if side is not None and side != nid: continue
            if e.other(nid) in s.visited: continue
            if e.gate and not e.gate(run): continue
            pickers = [p for p in run.alive if getattr(p, 'thieves_tools', None) is not None]
            if not pickers and not e.lock.get('anyone'): continue
            s.lock_tried.add(i)
            ok = False
            for p in pickers:
                if d20(-1 if p.exh else 0) + p.thieves_tools >= e.lock['dc']: ok = True; break
            run.metrics.setdefault('locks', {})[e.label or f'{e.a}-{e.b}'] = ok
            if ok:
                s.lock_open.add(i); run.events.append(f"picked the lock: {e.label or e.a + '–' + e.b}")
    def fire_triggers(s):
        for t in s.m.triggers:
            if (t.once and t.name in s.fired) or not t.when(s.run): continue
            s.fired.add(t.name)
            t.do(s, s.run)
            if s.run.outcome: return
    # ---------- choosing ----------
    def default_appeal(s, nid, path):
        dist = len(path) - 1
        if dist == 1: return (0.8 - 0.02 * dist, 'the next room on from here')
        return (0.5 - 0.02 * dist, 'the nearest unexplored room')
    def candidates(s):
        run = s.run
        paths = s.reach()
        goal = None; new = {}; retry = {}
        for n, p in paths.items():
            node = s.m.nodes[n]
            if n == s.at: continue
            if node.goal:
                if s.m.goal_ready(run) and n not in s.visited: goal = (n, p)
                continue
            if n not in s.visited: new[n] = p
            elif n not in s.cleared and node.blocks: retry[n] = p
        return goal, new, retry
    def detours(s, new):
        """Side trips the party weighs once, when they first open up. Returns a room to head to now, if any."""
        run = s.run
        for n, p in list(new.items()):
            a, b = p[-2], p[-1]
            e = next((e for e in s.m.adj(a) if e.other(a) == b and s.edge_open(e, a)), None)
            if e is None or not e.detour: continue
            d = e.detour(run)
            if d is None: continue
            i = s.m.edges.index(e)
            if i not in s.detour_decided:
                go, gr, stay, sr = d
                pick = choose(run, f'{s.m.nodes[a].name}: {e.label or "a way to " + s.m.nodes[b].name}',
                              {'go': (go, gr), 'stay': (stay, sr)})
                s.detour_decided[i] = pick
                if pick == 'go': return n
            if s.detour_decided[i] == 'stay': new.pop(n)
        return None
    def step(s):
        """Pick the next room and go there. False when there's nowhere left to go."""
        run = s.run
        goal, new, retry = s.candidates()
        nxt = s.detours(new)
        if nxt is None:
            opts = {}
            c, q, b = traits(run)
            if goal:
                opts[goal[0]] = (0.6 - 0.3 * q, 'head for the goal')
                for n in new: opts[n] = (0.25 + 0.4 * q, 'curious about what is left')
            else:
                for n, p in new.items():
                    node = s.m.nodes[n]
                    a = node.appeal(run, s) if node.appeal else None
                    opts[n] = a if a is not None else s.default_appeal(n, p)
                need = s.m.goal_ready(run)
                for n in retry:
                    node = s.m.nodes[n]
                    a = node.retry(run, s) if node.retry else ((0.8, 'it stands between the party and the goal') if need else None)
                    if a is not None: opts[n] = a
            if not opts: return False
            if len(opts) == 1: nxt = next(iter(opts))
            else: nxt = choose(run, f'at {s.m.nodes[s.at].name}: where next', opts)
        s.walk_to(nxt)
        return True
    def play(s):
        run = s.run
        run.traits = party_traits(run)
        c, q, b = traits(run)
        run.sr_thresh = 0.5 + 0.3 * c            # cautious parties rest sooner
        run.retreat_frac = 0.5 - 0.25 * c        # and pull out of a losing fight sooner
        try:
            if s.m.prologue and s.m.prologue(run) is False: return run
            run.day_start()
            s.enter(s.m.start)
            for _ in range(400):
                if run.outcome: break
                if s.at in s.m.nodes and s.m.nodes[s.at].goal and s.m.goal_ready(run):
                    run.outcome = 'complete' if run.captures == 0 else 'complete after capture'
                    break
                if not s.step():
                    run.outcome = 'stuck'; run.fail_room = run.room; break
        except Stop:
            pass
        if not run.alive and not run.outcome: run.outcome = 'wiped'
        return run
    # ---------- declarative rooms ----------
    def default_script(s, run, node):
        from .encounters import run_room
        return run_room(s, run, node)

def play(module, pcs, cfg=None, verbose=False):
    """One playthrough. cfg overrides the module's defaults."""
    cfg = dict(module.config, **(cfg or {}))
    VERBOSE[0] = verbose; LOG.clear()
    run = Run(pcs, cfg, module)
    return Director(module, run).play()
