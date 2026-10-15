# Homebrew Intel Bottles

Experimental, self-hosted Homebrew bottles built on GitHub's Intel macOS 15 runners for /usr/local (x86_64, Sequoia). **Bottles are not signed or notarized.** This is a personal binary cache, not a drop-in replacement for Homebrew/core.

## Install the external command

The GitHub repository name is homebrew-intel-bottles, so its short Homebrew tap name is louisje/intel-bottles:

    brew tap louisje/intel-bottles
    brew trust --command louisje/intel-bottles/intel-bottle
    brew intel-bottle help

Homebrew commands not explicitly handled by the extension are forwarded to the real /usr/local/bin/brew.

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
    brew intel-bottle install protobuf

    # Request a remote build, unless the same Formula version is already active:
    brew intel-bottle build llvm

    # Explicitly override duplicate protection if required:
    brew intel-bottle build --force llvm

### Optional transparent Bash alias

After validating the extension on your machine, **opt in**:

    alias brew='brew intel-bottle'

With this alias, **brew --help, brew -h, brew help**, and **brew intel-bottle --help** all display the combined Intel Bottle help, including extensions (jobs, status, build, releases) and common native Homebrew commands that pass through unchanged. Native brew list, brew info, brew upgrade, brew uninstall, and brew --version continue unchanged; brew jobs is equivalent to brew intel-bottle jobs.

To see the full original Homebrew help or bypass the alias:

    command brew --help
    command brew list

To disable the alias in the current shell:

    unalias brew

The alias only affects interactive Bash by default. Existing Bash sessions need to source ~/.bash_aliases.d/brew.alias or start a new shell after updating the alias. Scripts, direct /usr/local/bin/brew invocations, and other shells are not transparently intercepted.

### Cask and third-party Tap policy

**Only `homebrew/core` Formulae use the Intel Bottle fallback and cloud builder.** Casks and third-party Tap Formulae always use native Homebrew, which decides whether to download a Cask, pour the Tap's own Bottle, or build locally from source. The helper identifies Formulae and Casks together using `brew info --json=v2` (without `--formula`), so `brew install opencode-desktop claude-code-history-viewer` no longer fails a Formula-only lookup. Third-party Cask tokens are passed with their full Tap name, such as `jhlee0409/tap/claude-code-history-viewer`. This applies to both `brew install oven-sh/bun/bun` and the unqualified `brew install bun`: the helper resolves the Tap and forwards `bun` as `oven-sh/bun/bun` to avoid choosing a conflicting `homebrew/core/bun` formula. Explicit third-party references are sent straight to native Homebrew even if their Tap is not yet installed (Homebrew can auto-tap).

If a single `brew install` invocation mixes Formulae and Casks, or Core and third-party Formulae, **the entire batch is forwarded to native Homebrew** (including any Core dependencies). Similarly, Core Formulae whose dependency graph contains a third-party Formula fall back to native Homebrew. In these situations native Homebrew may compile from source locally; the extension prints a notice but never dispatches these third-party builds to GitHub Actions. To keep Core Formulae on the cloud Bottle path, install them separately. An explicit `brew intel-bottle build bun` is rejected when `bun` resolves to a third-party Tap.

    brew install aria2                       # homebrew/core -> Intel Bottle planner
    brew install bun                         # resolves -> native brew install oven-sh/bun/bun
    brew install oven-sh/bun/bun              # third-party -> native Homebrew
    brew install aria2 bun                   # mixed -> native Homebrew for both
    brew install opencode-desktop claude-code-history-viewer # Casks -> native Homebrew
    brew install aria2 opencode-desktop      # mixed Formula/Cask -> native Homebrew
    brew intel-bottle status opencode-desktop # Cask -> native Homebrew
    brew intel-bottle status bun             # shows Tap ownership; no cloud build

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

Other install forms (casks, --HEAD, special build flags, etc.) are forwarded unchanged to Homebrew. For now, only Intel macOS 15 with the standard /usr/local prefix is supported by the self-hosted fallback. There is no automatic upgrade interception yet, and older bottle versions are rejected if they do not match the current Formula. The Bottle JSON's original upstream root_url does not control installation because the extension downloads local archives.

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