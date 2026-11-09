---
type: reference
tags: [toolbox, simulation]
created: 2026-10-15
status: active
summary: Public README for the D&D playtest simulator on GitHub: what it does, how to run it, and how to write a module.
---
# D&D Playtest Simulator

Plays a D&D 5e adventure thousands of times with a party under full combat rules, rolling every die. It then reports where parties win, lose and die, and why, in a note written for the adventure's designer.

```bash
python3 -m playtest brief delian_tomb     # say what you want to learn
python3 -m playtest run delian_tomb       # play it 2,000 times
python3 -m playtest report delian_tomb    # write the report and the room map
```

Python 3.9+, no dependencies. `pypdf` is only needed for reading character-sheet and module PDFs.

## What it does

- **Runs whole adventures, not single fights.** An adventure is a map of rooms joined by doors and passages, written in [the module format](modules/README.md). Each room can hold monsters, traps, skill checks, loot, terrain, or a short script for anything unusual. The party moves through it from room to room.
- **The party makes its own choices.** Each member has a personality (caution, curiosity, boldness), drawn fresh each run for the stock party. The loudest voice speaks for the group, and the run's leader settles it when the rest clearly disagree; a choice one person would make alone is theirs, and the log names them. The party picks its route, weighs side trips, decides when to rest or retreat, and can take a deal, all from those personalities and what it can see. `--set voices=party` plays the original single party personality.
- **Combat follows the rules:**
  - attacks, saves, spells and slots;
  - conditions and concentration;
  - reactions, legendary and lair actions, regeneration;
  - morale, surprise, death saves.
- **Positioning is zone-based, not a grid.** Distance, difficult ground, high ground, chokepoints, cover, darkness and hazards all apply.
- **Monsters come from stat blocks.**
  - **Sources:** the 334 monsters of the 5e SRD are included. A stat block pasted from a PDF or written in a Markdown note works too.
  - **Tactics:** each monster weighs its options every turn: multiattack, breath weapons, spells, conditions, finishing off the wounded.
- **The party is built from rules.**
  - **The stock party** is a fighter, cleric, rogue and wizard at any level.
  - **Your own characters:** the class builder makes them from MPMB character sheets (`tools/read_sheets.py`), at any level.
- **The report answers a question.**
  - **The brief:** a short form where you say what you want to learn, and the targets (how often parties should finish, how many deaths you'll accept).
  - **The report** opens with your question, a plain account of what happened, and ranked priority items.
  - **Then the detail:** every room, fight and decision, a room map coloured by where runs ended, and standout runs you can replay roll by roll.

## Commands

Run from this folder.

| Command | What it does |
|---|---|
| `python3 -m playtest list` | Modules and their studies |
| `python3 -m playtest brief <module>` | Make the playtest brief (a Markdown note with properties) |
| `python3 -m playtest run <module>` | Run what the brief asks for |
| `python3 -m playtest run <module> all` | Run every study the module defines |
| `python3 -m playtest run <module> --party stock@3x5 --set traits=random` | A custom party (level 3, five PCs) and settings |
| `python3 -m playtest report <module>` | Write the report and map into `Reports/` |
| `python3 -m playtest replay <module> <study> <seed>` | One run again, roll by roll |
| `python3 -m playtest fight none --party stock --level 3 --monsters "owlbear, wolf x2" --terrain '{"distance": 60}'` | One fight 500 times |
| `python3 -m playtest validate <module>` | Check a module's map |
| `python3 -m playtest pdf "<module>.pdf" --out notes.txt` | A module PDF's text, for writing a new module |

## Layout

| | |
|---|---|
| `playtest/` | The engine |
| `modules/` | Adventures. `delian_tomb` is a worked example, and [the module guide](modules/README.md) explains the format |
| `roster/` | The stock party (`stock.json`). Add your own characters as `sheets.json` (from `tools/read_sheets.py`) or `extra.json` |
| `monsters/srd/` | The SRD monster list (see its NOTICE) |
| `tools/` | Character-sheet and PDF readers |

**Settings that belong to your machine** go in `local.json`, which git ignores, for example `{"statblocks": "/path/to/your/stat-block notes"}`. With that set, every stat block in that folder can be named in any module.

## Limits

- **No battle map.** Positioning is front rank, back rank and terrain zones.
- **Scripted players.** Real tables are smarter and stranger.
- **Thin on non-combat play.** Social scenes, mysteries and puzzles reduce to skill-check odds.

What it's good at: attrition across a whole adventure, which fights actually kill, the content parties never see, and the rulings and settings that swing the result.

The Delian Tomb is Matt Colville's free first-level adventure (MCDM). The module here encodes its rooms, encounters and checks for simulation; get the adventure itself from MCDM.
