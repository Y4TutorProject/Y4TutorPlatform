# TutorPlatform

A college peer-tutoring prototype built with Flask services, MongoDB and Docker Compose.

- [Start the app locally](docs/setup/local-development.md)
- [Read the architecture overview](docs/architecture/overview.md)
- [Run the documentation checks](docs/development/docs-workflow.md)

The documentation is built with MkDocs. To preview it without starting the app:

```sh
python3.12 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r requirements-docs.txt
.venv-docs/bin/python -m mkdocs serve
```

Open <http://127.0.0.1:8000>. To run the same checks as CI:

```sh
.venv-docs/bin/python scripts/check_docs.py
```

The Pages workflow is prepared in `.github/workflows/docs.yml`. A repository owner still needs to enable GitHub Pages before the first deployment. See the [CI/CD guide](docs/development/ci-cd.md).
