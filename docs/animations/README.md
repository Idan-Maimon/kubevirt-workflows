# Animations

One animation per procedure, walking its flow step by step. Each step shows the real call,
payload and response beneath the diagram.

**Open them from GitHub Pages** (the links below), or open a file locally in any browser. Each
file is self-contained, with no dependencies and no network calls, so it also works air-gapped.

| Key | Action |
|---|---|
| → / ← | Next / previous step |
| Space | Play / pause |
| `#step=7` on the link | Open on step 7 |
| `#vm` on the link | Open on the second toggle option (e.g. Virtual, Any node) |

Base address: `https://idan-maimon.github.io/kubevirt-workflows/docs/animations/`

---

## Inventory

| # | Animation | Procedure |
|---|---|---|
| 01 | [Add Server to MCE](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/01-add-server-to-mce.html) | [01](../procedures/01-add-server-to-mce.md) |
| 02 | [Remove Server from MCE](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/02-remove-server-from-mce.html) | [02](../procedures/02-remove-server-from-mce.md) |
| 21 | [Create VM](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/21-create-vm.html) | [21](../procedures/21-create-vm.md) |
| 22 | [Delete VM](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/22-delete-vm.html) | [22](../procedures/22-delete-vm.md) |

## Tenant clusters

| # | Animation | Procedure |
|---|---|---|
| 03 | [Create Hosted Cluster](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/03-create-hosted-cluster.html) | [03](../procedures/03-create-hosted-cluster.md) |
| 04 | [Update NodePool](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/04-update-nodepool.html) | [04](../procedures/04-update-nodepool.md) |
| 05 | [Delete Hosted Cluster](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/05-delete-hosted-cluster.html) | [05](../procedures/05-delete-hosted-cluster.md) |
| 19 | [Remove Server from NodePool](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/19-remove-server-from-nodepool.html) | [19](../procedures/19-remove-server-from-nodepool.md) |
| 20 | [Remove Nodes: Customer Picks, or Any](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/20-remove-node-flow-draft.html) **(draft, for review)** | [19](../procedures/19-remove-server-from-nodepool.md) |

## KubeVirt clusters

| # | Animation | Procedure |
|---|---|---|
| 06 | No animation | [06](../procedures/06-create-kv-cluster.md) |
| 07 | [Add Bare-Metal Node to a KV Cluster](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/07-add-bm-to-kv-cluster.html) | [07](../procedures/07-add-bm-to-kv-cluster.md) |
| 08 | [Remove Bare-Metal Node from a KV Cluster](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/08-remove-bm-from-kv-cluster.html) | [08](../procedures/08-remove-bm-from-kv-cluster.md) |
| 09 | [Decommission a KV Cluster](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/09-decommission-kv-cluster.html) | [09](../procedures/09-decommission-kv-cluster.md) |

## Seeds and hubs

| # | Animation | Procedure |
|---|---|---|
| 10 | No animation | [10](../procedures/10-create-seed-cluster.md) |
| 11 | [Add Bare-Metal Node to a Seed Cluster](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/11-add-bm-to-seed-cluster.html) | [11](../procedures/11-add-bm-to-seed-cluster.md) |
| 12 | No animation | [12](../procedures/12-create-customer-mce.md) |
| 23 | [Create UPI Cluster](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/23-create-upi-cluster.html) | [23](../procedures/23-create-upi-cluster.md) |

## Upgrades

| # | Animation | Procedure |
|---|---|---|
| 13 | [Upgrade Hosted Cluster Workers](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/13-upgrade-hosted-cluster-workers.html) | [13](../procedures/13-upgrade-hosted-cluster-workers.md) |
| 14 | [Upgrade Hosted Cluster Control Plane](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/14-upgrade-hosted-cluster-control-plane.html) | [14](../procedures/14-upgrade-hosted-cluster-control-plane.md) |
| 15 | [Upgrade an MCE Hub](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/15-upgrade-mce-hub.html) | [15](../procedures/15-upgrade-mce-hub.md) |
| 16 | [Upgrade a KV Cluster](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/16-upgrade-kv-cluster.html) | [16](../procedures/16-upgrade-kv-cluster.md) |
| 17 | [Upgrade a Seed Cluster](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/17-upgrade-seed-cluster.html) | [17](../procedures/17-upgrade-seed-cluster.md) |

## Migration

| # | Animation | Procedure |
|---|---|---|
| 18 | [Migrate a Hosted Cluster to Another Version Band](https://idan-maimon.github.io/kubevirt-workflows/docs/animations/18-migrate-hosted-cluster-version-band.html) | [18](../procedures/18-migrate-hosted-cluster-version-band.md) |

---

## Changing an animation

All animations are generated from [`_generate.py`](_generate.py). Edit a step there and run:

```
python3 _generate.py
```

Never edit the HTML by hand: the next run overwrites it.
