"""Tests for quiz.py. Run with: python -m unittest discover -s tests"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quiz  # noqa: E402


def question(**changes):
    q = {
        "id": "sample",
        "difficulty": "easy",
        "question": "What does this print?",
        "code": ["print(1 + 1)"],
        "options": ["`2`", "`11`"],
        "answer": 0,
        "explanation": "Integers add.",
        "check": "output",
    }
    q.update(changes)
    return q


class CodeSpanTest(unittest.TestCase):
    def test_single_span(self):
        self.assertEqual(quiz.code_span("`df.head()`"), "df.head()")

    def test_double_backticks_allow_backticks_inside(self):
        self.assertEqual(quiz.code_span("`` df.query('`a b` > 1') ``"), "df.query('`a b` > 1')")

    def test_prose_and_several_spans_are_not_one_span(self):
        self.assertIsNone(quiz.code_span("Raises `KeyError`"))
        self.assertIsNone(quiz.code_span("`a` or `b`"))
        self.assertIsNone(quiz.code_span("plain text"))


class QuestionProblemsTest(unittest.TestCase):
    def test_valid_question(self):
        self.assertEqual(quiz.question_problems(question()), [])

    def test_reports_each_problem(self):
        problems = quiz.question_problems(question(difficulty="trivial", answer=5, typo=True))
        self.assertIn('unknown key "typo"', problems)
        self.assertTrue(any('"difficulty"' in p for p in problems))
        self.assertTrue(any('"answer"' in p for p in problems))

    def test_duplicate_options(self):
        self.assertIn("options must all be different", quiz.question_problems(question(options=["`2`", "`2`"])))

    def test_options_check_needs_code_span_options(self):
        problems = quiz.question_problems(question(check="options", options=["`sorted(x)`", "sort it"]))
        self.assertTrue(any("single `code` span" in p for p in problems))

    def test_check_needs_code(self):
        q = question()
        del q["code"]
        self.assertIn('"check" needs "code" to run', quiz.question_problems(q))


class ChecksTest(unittest.TestCase):
    def test_output_check(self):
        self.assertEqual(quiz.check_output(question(), ""), [])
        problems = quiz.check_output(question(answer=1), "")
        self.assertTrue(any("but the answer is '11'" in p for p in problems))

    def test_output_check_compares_exception_names(self):
        q = question(code="{}['missing']", options=["`KeyError`", "`None`"])
        self.assertEqual(quiz.check_output(q, ""), [])

    def test_output_check_flags_options_that_also_match(self):
        q = question(options=["`2`", "2"])
        self.assertIn("option 1 matches the output too", quiz.check_output(q, ""))

    def test_options_check_flags_a_second_working_option(self):
        q = question(check="options", code="x = [3, 1, 2]",
                     options=["`sorted(x)`", "`list(sorted(x))`", "`x.sort()`", "`sorted(y)`"])
        self.assertEqual(quiz.check_options(q, ""), ["option 1 gives the same result as the answer"])

    def test_options_check_with_expect(self):
        q = question(check="options", code="x = [3, 1, 2]", options=["`sorted(x)`", "`x`"], expect="[1, 2, 3]")
        self.assertEqual(quiz.check_options(q, ""), [])
        q["expect"] = "[3, 2, 1]"
        self.assertEqual(quiz.check_options(q, ""), ['the answer does not equal "expect"'])

    def test_deprecated_answers_fail(self):
        q = question(code="import warnings\nwarnings.warn('old', FutureWarning)\nprint(2)")
        self.assertTrue(any("deprecated" in p for p in quiz.check_output(q, "")))


class RepositoryTest(unittest.TestCase):
    def test_quiz_files_are_valid(self):
        self.assertEqual(quiz.validate(quiz.load_subjects()), [])

    def test_build_inlines_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = quiz.build(Path(tmp)).read_text(encoding="utf-8")
        self.assertNotIn('src="app.js"', html)
        self.assertNotIn('href="styles.css"', html)
        marker = '<script id="quiz-data" type="application/json">'
        start = html.index(marker) + len(marker)
        data = json.loads(html[start:html.index("</script>", start)])
        self.assertTrue(data["subjects"])
        question_keys = {k for s in data["subjects"] for t in s["topics"] for q in t["questions"] for k in q}
        self.assertNotIn("check", question_keys)


if __name__ == "__main__":
    unittest.main()
