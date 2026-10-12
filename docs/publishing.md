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

The first deployment succeeded in [Documentation run #4](https://github.com/appunni-m/python-standard/actions/runs/38199791257) for commit `41f0b4a` on 2026-10-12. The latest verified deployment at the time of this edit is [run 38226724951](https://github.com/appunni-m/python-standard/actions/runs/38226724951) for main commit `ef584957`. The site is live at [appunni-m.github.io/python-standard](https://appunni-m.github.io/python-standard/). Each push to `main` builds `site/`, uploads it as a Pages artifact, and deploys it to the `github-pages` environment. To deploy manually, open **Actions → Documentation** and choose **Run workflow**.

The workflow grants only `contents: read`, `pages: write`, and `id-token: write`, and uses GitHub's recommended Pages actions. See [GitHub's publishing-source guide](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site), [GitHub's custom-workflow requirements](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), and [Zensical's GitHub Pages guide](https://zensical.org/docs/publish-your-site/).

The live Pages URL, `https://appunni-m.github.io/python-standard/`, matches `site_url` in `zensical.toml`. Keep this setting aligned if the repository's Pages domain changes. Zensical recommends this setting for canonical page metadata; instant navigation and instant previews also require it.

## Published distribution

The [PyPI `standard` project](https://pypi.org/project/standard/) has release `0.1.1`. The annotated `v0.1.1` tag was published through this repository's release workflow, run [38249688229](https://github.com/appunni-m/python-standard/actions/runs/38249688229), which completed successfully. The [GitHub release](https://github.com/appunni-m/python-standard/releases/tag/v0.1.1) is live. The published wheel and source archive declare the `fastapi` and `aws` extras and include the corresponding `std` modules.

This describes the published `0.1.1` artifact. The working tree may contain later local documentation and logging changes; those are not part of `0.1.1` unless released under a later version.

## Configure PyPI Trusted Publishing

The release workflow is present at `.github/workflows/release.yml`. It uses PyPI Trusted Publishing through GitHub's OIDC identity, so the publishing job does not need a long-lived `PYPI_TOKEN` secret. The successful `v0.1.1` run verifies the current publisher path for the existing `standard` project.

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

The `standard` project already exists and lists `appunni-m` as its maintainer. Its publisher is verified by the successful `v0.1.1` release. Do not create a pending publisher for this existing project.

## Distribution projects

Core and the CLI stay in `standard`. The additional project names and import
ownership are:

| PyPI project | Python import | Contents | Publisher status |
| --- | --- | --- | --- |
| `standard` | `std` | Core utilities, configuration, logging, CLI, and skill. | Existing publisher; verified by release `v0.1.1`. |
| `standard-fastapi` | `std.fastapi` | FastAPI integration. | Source project and release workflow exist; PyPI returned 404 on 2026-10-12; publisher setup is unverified. |
| `standard-aws` | `std.aws` | AWS integration. | Source project and release workflow exist; PyPI returned 404 on 2026-10-12; publisher setup is unverified. |
| `standard-http` | `std.http` | HTTP client and authentication helpers. | Implementation and release workflow are in the working tree; PyPI returned 404 on 2026-10-12; publisher setup is unverified. |
| `standard-cache` | `std.cache` | Redis client, caching decorators, and locks. | Implementation and release workflow are in the working tree; PyPI returned 404 on 2026-10-12; publisher setup is unverified. |
| `standard-rdbms` | `std.rdbms` | Relational database configuration and session helpers. | Implementation and release workflow are in the working tree; PyPI returned 404 on 2026-10-12; publisher setup is unverified. |

The exact [PyPI JSON endpoint for `standard`](https://pypi.org/pypi/standard/json)
returned HTTP 200 on 2026-10-12. The endpoints for the five add-on names above
returned HTTP 404 that day. This is an availability snapshot, not a reservation;
check again immediately before publisher setup and release.

The core project's extras are convenience selectors: `standard[fastapi]`
installs `standard-fastapi`, `standard[aws]` installs `standard-aws`,
`standard[http]` installs `standard-http`, `standard[cache]` installs
`standard-cache`, and `standard[rdbms]` installs `standard-rdbms`. These
extras are declared in the repository's 0.2.0 metadata. They become available
from PyPI after the matching core and add-on releases have been published.
There is no separate `standard-core` or `standard-cli` project.

For each new project, use a PyPI **pending publisher** under the owner's account
and these identity fields. The workflow filename must match that project's
dedicated release workflow:

| PyPI project | Workflow filename | Publisher | Owner | Repository | GitHub environment |
| --- | --- | --- | --- | --- | --- |
| `standard-fastapi` | `release-fastapi.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |
| `standard-aws` | `release-aws.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |
| `standard-http` | `release-http.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |
| `standard-cache` | `release-cache.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |
| `standard-rdbms` | `release-rdbms.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |

Add one pending publisher for each new project under the PyPI account's
**Publishing** page. PyPI converts it to a normal publisher on first successful
publication. A pending publisher does **not** reserve the project name; verify
availability immediately before configuring and publishing it. Publisher
configuration for `standard-fastapi` and `standard-aws` is not verified here.
Separate workflow names also keep
each publisher's OIDC identity scoped to one project. See PyPI's
[project creation with a pending publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
and [publisher setup guide](https://docs.pypi.org/trusted-publishers/adding-a-publisher/),
plus PyPI's [Trusted Publisher security model](https://docs.pypi.org/trusted-publishers/security-model/).

The core workflow builds `standard` on `v<version>` tags. Dedicated provider
workflows build their package directories on project-specific version tags.
All six workflows are present in this working tree; only the core workflow
has published a release:

| Project | Workflow | Tag pattern |
| --- | --- | --- |
| `standard` | `release.yml` | `vX.Y.Z` |
| `standard-fastapi` | `release-fastapi.yml` | `standard-fastapi-vX.Y.Z` |
| `standard-aws` | `release-aws.yml` | `standard-aws-vX.Y.Z` |
| `standard-http` | `release-http.yml` | `standard-http-vX.Y.Z` |
| `standard-cache` | `release-cache.yml` | `standard-cache-vX.Y.Z` |
| `standard-rdbms` | `release-rdbms.yml` | `standard-rdbms-vX.Y.Z` |

The repository's core metadata selects all five provider distributions through
their matching extras. Release `standard` 0.2.0 before its add-ons so their
`standard>=0.2.0` dependency can resolve, then publish each add-on and verify
the extras in clean environments. The extras cannot install successfully from
PyPI until their matching add-on has been published. The core wheel has an
explicit allow-list, and each add-on wheel owns only its `std.<integration>`
subtree. No provider release tag has been pushed by this work.

### GitHub environment setup

The `pypi` environment is configured and was used successfully by the
`v0.1.1` release. The FastAPI and AWS workflows use that environment with
separate workflow identities. Their Trusted Publishers still need to be
configured in PyPI. If repository protection rules or the environment name
change, update each publisher to match before publishing.

### Version-tag release flow

The core and provider workflows apply the annotated-tag, exact-commit CI,
checksum, OIDC, and artifact-attestation safeguards used by
[pillow-rs](https://github.com/appunni-m/pillow-rs/blob/main/.github/workflows/release.yml),
adapted to Python wheels and source distributions. The provider workflows also
validate the package's own version and build only its package directory. They
run when their matching project tag is pushed. The core workflow:

1. Requires an annotated tag that resolves to the workflow commit and exactly matches `v` plus `[project].version` in the root `pyproject.toml` (the current core release is `0.1.1`, tagged `v0.1.1`).
2. Requires a successful `main` CI run for that exact commit. This includes the Python matrix, quality checks, and Testcontainers end-to-end job.
3. Builds one wheel and one source distribution, checks them with `twine check`, and stores them with a SHA-256 manifest.
4. Compares any existing files for that PyPI version by filename and SHA-256. It publishes only missing files, skips identical files on a retry, and stops if PyPI contains a conflicting artifact.
5. Publishes from the `pypi` environment with `pypa/gh-action-pypi-publish` pinned to verified commit `dc37677b2e1c63e2034f94d8a5b11f265b73ba33` (v1.14.2), then attests the release bundle and creates a GitHub release with the files and checksum manifest.

For a core release, update the root `project.version`, push the commit to
`main`, and wait for its CI run to pass before tagging that same commit. For an
add-on, update the version in its package `pyproject.toml`, push that commit to
`main`, and wait for the same successful CI run before tagging. The container
check requires Docker; the main-branch CI run covers it in CI.

```bash
make check
make test-e2e
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

Replace `X.Y.Z` with the exact version in `pyproject.toml`. The annotated tag must point at the commit whose `main` CI passed. The pushed tag starts the workflow; monitor **Release** in GitHub Actions and verify the PyPI files and GitHub release. Treat release tags as immutable: publish a correction with the next version.

For add-ons, use the exact tag and workflow shown in the table above. Before
publishing, verify each project name and configure its PyPI pending publisher
with the fields above. GitHub environment settings require a repository owner
or administrator; PyPI publisher setup requires control of the account. No
provider release tag has been pushed by this work.
