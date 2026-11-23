# Contributing

How to add questions and subjects, and how the quiz files are checked. For running and using
the quiz, see the [README](README.md).

## Adding questions and subjects

Every folder under `quizzes/` that contains a `quiz.json` is a subject. The folders above it
are just for organizing:

```
quizzes/
└── python/
    └── pandas/
        ├── quiz.json                      the subject
        ├── 01-series-and-dataframes.json  one file per topic, shown in file-name order
        ├── 02-selecting-data.json
        └── ...
```

To add a subject, say SQL, create `quizzes/sql/postgres/quiz.json` plus a topic file, run
`python quiz.py validate`, and reload the page.

### quiz.json

```json
{
  "title": "Pandas",
  "category": "Python",
  "badge": "pd",
  "language": "python",
  "description": "Read pandas code and predict the result, or pick the call that does the job.",
  "note": "Every snippet assumes `import pandas as pd` and `import numpy as np`.",
  "prelude": ["import pandas as pd", "import numpy as np"]
}
```

| Field | | |
| --- | --- | --- |
| `title`, `category` | required | Subjects are grouped under their category on the home page. |
| `badge` | optional | Short text on the subject's tile, such as the import alias `pd`. |
| `language` | optional | Syntax highlighting: `python` or `sql`. Other values show plain code. |
| `description`, `note` | optional | Shown on the subject page. `note` is a good place for assumptions. |
| `prelude` | optional | Code that `verify` runs before every snippet. It isn't shown in questions. |

### Topic files

```json
{
  "topic": "GroupBy and aggregation",
  "questions": [
    {
      "id": "groupby-sum-dict",
      "difficulty": "easy",
      "question": "What does this print?",
      "code": [
        "df = pd.DataFrame({'k': ['a', 'b', 'a'], 'v': [1, 2, 3]})",
        "print(df.groupby('k')['v'].sum().to_dict())"
      ],
      "options": ["`{'a': 4, 'b': 2}`", "`{'a': 1, 'b': 2}`", "`{'a': 3, 'b': 2}`"],
      "answer": 0,
      "explanation": "Rows with the same key are summed: `a` is 1 + 3 = 4 and `b` is 2.",
      "check": "output"
    }
  ]
}
```

| Field | | |
| --- | --- | --- |
| `id` | required | Lowercase words joined by hyphens, unique within the subject. Progress is saved per id, so keep it stable. |
| `difficulty` | required | `easy`, `medium` or `hard`. |
| `question`, `explanation` | required | Text with `` `code` `` and `**bold**`. Explanations can also have paragraphs (blank lines) and fenced code blocks. |
| `code` | optional | The snippet, as a string or a list of lines. |
| `options` | required | 2 to 6 answers. An option containing a line break is shown as preformatted text, which suits printed DataFrames. |
| `answer` | required | Index of the correct option. The app shuffles options, so it can always be `0`. |
| `check` | optional | How `verify` tests the question; see below. |
| `expect` | optional | With `"check": "options"`: a Python expression the answer must equal. |
| `shuffle` | optional | `false` keeps the options in file order. |

### Checked answers

`python quiz.py verify` runs the questions of Python subjects that have a `check`:

- `"check": "output"` runs `code`. What it prints, or the name of the exception it raises, must
  equal the correct option (backticks removed), and must not equal any other option.
- `"check": "options"` runs `code` as setup, then evaluates each option as a Python expression.
  The answer must run, and every other option must raise or return something different.

Either check also fails when the answer triggers a `DeprecationWarning` or `FutureWarning`, so
the quiz doesn't teach syntax that's on its way out. Questions without a `check` (concepts,
and file or database I/O) are validated for structure only, so review them by hand.

## Commands

| Command | |
| --- | --- |
| `python quiz.py` | Serve the app on port 8000 (or the next free one). Add `serve --port 9000 --no-open` to change that. |
| `python quiz.py build [--out DIR]` | Write the single-file app to `dist/index.html`. |
| `python quiz.py validate` | Check every quiz file's structure: required fields, unique ids, valid answer indexes. |
| `python quiz.py verify [SUBJECT]` | Run the checked questions. Needs `pip install -r requirements-dev.txt`. |
| `python -m unittest discover -s tests` | Tests for `quiz.py`. |

GitHub Actions runs all of these on every push (`.github/workflows/ci.yml`).

## Library versions

The checked answers are verified against pandas 3.1 and scikit-learn 1.9. After upgrading a
library, run `python quiz.py verify` to see which answers changed.

## Layout

```
quiz.py              serve, build, validate and verify (standard library only)
app/                 the web app: index.html, styles.css, app.js (no dependencies)
quizzes/             the questions
tests/test_quiz.py   unit tests for quiz.py
```
