# Udemy to Anki

Converts saved Udemy practice exam pages into Anki flashcard decks (`.apkg`).

The script is fully self-contained — no reference `.apkg` file or external Anki installation is needed to generate the deck.

Please use the resulting flashcards in accordance with IP law. The platform might get more locked down if people misbehave.

## Requirements

- Python 3.8+
- [beautifulsoup4](https://pypi.org/project/beautifulsoup4/)
- [zstandard](https://pypi.org/project/zstandard/)

```bash
pip install beautifulsoup4 zstandard
```

## Anki note type

The generated deck uses a modified version of the **AllInOne (kprim, mc, sc)++sixOptions** note type. The note type definition is bundled inside the script, so it will be installed in Anki automatically on first import — no manual setup required.

## Saving a Udemy quiz page

1. Complete or review a Udemy practice exam so the results page is visible.
2. Save the page with your browser: **File → Save Page As → Webpage, Complete**.
   - This produces e.g. `My Exam.html` and a companion folder `My Exam_files/`.
3. Keep the HTML file and the `_files/` folder in the same directory — the script needs both.

## Usage

```bash
python create_anki_deck.py <html_file> [options]
```

### Arguments

| Argument | Description |
|---|---|
| `html_file` | Path to the saved Udemy results HTML file |
| `--output NAME` | Stem for output files (default: HTML filename without extension) |
| `--deck DECK` | Anki deck name, `::` separated (default: derived from filename) |
| `--deck-id ID` | Integer deck ID (default: auto-generated from current timestamp) |

### Output

Two files are written to the same folder as the input HTML:

- `<name>.apkg` — Anki package, ready to import via **File → Import**
- `<name>.txt` — Tab-separated export compatible with Anki's text importer

### Examples

```bash
# Minimal — deck name derived from the filename
python create_anki_deck.py "Course_ AWS Practice Exam 1 _ Udemy.html"

# Custom deck name
python create_anki_deck.py "exam1.html" --deck "All::AWS::Practice Exams"

# Custom output stem and deck name
python create_anki_deck.py "exam2.html" --output AWS_Exam2 --deck "All::AWS::Practice Exams"
```

## Project structure

```
create_anki_deck.py          # Self-contained script — run this
create_anki_deck_template.py # Source template (developer use)
build_script.py              # Regenerates create_anki_deck.py from template + seed DBs
seed_db_vacuumed.b64         # Embedded Anki collection.anki21 seed (gzip+base64)
seed_legacy.b64              # Embedded legacy collection.anki2 seed (gzip+base64)
card_templates/              # Reference copies of the AllInOne card templates
  front.txt
  back.txt
  styl.txt
```

## Rebuilding the script

If you modify `create_anki_deck_template.py` or the seed databases, regenerate the distributable script with:

```bash
python build_script.py
```

This inlines the base64-encoded seed databases into `create_anki_deck.py`.

## Attribution

The card templates incorporate [anki-persistence](https://github.com/SimonLammer/anki-persistence) (MIT) and portions derived from [Glutanimate's Cloze Overlapper](https://github.com/glutanimate/cloze-overlapper) (CC BY-SA 4.0). See [NOTICE.md](NOTICE.md) for full details.
