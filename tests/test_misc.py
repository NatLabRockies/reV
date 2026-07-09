# -*- coding: utf-8 -*-
"""PyTest file misc reV tests"""
import os
import shutil
import subprocess
from importlib.metadata import version


def test_rev_version_cli_is_clean():
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
