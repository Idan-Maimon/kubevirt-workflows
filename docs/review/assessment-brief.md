# Assessment brief: OCP KubeVirt platform architecture

You are an independent reviewer. Assess the architecture of an internal OpenShift platform
and how well it matches the systems built to implement it. You were not involved in the
work. Your value is a read that is not anchored on ours, so verify everything against the
sources rather than trusting any summary, including this one.

---

## 1. Ground rules

1. **Everything is read-only.** Do not edit, commit, branch, push, open pull requests, comment
   on issues or change any repository, including ours. You report; the architect decides what
   changes.
2. **Do not run anything that writes** to a cluster, an API or a repository. Reading files,
   running a repository's own unit tests locally, and reading public endpoints is fine.
3. **Ignore credentials.** If you come across a token, secret or kubeconfig, do not use it,
   copy it or print it. Mention only that it exists and where.
4. **Cite evidence.** Every finding names the repository, file and line, and quotes the text
   or code it rests on. Mark each claim as **verified** (you read it) or **inferred** (you
   reasoned to it).
5. **Respect authorship** (section 3). The architecture document is the architect's. Where it
   and an implementation disagree, do not assume either is right. Say which, if either, is
   wrong and why.

---

## 2. What the platform is

An internal cloud for OpenShift clusters, run by the RedBull infrastructure team for hundreds
of clusters. Tenants get **hosted clusters** (HyperShift hosted control planes). Their workers
are **KubeVirt VMs** that look to OpenShift like bare-metal machines: each VM is exposed
through a virtual Redfish BMC and installed by MCE's Agent-based installer, exactly like a
physical server.

The layers, top to bottom:

| Layer | What it is |
|---|---|
| Tenant hosted cluster | Control plane as pods on a Customer MCE hub; workers are VMs, one NodePool per zone |
| Customer MCE | The tenant hub. Runs HyperShift and the Agent installer. Itself runs on VMs |
| KV cluster | Where the VMs physically run. A hosted cluster whose control plane runs on the Seed and whose workers are bare-metal KubeVirt hosts |
| Seed | One bare-metal cluster per zone, installed by hand. Hosts the KV clusters' control planes |
| Bare metal | Physical servers, tracked by server-scan |

Workers are supplied from **pools**. A pool is one InfraEnv: a server type, a zone and a VM size.
Pools are shared by every tenant and kept topped up ahead of demand. Desired cluster state
lives in Git and is applied by ArgoCD. Multi-step automation runs in Temporal workflows.

---

## 3. Repositories

Local clones sit under `~/claude/`. Check each clone's last commit; some may be days behind.

### 3.1 Ours

| Repo | Local path | Notes |
|---|---|---|
| `github.com/Idan-Maimon/kubevirt-workflows` | `~/claude/kubevirt-workflows` | The architecture and its design documents |

What is in it, and how much weight each part carries:

| Path | Author | Weight |
|---|---|---|
| `docs/architecture.md` | **The architect.** Arc42-style, sections 1 to 9 and 12 | **Authoritative.** The document under assessment |
| `docs/inventory-controller.md` | Written with an AI assistant from the architect's decisions | Design. Describes herzi |
| `docs/kv-capacity-controller.md` | Same | Specification of a controller **not yet built** |
| `docs/vm-placement.md` | Same | Describes placement in `create-vm`, plus changes the architecture requires |
| `docs/procedures/00`–`18` and `docs/animations/` | AI-generated, **not reviewed by the architect** | Drafts. A conflict with the architecture is more likely the draft's fault |
| `docs/GAPS.md` | AI-generated | Stale, written after procedure 03 |
| `workflow/`, `nodepools/`, `argocd/` | Early prototype | **Superseded.** History only |

### 3.2 Primary read-only repos

Assess these against the architecture in depth.

| Repo | Local path | What it is |
|---|---|---|
| `team-redbull/server-scan` | `~/claude/external/server-scan/repo` | The inventory of record for about 2,500 physical servers, and VMs when they are registered. Vendor collectors (UCS Central, Intersight, OpenManage, OneView, Redfish) write to MongoDB. Per-cluster jobs report which servers are in use. It owns the **install reservation lock** and `GET /api/v1/servers/available`. Start with `README.md`, `docs/arc42.md`, `docs/adr/` (48 ADRs) |
| `team-redbull/segments-manager` | `~/claude/external/segments-manager/repo` | The per-site pool of VLAN segments (/24) and which cluster holds each. FastAPI and MongoDB, atomic allocation. Start with `README.md`, `ARCHITECTURE.md` |

### 3.3 Context repos, read-only

Read these as far as you need to judge the architecture. Do not review their code quality.

