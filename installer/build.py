"""Build the Windows installer: dist/CodeQuiz-Setup-<version>.exe

    python installer/build.py

Needs NSIS (makensis) on the PATH; it runs on Windows, Linux and macOS
(`apt install nsis`, `brew install makensis`, or https://nsis.sourceforge.io).

The installer carries its own copy of Python, so nothing else has to be
installed on the PC. That copy is the official "python" package on NuGet
(published by the Python Software Foundation): it is downloaded once into
build/, checked against a pinned SHA-512 and trimmed of what the app never
uses (pip, venv, C headers). The app, the built-in subjects and the icon are
staged next to it and makensis packs everything with installer/codequiz.nsi.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "installer"
sys.path.insert(0, str(ROOT))
import quiz  # noqa: E402  (the version number and the quiz checks)

PYTHON_VERSION = "3.13.17"
PYTHON_URL = f"https://api.nuget.org/v3-flatcontainer/python/{PYTHON_VERSION}/python.{PYTHON_VERSION}.nupkg"
PYTHON_SHA512 = (
    "0e667928bb4f19573c6cd88f65133b2e07b243a5c716f335b56aa66bb9ec6f82"
    "328256d22c3a29e23a0276ac5c6a6d786211feab524890ad1e56629196c6b29c"
)
# Parts of the Python package the app never uses.
PRUNE = ["include", "libs", "Lib/ensurepip", "Lib/venv", "Lib/pydoc_data", "Lib/__phello__", "Lib/site-packages"]
APP_FILES = ["index.html", "styles.css", "app.js", "icon.svg"]


def python_package(cache: Path, local: Path | None) -> Path:
    """The pinned NuGet package, downloaded once; refuses a file with the wrong checksum."""
    path = local or cache / f"python.{PYTHON_VERSION}.nupkg"
    if not path.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        print(f"Downloading Python {PYTHON_VERSION} for Windows from NuGet")
        partial = path.with_suffix(".part")
        with urllib.request.urlopen(PYTHON_URL, timeout=120) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out)
        partial.replace(path)
    digest = hashlib.sha512(path.read_bytes()).hexdigest()
    if digest != PYTHON_SHA512:
        raise SystemExit(f"{path} does not match the pinned SHA-512 (got {digest}); delete it and run again.")
    return path


def extract_python(package: Path, target: Path) -> None:
    """Unpack tools/ (the Python install) into target, then trim it."""
    root = target.resolve()
    with zipfile.ZipFile(package) as archive:
        for member in archive.infolist():
            name = member.filename
            if not name.startswith("tools/") or name.endswith("/"):
                continue
            dest = (root / name[len("tools/"):]).resolve()
            if not dest.is_relative_to(root):
                raise SystemExit(f"Refusing to unpack {name}: it points outside {root}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
    for part in PRUNE:
        shutil.rmtree(root / part, ignore_errors=True)
    for cache in root.rglob("__pycache__"):
        shutil.rmtree(cache)
    for name in ("python.exe", "pythonw.exe", "python313.dll", "Lib/os.py"):
        if not (root / name).is_file():
            raise SystemExit(f"The Python package has no {name}; is PYTHON_VERSION right?")


def stage(stage_dir: Path, package: Path) -> None:
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    extract_python(package, stage_dir / "python")
    shutil.copy2(ROOT / "quiz.py", stage_dir / "quiz.py")
    shutil.copy2(HERE / "icon.ico", stage_dir / "icon.ico")
    (stage_dir / "app").mkdir()
    for name in APP_FILES:
        shutil.copy2(quiz.APP_DIR / name, stage_dir / "app" / name)
    shutil.copytree(quiz.QUIZ_DIR, stage_dir / "quizzes", ignore=shutil.ignore_patterns("__pycache__", ".*"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "dist", help="where the installer goes (default: dist/)")
    parser.add_argument("--python-package", type=Path, help=f"a local copy of python.{PYTHON_VERSION}.nupkg")
    parser.add_argument("--makensis", default=shutil.which("makensis"), help="path to makensis")
    args = parser.parse_args()

    if not args.makensis:
        raise SystemExit("makensis was not found. Install NSIS (apt install nsis / brew install makensis) and run again.")
    errors = quiz.validate(quiz.load_subjects())
    if errors:
        raise SystemExit("The quizzes have problems; fix them first:\n" + "\n".join(errors))

    build = ROOT / "build"
    stage_dir = build / "stage"
    stage(stage_dir, python_package(build / "cache", args.python_package))
    args.out.mkdir(parents=True, exist_ok=True)
    outfile = (args.out / f"CodeQuiz-Setup-{quiz.VERSION}.exe").resolve()
    subprocess.run(
        [args.makensis, "-V2", f"-DVERSION={quiz.VERSION}", f"-DSTAGE={stage_dir.resolve()}",
         f"-DOUTFILE={outfile}", str(HERE / "codequiz.nsi")],
        check=True,
    )
    print(f"Built {outfile.relative_to(ROOT) if outfile.is_relative_to(ROOT) else outfile} "
          f"({outfile.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
