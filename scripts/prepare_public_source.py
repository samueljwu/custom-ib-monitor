"""Stage a narrow, auditable source candidate without personal local files.

The output is an untracked review artifact, not a release or a Git repository.
Only an explicitly listed set of source paths is copied.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]
BASE_FILES = (
    Path("main.py"),
    Path("requirements.txt"),
    Path("requirements-dev.txt"),
    Path("README.md"),
    Path("HISTORICAL_REPORTS.md"),
    Path("enter_flex_token.cmd"),
    Path("tests/test_paths.py"),
    Path("tests/test_flex_transport.py"),
    Path("tests/test_cash_flex.py"),
    Path("scripts/prepare_public_source.py"),
    Path("scripts/enter_flex_token.py"),
    Path("scripts/import_history.py"),
    Path("scripts/sync_trades.py"),
    Path("scripts/sync_analytics.py"),
    Path("scripts/sync_cash.py"),
)
BLOCKED_CONTENT = {
    "account identifier": re.compile(r"\b(?:U\d{6,}|DU\d{5,})\b"),
    "personal Windows path": re.compile(r"C:[/\\]+Users[/\\]+[^/\\\s]+", re.I),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "credential literal": re.compile(
        r"(?i)(?:token|secret|password|api[_-]?key)\s*[:=]\s*['\"][^'\"\r\n]{16,}['\"]"
    ),
}
PRIVATE_FILE_SUFFIXES = {".xlsx", ".xls", ".sqlite3", ".db", ".xml", ".csv", ".pem", ".key", ".p12", ".pfx"}
PUBLIC_IGNORE = """__pycache__/\n.pytest_cache/\n*.pyc\n*.sqlite3*\n*.db*\n*.xlsx\n*.xls\n*.xml\n*.csv\n*.pem\n*.key\n*.p12\n*.pfx\n*.zip\ndata/\nbackups/\nreports/\nlogs/\nsecrets/\nlocal_config.json\n.env*\nbuild/\ndist/\n.venv/\nvenv/\n"""


def selected_files() -> list[Path]:
    return [*BASE_FILES, *sorted((ROOT / "app").glob("*.py"))]


def audit(directory: Path) -> list[str]:
    findings = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        if path.suffix.lower() in PRIVATE_FILE_SUFFIXES:
            findings.append(f"{relative}: private data file type")
            continue
        if path.name == ".gitignore":
            continue
        try:
            contents = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            findings.append(f"{relative}: unexpected unreadable file")
            continue
        for label, pattern in BLOCKED_CONTENT.items():
            if pattern.search(contents):
                findings.append(f"{relative}: {label}")
    return findings


def stage(output: Path) -> list[str]:
    output = output.resolve()
    allowed = (ROOT / "build").resolve()
    if allowed not in output.parents or output.exists():
        raise ValueError("Choose a new output directory inside this project's build directory")
    files = selected_files()
    for source in files:
        source = source if source.is_absolute() else ROOT / source
        if source.is_symlink() or not source.is_file() or ROOT.resolve() not in source.resolve().parents:
            raise FileNotFoundError(source)
    output.mkdir(parents=True)
    for source in files:
        source = source if source.is_absolute() else ROOT / source
        target = output / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (output / ".gitignore").write_text(PUBLIC_IGNORE, encoding="utf-8")
    return audit(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "custom-ib-monitor")
    args = parser.parse_args()
    findings = stage(args.output)
    if findings:
        for finding in findings:
            print(finding)
        print("Source candidate failed the privacy scan; do not publish it.")
        return 1
    print(f"Source candidate staged and scanned at {args.output.resolve()}")
    print("Manual review, tests, license, security work, and release checks still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
