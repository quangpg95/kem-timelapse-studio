import ast
from pathlib import Path


def test_core_never_imports_pyside6() -> None:
    violations: list[str] = []
    for path in Path("src/kem_timelapse").rglob("*.py"):
        if "ui" in path.relative_to("src/kem_timelapse").parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(name == "PySide6" or name.startswith("PySide6.") for name in names):
                violations.append(str(path))
    assert violations == []
