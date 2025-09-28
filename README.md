# Chord Chart Converter — Plain Text → Markdown (for `markdown-it-chords`)

## Overview

This repository contains a small **Python** utility that converts plain-text chord charts — where chord names are written on a line above the lyrics — into a Markdown file formatted for the [`markdown-it-chords`](https://dnotes.github.io/markdown-it-chords/) plugin.

The output is a single `.md` file where chords are embedded inline in the `[Chord]Lyrics` style that `markdown-it-chords` expects.

This README is a single `.md` file you can save and distribute with the converter script.

---

## What the script does (high level)

- **Detects chord-only lines** in plain-text charts using a conservative token heuristic (root note A–G, optional accidentals, typical quality/extension tokens, optional slash bass).
- **Merges chord lines and lyric lines**: when a chord-only line is directly above a lyric line, the script inserts bracketed chords (`[C]`, `[Em]`, etc.) into the lyric at approximately the same character column positions as the chords in the source.
- **Preserves structural labels and spacing**: lines like `[Chorus]`, `[Verse 1]`, and blank lines are preserved exactly.
- **Converts standalone chord-only lines** (e.g., an intro: `| B | A | E | E | x2`) into inline chord notation while preserving pipes and parenthetical annotations.
- **Writes output to a Markdown file** in the same folder where the script is run. The script chooses a safe filename and will avoid clobbering an existing file.

---

## Why this approach

- Plain-text chord sheets are often composed in monospaced editors with chords aligned by column. Inserting chords by *character column* generally preserves the intended alignment and makes the converted Markdown render nicely when processed by `markdown-it-chords`.
- A robust EOF-driven interactive mode is used so users can paste multi-line charts that include blank lines without confusion.
- The chord-detection heuristic tries to minimize false positives on lyrics while accepting the common chord notations you’ll see in songbooks.

---

## Requirements

- **Python 3.7+** (the scripts use only the standard library)
- No additional Python packages are required to run the converter itself.
- To render the `.md` visually (web preview, static site, etc.) using `markdown-it-chords`, you'll need a Markdown-It environment that supports that plugin (Node.js or a renderer that can load Markdown-It plugins).

`markdown-it-chords` docs: https://dnotes.github.io/markdown-it-chords/

---

## Files

- `convert_chords_verbose.py` — the main converter script (verbose comments included)
- Example input files (optional) — plain-text chord charts you can test with
- Output files: the script will create `basename_converted.md` (for file input) or `converted_chords.md` (for interactive/piped input), choosing a unique name if the default already exists

---

## Usage

Three main usage modes are supported. In all interactive cases **run the script first**, then paste your chart into the terminal window where the script is waiting for input; otherwise your shell will try to execute your pasted text as shell commands.

### 1) Convert an existing file

python convert_chords_verbose.py song.txt

- Reads `song.txt`
- Writes `song_converted.md` (or `song_converted_<timestamp>_<n>.md` if a collision occurs) in the current directory

### 2) Pipe a file into the script

cat song.txt | python convert_chords_verbose.py

- Useful for quick, non-interactive conversion
- Writes `converted_chords.md` (or `converted_chords_<timestamp>_<n>.md`) to the current directory

### 3) Interactive paste (recommended for quick one-offs)

python convert_chords_verbose.py

- The script will display instructions and wait for pasted input
- Paste your entire plain-text chart
- When finished, send EOF:
  - macOS / Linux terminals: Ctrl-D (on a new line)
  - Windows (cmd.exe): Ctrl-Z then Enter
- The script writes `converted_chords.md` (or a uniquely suffixed variant) in the current folder

**Important note:** If you paste the chart into your shell before running the script, the shell will execute each pasted line as a command (causing "command not found" errors). To avoid that:
- First run `python convert_chords_verbose.py`, then paste into the terminal where the script is running and send EOF
- Or use `cat song.txt | python convert_chords_verbose.py` or `python convert_chords_verbose.py song.txt`

---

## Example Input / Output

**Input (plain text, chords above lyrics)**

[Intro]

E

[Verse 1]
                              E
She never mentions the word "addiction"

In certain company
                              E
Yes, she'll tell you she's an orphan

After you meet her family

**Output (Markdown with inline `[Chord]` markers)**

[Intro]
[E]

[Verse 1]
[E]She never mentions the word "addiction"

In certain company
[E]Yes, she'll tell you she's an orphan

After you meet her family

---

## Notes, limitations, and tips

- **Heuristic detection:** Chord tokens are validated with a regex that matches typical chord notations (A–G, optional #/b, typical suffixes like m, maj7, sus4, optional /bass). It intentionally errs on the side of conservatism to avoid wrapping lyric words as chords
- **Alignment:** The converter aligns chords by text column. If the source used tabs or mixed spacing, alignment may be imperfect. For best results, use monospaced source text
- **Bar separators & annotations:** | tokens and parenthetical annotations such as (x2) are preserved when formatting chord-only lines
- **Transposition & features:** This script focuses only on conversion. If you want transposition, alternate instrument tunings, or automated chord simplification, those can be added as optional flags in a future enhancement

---

## Integrating with `markdown-it-chords`

- `markdown-it-chords` is a Markdown-It plugin that recognizes `[Chord]lyrics` syntax and renders chord symbols in a visually pleasant way (e.g., chords above lyrics)
- To preview or publish `.md` files generated by this converter in a browser or static site, ensure your Markdown pipeline uses markdown-it and includes the markdown-it-chords extension

**Node.js example setup:**

npm install markdown-it markdown-it-chords

**Example rendering script:**

const MarkdownIt = require('markdown-it');
const chords = require('markdown-it-chords');
const md = new MarkdownIt();
md.use(chords);
const html = md.render(markdownString);

If you're using a CMS, static site generator, or editor that supports Markdown-It plugins, install/configure `markdown-it-chords` there and open the `.md` output from this converter.

---

## Troubleshooting

- **"Command not found" when pasting:** Happens when you paste the text into the shell without first running the converter. Always run the script, then paste into the terminal where the script is awaiting input, or use a pipe/file input
- **Chords end up in the middle of words:** The converter inserts by character column. If the lyric line is shorter than the chord columns, chords will be appended at the end — manually adjust such cases or shorten chord spacing
- **Output file not where you expected:** The script writes the Markdown file to the directory where you ran the script (current working directory). Check the printed completion message for the exact path/name

---

## License

This converter and accompanying documentation are provided under the **MIT License** — do with it what you will. Attribution is appreciated but not required
