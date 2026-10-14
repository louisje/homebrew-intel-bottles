# Homebrew Intel Bottles

Experimental builds of Homebrew bottles on GitHub-hosted macOS 15 Intel runners.

The workflow builds `gcc`, `apache-arrow`, `openjdk`, `aws-sdk-cpp`, and `grpc` independently. Successful bottles and build logs are retained as workflow artifacts for 30 days. Builds may fail due to disk, runner limitations, unavailable dependencies, or Homebrew bottle relocation requirements.

These bottles are experimental and not automatically published to a Homebrew tap.
