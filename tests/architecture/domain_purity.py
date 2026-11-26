"""AST check: domain code does no I/O.

A domain module may not import I/O modules nor call open, input or print.
"""

import ast

FORBIDDEN_MODULES = frozenset(
    {
        "aiohttp",
        "astropy.io",
        "astroquery",
        "glob",
        "http",
        "httpx",
        "importlib",
        "io",
        "lightkurve",
        "logging",
        "os",
        "pathlib",
        "requests",
        "shutil",
        "socket",
        "sqlite3",
        "subprocess",
        "sys",
        "tempfile",
        "urllib",
    }
)
FORBIDDEN_CALLS = frozenset({"open", "input", "print", "__import__"})


def _is_forbidden(module: str) -> bool:
    return any(module == m or module.startswith(m + ".") for m in FORBIDDEN_MODULES)


def find_violations(source: str, filename: str = "<string>") -> list[str]:
    violations = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        where = f"{filename}:{getattr(node, 'lineno', 0)}"
        if isinstance(node, ast.Import):
            violations += [f"{where} imports {a.name}" for a in node.names if _is_forbidden(a.name)]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if _is_forbidden(node.module):
                violations.append(f"{where} imports {node.module}")
            else:
                violations += [
                    f"{where} imports {node.module}.{a.name}"
                    for a in node.names
                    if _is_forbidden(f"{node.module}.{a.name}")
                ]
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in FORBIDDEN_CALLS
        ):
            violations.append(f"{where} calls {node.func.id}()")
    return violations
