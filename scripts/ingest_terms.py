#!/usr/bin/env python3
"""Ingest and normalize the Razorpay Payments Terms page.

The script fetches the live Razorpay terms page, extracts the terms body,
normalizes it into ordered text blocks, and emits a JSON artifact that
preserves the document hierarchy needed for compliance Q&A generation.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_SOURCE_URL = "https://razorpay.com/terms/"
DEFAULT_OUTPUT_PATH = Path("data/razorpay_terms_normalized.json")
PARSER_VERSION = "2026-06-21.1"

TERMS_START_RE = re.compile(r"^PAYMENTS:\s+TERMS\s+AND\s+CONDITIONS$", re.IGNORECASE)
EFFECTIVE_DATE_RE = re.compile(
    r"\bEffective\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})\b", re.IGNORECASE
)
PART_RE = re.compile(r"^PART\s+([AB])\s*:\s*(.+)$", re.IGNORECASE)
PART_SUBSECTION_RE = re.compile(
    r"^Part\s+([IVXLCDM]+[A-Z]?)\s*[-:]\s*(.+)$", re.IGNORECASE
)
FOOTER_START_RE = re.compile(
    r"^A comprehensive payments suite in India designed to help businesses",
    re.IGNORECASE,
)
NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\.\s+(.+)$")
NUMBERED_ITEM_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$")
LETTERED_ITEM_RE = re.compile(r"^([a-z])\.\s+(.+)$")
ROMAN_ITEM_RE = re.compile(r"^\(([ivxlcdm]+)\)\s+(.+)$", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass
class TextBlock:
    """A normalized text block extracted from the HTML document."""

    sequence: int
    text: str
    tag: str
    heading_level: int | None = None


@dataclass
class HierarchyState:
    """Current position in the terms hierarchy while walking blocks."""

    part: str | None = None
    section: str | None = None
    subsection: str | None = None
    clause: str | None = None
    subclause: str | None = None
    item: str | None = None
    part_title: str | None = None
    section_title: str | None = None
    subsection_title: str | None = None
    clause_title: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "part": self.part,
            "part_title": self.part_title,
            "section": self.section,
            "section_title": self.section_title,
            "subsection": self.subsection,
            "subsection_title": self.subsection_title,
            "clause": self.clause,
            "clause_title": self.clause_title,
            "subclause": self.subclause,
            "item": self.item,
        }

    def path_parts(self) -> list[str]:
        parts: list[str] = []
        if self.part:
            parts.append(join_label(self.part, self.part_title))
        if self.section:
            parts.append(join_label(self.section, self.section_title))
        if self.subsection:
            parts.append(join_label(self.subsection, self.subsection_title))
        if self.clause:
            parts.append(join_label(self.clause, self.clause_title))
        if self.subclause:
            parts.append(self.subclause)
        if self.item:
            parts.append(self.item)
        return parts


class BlockHTMLParser(HTMLParser):
    """Extract user-visible text from common block-level HTML tags."""

    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "caption",
        "dd",
        "div",
        "dt",
        "figcaption",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "p",
        "section",
        "td",
        "th",
        "tr",
    }
    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[TextBlock] = []
        self._tag_stack: list[str] = []
        self._skip_depth = 0
        self._buffer: list[str] = []
        self._current_tag: str | None = None
        self._current_heading_level: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in self.BLOCK_TAGS:
            self._flush()
            self._tag_stack.append(tag)
            self._current_tag = tag
            self._current_heading_level = int(tag[1]) if re.fullmatch(r"h[1-6]", tag) else None

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in self.BLOCK_TAGS:
            self._flush()
            if self._tag_stack:
                self._tag_stack.pop()
            self._current_tag = self._tag_stack[-1] if self._tag_stack else None
            self._current_heading_level = (
                int(self._current_tag[1])
                if self._current_tag and re.fullmatch(r"h[1-6]", self._current_tag)
                else None
            )

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if data and data.strip():
            self._buffer.append(data)

    def _flush(self) -> None:
        text = normalize_text(" ".join(self._buffer))
        self._buffer = []
        if not text:
            return
        if is_noise_block(text):
            return
        self.blocks.append(
            TextBlock(
                sequence=len(self.blocks) + 1,
                text=text,
                tag=self._current_tag or "text",
                heading_level=self._current_heading_level,
            )
        )


def normalize_text(value: str) -> str:
    """Normalize HTML text while preserving legal wording."""

    value = html.unescape(value).replace("\xa0", " ")
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("“", '"').replace("”", '"').replace("’", "'")
    value = WHITESPACE_RE.sub(" ", value)
    return value.strip()


def is_noise_block(text: str) -> bool:
    """Remove obvious page chrome without filtering legal terms."""

    if text in {"•", "NEW"}:
        return True
    if re.fullmatch(r"Image", text, re.IGNORECASE):
        return True
    return False


def fetch_html(source_url: str, timeout: int) -> str:
    request = Request(
        source_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; razorpay-compliance-assistant/0.1; "
                "+https://github.com/meyharsharma/razorpay-compliance-assistant)"
            )
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"failed to fetch {source_url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"failed to fetch {source_url}: {exc.reason}") from exc


def extract_blocks(raw_html: str) -> list[TextBlock]:
    parser = BlockHTMLParser()
    parser.feed(raw_html)
    parser.close()
    return resequence(dedupe_adjacent_blocks(parser.blocks))


def dedupe_adjacent_blocks(blocks: Iterable[TextBlock]) -> list[TextBlock]:
    """Remove adjacent duplicate chrome caused by responsive nav markup."""

    deduped: list[TextBlock] = []
    previous_text: str | None = None
    for block in blocks:
        if block.text == previous_text:
            continue
        deduped.append(block)
        previous_text = block.text
    return deduped


def resequence(blocks: Iterable[TextBlock]) -> list[TextBlock]:
    return [
        TextBlock(
            sequence=index,
            text=block.text,
            tag=block.tag,
            heading_level=block.heading_level,
        )
        for index, block in enumerate(blocks, start=1)
    ]


def slice_terms_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    start_index = next(
        (index for index, block in enumerate(blocks) if TERMS_START_RE.match(block.text)),
        None,
    )
    if start_index is None:
        raise RuntimeError("could not locate the 'PAYMENTS: TERMS AND CONDITIONS' start heading")

    end_index = next(
        (
            index
            for index, block in enumerate(blocks[start_index + 1 :], start=start_index + 1)
            if FOOTER_START_RE.match(block.text)
        ),
        len(blocks),
    )
    sliced = blocks[start_index:end_index]
    return resequence(sliced)


def extract_effective_date(blocks: list[TextBlock]) -> tuple[str | None, str | None]:
    for block in blocks:
        match = EFFECTIVE_DATE_RE.search(block.text)
        if not match:
            continue
        month_name, day_text, year_text = match.groups()
        month = MONTHS.get(month_name.lower())
        if not month:
            return match.group(0), None
        date_value = datetime(int(year_text), month, int(day_text)).date()
        return match.group(0), date_value.isoformat()
    return None, None


def classify_block(block: TextBlock) -> str:
    text = block.text
    if PART_RE.match(text):
        return "part_heading"
    if PART_SUBSECTION_RE.match(text):
        return "section_heading"
    if block.heading_level is not None:
        if NUMBERED_HEADING_RE.match(text):
            return "numbered_heading"
        return "heading"
    if NUMBERED_ITEM_RE.match(text):
        return "numbered_clause"
    if LETTERED_ITEM_RE.match(text):
        return "lettered_item"
    if ROMAN_ITEM_RE.match(text):
        return "roman_item"
    return "paragraph"


def normalize_heading_label(text: str) -> str:
    return text.strip().rstrip(":").strip()


def join_label(label: str, title: str | None) -> str:
    return f"{label}: {title}" if title else label


def update_hierarchy(state: HierarchyState, block: TextBlock, block_type: str) -> None:
    text = block.text

    part_match = PART_RE.match(text)
    if part_match:
        state.part = f"Part {part_match.group(1).upper()}"
        state.part_title = normalize_heading_label(part_match.group(2))
        state.section = None
        state.section_title = None
        state.subsection = None
        state.subsection_title = None
        state.clause = None
        state.clause_title = None
        state.subclause = None
        state.item = None
        return

    section_match = PART_SUBSECTION_RE.match(text)
    if section_match:
        state.section = f"Part {section_match.group(1).upper()}"
        state.section_title = normalize_heading_label(section_match.group(2))
        state.subsection = None
        state.subsection_title = None
        state.clause = None
        state.clause_title = None
        state.subclause = None
        state.item = None
        return

    numbered_heading_match = NUMBERED_HEADING_RE.match(text)
    if block_type == "numbered_heading" and numbered_heading_match:
        number, title = numbered_heading_match.groups()
        state.clause = number
        state.clause_title = normalize_heading_label(title)
        state.subclause = None
        state.item = None
        return

    if block_type == "heading":
        if block.heading_level and block.heading_level <= 4:
            state.subsection = normalize_heading_label(text)
            state.subsection_title = None
            state.clause = None
            state.clause_title = None
            state.subclause = None
            state.item = None
        return

    numbered_item_match = NUMBERED_ITEM_RE.match(text)
    if numbered_item_match:
        marker = numbered_item_match.group(1)
        if "." in marker:
            state.subclause = marker
            state.item = None
        else:
            state.item = marker
        return

    lettered_item_match = LETTERED_ITEM_RE.match(text)
    if lettered_item_match:
        state.item = lettered_item_match.group(1)
        return

    roman_item_match = ROMAN_ITEM_RE.match(text)
    if roman_item_match:
        state.item = f"({roman_item_match.group(1).lower()})"


def extract_marker(text: str, block_type: str) -> str | None:
    patterns = {
        "numbered_heading": NUMBERED_HEADING_RE,
        "numbered_clause": NUMBERED_ITEM_RE,
        "lettered_item": LETTERED_ITEM_RE,
        "roman_item": ROMAN_ITEM_RE,
    }
    pattern = patterns.get(block_type)
    if not pattern:
        return None
    match = pattern.match(text)
    return match.group(1) if match else None


def strip_marker(text: str, block_type: str) -> str:
    patterns = {
        "numbered_heading": NUMBERED_HEADING_RE,
        "numbered_clause": NUMBERED_ITEM_RE,
        "lettered_item": LETTERED_ITEM_RE,
        "roman_item": ROMAN_ITEM_RE,
    }
    pattern = patterns.get(block_type)
    if not pattern:
        return text
    match = pattern.match(text)
    return match.group(2).strip() if match else text


def normalize_terms(
    *,
    source_url: str,
    raw_html: str,
    fetched_at_utc: str,
) -> dict[str, object]:
    all_blocks = extract_blocks(raw_html)
    terms_blocks = slice_terms_blocks(all_blocks)
    effective_date_text, effective_date_iso = extract_effective_date(all_blocks)

    state = HierarchyState()
    normalized_blocks: list[dict[str, object]] = []
    clauses: list[dict[str, object]] = []

    for block in terms_blocks:
        block_type = classify_block(block)
        update_hierarchy(state, block, block_type)
        path_parts = state.path_parts()
        marker = extract_marker(block.text, block_type)
        text_without_marker = strip_marker(block.text, block_type)

        normalized_block = {
            "sequence": block.sequence,
            "type": block_type,
            "tag": block.tag,
            "heading_level": block.heading_level,
            "marker": marker,
            "text": block.text,
            "text_without_marker": text_without_marker,
            "hierarchy": state.as_dict(),
            "clause_path": path_parts,
            "clause_path_text": " > ".join(path_parts),
        }
        normalized_blocks.append(normalized_block)

        if block_type in {
            "numbered_clause",
            "lettered_item",
            "roman_item",
            "paragraph",
        }:
            clauses.append(
                {
                    "id": f"clause-{len(clauses) + 1:04d}",
                    "sequence": block.sequence,
                    "type": block_type,
                    "marker": marker,
                    "text": block.text,
                    "text_without_marker": text_without_marker,
                    "hierarchy": state.as_dict(),
                    "clause_path": path_parts,
                    "clause_path_text": " > ".join(path_parts),
                }
            )

    return {
        "metadata": {
            "source_url": source_url,
            "source_name": "Razorpay Payments Terms and Conditions",
            "fetched_at_utc": fetched_at_utc,
            "effective_date_text": effective_date_text,
            "effective_date_iso": effective_date_iso,
            "parser_version": PARSER_VERSION,
            "raw_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
            "block_count": len(normalized_blocks),
            "clause_count": len(clauses),
        },
        "blocks": normalized_blocks,
        "clauses": clauses,
    }


def write_json(payload: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape and normalize the Razorpay Payments Terms page."
    )
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL, help="Razorpay terms URL.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Path to write normalized JSON.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--input-html",
        default=None,
        help="Optional local HTML file for deterministic/offline parsing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    fetched_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    if args.input_html:
        raw_html = Path(args.input_html).read_text(encoding="utf-8")
    else:
        raw_html = fetch_html(args.source_url, args.timeout)

    payload = normalize_terms(
        source_url=args.source_url,
        raw_html=raw_html,
        fetched_at_utc=fetched_at_utc,
    )
    write_json(payload, Path(args.output))

    metadata = payload["metadata"]
    print(
        "Wrote {output} ({blocks} blocks, {clauses} clauses, effective date: {effective_date})".format(
            output=args.output,
            blocks=metadata["block_count"],
            clauses=metadata["clause_count"],
            effective_date=metadata["effective_date_iso"] or "unknown",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
