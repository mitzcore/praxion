"""AST-level static checker for Muse-authored controller modules.

This is *defense in depth*, not the security boundary. The security boundary is the
Docker sandbox (``backend/controller/sandbox.py``). The checker exists so that obviously
invalid or hostile candidates are rejected early, with line-numbered, human-readable
violations that are fed back to Muse so it can revise its code.

Contract enforced (plan section 6.5 / 6.6)::

    import math                      # the only permitted import (or ``from math import ...``)
    def control(obs, state):         # exactly one, exactly two positional parameters
        ...
        return u, state

Top level may contain only: a module docstring, ``math`` imports, function definitions
(``control`` plus helpers), and simple constant assignments.
"""
from __future__ import annotations

import ast
import math

from pydantic import BaseModel

MAX_LINES = 400
MAX_RANGE_LITERAL = 100_000
MAX_SEQUENCE_REPEAT = 100_000

ALLOWED_IMPORTS = frozenset({"math"})

FORBIDDEN_NAMES = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "open",
        "input",
        "__import__",
        "globals",
        "locals",
        "vars",
        "getattr",
        "setattr",
        "delattr",
        "breakpoint",
        "exit",
        "quit",
        "memoryview",
        "bytearray",
        "super",
        "object",
    }
)
# ``type`` is forbidden only when called (``type(x)``, ``type(name, bases, ns)``).
FORBIDDEN_CALL_NAMES = frozenset({"type"})
# ``"{0.__class__}".format(x)`` reads arbitrary attributes through a format string, which
# side-steps the dunder-attribute rule. A controller has no need for string formatting.
FORBIDDEN_ATTRIBUTES = frozenset({"format", "format_map"})


class StaticCheckResult(BaseModel):
    """Outcome of :func:`static_check`. ``violations`` entries start with ``line N:``."""

    ok: bool
    violations: list[str]
    line_count: int
    function_count: int


def _const_value(node: ast.AST) -> float | None:
    """Best-effort evaluation of a purely literal numeric expression.

    Returns ``None`` when the expression is not a numeric literal expression. Large
    powers are evaluated in floating point so the checker itself can never be DoS'd.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(
        node.value, bool
    ):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _const_value(node.operand)
        if v is None:
            return None
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        left = _const_value(node.left)
        right = _const_value(node.right)
        if left is None or right is None:
            return None
        try:
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Pow):
                if abs(right) > 1000:
                    return math.inf if abs(left) > 1 else 0.0
                return float(left) ** float(right)
            if isinstance(node.op, ast.LShift):
                return left * (2.0 ** min(right, 1000.0))
            if isinstance(node.op, (ast.Div, ast.FloorDiv)) and right != 0:
                return left / right
        except (OverflowError, ValueError, ZeroDivisionError):
            return math.inf
    return None


def _is_simple_constant(node: ast.AST) -> bool:
    """True for literal constants, arithmetic over literals, and literal containers."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp):
        return _is_simple_constant(node.operand)
    if isinstance(node, ast.BinOp):
        return _is_simple_constant(node.left) and _is_simple_constant(node.right)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_simple_constant(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is not None and _is_simple_constant(k) for k in node.keys) and all(
            _is_simple_constant(v) for v in node.values
        )
    # ``math.pi`` and friends.
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "math":
        return not node.attr.startswith("_")
    return False


def _is_truthy_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and bool(node.value)


def _loop_has_break(loop: ast.While) -> bool:
    """True if a ``break`` that belongs to *this* loop exists in its body."""
    stack: list[ast.AST] = list(loop.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Break):
            return True
        # A break inside a nested loop or nested function does not exit this loop.
        if isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
            stack.extend(node.orelse)
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return False


