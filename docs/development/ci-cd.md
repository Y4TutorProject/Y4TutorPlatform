# Documentation CI/CD

`.github/workflows/docs.yml` validates the documentation and publishes the MkDocs site.

## What runs

The workflow runs on pull requests, pushes to `main` and manual runs. It uses Python 3.12 and installs `requirements-docs.txt`.

The validation job runs `python scripts/check_docs.py`:

1. Check formatting and YAML, then run the link-checker tests.
2. Run PyMarkdown on `docs`, the root README and PR template.
3. Build MkDocs with `--strict`.
4. Check generated local links, assets and heading anchors.
5. Upload `site/` as the `documentation-site` artifact, retained for 14 days.

A failed check stops the job. PR previews are downloaded from the Actions artifact.

## Deployment

Successful runs on `main` upload a Pages artifact and deploy it to the `github-pages` environment. The deployment job has `pages: write` and `id-token: write` permissions. Validation has read access to repository contents.

PRs and manual runs on feature branches validate only. Manual runs on `main` can publish.

## First-time Pages setup

In repository settings:

1. Open **Pages** and select **GitHub Actions** as the source.
2. Enable Actions and allow the `github-pages` environment to deploy from `main`.
3. Merge the workflow and documentation into `main`, or run the workflow from `main`.
4. Open the deployment URL from Actions and check navigation, diagrams and nested pages.

The configured site address is <https://Y4TutorProject.github.io/Y4TutorPlatform/>.

## Failed builds and rollback

Open the failed job in Actions and reproduce it locally:

```sh
.venv-docs/bin/python scripts/check_docs.py
```

Fix the source on a branch and submit it for review. To roll back a published change, revert its documentation commit through a PR. Merging to `main` triggers a new build and deployment.
