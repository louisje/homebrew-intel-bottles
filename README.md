# Homebrew Intel Bottles

Experimental, self-hosted Homebrew bottles built on GitHub's Intel macOS 15 runners for /usr/local (x86_64, Sequoia). **Bottles are not signed or notarized.** This is a personal binary cache, not a drop-in replacement for Homebrew/core.

## Install the external command

The GitHub repository name is homebrew-intel-bottles, so its short Homebrew tap name is louisje/intel-bottles:

    brew tap louisje/intel-bottles
    brew trust --command louisje/intel-bottles/intel-bottle
    brew intel-bottle help

`brew intel-bottle` is a dedicated external command. It handles only its documented subcommands; other Homebrew commands belong to native `brew`. Within its `install` action, Casks and third-party Tap Formulae are deliberately delegated to native Homebrew.

    # Inspect which provider would be used:
    brew intel-bottle status protobuf
    brew intel-bottle releases
    brew intel-bottle install --dry-run protobuf
    brew intel-bottle --help

    # Cloud jobs (pending/in-progress by default):
    brew intel-bottle jobs
    brew intel-bottle jobs aria2
    brew intel-bottle jobs --all
    brew intel-bottle jobs --all aria2

    # Install from Homebrew or a verified GitHub Release:
    brew intel-bottle outdated --verbose --sort=date --reverse
    brew intel-bottle install protobuf

    # Upgrade only outdated packages, without compiling Core locally:
    brew intel-bottle upgrade --dry-run vim
    brew intel-bottle upgrade vim
    brew intel-bottle upgrade --dry-run   # all outdated Formulae/Casks

    # Request a remote build, unless the same Formula version is already active:
    brew intel-bottle build llvm

    # Explicitly override duplicate protection if required:
    brew intel-bottle build --force llvm

### Optional Bash function router (Outland)

The **Shell function** is the optional interactive convenience layer; the Python extension itself no longer impersonates all of Homebrew. On a machine with `~/outland` installed:

    ln -s ../outland/configs/func.d/brew.func ~/.bash_functions.d/brew.func
    source ~/.bash_functions.d/brew.func

The function is maintained in `~/outland/configs/func.d/brew.func`. Existing `~/.bashrc` configuration loads files from `~/.bash_functions.d` at shell startup. The previous `alias brew='brew intel-bottle'` must be removed, and the function automatically unaliases `brew` when sourced (for shells that had already loaded the old alias).

| User command | Route |
| --- | --- |
| `brew outdated`, `brew outdated --verbose`, `brew outdated --sort=date --reverse` | Intel Bottle outdated handler (native output for plain command; enriched sorting when requested) |
| `brew install aria2` | `brew intel-bottle install aria2` |
| `brew install bun`, `brew install opencode-desktop` | Intel Bottle entrypoint resolves Cask/Tap and delegates to native Homebrew |
| `brew install xterm vim opencode-desktop` | Intel Bottle handles Core Formulae first; native Homebrew handles the Cask only after Core succeeds |
| `brew upgrade vim` | Intel Bottle checks whether vim is outdated and upgrades with an official/verified Bottle |
| `brew upgrade` | Find all outdated, unpinned packages and split Core Formulae from native Casks/Taps |
| `brew upgrade --cask foo`, `brew upgrade -v vim` | Native Homebrew (unsupported extension flags) |
| `brew install --cask foo`, `brew install --HEAD foo` | Native Homebrew (unsupported extension flags) |
| `brew jobs`, `brew status aria2`, `brew build aria2`, `brew releases` | Intel Bottle external command |
| `brew intel-bottle jobs` | Intel Bottle external command, **without double insertion** |
| `brew info`, `brew list`, `brew upgrade`, `brew tap`, `brew --version` | Native Homebrew directly |
| `brew --help` | Intel Bottle help **followed by** original Homebrew help |
| `brew intel-bottle --help` | Intel Bottle help only |
| `command brew --help` | Original Homebrew help only |

Native options like `brew install --cask`, `--formula`, `--HEAD`, `-v`, `-n` are not interpreted by the extension. The `upgrade` router accepts the extension's `--dry-run` and `--yes` flags; other upgrade flags (such as `--cask` or `--greedy`) go to native Homebrew. To bypass the Bash function for any command, use `command brew ...`; to temporarily disable it, use `unset -f brew`.

