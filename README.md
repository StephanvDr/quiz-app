# Code Quiz

Private app for training skills within different domains.

Every round is multiple choice, and every answer comes with an explanation. The app keeps
track of what you've mastered and what you missed, per subject.

| Subject | Language | Questions | Topics |
| --- | --- | ---: | ---: |
| [Pandas](#pandas) | English | 183 | 14 |
| [BI Drill-down](#bi-drill-down) | Dutch | 144 | 7 |
| [Contoso LU1 deel 2](#contoso-lu1-deel-2) | Dutch | 169 | 11 |

### Pandas

Syntax drills for data engineering and LLM work, in `quizzes/python/pandas`. Each question
shows a snippet and asks what it prints, or which call does the job. 172 of the questions
are checked by actually running the code, so the marked answers are what pandas really does.

| Topic | Questions |
| --- | ---: |
| Series and DataFrames | 13 |
| Selecting with `[]`, `loc` and `iloc` | 13 |
| Filtering rows | 13 |
| Creating and changing columns | 13 |
| Missing values and duplicates | 13 |
| Sorting and ranking | 10 |
| GroupBy and aggregation | 15 |
| Merging and concatenating | 13 |
| Reshaping: pivot, melt and stack | 12 |
| Text with the `.str` accessor | 12 |
| Dates and time series | 15 |
| Reading and writing files | 13 |
| Dtypes, memory and performance | 14 |
| JSON and text for LLM pipelines | 14 |

### BI Drill-down

Business intelligence concepts in Dutch, in `quizzes/bi/drilldown`: multiple choice and
true/false, with many examples set in a hotel chain.

| Onderwerp | Vragen |
| --- | ---: |
| Maturitymodel | 22 |
| OLTP vs OLAP | 22 |
| Grain & feiten | 20 |
| Standaardisatie | 17 |
| Star & snowflake | 26 |
| Self-service BI | 17 |
| DWH & ETL | 20 |

### Contoso LU1 deel 2

The logic and syntax of the Contoso notebook (LU1 Data Engineering, part 2) in Dutch, in
`quizzes/bi/contoso-lu1`: the ETL that builds the star schema in pandas, the validation, the
ten user-story charts and the conclusions. Questions quote the notebook's code; where a
snippet needs the real Contoso data, it runs on a small example instead. 63 of the questions
are checked by running the code, on pandas 2.2 as well as 3.0.

| Onderwerp | Vragen |
| --- | ---: |
| Instellingen en hulpfuncties | 14 |
| Extract: data laden | 17 |
| Data verkennen | 12 |
| Transform: datum, kanaal, geografie en winkel | 17 |
| Transform: product, promotie en land | 19 |
| Transform: FactSales | 15 |
| Validatie | 11 |
| star(), US01 en US02 | 15 |
| US03, US04 en US05 | 15 |
| Store Manager: US06 t/m US10 | 20 |
| Conclusies | 14 |

## Run it

```bash
python quiz.py
```

This serves the app at <http://localhost:8000> and opens your browser. It needs Python 3.10
or newer and nothing else: no packages, no Node, no build step. Edits to the quiz files show
up when you reload the page.

To share the quiz without Python, build a single self-contained HTML file:

```bash
python quiz.py build
```

`dist/index.html` holds the app and every question. Open it straight from disk, send it to
someone, or host it on any static host (GitHub Pages, Netlify, S3).

## Desktop app

On Windows, install Code Quiz with `CodeQuiz-Setup-1.0.0.exe`. Get it from the repository's
[Releases](../../releases) page, from the artifacts of a run of the "Windows installer"
workflow on the Actions tab, or [build it yourself](#building-the-installer).

- It installs for your user only (no administrator rights) into
  `%LOCALAPPDATA%\Programs\Code Quiz`, with a Start menu shortcut, an optional desktop
  shortcut, and its own copy of Python. A Python you already have is left alone.
- The installer isn't code-signed, so SmartScreen may say "Windows protected your PC". Click
  **More info**, then **Run anyway**.
- Code Quiz opens in its own Edge (or Chrome) app window. It quietly stops 15 minutes after
  you close that window.
- Your progress is saved in that window, separately from the progress of `python quiz.py` in
  a normal browser tab.
- Modules you add and your settings are kept in `%APPDATA%\CodeQuiz`. Updates keep them, and
  when you uninstall (Settings > Apps > Code Quiz) you're asked whether to delete them.

On macOS and Linux, run the same desktop app with `python3 quiz.py app`. It keeps its data in
`~/Library/Application Support/CodeQuiz` or `~/.local/share/code-quiz`.

### Modules

Every subject is a module. The desktop app's **Modules** page (the last tile on the home
page, "Add or update subjects") shows where each one comes from and adds new ones:

- **Built in:** the subjects in `quizzes/` when the installer was built.
- **From a file:** a `.quiz` module file. Drop it anywhere on the window, choose it on the
  Modules page, double-click it (Windows), or copy it into the modules folder. Make one with
  `python quiz.py pack python-pandas`, which writes `dist/modules/python-pandas.quiz`;
  without a subject id it packs every subject.
- **From GitHub:** see below.

A module with the same id as a built-in subject replaces it. Remove the module and the
built-in version comes back.

### GitHub library

The Modules page also reads the `quizzes/` folder of a GitHub repository, by default
`StephanvDr/quiz-app` on `main`, and lists every subject in it as **Install**, **Update** or
**Up to date**. So the workflow for new questions is: add them to the repository, push, then
click **Save and check** on the Modules page and update the subject.

The repository and branch can be changed there. A private repository needs a token:

1. On GitHub, open Settings > Developer settings > Personal access tokens > Fine-grained
   tokens, and generate a new token.
2. Under Repository access, choose **Only select repositories** and pick the repository.
3. Under Permissions > Repository permissions, set **Contents** to **Read-only**.
4. Paste the token in the Access token field on the Modules page and click **Save and check**.

The token is saved in `settings.json` in the data folder, is only sent to `api.github.com`,
and is never shown again. Without a token, GitHub allows 60 checks an hour per network.

### Module file format

A module file is one subject in a single JSON file: the `quiz.json` as `subject`, and each
topic file as an entry of `topics`, with its file name in `file` (that sets the order).

```json
{
  "format": "code-quiz-module",
  "version": 1,
  "id": "sql-basics",
  "subject": { "title": "SQL basics", "category": "SQL", "language": "sql" },
  "topics": [
    { "file": "01-select", "topic": "SELECT", "questions": [] }
  ]
}
```

The app checks a module like `python quiz.py validate` checks the quiz folders, and says what
is wrong when it can't add one.

## Using the quiz

- Pick the topics, the round size (10, 20, 30 or all), a difficulty (for subjects that have
  levels), and which questions to draw from: all of them, ones you haven't seen yet, or ones
  you got wrong last time.
- Answer options are shuffled every time. Press `1`–`6` or `A`–`F` to answer and `Enter` to
  continue. "I don't know, show me" reveals the answer and counts it as missed.
- The results page breaks the score down by topic, lists every miss with its explanation, and
  can start a new round with just the questions you missed.
- Progress is stored in your browser's `localStorage`, per subject. Nothing is sent anywhere.

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
| `language` | optional | Syntax highlighting: `python` or `sql`. Other values show plain code; leave it out for subjects without code. |
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
| `difficulty` | optional | `easy`, `medium` or `hard`. The difficulty filter only appears for subjects that use it. |
| `question`, `explanation` | required | Text with `` `code` `` and `**bold**`. Explanations can also have paragraphs (blank lines) and fenced code blocks. |
| `code` | optional | The snippet, as a string or a list of lines. |
| `options` | required | 2 to 6 answers. An option containing a line break is shown as preformatted text, which suits printed DataFrames. |
| `answer` | required | Index of the correct option. The app shuffles options, so it can always be `0`. |
| `check` | optional | How `verify` tests the question; see below. |
| `expect` | optional | With `"check": "options"`: a Python expression the answer must equal. |
| `shuffle` | optional | `false` keeps the options in file order, e.g. `["True", "False"]` for true/false questions. |

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
| `python quiz.py app [--import FILE]` | Run the desktop app, adding a module file first if given. |
| `python quiz.py quit` | Stop a running desktop app. |
| `python quiz.py pack [SUBJECT ...] [--out DIR]` | Write subjects as `.quiz` module files to `dist/modules/`. |
| `python installer/build.py` | Build the Windows installer; see below. |
| `python -m unittest discover -s tests` | Tests for `quiz.py`. |

GitHub Actions runs the checks on every push (`.github/workflows/ci.yml`).

## Building the installer

```bash
python installer/build.py
```

This writes `dist/CodeQuiz-Setup-<version>.exe` and works on Windows, Linux or macOS with
[NSIS](https://nsis.sourceforge.io) installed (`apt install nsis` or `brew install makensis`).
It downloads Python 3.13 for Windows once (the official `python` package on NuGet, checked
against a pinned SHA-512), trims what the app doesn't use, and packs it with the app and the
subjects in `quizzes/`. The installer script is `installer/codequiz.nsi`.

To publish a release, raise `VERSION` in `quiz.py`, then push a matching tag:

```bash
git tag v1.0.1
```

```bash
git push origin v1.0.1
```

The "Windows installer" workflow (`.github/workflows/installer.yml`) builds the installer and
attaches it to a GitHub release for that tag.

## pandas versions

Answers are verified against pandas 3.0. Almost all of them are the same on pandas 2.x. The
few that cover pandas 3 changes (the `str` dtype, Copy-on-Write, removed APIs and the new
frequency aliases) say "In pandas 3" and explain the 2.x behavior. After a pandas upgrade,
run `python quiz.py verify` to see which answers changed.

## Layout

```
quiz.py              serve, build, validate, verify, pack and the desktop app (standard library only)
app/                 the web app: index.html, styles.css, app.js, icon.svg (no dependencies)
quizzes/             the questions
installer/           build.py, the NSIS script, the icon and the setup wizard image
tests/               unit tests for quiz.py and the desktop app
```