| Repo | Local path | What it is |
|---|---|---|
| `team-redbull/workflows` | `~/claude/external/workflows/repo` | The Temporal orchestrator: `add-server-to-mce`, `create-vm`, `provision-cluster`, `upgrade-cluster`, segment workflows. `CLAUDE.md` is long and dense but records every decision; `docs/design/` has the designs |
| `team-redbull/herzi` | `~/claude/external/herzi/repo` | The inventory controller, one per MCE hub. Go. `docs/design/herzi-design.md` |
| `LiadYahav/wingman` | `~/claude/external/wingman/repo` | The self-service portal (Next.js and FastAPI): cluster create, flavors, MCE placement, upgrades, inventory, server-scan and segments-manager views. `docs/ecosystem/README.md` maps the whole ecosystem; `docs/ideas/architecture-fit.md` is its reading of our architecture; `docs/adr/` |

A live Wingman runs at `https://wingman.apps.cluster-2qsc5.2qsc5.sandbox5410.opentlc.com`. It
needs an OpenShift OAuth login, so expect to see only its login page and public health routes.

### 3.4 Ignore

| Repo | Why |
|---|---|
| `team-redbull/segment_manager` (`~/claude/external/segment_manager`) | Dead since June. Superseded by `segments-manager` |
| `team-redbull/ServerScanner` | Dead since May. Superseded by `server-scan` |
| `external/vmar` (`virtual-machine-agent-reconciler`) | Stale prototype since July |
| `external/hypershift`, `external/assisted`, `external/capi-agent` | Upstream projects. Use only to check a claim about upstream behaviour |

Referenced but not cloned: `redbull-platform` (the ArgoCD repo holding the deployed charts),
`kubevirt-redfish`, `kv-agents`, `pxe-map-api`, `dhcp_scope_manager`.

---

## 4. Decisions made but not yet written down

The architect settled these in conversation, and they are not in `architecture.md` yet. Treat
them as decided. Flag a document that contradicts them, but do not reopen them unless one is
technically unworkable.

- **Zones are soft.** A zone is a label assigned by the InfraEnv an agent registers from, not a
  recorded physical location. Rack data is being added to server-scan, after which zones can
  be derived from racks.
- **A site** is a physical place containing several zones. One MCE hub per site per OpenShift
  version band.
- **VMs will be registered in server-scan**, collected by scanning the KV clusters. Decided, not
  built.
- **One document per owned artifact:** the platform, server-scan, segments-manager, the
  orchestrator, and a system document. Layers are a view inside the system document.

---

## 5. Suggested reading order

1. This brief.
2. `kubevirt-workflows/docs/architecture.md`, in full, twice: once for the story, once for
   cross-references.
3. `kubevirt-workflows/docs/inventory-controller.md`, `kv-capacity-controller.md`,
   `vm-placement.md`.
4. `wingman/docs/ecosystem/README.md`, the best map of how the systems connect today.
5. server-scan: `README.md`, `docs/arc42.md`, the ADRs on the install lock, availability and
   classification.
6. segments-manager: `README.md`, `ARCHITECTURE.md`, the allocation code.
7. workflows: the `create-vm`, `add-server-to-mce` and `provision-cluster` sections of
   `CLAUDE.md`, and `docs/design/`.
8. herzi: `README.md`, `docs/design/herzi-design.md`.
9. A sample of the procedures, to judge whether they are usable.

---

## 6. What to assess

### A. The architecture on its own

- Do requirements, quality goals, quality scenarios, quality controls, constraints,
  decisions and risks trace to one another? Is any decision unmotivated, or any quality goal
  served by no control?
- Do the sections contradict each other? Compare decisions with quality controls, the
  glossary, the naming conventions and the context section.
- Is each decision technically sound for OpenShift, HyperShift, MCE, KubeVirt and the Agent
  platform as they actually behave? Pay particular attention to:
  - AD3, AD8 and C2: NodePools across several KV clusters through the Agent platform;
  - AD21: pools keyed on server type, zone and size;
  - AD23 and AD24: destroy-on-release, and in-place upgrades;
  - AD25: version skew between workers and control plane;
  - AD26 to AD31: the capacity model, meaning growth to 40 nodes at 15% free CPU, the standby
    cluster, placement serialised per zone, node-level bin-packing with `HighNodeUtilization`
    and `CompactAndScale`, and one shared policy file.
- Arc42 conformance: which sections are missing or empty (building block view, runtime
  views, context diagram, risks), and which absences matter most.

### B. The architecture against the implementations

For each of server-scan, segments-manager, workflows, herzi and Wingman:

- What does the architecture assume this system does? Does it?
- Where they disagree, is the document behind the code, is the code wrong against a decision,
  or is the decision itself the problem?
