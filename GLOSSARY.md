# SQL Review Agent: Requirements Handoff & Glossary

Handoff of everything agreed so far for the **Site SQL Review Agent**. Written so a developer or another AI agent (OpenCode, Claude Code, etc.) can continue without the original chat.

Status legend: ✅ done and tested · 🟡 decided, not built · ❓ open question · ⚠️ unverified assumption

---

## 1. Problem statement

**Pain point.** Site IT must execute SQL scripts that HQ provides for the site's own database. The HQ development team often sends scripts with missing, incorrect, or wrong syntax, so the site's update function fails.

**Goal.** An AI agent running on the site IT laptop that fetches each SQL script, reviews it, and reports problems to the team in MS Teams before anyone executes it.

**Constraints.**

- Database engine: **PostgreSQL**.
- **No Docker or test database** (decided). Static checks only.
- All Python dependencies must be installed and used through the project's `.venv`; do not install project dependencies into system Python.
- The deploy sheet and the SQL files are on **kdocs.cn (WPS)** and **require login**.
- Runs on the user's laptop.
- The LLM is a **local model run through OpenCode** (decided), so script content is not sent to a cloud LLM.
- Relationship checking from `schema.md` is **deferred to the next version**.

---

## 2. Scope

### MVP (this version)

1. Standard PostgreSQL syntax check ✅
2. Message locale check: every `message_key` must have a row with `message_locale = 'en_US'` ✅
3. Embedded SQL check (found from the real sample, see §6) ✅
4. Teams messages, **one per issue** 🟡
5. Agent monitoring UI (card list and card detail) 🟡
6. Review workflow (approve / edit / reject before posting) 🟡
7. Fetch from kdocs: export the sheet, select the SQL rows by deploy date (§3.1), download each SQL file 🟡 (needs a spike first)

### Next version

- Relationship check from `schema.md` (Mermaid `erDiagram`): missing parent/child rows, unknown tables or columns.
- Check `sort_column` and `result_column` values against the embedded query (same alias problem as in §6).

### Out of scope

- Docker or a live database test.
- Executing the SQL on any database.

---

## 3. End-to-end workflow

1. **Choose the deploy date.** The user types `MM.DD` (for example `10.13`). It is a required input; there is no default.
2. Open the **MES deploy sheet** on kdocs and export it to `.xlsx`.
3. **Select the deploy window:** every row above the chosen deploy separator, back to the previous deploy separator (§3.1), that has an SQL link in **column L**.
4. For each selected row, take the SR number from **column D** (a prefix from the configured list + `YYMMDD` + 3 digits), download the attached file (hover over the column L cell and click the download icon, §5), and rename it to `SQL_<SR_Number>.sql`, for example `SQL_STH260804018.sql`. If no SR number is found, use the fallback name in §3.1 rule 6.
5. Review each script (syntax, locale, embedded SQL).
6. Human review of the findings (approve / edit / reject).
7. Post **one Teams message per issue** (finding). Each message is self-contained so the stream can be collected as an issue-tracking list. A file with no issues gets one "no issues found" message. For now the destination is a **Teams channel**.

**Finding format in the Teams card** (required by the user), one block per issue:

```
<icon> <line>: <filename> - <error_title>
description
recommendation
```

Icons: ❌ error · ⚠️ warning · ℹ️ info.

**Message grouping (decided): one Teams message per issue**, not per file. For now the messages go to a **Teams channel** (decided). A later move to an issue-tracking list is set in the Workflows flow, not in code (⚠️ assumption). Proposed details:

- Each message carries the SR number, deploy date, and a stable issue ID (a hash of file + line + check title).
- The agent stores posted issue IDs in SQLite and does not re-post the same issue on a re-run.
- Send messages one at a time with a short delay, and retry on errors (⚠️ Power Automate throttling limits not verified).
- A file with no findings gets one message, `✅ <filename> - No issues found`, listing the checks that ran (decided).

### 3.1 Which SQL files to review: the deploy-date rule ✅ (resolved)

The sheet is chronological. Each deploy is **closed by a red separator row** such as `2026.10.13 9:43 package (10.13 online)`. The SQL files for a deploy are the ones in the rows **above** its separator, back to (not including) the **previous** separator.

