# Release update checks

The interactive Locdex CLI can check whether a newer **stable** Locdex release is available. This is a notification-only feature: it never installs, downloads or upgrades Python, npm, model files or runtime packages on its own.

## Behavior

- On interactive startup, a daemon thread queries the public PyPI metadata endpoint for `locdex` using a two-second network timeout. The welcome screen and model preload do not wait for this request.
- A successful version check is cached locally for **24 hours**, preventing repeated network requests every time Locdex starts.
- Pre-releases, development releases and fully yanked releases are ignored. The installed Python Locdex version is compared using PEP 440 version rules.
- When a newer stable release exists, Locdex displays a brief two-line message: the current and new version, followed by a single upgrade command appropriate for the installation channel. npm-launched sessions show an npm command; Python installations show a pip command. Notifications are rendered at safe terminal prompt boundaries rather than interrupting text being typed.
- Network errors and timeouts are nonfatal. The coding agent and inference worker remain usable.
- The checker requests only public `https://pypi.org/pypi/locdex/json` data, identifying the CLI version in a generic HTTP User-Agent. It does not send prompts, repository paths, source code, model telemetry or any project information.
- Automatic checks are skipped if the active interactive sandbox disallows network access or the process is in offline mode. This check is separate from model inference and does not enable cloud execution.

## Commands

```bash
locdex update status
locdex update check
locdex update off
locdex update on
```

Within the interactive CLI:

```text
/update
/update check
/update off
/update on
```

The `status` command reads the local cache without making a network request. The explicit `check` command performs a bounded live check, including when automatic checks are switched off, unless network access is disabled by the environment or active sandbox.

To disable network checks for a single process, set `LOCDEX_OFFLINE=1` or `LOCDEX_NO_UPDATE_CHECK=1`. CI environments also skip them automatically.

## Installing a release

Locdex never performs unattended package installations. Review the [GitHub release notes](https://github.com/Locdex/Locdex/releases) first.

For a Python installation, use the package manager used to install Locdex. For npm-managed installations, install a matching published `@locdex/cli` version; the npm launcher pins the corresponding Python core. An update notification does **not** imply that a matching npm release is already available.
