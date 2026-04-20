"""
Convert Udemy HTML practice exam to Anki .apkg deck.

The AllInOne (kprim, mc, sc)++sixOptions model definition is bundled in this
script, so no reference .apkg file is needed.

Usage:
  python create_anki_deck.py <html_file> [options]

  html_file        Path to the saved Udemy quiz results HTML.
                   The companion _files/ folder must sit next to the HTML.

Options:
  --output NAME    Stem for output files (default: stem of html_file).
                   Produces NAME.apkg and NAME.txt in the same folder as html_file.
  --deck DECK      Anki deck name (use :: as separator).
                   Default: derived from the HTML filename.
  --deck-id ID     Anki deck ID (integer). Default: auto-generated.

Examples:
  python create_anki_deck.py "exam1.html"
  python create_anki_deck.py "exam2.html" --output MyExam2 --deck "All::AWS::Practice"
"""

import argparse
import base64
import gzip
import hashlib
import os
import re
import sqlite3
import tempfile
import time
import json
import zipfile
from bs4 import BeautifulSoup

MODEL_ID = 1744270289295   # AllInOne (kprim, mc, sc)++sixOptions

# ── Embedded seed database ─────────────────────────────────────────────────────
# Minimal Anki collection.anki21 (gzip-compressed, base64-encoded).
# Contains the AllInOne (kprim, mc, sc)++sixOptions note type only; no notes/cards.
SEED_DB_B64 = (
    "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"
)

# Minimal legacy collection.anki2 for backwards compatibility (gzip+base64).
SEED_LEGACY_B64 = (
    "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"
    "pbv+etyfqtwvjf4/HLeJIgDIAAA="
)

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    description='Convert Udemy HTML practice exam to Anki .apkg')
parser.add_argument('html_file', help='Path to the Udemy HTML file')
parser.add_argument('--output', default=None,
    help='Output stem (default: html filename without extension)')
parser.add_argument('--deck', default=None,
    help='Anki deck name (:: separated, default: derived from filename)')
parser.add_argument('--deck-id', type=int, default=None,
    help='Anki deck ID integer (default: auto-generated)')
args = parser.parse_args()

HTML_FILE = os.path.abspath(args.html_file)
BASE_DIR  = os.path.dirname(HTML_FILE)
stem      = args.output or os.path.splitext(os.path.basename(HTML_FILE))[0]
FILES_DIR = os.path.join(BASE_DIR, os.path.splitext(os.path.basename(HTML_FILE))[0] + '_files')

OUTPUT_APKG = os.path.join(BASE_DIR, stem + '.apkg')
OUTPUT_TXT  = os.path.join(BASE_DIR, stem + '.txt')

# Derive deck name from filename if not specified:
# Strip common Udemy prefixes/suffixes and use the stem directly.
def _stem_to_deck(s):
    import re as _re
    s = _re.sub(r'^Course[_ ]+', '', s)                    # "Course_ " prefix
    s = _re.sub(r'[_ ]+Udemy\s*$', '', s, flags=_re.I)    # " _ Udemy" suffix
    s = s.replace('_', ' ')
    s = _re.sub(r' {2,}', ' ', s).strip(' -')             # collapse extra spaces
    return s

DECK_NAME = args.deck or _stem_to_deck(stem)
DECK_ID   = args.deck_id or (int(time.time() * 1000) + 1)

print(f"HTML     : {HTML_FILE}")
print(f"Files dir: {FILES_DIR}")
print(f"Output   : {OUTPUT_APKG}")
print(f"Deck     : {DECK_NAME}")

# ── HTML helpers ──────────────────────────────────────────────────────────────

def process_images(element, media_files, image_map):
    """Resolve image references in-place; collect local files into media_files."""
    for wrapper in list(element.find_all(
            lambda t: t.name in ('span', 'div')
            and 'open-full-size-image' in ' '.join(t.get('class', [])))):
        img = wrapper.find('img', loading='eager') or wrapper.find('img')
        if img:
            src = img.get('src', '')
            fname = os.path.basename(src)
            fpath = os.path.join(FILES_DIR, fname)
            if os.path.exists(fpath):
                if fname not in image_map:
                    image_map[fname] = fname
                    media_files.append(fpath)
                new_img = BeautifulSoup(
                    f'<img src="{fname}" style="max-width:100%;">', 'html.parser').find('img')
                wrapper.replace_with(new_img)
            else:
                wrapper.decompose()
        else:
            wrapper.decompose()

    for img in list(element.find_all('img')):
        style = img.get('style', '').replace(' ', '')
        if 'display:none' in style:
            img.decompose()
            continue
        src = img.get('src', '')
        if not src or src.startswith('data:'):
            img.decompose()
            continue
        fname = os.path.basename(src)
        fpath = os.path.join(FILES_DIR, fname)
        if os.path.exists(fpath):
            if fname not in image_map:
                image_map[fname] = fname
                media_files.append(fpath)
            img['src'] = fname
        else:
            img.decompose()


