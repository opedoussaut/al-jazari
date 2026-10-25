"""Hardened XML loading for untrusted robot descriptions."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, remove_comments=True, huge_tree=False
)


def load_xml(path: Path) -> etree._Element:
    return etree.parse(str(path), _PARSER).getroot()


def floats(text: str | None) -> list[float] | None:
    if text is None:
        return None
    return [float(x) for x in text.split()]