def _is_range_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range"


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[str] = []

    def add(self, node: ast.AST, reason: str) -> None:
        line = getattr(node, "lineno", 0)
        self.violations.append(f"line {line}: {reason}")

    # --- imports -----------------------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name not in ALLOWED_IMPORTS:
                self.add(node, f"import of '{alias.name}' is forbidden; only 'import math' is permitted")
            elif alias.asname is not None:
                self.add(node, "'import math as ...' is forbidden; use plain 'import math'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level != 0 or node.module not in ALLOWED_IMPORTS:
            mod = ("." * node.level) + (node.module or "")
            self.add(node, f"'from {mod} import ...' is forbidden; only 'math' may be imported")
        else:
            for alias in node.names:
                if alias.name == "*":
                    self.add(node, "'from math import *' is forbidden; import names explicitly")
                elif alias.name.startswith("_"):
                    self.add(node, f"importing private name '{alias.name}' from math is forbidden")
        self.generic_visit(node)

    # --- names and attributes ----------------------------------------------------------
    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_NAMES:
            self.add(node, f"use of forbidden name '{node.id}'")
        elif node.id.startswith("__") and node.id.endswith("__"):
            self.add(node, f"use of dunder name '{node.id}' is forbidden")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__") and node.attr.endswith("__"):
            self.add(node, f"access to dunder attribute '.{node.attr}' is forbidden")
        elif node.attr in FORBIDDEN_NAMES:
            self.add(node, f"access to forbidden attribute '.{node.attr}'")
        elif node.attr in FORBIDDEN_ATTRIBUTES:
            self.add(node, f"string formatting via '.{node.attr}' is forbidden (it can read attributes)")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALL_NAMES:
            self.add(node, f"calling '{node.func.id}(...)' is forbidden")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Mult):
            for seq, count in ((node.left, node.right), (node.right, node.left)):
                is_seq = isinstance(seq, (ast.List, ast.Tuple)) or (
                    isinstance(seq, ast.Constant) and isinstance(seq.value, (str, bytes))
                )
                if is_seq:
                    n = _const_value(count)
                    if n is not None and n > MAX_SEQUENCE_REPEAT:
                        self.add(
                            node,
                            f"sequence repeated {n:.3g} times (> {MAX_SEQUENCE_REPEAT}); "
                            "this would exhaust memory",
                        )
                        break
        self.generic_visit(node)

    # --- statements ---------------------------------------------------------------------
    def visit_Global(self, node: ast.Global) -> None:
        self.add(node, "'global' statements are forbidden; keep memory in the state dict")
        self.generic_visit(node)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.add(node, "'nonlocal' statements are forbidden; keep memory in the state dict")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.add(node, "class definitions are forbidden")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.add(node, "'async def' is forbidden")
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.add(node, "'async for' is forbidden")
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self.add(node, "'async with' is forbidden")
        self.generic_visit(node)

    def visit_Await(self, node: ast.Await) -> None:
        self.add(node, "'await' is forbidden")
        self.generic_visit(node)

    def visit_Yield(self, node: ast.Yield) -> None:
        self.add(node, "'yield' is forbidden; control() must return (u, state)")
        self.generic_visit(node)

    def visit_YieldFrom(self, node: ast.YieldFrom) -> None:
        self.add(node, "'yield from' is forbidden; control() must return (u, state)")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.decorator_list:
            self.add(node.decorator_list[0], f"decorators on '{node.name}' are forbidden")
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        if _is_truthy_constant(node.test) and not _loop_has_break(node):
            self.add(node, "'while True' loop without a 'break' would never terminate; bound the loop")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._check_range(node.iter)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self._check_range(node.iter)
        self.generic_visit(node)

    def _check_range(self, it: ast.AST) -> None:
        if not _is_range_call(it):
            return
        assert isinstance(it, ast.Call)
        for arg in it.args:
            v = _const_value(arg)
            if v is not None and abs(v) > MAX_RANGE_LITERAL:
                self.add(
                    it,
                    f"loop over range with literal bound {v:.3g} (> {MAX_RANGE_LITERAL}); "
                    "a single control step must be cheap",
                )
                return


def _check_top_level(tree: ast.Module, visitor: _Visitor) -> int:
    """Check module-level structure. Returns the number of top-level function defs."""
    controls: list[ast.FunctionDef] = []
    function_count = 0
    for i, stmt in enumerate(tree.body):
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(stmt, ast.FunctionDef):
            function_count += 1
            if stmt.name == "control":
                controls.append(stmt)
            continue
        if (
            i == 0
            and isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            continue  # module docstring
        if isinstance(stmt, ast.Assign):
            if all(isinstance(t, ast.Name) for t in stmt.targets) and _is_simple_constant(stmt.value):
                continue
            visitor.add(stmt, "top-level assignments must bind a name to a simple constant")
            continue
        if isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.value is not None and _is_simple_constant(
                stmt.value
            ):
                continue
            visitor.add(stmt, "top-level assignments must bind a name to a simple constant")
            continue
        if isinstance(stmt, (ast.ClassDef, ast.AsyncFunctionDef)):
            continue  # reported by the visitor
        visitor.add(
            stmt,
            f"top-level '{type(stmt).__name__}' statement is forbidden; only imports, function "
            "definitions and constant assignments may appear at module level",
        )

    if not controls:
        visitor.add(tree, "module must define a top-level 'def control(obs, state)'")
    elif len(controls) > 1:
        for extra in controls[1:]:
            visitor.add(extra, "'control' is defined more than once; define it exactly once")
    for fn in controls[:1]:
        a = fn.args
        positional = list(a.posonlyargs) + list(a.args)
        if len(positional) != 2 or a.vararg or a.kwarg or a.kwonlyargs:
            names = ", ".join(p.arg for p in positional)
            visitor.add(
                fn,
                f"'control' must take exactly two positional parameters (obs, state); got ({names})"
                + (" plus *args/**kwargs/keyword-only parameters" if (a.vararg or a.kwarg or a.kwonlyargs)
                   else ""),
            )
        if a.defaults or a.kw_defaults:
            visitor.add(fn, "'control' parameters must not have default values")
    return function_count


def static_check(source: str) -> StaticCheckResult:
    """Statically validate a candidate controller module.

    Args:
        source: full module source as authored by the model.

    Returns:
        A :class:`StaticCheckResult`; ``ok`` is True only when there are no violations.
        Every violation starts with ``line N:`` (``line 0`` means "whole module").
    """
    lines = source.splitlines()
    line_count = len(lines)
    violations: list[str] = []
    if line_count > MAX_LINES:
        violations.append(f"line {MAX_LINES + 1}: module has {line_count} lines; maximum is {MAX_LINES}")
    if "\x00" in source:
        violations.append("line 0: source contains NUL bytes")
        return StaticCheckResult(ok=False, violations=violations, line_count=line_count, function_count=0)
    try:
        tree = ast.parse(source, filename="<candidate>", mode="exec")
    except SyntaxError as exc:
        violations.append(f"line {exc.lineno or 0}: syntax error: {exc.msg}")
        return StaticCheckResult(ok=False, violations=violations, line_count=line_count, function_count=0)

    visitor = _Visitor()
    function_count = _check_top_level(tree, visitor)
    visitor.visit(tree)
    violations.extend(visitor.violations)
    return StaticCheckResult(
        ok=not violations, violations=violations, line_count=line_count, function_count=function_count
    )
