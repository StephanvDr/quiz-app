# Code Quiz

A multiple-choice quiz app for practising data, BI and machine-learning skills. Each
question explains its answer, whether you got it right or not, so you learn from every miss.
The app keeps track of what you've mastered and what you missed, per subject.

## Subjects

| Subject | Language | Questions | Topics |
| --- | --- | ---: | ---: |
| [Pandas](#pandas) | English | 183 | 14 |
| [ML pitfalls](#ml-pitfalls) | English | 104 | 7 |
| [BI Drill-down](#bi-drill-down) | Dutch | 144 | 7 |
| [Contoso LU1 deel 2](#contoso-lu1-deel-2) | Dutch | 169 | 11 |

### Pandas

Syntax drills for data engineering and LLM work. Read a snippet and predict what it prints,
or pick the call that does the job. The code answers are checked by running them on pandas
3.1; where pandas 2.x behaves differently, the explanation says so.

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

### ML pitfalls

Supervised-learning terminology and common mistakes, with Dutch terms where the course
slides use them. The scikit-learn code questions are checked by running them.

| Topic | Questions |
| --- | ---: |
| Workflow and basics | 14 |
| Algorithms | 14 |
| Pitfalls 1: data quality and preprocessing | 16 |
| Pitfalls 2: model choice and training | 15 |
| Pitfalls 3a: classification metrics | 15 |
| Pitfalls 3b: regression metrics and validation | 17 |
| Pitfalls 4: implementation in practice | 13 |

### BI Drill-down

Business intelligence concepts in Dutch: multiple choice and true/false, with many examples
set in a hotel chain.

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

The logic and syntax of the Contoso notebook (LU1 Data Engineering, part 2) in Dutch: the
ETL that builds the star schema in pandas, the validation, the ten user-story charts and the
conclusions. Questions quote the notebook's code; where a snippet needs the real Contoso
data, it runs on a small example instead.

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

## Install on Windows

Install Code Quiz with `CodeQuiz-Setup-<version>.exe` from the repository's
[Releases](../../releases) page.

- It installs for your user only (no administrator rights needed), with a Start menu
  shortcut, an optional desktop shortcut and its own copy of Python. A Python you already
  have is left alone.
- The installer isn't code-signed, so SmartScreen may say "Windows protected your PC". Click
  **More info**, then **Run anyway**.
- Code Quiz opens in its own Edge (or Chrome) app window. It quietly stops 15 minutes after
  you close that window.
- Subjects you add and your settings are kept in `%APPDATA%\CodeQuiz`. Updates keep them,
  and when you uninstall (Settings > Apps > Code Quiz) you're asked whether to delete them.

## Run it with Python

On any system with Python 3.10 or newer (nothing else to install), run this in the project
folder:

```bash
python quiz.py
```

The quiz opens in a browser tab at <http://localhost:8000>. Press Ctrl+C in the terminal to
stop it.

To run it as a desktop app window instead, with the Modules page described below:

```bash
python3 quiz.py app
```

It keeps its data in `~/Library/Application Support/CodeQuiz` on macOS or
`~/.local/share/code-quiz` on Linux.

### Without Python

Build a single HTML file that holds the whole app and every question:

```bash
python quiz.py build
```

Open `dist/index.html` straight from disk, send it to someone, or put it on any static host
such as GitHub Pages.

## How it works

- **Pick a round**: choose topics, a round size (10, 20, 30 or all), a difficulty (for
  subjects that have levels), and which questions to draw from: all, ones you haven't seen
  yet, or ones you got wrong last time.
- **Answer**: click an option, or press `1`–`6` or `A`–`F`, then `Enter` to continue.
  Options are shuffled every time. "I don't know, show me" reveals the answer and counts it
  as missed.
- **Review**: the results page shows your score per topic, lists every miss with its
  explanation, and can start a new round with just the questions you missed.
- **Progress** is saved in the browser or app window you use, per subject. Nothing is sent
  anywhere. The desktop app and a normal browser tab keep separate progress.

## Adding and updating subjects

In the desktop app, the **Modules** page (the last tile on the home page, "Add or update
subjects") shows where each subject comes from and adds new ones:

- **Built in**: the subjects that came with the app.
- **From a file**: a `.quiz` module file. Drop it anywhere on the window, choose it on the
  Modules page, or double-click it (Windows).
- **From GitHub**: the Modules page reads the subjects in a GitHub repository, by default
  `StephanvDr/quiz-app` on `main`, and lists each one as **Install**, **Update** or
  **Up to date**. Click **Save and check** to look for new questions.

A module with the same name as a built-in subject replaces it. Remove the module and the
built-in version comes back.

### Using a private repository

The repository and branch can be changed on the Modules page. A private repository needs a
token:

1. On GitHub, open Settings > Developer settings > Personal access tokens > Fine-grained
   tokens, and generate a new token.
2. Under Repository access, choose **Only select repositories** and pick the repository.
3. Under Permissions > Repository permissions, set **Contents** to **Read-only**.
4. Paste the token in the Access token field on the Modules page and click **Save and check**.

The token is saved on your computer, is only sent to GitHub, and is never shown again.
Without a token, GitHub allows 60 checks an hour per network.

## Writing questions

Want to write questions, make a module file or build the installer? See
[CONTRIBUTING.md](CONTRIBUTING.md).
