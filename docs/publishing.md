# Publishing documentation

## Local build

```bash
make docs-install
make docs-build
```

The generated site is written to `site/` and is excluded from Git.

## GitHub Pages deployment

The repository includes `.github/workflows/docs.yml`. It builds the docs with the pinned documentation dependencies and publishes them on pushes to `main` or a manual workflow run.

### Verified deployment

The first deployment succeeded in [Documentation run #4](https://github.com/appunni-m/python-standard/actions/runs/38199791257) for commit `41f0b4a` on 2026-10-12. The site is live at [appunni-m.github.io/python-standard](https://appunni-m.github.io/python-standard/). Each push to `main` builds `site/`, uploads it as a Pages artifact, and deploys it to the `github-pages` environment. To deploy manually, open **Actions → Documentation** and choose **Run workflow**.

The workflow grants only `contents: read`, `pages: write`, and `id-token: write`, and uses GitHub's recommended Pages actions. See [GitHub's publishing-source guide](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site), [GitHub's custom-workflow requirements](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), and [Zensical's GitHub Pages guide](https://zensical.org/docs/publish-your-site/).

The live Pages URL, `https://appunni-m.github.io/python-standard/`, matches `site_url` in `zensical.toml`. Keep this setting aligned if the repository's Pages domain changes. Zensical recommends this setting for canonical page metadata; instant navigation and instant previews also require it.

## Published distribution

The [PyPI project](https://pypi.org/project/standard/) currently lists release `0.1.0`, one maintainer (`appunni-m`), a source distribution, a universal wheel, and the `fastapi` and `aws` extras. On 2026-10-12, fresh CPython 3.12 environments installed the base package, each extra, and the combined extras from PyPI; imports and CLI checks passed.

The GitHub Release workflow has no runs, the repository has no release tags, and GitHub has no releases. The PyPI release therefore has not been verified through this repository's OIDC workflow. The published 0.1.0 README and `std guide` still contain the old claim that the `standard` name belongs to someone else. Repository version 0.1.1 corrects that text; PyPI will continue serving 0.1.0 until a new release is explicitly published.

## Configure PyPI Trusted Publishing

The release workflow is present at `.github/workflows/release.yml`. It uses PyPI Trusted Publishing through GitHub's OIDC identity, so the publishing job does not need a long-lived `PYPI_TOKEN` secret. The owner reports that the publisher is configured, but no Release workflow run has verified the OIDC exchange yet.

### Publisher fields

For the existing `standard` project, configure a GitHub Actions publisher whose values exactly match the workflow identity:

| PyPI or GitHub field | Value |
| --- | --- |
| PyPI project name | `standard` |
| Publisher | GitHub Actions |
| Owner | `appunni-m` |
| Repository | `python-standard` |
| Workflow filename | `release.yml` (the repository file is `.github/workflows/release.yml`) |
| GitHub environment | `pypi` |

PyPI matches the owner, repository, workflow filename, and optional environment against the GitHub Actions identity. The publisher form asks for the workflow filename, not the `.github/workflows/` path. See PyPI's [publisher setup guide](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).

The `standard` project already exists and lists `appunni-m` as its maintainer. Configure or verify the publisher through that project's **Publishing** page. Do not create a pending publisher for a name that already has a project.

### GitHub environment setup

An owner or repository administrator must configure the environment in `appunni-m/python-standard`:

1. Open **Settings → Environments** and create an environment named `pypi`.
2. Restrict deployment refs to tags matching `v*`, which matches this workflow's release trigger.
3. Restrict this environment to tags matching `v*` and require a trusted maintainer to approve publishing jobs when the repository plan supports reviewers.

The workflow's publish job references `pypi`; GitHub can create a missing environment automatically, but only an owner or administrator can configure its protection rules. See GitHub's [environment setup guide](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) and [deployment branch and tag rules](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments#deployment-branches-and-tags).

### Version-tag release flow

`.github/workflows/release.yml` applies the annotated-tag, exact-commit CI, checksum, OIDC, and artifact-attestation safeguards used by [pillow-rs](https://github.com/appunni-m/pillow-rs/blob/main/.github/workflows/release.yml), adapted to this project's Python wheel and source distribution. It runs when a tag beginning with `v` is pushed. The workflow:

1. Requires an annotated tag that resolves to the workflow commit and exactly matches `v` plus `[project].version` in `pyproject.toml` (the repository is now version `0.1.1`, so its tag is `v0.1.1`).
2. Requires a successful `main` CI run for that exact commit. This includes the Python matrix, quality checks, and Testcontainers end-to-end job.
3. Builds one wheel and one source distribution, checks them with `twine check`, and stores them with a SHA-256 manifest.
4. Compares any existing files for that PyPI version by filename and SHA-256. It publishes only missing files, skips identical files on a retry, and stops if PyPI contains a conflicting artifact.
5. Publishes from the `pypi` environment with `pypa/gh-action-pypi-publish` pinned to verified commit `dc37677b2e1c63e2034f94d8a5b11f265b73ba33` (v1.14.2), then attests the release bundle and creates a GitHub release with the files and checksum manifest.

For a release, complete the owner-only setup above, update `project.version`, push the commit to `main`, and wait for its CI run to pass before tagging that same commit. The container check requires Docker, so run it locally when Docker is available; the main-branch CI run covers it in CI.

```bash
make check
make test-e2e
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

Replace `X.Y.Z` with the exact version in `pyproject.toml`. The annotated tag must point at the commit whose `main` CI passed. The pushed tag starts the workflow; monitor **Release** in GitHub Actions and verify the PyPI files and GitHub release. Treat release tags as immutable: publish a correction with the next version.

Before the next automated release, push `main`, configure the repository's `pypi` environment, and verify the matching Trusted Publisher in PyPI. GitHub environment settings require a repository owner or administrator; PyPI publisher setup requires control of the corresponding PyPI project or account. The current release workflow has not run, so the OIDC publishing path still needs verification.