- Contracts at the boundaries: the hostname prefix `^ocp-<infraEnv>`, the install lock, the
  availability semantics, segment allocation and release, workflow ids and slots, and the
  InfraEnv and cluster naming.

### C. The supporting documents against the architecture

- Do the controller specifications and `vm-placement.md` implement AD21 to AD31 faithfully?
- Do the procedures still follow the architecture? Sample at least 01, 03, 04, 05, 13 and 16.

### D. Gaps and risks

- Steps that have no owner: something must happen, and nothing in any repository does it.
- Failure modes the risk section misses.
- Decisions that will be expensive to reverse, especially naming (cluster names are
  immutable).

---

## 7. Expected output

Write one Markdown report, `assessment-report.md`, with these sections in this order.

### 7.1 Executive summary
At most ten lines. Your overall verdict on the architecture's soundness and on how far the
implementations match it, the three most important findings, and whether anything should
stop work now.

### 7.2 Findings

One row per finding, most severe first.

| Field | Content |
|---|---|
| ID | `F-01`, `F-02`, … |
| Severity | Critical, High, Medium or Low (below) |
| Category | `consistency`, `soundness`, `implementation-drift`, `gap`, `risk`, `naming`, `arc42` |
| Where | Repo, file and line for every side of the issue |
| Evidence | The quoted text or code |
| Why it matters | The concrete consequence: what breaks, for whom, when |
| Recommendation | What to change, and in which repository or document |
| Confidence | Verified or inferred, and why |

Severity:

| Level | Meaning |
|---|---|
| **Critical** | Will cause data loss, tenant outage, cross-tenant exposure or a design that cannot work as written |
| **High** | A decision or contract that is wrong or contradicted, and will cost real rework if built on |
| **Medium** | An inconsistency or gap that misleads readers or leaves a step unowned |
| **Low** | Wording, a stale reference, a missing cross-reference |

### 7.3 Decisions to challenge
Decisions you believe are wrong or under-argued. For each: the decision, the strongest case
against it, the alternative, and what evidence would settle it. Keep this separate from
findings. These are judgements, not defects.

### 7.4 Alignment matrix
Rows are architecture decisions and key assumptions. Columns are server-scan,
segments-manager, workflows, herzi and Wingman. Each cell is `matches`, `diverges`,
`not implemented` or `n/a`, with a finding ID where it diverges.

### 7.5 Questions for the architect
Things you could not resolve from the sources, each phrased so the answer changes a finding.

### 7.6 What is sound
Parts you checked and found solid, briefly. These tell the architect what not to touch.

### 7.7 Top ten actions
Ordered by value for effort. Each names the owner (architecture, our docs, or a team repo) and
the findings it closes.

### 7.8 Not checked
What you did not read or could not verify, so silence is not mistaken for approval.

---

## Appendix: items already known

**Read this only after you have formed your own findings.** It lists problems we already know
about, so you can confirm or refute them and report what we missed. Do not count a known item
as a finding unless you add evidence or show it is worse than stated.

- `create-vm` places VMs in parallel without a lock; parallel runs land on one cluster (AD29
  requires one per zone).
- `create-vm`'s buffer defaults to 30% and is configured per deployment, not read from one
  policy file (AD31 says 15%, shared).
- Nothing calls `create-vm` automatically, so VM pools are never replenished.
- No `update-nodepool` workflow exists, so the KV Capacity Controller could not grow a cluster.
- `provision-cluster` waits for a human merge, which a standby KV cluster's lead time must
  absorb.
- The InfraEnv naming in code (`x201-zone-a-8`), in the live chart
  (`dell-r660-site-a-128c-1024gb-5tb`) and in architecture §9 (`conf203-zone-a-medium`) all
  differ. Cluster naming in Wingman and the workflows (`ocp4-<env>-…`) differs from §9
  (`<env>-<site>-hc-<tenant>`, no `ocp4`).
- AD8 says each NodePool targets a different KV cluster; with several KV clusters per zone
  and shared InfraEnvs, a NodePool draws from all of a zone's KV clusters.
- AD10 (stretched bare-metal hub) conflicts with AD19 and AD20 (Customer MCE on VMs).
- AD5, AD13 and §8.2 say all state goes through Git; AD22 sends machine-level objects straight
  to the API.
- The Upgrade quality controls mention replacing NodePools; AD24 says in-place.
- Procedures 02, 04, 05, 09 and 13 predate AD23, AD24 and AD26 and still describe
  return-to-pool, shrinking and replacement upgrades.
- herzi is in dry run on every pool and has never run against a real hub.
- `HighNodeUtilization` and `CompactAndScale` are not confirmed on any KV cluster.
- §8.2 does not name herzi, Wingman or server-scan's role in VM registration.
