from __future__ import annotations

import unicodedata

#: Fuzzy (subsequence) matching is opt-in: a scatter hit cannot be located
#: or highlighted on a page, so surfaces that must show *where* the query
#: matched (help search, Find Action, settings targets) never enable it.
#: Label lists may enable it explicitly when their UI advertises fuzzy input.
DEFAULT_FUZZY = False


def normalize_for_search(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text)).casefold()
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_marks.split())


def normalized_offsets(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Normalize like ``normalize_for_search``, keeping raw offset spans.

    Returns ``(norm_text, spans)`` where ``spans[i]`` is the ``(start, end)``
    raw-text slice that produced normalized char ``i``. Lets consumers map a
    normalized match back onto the original text (e.g. highlight the exact
    occurrence a scorer accepted) — same normalization, single source of
    truth for "what matched".
    """
    norm_chars: list[str] = []
    spans: list[tuple[int, int]] = []
    raw = str(text)
    n = len(raw)
    in_ws = False
    ws_start = 0
    emitted_any = False
    i = 0
    while i < n:
        ch = raw[i]
        if ch.isspace():
            if not in_ws:
                in_ws = True
                ws_start = i
            i += 1
            continue
        if in_ws:
            in_ws = False
            if emitted_any:
                # Collapse the run only between emitted chars — like
                # ``normalize_for_search``'s split/join, which drops leading
                # and trailing whitespace.
                norm_chars.append(" ")
                spans.append((ws_start, i))
        decomposed = unicodedata.normalize("NFKD", ch).casefold()
        for piece in decomposed:
            if unicodedata.combining(piece):
                continue
            norm_chars.append(piece)
            spans.append((i, i + 1))
        emitted_any = True
        i += 1
    # Trailing whitespace is dropped, like ``normalize_for_search``'s
    # split/join.
    return "".join(norm_chars), spans


def find_normalized(
    norm_query: str,
    text: str,
    *,
    start: int = 0,
) -> tuple[int, int, int] | None:
    """First normalized occurrence of ``norm_query`` in raw ``text``.

    Returns ``(raw_start, raw_end, norm_pos)`` or ``None``. Uses the same
    normalization as the scorers, so a hit here is exactly a hit the
    non-fuzzy ``match_score_normalized`` would rank.
    """
    if not norm_query:
        return None
    norm_text, spans = normalized_offsets(text)
    pos = norm_text.find(norm_query, start)
    if pos < 0:
        return None
    start_span = spans[pos]
    end_span = spans[pos + len(norm_query) - 1]
    return start_span[0], end_span[1], pos


def match_score(query: str, text: str, *, fuzzy: bool = DEFAULT_FUZZY) -> int | None:
    norm_query = normalize_for_search(query)
    norm_text = normalize_for_search(text)
    return match_score_normalized(norm_query, norm_text, fuzzy=fuzzy)


def match_score_normalized(
    norm_query: str,
    norm_text: str,
    *,
    fuzzy: bool = DEFAULT_FUZZY,
) -> int | None:
    """Rank a normalized query against a normalized haystack.

    Exact, word-prefix, and substring hits score below 100. With
    ``fuzzy=True`` a subsequence scatter fallback (>= 100) is also
    accepted; it is off by default because scatter hits are not locatable
    on a page and silently match almost any short query against long text.
    """
    if not norm_query:
        return 0
    if not norm_text:
        return None
    if norm_text.startswith(norm_query):
        return 0

    for word_index, word in enumerate(norm_text.split()):
        if word.startswith(norm_query):
            return 10 + word_index

    substring_pos = norm_text.find(norm_query)
    if substring_pos >= 0:
        return 40 + substring_pos

    if not fuzzy:
        return None

    query_pos = 0
    first_match = -1
    last_match = -1
    for text_index, char in enumerate(norm_text):
        if query_pos < len(norm_query) and char == norm_query[query_pos]:
            if first_match < 0:
                first_match = text_index
            last_match = text_index
            query_pos += 1
            if query_pos == len(norm_query):
                gap_penalty = max(0, last_match - first_match - len(norm_query) + 1)
                return 100 + first_match + gap_penalty
    return None


def visible_indices(
    items: list[object],
    *,
    search_enabled: bool,
    search_text: str,
    fuzzy: bool = DEFAULT_FUZZY,
) -> list[int]:
    if not search_enabled or not search_text:
        return list(range(len(items)))

    matches: list[tuple[int, int]] = []
    for idx, item in enumerate(items):
        score = match_score(search_text, getattr(item, "text", ""), fuzzy=fuzzy)
        if score is not None:
            matches.append((score, idx))
    matches.sort(key=lambda item: (item[0], item[1]))
    return [idx for _score, idx in matches]


def visible_indices_normalized(
    normalized_items: list[str],
    *,
    search_enabled: bool,
    search_text: str,
    fuzzy: bool = DEFAULT_FUZZY,
) -> list[int]:
    if not search_enabled or not search_text:
        return list(range(len(normalized_items)))

    norm_query = normalize_for_search(search_text)
    matches: list[tuple[int, int]] = []
    for idx, norm_text in enumerate(normalized_items):
        score = match_score_normalized(norm_query, norm_text, fuzzy=fuzzy)
        if score is not None:
            matches.append((score, idx))
    matches.sort(key=lambda item: (item[0], item[1]))
    return [idx for _score, idx in matches]
