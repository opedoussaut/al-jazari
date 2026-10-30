"""Hardened XML loading for untrusted robot descriptions."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, remove_comments=True, huge_tree=False
)

# Attributes added by JAZARI to elements copied from another file (MJCF <include>, Xacro),
# holding "<absolute path>|<line>" of where the element is written.
SRC_ATTR = "data-jz-src"
CALL_ATTR = "data-jz-call"  # innermost Xacro macro call that emitted the element


class UnsafePath(ValueError):
    pass


def load_xml(path: Path) -> etree._Element:
    return etree.parse(str(path), _PARSER).getroot()


def floats(text: str | None) -> list[float] | None:
    if text is None:
        return None
    return [float(x) for x in text.split()]


def inside(path: Path, root: Path) -> Path:
    """Resolve `path` and refuse anything outside the sandbox `root` (no ../ escapes)."""
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise UnsafePath(f"{path} is outside the allowed source tree {root}")
    return resolved


def location(el: etree._Element, attr: str = SRC_ATTR) -> tuple[Path | None, int]:
    """(file, line) where an element is written; file None means the parsed file itself."""
    src = el.get(attr)
    if src:
        file, line = src.rsplit("|", 1)
        return Path(file), int(line)
    return None, el.sourceline or 0


def stamp(el: etree._Element, file: Path, attr: str = SRC_ATTR) -> None:
    el.set(attr, f"{file}|{el.sourceline}")
