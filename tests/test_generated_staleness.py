"""Staleness guard for ``src/graphann/_generated.py``.

Re-runs the exact generator invocation used by ``scripts/generate_types.sh``
into a scratch file and byte-compares it against the committed generated
module. The committed file must always equal what the generator currently
produces from the spec -- if it doesn't, someone edited ``_generated.py``
by hand or forgot to regenerate after a spec change.

The spec is bundled at the standalone SDK root or shared monorepo root.
Its absence is asserted rather than skipped. Only the generator
binary is optional: when ``datamodel-codegen`` is not installed the
byte-comparison skips, because that is a genuinely missing dev dependency
rather than a broken tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PYTHON_DIR = Path(__file__).resolve().parent.parent
GENERATED = PYTHON_DIR / "src" / "graphann" / "_generated.py"
HEADER = PYTHON_DIR / "scripts" / "_generated_header.txt"
# Prefer the standalone SDK bundle, then the shared monorepo spec.
_default_spec = PYTHON_DIR / "api" / "openapi" / "spec.yaml"
if not _default_spec.is_file():
    _default_spec = PYTHON_DIR.parent / "api" / "openapi" / "spec.yaml"
SPEC = Path(os.environ.get("GRAPHANN_SPEC_PATH") or _default_spec).resolve()

_codegen = shutil.which("datamodel-codegen")


def test_vendored_spec_is_present() -> None:
    """The spec is committed, so its absence is a broken checkout, not a missing
    optional tool. This assertion runs even when datamodel-codegen is absent, so
    the staleness check can never be silently skipped for both reasons at once."""
    assert SPEC.exists(), f"vendored spec missing at {SPEC}"


@pytest.mark.skipif(
    _codegen is None,
    reason="datamodel-codegen not installed (pip install -e '.[dev]')",
)
def test_generated_types_are_not_stale(tmp_path: Path) -> None:
    out = tmp_path / "_generated.py"
    subprocess.run(
        [
            str(_codegen),
            "--input",
            str(SPEC),
            "--input-file-type",
            "openapi",
            "--output",
            str(out),
            "--target-python-version",
            "3.10",
            "--formatters",
            "black",
            "--disable-timestamp",
            "--field-constraints",
            "--custom-file-header-path",
            str(HEADER),
        ],
        check=True,
        cwd=PYTHON_DIR,
    )
    # Match scripts/generate_types.sh: re-run standalone black then isort.
    # They don't always agree byte-for-byte with datamodel-codegen's
    # internal --formatters black pass (observed: quote normalization,
    # import order), and the repo's pre-commit hook runs standalone
    # black+isort on every staged .py file, re-staging the result -- so
    # the committed file is always in black+isort's output form.
    black = shutil.which("black")
    if black is not None:
        subprocess.run([black, "--quiet", str(out)], check=True)
    isort = shutil.which("isort")
    if isort is not None:
        subprocess.run([isort, "--quiet", str(out)], check=True, cwd=PYTHON_DIR)
    fresh = out.read_text()
    committed = GENERATED.read_text()
    assert fresh == committed, (
        "src/graphann/_generated.py is stale relative to api/openapi/spec.yaml. "
        "Run scripts/generate_types.sh and commit the result."
    )
