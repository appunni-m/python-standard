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
| `standard-fastapi` | `std.fastapi` | FastAPI integration. | Source project exists; PyPI returned 404 on 2026-10-12; publisher setup is owner action. |
| `standard-aws` | `std.aws` | AWS integration. | Source project exists; PyPI returned 404 on 2026-10-12; publisher setup is owner action. |
| `standard-http` | `std.http` | HTTP client and authentication helpers. | Source project exists; PyPI returned 404 on 2026-10-12; publisher setup is owner action. |
| `standard-cache` | `std.cache` | Redis client, caching decorators, and locks. | Source project exists; PyPI returned 404 on 2026-10-12; publisher setup is owner action. |
| `standard-rdbms` | `std.rdbms` | Relational database configuration and session helpers. | Source project exists; PyPI returned 404 on 2026-10-12; publisher setup is owner action. |

The exact [PyPI JSON endpoint for `standard`](https://pypi.org/pypi/standard/json)
returned HTTP 200 on 2026-10-12. The endpoints for the five add-on names above
returned HTTP 404 that day. This is an availability snapshot, not a reservation;
check again immediately before publisher setup and release.

The core project's extras are convenience selectors: `standard[fastapi]`
installs `standard-fastapi`, `standard[aws]` installs `standard-aws`,
`standard[http]` installs `standard-http`, `standard[cache]` installs
`standard-cache`, and `standard[rdbms]` installs `standard-rdbms`. On each
release, the build workflow pins every extra and add-on dependency to that
release's exact shared version. There is no separate `standard-core` or
`standard-cli` project.

For each add-on project, use a PyPI **pending publisher** under the owner's
account. All six projects use the same publisher identity because a single
tag-based workflow publishes the complete release:

| PyPI project | Workflow filename | Publisher | Owner | Repository | GitHub environment |
| --- | --- | --- | --- | --- | --- |
| `standard-fastapi` | `release.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |
| `standard-aws` | `release.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |
| `standard-http` | `release.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |
| `standard-cache` | `release.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |
| `standard-rdbms` | `release.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |

Add one pending publisher for each new project under the PyPI account's
**Publishing** page. PyPI converts it to a normal publisher on first successful
publication. A pending publisher does **not** reserve the project name; verify
availability immediately before configuring and publishing it. If a pending
publisher was registered with an older workflow filename, update or recreate
it with `release.yml` before the first upload. See PyPI's
[project creation with a pending publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
and [publisher setup guide](https://docs.pypi.org/trusted-publishers/adding-a-publisher/),
plus PyPI's [Trusted Publisher security model](https://docs.pypi.org/trusted-publishers/security-model/).

All six distributions share one version source and one tag. `hatch-vcs` reads
the same `vX.Y.Z` Git tag from each project directory, and the release script
checks that all projects use that tag pattern. No project has a separately
maintained version field:

| Project | Workflow | Tag pattern |
| --- | --- | --- |
| `standard` | `release.yml` | `vX.Y.Z` |
| `standard-fastapi` | `release.yml` | `vX.Y.Z` |
| `standard-aws` | `release.yml` | `vX.Y.Z` |
| `standard-http` | `release.yml` | `vX.Y.Z` |
| `standard-cache` | `release.yml` | `vX.Y.Z` |
| `standard-rdbms` | `release.yml` | `vX.Y.Z` |

The one release workflow builds the core and five providers from the same
commit. It verifies the name and version in all 12 wheel/source artifacts,
then publishes `standard` followed by each provider from the same `pypi`
environment. Before building, it pins each core extra and each provider's core
dependency to the tag version. This keeps `standard[fastapi]` and the other
extras on the matching release, including future patch or minor releases. The
core wheel has an explicit allow-list, and each add-on wheel owns only its
`std.<integration>` subtree. This change does not create a tag or publish files.

### GitHub environment setup

The `pypi` environment is configured and was used successfully by the
`v0.1.1` release. All six projects must have a Trusted Publisher for
`release.yml` and the `pypi` environment before their first coordinated
release. If repository protection rules or the environment name change, update
the publisher entries to match.

### Version-tag release flow

The single release workflow applies the annotated-tag, exact-commit CI,
checksum, OIDC, and artifact-attestation safeguards used by
[pillow-rs](https://github.com/appunni-m/pillow-rs/blob/main/.github/workflows/release.yml),
adapted to Python wheels and source distributions:

1. Requires one annotated `vX.Y.Z` tag that resolves to the workflow commit.
2. Requires a successful `main` CI run for that exact commit. This includes the Python matrix, quality checks, and Testcontainers end-to-end job.
3. Reads the version from the tag, synchronizes all cross-distribution requirements to that exact version, builds one wheel and source distribution per project, and checks every file with `twine check`.
4. Inspects the built metadata and fails unless all 12 artifacts declare the same version and exact cross-project pins. It stores the complete bundle with a SHA-256 manifest.
5. Compares existing PyPI files by filename and SHA-256. It uploads missing files in dependency order, skips identical files on a retry, and stops on conflicting files.
6. Publishes from the `pypi` environment with `pypa/gh-action-pypi-publish` pinned to `dc37677b2e1c63e2034f94d8a5b11f265b73ba33` (v1.14.2), then attests the full release bundle and creates one GitHub release with all 12 artifacts and the checksum manifest.

Do not edit version fields in individual `pyproject.toml` files. Merge the
release-ready commit to `main`, wait for its CI run (including Testcontainers)
to pass, then create and push one annotated tag. The tag is the one input
version; the workflow derives it for every project and creates the matching
dependency pins automatically. It does not guess whether the next release
should be a patch, minor, or major version.

```bash
make check
make test-e2e
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

Replace `X.Y.Z` with the single version for the complete release. The annotated tag must point at the commit whose `main` CI passed. The pushed tag starts the workflow; monitor **Release** in GitHub Actions and verify all six PyPI project versions and the GitHub release. Treat release tags as immutable: publish a correction with the next version.

Before the first coordinated release, verify the five project names and
configure each PyPI pending publisher with `release.yml` and `pypi` as shown
above. GitHub environment settings require a repository owner or administrator;
PyPI publisher setup requires control of the account. The add-on projects do
not yet have published releases.