```
[red]  2026.10.08 8:52 package (10.08 online)    <- previous deploy separator (exclusive)
       row  STH260804018 ...  [SQL]                ┐
       row  STH260804018 ...                       │ deploy window for "10.13 online"
       row  STH260804018 ...                       │ (rows to review)
       row  STH260804018 ...                       ┘
[red]  2026.10.13 9:43 package (10.13 online)    <- selected deploy separator (exclusive)
       rows below the last separator = next deploy, not scheduled yet (ignored)
```

**Rules**

1. **Find separators.** A separator row contains `(MM.DD online)`. Read the full date and time from the same text (`YYYY.MM.DD H:MM package`); use the full date, since `MM.DD` alone repeats every year. ⚠️ Separators look like merged cells, so confirm in the spike that the text exports to the first cell of the row.
2. **Window.** End = the row just above the selected separator. Start = the row just below the previous separator. If there is no previous separator, start at the first data row under the header.
3. **Candidates.** Every row in the window with a **hyperlink** in **column L** (confirmed to be a hyperlink, see §5). Rows without a link are skipped.
4. **SR number.** Search column D for a prefix from the **configuration list**, then `YYMMDD`, then a 3-digit sequence: `(?<![A-Za-z0-9])(?:STH|STP|SFQ|SWH|SXM|SBJ|SQD)\d{9}(?!\d)`. The list is the `sr_prefixes` setting in `config.yaml` (decided): `[STH, STP, SFQ, SWH, SXM, SBJ, SQD]`. The cell is multi-line text with branch paths, so match anywhere in it. Example: `branches/STH260804018.新增.工治具信息维护` → `STH260804018`. If a cell holds several SR numbers, **use the first** (decided). If the cell holds something shaped like an SR with an unlisted prefix (`S[A-Z]{2}\d{9}`), treat it as not found (rule 6) and add the warning "unlisted SR prefix <XYZ>, add it to the config" (proposed).
5. **Same SR on several rows.** Normal (in the screenshots, one SR spans 3 to 4 rows and only one has the link). Review one file per SR. If two rows for the same SR both have a link, name the second `SQL_<SR>_2.sql`.
6. **Link but no SR match (decided).** Still download and review the file, and name it `SQL_<YYYYMMDD>_<4 random digits>.sql`, for example `SQL_20261016_4821.sql`. The random number is re-drawn if the name already exists. YYYYMMDD is the current date of the run (decided). The card also shows a warning "SR not recognized" so a person can fix it.
7. **Empty window.** The run finishes as Done with "No SQL files in this deploy".
8. **Do not use the SR's date to pick rows.** The date inside the SR number appears to be the creation date, not the deploy date (for example `STH260804018` ships in the 10.13 deploy). ⚠️ Inferred from the screenshots.

**Worked example from the screenshots**

| Deploy | Window | SQL links found |
|---|---|---|
| `10.13 online` | 4 rows of `STH260804018` (工治具信息维护), between the 10.08 and 10.13 separators | 1 → `SQL_STH260804018.sql` |
| `10.08 online` | Rows above its separator (previous separator not visible): `STH260917015` (SONY Bee QR XML) and `STH260904020` (成品出库扫码-SI) | 2 → `SQL_STH260917015.sql`, `SQL_STH260904020.sql` |
| Below `10.13` | `EDW JOB` rows (prefix `STP261014021`), no separator yet | ignored (pending) |

**Sketch** (untested; for the developer):

```python
SEP = re.compile(r"\((\d{2})\.(\d{2}) online\)")
SR  = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(cfg.sr_prefixes) + r")\d{9}(?!\d)")

def deploy_window(rows, mmdd):
    seps = [i for i, r in enumerate(rows) if SEP.search(r.text)]   # separator row indexes
    target = the sep whose (MM.DD) == mmdd          # mmdd is typed by the user (required)
    prev = the sep just before target, or the header row
    return [r for r in rows[prev + 1 : target] if r.has_link_in_L]
```

---

## 4. Architecture (decided)

A **deterministic pipeline**, with an LLM only for wording. Rule-based checks always give the same answer, and an LLM alone would miss lines.

