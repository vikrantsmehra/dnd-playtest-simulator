"""Who plays: the stock party, anyone the class builder can make, and (when present) a campaign's own characters.

  party('stock')                     fighter, cleric, rogue, wizard at the module's level
  party('stock@5x6')                 the stock party at 5th level, six strong (the fifth and sixth are Grukk, a barbarian, and Lyra, a bard)
  party(['B Stock Cleric@7', ...])   anyone in roster/stock.json, sheets.json or extra.json, built at any level
                                     by the class builder (playtest/builder.py)

A campaign can add hand-built characters and saved parties in roster/campaign.py (kept out of the public repository);
names it knows are passed to it.
"""
try:
    from roster import campaign as _campaign
except ImportError:
    _campaign = None

PARTIES = dict(getattr(_campaign, 'PARTIES', {}))

def make(name):
    """One character by name. 'B <name>@<level>' uses the class builder; anything else goes to the campaign roster."""
    if name.startswith('B '):
        from playtest.builder import build
        nm, _, lvl = name[2:].partition('@')
        return build(nm, int(lvl) if lvl else None)
    if _campaign is None:
        raise KeyError(f"'{name}' isn't a builder name ('B <name>@<level>') and there's no roster/campaign.py")
    return _campaign.make(name)

STOCK = ['Stock Fighter', 'Stock Cleric', 'Stock Rogue', 'Stock Wizard']
EXTRA = ['Stock Barbarian', 'Stock Bard']          # the fifth and sixth players
# What the write-up calls them. Logs use these names when one member acts or decides alone.
NICKNAMES = {'Stock Fighter': 'Clarence', 'Stock Cleric': 'Orik', 'Stock Rogue': 'Pip', 'Stock Wizard': 'Zirael',
             'Stock Barbarian': 'Grukk', 'Stock Bard': 'Lyra'}

def stock(level, size=4):
    """The stock party at any level: fighter, cleric, rogue, wizard; a fifth and sixth player add a barbarian and a bard."""
    names = (STOCK + EXTRA)[:size]
    return [f'B {n}@{level}' for n in names]

def names_for(key, level=None):
    """'stock', 'stock@5', 'stock@5x6' (level and size), a saved party key, or a list of names."""
    if isinstance(key, str) and key.startswith('stock'):
        rest = key[5:].lstrip('@')
        lvl, _, size = rest.partition('x')
        return stock(int(lvl) if lvl else (level or 1), int(size) if size else 4)
    return PARTIES[key] if isinstance(key, str) else key

def party(key, level=None):
    return [make(n) for n in names_for(key, level)]
