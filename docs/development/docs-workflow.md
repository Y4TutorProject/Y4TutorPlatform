# Working on the documentation

Update the relevant page when a route, setting or user flow changes. Keep the documentation in the same branch and PR as the code.

## Preview and check

Install Node.js 20 or later, then from the repository root:

```sh
python3.12 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r requirements-docs.txt
npm ci
.venv-docs/bin/python -m mkdocs serve
```

Open <http://127.0.0.1:8000>. Run the checks before committing:

```sh
.venv-docs/bin/python scripts/check_docs.py
```

This checks source formatting, Markdown, YAML, Mermaid syntax and local links, runs the checker tests, and builds MkDocs in strict mode. Output goes to the ignored `site/` directory. To use another directory:

```sh
.venv-docs/bin/python scripts/check_docs.py --site-dir /tmp/tutorplatform-docs
```

Check external links, command examples and rendered diagrams separately. Mermaid syntax validation does not check diagram appearance or whether arrows reflect the implementation.

## Branch and review

1. Use a feature branch from `main`.
2. Update the affected pages alongside the code.
3. Run the checks and preview the changed pages.
4. Commit with a message describing the change, such as `docs: explain CSV preview errors`.
5. Open a PR and ask the other team member to review it. For setup changes, ask them to try the commands.
6. Address feedback and rerun the checks before merging.

## Style

Use short explanations, the names shown in the UI and working examples. Put commands in fenced code blocks with a language. Use one page title and relative links between Markdown pages.

PyMarkdown checks Markdown rules with line length disabled. The formatting check rejects tabs, trailing spaces and incorrect final newlines.

Keep diagrams in `mermaid` blocks. Check their arrows against Compose, gateway routes and service calls. Use example data and placeholder credentials in requests and screenshots.