| Step | Component | Status |
|---|---|---|
| Fetch | Playwright with a persistent browser profile; **the user logs in with WeChat and the agent waits** (§5); manual `inbox/` folder (fallback) | 🟡 |
| Parse sheet and select rows | `openpyxl` on the exported `.xlsx`; deploy-date rule in §3.1 | 🟡 |
| Review | `review_sql.py` using **`pglast`** (PostgreSQL's own parser, no database needed) | ✅ |
| Explain | **Local LLM (Ollama; OpenCode optional)** refines the wording of findings. The engine's own text is the default and the fallback (see "Local LLM plan"). It does **not** decide what counts as an error. | 🟡 |
| Human gate | Review UI: approve / edit / reject | 🟡 |
| Report | Teams Adaptive Card via a **Workflows (Power Automate) webhook**, **one message per issue**; webhook URL kept in `.env` | 🟡 |
| Monitor | SQLite event log, FastAPI with SSE, single HTML page | 🟡 |

**Local LLM plan (decided: any model that runs on this laptop).**

- **Hardware.** Dell Pro 14 PC14250. Retailer listings show Intel Core 5 120U / 220U or Core Ultra 7 255U, 8 to 16 GB DDR5 RAM, and **integrated graphics only (no discrete GPU)**. ⚠️ The user's exact unit is unconfirmed (Q22).
- **Model size.** Inference runs on the CPU, so use a **small 4-bit quantized model of about 3 to 4 billion parameters**. Candidates to benchmark in the spike (⚠️ not tested): Qwen2.5-Coder 3B, Qwen3 4B, Llama 3.2 3B, Phi-4-mini, Gemma 3 4B. A 7 to 8B model may fit in 16 GB RAM but is likely too slow; with 8 GB RAM stay at 3B or smaller.
- **Runtime.** **Ollama** as a local server; the Python orchestrator calls its HTTP API directly (`http://localhost:11434`). OpenCode is optional (for interactive experiments): the pipeline is fixed and needs no agent loop, so fewer moving parts is better on a CPU-only laptop.
- **Template first, LLM second.** The engine already writes a description and recommendation for every finding. The LLM only rewrites them in clearer wording, with a timeout (proposed 30 s) and a fallback to the engine's text. A `llm_enabled` setting in `config.yaml` turns it off.
- **Keep it small.** One finding in, short JSON out, output length capped; run it for errors and warnings only; cache by finding type.
- **Speed.** ⚠️ Not measured. Generation on a U-series CPU is likely slow, so the LLM step must never block posting to Teams.

**Finding schema** (every check outputs this):

```json
{
  "severity": "error",
  "file": "SQL_STH260804018.sql",
  "line": 87,
  "title": "Missing message_locale en_US",
  "description": "message_key 'MSG.ORDER.HOLD' has only th_TH.",
  "recommendation": "Add an INSERT for MSG.ORDER.HOLD with message_locale = 'en_US'."
}
```

**Teams card.** An Adaptive Card (version 1.4) wrapped in `{"type":"message","attachments":[...]}`, posted to a Workflows webhook URL. ⚠️ Office 365 connector webhooks were reported as being retired, so use Workflows; verify against the current Microsoft docs. **The webhook URL contains a signature key, so it is a secret.** Keep it in `.env` as `TEAMS_WEBHOOK_URL`; never put it in the repo or in this document. The user has supplied the URL separately.

---

## 5. kdocs / WPS integration

Everything below is ⚠️ **unverified against the real site**. A short spike must confirm it first.

- **Login (decided): WeChat login by the user; the agent waits.** kdocs login needs WeChat (QR code), which the agent must not automate. The agent starts a **visible** (not headless) Playwright browser with a dedicated persistent profile (`./browser-profile`; optionally `channel="msedge"` to use the installed Edge, ⚠️ untested). When it sees a login page it pauses: the card shows **Waiting for login**, the UI says "Scan the WeChat QR code in the browser window", and the agent checks every few seconds until the sheet is visible, then continues by itself. A **Resume** button is the manual override. After a timeout (proposed 10 minutes) the card shows Failed with a Retry button. The agent never types or stores credentials.
- **Session reuse.** The profile keeps the session, so later runs skip the WeChat step until the session expires (⚠️ lifetime unknown).
- **Keep `browser-profile/` out of git** (it holds session cookies).
- **Sheet.** kdocs sheets render on a canvas, so do not scrape cells. Export to `.xlsx` (File → Download as → Excel) and read it with `openpyxl`. Column L is a hyperlink (confirmed), so `cell.hyperlink.target` should hold the URL if the export keeps it (⚠️ unverified).
- **SQL file: hover and download in the sheet (decided, from the user).** With the sheet open in the logged-in browser, for each selected row the agent jumps to cell `L<row>` (typing the address into the Name Box at the top left), hovers over the cell, and clicks the **second icon** that appears, the download icon. It saves the original file as `SQL_<SR>.sql`. This downloads the **original attachment**, so the text is not altered by document rendering. ⚠️ Untested details for the spike: cells are drawn on a canvas, so the hover position must come from the Name Box navigation and the selected-cell overlay; find the icon's locator with `playwright codegen`; hidden or filtered rows could make the exported row numbers differ from the on-screen rows.
- **Fallback for the SQL file.** The column L hyperlink opens a read-only kdocs page that shows the file as a WPS document, like a Word file (URL pattern: `https://www.kdocs.cn/office/w/<doc_id>?sub_file_id=<id>&attachment_store_type=upload_ks3&disablePlugins&readonly`; keep the full query string). Use its download option or a plain-text export. If that also fails, use manual `inbox/` mode.
- **Fidelity risk (fallback path only; proposed handling).** A rendered document can alter the text: smart quotes (`’ “ ”`) in place of `'` and `"`, line wrapping, changed tabs or spaces, different line numbers. That causes false syntax errors. Warn about such characters instead of reporting them as PostgreSQL syntax errors.
- **Encoding (proposed).** Files from HQ may not be UTF-8 (for example GBK or GB18030). Detect the encoding and warn when it is not UTF-8. ⚠️ The engine currently reads UTF-8 only.
- **Fallbacks.** If a step fails, the card shows **Failed at: <step>**, and the user drops the file into `inbox/`. The agent renames it and continues.
- **Policy (assumption).** The earlier answer "Now allow" was ambiguous. The user's later answer (log in with WeChat, the agent waits and the user continues) is taken to mean browser automation under the user's own login is acceptable. ⚠️ If company policy says otherwise, use manual `inbox/` mode.

**What the real sheet looks like** (from two screenshots of "THA Daily Recods (New)"):

| Item | Observation |
|---|---|
| Column **D** (`info`) | Multi-line text with the SR number inside a branch path, for example `branches/STH260804018.新增.工治具信息维护` or `merge:branches/STH260904020.…`. Extract with the SR prefix list anywhere in the cell (§3.1). The same SR repeats on several rows. |
| Column **L** (`需要的执行sql文件`, "SQL files that need to be executed") | Shows a link-style "SQL" with a small file icon. **Confirmed: a hyperlink** to a read-only kdocs document page. Hovering over the cell shows icons; the second is download (§5). |
| Red rows | Deploy separators such as `2026.10.13 9:43 package (10.13 online)`. A separator **closes** a deploy: the rows above it, back to the previous separator, are that deploy's items (§3.1). |
| Empty L cells | Most rows. Skip them. |
| Other columns | K = whether config files change (`是否更新配置文件`). M looks like a table-structure update flag (cut off in the screenshot). |

---

## 6. Check specifications

### 6.1 PostgreSQL syntax ✅

- Split the script into statements with `pglast.split(..., with_parser=False)`, then parse each one separately, so one error does not hide the others.
- Report the error line. If a missing semicolon merged two statements, also report the line where the statement starts.
- **Gotcha, fixed:** the splitter silently drops a final statement when parentheses are unbalanced. The engine now parses any leftover text as an extra statement.
- **Not caught** without a database: unknown tables or columns, duplicate keys, constraint violations (partly covered by the next-version schema check).

### 6.2 Message locale ("language") ✅

- Applies to `INSERT` statements into **`ims_message`** (table name confirmed; a schema prefix such as `pangus.` is ignored). ⚠️ The engine currently matches any `INSERT` whose column list includes `message_key`; tighten it to `ims_message` (🟡 to do).
- Group rows by `message_key` across the whole script.
- Flag a key with no `en_US` row → ❌ `Missing message_locale en_US`.
- Flag an insert that has `message_key` but no `message_locale` column → ❌ `Missing message_locale column`.
- Non-plain-VALUES inserts (`INSERT ... SELECT`, `ON CONFLICT`) → ⚠️ "needs manual check" instead of guessing.
- Confirmed: "language" means exactly `message_locale = 'en_US'`.

### 6.3 Embedded SQL in string values ✅

Discovered from the real sample: some column values contain **URL-encoded SQL** (for example `table_name` in `ims_autocomplete_config`). The outer `INSERT` parses fine, but the stored query can be wrong.

- Decode values that contain `%XX` and start with `select` or `with`.
- Blank out `${...}` fragments (app templates, not SQL), then parse.
- Report parse errors, column references with more than two parts (`a.b.c`), and qualifiers that are not a defined alias.
- Limitation: aliases are pooled across the whole query, so nested subqueries may give false results.

**Result on the real sample** (`SQL_sample.sql`), all at line 3:

| Finding | Detail |
|---|---|
| ❌ invalid column reference | `bw.u.wu_id` has three parts (likely a typo) |
| ❌ undefined table alias | `bu.wu_code` (query defines only `w`, `bw`) |
| ❌ undefined table alias | `bu.wu_name` |

⚠️ These are static findings and were not confirmed on a real PostgreSQL database.

### 6.4 Relationship check from `schema.md` 🟡 (next version; the user will provide `schema.md` later)

Parse the Mermaid `erDiagram` into tables, columns, PK/FK and relationships. For each table the script inserts into:

- Child row whose FK parent is neither inserted in the script nor known to exist → ⚠️ warning (it may already exist on the site).
- Table or column in the script that is not in `schema.md` → ❌ error.

### 6.5 Engine changes still to make 🟡

1. Read `config.yaml` (`sr_prefixes`, message table `ims_message`, required locale, `llm_enabled`).
2. Restrict the locale check to `ims_message`.
3. Detect the file encoding and warn when it is not UTF-8.
4. Return an explicit "no issues" result so a "no issues found" message can be posted.
5. Warn about smart quotes and invisible characters (fallback path).

---

## 7. Monitoring and review UI 🟡

**Card list.** One run per deploy date, with one card per SQL file (SR number), each showing state, current step, and a progress bar. A run header shows the deploy date, number of SQL files, and total findings.

**States:** `Queued → Opening sheet → Selecting deploy rows → Downloading SQL → Reviewing → Waiting for review → Posting to Teams → Done`, plus **Waiting for login** (the user scans the WeChat QR code in the browser window; the agent continues automatically, or on Resume) and **Failed** (shows step and error, with a retry button).

**Card detail.** A live log of what the agent is doing, for example "Deploy 10.13: rows 334-337, 1 SQL link found" (row numbers are an example), "Downloaded 42 KB → SQL_STH260804018.sql", "Parsing 312 statements", plus the findings table.

**Review workflow.** The findings list with Approve / Edit / Reject buttons and a **Send to Teams** action that posts each approved finding as its own message. Nothing is posted before approval.

**Implementation.** Each pipeline step writes `(agent_id, step, status, message, timestamp)` to SQLite. A small FastAPI app streams the events over SSE to one HTML page.

---

## 8. Repository layout (proposed)

```
sql-review-agent/
├── review_sql.py          ✅ MVP review engine
├── config.yaml            sr_prefixes, message table, llm settings
├── samples/
│   ├── SQL_sample.sql             real HQ sample (masked)
│   └── SQL_synthetic_test.sql     synthetic smoke test
├── agent/                 🟡 fetch.py, explain.py, teams.py
├── schema/schema.md       🟡 Mermaid ER diagram (not provided yet)
├── inbox/                 manual download fallback
├── workspace/2026-10-13/SQL_STH260804018.sql   # one folder per deploy date
├── ui/                    🟡 FastAPI + HTML cards
├── browser-profile/       gitignored
├── .env                   TEAMS_WEBHOOK_URL (gitignored; never commit)
└── events.db
```

**Run the engine:** create the environment with `py -m venv .venv`, install with `.venv/Scripts/python.exe -m pip install pglast`, then run `.venv/Scripts/python.exe review_sql.py SQL_<SR>.sql [--json]`.

---

## 9. Build order

1. **kdocs spike (about an hour):** open the visible browser, log in with WeChat, and check (a) the agent waits and continues after the login, (b) the exported `.xlsx` keeps the red separator text, the column L hyperlinks and the real row numbers, (c) hovering over one column L cell and clicking the second icon downloads the original `.sql`, (d) the file's encoding (UTF-8 or GBK). Full list in §10.
2. **Review engine** ✅ (extend with `schema.md` later).
3. **Findings → Teams, one message per issue,** via the Workflows webhook.
4. **Monitoring and review UI.**
5. **Wire in the Playwright fetch** based on the spike results.
6. **Local model benchmark:** install Ollama, try two or three 3 to 4B models on three sample findings, and pick by speed and wording quality. The engine text stays as the fallback.

---

## 10. Open questions

### Resolved (answers from the user)

| # | Question | Answer |
|---|---|---|
| 1 | Which SQL files does a run review? | Every SQL link in the deploy window above the chosen deploy date, back to the previous deploy date (§3.1) |
| 2 | Is column L a hyperlink or an in-cell attachment? | **Hyperlink** |
| 3 | Preview page or direct download? | The link opens a **read-only WPS document page**, not a direct download (§5, fallback path) |
| 4 | Is "language" exactly `message_locale = 'en_US'`? | **Exactly** |
| 5 | Name of the message table | **`ims_message`** |
| 7 | Teams channel and Workflows webhook URL | **Provided** by the user; kept in `.env`, not recorded here |
| 8 | LLM provider | **Local model** (OpenCode or Ollama; see "Local LLM plan" in §4) |
| 9 | Policy / login | kdocs needs a **WeChat login**; the **agent waits** while the user logs in, then continues (§5) |
| 10 | Which deploy does a run target? | **The user types `MM.DD`** (no default) |
| 11 | Rows below the last separator | **Ignore** |
| 12 | SR prefix | Refined in Q21 to a configuration list |
| 13 | One row names several SR numbers | **Use the first** |
| 14 | Teams grouping | **One message per issue** |
| 15 | Row has an SQL link but no SR number | **Download it and name it `SQL_<YYYYMMDD>_<4 random digits>.sql`** (§3.1 rule 6) |
| 16 | How to get the SQL file | **Hover over the column L cell and click the second icon (download)** (§5) |
| 17 | Local model and hardware | **Any model that runs on the laptop**; Dell Pro 14 PC14250; Ollama or OpenCode |
| 18 | `<YYYYMMDD>` in the fallback name | **Current date** |
| 19 | Where do the messages go? | **A Teams channel first** |
| 20 | Post a message for a file with no issues? | **Yes** |
| 21 | SR prefixes | **Configuration list: `STH, STP, SFQ, SWH, SXM, SBJ, SQD`** |

### Still open

| # | Question | Needed for |
|---|---|---|
| 6 | `schema.md` file (user will provide later) | Relationship check (next version) |
| 22 | How much RAM does the laptop have (8, 16 or 32 GB)? Check Task Manager → Performance → Memory. | Model size choice |

### To verify in the spike (not questions for the user)

1. WeChat login works in the Playwright browser, the agent detects the login page and resumes, and the session persists between runs.
2. In the sheet, the Name Box jump plus hover shows the download icon, and the locator for it can be found.
3. The downloaded file is the original `.sql` (check its name and encoding: UTF-8 or GBK).
4. The `.xlsx` export keeps the separator text, the column L hyperlinks, and row numbers that match the screen (no hidden or filtered rows).
5. A 3 to 4B local model gives acceptable wording at acceptable speed (benchmark).

---

## 11. Glossary

| Term | Meaning |
|---|---|
| **SR (Service Request)** | A request number identifying one change, format = a prefix from the configured list (`STH`, `STP`, `SFQ`, `SWH`, `SXM`, `SBJ`, `SQD`) + `YYMMDD` + 3-digit sequence, for example `STH260804018`. Used in the file name `SQL_<SR_Number>.sql`. |
| **HQ** | Headquarters development team that writes and ships the SQL scripts. |
| **Site IT** | The local IT team that executes the scripts on the site's database (the user). |
| **MES deploy sheet** | The kdocs spreadsheet ("THA Daily Recods (New)") listing each deploy item and its SQL file. |
| **Deploy date / online date** | The date a package goes online, written `(MM.DD online)` on the red separator row, for example `(10.13 online)`. |
| **Deploy separator** | The red row that closes a deploy, such as `2026.10.13 9:43 package (10.13 online)`. |
| **Deploy window** | The rows above a deploy separator, back to the previous separator. The SQL files in this window are reviewed together. |
| **Package** | A deploy batch; the rows of one deploy window. |
| **Pending rows** | Rows below the last separator; the next deploy, with no date yet. Ignored. |
| **kdocs / WPS** | Kingsoft's cloud office (kdocs.cn); the host of the sheet and SQL files. Needs login. |
| **message_key** | Identifier of a system message. Each key needs one row per locale. |
| **message_locale** | The language of a message row. The required locale here is `en_US`. |
| **Embedded SQL** | A SQL query stored as URL-encoded text inside a column value, for example `table_name`. |
| **`${...}` fragment** | An application template placeholder inside embedded SQL (for example `${and w.pl_id=[plId]}`). It is not valid SQL and is skipped in checks. |
| **pglast** | Python library wrapping PostgreSQL's own parser (libpg_query). It gives real PostgreSQL syntax errors without a database. |
| **Playwright** | Browser automation library, used with a persistent profile to reuse the kdocs login. |
| **OpenCode** | Open-source coding-agent tool that can call many LLM providers, including local ones. |
| **Adaptive Card** | Microsoft's JSON card format used for each Teams issue message. |
| **Issue message** | One Teams message for one finding; the unit that is tracked. |
| **ims_message** | The PostgreSQL table that holds system messages, one row per `message_key` and `message_locale`. The locale check applies to it. |
| **Read-only document page** | The kdocs page that a column L link opens: the SQL file shown as a WPS document (like Word), not a direct download. Used only as a fallback to get the file. |
| **SR prefix list** | The `sr_prefixes` setting in `config.yaml`: `STH, STP, SFQ, SWH, SXM, SBJ, SQD`. Add a prefix there when a new one appears. |
| **Hover download** | Hovering over a column L cell in the sheet shows icons; the second one downloads the original attachment. |
| **Waiting for login** | The agent state while the user scans the WeChat QR code in the browser window; the agent continues automatically or on Resume. |
| **No-issues message** | The Teams message `✅ <file> - No issues found`, posted for a file with no findings. |
| **Fallback file name** | `SQL_<YYYYMMDD>_<4 random digits>.sql`, used when no SR number is found in column D; YYYYMMDD is the current date of the run. |
| **Local LLM** | A language model that runs on the laptop (for example through Ollama) and is called through Ollama (OpenCode is optional), so script content stays local. A small quantized model is used because the laptop has no discrete GPU. |
| **Workflows webhook** | A Power Automate flow ("Post to a channel when a webhook request is received") used to post cards to Teams. Its URL contains a signature key and is a secret. |
| **schema.md** | A Markdown file with a Mermaid `erDiagram` describing tables, keys and relationships. Used from the next version. |
| **Finding** | One detected issue: severity, file, line, title, description, recommendation. |
| **Human gate** | The review step where the user approves, edits or rejects findings before they are posted. |

---

## 12. Change log

- **v4:** Recorded the user's answers to the remaining questions (§10). Decisions: WeChat login by the user with the agent waiting; download by hovering over the column L cell (original file); SR prefixes become a configuration list; fallback file name uses the current date; messages go to a Teams channel first; "no issues" messages are posted; local model on a CPU-only laptop (small quantized model, template text as fallback). Added the engine to-do list (§6.5), the spike checklist (§10), and a file-encoding risk. Open: Q6 (`schema.md`), new Q22 (laptop RAM).
- **v3:** Recorded the user's answers to open questions 2 to 15 (§10). Decisions: local LLM via OpenCode; locale check on `ims_message`; user types the deploy date; ignore rows below the last separator; SR prefix is `S` + 2 letters; first SR wins; one Teams message per issue; fallback file name when no SR is found. Facts: column L is a hyperlink to a read-only WPS document page, not a direct download (new spike risk, §5). Not recorded: the webhook URL (secret). Open: Q9 "Now allow" is ambiguous; new questions 16 to 21.
- **v2:** Resolved the SR-selection question with the deploy-date rule (§3.1). Added the SR format `STHYYMMDDXXX`. **Corrected an earlier assumption:** column D does *not* start with the SR number; it contains the SR inside a branch path, so extract it with a regex. Added open questions 10 to 14. Changed the monitoring UI to one run per deploy date with one card per SQL file.
- **v1:** First handoff (problem, scope, architecture, check specs, glossary).
