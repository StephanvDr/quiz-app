"""Tests for modules, the GitHub library and the desktop app's server.

Run with: python -m unittest discover -s tests
"""

import base64
import contextlib
import io
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quiz  # noqa: E402


def repo_files() -> dict[str, bytes]:
    """This repository's quiz files, as GitHub would hold them, plus files to ignore."""
    files = {p.relative_to(quiz.ROOT).as_posix(): p.read_bytes() for p in quiz.QUIZ_DIR.rglob("*.json")}
    files["README.md"] = b"# not a quiz\n"
    files["quizzes/notes.json"] = b"{}"  # not inside a subject folder
    return files


class FakeGitHub(ThreadingHTTPServer):
    """Answers the three GitHub calls the library makes, from files in memory."""

    daemon_threads = True

    def __init__(self, files, repo="me/quizzes", branch="main", private=False, token="secret-token"):
        super().__init__(("127.0.0.1", 0), FakeGitHubHandler)
        self.files, self.repo, self.branch, self.private, self.token = files, repo, branch, private, token
        self.requests = []
        self.rate_limited = False

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"


class FakeGitHubHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        gh = self.server
        auth = self.headers.get("Authorization")
        path = unquote(urlsplit(self.path).path)
        gh.requests.append((path, auth))
        if gh.rate_limited:
            return self.send(403, {"message": "API rate limit exceeded"}, {"X-RateLimit-Remaining": "0"})
        allowed = not gh.private or auth == f"Bearer {gh.token}"
        api = f"/repos/{gh.repo}/git/"
        if path == f"{api}trees/{gh.branch}" and allowed:
            folders = {p.rsplit("/", 1)[0] for p in gh.files if "/" in p}
            tree = [{"path": f, "type": "tree", "sha": "0" * 40, "mode": "040000"} for f in sorted(folders)]
            tree += [{"path": p, "type": "blob", "sha": quiz.git_blob_sha(c), "mode": "100644", "size": len(c)}
                     for p, c in gh.files.items()]
            return self.send(200, {"sha": "1" * 40, "tree": tree, "truncated": False})
        if path.startswith(f"{api}blobs/") and allowed:
            sha = path.rsplit("/", 1)[1]
            content = next((c for c in gh.files.values() if quiz.git_blob_sha(c) == sha), None)
            if content is not None:
                # GitHub wraps the base64 content in lines, like encodebytes does
                return self.send(200, {"sha": sha, "size": len(content), "encoding": "base64",
                                       "content": base64.encodebytes(content).decode()})
        raw = f"/{gh.repo}/refs/heads/{gh.branch}/"
        if path.startswith(raw) and not gh.private and path[len(raw):] in gh.files:
            return self.send(200, gh.files[path[len(raw):]], raw=True)
        return self.send(404, {"message": "Not Found"})

    def send(self, status, data, headers=None, raw=False):
        body = data if raw else json.dumps(data).encode()
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def serve_in_background(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


class GitHubCase(unittest.TestCase):
    """Points the library at a fake GitHub for the duration of a test."""

    private = False

    def setUp(self):
        self.files = repo_files()
        self.github = FakeGitHub(self.files, private=self.private)
        serve_in_background(self.github)
        self.saved_urls = quiz.GITHUB_API, quiz.GITHUB_RAW
        quiz.GITHUB_API = quiz.GITHUB_RAW = self.github.url

    def tearDown(self):
        quiz.GITHUB_API, quiz.GITHUB_RAW = self.saved_urls
        self.github.shutdown()
        self.github.server_close()


class ModulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.modules = self.home / "modules"
        self.pandas = next(s for s in quiz.load_subjects() if s["id"] == "python-pandas")

    def tearDown(self):
        self.tmp.cleanup()

    def test_pack_and_install_round_trip(self):
        module = quiz.pack_subject(self.pandas)
        module["id"] = "pandas-copy"
        result = quiz.install_module(module, self.modules)
        self.assertEqual(result, {"id": "pandas-copy", "title": "Pandas", "questions": 183})
        added, problems = quiz.load_modules(self.modules)
        self.assertEqual(problems, [])
        self.assertEqual([s["id"] for s in added], ["pandas-copy"])
        self.assertEqual(added[0]["source"], {"kind": "file"})

    def test_added_module_replaces_built_in_subject(self):
        module = quiz.pack_subject(self.pandas)
        module["subject"] = {**module["subject"], "title": "Pandas (updated)"}
        quiz.install_module(module, self.modules)
        subjects = {s["id"]: s for s in quiz.payload(self.home)["subjects"]}
        self.assertEqual(subjects["python-pandas"]["title"], "Pandas (updated)")
        self.assertEqual(subjects["python-pandas"]["source"], {"kind": "file", "replaces": "built-in"})

    def test_broken_files_are_reported_not_fatal(self):
        self.modules.mkdir()
        (self.modules / "broken.quiz").write_text("{ not json", encoding="utf-8")
        (self.modules / "wrong.quiz").write_text(json.dumps({"format": "something-else"}), encoding="utf-8")
        copy = quiz.pack_subject(self.pandas)
        (self.modules / "a.quiz").write_text(json.dumps(copy), encoding="utf-8")
        (self.modules / "b.quiz").write_text(json.dumps(copy), encoding="utf-8")  # same id again
        data = quiz.payload(self.home)
        self.assertIn("python-pandas", [s["id"] for s in data["subjects"]])
        problems = {p["file"]: p["errors"] for p in data["problems"]}
        self.assertEqual(sorted(problems), ["b.quiz", "broken.quiz", "wrong.quiz"])
        self.assertIn("also used by a.quiz", problems["b.quiz"][0])

    def test_install_rejects_bad_modules(self):
        module = quiz.pack_subject(self.pandas)
        for bad_id in ("../escape", "Has Caps", ""):
            with self.assertRaises(quiz.QuizError):
                quiz.install_module({**module, "id": bad_id}, self.modules)
        broken = json.loads(json.dumps(module))
        broken["topics"][0]["questions"][0]["answer"] = 99
        with self.assertRaisesRegex(quiz.QuizError, '"answer" must be the index'):
            quiz.install_module(broken, self.modules)
        with self.assertRaisesRegex(quiz.QuizError, "not a Code Quiz module"):
            quiz.install_module({"title": "a plain quiz.json"}, self.modules)
        self.assertFalse(self.modules.exists() and any(self.modules.iterdir()))

    def test_remove_only_added_modules(self):
        quiz.install_module(quiz.pack_subject(self.pandas), self.modules)
        quiz.remove_module("python-pandas", self.modules)
        self.assertEqual(list(self.modules.iterdir()), [])
        for subject_id in ("python-pandas", "../quiz"):
            with self.assertRaises(quiz.QuizError):
                quiz.remove_module(subject_id, self.modules)

    def test_git_blob_sha_matches_git(self):
        # `printf 'hello\n' | git hash-object --stdin`
        self.assertEqual(quiz.git_blob_sha(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")
        self.assertEqual(quiz.git_blob_sha(b"hello\r\n"), quiz.git_blob_sha(b"hello\n"))

    def test_settings_keep_the_token_private(self):
        self.assertEqual(quiz.load_settings(self.home)["library"], {**quiz.DEFAULT_LIBRARY, "token": ""})
        quiz.save_settings(self.home, {"library": {"repo": "me/quizzes", "branch": "main", "token": "abc"}})
        public = quiz.public_library(quiz.load_settings(self.home))
        self.assertEqual(public, {"repo": "me/quizzes", "branch": "main", "hasToken": True})


class LibraryTest(GitHubCase):
    def test_catalog_lists_every_subject_folder(self):
        catalog = {e["id"]: e for e in quiz.Library("me/quizzes", "main").catalog()}
        self.assertEqual(sorted(catalog), sorted(s["id"] for s in quiz.load_subjects()))
        self.assertEqual(catalog["python-pandas"]["title"], "Pandas")
        self.assertEqual(catalog["python-pandas"]["topics"], 14)
        built_in = {s["id"]: quiz.local_revision(s) for s in quiz.load_subjects()}
        self.assertEqual({k: v["revision"] for k, v in catalog.items()}, built_in)

    def test_public_repository_files_come_from_raw_urls(self):
        quiz.Library("me/quizzes", "main").catalog()
        paths = [path for path, _ in self.github.requests]
        self.assertTrue(paths[0].startswith("/repos/me/quizzes/git/trees/main"))
        self.assertTrue(all(p.startswith("/me/quizzes/refs/heads/main/quizzes/") for p in paths[1:]))

    def test_module_is_a_valid_module(self):
        module = quiz.Library("me/quizzes", "main").module("bi-drilldown")
        subject = quiz.checked_module(module, Path("bi-drilldown.quiz"))
        self.assertEqual(sum(len(t["data"]["questions"]) for t in subject["topics"]), 144)
        self.assertEqual(module["source"]["kind"], "github")
        self.assertEqual(module["source"]["repo"], "me/quizzes")

    def test_unknown_subject_or_repository(self):
        with self.assertRaisesRegex(quiz.QuizError, "not in me/quizzes"):
            quiz.Library("me/quizzes", "main").module("does-not-exist")
        with self.assertRaisesRegex(quiz.QuizError, "couldn't find me/other"):
            quiz.Library("me/other", "main").catalog()

    def test_rate_limit_message(self):
        self.github.rate_limited = True
        with self.assertRaisesRegex(quiz.QuizError, "hourly limit"):
            quiz.Library("me/quizzes", "main").catalog()

    def test_unreachable_github(self):
        quiz.GITHUB_API = "http://127.0.0.1:9"
        with self.assertRaisesRegex(quiz.QuizError, "Couldn't reach GitHub"):
            quiz.Library("me/quizzes", "main").catalog()


class PrivateLibraryTest(GitHubCase):
    private = True

    def test_private_repository_needs_the_token(self):
        with self.assertRaisesRegex(quiz.QuizError, "save a token"):
            quiz.Library("me/quizzes", "main").catalog()
        with self.assertRaisesRegex(quiz.QuizError, "Check the name"):
            quiz.Library("me/quizzes", "main", "wrong-token").catalog()

    def test_token_reads_files_through_the_blob_api(self):
        module = quiz.Library("me/quizzes", "main", "secret-token").module("python-pandas")
        quiz.checked_module(module, Path("python-pandas.quiz"))
        self.assertTrue(all(auth == "Bearer secret-token" for _, auth in self.github.requests))
        self.assertTrue(all("/git/" in path for path, _ in self.github.requests))


class DesktopServerTest(GitHubCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        quiz.save_settings(self.home, {"library": {"repo": "me/quizzes", "branch": "main", "token": ""}})
        self.server = quiz.DesktopServer(("127.0.0.1", 0), self.home)
        serve_in_background(self.server)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()
        super().tearDown()

    def call(self, method, path, body=None, headers=None):
        headers = {"X-Code-Quiz": "1", **(headers or {})}
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.url + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_payload_describes_the_desktop(self):
        status, data = self.call("GET", "quizzes.json")
        self.assertEqual(status, 200)
        self.assertEqual(data["desktop"]["library"], {"repo": "me/quizzes", "branch": "main", "hasToken": False})
        self.assertEqual(data["desktop"]["modulesDir"], str(self.home / "modules"))

    def test_changes_need_the_app_header_and_host(self):
        module = quiz.pack_subject(quiz.load_subjects()[0])
        self.assertEqual(self.call("POST", "api/modules", module, {"X-Code-Quiz": ""})[0], 403)
        self.assertEqual(self.call("GET", "api/ping", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.call("POST", "api/modules", module)[0], 200)

    def test_library_states_follow_installs_and_changes(self):
        states = lambda: {e["id"]: e["state"] for e in self.call("GET", "api/library")[1]["subjects"]}
        self.assertEqual(set(states().values()), {"current"})  # identical to the built-in subjects

        meta = "quizzes/python/pandas/quiz.json"
        self.files[meta] = self.files[meta].replace(b'"Pandas"', b'"Pandas 2"')
        self.files["quizzes/sql/basics/quiz.json"] = json.dumps({"title": "SQL", "category": "SQL"}).encode()
        self.files["quizzes/sql/basics/01-select.json"] = json.dumps({"topic": "SELECT", "questions": [{
            "id": "select-star", "question": "What does `SELECT *` return?", "options": ["Every column", "Nothing"],
            "answer": 0, "explanation": "The star means all columns."}]}).encode()
        expected = {s["id"]: "current" for s in quiz.load_subjects()}
        expected.update({"python-pandas": "update", "sql-basics": "new"})
        self.assertEqual(states(), expected)

        for subject_id in ("python-pandas", "sql-basics"):
            status, result = self.call("POST", "api/library/install", {"id": subject_id})
            self.assertEqual(status, 200, result)
        self.assertEqual(set(states().values()), {"current"})
        subjects = {s["id"]: s for s in self.call("GET", "quizzes.json")[1]["subjects"]}
        self.assertEqual(subjects["python-pandas"]["title"], "Pandas 2")
        self.assertEqual(subjects["python-pandas"]["source"]["replaces"], "built-in")
        self.assertEqual(subjects["sql-basics"]["source"]["kind"], "github")

    def test_settings_validate_and_hide_the_token(self):
        status, data = self.call("POST", "api/settings", {"repo": "not a repo"})
        self.assertEqual(status, 400)
        status, data = self.call("POST", "api/settings", {"repo": "me/quizzes", "branch": "dev", "token": " abc "})
        self.assertEqual(data["library"], {"repo": "me/quizzes", "branch": "dev", "hasToken": True})
        self.assertEqual(quiz.load_settings(self.home)["library"]["token"], "abc")
        status, data = self.call("POST", "api/settings", {"clearToken": True})
        self.assertFalse(data["library"]["hasToken"])

    def test_finds_and_stops_a_running_app(self):
        port = self.server.server_address[1]
        self.assertEqual(quiz.find_instance(port), self.url)
        upload = Path(self.tmp.name) / "drop.quiz"
        upload.write_text(json.dumps(quiz.pack_subject(quiz.load_subjects()[0])), encoding="utf-8")
        self.assertTrue(quiz.send_module(self.url, upload).startswith("Added "))
        with contextlib.redirect_stdout(io.StringIO()):
            quiz.quit_app(port)  # returns once the app has stopped answering
        self.assertFalse(quiz.is_running(self.url))
        self.server.server_close()
        self.server = quiz.DesktopServer(("127.0.0.1", 0), self.home)  # a running server for tearDown to stop
        serve_in_background(self.server)


class HalfReplyHandler(BaseHTTPRequestHandler):
    """Promises 40 bytes and sends one, like an app that stops mid-reply."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "40")
        self.end_headers()
        self.wfile.write(b"{")

    def log_message(self, *args):
        pass


class InstanceTest(unittest.TestCase):
    def test_a_reply_cut_short_means_not_running(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), HalfReplyHandler)
        serve_in_background(server)
        try:
            self.assertFalse(quiz.is_running(f"http://127.0.0.1:{server.server_address[1]}/"))
        finally:
            server.shutdown()
            server.server_close()


class IdleTest(unittest.TestCase):
    def test_server_stops_when_the_window_is_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = quiz.DesktopServer(("127.0.0.1", 0), Path(tmp))
            threading.Thread(target=quiz.stop_when_idle, args=(server, 1), daemon=True).start()
            started = time.monotonic()
            server.serve_forever()  # returns once the idle watcher shuts it down
            server.server_close()
            self.assertLess(time.monotonic() - started, 10)


if __name__ == "__main__":
    unittest.main()
