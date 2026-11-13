"""
Streaming Sentence Chunker for low-latency TTS synthesis.

Accumulates streamed LLM text tokens and emits natural, speakable phrases
as soon as a sentence boundary (or long-clause boundary) is confirmed,
while suppressing <think>...</think> blocks, code fences, and markdown noise.
"""

from __future__ import annotations

import re

# Common abbreviations (lowercase, without trailing dot) that shouldn't split speech
_ABBREVIATIONS = frozenset({
    "т.д", "т.п", "т.е", "т.к", "т.н", "т.о", "и т.д", "и т.п",
    "г", "гг", "в", "вв", "см", "стр", "рис", "табл", "гл", "п", "пп",
    "ул", "д", "кв", "корп", "обл", "р-н", "г.р",
    "др", "пр", "проф", "акад", "доц", "им", "ред", "сост",
    "руб", "коп", "тыс", "млн", "млрд", "шт", "экз", "мин", "сек", "ч",
    "e.g", "i.e", "etc", "vs", "mr", "mrs", "ms", "dr", "prof", "st", "fig", "no",
})

_SENTENCE_END_ABBREVS = frozenset({"т.д", "т.п", "др", "etc"})

_CLAUSE_SEPS = (", ", "; ", ": ", " — ", " – ", " - ")
_SENTENCE_END_CHARS = frozenset(".!?…")
_HAS_SPEAKABLE_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MD_BULLET_RE = re.compile(r"^\s*[-*•]\s+", re.MULTILINE)
_MD_NUM_LIST_RE = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
_MULTI_SPACE_RE = re.compile(r"[ \t]+")


def clean_for_speech(text: str) -> str:
    """Strip markdown symbols and formatting noise so TTS reads clean prose."""
    if not text:
        return ""
    out = _MD_LINK_RE.sub(r"\1", text)
    out = _MD_HEADING_RE.sub("", out)
    out = _MD_BULLET_RE.sub("", out)
    out = _MD_NUM_LIST_RE.sub("", out)
    out = out.replace("**", "").replace("__", "").replace("~~", "")
    out = out.replace("`", "")
    # Remove standalone markdown emphasis markers like *word* -> word
    out = re.sub(r"(?<!\w)\*+|\*+(?!\w)", "", out)
    out = _MULTI_SPACE_RE.sub(" ", out)
    return out.strip()


