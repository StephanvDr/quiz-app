#!/usr/bin/env python3
"""Code Quiz: multiple-choice quizzes for coding subjects.

Each subject is a folder under quizzes/ holding a quiz.json (title, category,
...) and one JSON file per topic. This script serves the app, builds a
self-contained HTML file and checks the quiz files.

    python quiz.py                  serve the app on http://localhost:8000
    python quiz.py app              run the desktop app (modules, GitHub library)
    python quiz.py build            write dist/index.html (one self-contained file)
    python quiz.py pack             write each subject as a .quiz module file
    python quiz.py validate         check the structure of every quiz file
    python quiz.py verify           run the Python snippets and check the answers

Everything except `verify` uses only the standard library. `verify` needs the
libraries the snippets import (pip install -r requirements-dev.txt).
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import warnings
import webbrowser
from http.client import HTTPException
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit

VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
QUIZ_DIR = ROOT / "quizzes"
META_FILE = "quiz.json"

# A module is one subject in a single file, for sharing and for the desktop app.
MODULE_FORMAT = "code-quiz-module"
MODULE_EXT = ".quiz"

# The desktop app's GitHub library: subjects in the quizzes/ folder of this repository.
DEFAULT_LIBRARY = {"repo": "StephanvDr/quiz-app", "branch": "main"}
GITHUB_API = os.environ.get("CODEQUIZ_GITHUB_API", "https://api.github.com")
GITHUB_RAW = os.environ.get("CODEQUIZ_GITHUB_RAW", "https://raw.githubusercontent.com")
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
BRANCH_PATTERN = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_./-]*")

# The desktop app always tries the same port: the browser keeps progress per address.
APP_PORT = 47280
IDLE_SECONDS = 900  # the app window pings every 30 s; stop 15 minutes after it was closed
MAX_UPLOAD = 20_000_000

SUBJECT_KEYS = {"title", "category", "description", "language", "badge", "note", "prelude"}
QUESTION_KEYS = {
    "id", "difficulty", "question", "code", "options", "answer", "explanation",
    "check", "expect", "shuffle",
}
DIFFICULTIES = ("easy", "medium", "hard")
CHECKS = ("output", "options")
ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class QuizError(Exception):
    """Quiz files that can't be loaded or don't pass validation."""


# ---------------------------------------------------------------- loading


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise QuizError(f"{rel(path)}: invalid JSON on line {e.lineno}: {e.msg}") from None


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:  # an added module outside the repository
        return str(path)


def as_text(value) -> str:
    """Code can be written as a list of lines to keep the JSON readable."""
    return "\n".join(value) if isinstance(value, list) else value


def load_subjects() -> list[dict]:
    subjects = []
    for meta_path in sorted(QUIZ_DIR.rglob(META_FILE)):
        folder = meta_path.parent
        topics = [
            {"id": path.stem, "path": path, "data": read_json(path)}
            for path in sorted(folder.glob("*.json"))
            if path.name != META_FILE
        ]
        subjects.append({
            "id": "-".join(folder.relative_to(QUIZ_DIR).parts),
            "path": meta_path,
            "meta": read_json(meta_path),
            "topics": topics,
            "source": {"kind": "built-in"},
        })
    return subjects


def payload(home: Path | None = None) -> dict:
    """Everything the app needs, as one JSON-ready dict.

    With `home` (the desktop app's data folder), modules added there are
    included too; they replace a built-in subject with the same id.
    """
    subjects = load_subjects()
    errors = validate(subjects)
    if errors:
        raise QuizError("\n".join(errors))
    data = {}
    if home is not None:
        added, problems = load_modules(home / "modules")
        by_id = {s["id"]: s for s in subjects}
        for subject in added:
            if subject["id"] in by_id:
                subject["source"]["replaces"] = "built-in"
            by_id[subject["id"]] = subject
        subjects = list(by_id.values())
        data["problems"] = problems
        data["desktop"] = {
            "version": VERSION,
            "modulesDir": str(home / "modules"),
            "library": public_library(load_settings(home)),
        }
    subjects.sort(key=lambda s: (s["meta"]["category"].lower(), s["meta"]["title"].lower()))
    return {"subjects": [export_subject(s) for s in subjects], **data}


def export_subject(subject: dict) -> dict:
    meta = subject["meta"]
    return {
        "id": subject["id"],
        "title": meta["title"],
        "category": meta["category"],
        "description": meta.get("description", ""),
        "language": meta.get("language", ""),
        "badge": meta.get("badge", ""),
        "note": meta.get("note", ""),
        "source": subject.get("source", {"kind": "built-in"}),
        "topics": [
            {
                "id": topic["id"],
                "title": topic["data"]["topic"],
                "questions": [export_question(q) for q in topic["data"]["questions"]],
            }
            for topic in subject["topics"]
        ],
    }


def export_question(q: dict) -> dict:
    out = {key: q[key] for key in ("id", "question", "options", "answer", "explanation")}
    if "difficulty" in q:
        out["difficulty"] = q["difficulty"]
    if "code" in q:
        out["code"] = as_text(q["code"])
    if q.get("shuffle") is False:
        out["shuffle"] = False
    return out


# ---------------------------------------------------------------- validation


def validate(subjects: list[dict]) -> list[str]:
    errors = []
    if not subjects:
        errors.append(f"no subjects found: add a folder with a {META_FILE} under quizzes/")
    for subject in subjects:
        where = rel(subject["path"])
        meta = subject["meta"]
        if not isinstance(meta, dict):
            errors.append(f"{where}: must be a JSON object")
            continue
        for key in ("title", "category"):
            if not is_text(meta.get(key)):
                errors.append(f'{where}: "{key}" is required')
        for key in sorted(meta.keys() - SUBJECT_KEYS):
            errors.append(f'{where}: unknown key "{key}"')
        if not subject["topics"]:
            errors.append(f"{where}: no topic files next to it")
        seen_ids: dict[str, str] = {}
        for topic in subject["topics"]:
            errors.extend(validate_topic(topic, seen_ids))
    return errors


def validate_topic(topic: dict, seen_ids: dict[str, str]) -> list[str]:
    where = rel(topic["path"])
    data = topic["data"]
    if not isinstance(data, dict):
        return [f"{where}: must be a JSON object"]
    errors = []
    if not is_text(data.get("topic")):
        errors.append(f'{where}: "topic" is required')
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        return errors + [f'{where}: "questions" must be a non-empty list']
    for number, q in enumerate(questions, 1):
        label = q.get("id") if isinstance(q, dict) and is_text(q.get("id")) else f"#{number}"
        errors.extend(f"{where}: {label}: {problem}" for problem in question_problems(q))
        if isinstance(q, dict) and is_text(q.get("id")):
            if q["id"] in seen_ids:
                errors.append(f'{where}: {label}: id is already used in {seen_ids[q["id"]]}')
            seen_ids[q["id"]] = where
    return errors


def question_problems(q) -> list[str]:
    if not isinstance(q, dict):
        return ["must be a JSON object"]
    problems = [f'unknown key "{key}"' for key in sorted(q.keys() - QUESTION_KEYS)]
    if not (is_text(q.get("id")) and ID_PATTERN.fullmatch(q["id"])):
        problems.append('"id" must be lowercase words joined by hyphens, like "groupby-size"')
    if "difficulty" in q and q["difficulty"] not in DIFFICULTIES:
        problems.append(f'"difficulty" must be one of {", ".join(DIFFICULTIES)}')
    for key in ("question", "explanation"):
        if not is_text(q.get(key)):
            problems.append(f'"{key}" is required')
    if "code" in q and not (is_text(q["code"]) or is_text_list(q["code"])):
        problems.append('"code" must be a string or a list of lines')
    options = q.get("options")
    if not (is_text_list(options) and 2 <= len(options) <= 6 and all(o.strip() for o in options)):
        problems.append('"options" must be a list of 2 to 6 non-empty strings')
    else:
        if len(set(options)) != len(options):
            problems.append("options must all be different")
        answer = q.get("answer")
        if not (isinstance(answer, int) and not isinstance(answer, bool) and 0 <= answer < len(options)):
            problems.append(f'"answer" must be the index of the correct option (0 to {len(options) - 1})')
    check = q.get("check")
    if check is not None:
        if check not in CHECKS:
            problems.append(f'"check" must be one of {", ".join(CHECKS)}')
        if "code" not in q:
            problems.append('"check" needs "code" to run')
        if check == "options" and is_text_list(options) and any(code_span(o) is None for o in options):
            problems.append('with "check": "options", every option must be a single `code` span')
    if "expect" in q and (check != "options" or not is_text(q["expect"])):
        problems.append('"expect" is a Python expression and only works with "check": "options"')
    if "shuffle" in q and not isinstance(q["shuffle"], bool):
        problems.append('"shuffle" must be true or false')
    return problems


def is_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_text_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def code_span(text: str) -> str | None:
    """Return the code inside an option that is exactly one `code` span."""
    match = re.fullmatch(r"(`+)(?!`)(.*[^`])\1", text.strip(), re.S)
    if not match:
        return None
    ticks, code = match.groups()
    if re.search(rf"(?<!`){ticks}(?!`)", code):
        return None  # more than one span, e.g. "`a` or `b`"
    if code.startswith(" ") and code.endswith(" ") and code.strip():
        code = code[1:-1]
    return code


# ---------------------------------------------------------------- verification


class Raised:
    """Stands in for the result of an option that raised an exception."""

    def __init__(self, error: BaseException):
        self.name = type(error).__name__

    def __repr__(self):
        return f"raises {self.name}"


def run(source: str, namespace: dict, mode: str = "exec"):
    """Run code; return (result, stdout, deprecation warnings)."""
    stdout = io.StringIO()
    with warnings.catch_warnings(record=True) as caught, contextlib.redirect_stdout(stdout):
        warnings.simplefilter("always")
        try:
            result = eval(compile(source, "<quiz>", mode), namespace)
        except Exception as error:  # the snippet's own exceptions are part of the quiz
            result = Raised(error)
    deprecations = [
        f"{w.category.__name__}: {str(w.message).splitlines()[0]}"
        for w in caught
        if issubclass(w.category, (DeprecationWarning, FutureWarning))
    ]
    return result, stdout.getvalue(), deprecations


def normalize(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip("\n")


def option_text(option: str) -> str:
    code = code_span(option)
    return normalize(code if code is not None else option)


def same(a, b) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, Raised):
        return a.name == b.name
    if hasattr(a, "equals"):  # pandas objects
        return bool(a.equals(b))
    try:
        import numpy as np

        if isinstance(a, np.ndarray):
            return a.shape == b.shape and bool(np.array_equal(a, b))
    except ImportError:
        pass
    try:
        return bool(a == b)
    except Exception:
        return False


def check_output(q: dict, prelude: str) -> list[str]:
    """The code's printed output (or the exception it raises) must be the answer."""
    result, stdout, deprecations = run(prelude + as_text(q["code"]), {"__name__": "__quiz__"})
    produced = result.name if isinstance(result, Raised) else normalize(stdout)
    expected = [option_text(o) for o in q["options"]]
    problems = [f"uses deprecated API ({d})" for d in deprecations]
    if produced != expected[q["answer"]]:
        problems.append(f"the code outputs {produced!r}, but the answer is {expected[q['answer']]!r}")
    for i, text in enumerate(expected):
        if i != q["answer"] and text == produced:
            problems.append(f"option {i} matches the output too")
    return problems


def check_options(q: dict, prelude: str) -> list[str]:
    """Each option is an expression run after the code: only the answer may work."""
    setup = prelude + as_text(q["code"])

    def evaluate(expression):
        namespace = {"__name__": "__quiz__"}
        result, _, deprecations = run(setup, namespace)
        if isinstance(result, Raised):
            raise QuizError(f"the code raises {result.name}")
        result, _, more = run(expression, namespace, mode="eval")
        return result, deprecations + more

    try:
        results = [evaluate(code_span(o)) for o in q["options"]]
        expected = evaluate(q["expect"])[0] if "expect" in q else None
    except QuizError as e:
        return [str(e)]
    answer, deprecations = results[q["answer"]]
    problems = [f"the answer uses deprecated API ({d})" for d in deprecations]
    if isinstance(answer, Raised):
        problems.append(f"the answer {answer!r}")
    elif expected is not None and not same(answer, expected):
        problems.append('the answer does not equal "expect"')
    for i, (result, _) in enumerate(results):
        if i != q["answer"] and not isinstance(result, Raised) and same(result, answer):
            problems.append(f"option {i} gives the same result as the answer")
    return problems


def verify(subjects: list[dict], only: str | None) -> int:
    failures = checked = 0
    for subject in subjects:
        meta = subject["meta"]
        if (only and subject["id"] != only) or meta.get("language") != "python":
            continue
        prelude = as_text(meta.get("prelude", ""))
        prelude = prelude + "\n" if prelude else ""
        try:
            run_prelude(prelude)
        except QuizError as e:
            print(f"{subject['id']}: {e}")
            return 1
        count = 0
        for topic in subject["topics"]:
            for q in topic["data"]["questions"]:
                check = q.get("check")
                if check is None:
                    continue
                count += 1
                problems = (check_output if check == "output" else check_options)(q, prelude)
                for problem in problems:
                    print(f"  FAIL {rel(topic['path'])}: {q['id']}: {problem}")
                failures += bool(problems)
        checked += count
        print(f"{subject['id']}: ran {count} checked questions")
    if only and not checked:
        print(f'no checked questions for "{only}"')
        return 1
    print(f"{checked - failures} passed, {failures} failed")
    return 1 if failures else 0


def run_prelude(prelude: str) -> None:
    result, _, _ = run(prelude, {})
    if isinstance(result, Raised):
        raise QuizError(
            f"the prelude raises {result.name}; install the libraries it imports "
            "(pip install -r requirements-dev.txt)"
        )


# ---------------------------------------------------------------- modules


def pack_subject(subject: dict, source: dict | None = None) -> dict:
    """One subject as a module: the quiz.json plus every topic file, in one dict."""
    module = {
        "format": MODULE_FORMAT,
        "version": 1,
        "id": subject["id"],
        "subject": subject["meta"],
        "topics": [{"file": topic["id"], **topic["data"]} for topic in subject["topics"]],
    }
    if source:
        module["source"] = source
    return module


def module_problems(data) -> list[str]:
    """Problems with a module's outer structure; `validate` checks the questions."""
    if not isinstance(data, dict) or data.get("format") != MODULE_FORMAT:
        return [f'this is not a Code Quiz module (it needs "format": "{MODULE_FORMAT}")']
    problems = []
    if data.get("version") != 1:
        problems.append('unsupported "version": this app reads version 1 modules')
    if not (is_text(data.get("id")) and ID_PATTERN.fullmatch(data["id"])):
        problems.append('"id" must be lowercase words joined by hyphens, like "python-pandas"')
    if not isinstance(data.get("subject"), dict):
        problems.append('"subject" (the contents of quiz.json) is missing')
    topics = data.get("topics")
    if not isinstance(topics, list) or not topics:
        problems.append('"topics" must be a non-empty list')
    elif not all(isinstance(t, dict) and is_text(t.get("file")) and ID_PATTERN.fullmatch(t["file"]) for t in topics):
        problems.append('every topic needs a "file" name made of lowercase words and hyphens, like "01-basics"')
    return problems


def module_to_subject(data: dict, path: Path) -> dict:
    return {
        "id": data["id"],
        "path": path,
        "meta": data["subject"],
        "topics": [
            {"id": t["file"], "path": path, "data": {k: v for k, v in t.items() if k != "file"}}
            for t in data["topics"]
        ],
        "source": dict(data["source"]) if isinstance(data.get("source"), dict) else {"kind": "file"},
    }


def checked_module(data, label: Path) -> dict:
    """The subject in a module, or QuizError listing everything that is wrong with it."""
    errors = module_problems(data)
    if not errors:
        subject = module_to_subject(data, label)
        errors = validate([subject])
    if errors:
        raise QuizError("\n".join(errors))
    return subject


def load_modules(modules_dir: Path) -> tuple[list[dict], list[dict]]:
    """Valid modules in the folder, plus a problem report for every file that isn't."""
    subjects, problems, seen = [], [], {}
    for path in sorted(modules_dir.glob(f"*{MODULE_EXT}")):
        try:
            subject = checked_module(json.loads(path.read_text(encoding="utf-8-sig")), path)
        except (QuizError, OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            problems.append({"file": path.name, "errors": str(e).splitlines()})
            continue
        if subject["id"] in seen:
            problems.append({"file": path.name, "errors": [f'the id "{subject["id"]}" is also used by {seen[subject["id"]]}']})
            continue
        seen[subject["id"]] = path.name
        subjects.append(subject)
    return subjects, problems


def install_module(data, modules_dir: Path, label: str = "module") -> dict:
    """Check a module and save it as <id>.quiz, replacing an older copy."""
    subject = checked_module(data, Path(label))
    modules_dir.mkdir(parents=True, exist_ok=True)
    target = modules_dir / f"{subject['id']}{MODULE_EXT}"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(target)
    questions = sum(len(t["data"]["questions"]) for t in subject["topics"])
    return {"id": subject["id"], "title": subject["meta"]["title"], "questions": questions}


def remove_module(subject_id: str, modules_dir: Path) -> None:
    path = modules_dir / f"{subject_id}{MODULE_EXT}"
    if not ID_PATTERN.fullmatch(subject_id) or not path.is_file():
        raise QuizError(f"{subject_id} is not an added module")
    path.unlink()


def git_blob_sha(content: bytes) -> str:
    """The id git gives a file's contents (with LF line endings, as GitHub stores them)."""
    content = content.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(content) + content).hexdigest()


def revision(files: list[tuple[str, str]]) -> str:
    """A short fingerprint of a subject's files, from (repository path, blob sha) pairs."""
    text = "\n".join(f"{path} {sha}" for path, sha in sorted(files))
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def local_revision(subject: dict) -> str | None:
    """The revision of a built-in subject, comparable with what the library reports."""
    paths = [subject["path"], *(t["path"] for t in subject["topics"])]
    try:
        return revision([(rel(p), git_blob_sha(p.read_bytes())) for p in paths])
    except OSError:
        return None


# ---------------------------------------------------------------- desktop data


def data_dir() -> Path:
    """Where the desktop app keeps added modules, settings and its log."""
    if os.environ.get("CODEQUIZ_HOME"):
        return Path(os.environ["CODEQUIZ_HOME"])
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home()) / "CodeQuiz"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CodeQuiz"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "code-quiz"


