"""Helpers for hand-written monsters: a constructor, front-line targeting and the plain attack-everything turn.

Hand-written monsters are for bosses and anything with tactics worth scripting. Everything else can come from a stat
block through playtest.statblock, which builds the same kind of Creature with a generic brain.
"""
from .combat import *

def M(name, hp, ac, saves, **kw):
    return Creature(name, 'mon', hp, ac, saves, **kw)

def pick_front(enc, m, prefer=None):
    ts = enc.enemies(m)
    if not ts: return None
    if prefer:
        p = [t for t in ts if prefer(t)]
        if p: return R.choice(p)
    front = [t for t in ts if t.role == 'front']
    if front and R.random() < 0.8: return R.choice(front)
    return R.choice(ts)

def basic_turn(self, enc):
    for atk in self.attacks:
        t = pick_front(enc, self) if atk.get('melee') else (R.choice(enc.enemies(self)) if enc.enemies(self) else None)
        if t is None: return
        if enc.terrain and atk.get('melee') and not enc.terrain.can_melee(enc, self, t): return
        attack(enc, self, t, atk)

def bind(m, fn): m.turn = fn.__get__(m); return m