def inner_html(element):
    return element.decode_contents().strip()


def extract_question_data(q_div, media_files, image_map):
    """Parse one question pane, return a dict."""
    prompt_el = q_div.find('div', {'id': 'question-prompt'})
    if prompt_el:
        process_images(prompt_el, media_files, image_map)
        question_html = inner_html(prompt_el)
    else:
        question_html = ''

    answer_divs = q_div.find_all('div', {'data-purpose': 'answer'})
    options, correct_mask = [], []
    for div in answer_divs:
        classes = ' '.join(div.get('class', []))
        is_correct = 'answer-correct' in classes
        text_el = div.find('div', {'id': 'answer-text'})
        if text_el:
            process_images(text_el, media_files, image_map)
            opt_html = inner_html(text_el)
        else:
            opt_html = ''
        options.append(opt_html)
        correct_mask.append(1 if is_correct else 0)

    n = len(options)
    answers_binary = ' '.join(str(b) for b in correct_mask)
    qtype = '1' if sum(correct_mask) > 1 else '2'

    while len(options) < 6:
        options.append('')

    # Collect explanations: per-answer (inside each answer-result-pane)
    # or overall (single block at the end).
    answer_result_panes = q_div.find_all(
        'div', class_=re.compile(r'result-pane--answer-result-pane--'))
    per_answer_expls = []
    for arp in answer_result_panes:
        expl_el = arp.find('div', id='question-explanation')
        if expl_el:
            # Get the answer text for context
            ans_div = arp.find('div', attrs={'data-purpose': 'answer'})
            ans_text_el = ans_div.find('div', id='answer-text') if ans_div else None
            label = ans_text_el.get_text(strip=True)[:120] if ans_text_el else ''
            is_correct = bool(arp.find(class_=re.compile(r'answer-correct')))
            process_images(expl_el, media_files, image_map)
            mark = '\u2705' if is_correct else '\u274c'
            per_answer_expls.append(
                f'<p><b>{mark} {label}</b></p>{inner_html(expl_el)}')

    if per_answer_expls:
        explanation_html = '<hr>'.join(per_answer_expls)
    else:
        exp_el = q_div.find('div', {'id': 'overall-explanation'})
        if exp_el:
            process_images(exp_el, media_files, image_map)
            explanation_html = inner_html(exp_el)
        else:
            explanation_html = ''

    title_span = q_div.find('span', class_=re.compile(r'result-pane--pane-title--'))
    qnum = 0
    if title_span:
        m = re.search(r'Question\s+(\d+)', title_span.get_text())
        if m:
            qnum = int(m.group(1))

    return {
        'qnum': qnum,
        'question': question_html,
        'options': options[:6],
        'answers_binary': answers_binary,
        'num_options': n,
        'qtype': qtype,
        'explanation': explanation_html,
    }


def field_checksum(sort_field_text):
    """Anki checksum: first 8 hex chars of SHA1 of the sort field (plain text)."""
    plain = re.sub(r'<[^>]+>', '', sort_field_text)  # strip HTML
    return int(hashlib.sha1(plain.encode('utf-8')).hexdigest()[:8], 16)


def guid_for(*args):
    """Same GUID generation as genanki.guid_for."""
    h = hashlib.sha256(str(args).encode('utf-8')).digest()[:6]
    return base64.b64encode(h).decode('ascii')