def load_settings(home: Path) -> dict:
    try:
        saved = json.loads((home / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    library = saved.get("library") if isinstance(saved.get("library"), dict) else {}
    return {"library": {**DEFAULT_LIBRARY, "token": "", **library}}


def save_settings(home: Path, settings: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    path = home / "settings.json"
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    with contextlib.suppress(OSError):
        path.chmod(0o600)  # it can hold a GitHub token


def public_library(settings: dict) -> dict:
    """Library settings for the page: never the token itself."""
    library = settings["library"]
    return {"repo": library["repo"], "branch": library["branch"], "hasToken": bool(library["token"])}


# ---------------------------------------------------------------- GitHub library


class Library:
    """Subjects in the quizzes/ folder of a GitHub repository.

    One call to the trees API lists the files. Contents come from the blobs API
    when there is a token (needed for private repositories), and otherwise
    from raw.githubusercontent.com, which doesn't count against the API's
    hourly limit for requests without a token.
    """

    def __init__(self, repo: str, branch: str, token: str = ""):
        self.repo, self.branch, self.token = repo, branch, token

    def get(self, url: str) -> bytes:
        headers = {"User-Agent": f"code-quiz/{VERSION}", "Accept": "application/vnd.github+json"}
        if self.token and url.startswith(GITHUB_API):
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            raise QuizError(self.explain(e)) from None
        except (urllib.error.URLError, OSError) as e:
            raise QuizError(f"Couldn't reach GitHub ({getattr(e, 'reason', e)}). Check your internet connection.") from None

    def explain(self, e: urllib.error.HTTPError) -> str:
        if e.code == 401:
            return "GitHub didn't accept the token. It may have expired: create a new one and save it here."
        if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0":
            return "GitHub's hourly limit for requests without a token is used up. Try again later, or save a token."
        if e.code in (403, 404):
            hint = "Check the name and the branch." if self.token else "If the repository is private, save a token with read access to its contents."
            return f"GitHub couldn't find {self.repo} on branch {self.branch}. {hint}"
        return f"GitHub answered {e.code} {e.reason}."

    def subjects(self) -> list[dict]:
        url = f"{GITHUB_API}/repos/{self.repo}/git/trees/{quote(self.branch, safe='')}?recursive=1"
        tree = json.loads(self.get(url))
        blobs = {e["path"]: e["sha"] for e in tree.get("tree", []) if e.get("type") == "blob"}
        found = []
        for path in sorted(blobs):
            parts = path.split("/")
            if len(parts) < 3 or parts[0] != "quizzes" or parts[-1] != META_FILE:
                continue
            folder = path.rsplit("/", 1)[0]
            topics = sorted(
                p for p in blobs
                if p.rsplit("/", 1)[0] == folder and p.endswith(".json") and p != path
            )
            files = [path, *topics]
            found.append({
                "id": "-".join(parts[1:-1]),
                "files": [(p, blobs[p]) for p in files],
                "revision": revision([(p, blobs[p]) for p in files]),
            })
        return found

    def read(self, path: str, sha: str):
        if self.token:
            blob = json.loads(self.get(f"{GITHUB_API}/repos/{self.repo}/git/blobs/{sha}"))
            content = base64.b64decode(blob["content"])
        else:
            content = self.get(f"{GITHUB_RAW}/{self.repo}/refs/heads/{quote(self.branch)}/{quote(path)}")
        try:
            return json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise QuizError(f"{path} in {self.repo} is not valid JSON ({e})") from None

    def catalog(self) -> list[dict]:
        entries = []
        for found in self.subjects():
            meta = self.read(*found["files"][0])
            meta = meta if isinstance(meta, dict) else {}
            entries.append({
                "id": found["id"],
                "title": str(meta.get("title") or found["id"]),
                "category": str(meta.get("category") or ""),
                "description": str(meta.get("description") or ""),
                "badge": str(meta.get("badge") or ""),
                "topics": len(found["files"]) - 1,
                "revision": found["revision"],
            })
        return entries

    def module(self, subject_id: str) -> dict:
        found = next((s for s in self.subjects() if s["id"] == subject_id), None)
        if found is None:
            raise QuizError(f"{subject_id} is not in {self.repo} on branch {self.branch}.")
        (meta_path, meta_sha), *topic_files = found["files"]
        topics = []
        for path, sha in topic_files:
            data = self.read(path, sha)
            if not isinstance(data, dict):
                raise QuizError(f"{path} in {self.repo} is not a topic file")
            topics.append({"file": Path(path).stem, **data})
        return {
            "format": MODULE_FORMAT,
            "version": 1,
            "id": found["id"],
            "subject": self.read(meta_path, meta_sha),
            "topics": topics,
            "source": {"kind": "github", "repo": self.repo, "branch": self.branch, "revision": found["revision"]},
        }


# ---------------------------------------------------------------- serve & build


class AppHandler(SimpleHTTPRequestHandler):
    """Serves app/ plus quizzes.json, rebuilt from the quiz files on every request.

    Under the desktop app (a DesktopServer) it also answers the /api/ routes
    that add, remove and download modules. Those only accept requests for
    127.0.0.1 (no DNS rebinding), and changes need the X-Code-Quiz header,
    which other websites can't send.
    """

    # Fixed types for the app's files: on Windows, mimetypes reads the
    # registry, which can map .js to text/plain.
    extensions_map = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".svg": "image/svg+xml",
        ".json": "application/json",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    @property
    def home(self) -> Path | None:
        return getattr(self.server, "home", None)

    def do_GET(self):
        self.touch()
        path = urlsplit(self.path).path
        if self.home and not self.from_this_app():
            return self.reply(403, {"error": "Requests must come from Code Quiz itself."})
        if path == "/quizzes.json":
            return self.send_payload()
        if self.home and path.startswith("/api/"):
            return self.api("GET", path)
        return super().do_GET()

    def do_POST(self):
        self.change("POST")

    def do_DELETE(self):
        self.change("DELETE")

    def change(self, method: str) -> None:
        self.touch()
        path = urlsplit(self.path).path
        if not (self.home and path.startswith("/api/")):
            return self.reply(404, {"error": "Not found."})
        if not self.from_this_app() or self.headers.get("X-Code-Quiz") != "1":
            return self.reply(403, {"error": "Requests must come from Code Quiz itself."})
        return self.api(method, path)

    def from_this_app(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def touch(self) -> None:
        if hasattr(self.server, "last_seen"):
            self.server.last_seen = time.monotonic()

    def send_payload(self) -> None:
        try:
            body = json.dumps(payload(self.home), ensure_ascii=False).encode("utf-8")
            status, content_type = 200, "application/json"
        except QuizError as e:
            body = str(e).encode("utf-8")
            status, content_type = 500, "text/plain"
        self.send_body(status, content_type, body)

    def reply(self, status: int, data: dict) -> None:
        self.send_body(status, "application/json", json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def send_body(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            raise QuizError("That file is too large to be a quiz module.")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise QuizError("That file is not JSON, so it can't be a quiz module.") from None

    def api(self, method: str, path: str) -> None:
        modules = self.home / "modules"
        try:
            if (method, path) == ("GET", "/api/ping"):
                return self.reply(200, {"app": "code-quiz", "version": VERSION})
            if (method, path) == ("POST", "/api/modules"):
                return self.reply(200, install_module(self.read_body(), modules, "uploaded file"))
            if method == "DELETE" and path.startswith("/api/modules/"):
                remove_module(path.rsplit("/", 1)[1], modules)
                return self.reply(200, {"ok": True})
            if (method, path) == ("GET", "/api/library"):
                return self.reply(200, self.library_listing())
            if (method, path) == ("POST", "/api/library/install"):
                body = self.read_body()
                subject_id = str(body.get("id") if isinstance(body, dict) else "")
                if not ID_PATTERN.fullmatch(subject_id):
                    raise QuizError("Pick a subject from the library.")
                module = self.library().module(subject_id)
                return self.reply(200, install_module(module, modules, f"{subject_id} from GitHub"))
            if (method, path) == ("POST", "/api/settings"):
                return self.reply(200, self.update_settings(self.read_body()))
            if (method, path) == ("POST", "/api/open-folder"):
                modules.mkdir(parents=True, exist_ok=True)
                open_folder(modules)
                return self.reply(200, {"ok": True})
            if (method, path) == ("POST", "/api/quit"):
                self.reply(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return None
        except QuizError as e:
            return self.reply(400, {"error": str(e)})
        return self.reply(404, {"error": "Not found."})

    def library(self) -> Library:
        library = load_settings(self.home)["library"]
        return Library(library["repo"], library["branch"], library["token"])

    def library_listing(self) -> dict:
        library = self.library()
        entries = library.catalog()
        installed = {s["id"]: ("built-in", local_revision(s)) for s in load_subjects()}
        for subject in load_modules(self.home / "modules")[0]:
            installed[subject["id"]] = (subject["source"].get("kind"), subject["source"].get("revision"))
        for entry in entries:
            kind, rev = installed.get(entry["id"], (None, None))
            entry["installedAs"] = kind
            entry["state"] = "new" if kind is None else "current" if rev == entry["revision"] else "update"
        return {"repo": library.repo, "branch": library.branch, "subjects": entries}

    def update_settings(self, body) -> dict:
        if not isinstance(body, dict):
            raise QuizError("Settings must be a JSON object.")
        settings = load_settings(self.home)
        library = settings["library"]
        repo = str(body.get("repo", library["repo"])).strip()
        branch = str(body.get("branch", library["branch"])).strip()
        if not REPO_PATTERN.fullmatch(repo):
            raise QuizError('Write the repository as owner/name, like "StephanvDr/quiz-app".')
        if not BRANCH_PATTERN.fullmatch(branch):
            raise QuizError(f'"{branch}" is not a valid branch name.')
        library.update(repo=repo, branch=branch)
        if body.get("clearToken"):
            library["token"] = ""
        elif str(body.get("token") or "").strip():
            library["token"] = str(body["token"]).strip()
        save_settings(self.home, settings)
        return {"library": public_library(settings)}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        pass


class DesktopServer(ThreadingHTTPServer):
    """The desktop app's server: knows its data folder and when it was last used."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], home: Path):
        super().__init__(address, AppHandler)
        self.home = home
        self.last_seen = time.monotonic()


def open_folder(path: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - opens Explorer on our own folder
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as e:
        raise QuizError(f"Couldn't open {path}: {e}") from None


def serve(port: int, open_browser: bool) -> int:
    print(summary())
    for candidate in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), AppHandler)
            break
        except OSError:
            continue
    else:
        print(f"No free port between {port} and {port + 19}; pick one with --port.")
        return 1
    url = f"http://localhost:{candidate}/"
    print(f"Serving Code Quiz at {url}  (edits to quiz files show up on reload; Ctrl+C stops)")
    if open_browser:
        webbrowser.open(url)
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


def run_app(port: int, imports: list[Path], window: bool, idle: int) -> int:
    """The desktop app: one server per user, shown in its own browser window."""
    home = data_dir()
    (home / "modules").mkdir(parents=True, exist_ok=True)
    log_to_file(home)
    running = find_instance(port)
    if running:
        for path in imports:
            print(send_module(running, path))
        if window:
            show_window(running + ("#modules" if imports else ""))
        return 0
    server = None
    for candidate in range(port, port + 10):
        try:
            server = DesktopServer(("127.0.0.1", candidate), home)
            break
        except OSError:
            continue
    if server is None:
        print(f"Ports {port} to {port + 9} are all in use; start with --port to pick another.")
        return 1
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    for path in imports:
        try:
            added = install_module(json.loads(path.read_text(encoding="utf-8-sig")), home / "modules", path.name)
            print(f"Added {added['title']} from {path}")
        except (QuizError, OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f"Could not add {path}: {e}")
    print(f"Code Quiz {VERSION} at {url}  (modules: {home / 'modules'})")
    if window:
        show_window(url + ("#modules" if imports else ""))
    if idle:
        threading.Thread(target=stop_when_idle, args=(server, idle), daemon=True).start()
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


def log_to_file(home: Path) -> None:
    """pythonw.exe has no console, so keep messages and errors in a log file."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    path = home / "code-quiz.log"
    with contextlib.suppress(OSError):
        if path.stat().st_size > 1_000_000:
            path.unlink()
    log = open(path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives as long as the app
    sys.stdout = sys.stderr = log
    print(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')}")


def is_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "api/ping", timeout=1) as response:
            return json.loads(response.read()).get("app") == "code-quiz"
    except (OSError, ValueError, HTTPException):  # HTTPException: it stopped mid-reply
        return False


def find_instance(port: int) -> str | None:
    """The address of a Code Quiz app that is already running, if any."""
    for candidate in range(port, port + 10):
        url = f"http://127.0.0.1:{candidate}/"
        if is_running(url):
            return url
    return None


def call_instance(url: str, path: str, body: bytes = b"") -> dict:
    request = urllib.request.Request(
        url + path, data=body, method="POST",
        headers={"X-Code-Quiz": "1", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def send_module(url: str, path: Path) -> str:
    try:
        result = call_instance(url, "api/modules", path.read_bytes())
    except (OSError, ValueError, HTTPException) as e:
        return f"Could not add {path}: {e}"
    return f"Added {result['title']} from {path}" if "title" in result else f"Could not add {path}: {result.get('error')}"


def quit_app(port: int) -> int:
    running = find_instance(port)
    if not running:
        print("Code Quiz is not running.")
        return 0
    with contextlib.suppress(OSError, ValueError, HTTPException):
        call_instance(running, "api/quit")
    deadline = time.monotonic() + 10  # the installer waits on this before replacing files
    while is_running(running) and time.monotonic() < deadline:
        time.sleep(0.2)
    print(f"Stopped Code Quiz at {running}")
    return 0


def stop_when_idle(server: DesktopServer, idle: int) -> None:
    while True:
        time.sleep(min(5, idle))
        if time.monotonic() - server.last_seen > idle:
            server.shutdown()
            return


def show_window(url: str) -> None:
    """Open the app in its own window (Edge or Chrome app mode), or else a browser tab."""
    for browser in browser_candidates():
        if browser and Path(browser).is_file():
            try:
                subprocess.Popen([browser, f"--app={url}", "--window-size=1180,860"])
                return
            except OSError:
                continue
    webbrowser.open(url)


def browser_candidates() -> list[str | None]:
    if sys.platform == "win32":
        folders = [os.environ.get(name) for name in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        programs = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
        return [str(Path(folder) / program) for program in programs for folder in folders if folder]
    if sys.platform == "darwin":
        return [f"/Applications/{name}.app/Contents/MacOS/{name}" for name in ("Microsoft Edge", "Google Chrome", "Chromium")]
    return [shutil.which(name) for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser")]


def pack(subject_ids: list[str], out_dir: Path) -> list[Path]:
    subjects = load_subjects()
    errors = validate(subjects)
    if errors:
        raise QuizError("\n".join(errors))
    unknown = set(subject_ids) - {s["id"] for s in subjects}
    if unknown:
        raise QuizError(f"No subject called {', '.join(sorted(unknown))}; see `python quiz.py validate` for the ids")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for subject in subjects:
        if subject_ids and subject["id"] not in subject_ids:
            continue
        path = out_dir / f"{subject['id']}{MODULE_EXT}"
        path.write_text(json.dumps(pack_subject(subject), ensure_ascii=False, indent=1), encoding="utf-8")
        written.append(path)
    return written


def build(out_dir: Path) -> Path:
    data = json.dumps(payload(), ensure_ascii=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c")  # keeps "</script>" in a question from closing the tag
    html = (APP_DIR / "index.html").read_text(encoding="utf-8")
    css = (APP_DIR / "styles.css").read_text(encoding="utf-8")
    js = (APP_DIR / "app.js").read_text(encoding="utf-8")
    icon = base64.b64encode((APP_DIR / "icon.svg").read_bytes()).decode("ascii")
    inlined = {
        'href="icon.svg"': f'href="data:image/svg+xml;base64,{icon}"',
        '<link rel="stylesheet" href="styles.css">': f"<style>\n{css}</style>",
        '<script src="app.js"></script>': (
            f'<script id="quiz-data" type="application/json">{data}</script>\n<script>\n{js}</script>'
        ),
    }
    for tag, replacement in inlined.items():
        if tag not in html:
            raise QuizError(f"app/index.html: expected {tag}")
        html = html.replace(tag, replacement)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


def summary() -> str:
    try:
        data = payload()
    except QuizError as e:
        return f"Quiz files have problems (the app shows them too):\n{e}"
    lines = []
    for s in data["subjects"]:
        questions = sum(len(t["questions"]) for t in s["topics"])
        lines.append(f"{s['id']}: {questions} questions in {len(s['topics'])} topics")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve, build and check Code Quiz.")
    commands = parser.add_subparsers(dest="command")
    serve_cmd = commands.add_parser("serve", help="serve the app locally (the default)")
    serve_cmd.add_argument("--port", type=int, default=8000)
    serve_cmd.add_argument("--no-open", action="store_true", help="don't open a browser")
    app_cmd = commands.add_parser("app", help="run the desktop app: added modules, GitHub library, own window")
    app_cmd.add_argument("--port", type=int, default=APP_PORT)
    app_cmd.add_argument("--no-window", action="store_true", help="don't open a window")
    app_cmd.add_argument("--idle", type=int, default=IDLE_SECONDS,
                         help=f"stop after this many seconds without the window (default {IDLE_SECONDS}; 0 = never)")
    app_cmd.add_argument("--import", dest="imports", type=Path, action="append", default=[],
                         metavar="FILE", help="add a .quiz module file (used when you open a .quiz file)")
    quit_cmd = commands.add_parser("quit", help="stop a running desktop app")
    quit_cmd.add_argument("--port", type=int, default=APP_PORT)
    build_cmd = commands.add_parser("build", help="write one self-contained HTML file")
    build_cmd.add_argument("--out", type=Path, default=ROOT / "dist", help="output folder (default: dist)")
    pack_cmd = commands.add_parser("pack", help="write subjects as .quiz module files")
    pack_cmd.add_argument("subjects", nargs="*", help="subject ids (default: all)")
    pack_cmd.add_argument("--out", type=Path, default=ROOT / "dist" / "modules", help="output folder (default: dist/modules)")
    commands.add_parser("validate", help="check the structure of every quiz file")
    verify_cmd = commands.add_parser("verify", help="run Python snippets and check the answers")
    verify_cmd.add_argument("subject", nargs="?", help="only this subject, e.g. python-pandas")
    args = parser.parse_args(argv)

    try:
        if args.command in (None, "serve"):
            return serve(getattr(args, "port", 8000), not getattr(args, "no_open", False))
        if args.command == "app":
            return run_app(args.port, args.imports, not args.no_window, max(args.idle, 0))
        if args.command == "quit":
            return quit_app(args.port)
        if args.command == "build":
            out = build(args.out)
            print(f"Wrote {out} ({out.stat().st_size // 1024} KB). Open it in a browser or host it anywhere.")
            return 0
        if args.command == "pack":
            for path in pack(args.subjects, args.out):
                print(f"Wrote {path}")
            return 0
        subjects = load_subjects()
        errors = validate(subjects)
        if errors:
            print("\n".join(errors))
            print(f"{len(errors)} problem(s) found")
            return 1
        if args.command == "validate":
            print(summary())
            return 0
        return verify(subjects, args.subject)
    except QuizError as e:
        print(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
