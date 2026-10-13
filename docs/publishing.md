# Publishing documentation

## Local build

```bash
make docs-install
make docs-build
```

The generated site is written to `site/` and is excluded from Git.

## Current release status

The latest coordinated release is `v0.2.4`. It publishes the core package and
all five integration distributions at version `0.2.4` from one annotated tag.
The release workflow uses PyPI Trusted Publishing and creates one GitHub
release containing the distributions and checksum manifest.

| PyPI project | Import namespace | Install selection |
| --- | --- | --- |
| [`standard`](https://pypi.org/project/standard/) | `std` | `standard` |
| [`standard-fastapi`](https://pypi.org/project/standard-fastapi/) | `std.fastapi` | `standard[fastapi]` or `standard-fastapi` |
| [`standard-aws`](https://pypi.org/project/standard-aws/) | `std.aws` | `standard[aws]` or `standard-aws` |
| [`standard-http`](https://pypi.org/project/standard-http/) | `std.http` | `standard[http]` or `standard-http` |
| [`standard-cache`](https://pypi.org/project/standard-cache/) | `std.cache` | `standard[cache]` or `standard-cache` |
| [`standard-rdbms`](https://pypi.org/project/standard-rdbms/) | `std.rdbms` | `standard[rdbms]` or `standard-rdbms` |

Installing `standard` alone installs core only. Each extra selects its matching
provider; there is no separate `standard-core` or `standard-cli` project.

## GitHub Pages deployment

The repository includes `.github/workflows/docs.yml`. It builds the docs with the pinned documentation dependencies and publishes them on pushes to `main` or a manual workflow run.

### Verified deployment

An earlier deployment succeeded in [run 38226724951](https://github.com/appunni-m/python-standard/actions/runs/38226724951). The site is published at [appunni-m.github.io/python-standard](https://appunni-m.github.io/python-standard/). Each push to `main` builds `site/`, uploads it as a Pages artifact, and deploys it to the `github-pages` environment. To deploy manually, open **Actions → Documentation** and choose **Run workflow**.

The workflow grants only `contents: read`, `pages: write`, and `id-token: write`, and uses GitHub's recommended Pages actions. See [GitHub's publishing-source guide](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site), [GitHub's custom-workflow requirements](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), and [Zensical's GitHub Pages guide](https://zensical.org/docs/publish-your-site/).

The live Pages URL, `https://appunni-m.github.io/python-standard/`, matches `site_url` in `zensical.toml`. Keep this setting aligned if the repository's Pages domain changes. Zensical recommends this setting for canonical page metadata; instant navigation and instant previews also require it.

## Published distribution

The coordinated `v0.2.4` release includes the standalone integration packages.
The earlier `0.1.1` artifact bundled FastAPI and AWS in the core package; use
the current extras or direct provider package names above for new installs.

## Configure PyPI Trusted Publishing

The release workflow at `.github/workflows/release.yml` uses PyPI Trusted
Publishing through GitHub's OIDC identity. It does not need a long-lived
`PYPI_TOKEN` secret. The shared `v0.2.4` release uses the publisher identity
below for each of the six projects.

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

These values are a reference for maintaining the configured publishers. Do not
create duplicate pending publishers; each project has already participated in
the coordinated release.

## Distribution projects

Core and the CLI stay in `standard`. The additional project names and import
ownership are:

| PyPI project | Python import | Contents | Publisher status |
| --- | --- | --- | --- |
| `standard` | `std` | Core utilities, configuration, logging, CLI, and skill. | Published at `0.2.4`. |
| `standard-fastapi` | `std.fastapi` | FastAPI integration. | Published at `0.2.4`. |
| `standard-aws` | `std.aws` | AWS integration. | Published at `0.2.4`. |
| `standard-http` | `std.http` | HTTP client and authentication helpers. | Published at `0.2.4`. |
| `standard-cache` | `std.cache` | Redis client, caching decorators, and locks. | Published at `0.2.4`. |
| `standard-rdbms` | `std.rdbms` | Relational database configuration and session helpers. | Published at `0.2.4`. |

The five providers are optional runtime dependencies. Installing core does not
install or import them unless an application selects the relevant extra.

The core project's extras are convenience selectors: `standard[fastapi]`
installs `standard-fastapi`, `standard[aws]` installs `standard-aws`,
`standard[http]` installs `standard-http`, `standard[cache]` installs
`standard-cache`, and `standard[rdbms]` installs `standard-rdbms`. On each
release, the build workflow pins every extra and add-on dependency to that
release's exact shared version. There is no separate `standard-core` or
`standard-cli` project.

All six projects use the same publisher identity because one tag-based
workflow publishes the complete release:

| PyPI project | Workflow filename | Publisher | Owner | Repository | GitHub environment |
| --- | --- | --- | --- | --- | --- |
| `standard-fastapi` | `release.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |
| `standard-aws` | `release.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |
| `standard-http` | `release.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |
| `standard-cache` | `release.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |
| `standard-rdbms` | `release.yml` | GitHub Actions | `appunni-m` | `python-standard` | `pypi` |

If a new distribution is added later, configure its publisher on PyPI before
publishing. A pending publisher does not reserve a project name. See PyPI's
[pending publisher guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
[publisher setup guide](https://docs.pypi.org/trusted-publishers/adding-a-publisher/),
and [Trusted Publisher security model](https://docs.pypi.org/trusted-publishers/security-model/).

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
`std.<integration>` subtree.

### GitHub environment setup

The `pypi` environment is configured and was used for the coordinated
`v0.2.4` release. Each of the six projects must retain a Trusted Publisher for
`release.yml` and the `pypi` environment. If repository protection rules or
the environment name change, update the publisher entries to match.

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

Before a future release, merge the release-ready commit to `main`, wait for
that commit's CI and Testcontainers jobs to pass, and then push one annotated
tag. GitHub and PyPI settings require the corresponding repository and account
access; do not change publisher fields without coordinating the matching
configuration on both services.
