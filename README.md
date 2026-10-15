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

    # Install from Homebrew or a verified GitHub Release:
    brew intel-bottle install protobuf

    # Request a remote build:
    brew intel-bottle build llvm

### Optional transparent Bash alias

After validating the extension on your machine, **opt in**:

    alias brew='brew intel-bottle'

Now brew install protobuf uses the fallback handler, while native commands such as brew list, brew info, brew upgrade, brew uninstall, brew --version, and brew --help continue unchanged. To bypass the alias or disable it:

    command brew list
    unalias brew

The alias only affects interactive Bash by default. Scripts, direct /usr/local/bin/brew invocations, and other shells are not transparently intercepted.

### Bottle selection and safety

For plain formula names passed to install:

1. Resolve the current formula version and transitive required/recommended dependencies through Homebrew, in topological order.
2. Keep dependencies already installed at the same version; refuse to silently replace dependencies installed at another version.
3. Prefer an official Bottle with the exact OS tag. Otherwise look for a matching version, Sequoia tag, and compatible Cellar in our GitHub Release assets.
4. Show the installation plan. Verify each downloaded tar.gz against its corresponding Bottle JSON SHA256 before passing the local archive path to /usr/local/bin/brew install.
5. If any required Bottle is missing, stop before installing anything and offer to dispatch a GitHub Actions build. **Never automatically compile a missing source package locally.**

--dry-run is read-only, --yes skips interactive confirmation of self-hosted bottles, and build explicitly requests a GitHub Actions job. Remote builds are asynchronous: output is available for installation only after the GitHub Release is published.

Other install forms (casks, --HEAD, special build flags, etc.) are forwarded unchanged to Homebrew. For now, only Intel macOS 15 with the standard /usr/local prefix is supported by the self-hosted fallback. There is no automatic upgrade interception yet, and older bottle versions are rejected if they do not match the current Formula. The Bottle JSON's original upstream root_url does not control installation because the extension downloads local archives.

## Build and publish

Run the Build Intel Bottles GitHub Actions workflow manually, or invoke:

    gh workflow run build.yml -R louisje/homebrew-intel-bottles -f formulae=llvm,rust,openvino,boost,protobuf -f skip_if_bottled=true

The workflow runs up to five matrix jobs on macos-15-intel, building dependencies from source before the target, and attempting to bottle installed dependencies too. Each **successful formula independently** publishes a GitHub Release with the Bottle tarballs, JSON metadata, and SHA256SUMS. A failed or timed-out formula does not prevent other successful formulae from publishing.

Each tag is bottles-RUN_ID-ATTEMPT-FORMULA. Original Bottle archive filenames are kept intact. Logs and metadata are separately retained as GitHub Actions artifacts for 30 days.

Large builds can time out, and bottles may have CPU, macOS, Cellar, or source-version incompatibilities. Verify installation in a noncritical environment before relying on them.

## Development and tests

    python3 -m unittest discover -s tests -v
    python3 -m py_compile cmd/brew-intel-bottle