This wrapper affects only Bash sessions that source it; noninteractive scripts, other shells, and direct `/usr/local/bin/brew` invocations are unchanged.

### Cask and third-party Tap policy

**Only `homebrew/core` Formulae use the Intel Bottle fallback and cloud builder.** Casks and third-party Tap Formulae always use native Homebrew, which decides whether to download a Cask, pour the Tap's own Bottle, or build locally from source. The helper identifies Formulae and Casks together using `brew info --json=v2` (without `--formula`), so `brew install opencode-desktop claude-code-history-viewer` no longer fails a Formula-only lookup. Third-party Cask tokens are passed with their full Tap name, such as `jhlee0409/tap/claude-code-history-viewer`. This applies to both `brew install oven-sh/bun/bun` and the unqualified `brew install bun`: the helper resolves the Tap and forwards `bun` as `oven-sh/bun/bun` to avoid choosing a conflicting `homebrew/core/bun` formula. Explicit third-party references are sent straight to native Homebrew even if their Tap is not yet installed (Homebrew can auto-tap).

If one `brew install` invocation mixes Core Formulae with Casks or third-party Tap Formulae, **the request is split**. All `homebrew/core` roots are processed through Intel Bottle first. Only after their bottles have been installed does the command invoke native Homebrew for the Casks/third-party packages. If a Core Bottle is missing, independent Core roots with complete Bottle dependencies install first, while blocked roots are queued for cloud building. Native Casks/third-party packages remain postponed to avoid accidentally compiling Core dependencies locally. A Core root with third-party dependencies remains unsupported by the Intel Bottle planner. Install a Core root with native Homebrew explicitly using `command brew install …` only if local compilation is acceptable. Pure Cask/third-party requests still go straight to native Homebrew; they may involve local builds of their own dependencies. Explicit `brew intel-bottle build bun` is rejected when `bun` resolves to a third-party Tap.

    brew install aria2                       # homebrew/core -> Intel Bottle planner
    brew install bun                         # resolves -> native brew install oven-sh/bun/bun
    brew install oven-sh/bun/bun             # third-party -> native Homebrew
    brew install aria2 bun                   # core via Intel Bottle, then third-party native
    brew install opencode-desktop claude-code-history-viewer # Casks -> native Homebrew
    brew install aria2 opencode-desktop      # core via Intel Bottle, then Cask native
    brew install xterm vim opencode-desktop  # available Core roots install; missing ones and Cask wait
    brew intel-bottle status opencode-desktop # Cask -> native Homebrew
    brew intel-bottle status bun             # shows Tap ownership; no cloud build

### Outdated listing

The optional Bash wrapper sends **all** `brew outdated` calls to `brew intel-bottle outdated`. Without enhanced options, the command delegates to native Homebrew unchanged (including `--json=v2`). `--verbose` shows installed/current versions and the recipe edit date; `--sort=name|date|installed|current|version` sorts those records, and `--reverse` reverses the order. Version sorts are lexicographic. Dates now attempt to identify the **first verifiable Homebrew recipe commit** containing the currently available version (including explicit Formula revision), rather than the most recent recipe edit or upstream release date. A 24-hour cache is stored at `~/.cache/brew-intel-bottle/version-dates.json`. The lookup is deliberately bounded to 30 recent recipe commits; formulae with URL-inferred versions, complex DSL, older version transitions, third-party Taps, or unavailable history show `unknown` rather than a speculative date. History lookups can be slow and subject to GitHub API rate limits. Unknown dates always sort last even with `--reverse`. Native filters such as `--formula` and `--cask` pass through in enhanced mode. Use `command brew outdated ...` to bypass this wrapper.

### Upgrade routing

`brew upgrade vim` first checks `brew outdated --json=v2 vim`. If it is already current, there is nothing to do. If outdated, the Core Formula is upgraded using the same verified-bottle planner as `install` (an old installed version does **not** count as current). The command `brew upgrade` (with no package arguments) takes the full `brew outdated --json=v2` list and skips pinned packages. In both cases, the Core group is handled **before** native `brew upgrade` for Casks and third-party Tap packages; Homebrew's Cask outdated policy is preserved. If a Core Bottle is missing, unrelated Core upgrades whose Bottle dependency closures are complete proceed first. Blocked Core roots and native Cask/third-party upgrades remain deferred to prevent unintended Core source compilation.

