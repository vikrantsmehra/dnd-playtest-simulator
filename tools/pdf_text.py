"""A module PDF's text, page by page, for drafting a new module file (and its stat blocks).

  python3 -m playtest pdf "<file.pdf>" --out notes.txt
  python3 tools/pdf_text.py "<file.pdf>" [--statblocks out.md]

--statblocks pulls every stat block it can find (anchored on 'Armor Class') into one Markdown file that
playtest.bestiary.add_text() can read.
"""
import sys, re
import pypdf

def extract(path):
    r = pypdf.PdfReader(path)
    out = []
    for i, p in enumerate(r.pages):
        t = p.extract_text() or ''
        out.append(f"\n===== page {i + 1} =====\n{t}")
    return '\n'.join(out)

def statblocks(text):
    """Cut the text around each 'Armor Class': back to the name and size line, forward to the next block."""
    lines = text.split('\n')
    idx = [i for i, l in enumerate(lines) if re.match(r'\s*Armor Class\s*\d+', l)]
    blocks = []
    for k, i in enumerate(idx):
        start = i
        for j in range(i - 1, max(0, i - 5), -1):
            if re.search(r'\b(Tiny|Small|Medium|Large|Huge|Gargantuan)\b', lines[j]): start = j - 1; break
        end = idx[k + 1] - 2 if k + 1 < len(idx) else min(len(lines), i + 60)
        blk = '\n'.join(lines[max(0, start):end]).strip()
        name = lines[max(0, start)].strip()
        blocks.append(f"## {name}\n{blk}\n")
    return '\n'.join(blocks)

if __name__ == '__main__':
    t = extract(sys.argv[1])
    if '--statblocks' in sys.argv:
        out = sys.argv[sys.argv.index('--statblocks') + 1]
        open(out, 'w').write(statblocks(t)); print(f'stat blocks -> {out}')
    else:
        print(t)
