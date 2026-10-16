"""The installed package must hold every file the source tree ships.

``web_app/`` is not a Python package (Streamlit runs its files by path), so
setuptools only installs the files ``package_data`` lists.  A missing pattern
does not show in a development (editable) install, which reads the source tree;
it shows only after ``pip install git+https://...``, as a GUI that cannot start
(``web_app/Home.py`` missing).  This test reads ``setup.py``'s own arguments and
checks that every source file is covered by them.
"""

import fnmatch
import runpy
from pathlib import Path

import setuptools

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "pyDataOrg"


def _setup_kwargs(monkeypatch) -> dict:
    got = {}
    monkeypatch.setattr(setuptools, "setup", lambda **kw: got.update(kw))
    monkeypatch.chdir(ROOT)
    runpy.run_path(str(ROOT / "setup.py"))
    return got


def _installed(rel: str, packages: set, patterns: list) -> bool:
    path = Path(rel)
    if path.suffix == ".py" and ".".join(("pyDataOrg",) + path.parent.parts).rstrip(".") in packages:
        return True
    return any(fnmatch.fnmatch(rel, pat) and rel.count("/") == pat.count("/") for pat in patterns)


def test_every_source_file_of_the_package_is_installed(monkeypatch):
    kw = _setup_kwargs(monkeypatch)
    packages = set(kw["packages"])
    patterns = kw["package_data"]["pyDataOrg"]
    files = [p.relative_to(PKG).as_posix() for p in PKG.rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    missing = [f for f in files if not _installed(f, packages, patterns)]
    assert not missing, f"not installed by setup.py: {missing}"


def test_the_web_app_entry_point_is_installed(monkeypatch):
    """The reason this test exists: without web_app/Home.py no GUI starts."""
    kw = _setup_kwargs(monkeypatch)
    assert _installed("web_app/Home.py", set(kw["packages"]), kw["package_data"]["pyDataOrg"])
