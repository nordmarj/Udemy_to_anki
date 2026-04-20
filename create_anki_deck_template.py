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
                   Default: All::Software Engineering::AWS::
                             AWS MLS Machine Learning Specialty::AWS MLS Practice Exams
  --deck-id ID     Anki deck ID (integer). Default: 1768161246715.

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
import zipfile
import zstandard
from bs4 import BeautifulSoup

MODEL_ID = 1744270289295   # AllInOne (kprim, mc, sc)++sixOptions

# ── Embedded seed database ─────────────────────────────────────────────────────
# Minimal Anki collection.anki21 (gzip-compressed, base64-encoded).
# Contains the AllInOne (kprim, mc, sc)++sixOptions note type only; no notes/cards.
SEED_DB_B64 = (
%%SEED_DB_B64%%
)

# Minimal legacy collection.anki2 for backwards compatibility (gzip+base64).
SEED_LEGACY_B64 = (
%%SEED_LEGACY_B64%%
)

# Anki apkg meta file (protobuf: {version: 3}).  Required for correct import.
APKG_META = b'\x08\x03'

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


# ── Protobuf helpers (no external library needed) ─────────────────────────────

def _pb_varint(value):
    """Encode a non-negative integer as a protobuf varint."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            break
    return bytes(out)


def _pb_field(field_num, wire_type, payload):
    """Encode one protobuf field tag + payload."""
    tag = (field_num << 3) | wire_type
    return _pb_varint(tag) + payload


def _pb_len(field_num, data):
    """Wire type 2 (length-delimited) field."""
    return _pb_field(field_num, 2, _pb_varint(len(data)) + data)


def encode_media_protobuf(media_files):
    """
    Encode the media list as an Anki-format protobuf MediaEntries message.

    New-format .apkg uses protobuf for the media file:
      message MediaEntry { string name=1; int64 size=2; bytes sha1=3; }
      message MediaEntries { repeated MediaEntry entries=1; }
    """
    out = bytearray()
    for fpath in media_files:
        fname = os.path.basename(fpath)
        fsize = os.path.getsize(fpath)
        with open(fpath, 'rb') as f:
            sha1 = hashlib.sha1(f.read()).digest()  # 20 bytes
        inner = (
            _pb_len(1, fname.encode('utf-8')) +  # name
            _pb_field(2, 0, _pb_varint(fsize)) +  # size (varint)
            _pb_len(3, sha1)                       # sha1
        )
        out += _pb_len(1, inner)  # repeated entries = 1
    return bytes(out)


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

    # 3. Re-compress with zstd
    with open(db_path, 'rb') as f:
        raw = f.read()
    cctx = zstandard.ZstdCompressor()
    compressed_new = cctx.compress(raw)

    # 4. Build media file in protobuf format (required for new-format .apkg)
    media_proto = encode_media_protobuf(media_files)
    media_compressed = cctx.compress(media_proto)

    # 5. Write the .apkg
    # Note: collection.anki2 omitted — it doesn't contain the AllInOne model
    # anyway (only default models), and with meta=ver=3 Anki uses anki21b.
    with zipfile.ZipFile(OUTPUT_APKG, 'w', zipfile.ZIP_STORED) as zout:
        zout.writestr('meta', APKG_META)
        zout.writestr('collection.anki21b', compressed_new)
        zout.writestr('media', media_compressed)

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