Use `brew upgrade --dry-run` to inspect what would happen; it never installs or schedules jobs. Use `brew intel-bottle build FORMULA` to request missing cloud builds. `--yes` is an Intel Bottle option and is not forwarded to native Homebrew. Advanced flags or `command brew upgrade` bypass the router and **may** compile Core Formulae locally. Native Casks/third-party Formulae may still build their own dependencies locally.

Cloud jobs queries use the repository's GitHub Actions API. By default only queued, waiting, and in-progress Formula jobs are shown. With --all, active jobs plus jobs from up to 20 recent completed workflow runs are displayed (within the latest 100 workflow runs returned by GitHub). Older jobs without version metadata are labelled *version unverified*.

### Bottle selection and safety

For `homebrew/core` Formulae passed to install:

1. Resolve current Formula versions **including revisions** and recursive required/recommended dependencies through Homebrew. A bulk JSON query reduces repeated Homebrew startup overhead.
2. Keep installed dependencies instead of silently upgrading/downgrading them, even if the current Formula version differs. Homebrew still performs its own installation/linkage checks.
3. Prefer an official Bottle for the exact OS tag. Otherwise look for a matching version/revision, Sequoia tag, compatible Cellar, and SHA256 in GitHub Releases.
4. When Bottle files are missing, query active GitHub Actions **by Formula and pinned version**. Display the existing job and do not dispatch a duplicate. Older jobs without a version are shown as **unverified**, never claimed to match exactly; they also block implicit duplicate dispatch. Use --force only after reviewing them.
5. Group absent dependencies under an absent root Formula: that cloud root job already builds and bottles its dependencies. If the root Bottle is available but a dependency is not, schedule the missing dependency separately. Avoid separate dependency jobs when a missing root already covers them; two different roots may still rebuild the same dependency on separate runners.
6. If a new cloud build is needed, request confirmation and dispatch only uncovered roots/dependencies with explicit version pins. On a previous failure, display the failure link and offer a retry. Cloud builds are asynchronous.
7. When all necessary Bottles exist, show the install plan, download the archives, validate SHA256, and pass them to the original Homebrew. **Never automatically compile a missing source package locally.**

--dry-run is read-only, --yes skips interactive confirmation of self-hosted bottles, and build explicitly requests a GitHub Actions job. Remote builds are asynchronous: output is available for installation only after the GitHub Release is published.

Casks and third-party Tap Formulae are handed to native Homebrew during package resolution. Unsupported extension flags (`--HEAD`, `--cask`, `-v`, etc.) cause an explicit error in `brew intel-bottle install`, while the Bash wrapper sends regular `brew install` invocations with those flags straight to native Homebrew. For now, only Intel macOS 15 with the standard /usr/local prefix is supported by the self-hosted fallback. There is no automatic upgrade interception yet, and older bottle versions are rejected if they do not match the current Formula. The Bottle JSON's original upstream root_url does not control installation because the extension downloads local archives.

## Build and publish

Run the Build Intel Bottles GitHub Actions workflow manually, or invoke:

    gh workflow run build.yml -R louisje/homebrew-intel-bottles -f formulae=llvm,rust,openvino,boost,protobuf -f skip_if_bottled=true

The workflow runs up to five matrix jobs on macos-15-intel. The command adds the versions input (formula=version including the Homebrew revision). The runner validates each pinned version against its own brew info metadata before beginning an expensive build. Job names expose Formula and version for robust status queries. Manual builds without version pins are allowed, but clients consider their versions unverified.

The workflow builds dependencies from source, **bottles those dependencies first**, and then builds the root Formula. Independent per-Formula GitHub Releases contain valid Bottle+JSON pairs and SHA256SUMS. If a root build fails after dependencies were bottled, their valid archives can still be published as a partial Release, while the job correctly reports failure.

Each tag is bottles-RUN_ID-ATTEMPT-FORMULA. Original Bottle archive filenames are kept intact. Logs and metadata are separately retained as GitHub Actions artifacts for 30 days.

Large builds can time out, and bottles may have CPU, macOS, Cellar, or source-version incompatibilities. Verify installation in a noncritical environment before relying on them.

## Development and tests

    python3 -m unittest discover -s tests -v
    python3 -m py_compile cmd/brew-intel-bottle