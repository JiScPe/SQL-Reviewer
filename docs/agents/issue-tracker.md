# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- Create: `gh issue create --title "..." --body "..."`.
- Read: `gh issue view <number> --json number,title,body,labels,comments`.
- List: `gh issue list --state open --json number,title,body,labels,comments`.
- Comment: `gh issue comment <number> --body "..."`.
- Apply/remove labels: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`.
- Close: `gh issue close <number> --comment "..."`.
- Infer the repo from `git remote -v`; `gh` does this automatically inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** Set to `yes` only if this repo treats external PRs as feature requests.

When enabled, use `gh pr view`, `gh pr diff`, `gh pr comment`, and `gh pr edit` equivalents. GitHub shares one number space across issues and PRs; resolve a bare `#42` by checking `gh pr view 42` and then `gh issue view 42`.

## Publishing and fetching

When a skill says to publish, create a GitHub issue. When it says to fetch a ticket, run `gh issue view <number> --comments`.

## Wayfinding

- Map: one issue labelled `wayfinder:map`.
- Child ticket: a GitHub sub-issue of the map, labelled `wayfinder:<type>` (`research`, `prototype`, `grilling`, or `task`). If sub-issues are unavailable, use a task list and `Part of #<map>` in the child body.
- Blocking: use native issue dependencies; if unavailable, record `Blocked by: #<n>` in the child body.
- Frontier: choose the first map child that is open, unblocked, and unassigned.
- Claim: assign it with `gh issue edit <n> --add-assignee @me`.
- Resolve: comment with the answer, close the issue, then add a context pointer to the map's Decisions-so-far.