# ── Parse HTML ────────────────────────────────────────────────────────────────
print("Reading HTML...")
with open(HTML_FILE, encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')
question_panes = soup.find_all(
    'div', class_=re.compile(r'result-pane--question-result-pane--'))
print(f"Found {len(question_panes)} question panes")

media_files = []
image_map   = {}
all_data    = []

for i, q_div in enumerate(question_panes):
    data = extract_question_data(q_div, media_files, image_map)
    if not data['qnum']:
        data['qnum'] = i + 1
    all_data.append(data)
    mc_label = ' [MC]' if data['qtype'] == '1' else ''
    print(f"  Q{data['qnum']:2d}{mc_label}: {data['num_options']} opts, "
          f"ans={data['answers_binary']}")

print(f"\nTotal questions : {len(all_data)}")
print(f"Unique media files: {len(media_files)}")
for mf in media_files:
    print(f"  {os.path.basename(mf)}")

# ── Build .apkg using new Anki format ─────────────────────────────────────────
print("\nBuilding .apkg...")

with tempfile.TemporaryDirectory() as tmp:
    # 1. Decode embedded seed databases
    db_bytes     = gzip.decompress(base64.b64decode(SEED_DB_B64))
    legacy_anki2 = gzip.decompress(base64.b64decode(SEED_LEGACY_B64))

    db_path = os.path.join(tmp, 'collection.anki21')
    with open(db_path, 'wb') as f:
        f.write(db_bytes)

    # Register unicase collation (required by Anki's tag table)
    conn = sqlite3.connect(db_path)
    conn.create_collation('unicase', lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    cur = conn.cursor()

    # 2a. Replace seed deck hierarchy with the user's deck
    # Anki stores hierarchical deck names with \x1f as level separator.
    # Pre-compressed blobs for a normal deck (zstd-wrapped protobuf defaults).
    _DECK_KIND   = bytes.fromhex('28b52ffd20042100000a020801')  # NormalDeck
    _DECK_COMMON = bytes.fromhex('28b52ffd2000010000')           # all-default
    cur.execute("DELETE FROM decks WHERE id != 1")  # keep only Default
    parts      = [p.strip() for p in DECK_NAME.split('::')]
    now_sec    = int(time.time())
    base_id    = int(time.time() * 1000)
    for j, part in enumerate(parts):
        anki_name = '\x1f'.join(parts[:j+1])
        did = DECK_ID if j == len(parts) - 1 else (base_id + j + 2)
        cur.execute(
            "INSERT OR IGNORE INTO decks (id, name, mtime_secs, usn, common, kind) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (did, anki_name, now_sec, -1, _DECK_COMMON, _DECK_KIND))
    print(f"Deck     : {DECK_NAME}  (id={DECK_ID})")

    # 2b. Insert our new notes and cards
    base_id  = int(time.time() * 1000)  # ms timestamp base for IDs

    for i, data in enumerate(all_data):
        fields = [
            data['question'],      # Question
            '',                    # Title
            data['qtype'],         # QType
            data['options'][0],    # Q_1
            data['options'][1],    # Q_2
            data['options'][2],    # Q_3
            data['options'][3],    # Q_4
            data['options'][4],    # Q_5
            data['options'][5],    # Q_6
            data['answers_binary'],# Answers
            '',                    # Sources
            data['explanation'],   # Extra 1
        ]
        flds_str = '\x1f'.join(fields)
        sfld = re.sub(r'<[^>]+>', '', data['question'])  # plain text sort field
        csum = field_checksum(data['question'])
        nid  = base_id + i
        guid = guid_for(stem, str(data['qnum']))

        cur.execute(
            "INSERT INTO notes (id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (nid, guid, MODEL_ID, now_sec, -1, '', flds_str, sfld, csum, 0, ''))

        # One card per note (single template)
        cid = nid  # card ID = note ID for single-template notes
        due = i + 1  # new card due order
        cur.execute(
            "INSERT INTO cards (id, nid, did, ord, mod, usn, type, queue, due, "
            "ivl, factor, reps, lapses, left, odue, odid, flags, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, nid, DECK_ID, 0, now_sec, -1, 0, 0, due,
             0, 0, 0, 0, 0, 0, 0, 0, ''))

    conn.commit()
    conn.close()

    # 3. Read the final database
    with open(db_path, 'rb') as f:
        db_raw = f.read()

    # 4. Build media index (JSON: {"0": "filename.jpg", ...})
    media_index = {str(i): os.path.basename(fpath) for i, fpath in enumerate(media_files)}

    # 5. Write the .apkg (collection.anki21 format — compatible with all Anki 2.1+ versions)
    with zipfile.ZipFile(OUTPUT_APKG, 'w', zipfile.ZIP_STORED) as zout:
        zout.writestr('collection.anki21', db_raw)
        zout.writestr('media', json.dumps(media_index))

        for i, fpath in enumerate(media_files):
            zout.write(fpath, str(i))

print(f"\nCreated .apkg : {OUTPUT_APKG}")

# ── Write AllInOne-compatible .txt ────────────────────────────────────────────
# Column layout (16 cols, matches AllInOne (kprim, mc, sc)++sixOptions):
#  1=guid  2=notetype  3=deck  4=Question  5=Title  6=QType
#  7-12=Q_1..Q_6  13=Answers  14=Sources  15=Extra 1  16=tags

with open(OUTPUT_TXT, 'w', encoding='utf-8', newline='') as f:
    f.write('#separator:tab\n')
    f.write('#html:true\n')
    f.write('#guid column:1\n')
    f.write('#notetype column:2\n')
    f.write('#deck column:3\n')
    f.write('#tags column:16\n')
    for data in all_data:
        guid = guid_for(stem, str(data['qnum']))
        cols = [
            guid,
            'AllInOne (kprim, mc, sc)++sixOptions',
            DECK_NAME,
            data['question'],       # 4  Question
            '',                     # 5  Title
            data['qtype'],          # 6  QType (2=sc, 1=mc)
            data['options'][0],     # 7  Q_1
            data['options'][1],     # 8  Q_2
            data['options'][2],     # 9  Q_3
            data['options'][3],     # 10 Q_4
            data['options'][4],     # 11 Q_5
            data['options'][5],     # 12 Q_6
            data['answers_binary'], # 13 Answers
            '',                     # 14 Sources
            data['explanation'],    # 15 Extra 1
            '',                     # 16 tags
        ]
        f.write('\t'.join(cols) + '\n')

print(f"Created .txt  : {OUTPUT_TXT}")
print("Done!")
