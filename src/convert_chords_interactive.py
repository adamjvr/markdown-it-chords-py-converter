#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert_chords_verbose.py

PURPOSE
-------
This script converts plain-text chord charts (where chord names are written
on a line above the lyric line they belong to) into the "markdown-it-chords"
inline style where chords are embedded into lyrics like:

    [Em]Here are the [D]lyrics...

The program supports two main usage modes:
  1. File mode:
       python convert_chords_verbose.py input.txt
     This reads the input file and writes a converted file in the same folder
     with a "_converted.md" suffix, preserving the original filename base.

  2. Interactive / piped mode:
       python convert_chords_verbose.py
     The script will print instructions and then read from standard input until
     an EOF (End-Of-File) is received. On Unix/macOS press Ctrl-D on a new
     line to send EOF. On Windows (cmd.exe) press Ctrl-Z then Enter.
     Alternatively you can pipe in data:
       cat input.txt | python convert_chords_verbose.py

WHY EOF?
---------
We use EOF to end interactive paste input because chord charts commonly contain
blank lines — using a "blank line to finish" heuristic is ambiguous and easily
broken by real content. EOF is the conventional and reliable way to indicate
that the user's paste is complete. If you prefer a different finish-signal,
we can modify the script, but EOF is robust and standard.

ALGORITHM SUMMARY
-----------------
1. Read input (from a file, or from stdin/paste).
2. Split the input into lines (preserve the sequence of blank lines).
3. Walk lines with an index so we can look ahead:
   - If a line looks like a "chord-only" line (e.g., "Em    D    Bm  C" or
     " | B | A | E | E | x2"), we attempt to merge it with the next non-empty
     lyric line. The merge places bracketed chord tokens into the lyric
     at approximately the same column positions as in the chord line.
   - If the chord-only line has no lyrics following it (e.g. an instrumental
     intro), we render it as a single line where each chord token is wrapped
     in brackets (while preserving separators like '|' and annotations like '(x2)').
   - Lines that are not chord-only (headers like [Chorus], lyric lines, etc.)
     are passed through unchanged.
4. Write the converted lines into a Markdown file in the current working directory.

LIMITATIONS & NOTES
-------------------
- The script uses a heuristic to decide if a token is a chord (root A-G, optional
  accidental, optional quality/number, optional slash bass). This covers most
  common guitar/band chord notations but is not guaranteed to match every
  possible exotic notation. The detection is intentionally conservative to
  reduce false positives.
- The algorithm aligns chords by *character column*, which works well for
  monospace-typed plain text. It's an approximation — for variable-width fonts
  or messy spacing the alignment can be off.
- Chord tokens inside chord lines are detected using a regular expression and
  tokens that are separators (pipes '|') or parenthetical annotations (x2, (x2))
  are preserved.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from typing import List, Tuple

# ------------------------------------------------------------------------------
# Regex definitions and token helpers
# ------------------------------------------------------------------------------
# The chord token regex attempts to capture common chord shapes:
#
#   Root:
#     [A-G]                     -> A through G
#     (?:#|b)?                  -> optional sharp (#) or flat (b)
#
#   Optional quality / extension:
#     (?:
#         (?:maj|min|m|dim|aug|sus|add)  -> common keywords
#         \d*                            -> optional digits like 7,9,11,13
#     )?
#
#   Optional slash bass:
#     (?:/[A-G](?:#|b)?)?       -> e.g. C/E or G#/Bb
#
# Entire pattern anchored with ^ and $ so we match the whole token.
#
# We compile with re.IGNORECASE to accept lowercase tokens as well (some charts
# are inconsistent with capitalization).
CHORD_TOKEN_RE = re.compile(
    r"^[A-G](?:#|b)?(?:(?:maj|min|m|dim|aug|sus|add)\d*)?(?:/[A-G](?:#|b)?)?$",
    re.IGNORECASE,
)

# Parenthetical annotations are things like "(x2)" or "(repeat)". Some chord
# lines append these annotations; we should allow them on chord-only lines so
# they don't make the line look non-chord-like.
PAREN_ANNOTATION_RE = re.compile(r"^\(.*\)$")

# A "bar separator" token like '|' appears in many chord charts to show bar
# boundaries. We treat this as a neutral token that doesn't invalidate a
# chord-only line.
BAR_SEPARATOR_RE = re.compile(r"^\|+$")


