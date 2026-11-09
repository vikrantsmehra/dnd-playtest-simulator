"""One playthrough's state: the party, its resources, rests, fights, retreats and what happens on a wipe.

The director (playtest/director.py) moves the party around a module's map; room scripts call run.fight(), run.check()
and the rest helpers. Module-specific counters (keys found, braziers lit, holy water left) are plain attributes the
module's run_setup hook creates, and module rules plug in through playtest.hooks.
"""
from .pc import *
from . import hooks as H

class Stop(Exception):
    """Ends the run (wipe, abandonment, giving up)."""

class Run:
    def __init__(s, pcs, cfg, module=None):
        s.cfg = cfg; s.module = module
        s.pcs = pcs
        s.potions = cfg.get('potions_bought', 2)
        s.diamonds = cfg.get('diamonds', 1)                 # for revivify
        s.captures = 0; s.short_rests = 0
        s.wanders = []; s.drops = []; s.deaths = []; s.events = []
        s.enc_stats = {}
        s.outcome = None; s.fail_room = None
        s.room = 'start'
        s.metrics = {}                                      # anything a module wants in the results rows
        s.n = len(s.pcs)
        s.pending_wander = None                             # a wandering-monster result waiting to join the room's fight
        s.flags = {}                                        # keys found, doors opened, prisoners freed (module state)
        s.alarm = []                                        # monsters that fled to warn the next room
        s.alarmed = False
        for p in s.pcs: p.potions = 0
        H.each('run_setup', s)
    # ---------- helpers ----------
    @property
    def alive(s): return [p for p in s.pcs if not p.dead]
    def best(s, skill, pool=None):
        pool = pool or [p for p in s.alive if not p.down]
        return max(pool, key=lambda p: p.skills.get(skill, 0))
    def hp_frac(s):
        a = s.alive
        return sum(p.hp for p in a) / max(1, sum(p.maxhp for p in a))
    def give_potions(s):
        # potions travel with the front-liners who can feed them to fallen allies
        carriers = sorted(s.alive, key=lambda p: p.role != 'front')
        for p in s.pcs: p.potions = 0
        for i in range(s.potions): carriers[i % len(carriers)].potions += 1
    def collect_potions(s):
        s.potions = sum(p.potions for p in s.pcs if not p.dead)
    # ---------- wandering monsters ----------
    def wander_roll(s, where):
        w = s.module.wandering if s.module else None
        if not w: return None
        t = w.roll(s, where)
        if t is not None: s.wanders.append((where, t))
        return t
    def wander_mons(s, t):
        return s.module.wandering.monsters(s, t)
    # ---------- fights ----------
    def fight(s, name, mons, importance='normal', patrol=None, env=None, quicksand=0.0, arrivals=None, optional=False,
              retreat=None, join_wander=True):
        """Run a fight to its end, including retreats and rematches. patrol: a wandering-monster result that joins in
        round 2 (or is the whole fight if mons is empty). Returns 'win', 'retreat', 'captured' or 'dead'.
        optional fights return after a retreat or a capture instead of going again. A wandering result rolled on
        entering the room joins the room's first fight unless join_wander=False."""
        if patrol is None and join_wander and s.pending_wander:
            patrol = s.pending_wander; s.pending_wander = None
        arrivals = list(arrivals or [])
        if patrol:
            pm = s.wander_mons(patrol)
            if pm:
                if mons: arrivals.append((2, pm))
                else: mons = pm
        if not mons and not arrivals: return 'win'
        s.give_potions()
        env = dict(env or {})
        if getattr(s, 'room_terrain', None) and 'terrain' not in env: env['terrain'] = s.room_terrain   # the room's ground
        H.each('fight_env', s, env, name)
        if retreat is None: retreat = importance in ('major', 'boss')
        if retreat: env.setdefault('retreat_ok', True)
        env.setdefault('retreat_frac', getattr(s, 'retreat_frac', 0.5))
        env.setdefault('objectives', [])
        env['objectives'].append(potion_obj)
        while True:
            H.each('before_encounter', s)
            enc = Encounter([p for p in s.pcs if not p.dead], mons, name, room=s.room, reveal=bool(H.first('reveal', s)),
                            importance=importance, arrivals=arrivals, quicksand=quicksand, env=env)
            res = run_encounter(enc)
            s.collect_potions()
            st = s.enc_stats.setdefault(name, {'n': 0, 'rounds': 0, 'drops': 0, 'deaths': 0, 'lost': 0, 'hp_after': 0.0})
            st['n'] += 1; st['rounds'] += enc.round; st['drops'] += len(enc.drops); st['deaths'] += len(enc.deaths)
            s.drops += enc.drops; s.deaths += enc.deaths
            s.last_enc = enc
            if getattr(enc, 'special', None):
                st[enc.special] = st.get(enc.special, 0) + 1
                s.recover_ko()
                return enc.special
            if res == 'win':
                for room_, nm in list(enc.deaths):
                    cl = next((p for p in s.alive if 'revivify' in p.spells and p.slots.get(3, 0) > 0), None)
                    dead = next((p for p in s.pcs if p.name == nm and p.dead), None)
                    if cl and dead and s.diamonds > 0:
                        cl.slots[3] -= 1; s.diamonds -= 1; dead.dead = False; dead.down = False; dead.hp = 1; dead.fails = 0
                        s.deaths.remove((room_, nm)); s.events.append(f'{nm} revivified after {name}')
                        s.revived = getattr(s, 'revived', 0) + 1
                st['hp_after'] += s.hp_frac()
                esc = getattr(enc, 'escaped', None)
                if esc:
                    s.unbroken = getattr(s, 'unbroken', 0) + len(esc)
                    s.events.append(f'walked away from foes that would not stay down at {name}')
                    H.each('escaped', s, esc)
                    for m in esc: m.dead = True
                H.each('after_win', s, enc, name)
                s.recover_ko()
                st['won'] = st.get('won', 0) + 1
                return 'win'
            if res == 'retreat':
                s.retreats = getattr(s, 'retreats', 0) + 1
                up = [p for p in s.alive if p.up]; downed = [p for p in s.alive if p.down]
                for p in downed[len(up):]:
                    if R.random() < 0.4: continue        # hauled out on a rope / woken by a healing word
                    p.dead = True; s.deaths.append((s.room, p.name)); s.events.append(f'{p.name} left behind at {name}')
                if len(s.alive) * 2 < s.n:
                    s.outcome = 'abandoned (survivors leave)'; s.fail_room = name; raise Stop()
                for p in s.alive:
                    if p.down: p.down = False; p.hp = 0; p.ko = True
                s.events.append(f'retreat from {name}')
                st['retreats'] = st.get('retreats', 0) + 1
                s.recover_ko()
                s.long_rest('inside (after retreat)')
                if s.outcome: return 'dead'
                if optional: return 'retreat'
                mons = [m for m in mons if not m.dead and 'summoned' not in m.tags]
                for m in mons: m.cond = {}; m.down = False
                for m in mons:
                    if m.hp <= 0: m.hp = m.maxhp
                arrivals = []
                env['retreat_ok'] = st['retreats'] < 2
                continue
            st['lost'] += 1
            if not s.alive:
                s.outcome = 'wiped'; s.fail_room = name; raise Stop()
            rule = H.first('wipe', s, name) or s.cfg.get('wipe', 'death')
            if rule == 'death':
                for p in s.alive:
                    p.dead = True; s.deaths.append((s.room, p.name))
                s.outcome = 'wiped'; s.fail_room = name; raise Stop()
            # captured: the party wakes up locked away, rests, and gets another go at whoever beat them
            s.captures += 1
            if s.captures > s.cfg.get('max_captures', 3):
                s.outcome = f"gave up (captured {s.captures}x)"; s.fail_room = name; raise Stop()
            s.events.append(f'captured at {name}')
            for p in s.alive:
                if p.rot and p.hp <= 0: p.down = True; p.stable = True; continue
                p.down = False; p.hp = 1; p.stable = False
            s.long_rest('outside')        # locked up: wandering monsters can't reach them
            if s.outcome: return 'dead'
            if optional: return 'captured'
            for m in mons:            # the enemies that won stay at full strength
                m.dead = False; m.down = False; m.hp = m.maxhp; m.cond = {}
            mons = [m for m in mons if 'summoned' not in m.tags]
            arrivals = []
    def recover_ko(s):
        for p in s.alive:
            if p.hp <= 0 or p.ko:
                p.ko = False
                if p.rot and p.hp <= 0:            # cursed: can't regain HP, so stays unconscious and is carried
                    p.down = True; p.stable = True; p.hp = 0
                    continue
                healers = [h for h in s.alive if h.hp > 0]
                done = False
                for h in healers:
                    if h.uses.get('hl', 0) > 0: h.uses['hl'] -= 1; heal(p, roll('1d6')); done = True; break
                    if h.uses.get('loh', 0) > 0: h.uses['loh'] -= 1; heal(p, 1); done = True; break
                if not done:
                    for h in healers:
                        if getattr(h, 'healer', False) and h.slots_avail(1) and h.total_slots() > 2:
                            h.spend_slot(1); heal(p, roll('1d4+3')); done = True; break
                if not done and s.potions and not p.rot:
                    s.potions -= 1; heal(p, roll('2d4+2')); done = True
                if not done: p.hp = max(p.hp, 1)
                p.down = False
    # ---------- rests ----------
    def maybe_short_rest(s, before_boss=False, force=False):
        if s.short_rests >= s.cfg.get('max_short_rests', 3) and not force: return False
        need = s.hp_frac() < getattr(s, 'sr_thresh', 0.65) or any(p.hp < p.maxhp * 0.4 and p.hd > 0 for p in s.alive)
        sr_spent = any(p.uses.get(k, 1) < p.max_uses.get(k, 0) for p in s.alive for k in p.sr_keys) or \
            any(p.pact != p.max_pact for p in s.alive)
        if not (need or (before_boss and (sr_spent or s.hp_frac() < 0.9)) or force): return False
        if not any(p.hd > 0 for p in s.alive) and not sr_spent: return False
        s.short_rests += 1
        song = next((getattr(p, 'song_of_rest') for p in s.pcs if not p.dead and getattr(p, 'song_of_rest', None)), None)
        for p in s.alive: p.short_rest(song, recover=s.cfg.get('arcane_recovery', True))
        s.events.append(f'short rest ({s.room})')
        return True
    def long_rest(s, where):
        """where == 'outside' means somewhere safe; anywhere else rolls for wandering monsters."""
        if where != 'outside':
            w = s.module.wandering if s.module else None
            for _ in range(w.rest_rolls if w else 0):
                t = s.wander_roll(f'long rest ({where})')
                if t:
                    if R.random() < 0.5:
                        for p in s.alive: p.short_rest(recover=s.cfg.get('arcane_recovery', True))
                    r = s.fight('wandering monsters during rest', [], 'normal', patrol=t)
                    if r == 'dead': return
        for p in s.alive: p.long_rest()
        s.short_rests = 0
        s.day_start()
    def day_start(s):
        for c in s.alive:
            if 'aid' in c.spells and c.slots.get(2, 0) > 0:
                c.slots[2] -= 1
                for t in sorted(s.alive, key=lambda p: p.maxhp)[:3]:
                    t.maxhp += 5; t.hp += 5; t.cond['aid'] = True
                break
        H.each('day_start', s)
    def resources(s):
        a = s.alive
        hp = s.hp_frac()
        ms = sum(sum(p.max_slots.values()) + sum(p.max_pact.values()) for p in a)
        sl = sum(p.total_slots() for p in a) / ms if ms else 1
        hd = sum(p.hd for p in a) / max(1, sum(p.hd_max for p in a))
        return hp, sl, hd
    def after_room(s, can_rest=True, before_boss=False):
        if can_rest: s.maybe_short_rest(before_boss)
        hp, sl, hd = s.resources()
        if can_rest and getattr(s, 'extra_lr', 0) < s.cfg.get('max_extra_long_rests', 2) and ((hp < 0.55 and (sl < 0.35 or hd < 0.3)) or (sl < 0.2 and hd < 0.3) or hp < 0.4):
            s.extra_lr = getattr(s, 'extra_lr', 0) + 1
            s.events.append(f'long rest inside after {s.room}')
            s.long_rest('inside')
            return
        # emergency long rest if the party is spent (a module can rule it out: no time, no safe place)
        if s.cfg.get('emergency_long_rest', True) and s.hp_frac() < 0.35 and s.short_rests >= s.cfg.get('max_short_rests', 3) \
                and not any(p.hd for p in s.alive):
            s.events.append(f'emergency long rest after {s.room}')
            s.long_rest('inside')
