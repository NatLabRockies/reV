# -*- coding: utf-8 -*-
"""PyTest file misc reV tests"""
import os
import shutil
import subprocess
import py_compile
import warnings
from pathlib import Path
from importlib.metadata import version

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_rev_version_cli_is_clean():
    """Test that no warning is thrown when checking the reV CLI version"""
    exe = shutil.which("reV")
    assert exe is not None, "reV console script not found on PATH"

    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "error::SyntaxWarning"

    result = subprocess.run([exe, "--version"], capture_output=True, text=True,
                            env=env, check=False)

    expected = f"reV, version {version('NLR-reV')}"

    assert result.returncode == 0, (f"stdout: {result.stdout}\n"
                                    f"stderr: {result.stderr}")
    assert result.stderr == ""
    assert result.stdout.splitlines() == [expected]


@pytest.mark.parametrize(
    "relpath",
    [
        "reV/supply_curve/points.py",
        "reV/bespoke/bespoke.py",
        "reV/supply_curve/sc_aggregation.py",
    ],
)
def test_no_invalid_escape_warnings(relpath):
    """Test that no warning is thrown at compile time"""
    path = ROOT / relpath
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        py_compile.compile(str(path), doraise=True)
