# OCP KubeVirt platform

<a href="https://idan-maimon.github.io/kubevirt-workflows/docs/implementation-status/">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/implementation-status/status-dark.svg">
    <img alt="OCP KubeVirt platform build status" src="docs/implementation-status/status-light.svg">
  </picture>
</a>

Click the diagram for the interactive version: hover a component for its details, filter by status,
click through to its repository.

**Updating the status:** edit [`docs/implementation-status/components.json`](docs/implementation-status/components.json), then run
`python3 docs/implementation-status/_generate.py` and commit the regenerated files.

## Documents

| | |
|---|---|
| [Architecture](docs/architecture.md) | Requirements, quality goals, constraints, decisions, risks |
| [Naming convention](docs/naming-convention.md) | Names, zones and labels |
| [Acceptance tests](acceptance-tests/acceptance-tests.md) | Provisioning, modification, upgrade and deletion tests, with their acceptance criteria |
| [Procedures](docs/procedures/README.md) | Every platform procedure, by layer |
| [Animations](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/) | Each procedure, step by step |