# ------------------------------------------------------------------------------
# Token classification helpers
# ------------------------------------------------------------------------------
def is_chord_token(token: str) -> bool:
    """
    Return True if the single whitespace-delimited token looks like a chord.

    - Strips whitespace and tests the token against CHORD_TOKEN_RE.
    - Examples that return True: "C", "Am", "F#m7", "Bbmaj7", "G7", "C/E"
    - Examples that return False: "She", "the", "and", "Hello", "word"
    """
    if not token:
        return False
    return bool(CHORD_TOKEN_RE.match(token.strip()))


def is_parenthetical_annotation(token: str) -> bool:
    """
    Return True if the token is a parenthetical annotation like "(x2)".

    These are allowed on chord-only lines and should be preserved verbatim.
    """
    return bool(PAREN_ANNOTATION_RE.match(token.strip()))


def is_bar_separator(token: str) -> bool:
    """
    Return True if the token looks like a bar separator such as '|' or '||'.

    Charts use '|' to show measure boundaries. These tokens are neither lyric
    nor chord; treat them as neutral/preserved tokens.
    """
    return bool(BAR_SEPARATOR_RE.match(token.strip()))


def is_chord_only_line(line: str) -> bool:
    """
    Determine whether a given line should be classified as a "chord-only" line.

    Heuristic:
      - Split the line by whitespace into tokens.
      - The line is chord-only if:
          * there is at least one token, and
          * every token is one of:
              - a recognized chord token (is_chord_token)
              - a bar separator token ('|' etc.)
              - a parenthetical annotation like '(x2)'
      - This allows lines like:
          "Em Bm D C"
          "| B | A | E | E | x2"
          "A  E  (x2)"
      - It rejects lines that contain ordinary lyric words.
    """
    tokens = [tok for tok in line.split() if tok != ""]
    if not tokens:
        # Empty lines are not considered chord-only.
        return False
    for tok in tokens:
        if not (
            is_chord_token(tok)
            or is_parenthetical_annotation(tok)
            or is_bar_separator(tok)
        ):
            return False
    return True


# ------------------------------------------------------------------------------
# Merge algorithm: insert bracketed chords into lyric lines
# ------------------------------------------------------------------------------
def merge_chords_and_lyrics(chord_line: str, lyric_line: str) -> str:
    """
    Overlay chords (from chord_line) onto lyric_line by inserting bracketed chord
    markers at approximate column positions.

    Implementation details and reasoning:
      - We locate chord tokens in chord_line using re.finditer(r'\S+'),
        which yields each token and its starting character index.
      - For each token that is recognized as a chord token (is_chord_token),
        we note its start column (an integer offset from line start).
      - We convert the lyric_line into a mutable list of characters so we can
        insert multiple characters at precise indices. Use lyric_chars[n:n] =
        list(bracketed) to insert multiple characters as individual list elements.
      - We maintain an 'offset' measured in characters: after inserting "[Em]"
        (4 characters), subsequent insert positions must be shifted right by 4.
      - If a chord's intended column is past the lyric length, we clamp to the
        end and append the bracketed chord. This is preferable to losing the chord.
      - We skip tokens that are non-chord (bar separators and parenthetical
        annotations) during position-driven merges; those tokens are handled if
        the whole line is chord-only via format_chord_only_line.
    """
    # 1) Find tokens and their start positions in the chord line
    chord_positions: List[Tuple[int, str]] = []
    for match in re.finditer(r"\S+", chord_line):
        token = match.group(0)
        if is_chord_token(token):
            # record (character index where the token starts, the token text)
            chord_positions.append((match.start(), token))

    # 2) Convert lyric_line into a list of single characters for precise insertion
    lyric_chars: List[str] = list(lyric_line)

    # 3) Insert bracketed chord strings into lyric_chars at approximate columns
    offset = 0  # number of characters already inserted (affects subsequent indices)
    for pos, chord in chord_positions:
        # Calculate the insertion index adjusted by the offset of prior insertions
        insert_at = pos + offset

        # Clamp insert position to [0, len(lyric_chars)]
        if insert_at < 0:
            insert_at = 0
        if insert_at > len(lyric_chars):
            insert_at = len(lyric_chars)

        # Build the bracketed chord to insert (markdown-it-chords expects [Chord])
        bracketed = f"[{chord}]"

        # Insert the bracketed chord as characters (so lyric_chars remains a char list)
        # Using slice assignment lyric_chars[insert_at:insert_at] = list(bracketed)
        # inserts each character so index arithmetic (offset) remains correct.
        lyric_chars[insert_at:insert_at] = list(bracketed)

        # Update offset by the number of characters added
        offset += len(bracketed)

    # 4) Recombine characters into a single string and return
    return "".join(lyric_chars)


