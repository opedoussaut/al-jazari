"""A sandboxed Xacro expander for the subset used by generated robot descriptions.

Supported: <xacro:arg>, <xacro:property name value>, <xacro:include> (with $(find pkg)
mapped to a folder of the pinned checkout), <xacro:macro> with params and `:=` defaults,
macro calls, <xacro:if>/<xacro:unless>, and ${...} expressions made of names, literals,
arithmetic, comparisons and boolean operators.

Unlike ROS xacro, nothing is executed: expressions are evaluated by a small AST walker
(no Python eval), $(env)/$(eval)/$(optenv) are refused, and includes may not leave the
source tree. Anything outside the subset raises XacroError instead of being guessed.

Every emitted element is stamped with where it is written (SRC_ATTR) and the innermost
macro call that produced it (CALL_ATTR), so facts keep exact provenance.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from pathlib import Path

from lxml import etree

from .xml import CALL_ATTR, SRC_ATTR, inside, load_xml

XACRO = "http://www.ros.org/wiki/xacro"
_DOLLAR = re.compile(r"\$\((\w+)\s*([^)]*)\)")
_EXPR = re.compile(r"\$\{([^}]*)\}")
MAX_DEPTH = 40


class XacroError(ValueError):
    pass


def _literal(value: object) -> object:
    """xacro-style typing of property text: booleans and numbers, otherwise the string."""
    if not isinstance(value, str):
        return value
    v = value.strip()
    if v in ("true", "True"):
        return True
    if v in ("false", "False"):
        return False
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return value


_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Mod: operator.mod}
_CMPOPS = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
           ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}


def evaluate(expr: str, scope: dict[str, object]) -> object:
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise XacroError(f"cannot parse expression ${{{expr}}}: {e}") from e

    def ev(n: ast.AST) -> object:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float, str, bool)):
            return n.value
        if isinstance(n, ast.Name):
            if n.id in scope:
                return _literal(scope[n.id])
            if n.id in ("true", "True"):
                return True
            if n.id in ("false", "False"):
                return False
            if n.id == "pi":
                return math.pi
            raise XacroError(f"undefined name {n.id!r} in ${{{expr}}}")
        if isinstance(n, ast.BoolOp):
            vals = [ev(v) for v in n.values]
            if isinstance(n.op, ast.And):
                return all(vals) and vals[-1]
            return next((v for v in vals if v), vals[-1])
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            if isinstance(n.op, ast.Not):
                return not v
            if isinstance(n.op, ast.USub):
                return -v
            if isinstance(n.op, ast.UAdd):
                return +v
        if isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
            return _BINOPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in _CMPOPS:
            return _CMPOPS[type(n.ops[0])](ev(n.left), ev(n.comparators[0]))
        if isinstance(n, ast.IfExp):
            return ev(n.body) if ev(n.test) else ev(n.orelse)
        raise XacroError(f"unsupported construct {type(n).__name__} in ${{{expr}}}")

    return ev(tree)


def _truth(text: str) -> bool:
    v = text.strip()
    if v in ("true", "True", "1"):
        return True
    if v in ("false", "False", "0", ""):
        return False
    raise XacroError(f"condition value {text!r} is not a boolean")


class Expander:
    def __init__(self, sandbox: Path, packages: dict[str, Path], args: dict[str, str] | None = None):
        self.sandbox = sandbox.resolve()
        self.packages = {k: inside(v, self.sandbox) for k, v in packages.items()}
        self.args: dict[str, str] = dict(args or {})
        self.macros: dict[str, tuple[list[tuple[str, str | None]], etree._Element, Path]] = {}
        self.globals: dict[str, object] = {}
        self.files: list[Path] = []

    # ------------------------------------------------------------- text
    def sub(self, text: str, scope: dict[str, object]) -> str:
        def dollar(m: re.Match) -> str:
            kind, arg = m.group(1), m.group(2).strip()
            if kind == "arg":
                if arg not in self.args:
                    raise XacroError(f"$(arg {arg}) used but never declared")
                return self.args[arg]
            if kind == "find":
                if arg not in self.packages:
                    raise XacroError(f"$(find {arg}): package not mapped in the manifest")
                return str(self.packages[arg])
            raise XacroError(f"$({kind} ...) is not supported (no environment or eval access)")

        text = _DOLLAR.sub(dollar, text)
        whole = _EXPR.fullmatch(text.strip())
        if whole:
            return self._fmt(evaluate(whole.group(1), scope))
        return _EXPR.sub(lambda m: self._fmt(evaluate(m.group(1), scope)), text)

    @staticmethod
    def _fmt(v: object) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)

    # ------------------------------------------------------------- tree
    def expand(self, path: Path) -> etree._Element:
        path = inside(path, self.sandbox)
        self.files.append(path)
        src = load_xml(path)
        out = etree.Element(src.tag, {k: self.sub(v, self.globals) for k, v in src.attrib.items()})
        out.set(SRC_ATTR, f"{path}|{src.sourceline}")
        self._children(src, out, self.globals, path, None, 0)
        return out

    def _children(self, src: etree._Element, dst: etree._Element, scope: dict, file: Path,
                  call: str | None, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise XacroError("macro recursion too deep")
        for el in src:
            if not isinstance(el.tag, str):
                continue
            if el.tag.startswith(f"{{{XACRO}}}"):
                self._directive(el, dst, scope, file, call, depth)
                continue
            new = etree.SubElement(dst, el.tag, {k: self.sub(v, scope) for k, v in el.attrib.items()
                                                 if not k.startswith("{")})
            new.set(SRC_ATTR, f"{file}|{el.sourceline}")
            if call:
                new.set(CALL_ATTR, call)
            if el.text and el.text.strip():
                new.text = self.sub(el.text, scope)
            self._children(el, new, scope, file, call, depth)

    def _directive(self, el: etree._Element, dst: etree._Element, scope: dict, file: Path,
                   call: str | None, depth: int) -> None:
        name = etree.QName(el).localname
        if name == "arg":
            self.args.setdefault(el.get("name"), self.sub(el.get("default", ""), scope))
        elif name == "property":
            if el.get("value") is None:
                raise XacroError(f"block property {el.get('name')!r} is not supported")
            scope[el.get("name")] = self.sub(el.get("value"), scope)
        elif name == "include":
            target = Path(self.sub(el.get("filename"), scope))
            if not target.is_absolute():
                target = file.parent / target
            target = inside(target, self.sandbox)
            self.files.append(target)
            self._children(load_xml(target), dst, scope, target, call, depth + 1)
        elif name == "macro":
            params: list[tuple[str, str | None]] = []
            for p in (el.get("params") or "").split():
                if p.startswith("*") or ":=^" in p or p.endswith(":^"):
                    raise XacroError(f"macro parameter form {p!r} is not supported")
                pname, _, default = p.partition(":=")
                params.append((pname, default if _ else None))
            self.macros[el.get("name")] = (params, el, file)
        elif name in ("if", "unless"):
            cond = _truth(self.sub(el.get("value", ""), scope))
            if cond == (name == "if"):
                self._children(el, dst, scope, file, call, depth + 1)
        elif name in self.macros:
            params, body, mfile = self.macros[name]
            local = dict(self.globals)
            for pname, default in params:
                if el.get(pname) is not None:
                    local[pname] = self.sub(el.get(pname), scope)
                elif default is not None:
                    local[pname] = self.sub(default, local)
                else:
                    raise XacroError(f"macro {name!r} called without parameter {pname!r}")
            self._children(body, dst, local, mfile, f"{file}|{el.sourceline}", depth + 1)
        else:
            raise XacroError(f"<xacro:{name}> is not supported or the macro is undefined")


def expand_xacro(path: Path, sandbox: Path, packages: dict[str, Path],
                 args: dict[str, str] | None = None) -> tuple[etree._Element, list[Path]]:
    exp = Expander(sandbox, packages, args)
    root = exp.expand(path)
    return root, exp.files
