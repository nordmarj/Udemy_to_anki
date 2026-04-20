"""Helper to generate the self-contained create_anki_deck.py.

All files (template, seed .b64 files, output) live in the same directory
as this script.
"""
import textwrap, os

HERE = os.path.dirname(os.path.abspath(__file__))

data   = open(os.path.join(HERE, 'seed_db_vacuumed.b64')).read().strip()
legacy = open(os.path.join(HERE, 'seed_legacy.b64')).read().strip()

def wrap_b64(b64, indent=4):
    lines = textwrap.wrap(b64, 76)
    return '\n'.join((' ' * indent) + '"' + ln + '"' for ln in lines)

SEED_BLOCK   = wrap_b64(data)
LEGACY_BLOCK = wrap_b64(legacy)

template = open(os.path.join(HERE, 'create_anki_deck_template.py'),
                'r', encoding='utf-8').read()

out = template.replace('%%SEED_DB_B64%%', SEED_BLOCK)
out = out.replace('%%SEED_LEGACY_B64%%', LEGACY_BLOCK)

dest = os.path.join(HERE, 'create_anki_deck.py')
with open(dest, 'w', encoding='utf-8') as f:
    f.write(out)
print(f"Written {dest} ({len(out)} chars)")