# ------------------------------------------------------------------------------
# Format chord-only line into inline chord tokens while preserving pipes/annotations
# ------------------------------------------------------------------------------
def format_chord_only_line(line: str) -> str:
    """
    Convert a chord-only line to a line where chord tokens are wrapped in [ ] but
    bar separators and parenthetical annotations are preserved in place.

    Example:
      Input:  "| B   | A   | E   | E   | x2"
      Output: "| [B] | [A] | [E] | [E] | x2"

    We do this token-by-token so that pipe characters and annotations remain unchanged.
    """
    parts = []
    for token in re.finditer(r"\S+|\s+", line):
        tok = token.group(0)
        if tok.isspace():
            # Preserve original whitespace sequences exactly
            parts.append(tok)
            continue
        # Non-space token
        if is_chord_token(tok):
            parts.append(f"[{tok}]")
        elif is_parenthetical_annotation(tok) or is_bar_separator(tok):
            # Preserve annotations like (x2) and separators like '|' unchanged
            parts.append(tok)
        else:
            # As a fallback, preserve the token unchanged (shouldn't usually happen
            # for chord-only lines because those tokens were pre-validated).
            parts.append(tok)
    return "".join(parts)


# ------------------------------------------------------------------------------
# Top-level processing pass: walk the input lines and convert as needed
# ------------------------------------------------------------------------------
def process_lines(lines: List[str]) -> List[str]:
    """
    Walk through lines and produce converted lines where chord-lines are merged
    into the lyric-lines that follow them. This function carefully handles:
      - chord-only lines followed by lyric lines (merge into single inline line)
      - chord-only lines without following lyrics (convert to inline chord-only)
      - other lines (section headers, plain lyrics) are left untouched

    Implementation notes:
      - We intentionally use an index-based loop (while i < n) rather than for-each
        so we can consume the next line when we merge a chord line with its lyric.
      - We always preserve blank lines by appending an empty string to the output
        when lines contain no characters.
    """
    out: List[str] = []
    i = 0
    n = len(lines)
    while i < n:
        cur_line = lines[
            i
        ]  # note: lines expected without trailing newline to simplify joins

        # Quick classification: is this a chord-only line?
        if is_chord_only_line(cur_line):
            # Look ahead to see whether there's a lyric line to merge with.
            # Typical layout: chord line, then lyric line (possibly short).
            if i + 1 < n:
                next_line = lines[i + 1]
                # We require the next line to contain non-empty text to merge.
                # If it's blank or a bracketed section header like [Chorus], we choose
                # not to merge because those are structural labels.
                if next_line.strip() != "" and not re.match(
                    r"^\s*\[.*\]\s*$", next_line
                ):
                    # Merge chord_line (cur_line) with next_line lyrics
                    merged = merge_chords_and_lyrics(cur_line, next_line)
                    out.append(merged)
                    # Skip the next line since it's been consumed by the merge
                    i += 2
                    continue
            # If there was no suitable lyric to merge with, format the chord-only line
            formatted = format_chord_only_line(cur_line)
            out.append(formatted)
            i += 1
            continue

        # Not a chord-only line: preserve as-is (lyrics, headers, blank lines, etc.)
        out.append(cur_line)
        i += 1

    return out


# ------------------------------------------------------------------------------
# Input reading helpers: file mode, piped mode, interactive mode
# ------------------------------------------------------------------------------
def read_input_from_file(path: str) -> str:
    """
    Read entire file content and return it as a single string.

    We open with utf-8 and let IO errors bubble up to the caller so the main
    function can report helpful messages.
    """
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def read_input_interactively() -> str:
    """
    Read input from standard input in a robust way.

    Behavior:
      - If stdin is not a TTY (meaning content was piped in), we read all content
        with sys.stdin.read() and return immediately. This supports:
            cat file.txt | python script.py
      - If stdin is a TTY (the user invoked the script in a terminal), we print
        clear instructions and then call sys.stdin.read() as well; the user should
        paste (or type) their chart and then signal EOF (Ctrl-D on Unix/macOS,
        Ctrl-Z then Enter on Windows). We prefer EOF to blank-line termination
        because charts often contain blank lines.
    """
    # If data is being piped in, sys.stdin.isatty() will be False.
    if not sys.stdin.isatty():
        # Piped mode: read everything until EOF (pipe will provide EOF automatically)
        return sys.stdin.read()

    # Interactive TTY mode: instruct the user and then also read until EOF
    instructions = (
        "Paste your plain-text chord chart below. When you are finished, signal EOF:\n"
        "  - On Unix/macOS: press Ctrl-D on a new line\n"
        "  - On Windows (cmd.exe): press Ctrl-Z then Enter on a new line\n\n"
        "Paste now and then send EOF.\n"
    )
    print(instructions, end="", flush=True)

    # Read until EOFError is raised (user sends EOF)
    try:
        return sys.stdin.read()
    except KeyboardInterrupt:
        # If user hits Ctrl-C, provide a helpful message and exit cleanly.
        print("\nInput aborted (KeyboardInterrupt). Exiting.", file=sys.stderr)
        sys.exit(1)


