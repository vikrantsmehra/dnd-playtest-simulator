"""Hook points where a module plugs its own rules into the engine.

The engine knows 5e. Anything a single adventure invents (a lamp that reveals ghosts, bones that reassemble, a blade
to pull out of a boss's skull) lives in that module and attaches here. A run uses one module, so the registry is global:
the module's register() fills it before the first run, and clear() empties it.

Hooks the engine calls (arguments in brackets):
  attack_adv        (enc, attacker, target, atk) -> int added to the advantage tally
  unseen            (enc, pc, target) -> True if a needs-sight option can't target it
  after_damage      (enc, target, dealt)
  monster_zero      (enc, monster) -> True if the module handled a monster reaching 0 HP
  monster_down_turn (enc, monster)                 a downed (not dead) monster's turn
  pc_dropped        (pc)                           a PC drops to 0 HP
  encounter_init    (enc)
  encounter_over    (enc) -> 'win' / 'lose' / None to override the normal end check
  encounter_end     (enc, result)
  retreat_veto      (enc) -> True to stop a retreat
  ev_down_target    (pc, enc, opt, target) -> value of hitting a downed foe that will get back up
  strike_down_target(pc, enc, opt, target) -> True if the module resolved the strike
  run_setup         (run)                          module state on a fresh run
  day_start         (run)                          after every long rest
  fight_env         (run, env, name)               add module objectives and data to a fight
  reveal            (run) -> bool                  whether this fight is lit by the module's revealing light
  before_encounter  (run)
  after_win         (run, enc, name)
  escaped           (run, monsters)                downed foes the party walked away from
  wipe              (run, name) -> 'death' or 'capture'
"""
HOOKS = {}

def on(name, fn):
    HOOKS.setdefault(name, []).append(fn)

def clear():
    HOOKS.clear()

def first(name, *a):
    """Call each hook until one returns something other than None."""
    for f in HOOKS.get(name, ()):
        r = f(*a)
        if r is not None: return r
    return None

def each(name, *a):
    for f in HOOKS.get(name, ()):
        f(*a)

def total(name, *a):
    t = 0
    for f in HOOKS.get(name, ()):
        t += f(*a)
    return t

def has(name):
    return bool(HOOKS.get(name))
