# OCP KubeVirt platform

<a href="https://idan-maimon.github.io/kubevirt-workflows/docs/status/">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/status/status-dark.svg">
    <img alt="OCP KubeVirt platform build status" src="docs/status/status-light.svg">
  </picture>
</a>

Click the diagram for the interactive version: hover a component for its details, filter by status,
click through to its repository.

**Updating the status:** edit [`docs/status/components.json`](docs/status/components.json), then run
`python3 docs/status/_generate.py` and commit the regenerated files.

## Documents

| | |
|---|---|
| [Architecture](docs/architecture.md) | Requirements, quality goals, constraints, decisions, risks |
| [Naming convention](docs/naming-convention.md) | Names, zones and labels |
| [Procedures](docs/procedures/README.md) | Every platform procedure, by layer |
| [Animations](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/) | Each procedure, step by step |
