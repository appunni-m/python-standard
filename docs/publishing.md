# Publishing documentation

## Local build

```bash
make docs-install
make docs-build
```

The generated site is written to `site/` and is excluded from Git.

## GitHub Pages setup

The repository includes `.github/workflows/docs.yml`. It builds the docs with the pinned documentation dependencies and publishes them on pushes to `main` or a manual workflow run.

### First deploy

1. Push this project's `main` branch to `origin` to start the first Pages deployment.
2. In **Settings → Pages**, select **GitHub Actions** as the build and deployment source.
3. Push a commit to `main`, or run the **Documentation** workflow from the Actions tab. The workflow builds `site/`, uploads it as a Pages artifact, and deploys it to the `github-pages` environment.
4. Open the deployment job's environment URL to see the published site.

The workflow grants only `contents: read`, `pages: write`, and `id-token: write`, and uses GitHub's recommended Pages actions. See [GitHub's publishing-source guide](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site), [GitHub's custom-workflow requirements](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), and [Zensical's GitHub Pages guide](https://zensical.org/docs/publish-your-site/).

The expected Pages URL, `https://appunni-m.github.io/python-standard/`, is configured as `site_url` in `zensical.toml`. Confirm the URL after the first successful deployment and adjust `site_url` if GitHub reports a different address. Zensical recommends this setting for canonical page metadata; instant navigation and instant previews also require it.

## Resolve the PyPI distribution name

The current PyPI project page for `standard` returned 404 in the browser used during setup, while an indexed PyPI page still reports an unrelated `standard 1.0.3` release from 2018. The name's current availability and ownership are therefore unconfirmed. Before publishing, verify the project through the PyPI account that will own it. Do not add a publisher to a project you do not control. Checkout installs such as `python -m pip install '.[fastapi]'` install this repository's wheel and remain available.

PyPI's [Name Retention policy](https://docs.pypi.org/project-management/name-retention/) treats reassignment as a last resort. A project is considered abandoned only when its owner is unreachable, it has had no release in the past twelve months, and its homepage has had no owner activity (or no homepage is listed). Reusing a name for a different project has additional requirements, including documented attempts to contact the owner, evidence that the existing project is not being used, evidence that the proposed project meets the policy's notability criteria, and an explanation of why another name is not an acceptable alternative. Age alone does not establish eligibility.

No owner contact or PyPI name-retention request has been made. If keeping `standard` is essential, first seek an owner-approved transfer; if the owner cannot be reached, gather the policy evidence and follow PyPI's support process. The existing project's reachability, homepage activity, and current usage have not been established, so do not describe it as abandoned. If a transfer is unavailable, get approval for a different distribution name before changing the project metadata.

## Configure PyPI Trusted Publishing

The release workflow is present at `.github/workflows/release.yml`. It uses PyPI Trusted Publishing through GitHub's OIDC identity, so the publishing job does not need a long-lived `PYPI_TOKEN` secret. A hosted release run has not been verified.

### Publisher fields

When the distribution name is available to this project, configure a GitHub Actions publisher whose values exactly match the workflow identity:

| PyPI or GitHub field | Value |
| --- | --- |
| PyPI project name | `standard` (use only after confirming the name is available and owned by this project) |
| Publisher | GitHub Actions |
| Owner | `appunni-m` |
| Repository | `python-standard` |
| Workflow filename | `release.yml` (the repository file is `.github/workflows/release.yml`) |
| GitHub environment | `pypi` |

PyPI matches the owner, repository, workflow filename, and optional environment against the GitHub Actions identity. The publisher form asks for the workflow filename, not the `.github/workflows/` path. See PyPI's [publisher setup guide](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).

If a `standard` project already exists under the owner's account, add the publisher from that project's **Publishing** page. If the name is available, create a pending publisher from the PyPI account's **Publishing** page. If it belongs to someone else, obtain an approved transfer or choose another distribution name first. PyPI says a pending publisher does not reserve a name before first publication ([pending publisher guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)).

### GitHub environment setup

An owner or repository administrator must configure the environment in `appunni-m/python-standard`:

1. Open **Settings → Environments** and create an environment named `pypi`.
2. Restrict deployment refs to tags matching `v*`, which matches this workflow's release trigger.
3. Restrict this environment to tags matching `v*` and require a trusted maintainer to approve publishing jobs when the repository plan supports reviewers.

The workflow's publish job references `pypi`; GitHub can create a missing environment automatically, but only an owner or administrator can configure its protection rules. See GitHub's [environment setup guide](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) and [deployment branch and tag rules](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments#deployment-branches-and-tags).

### Version-tag release flow

`.github/workflows/release.yml` runs when a tag beginning with `v` is pushed. The workflow runs the reusable CI workflow first, then:

1. Requires the tag to equal `v` plus `[project].version` in `pyproject.toml` (for version `0.1.0`, the tag is `v0.1.0`).
2. Builds a wheel and source distribution, checks them with `twine check`, and stores the files as workflow artifacts.
3. Publishes those artifacts to PyPI from the `pypi` environment using `pypa/gh-action-pypi-publish` pinned to verified commit `dc37677b2e1c63e2034f94d8a5b11f265b73ba33` (v1.14.2).

For a release, first resolve the PyPI name and complete the owner-only setup above. Then update `project.version`, run the local checks, create the matching tag, and push it. The container check requires Docker, so run it locally when Docker is available; the release workflow's CI job runs it in CI.

```bash
make check
make test-e2e
git tag vX.Y.Z
git push origin vX.Y.Z
```

Replace `X.Y.Z` with the exact version in `pyproject.toml`. The pushed tag starts the workflow; monitor the **Release** workflow in GitHub Actions and verify the published files on the project's PyPI page. Treat release tags as immutable: publish a correction with the next version.

Before the first release, push `main`, configure the repository's `pypi` environment, confirm the PyPI project name is available and controlled by this project, and register the matching Trusted Publisher in PyPI. GitHub environment settings require a repository owner or administrator; PyPI publisher setup requires control of the corresponding PyPI project or account.