class SentenceChunker:
    """
    Incremental text buffer that splits streamed LLM output into TTS-ready chunks.

    Lookahead rules avoid premature splitting on decimals (``3.5``),
    ellipsis (``...``), or abbreviations (``т.д.``) while keeping first-chunk
    latency low via optional clause breaks on long sentences.
    """

    def __init__(self, min_clause_words: int = 8, max_chunk_words: int = 26) -> None:
        self._min_clause_words = max(3, min_clause_words)
        self._max_chunk_words = max(self._min_clause_words + 4, max_chunk_words)
        self._raw_buffer: str = ""
        self._in_think: bool = False
        self._in_code_block: bool = False
        self._emitted_any: bool = False

    def feed(self, token: str) -> list[str]:
        """Feed a token delta and return any newly completed speech chunks."""
        if not token:
            return []

        self._raw_buffer += token
        self._filter_hidden_blocks()
        return self._extract_ready_chunks(final=False)

    def flush(self) -> list[str]:
        """Flush any remaining buffered speech at the end of the stream."""
        self._filter_hidden_blocks(final=True)
        chunks = self._extract_ready_chunks(final=True)
        self._raw_buffer = ""
        return chunks

    def reset(self) -> None:
        """Reset all internal state (e.g., on barge-in cancellation)."""
        self._raw_buffer = ""
        self._in_think = False
        self._in_code_block = False
        self._emitted_any = False

    def _filter_hidden_blocks(self, final: bool = False) -> None:
        """Strip ``<think>...</think>`` and fenced code blocks incrementally."""
        # Handle <think> blocks
        while True:
            if self._in_think:
                end_idx = self._raw_buffer.find("</think>")
                if end_idx == -1:
                    # Keep only a small tail in case '</think>' is split across tokens
                    if not final and len(self._raw_buffer) > 8:
                        self._raw_buffer = self._raw_buffer[-8:]
                    elif final:
                        self._raw_buffer = ""
                    return
                self._raw_buffer = self._raw_buffer[end_idx + len("</think>"):]
                self._in_think = False
            else:
                start_idx = self._raw_buffer.find("<think>")
                if start_idx == -1:
                    break
                before = self._raw_buffer[:start_idx]
                after = self._raw_buffer[start_idx + len("<think>"):]
                self._in_think = True
                end_idx = after.find("</think>")
                if end_idx != -1:
                    self._raw_buffer = before + after[end_idx + len("</think>"):]
                    self._in_think = False
                else:
                    self._raw_buffer = before
                    return

        # Handle fenced code blocks ```...``` (don't read raw code aloud)
        while "```" in self._raw_buffer:
            first = self._raw_buffer.find("```")
            if self._in_code_block:
                self._raw_buffer = self._raw_buffer[first + 3:]
                self._in_code_block = False
            else:
                second = self._raw_buffer.find("```", first + 3)
                if second != -1:
                    self._raw_buffer = (
                        self._raw_buffer[:first] + " " + self._raw_buffer[second + 3:]
                    )
                else:
                    self._raw_buffer = self._raw_buffer[:first]
                    self._in_code_block = True
                    break

    def _holdback_tail_len(self) -> int:
        """Keep incomplete tag prefixes like '<th' or '``' until next token."""
        if not self._raw_buffer:
            return 0
        for prefix in ("<think>", "</think>"):
            for k in range(len(prefix) - 1, 0, -1):
                if self._raw_buffer.endswith(prefix[:k]):
                    return k
        if self._raw_buffer.endswith("``"):
            return 2
        if self._raw_buffer.endswith("`"):
            return 1
        return 0

    def _extract_ready_chunks(self, final: bool) -> list[str]:
        """Extract complete sentences/clauses from ``_raw_buffer``."""
        if self._in_think or self._in_code_block:
            return []

        holdback = 0 if final else self._holdback_tail_len()
        searchable = (
            self._raw_buffer[: len(self._raw_buffer) - holdback]
            if holdback
            else self._raw_buffer
        )
        tail = self._raw_buffer[len(searchable):]

        chunks: list[str] = []
        while searchable:
            split_at = self._find_split_index(searchable, final=final)
            if split_at is None:
                break
            part = searchable[:split_at]
            searchable = searchable[split_at:].lstrip(" \t")
            cleaned = clean_for_speech(part)
            if cleaned and _HAS_SPEAKABLE_RE.search(cleaned):
                chunks.append(cleaned)
                self._emitted_any = True

        if final and searchable.strip():
            cleaned = clean_for_speech(searchable)
            if cleaned and _HAS_SPEAKABLE_RE.search(cleaned):
                chunks.append(cleaned)
                self._emitted_any = True
            searchable = ""

        self._raw_buffer = searchable + tail
        return chunks

    def _find_split_index(self, text: str, final: bool) -> int | None:
        """
        Return index after the separator where ``text`` can be safely split,
        or ``None`` if we should keep buffering.
        """
        n = len(text)
        # 1. Look for newlines or sentence-ending punctuation
        for i, ch in enumerate(text):
            if ch == "\n":
                # Emit if we have speakable content before newline
                if _HAS_SPEAKABLE_RE.search(text[:i]):
                    return i + 1
                continue

            if ch in _SENTENCE_END_CHARS:
                # Lookahead: wait if punctuation run continues (. -> ... or ? -> ?!)
                if i + 1 < n and text[i + 1] in _SENTENCE_END_CHARS:
                    continue
                if i + 1 >= n and not final:
                    # Wait for next char so we don't split '3.5', '...', or 'т.д.' prematurely
                    return None

                if ch == ".":
                    # Decimal / IP / version number check (digit before and digit after)
                    if (
                        i > 0
                        and text[i - 1].isdigit()
                        and i + 1 < n
                        and text[i + 1].isdigit()
                    ):
                        continue
                    # Abbreviation check
                    abbrev = self._trailing_abbreviation(text[:i])
                    if abbrev:
                        if abbrev in _SENTENCE_END_ABBREVS:
                            # Wait for the next non-space char to see if a new uppercase sentence starts
                            rest = text[i + 1 :]
                            stripped_rest = rest.lstrip(" \t")
                            if not stripped_rest:
                                if not final:
                                    return None
                            elif not stripped_rest[0].isupper():
                                continue
                        elif not final or i + 1 < n:
                            continue

                # Require at least one speakable char before punctuation
                if _HAS_SPEAKABLE_RE.search(text[:i]):
                    # Include closing quotes/parens right after punctuation if present
                    end_idx = i + 1
                    while end_idx < n and text[end_idx] in ('"', "'", "»", ")"):
                        end_idx += 1
                    return end_idx

        # 2. Clause splitting for long sentences (fast first audio)
        words = text.split()
        # Use a slightly lower threshold on the very first chunk so TTS starts immediately
        clause_threshold = 5 if not self._emitted_any else self._min_clause_words
        if len(words) >= clause_threshold:
            best_clause_idx = None
            for sep in _CLAUSE_SEPS:
                idx = text.find(sep)
                while idx != -1:
                    prefix_words = len(text[:idx].split())
                    if prefix_words >= clause_threshold:
                        candidate = idx + len(sep)
                        if best_clause_idx is None or candidate < best_clause_idx:
                            best_clause_idx = candidate
                        break
                    idx = text.find(sep, idx + len(sep))
            if best_clause_idx is not None:
                return best_clause_idx

        # 3. Hard word-count fallback if a model outputs a wall of text without punctuation
        if len(words) >= self._max_chunk_words:
            # Find last whitespace before the limit
            space_idx = text.rfind(" ")
            if space_idx > 0:
                return space_idx + 1

        return None

    @staticmethod
    def _trailing_abbreviation(prefix: str) -> str | None:
        """Return lowercase abbreviation token if ``prefix`` ends with one, else None."""
        token_match = re.search(r"([A-Za-zА-Яа-яЁё0-9.\-]+)$", prefix)
        if not token_match:
            return None
        token = token_match.group(1).lower()
        if token in _ABBREVIATIONS:
            return token
        parts = token.split(".")
        if len(parts) >= 2 and all(1 <= len(p) <= 3 for p in parts):
            return token
        if len(token) == 1 and token.isalpha():
            return token
        return None