# ------------------------------------------------------------------------------
# Safely choose an output filename and write results, avoid clobbering files
# ------------------------------------------------------------------------------
def unique_output_filename(base_name: str, ext: str = ".md") -> str:
    """
    Build a non-colliding filename in the current working directory using the
    provided base_name and extension. If "<base_name><ext>" exists, append a
    numeric suffix "-1", "-2", ... until an unused name is found. Return the
    chosen filename (not the full path).
    """
    candidate = f"{base_name}{ext}"
    if not os.path.exists(candidate):
        return candidate

    # If it exists, append a timestamp + counter to be extra-safe
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    counter = 1
    while True:
        candidate = f"{base_name}_{timestamp}_{counter}{ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def write_output_file(filename: str, lines: List[str]) -> str:
    """
    Write the list of output lines to the filename (in the current directory).
    Returns the absolute path to the written file.

    The function joins lines with a single '\n' and ensures the file ends with
    a newline (common convention for text files).
    """
    content = "\n".join(lines) + "\n"
    with open(filename, "w", encoding="utf-8") as fh:
        fh.write(content)
    return os.path.abspath(filename)


# ------------------------------------------------------------------------------
# Program entry point
# ------------------------------------------------------------------------------
def main(argv: List[str]) -> None:
    """
    Parse arguments, read input (file or interactive), process text, and write output.

    Expected argv patterns:
      - argv = [script]           -> interactive mode (paste and send EOF)
      - argv = [script, file.txt] -> file mode
      - argv = [script, -h|--help] -> print docstring/help

    We deliberately keep the CLI simple. If more options (transpose, output
    path, overwrite flag) are desired, we can add an argparse-based interface.
    """
    # Quick help flag
    if len(argv) > 1 and argv[1] in ("-h", "--help"):
        print(__doc__)
        print("Examples:")
        print("  python convert_chords_verbose.py song.txt")
        print("  cat song.txt | python convert_chords_verbose.py")
        print("  python convert_chords_verbose.py   # then paste and press Ctrl-D")
        return

    # Decide input mode
    if len(argv) > 1:
        # FILE MODE ----------------------------------------------------------
        input_path = argv[1]
        try:
            raw = read_input_from_file(input_path)
        except FileNotFoundError:
            print(f"Error: file not found: {input_path}", file=sys.stderr)
            sys.exit(2)
        except IOError as e:
            print(f"Error reading file {input_path}: {e}", file=sys.stderr)
            sys.exit(3)

        # Convert the file base name into an output name, adding '_converted'
        base = os.path.splitext(os.path.basename(input_path))[0] + "_converted"
        out_name = unique_output_filename(base, ".md")

    else:
        # INTERACTIVE / PIPED MODE -------------------------------------------
        raw = read_input_interactively()
        # Default output filename for pasted input
        out_name = unique_output_filename("converted_chords", ".md")

    # Split into lines preserving empty lines. splitlines() removes the newline
    # character; we handle rejoining at write time. This simplifies processing.
    lines = raw.splitlines()

    # Process the lines to convert chord-only lines into inline chords.
    converted = process_lines(lines)

    # Write the converted content to a file in the current working directory.
    output_path = write_output_file(out_name, converted)

    # Print a helpful completion message with the absolute path to the output file.
    print(f"\n✅ Conversion complete — markdown saved to:\n{output_path}")


# Standard boilerplate to allow importing this file as a module without running
# the script, while still enabling direct execution with `python script.py`.
if __name__ == "__main__":
    main(sys.argv)
