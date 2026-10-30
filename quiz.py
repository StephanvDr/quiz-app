#!/usr/bin/env python3
"""Code Quiz: multiple-choice quizzes for coding subjects.

Each subject is a folder under quizzes/ holding a quiz.json (title, category,
...) and one JSON file per topic. This script serves the app, builds a
self-contained HTML file and checks the quiz files.

    python quiz.py                  serve the app on http://localhost:8000
    python quiz.py build            write dist/index.html (one self-contained file)
    python quiz.py validate         check the structure of every quiz file
    python quiz.py verify           run the Python snippets and check the answers

Everything except `verify` uses only the standard library. `verify` needs the
libraries the snippets import (pip install -r requirements-dev.txt).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import warnings
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
QUIZ_DIR = ROOT / "quizzes"
META_FILE = "quiz.json"

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
    return path.relative_to(ROOT).as_posix()


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
        })
    return subjects


def payload() -> dict:
    """Everything the app needs, as one JSON-ready dict."""
    subjects = load_subjects()
    errors = validate(subjects)
    if errors:
        raise QuizError("\n".join(errors))
    return {"subjects": [export_subject(s) for s in subjects]}


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


# ---------------------------------------------------------------- serve & build


class AppHandler(SimpleHTTPRequestHandler):
    """Serves app/ plus quizzes.json, rebuilt from the quiz files on every request."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def do_GET(self):
        if self.path.split("?", 1)[0] != "/quizzes.json":
            return super().do_GET()
        try:
            body = json.dumps(payload(), ensure_ascii=False).encode("utf-8")
            status, content_type = 200, "application/json"
        except QuizError as e:
            body = str(e).encode("utf-8")
            status, content_type = 500, "text/plain"
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        pass


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


def build(out_dir: Path) -> Path:
    data = json.dumps(payload(), ensure_ascii=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c")  # keeps "</script>" in a question from closing the tag
    html = (APP_DIR / "index.html").read_text(encoding="utf-8")
    css = (APP_DIR / "styles.css").read_text(encoding="utf-8")
    js = (APP_DIR / "app.js").read_text(encoding="utf-8")
    inlined = {
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
    build_cmd = commands.add_parser("build", help="write one self-contained HTML file")
    build_cmd.add_argument("--out", type=Path, default=ROOT / "dist", help="output folder (default: dist)")
    commands.add_parser("validate", help="check the structure of every quiz file")
    verify_cmd = commands.add_parser("verify", help="run Python snippets and check the answers")
    verify_cmd.add_argument("subject", nargs="?", help="only this subject, e.g. python-pandas")
    args = parser.parse_args(argv)

    try:
        if args.command in (None, "serve"):
            return serve(getattr(args, "port", 8000), not getattr(args, "no_open", False))
        if args.command == "build":
            out = build(args.out)
            print(f"Wrote {out} ({out.stat().st_size // 1024} KB). Open it in a browser or host it anywhere.")
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
