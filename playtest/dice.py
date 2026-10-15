"""Dice, probabilities and the run log. Every roll in the simulator goes through R, so a seed replays a run exactly."""
import random, re

R = random.Random()
VERBOSE = [False]
LOG = []
def log(s):
    if VERBOSE[0]: LOG.append(s)

_dice_re = re.compile(r'([+-]?)\s*(\d+d\d+|\d+)')
def avg(expr):
    t = 0.0
    for sign, term in _dice_re.findall(expr):
        if 'd' in term:
            n, s = map(int, term.split('d')); v = n * (s + 1) / 2
        else: v = int(term)
        t += -v if sign == '-' else v
    return t
DICE = []
LAST_D20 = [None]
def roll(expr, crit=False):
    t = 0
    for sign, term in _dice_re.findall(expr):
        if 'd' in term:
            n, s = map(int, term.split('d'))
            if crit: n *= 2
            rs = [R.randint(1, s) for _ in range(n)]
            v = sum(rs)
            if VERBOSE[0]: DICE.append(f"{n}d{s}[{','.join(map(str, rs))}]")
        else: v = int(term)
        t += -v if sign == '-' else v
    return max(0, t)
def d20(adv=0, lucky=False):
    def one():
        r = R.randint(1, 20)
        if lucky and r == 1: r = R.randint(1, 20)
        return r
    if adv > 0:
        a, b = one(), one(); LAST_D20[0] = f"adv {a},{b}→{max(a,b)}"; return max(a, b)
    if adv < 0:
        a, b = one(), one(); LAST_D20[0] = f"dis {a},{b}→{min(a,b)}"; return min(a, b)
    r = one(); LAST_D20[0] = str(r); return r
def net(adv): return 1 if adv > 0 else -1 if adv < 0 else 0
def p_hit(bonus, ac, adv=0):
    need = ac - bonus
    p = min(0.95, max(0.05, (21 - need) / 20))
    if adv > 0: return 1 - (1 - p) ** 2
    if adv < 0: return p * p
    return p
def p_save(mod, dc, adv=0): return p_hit(mod, dc, adv)
