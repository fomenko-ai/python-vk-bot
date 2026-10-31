"""Compile package sources without imports, dependencies, or bytecode writes.

Run under the interpreter being assessed. Syntax success does not establish runtime
support; follow it with dependency installation and the regression suite when applicable.
"""

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    failures = 0
    sources = sorted((root / "python_vk_bot").rglob("*.py"))
    print(f"Python {sys.version.split()[0]}: checking {len(sources)} package sources")
    for source in sources:
        try:
            compile(source.read_bytes(), str(source), "exec", dont_inherit=True)
        except SyntaxError as error:
            failures += 1
            print(f"  {source.relative_to(root)}:{error.lineno}: {error.msg}")
    if failures:
        print(f"INCOMPATIBLE: {failures} source files cannot be compiled")
        return 1
    print("SYNTAX PASS: runtime support requires separate dependency and regression checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
