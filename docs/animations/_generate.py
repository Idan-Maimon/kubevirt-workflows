#!/usr/bin/env python3
"""Emit one self-contained animation per workflow.

Every output file is standalone: inline SVG, CSS and vanilla JS, no CDN, no
imports, nothing fetched at runtime. That is deliberate — these have to open by
double-click inside an air-gapped environment.

Run:  python3 _generate.py        (writes *.html beside this script)
"""
from pathlib import Path
import json

HERE = Path(__file__).parent

# --------------------------------------------------------------------------
# Node library. Coordinates are on a 1000 x 560 canvas.
# --------------------------------------------------------------------------
def N(x, y, t, s, w=170, h=54):
    return {"x": x, "y": y, "w": w, "h": h, "t": t, "s": s}


def NK(x, y, t, s, k, w=200, h=50):
    """A node with a kind, coloured by the v2 look: actor, orch, svc, hub or machine."""
    return {"x": x, "y": y, "w": w, "h": h, "t": t, "s": s, "k": k}

CUST = N(30,  36, "Customer",           "catalog or ticket")
CTL  = N(30,  36, "Inventory Controller", "on this hub")
TMP  = N(400, 36, "Temporal",           "", 200)
GIT  = N(415, 180, "Git",               "desired state", 170)
ARGO = N(415, 300, "ArgoCD",            "sole applicator", 170)
SCAN = N(800, 36, "server-scan",        "fleet inventory")
SEG  = N(30, 172, "Segments Manager",   "VLAN pool")
DHCP = N(30, 290, "DHCP API",           "scope")
KV   = N(800, 172, "KV Cluster",        "KubeVirt")
PXE  = N(30, 470, "PXE Host",           "per site")
HUB  = N(380, 430, "MCE Hub",           "HostedCluster + NodePools", 240)
SEED = N(800, 430, "Seed Cluster",      "hosts KV control planes")


def page(title, subtitle, nodes, group, steps, mode_labels=("Pool", "Bare metal", "Virtual"), tags=None,
         look=None):
    html = _page(title, subtitle, nodes, group, steps, mode_labels)
    if look == "v2":
        html = _look_v2(html)
    if tags:
        badge = """'<span class="tag '+s.b+'">'+s.b+'</span>'"""
        assert badge in html
        html = html.replace(badge, """'<span class="tag '+s.b+'">'+(TAGS[s.b]||s.b)+'</span>'""") \
                   .replace("const HAS_MODES =", "const TAGS = " + json.dumps(tags) + ";\nconst HAS_MODES =", 1)
    return html


V2_CSS = """
  #svg{height:470px}
  .node text{font-size:14px}
  .node .kbar,.node.hot .kbar,.node.done .kbar{stroke:none}
  .node.k-actor .kbar{fill:#3ecf8e} .node.k-orch .kbar{fill:#4da3ff}
  .node.k-svc .kbar{fill:#58c7d8}   .node.k-hub .kbar{fill:#b57bff}
  .node.k-machine .kbar{fill:#e8b339}
  .edge.trail{stroke:#4da3ff;stroke-opacity:.25;stroke-width:1.5;stroke-dasharray:5 4}
  .edge.hot{marker-end:url(#ah)}
  .legend{display:flex;flex-wrap:wrap;gap:16px;margin-top:9px;font-size:11.5px;color:var(--dim)}
  .legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;
            vertical-align:-1px}
"""

V2_LEGEND = """  <div class="legend">
    <span><i style="background:#3ecf8e"></i>requester</span>
    <span><i style="background:#4da3ff"></i>orchestration</span>
    <span><i style="background:#58c7d8"></i>service</span>
    <span><i style="background:#b57bff"></i>MCE object</span>
    <span><i style="background:#e8b339"></i>machine</span>
    <span><i style="border:1px dashed #4da3ff"></i>path so far</span>
  </div>
</header>"""


def _look_v2(html):
    """Arrowheads on the active arrow, a faint trail of the path so far, and a colour accent
    per kind of node (NK), with a legend. Applied only to pages that ask for it, so every
    other page renders exactly as before."""
    def rep(h, a, b):
        assert h.count(a) == 1, f"v2 look: expected once: {a[:60]!r}"
        return h.replace(a, b, 1)
    html = rep(html, "</style>", V2_CSS + "</style>")
    html = rep(html, "</header>", V2_LEGEND)
    html = rep(html, 'svg.innerHTML="";',
               'svg.innerHTML=\'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" '
               'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
               '<path d="M0,0 L10,5 L0,10 z" fill="#4da3ff"/></marker></defs>\';')
    html = rep(html, 'n.appendChild(el("rect",{x:d.x,y:d.y,width:d.w,height:d.h}));',
               'n.appendChild(el("rect",{x:d.x,y:d.y,width:d.w,height:d.h}));\n'
               '    if(d.k){ n.classList.add("k-"+d.k);\n'
               '      n.appendChild(el("rect",{x:d.x+1,y:d.y+9,width:4,height:d.h-18,rx:2,class:"kbar"})); }')
    html = rep(html, "function path(a,b){",
               "function clip(n,tx,ty){ // where the line toward (tx,ty) leaves node n's box\n"
               "  const d=NODES[n], x=cx(n), y=cy(n), dx=tx-x, dy=ty-y;\n"
               "  const k=Math.min((d.w/2+4)/Math.max(Math.abs(dx),1e-6),\n"
               "                   (d.h/2+4)/Math.max(Math.abs(dy),1e-6));\n"
               "  return [x+dx*k, y+dy*k];\n"
               "}\n"
               "function path(a,b){")
    html = rep(html, "const x1=cx(a), y1=cy(a), x2=cx(b), y2=cy(b);",
               "const [x1,y1]=clip(a,cx(b),cy(b)), [x2,y2]=clip(b,cx(a),cy(a));")
    html = rep(html, 'document.getElementById("n_"+STEPS[si].t)?.classList.add("done"); });',
               'document.getElementById("n_"+STEPS[si].t)?.classList.add("done"); });\n'
               '  act.forEach((si,pos)=>{ if(here>=0 && pos<here){ const t=STEPS[si];\n'
               '    edges.appendChild(el("path",{class:"edge trail",d:path(t.f,t.t)})); } });')
    return html


def _page(title, subtitle, nodes, group, steps, mode_labels):
    """`group` may be None, one dict, or a list of dicts. `mode_labels` names the
    two-way toggle: (caption, label of the "BM" steps, label of the "VM" steps).
    `tags` optionally renames the badge shown on a mode-specific step, e.g.
    {"BM": "4.19+"}. Applied only when given, so pages without it render exactly
    as before."""
    groups = group if isinstance(group, list) else ([group] if group else [])
    modes = any(s[2] != "both" for s in steps)
    return TEMPLATE \
        .replace("__TITLE__", title) \
        .replace("__SUB__", subtitle) \
        .replace("__NODES__", json.dumps(nodes, indent=2)) \
        .replace("__GROUPS__", json.dumps(groups, indent=2)) \
        .replace("__STEPS__", json.dumps(steps, indent=2)) \
        .replace("__MODES__", "true" if modes else "false") \
        .replace("__MODE_CAPTION__", mode_labels[0]) \
        .replace("__MODE_A__", mode_labels[1]) \
        .replace("__MODE_B__", mode_labels[2])


# --------------------------------------------------------------------------
# Per-workflow definitions
# --------------------------------------------------------------------------
WORKFLOWS = {}

WORKFLOWS["01-add-server-to-mce"] = dict(
    title="01 :: Add Server to MCE",
    subtitle="One run puts one machine into one pool; N machines are N runs in numbered slots. "
             "Bare metal and VMs take the same run: a VM pool first builds its VM through the "
             "create-vm child (AD29). Where main differs today, the step says so (procedure 01, §8).",
    look="v2",
    nodes={"cvm":  NK(20, 36, "create-vm", "child · zone lock, first fit", "orch"),
           "vm":   NK(20, 140, "VirtualMachine", "Halted · MAC from KubeMacPool", "machine"),
           "ctl":  NK(20, 262, "Inventory Controller", "herzi · or an operator", "actor"),
           "tmp":  NK(385, 20, "Temporal", "add-server-to-mce · a run per slot", "orch", 230),
           "seg":  NK(780, 20, "Segments Manager", "the MCE's VLAN", "svc"),
           "scan": NK(780, 120, "server-scan", "allocates · locks", "svc"),
           "pxe":  NK(780, 220, "PXE VM", "per site · IPMI only", "svc"),
           "hubw": NK(400, 180, "server-lifecycle worker", "activities on the MCE", "hub"),
           "ienv": NK(270, 290, "InfraEnv", "the pool · 4 labels", "hub"),
           "res":  NK(535, 290, "BMH · NMState · Secret", "labelled installed-by", "hub"),
           "agt":  NK(400, 470, "Agent", "free · the pool's labels", "hub"),
           "srv":  NK(780, 380, "The machine", "bare metal, or the VM", "machine")},
    group=[{"x": 8, "y": 6, "w": 224, "h": 196, "label": "KV CLUSTER · VM POOLS"},
           {"x": 250, "y": 150, "w": 505, "h": 395, "label": "MCE HUB"}],
    steps=[
      ("ctl","ctl","both","Work out the need","Spares plus waiting workers, per pool (AD26).",
       {"call":"no call — the controller's own arithmetic, every 60 seconds",
        "send":"pending  = AgentMachines waiting for an Agent (NoSuitableAgents)  -> 2\n"
               "spares   = this pool's number, from the controller's ConfigMap    -> 2\n"
               "free     = fresh, free Agents in the pool                         -> 1\n"
               "inFlight = add-server-to-mce runs open on the pool's slots        -> 1\n"
               "need     = pending + spares - (free + inFlight) = 2 + 2 - 2 = 2",
        "warn":"Each NodePool's supply follows its own waiting workers, so a NodePool slow\n"
               "to release machines leaves the others supplied.\n"
               "need <= 0: the pass ends there."}),

      ("ctl","tmp","both","Order N runs","One request, N parallel runs.",
       {"call":"POST /workflows/server-lifecycle/add-server-to-mce",
        "send":"{ \"mce_cluster\": \"ocp4-prod-mce-five-a\",\n"
               "  \"infra_env\":   \"c200-mtl-az1\",\n"
               "  \"count\":       2 }",
        "recv":"202, a per-slot report: started / already_running / failed",
        "warn":"count starts that many NEW runs, one server each: at most 20 per request,\n"
               "across 100 slots per pool. An operator names servers instead:\n"
               "\"server_names\": [\"ocp-c200-mtl-five-fch2145v1ab\"]   (1 to 20)"}),

      ("tmp","tmp","both","Take free slots","add-server-to-mce-&lt;mce&gt;_&lt;infraEnv&gt;_&lt;slot&gt;",
       {"call":"start add-server-to-mce-ocp4-prod-mce-five-a_c200-mtl-az1_1, then _2, ...",
        "recv":"a slot already running counts as busy, and the next free one is taken",
        "warn":"In-flight is visible to anyone: the controller counts open runs by their\n"
               "ids. One running workflow per id, so each slot runs once at a time, and a\n"
               "finished slot is free again."}),

      ("tmp","seg","both","Resolve the VLAN","resolving-vlan · segment-lifecycle queue",
       {"call":"Segments Manager: the MCE's INVENTORY segment, by cluster name",
        "recv":"vlan_id",
        "warn":"The VLAN belongs to the MCE, so it is read once, before any server is\n"
               "drawn, on the segment-lifecycle queue where that credential lives."}),

      ("tmp","hubw","both","Hand the run to the MCE","Every later call is an activity here.",
       {"call":"ExecuteActivity -> queue server-lifecycle-activity-ocp4-prod-mce-five-a",
        "send":"the activity name and typed arguments",
        "recv":"a typed result, recorded in the run's history",
        "warn":"The workflow replays from its history after a crash and holds no\n"
               "credentials. Every outside call is an activity, run by a worker inside\n"
               "the cluster it talks to."}),

      ("hubw","ienv","both","Check the InfraEnv","validating-infraenv · it names its servers",
       {"call":"GET agent-install.openshift.io/v1beta1 InfraEnv c200-mtl-az1   (namespace inventory)",
        "recv":"spec.agentLabels:\n"
               "  redbull.io/flavor: c200     redbull.io/size: mtl\n"
               "  redbull.io/site: five       topology.kubernetes.io/zone: az1",
        "warn":"A missing InfraEnv, or one missing a label, fails the run before any\n"
               "server is drawn. size tells the pools apart: mtl is bare metal, kv<cpu>\n"
               "a VM of that size."}),

      ("tmp","cvm","VM","Build the VM","create-vm child (AD29)",
       {"call":"child workflow create-vm-ocp4-prod-mce-five-a_c200-kv32-az1_1",
        "send":"InfraEnv c200-kv32-az1: 32 vCPUs, zone az1",
        "warn":"The zone's lock (AD32), then the oldest KV cluster that fits (AD33):\n"
               "procedure 21.\n\n"
               "Built today: create-vm runs as its own workflow, started through\n"
               "POST /workflows/vm-lifecycle/create-vm. The lock and the placement are\n"
               "built; the child is still to be built (procedure 01, §8)."}),

      ("cvm","vm","VM","VM created, Halted","KubeMacPool's MAC · kubevirt-redfish exposes it",
       {"call":"CREATE kubevirt.io/v1 VirtualMachine   by the chosen KV cluster's worker",
        "send":"name: ocp-c200-kv32-five-k7q2m9xd   (an 8-character serial)\n"
               "runStrategy: Halted · no MAC requested: KubeMacPool assigns it\n"
               "labels: redbull.io/created-by: <run id> · redfish-enabled: \"true\"",
        "recv":"the root disk bound; kubevirt-redfish exposes it as a Redfish system",
        "warn":"The serial is also the VM's SMBIOS serial, so the Agent's inventory\n"
               "reports the serial its name carries, as bare metal does."}),

      ("hubw","scan","both","Allocate one server","acquiring-server · locked for this run",
       {"call":"POST /servers/available",
        "send":"flavor c200, size mtl, site five, zone az1   -> ocp-c200-mtl-five-…\n"
               "a VM pool: the VM its child built, by name",
        "recv":"one server, locked for this run's id and live-checked while locked",
        "warn":"One server per run (server-scan ADR-0063): server-scan picks, locks and\n"
               "checks it, so the server comes back already this run's.\n\n"
               "Built today: the draw sends flavor, size and site; the zone is still to\n"
               "be added (procedure 01, §8)."}),

      ("hubw","hubw","both","Check the server","selecting-server",
       {"call":"no call — checks on what server-scan returned",
        "recv":"a usable name, a known BMC, no BareMetalHost yet;\n"
               "the two bond NICs, as server-scan vouched for them",
        "warn":"A server that fails a check goes back to server-scan with its lock, and\n"
               "the run fails saying why. The controller's next pass orders again."}),

      ("hubw","pxe","IPMI","Map the bond MACs","registering-pxe-boot · before the BMH",
       {"call":"the site's PXE VM: map both bond MACs",
        "send":"-> the InfraEnv's boot entry  ocp4-prod-mce-five-a/c200-mtl-az1.ipxe",
        "warn":"IPMI servers (UCS blades) PXE-boot, having no virtual media. The MACs are\n"
               "mapped first, because Ironic may power the host on as soon as it\n"
               "registers it."}),

      ("hubw","res","IPMI","NMStateConfig first","Then wait for a new discovery image.",
       {"call":"CREATE agent-install.openshift.io/v1beta1 NMStateConfig",
        "send":"bond0 without an address · bond0.<vlan> on DHCP",
        "recv":"the InfraEnv's discovery image regenerated after it   (up to 10 minutes)",
        "warn":"So the host boots an image that already carries its own network config,\n"
               "however many installs of the InfraEnv run at once."}),

      ("hubw","pxe","IPMI","Publish the boot entry","publishing-pxe-boot",
       {"call":"the site's PXE VM: publish the InfraEnv's iPXE script as its boot entry",
        "recv":"a newer entry already there counts as success",
        "warn":"One entry per InfraEnv, published once the image includes this host."}),

      ("hubw","res","both","Write Secret, BMH, NMState","creating-* · labelled installed-by",
       {"call":"CREATE Secret · metal3.io BareMetalHost · NMStateConfig   (create-if-absent)",
        "send":"BareMetalHost ocp-c200-mtl-five-fch2145v1ab\n"
               "  bootMACAddress: <bond member 1>   online: true\n"
               "  customDeploy: start_assisted_install\n"
               "labels:\n"
               "  infraenvs.agent-install.openshift.io: c200-mtl-az1\n"
               "  redbull.io/installed-by: <this run's run id>   (AD37)",
        "warn":"installed-by lets the controller count the machine once: in flight until\n"
               "its Agent exists, then as a free Agent. A VM's BareMetalHost points at\n"
               "its Redfish endpoint on kubevirt-redfish, and also carries\n"
               "redbull.io/kv-cluster and redbull.io/created-by for its later delete.\n\n"
               "Built today: these labels are still to be built (procedure 01, §8)."}),

      ("res","srv","both","Boot the discovery image","Ironic powers the host on.",
       {"call":"Ironic, through the BMC: virtual media, or PXE for IPMI",
        "recv":"the host boots the InfraEnv's discovery image with its NMStateConfig",
        "warn":"A VM boots the same way, through kubevirt-redfish."}),

      ("srv","agt","both","Agent registers","awaiting-agent · up to an hour",
       {"call":"LIST agent-install.openshift.io/v1beta1 Agent   (matched to the host)",
        "recv":"an Agent, unbound, labelled from the InfraEnv's agentLabels:\n"
               "  redbull.io/flavor · size · site · topology.kubernetes.io/zone",
        "warn":"The Agent proves BMC, bond, VLAN and DHCP all worked.\n\n"
               "No Agent within the hour: NMStateConfig and BareMetalHost removed, IPMI\n"
               "MACs unmapped, the server set to MAINTENANCE in server-scan, the lock\n"
               "released, and the run fails with AgentNeverAppearedError."}),

      ("hubw","scan","both","Hold, then release","holding-server · releasing-lock",
       {"call":"server-scan: extend the lock to a day; read the server every 5 minutes",
        "recv":"INSTALLED_TO_INVENTORY or INSTALLED  -> the lock is released",
        "warn":"The lock keeps the machine out of every other MCE's draw until server-scan\n"
               "sees it installed. Unseen within the day, the lock expires and the run\n"
               "completes."}),

      ("agt","ctl","both","Counted once","The next pass sees a free Agent.",
       {"call":"the controller's next pass lists the pool's Agents",
        "recv":"the new Agent counts as free; its run, still holding the lock, is\n"
               "matched by its run id through installed-by, and counted once",
        "warn":"A NodePool claims the Agent like any other. Once bound, the controller\n"
               "labels it redbull.io/claimed (AD34)."}),
    ])

WORKFLOWS["02-remove-server-from-mce"] = dict(
    title="02 :: Remove Server from MCE",
    subtitle="One start per server takes it out of an MCE's inventory, so a machine that has served a "
             "cluster is never reused as it is (AD23). Bare metal goes back to server-scan for a full "
             "reinstall; a VM is deleted as the last step (AD36). Where main differs today, the step says so "
             "(procedure 02, §6).",
    look="v2",
    nodes={"ctl":  NK(20, 30, "Inventory Controller", "collects used Agents", "actor"),
           "tmp":  NK(385, 30, "Temporal", "remove-server-from-mce-<server>", "orch", 230),
           "pxe":  NK(780, 160, "PXE VM", "the MCE's site", "svc"),
           "hubw": NK(400, 160, "server-lifecycle worker", "activities on the MCE", "hub"),
           "bmh":  NK(270, 280, "BMH · NMState · Secret", "the host's objects", "hub"),
           "agt":  NK(520, 280, "Agent", "unbound · used", "hub", 180),
           "m3":   NK(270, 410, "metal3 · Ironic", "deprovisions the host", "hub"),
           "kvw":  NK(780, 330, "KV cluster worker", "the VM's own cluster", "svc"),
           "vm":   NK(780, 440, "VirtualMachine", "found by its run id", "machine")},
    group=[{"x": 250, "y": 130, "w": 505, "h": 345, "label": "MCE HUB"},
           {"x": 765, "y": 300, "w": 230, "h": 210, "label": "KV CLUSTER · VMs"}],
    steps=[
      ("ctl","ctl","both","A used Agent is free","R3 · unbound, labelled claimed",
       {"call":"the controller's pass: Agents labelled redbull.io/claimed, unbound, unchanged for a grace period",
        "recv":"ocp-c200-mtl-five-fch2145v1ab: free again after a scale-down",
        "warn":"Others start the same run: uninstall-server-from-hc as its child, a\n"
               "cancelled add-server-to-mce in its rollback, an operator.\n\n"
               "Built today: herzi's collector is still to be built (herzi PR #1)."}),

      ("ctl","tmp","both","Start the removal","One start per server.",
       {"call":"POST /workflows/server-lifecycle/remove-server-from-mce",
        "send":"{ \"server_name\": \"ocp-c200-mtl-five-fch2145v1ab\",\n"
               "  \"mce_cluster\": \"ocp4-prod-mce-five-a\" }",
        "recv":"202. The workflow id is the server, so a repeated start returns 409"}),

      ("tmp","hubw","both","Hand the run to the MCE","Every call is an activity there.",
       {"call":"ExecuteActivity -> queue server-lifecycle-activity-ocp4-prod-mce-five-a",
        "warn":"The workflow holds no credentials; the worker inside the MCE makes every\n"
               "call to the hub."}),

      ("hubw","bmh","both","Inspect the host","inspecting · BMH, NMState, Agents",
       {"call":"GET the BareMetalHost, the NMStateConfig and the Agents matched to the host",
        "recv":"matched by BMAC's bmh label, or by any MAC of the machine, from either\n"
               "resource or from server-scan",
        "warn":"Nothing found at all: the run succeeds with nothing to do.\n"
               "For a VM, the BareMetalHost's redbull.io/kv-cluster and\n"
               "redbull.io/created-by are read now, before the host is deleted."}),

      ("hubw","agt","both","Refuse a bound Agent","spec.clusterDeploymentName",
       {"call":"check each Agent's spec.clusterDeploymentName",
        "recv":"unbound: carry on.   bound: AgentBoundToClusterError, nothing changed",
        "warn":"The run covers a server that is inventory only. The controller collects\n"
               "unbound Agents, so its runs pass this check."}),

      ("hubw","bmh","both","Delete NMState and BMH","removing-host · metal3 takes over",
       {"call":"DELETE NMStateConfig · DELETE metal3.io BareMetalHost   (no Agent bound, re-checked)",
        "warn":"No separate power-off and no finalizer dropped: metal3's own delete\n"
               "deprovisions the host, and a finalizer dropped early once orphaned Ironic\n"
               "nodes that kept forcing a stale power state."}),

      ("bmh","m3","both","metal3 deprovisions","on the BareMetalHost's delete",
       {"call":"metal3: deprovisioning -> powering off before delete -> deleting",
        "warn":"metal3 releases its finalizer only once the host is off and its Ironic\n"
               "node is deleted."}),

      ("m3","m3","BM","Host powered off","through its BMC",
       {"call":"Ironic, through the BMC: power off",
        "recv":"the host is off, so it can no longer boot the discovery image"}),

      ("m3","vm","VM","VM powered off","through kubevirt-redfish",
       {"call":"Ironic, through kubevirt-redfish: power off",
        "recv":"the VM is stopped on its KV cluster, its disk still in place"}),

      ("hubw","bmh","both","Wait for the BMH to go","awaiting-bmh-deletion · every 15 s",
       {"call":"GET the BareMetalHost every 15 seconds, up to 15 minutes; then DELETE its BMC Secret",
        "warn":"Still there after 15 minutes: BmhDeletionTimeoutError, with the Agent\n"
               "untouched. Usually a BMC that is not answering; a re-run waits for the\n"
               "same delete."}),

      ("hubw","agt","both","Delete the Agent","removing-agent · last",
       {"call":"DELETE agent-install.openshift.io/v1beta1 Agent   (re-checked as unbound)",
        "warn":"Last, because a host still running discovery registers again within a\n"
               "minute once its Agent disappears."}),

      ("hubw","pxe","both","Clear the PXE entries","removing-pxe-boot · best effort",
       {"call":"the PXE VM of the MCE's site: clear every MAC of the host",
        "recv":"MACs pointing at another MCE's boot entry are kept (pxe_kept)",
        "warn":"Best effort: a failure is reported in pxe_failed, and the removal\n"
               "completes."}),

      ("hubw","hubw","both","Verify","verifying · nothing left",
       {"call":"inspect again until no Agent, BareMetalHost or NMStateConfig is left",
        "recv":"done, or ServerStillPresentError naming what is left"}),

      ("tmp","kvw","VM","Delete the VM","deleting-vm · on the cluster's own queue",
       {"call":"delete_vm_on_cluster -> queue of ocp4-prod-kv-five-az1-a's worker",
        "send":"every VM labelled redbull.io/created-by: <run id>, in every namespace",
        "warn":"The cluster comes from the BareMetalHost's redbull.io/kv-cluster, read in\n"
               "the first step. Retried until the cluster answers (procedure 22).\n\n"
               "Built today: this step is still to be built (procedure 02, §6)."}),

      ("kvw","vm","VM","VM and root disk gone","Room given back to the cluster.",
       {"call":"DELETE kubevirt.io/v1 VirtualMachine ocp-c200-kv32-five-k7q2m9xd",
        "recv":"the VM and its root disk deleted",
        "warn":"A Halted VM counts as used for placement and for the KV Capacity\n"
               "Controller, so the room shows as soon as it is gone."}),

      ("tmp","ctl","both","Removal complete","One used Agent fewer.",
       {"call":"the run completes",
        "recv":"bare metal: back in server-scan, for the next install to draw and reinstall\n"
               "a VM: deleted",
        "warn":"server-scan's install lock stays with its holder: a caller holding one\n"
               "releases it itself."}),
    ])

WORKFLOWS["21-create-vm"] = dict(
    title="21 :: Create VM",
    subtitle="One Halted VM for a KubeVirt InfraEnv, on the oldest KV cluster of the zone that fits, "
             "with the zone held by one run at a time (AD32, AD33). A create that fails moves on to "
             "the next cluster. Started by add-server-to-mce for a VM pool (AD29).",
    look="v2",
    mode_labels=("Create", "Lands on the oldest", "Moves on"),
    tags={"BM": "lands", "VM": "moves on"},
    nodes={"par":  NK(20, 30, "add-server-to-mce", "the parent run (AD29)", "orch"),
           "tmp":  NK(385, 30, "Temporal", "create-vm-<mce>_<infraEnv>_<slot>", "orch", 230),
           "day1": NK(780, 30, "day1 repo", "the zone's KV clusters", "svc"),
           "lock": NK(20, 150, "kv-zone-lock", "one run per site and zone", "orch", 180),
           "dsv":  NK(20, 270, "delete-stray-vm", "an abandoned child", "orch", 180),
           "kva":  NK(310, 230, "worker · cluster a", "the oldest", "svc"),
           "vma":  NK(310, 340, "VirtualMachine", "on cluster a", "machine"),
           "kvb":  NK(550, 230, "worker · cluster b", "the next", "svc"),
           "vmb":  NK(550, 340, "VirtualMachine", "on cluster b", "machine"),
           "kvr":  NK(790, 230, "kubevirt-redfish", "exposes the VM", "svc", 190),
           "scan": NK(790, 350, "server-scan", "lists it by name", "svc", 190)},
    group=[{"x": 300, "y": 200, "w": 220, "h": 200, "label": "KV CLUSTER a"},
           {"x": 540, "y": 200, "w": 220, "h": 200, "label": "KV CLUSTER b"}],
    steps=[
      ("par","tmp","both","Start the child","create-vm-&lt;mce&gt;_&lt;infraEnv&gt;_&lt;slot&gt;",
       {"call":"child workflow create-vm-ocp4-prod-mce-five-a_c200-kv32-az1_1",
        "send":"InfraEnv c200-kv32-az1 -> 32 vCPUs · 240 GiB (32 × 7.5) · zone az1 · site five",
        "warn":"Built today: create-vm is started through its own route,\n"
               "POST /workflows/vm-lifecycle/create-vm (procedure 21, §5)."}),

      ("tmp","day1","both","List the zone's clusters","listing-kv-clusters · before the lock",
       {"call":"day1 main, read by the cluster-lifecycle limb (it holds the day1 token)",
        "recv":"ocp4-prod-kv-five-az1-a, ocp4-prod-kv-five-az1-b   (oldest first)\n"
               "the placement buffer",
        "warn":"Read before the lock, so the locked part stays short. None usable:\n"
               "NoKvClusterError."}),

      ("tmp","lock","both","Take the zone's lock","awaiting-zone-lock · one run at a time",
       {"call":"signal the zone's kv-zone-lock run, or start it; wait for lock_granted",
        "recv":"a lease of up to five minutes",
        "warn":"Ten runs reading at once would all pick the same empty cluster, so only\n"
               "the lock's holder reads figures and chooses (AD32). After 30 minutes in\n"
               "line: KvZoneLockTimeoutError."}),

      ("tmp","kva","both","Read cluster a","choosing-kv-cluster · oldest first",
       {"call":"figures from the worker inside ocp4-prod-kv-five-az1-a, on its own queue",
        "recv":"per node: allocatable and requested CPU and memory, Halted VMs counted",
        "warn":"It fits when a node has room for the VM's CPU and memory and the cluster\n"
               "stays within 1 − buffer. The scan stops at the first that fits (AD33)."}),

      ("kva","vma","BM","Create the VM on a","creating-vm · Halted, no MAC requested",
       {"call":"the worker creates kubevirt.io/v1 VirtualMachine, Halted",
        "send":"name: ocp-c200-kv32-five-k7q2m9xd   (serial drawn by the worker)\n"
               "MAC: assigned by KubeMacPool\n"
               "labels: redbull.io/created-by: <run id> · redfish-enabled: \"true\"",
        "recv":"the VM object exists",
        "warn":"A taken name is drawn again, up to 3 times. The worker creates nothing\n"
               "after the create's deadline: 90 seconds, or the lease's end."}),

      ("kva","kva","VM","Create on a fails","an outage, or a worker gone",
       {"call":"the create on ocp4-prod-kv-five-az1-a fails, retried until its deadline",
        "warn":"The run carries on to the next cluster (the operator, 2026-11-24)."}),

      ("tmp","kva","VM","Did it land on a?","checking-kv-cluster · after the deadline",
       {"call":"ask cluster a for a VM labelled redbull.io/created-by: <run id>",
        "recv":"a VM there: the run keeps it.   none: clean.   no answer: unknown",
        "warn":"Asked after the create's deadline, so nothing of the run can still land\n"
               "there while the run moves on."}),

      ("tmp","dsv","VM","Clean up later","cluster a did not answer",
       {"call":"start delete-stray-vm-ocp4-prod-kv-five-az1-a-<run id> as an abandoned child",
        "warn":"It deletes any VM of the run on cluster a once the cluster answers\n"
               "(procedure 22). The run moves on meanwhile."}),

      ("tmp","kvb","VM","Read cluster b","the next cluster",
       {"call":"figures from the worker inside ocp4-prod-kv-five-az1-b",
        "recv":"fits"}),

      ("kvb","vmb","VM","Create the VM on b","creating-vm · Halted, no MAC requested",
       {"call":"the worker creates kubevirt.io/v1 VirtualMachine, Halted",
        "send":"name: ocp-c200-kv32-five-k7q2m9xd · MAC from KubeMacPool\n"
               "labels: redbull.io/created-by: <run id> · redfish-enabled: \"true\"",
        "recv":"the VM object exists"}),

      ("tmp","lock","both","Release the lock","releasing-zone-lock · the VM object exists",
       {"call":"release the zone's kv-zone-lock",
        "warn":"The next run's figures already count this VM, as a stopped VM: nothing\n"
               "is remembered between runs."}),

      ("vma","vma","BM","Root disk bound","awaiting-root-disk · outside the lock",
       {"call":"wait for the root disk's DataVolume: Succeeded and bound, the VM admitted",
        "warn":"Up to 10 minutes, then VmRootDiskNotBoundError: the run deletes its own\n"
               "VM by its run-id label (removing-vm) and fails."}),

      ("vmb","vmb","VM","Root disk bound","awaiting-root-disk · outside the lock",
       {"call":"wait for the root disk's DataVolume: Succeeded and bound, the VM admitted"}),

      ("vma","kvr","BM","Exposed as Redfish","kubevirt-redfish",
       {"call":"kubevirt-redfish exposes the VM labelled redfish-enabled as a Redfish system"}),

      ("vmb","kvr","VM","Exposed as Redfish","kubevirt-redfish",
       {"call":"kubevirt-redfish exposes the VM labelled redfish-enabled as a Redfish system"}),

      ("kvr","scan","both","Listed in server-scan","under its name",
       {"recv":"ocp-c200-kv32-five-k7q2m9xd, available",
        "warn":"The serial is also the VM's SMBIOS serial, so the Agent's inventory\n"
               "reports the serial the name carries."}),

      ("tmp","par","both","Hand the VM to the parent","completed · name, MAC, cluster",
       {"recv":"ocp-c200-kv32-five-k7q2m9xd · its MAC · its KV cluster · the placement table",
        "warn":"The parent installs exactly that VM (procedure 01, from step 4)."}),

      ("dsv","kva","VM","Delete the stray","later, when cluster a answers",
       {"call":"delete_vm_on_cluster on cluster a's queue, by the run-id label, in every namespace",
        "recv":"deleted: true, or false when the create had never landed",
        "warn":"So a run never keeps two VMs: a stray stays Halted and unused until it is\n"
               "deleted."}),
    ])

WORKFLOWS["22-delete-vm"] = dict(
    title="22 :: Delete VM",
    subtitle="A VM is deleted by its owner label, redbull.io/created-by, through the worker inside its "
             "KV cluster: as the last step of remove-server-from-mce (AD23, AD36), or by "
             "delete-stray-vm for a VM a create left behind.",
    look="v2",
    mode_labels=("Started by", "remove-server-from-mce", "create-vm (stray)"),
    tags={"BM": "removal", "VM": "stray"},
    nodes={"cvm":  NK(20, 30, "create-vm", "moved on from a cluster", "orch"),
           "dsv":  NK(20, 130, "delete-stray-vm", "an abandoned child", "orch"),
           "rsm":  NK(20, 260, "remove-server-from-mce", "its last step (AD36)", "orch"),
           "hubw": NK(330, 260, "server-lifecycle worker", "the MCE", "hub"),
           "bmh":  NK(330, 380, "BareMetalHost", "kv-cluster · created-by", "hub"),
           "kvw":  NK(600, 130, "KV cluster worker", "the VM's own cluster", "svc"),
           "vm":   NK(600, 260, "VirtualMachine", "and its root disk", "machine"),
           "kvr":  NK(820, 260, "kubevirt-redfish", "drops the system", "svc", 160),
           "scan": NK(820, 380, "server-scan", "drops the server", "svc", 160),
           "fig":  NK(600, 420, "Cluster figures", "placement · KV Capacity", "svc")},
    group=[{"x": 315, "y": 232, "w": 230, "h": 210, "label": "MCE HUB"},
           {"x": 585, "y": 100, "w": 230, "h": 222, "label": "KV CLUSTER"}],
    steps=[
      ("rsm","hubw","BM","The removal runs","remove-server-from-mce-&lt;server&gt;",
       {"call":"remove-server-from-mce-ocp-c200-kv32-five-k7q2m9xd, on the MCE's queue",
        "warn":"Started by the Inventory Controller for a used Agent (AD34), by\n"
               "uninstall-server-from-hc, by a cancelled install, or by an operator."}),

      ("hubw","bmh","BM","Read the labels","inspecting · before the host goes",
       {"call":"GET metal3.io BareMetalHost ocp-c200-kv32-five-k7q2m9xd",
        "recv":"redbull.io/kv-cluster: ocp4-prod-kv-five-az1-a\n"
               "redbull.io/created-by: <the create-vm run id>",
        "warn":"Read in the first step, because the host is deleted later in the run.\n\n"
               "Built today: these labels on the BareMetalHost are still to be built\n"
               "(naming convention, open item 5)."}),

      ("hubw","hubw","BM","Host, NMState, Agent removed","phases 3 to 6 of procedure 02",
       {"call":"delete the NMStateConfig and the BareMetalHost (metal3 powers the VM off\n"
               "through kubevirt-redfish), delete the Agent, clear the PXE entries, verify",
        "warn":"The VM is stopped, and nothing on the MCE refers to it any more."}),

      ("hubw","kvw","BM","Delete the VM","deleting-vm · on the cluster's own queue",
       {"call":"delete_vm_on_cluster -> queue of ocp4-prod-kv-five-az1-a's worker",
        "send":"every VM labelled redbull.io/created-by: <run id>, in every namespace",
        "warn":"Retried until the cluster answers.\n\n"
               "Built today: this step is still to be built (procedure 02, §6)."}),

      ("cvm","dsv","VM","Start the cleanup","cluster a did not answer",
       {"call":"start delete-stray-vm-ocp4-prod-kv-five-az1-a-<run id>, abandoned",
        "warn":"create-vm moved on to the next cluster; this child removes any VM of the\n"
               "run left on cluster a (procedure 21, checking-kv-cluster). Built."}),

      ("dsv","kvw","VM","Delete by run id","retried until the cluster answers",
       {"call":"delete_vm_on_cluster on cluster a's queue, by the run-id label, in every namespace",
        "recv":"deleted: true, or false when the create had never landed",
        "warn":"A refusal no retry can fix fails the run, naming the label to delete by\n"
               "hand."}),

      ("kvw","vm","both","VM deleted","with its root disk",
       {"call":"DELETE kubevirt.io/v1 VirtualMachine, labelled redbull.io/created-by: <run id>",
        "recv":"the VM and its root disk deleted",
        "warn":"Only a VM carrying that run id: a hand-made VM, or another run's VM of\n"
               "the same name, stays."}),

      ("vm","kvr","both","Redfish system gone","kubevirt-redfish drops it",
       {"call":"the Redfish system goes with the VM"}),

      ("kvr","scan","both","Gone from server-scan","at its next collection",
       {"recv":"the server leaves server-scan's list, so no draw can offer it"}),

      ("vm","fig","both","Room given back","Halted VMs count as used",
       {"warn":"create-vm's placement and the KV Capacity Controller both count Halted\n"
               "VMs, so the room shows as soon as the VM is gone."}),
    ])

WORKFLOWS["03-create-hosted-cluster"] = dict(
    title="03 :: Create Hosted Cluster",
    subtitle="Creates demand and stops. Workers appear because the controller sees the new "
             "demand and fills the pools. The run ends at control plane available.",
    nodes={"cust": CUST, "tmp": TMP, "seg": SEG, "git": GIT, "argo": ARGO, "hub": HUB,
           "ctl": N(800, 300, "Inventory Controller", "sees new demand"),
           "pool": N(800, 430, "Pools fill", "via workflow 01")},
    group=None,
    steps=[
      ("cust","tmp","both","Request a cluster","Name, hub, release by digest, worker types per zone."),
      ("tmp","tmp","both","Validate","Hub known, pools exist for every type in all three zones."),
      ("tmp","seg","both","Allocate a segment","An HC segment at the hub's site.",
       {"call":"POST /api/segments/allocate            (bearer token)",
        "send":"{ \"cluster_name\": \"tenant-prod-01\",\n"
               "  \"site\": \"bat-yam\",\n"
               "  \"type\": \"HC\" }",
        "recv":"{ \"vlan_id\": 112, \"segment\": \"10.20.94.0/24\",\n"
               "  \"cluster_name\": \"tenant-prod-01\", \"type\": \"HC\" }",
        "warn":"Idempotent server-side per (cluster, site, type), so a retry returns the\n"
               "same allocation. A 503 means the site's pool is EMPTY: terminal, a human\n"
               "creates segments, waiting will not help.\n\n"
               "cluster_name may come back as a LIST for shared segments."}),

      ("seg","tmp","both","Verify the allocation","Status, cluster, VLAN and type must all match.",
       {"call":"GET /api/segments/by-segment?segment=<CIDR>",
        "recv":"status == \"Allocated\"  and  cluster_name == ours\n"
               "vlan_id == the one just handed back  and  type == \"HC\"",
        "warn":"Read back BEFORE committing anything to Git, so the repository can never\n"
               "record a VLAN the Segments Manager does not confirm."}),

      ("tmp","git","both","Commit manifests","HostedCluster plus one NodePool per zone per type.",
       {"call":"git clone --depth 1 -b <values_branch>, edit, commit, push",
        "send":"sites/<site>/mces/<hub>/hostedClusters/<cluster>.yaml\n"
               "  vlanId: 112\n"
               "  dhcp_values: {network: \"10.20.94.0\", exclusions: [...]}\n"
               "plus HostedCluster and one NodePool per zone per worker type",
        "warn":"The commit message carries [skip ci], or the push restarts the pipeline that\n"
               "called this workflow. The token is injected in memory and scrubbed from\n"
               "every message before the exception object exists, because activity errors\n"
               "land verbatim in Temporal history."}),
      ("git","argo","both","Human merges to main","ArgoCD only reads main. The one manual step."),
      ("argo","hub","both","Apply","Control plane pods start on the hub."),
      ("hub","tmp","both","Await control plane","Run completes here. Not at workers ready."),
      ("hub","ctl","both","Demand is now visible","NodePools want agents that may not exist yet."),
      ("ctl","pool","both","Controller fills the pools","Deep pool looks instant. Empty pool means a full build."),
    ])

WORKFLOWS["04-update-nodepool"] = dict(
    title="04 :: Update NodePool",
    subtitle="The only place a customer's desired worker count enters the system. "
             "Everything downstream is a consequence. This never provisions anything.",
    nodes={"cust": CUST, "tmp": TMP, "git": GIT, "argo": ARGO, "hub": HUB,
           "ctl": N(800, 180, "Inventory Controller", "sees the change"),
           "up":  N(800, 300, "Scale up", "pool below target"),
           "dn":  N(800, 430, "Scale down", "agents return to pool")},
    group=None,
    steps=[
      ("cust","tmp","both","Request a total","Absolute across all three zones, never a delta."),
      ("tmp","tmp","both","Validate","At least three, so every zone keeps a node."),
      ("tmp","git","both","Read current replicas","All three zones in one clone.",
       {"call":"git clone --depth 1 -b <values_branch>",
        "recv":"nodepools/<cluster>/<node_type>/zone-1.yaml  spec.replicas\n"
               "                               /zone-2.yaml  spec.replicas\n"
               "                               /zone-3.yaml  spec.replicas",
        "warn":"One clone for all three zones, so the three values are read at a single\n"
               "point in time and cannot disagree with each other."}),

      ("tmp","tmp","both","Spread across zones","Evenly; earlier zones take the remainder.",
       {"call":"pure function, no I/O",
        "send":"base  = desired_total / 3\n"
               "extra = desired_total % 3\n"
               "the first `extra` zones get base + 1\n\n"
               "10 -> 4,3,3      9 -> 3,3,3      5 -> 2,2,1",
        "warn":"Deterministic, so the same total always produces the same layout regardless\n"
               "of what is currently deployed. That is what makes a replay safe."}),

      ("tmp","git","both","Commit, or skip","No change means no commit at all.",
       {"call":"patch spec.replicas on changed zones, one commit, push",
        "send":"commit: scale <cluster>/<node_type> -> total=10 "
               "(zone-1=4, zone-2=3, zone-3=3) [skip ci]",
        "warn":"Zones whose value is unchanged are not staged. If nothing changed there is\n"
               "no commit, which keeps the repository readable by humans rather than\n"
               "filling it with no-op churn."}),
      ("git","argo","both","Human merges to main","Out of band."),
      ("argo","hub","both","Apply to the hub","NodePool replicas updated."),
      ("hub","ctl","both","Controller observes","Demand moved. It does not get told; it looks."),
      ("ctl","up","both","If demand rose","Pool below target, workflow 01 runs."),
      ("ctl","dn","both","If demand fell","Agents unbind and wait in the pool. Nothing is destroyed."),
    ])

WORKFLOWS["19-remove-server-from-nodepool"] = dict(
    title="19 :: Remove Server from NodePool",
    subtitle="A scale-down of update-nodepool by one worker: mark the Machine, lower the count, "
             "let CAPI delete what was marked, then release the machine. Steps marked (to add) "
             "are not on the branch yet.",
    nodes={"cust": N(30, 36, "Wingman", "tenant or SRE"),
           "tmp":  N(400, 36, "Temporal", "update-nodepool", 200),
           "scan": N(800, 36, "server-scan", "fleet inventory"),
           "ctl":  N(30, 172, "Inventory Controller", "sees demand drop"),
           "git":  GIT,
           "kv":   N(800, 172, "KV Cluster", "the VM"),
           "hc":   N(30, 300, "Hosted cluster", "the Node drains"),
           "argo": ARGO,
           "capi": N(800, 300, "CAPI MachineSet", "deletes marked first"),
           "hub":  N(380, 430, "MCE Hub", "NodePool · Machine · Agent", 240)},
    group=None,
    steps=[
      ("cust","tmp","both","Ask for one fewer","Named: this node. Any: the NodePool's policy or CAPI chooses.",
       {"call":"POST /workflows/server-lifecycle/update-nodepool",
        "send":"{ \"mce_cluster\": \"ocp4-prod-mce-bat-yam-a\",\n"
               "  \"cluster\":     \"ocp4-prod-payments-bat-yam-a\",\n"
               "  \"nodepool\":    \"<nodepool>\",\n"
               "  \"replicas\":    <current - 1>,\n"
               "  \"node_name\":   \"<node>\"        // Named mode only (to add)\n}",
        "warn":"The count is absolute, never a delta. Workflow id update-nodepool-<cluster>:\n"
               "one change per cluster at a time, and a 409 while upgrade-cluster runs."}),

      ("tmp","git","both","Read day1","The NodePool's replicas on main.",
       {"call":"clone day1 main, read sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml",
        "recv":"nodepool[<name>].replicas, and the file's blob id for the compare-and-set",
        "warn":"Day1 and the live NodePools must agree both ways, or the run stops with\n"
               "nothing written."}),

      ("tmp","hub","both","Read the NodePool","Refuse autoscaling, a rollout, or a count below the floor.",
       {"call":"get NodePool, its MachineSet and its Machines",
        "warn":"Refused with nothing written: Machines across two MachineSets (a rollout),\n"
               "a Machine already deleting, another run's mark, Machines != replicas.\n"
               "The floor and the autoscaling refusal are (to add)."}),

      ("tmp","hub","both","Named: find the Machine","Node -> Agent -> AgentMachine -> Machine. (to add)",
       {"call":"Node.spec.providerID = agent://<agent>\n"
               "Agent -> AgentMachine -> Machine -> MachineSet -> NodePool",
        "warn":"Refuse if the MachineSet holds a CAPI-unhealthy Machine. CAPI 4.18 ties a\n"
               "marked Machine with an unhealthy one and breaks the tie by name, so the\n"
               "named node would not be guaranteed to go."}),

      ("tmp","hub","both","Mark the Machine","Before the commit, and read back.",
       {"call":"annotate Machine  cluster.x-k8s.io/delete-machine=<workflow id>",
        "warn":"Mark first, then lower the count. The other way round, CAPI may delete a\n"
               "different Machine before the mark lands. Any mode with no policy marks\n"
               "nothing and CAPI picks at random, unhealthy Machines first."}),

      ("tmp","git","both","Commit replicas - 1","One commit to main, compare-and-set on the file.",
       {"call":"commit nodepool(<cluster>): <nodepool> replicas N -> N-1, push to main",
        "warn":"If the file moved, or the push is refused, the marks come off and the run\n"
               "fails. Once the commit has landed the marks are never removed."}),

      ("tmp","argo","both","Sync to that commit","Exactly that revision, only the moved NodePool out of sync."),
      ("argo","hub","both","NodePool shows N-1","Read back."),

      ("hub","capi","both","CAPI deletes the marked Machine","Checked: an unmarked Machine deleting fails the run.",
       {"warn":"Never delete the Machine directly. The MachineSet would replace it at once,\n"
               "and the next scale-down would remove a second node."}),

      ("capi","hc","both","Drain the Node","Cordon and evict. Bounded wait. (to add)",
       {"warn":"A PodDisruptionBudget can block the drain. The wait fails naming the pods\n"
               "and the budgets involved."}),

      ("hub","hub","both","Agent unbound","The provider's pre-terminate hook releases it. (to add)"),

      ("tmp","hub","both","Remove from the MCE","remove-server-from-mce as a child. (to add)",
       {"call":"child: remove-server-from-mce",
        "warn":"Power off, BareMetalHost, NMStateConfig, Agent, PXE map. Without this the\n"
               "machine returns to the pool as a free Agent with the last tenant's disk (AD23)."}),

      ("tmp","kv","VM","Destroy the VM","By name and MAC. (to add)",
       {"call":"delete VirtualMachine <name> on its KV cluster",
        "warn":"Name AND MAC: if someone replaced the VM, the MAC differs and the VM is\n"
               "left alone."}),

      ("hub","scan","BM","Back to server-scan","Reinstalled from scratch by the next install that draws it. (to add)",
       {"warn":"Reinstalling overwrites the install disk only. Whether bare metal is also\n"
               "wiped is still open (D5)."}),

      ("hub","ctl","both","Demand dropped","The pool's target falls; nothing is ordered back (AD26)."),
    ])

WORKFLOWS["20-remove-node-flow-draft"] = dict(
    title="20 :: Remove Nodes: Customer Picks, or Any (DRAFT, for review)",
    subtitle="Two ways to remove: the customer picks the nodes (offered from control plane 4.19, "
             "CAPI 1.9+), or asks for any N and the workflow picks (offered on every version). "
             "The UI offers; the workflow enforces. Only the NodePool count goes through Git; "
             "Machines and Agents are changed directly on the MCE's API (AD22).",
    mode_labels=("Who chooses", "Customer picks", "Any node"),
    tags={"BM": "picked", "VM": "any"},
    nodes={"cust": N(30, 36, "Wingman", "tenant or SRE"),
           "tmp":  N(400, 36, "Temporal", "update-nodepool", 200),
           "scan": N(800, 36, "server-scan", "fleet inventory"),
           "git":  N(30, 172, "Git (day1)", "NodePool count only"),
           "kv":   N(800, 172, "KV Cluster", "VMs destroyed"),
           "argo": N(30, 300, "ArgoCD", "applies the NodePool"),
           "capi": N(800, 300, "CAPI MachineSet", "ranks, deletes top N"),
           "ctl":  N(30, 430, "Inventory Controller", "sees demand drop"),
           "hub":  N(380, 430, "MCE Hub API", "Machines · Agents: direct", 240),
           "hc":   N(800, 430, "Hosted cluster", "Nodes drain")},
    group=None,
    steps=[
      ("cust","tmp","both","Ask what removal allows","Wingman asks the orchestrator, before drawing the form.",
       {"call":"GET /workflows/server-lifecycle/removal-options?cluster=<cluster>   (synchronous, like upgrade-targets)",
        "warn":"Wingman renders the form from this answer and carries no version rule of its own,\n"
               "so the UI and the workflow can never disagree."}),

      ("tmp","hub","both","Read the running CAPI","The control plane version CAPI actually runs on.",
       {"call":"HostedCluster status: running control plane version\n"
               "HostedCluster annotation: hypershift.openshift.io/capi-manager-image (an override)",
        "warn":"Not day1's mastertag: that is the desired version. During an upgrade the control\n"
               "plane, and with it CAPI, may still be on the old one."}),

      ("tmp","cust","BM","Picking is offered only on 4.19+","CAPI 1.9+: a marked Machine (75) beats an unhealthy one (50).",
       {"recv":"4.19+:  { \"choose_node\": true,  \"any\": true }\n"
               "4.18-:  { \"choose_node\": false, \"any\": true,\n"
               "          \"reason\": \"choosing a node needs control plane 4.19 or later\" }",
        "warn":"On 4.18 and earlier CAPI ties a marked Machine with an unhealthy one (50 = 50) and\n"
               "breaks the tie by name, so a picked node is not guaranteed to go. The option is\n"
               "shown disabled with the reason, and the customer uses 'any node'.\n"
               "Fails safe: a 4.18 cluster with a CAPI override is under-offered, never over-promised."}),
      ("tmp","cust","VM","Any node is offered on every version","The workflow picks, so CAPI's version does not matter.",
       {"recv":"{ \"choose_node\": <true on 4.19+>, \"any\": true }"}),

      ("cust","tmp","BM","Remove these nodes","node_name(s) plus the new total.",
       {"send":"{ \"cluster\": \"<cluster>\", \"nodepool\": \"<np>\", \"replicas\": 12,\n"
               "  \"node_names\": [\"<node-a>\", \"<node-b>\"] }"}),
      ("cust","tmp","VM","Remove any N","Only the new total.",
       {"send":"{ \"cluster\": \"<cluster>\", \"nodepool\": \"<np>\", \"replicas\": 12 }"}),

      ("tmp","tmp","both","Join the running workflow; latest wins","A new total replaces the one waiting. Settle 60 s.",
       {"call":"update-with-start on update-nodepool-<cluster>",
        "warn":"18 -> 12, then 14, then 10, thirty seconds apart: one change, 18 -> 10, one commit.\n"
               "Nothing is added and then destroyed."}),

      ("tmp","tmp","BM","Enforce the same rule","node_names on CAPI < 1.9 is refused here too.",
       {"warn":"The orchestrator API has no authentication and the UI can be stale (a cluster\n"
               "mid-upgrade), so the workflow is the judge. Wingman shows its refusal verbatim."}),

      ("tmp","git","both","Read day1","The NodePool's count in Git.",
       {"warn":"Git holds the desired count and nothing else about the machines (AD22)."}),
      ("tmp","hub","both","Read the live NodePool","Direct API. Must agree with day1; refuse autoscaling, a rollout, a deleting Machine, the floor."),

      ("tmp","hub","BM","Find the named Machines","Direct API: Node -> Agent -> AgentMachine -> Machine.",
       {"call":"Node.spec.providerID = agent://<agent>  ->  AgentMachine  ->  Machine  ->  MachineSet",
        "warn":"Each must belong to the requested NodePool's MachineSet."}),
      ("tmp","hub","VM","The workflow chooses","Unhealthy first by name, then the policy or a random pick. Any version.",
       {"warn":"Unhealthy includes a Machine still installing (no nodeRef) and a Node reporting\n"
               "Ready=False. Putting them first makes the marked set CAPI's own top set, on 4.18\n"
               "as on 4.19+. That is why 'any node' needs no version check."}),

      ("tmp","hub","both","Mark, and record each Agent","Direct API, not Git: annotation on the Machine; Agent and server saved in the run.",
       {"call":"annotate Machine  cluster.x-k8s.io/delete-machine=<workflow id>\n"
               "record  Machine -> agent://<agent> -> server name",
        "warn":"Recorded now, while the Machine still exists: it is gone after the scale-down."}),

      ("tmp","hub","both","Label the Agents","Direct API, not Git: redbull.io/uninstalling, before the commit.",
       {"warn":"Harmless on a bound Agent: the provider reads a NodePool's selector only when it\n"
               "picks a FREE Agent. Once released, a labelled Agent cannot be claimed by any other\n"
               "NodePool on the hub. Needs the NodePool selector (DoesNotExist) in the chart.\n"
               "On 4.18 with 'any node', label every Machine CAPI could pick, and unlabel the\n"
               "survivors once the deleting set is known."}),

      ("tmp","git","both","Newest target? Then commit","The only Git write: the NodePool's count, compare-and-set, one batch.",
       {"call":"commit nodepool(<cluster>): <np> replicas 18 -> 16   (batch of 2 per NodePool)",
        "warn":"Batches bound the capacity dip, as maxUnavailable does for upgrades. Each batch\n"
               "is a full mark -> commit -> check -> release step."}),

      ("tmp","argo","both","Sync to that commit","ArgoCD applies the NodePool's new count."),
      ("argo","hub","both","NodePool updated","The MCE's NodePool now wants fewer workers."),

      ("hub","capi","BM","CAPI deletes the picked nodes","4.19+: 100 deleting, 75 marked, 50 unhealthy, 20 healthy.",
       {"warn":"A Machine already deleting (100) still outranks the mark, on every version."}),
      ("hub","capi","VM","CAPI deletes the marked set","4.19+: 75 > 50 > 20.  4.18-: 50 marked = 50 unhealthy, ties by name.",
       {"warn":"Either way the marked set is CAPI's top set, because the workflow marked the\n"
               "unhealthy Machines first. A Machine already deleting (100) still outranks both."}),

      ("tmp","hub","both","Check the deleting set","Direct API: deleting == marked. Otherwise follow what is deleting.",
       {"warn":"An unmarked Machine deleting (a repair started in between): follow it, label its\n"
               "Agent, unlabel the Machine left behind, and report the difference."}),

      ("capi","hc","both","Drain the batch","In parallel, each with its own deadline."),
      ("hub","hub","both","Agents unbound","Held out of the pool by the label."),

      ("tmp","hub","both","Release, one child per server","Direct API, outside the cluster's lock: remove-server-from-mce.",
       {"call":"child per server: remove-server-from-mce-<server>",
        "warn":"One stuck machine does not hold the others, and the cluster can take its next\n"
               "change while machines are still being released."}),

      ("tmp","kv","both","VM destroyed; bare metal reinstalled","AD23: never reused as it is.",
       {"warn":"VM: deleted by name and MAC. Bare metal: back to server-scan, reinstalled from\n"
               "scratch by the next install that draws it."}),

      ("hub","ctl","both","Demand dropped","Nothing is ordered back (AD26)."),
    ])

WORKFLOWS["05-delete-hosted-cluster"] = dict(
    title="05 :: Delete Hosted Cluster",
    subtitle="Order matters more here than anywhere else. Each step exists because the next "
             "one is unsafe without it.",
    nodes={"cust": CUST, "tmp": TMP, "git": GIT, "argo": ARGO, "hub": HUB,
           "seg": SEG, "dhcp": DHCP,
           "pool": N(800, 300, "Pool", "capacity returns")},
    group=None,
    steps=[
      ("cust","tmp","both","Request deletion","Explicit confirmation. This is not reversible."),
      ("tmp","hub","both","Drain workloads","Bounded. A decommission is not blocked by its own workloads."),
      ("tmp","git","both","Remove the manifests","Deleting the files IS the decommission."),
      ("git","argo","both","Human merges to main","Out of band."),
      ("argo","hub","both","Prune every resource","Nothing below is safe while one still exists."),
      ("hub","pool","both","Agents unbind","Worker capacity returns to the pool after a disk reset."),
      ("tmp","dhcp","both","Delete the scope","After the prune. A live application re-creates it in a minute.",
       {"call":"GET  /api/v1/scopes/<network>     then\n"
               "DELETE /api/v1/scopes/<network>   then GET again to confirm absence",
        "recv":"204 whether or not the scope existed",
        "warn":"Runs PowerShell against a remote Windows DHCP server, so budget 150s.\n"
               "If the GitOps application is still alive it re-POSTs the scope about a\n"
               "minute later, which is why this comes after the prune, not before."}),

      ("tmp","seg","both","Release the segment","After the scope. Re-read the owner first.",
       {"call":"GET /api/segments/by-segment   then   POST /api/segments/release",
        "send":"{ \"segment\": \"10.20.94.0/24\" }",
        "warn":"Re-read the owner immediately first. The release endpoint does not check\n"
               "who holds it, so without that check this can release a segment another\n"
               "cluster now owns. An already-available segment answers success."}),

      ("seg","tmp","both","Verify released","Available, no cluster, no type.",
       {"call":"GET /api/segments/by-segment?segment=<CIDR>",
        "recv":"status == \"Available\",  cluster_name is null,  type is null"}),
    ])

WORKFLOWS["07-add-bm-to-kv-cluster"] = dict(
    title="07 :: Add Bare-Metal Node to a KV Cluster",
    subtitle="No steps of its own. This is workflow 04 then workflow 01, with the Seed as "
             "the hub, plus one wait that only matters here.",
    nodes={"op": N(30, 36, "Operator", "or capacity policy"), "tmp": TMP,
           "git": GIT, "argo": ARGO, "seed": N(380, 430, "Seed Cluster", "the hub here", 240),
           "ctl": N(800, 180, "Controller on Seed", "BM pool"),
           "scan": SCAN, "kvn": N(800, 430, "New hypervisor", "KubeVirt schedulable")},
    group=None,
    steps=[
      ("op","tmp","both","Raise the node count","Workflow 04 with hub = Seed, pool type = BM."),
      ("tmp","git","both","Commit the NodePool","Same manifest shape as any tenant cluster."),
      ("git","argo","both","Merge and apply","Out of band, then ArgoCD."),
      ("argo","seed","both","Seed claims free agents","Its NodePool controller takes what is already there."),
      ("seed","ctl","both","Controller sees the gap","Demand now exceeds supply in the BM pool."),
      ("ctl","scan","both","Draw and install a machine","Workflow 01 on the Seed."),
      ("scan","kvn","both","Node joins","Reports Ready."),
      ("kvn","kvn","both","Await KubeVirt","A joined node is not capacity until KubeVirt runs on it."),
    ])

WORKFLOWS["08-remove-bm-from-kv-cluster"] = dict(
    title="08 :: Remove Bare-Metal Node from a KV Cluster",
    subtitle="The evacuation is the whole difficulty. A hypervisor carries other people's "
             "running machines, so it cannot simply be removed.",
    nodes={"op": N(30, 36, "Operator", "maintenance or shrink"), "tmp": TMP,
           "cell": N(760, 36, "Cell headroom", "can it absorb?", 200),
           "node": N(400, 180, "Hypervisor", "being removed", 200),
           "guests": N(760, 180, "Tenant VMs", "must move first", 200),
           "git": GIT, "argo": ARGO, "seed": N(380, 430, "Seed Cluster", "the hub", 240)},
    group=None,
    steps=[
      ("op","tmp","both","Request removal","For maintenance, decommissioning, or a shrinking cell."),
      ("tmp","cell","both","Check headroom","The rest of the cell must hold these guests, margin intact."),
      ("tmp","node","both","Cordon","No new guest lands here."),
      ("node","guests","both","Live-migrate every guest","Possible only because guest storage is shared."),
      ("guests","tmp","both","Verify empty","A guest that will not move stops the run, named. Never force."),
      ("tmp","git","both","Shrink the NodePool","Workflow 04 against the Seed, total minus one."),
      ("git","argo","both","Merge and apply","Out of band."),
      ("argo","seed","both","Node leaves","Then workflow 02 tears down its host resources."),
    ])

WORKFLOWS["09-decommission-kv-cluster"] = dict(
    title="09 :: Decommission a KV Cluster",
    subtitle="Cell contraction. The most disruptive workflow in the platform, because every "
             "guest on the cell has to go somewhere else first.",
    nodes={"pol": N(30, 36, "Capacity policy", "or operator"), "tmp": TMP,
           "cell": N(380, 170, "This cell", "under threshold", 200),
           "tgt":  N(760, 170, "Target cells", "same zone, with room", 200),
           "seed": N(380, 310, "Seed Cluster", "hosts its control plane", 200),
           "bm":   N(760, 310, "Hypervisors", "return to inventory", 200),
           "seg": SEG},
    group=None,
    steps=[
      ("pol","tmp","both","Sustained under threshold","A quiet afternoon is not a reason. Cooldown in days."),
      ("tmp","tgt","both","Find destinations","Same zone, enough room for every guest, margin intact."),
      ("tmp","cell","both","Mark draining","Nothing new is placed here."),
      ("cell","tgt","both","Evacuate every hypervisor","Cross-cluster migration. Verify this works before building it."),
      ("tmp","cell","both","Verify empty","Any guest left stops the run."),
      ("tmp","seed","both","Delete the cluster","Workflow 05 with hub = Seed."),
      ("seed","bm","both","Hypervisors return","To inventory, or destroyed if the pool is over its ceiling."),
      ("tmp","seg","both","Release the segment","Handled inside the delete."),
    ])

WORKFLOWS["11-add-bm-to-seed-cluster"] = dict(
    title="11 :: Add Bare-Metal Node to a Seed Cluster",
    subtitle="The one cluster that is not hosted, so there is no NodePool to change. "
             "Blocked on a decision: which join mechanism.",
    nodes={"op": N(30, 36, "Operator", "rare"), "tmp": TMP, "scan": SCAN,
           "seg": SEG,
           "a": N(330, 300, "Agent flow", "reuses workflow 01", 200),
           "b": N(610, 300, "Ignition flow", "classic UPI", 200),
           "seed": N(400, 440, "Seed Cluster", "new worker joins", 200)},
    group={"x": 300, "y": 262, "w": 540, "h": 92, "label": "UNDECIDED — PICK ONE"},
    steps=[
      ("op","tmp","both","Request capacity","The Seed is short of room for the control planes it hosts."),
      ("tmp","scan","both","Draw and reserve a machine","Same draw and lock as workflow 01."),
      ("tmp","seg","both","Resolve the Seed's network","Its own network, not a tenant VLAN."),
      ("tmp","a","both","Option A: Agent flow","Nearly all of 01 is reusable. The Seed stops being special."),
      ("tmp","b","both","Option B: ignition","No dependency on the Seed's own operators. Manual."),
      ("a","seed","both","Node joins","Then approve certificates if the path needs it."),
      ("seed","seed","both","Await ready","Workloads schedule onto it."),
    ])

WORKFLOWS["13-upgrade-hosted-cluster-workers"] = dict(
    title="13 :: Upgrade Hosted Cluster Workers",
    subtitle="Separate from the control plane so unpredictable workload drain cannot delay "
             "API availability. Run 14 first.",
    nodes={"cust": CUST, "tmp": TMP, "git": GIT, "argo": ARGO,
           "pool": N(800, 180, "Warm pool", "supplies surge nodes"),
           "z1": N(300, 430, "Zone 1", "rolls first", 150),
           "z2": N(470, 430, "Zone 2", "then", 150),
           "z3": N(640, 430, "Zone 3", "then", 150)},
    group={"x": 280, "y": 394, "w": 530, "h": 110, "label": "ONE ZONE AT A TIME"},
    steps=[
      ("cust","tmp","both","Choose a window","The tenant picks when."),
      ("tmp","pool","both","Check surge capacity","Each surging node comes out of the warm pool."),
      ("tmp","tmp","both","Preflight","Healthy, nothing else in flight, control plane already upgraded."),
      ("tmp","git","both","Patch the release image","By digest. Set surge explicitly; do not inherit a default."),
      ("git","argo","both","Merge and apply","Out of band."),
      ("argo","z1","both","Roll zone 1","New node up before the old one drains."),
      ("z1","z2","both","Roll zone 2","Only after zone 1 settles."),
      ("z2","z3","both","Roll zone 3","A failure mid-roll then affects one zone, not three."),
    ])

WORKFLOWS["14-upgrade-hosted-cluster-control-plane"] = dict(
    title="14 :: Upgrade Hosted Cluster Control Plane",
    subtitle="Pods on a hub, no tenant workloads to drain, so it is fast and predictable. "
             "Gated by what the hub supports.",
    nodes={"cust": CUST, "tmp": TMP, "git": GIT, "argo": ARGO,
           "hub": N(760, 36, "Hub version", "the ceiling", 200),
           "etcd": N(760, 180, "etcd backup", "verified, not just taken", 200),
           "cp": N(400, 430, "Control plane", "3 replicas, one at a time", 240)},
    group=None,
    steps=[
      ("cust","tmp","both","Choose a window","Or the platform does; it should be invisible."),
      ("tmp","hub","both","Check the ceiling","A cluster may never be newer than its hub supports."),
      ("tmp","tmp","both","Preflight","API up, quorum intact, no degraded operators."),
      ("tmp","etcd","both","Back up and verify","An unverified backup produces confidence, not safety."),
      ("tmp","git","both","Patch the release image","By digest."),
      ("git","argo","both","Merge and apply","Out of band."),
      ("argo","cp","both","Roll one replica at a time","Two of three stay up throughout."),
      ("cp","tmp","both","Verify between replicas","Losing quorum mid-roll is the hard failure."),
    ])

WORKFLOWS["15-upgrade-mce-hub"] = dict(
    title="15 :: Upgrade an MCE Hub",
    subtitle="The skew check is the real work here. The upgrade itself is ordinary.",
    nodes={"op": N(30, 36, "Operator", "platform"), "tmp": TMP,
           "hcs": N(760, 36, "Hosted clusters", "every one on this hub", 200),
           "ctl": N(760, 180, "Controller", "paused during the roll", 200),
           "cp": N(330, 430, "Hub masters", "one at a time", 200),
           "wk": N(570, 430, "Hub workers", "with surge", 200)},
    group=None,
    steps=[
      ("op","tmp","both","Request the upgrade","Raises the ceiling for everything hosted here."),
      ("tmp","hcs","both","Inventory what is hosted","Every cluster, with its current version."),
      ("tmp","hcs","both","Compute skew both ways","Too far forward strands the oldest clusters."),
      ("tmp","tmp","both","Preflight and back up","Healthy, quorum intact, nothing in flight anywhere."),
      ("tmp","ctl","both","Pause the controller","Rolling workers churns pods; do not act on transient state."),
      ("tmp","cp","both","Roll the masters","Quorum held throughout."),
      ("cp","wk","both","Roll the workers","They carry the hosted control planes."),
      ("wk","ctl","both","Resume the controller","Must happen on the failure path too."),
    ])

WORKFLOWS["16-upgrade-kv-cluster"] = dict(
    title="16 :: Upgrade a KV Cluster",
    subtitle="The most careful upgrade in the platform. Every node being rolled is carrying "
             "other people's running machines.",
    nodes={"op": N(30, 36, "Operator", "platform"), "tmp": TMP,
           "seed": N(760, 36, "Seed", "hosts the control plane", 200),
           "mark": N(760, 180, "Cell marked", "upgrading", 200),
           "hv": N(330, 430, "Hypervisor", "one at a time", 200),
           "tgt": N(570, 430, "Rest of cell", "absorbs its guests", 200)},
    group=None,
    steps=[
      ("op","tmp","both","Request the upgrade","Blast radius is every tenant VM on the cell."),
      ("tmp","tmp","both","Preflight","Cell healthy, shared storage healthy, nothing in flight."),
      ("tmp","mark","both","Mark the cell upgrading","Placement must honour it, or the next evacuation fails."),
      ("tmp","seed","both","Upgrade the control plane","Workflow 14 with the Seed as hub."),
      ("tmp","hv","both","Cordon one hypervisor","Only one, ever."),
      ("hv","tgt","both","Evacuate its guests","Live migration. A guest that will not move stops the roll."),
      ("tgt","hv","both","Upgrade and wait","Ready, then KubeVirt schedulable, then uncordon."),
      ("hv","mark","both","Next hypervisor, or done","Clear the mark at the end."),
    ])

WORKFLOWS["17-upgrade-seed-cluster"] = dict(
    title="17 :: Upgrade a Seed Cluster",
    subtitle="First in a zone. Its workers carry the control planes of every KubeVirt "
             "cluster there, so infrastructure management pauses — tenant VMs do not.",
    nodes={"op": N(30, 36, "Operator", "rare"), "tmp": TMP,
           "kvs": N(760, 36, "KV clusters", "their control planes live here", 200),
           "vms": N(760, 180, "Tenant VMs", "unaffected throughout", 200),
           "cp": N(330, 430, "Seed masters", "one at a time", 200),
           "wk": N(570, 430, "Seed workers", "with surge", 200)},
    group=None,
    steps=[
      ("op","tmp","both","Request the upgrade","First step in the zone's upgrade order."),
      ("tmp","kvs","both","Compute skew","Against the KV clusters hosted here, not tenant clusters."),
      ("tmp","tmp","both","Preflight","No cell operation anywhere in the zone may be in flight."),
      ("tmp","cp","both","Roll the masters","Quorum held."),
      ("cp","wk","both","Roll the workers with surge","Hosted control planes move before the old node goes."),
      ("wk","kvs","both","KV APIs return","Creating, scaling and upgrading cells was blocked until now."),
      ("kvs","vms","both","Tenant VMs never noticed","The data plane is independent of the control plane."),
    ])

WORKFLOWS["18-migrate-hosted-cluster-version-band"] = dict(
    title="18 :: Migrate a Hosted Cluster to Another Version Band",
    subtitle="A rebuild, not a move. No operation relocates a control plane, and a cluster's "
             "NodePools cannot span hubs.",
    nodes={"cust": CUST, "tmp": TMP,
           "old": N(330, 430, "Old hub", "stays up throughout", 200),
           "new": N(610, 430, "New hub", "newer version band", 200),
           "cap": N(760, 36, "Capacity check", "both clusters at once", 200),
           "ten": N(760, 180, "Tenant", "moves their workloads", 200)},
    group=None,
    steps=[
      ("cust","tmp","both","Request a newer version","Beyond what their hub can reach."),
      ("tmp","cap","both","Check capacity for both","The old cluster stays up, so the pools carry double."),
      ("tmp","new","both","Create the new cluster","Workflow 03 on the target hub, same worker shape."),
      ("new","tmp","both","Await full readiness","Control plane healthy and every worker present."),
      ("tmp","ten","both","Tenant moves their workloads","Not a platform step. Mostly repointing their pipelines."),
      ("ten","tmp","both","Wait for confirmation","Indefinitely. A timeout here is a data-loss incident."),
      ("tmp","old","both","Delete the old cluster","Workflow 05. Only now."),
    ])


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root{
    --bg:#0e0e11; --panel:#16161b; --line:#2c2c35; --ink:#e6e6ec; --dim:#8b8b99;
    --accent:#4da3ff; --ok:#3ecf8e; --warn:#e8b339; --vm:#b57bff; --bm:#58c7d8;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:14px/1.5 "Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  header{padding:18px 24px 10px;border-bottom:1px solid var(--line)}
  h1{margin:0;font-size:19px;font-weight:600;letter-spacing:.2px}
  .sub{color:var(--dim);font-size:13px;margin-top:4px;max-width:900px}
  .wrap{display:flex;align-items:stretch;min-height:700px}
  .stage{flex:1;padding:14px 10px 12px 18px;display:flex;flex-direction:column;min-width:0}
  #svg{width:100%;height:400px;flex:0 0 auto}
  .detail{margin-top:10px;border:1px solid var(--line);border-radius:8px;background:#121217;
          padding:11px 14px;flex:1;min-height:210px;max-height:350px;overflow:auto}
  .dh{color:var(--dim);font-size:10.5px;text-transform:uppercase;letter-spacing:1.2px;
      margin:0 0 8px;font-weight:600}
  .k{color:var(--dim);font-size:10px;text-transform:uppercase;letter-spacing:1px;
     display:block;margin:9px 0 3px}
  .k:first-of-type{margin-top:0}
  .detail pre{margin:0;white-space:pre-wrap;word-break:break-word;
       font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
       font-size:11.5px;line-height:1.55;color:#cfd3da}
  pre.call{color:var(--accent)}
  pre.warn{color:var(--warn)}
  .empty{color:var(--dim);font-style:italic;font-size:12.5px}
  .side{width:366px;border-left:1px solid var(--line);background:var(--panel);
        padding:14px 16px;overflow-y:auto;max-height:770px}
  .side h2{font-size:12px;text-transform:uppercase;letter-spacing:1.2px;
           color:var(--dim);margin:0 0 10px;font-weight:600}
  .step{padding:8px 10px;border-radius:6px;cursor:pointer;display:flex;gap:9px;
        border:1px solid transparent;margin-bottom:3px}
  .step:hover{background:#1e1e25}
  .step.on{background:#1b2838;border-color:var(--accent)}
  .step.off{opacity:.3}
  .num{color:var(--dim);font-variant-numeric:tabular-nums;min-width:22px;font-size:12px}
  .step.on .num{color:var(--accent)}
  .txt{flex:1}
  .nm{font-weight:500;display:block}
  .nt{color:var(--dim);font-size:12px;margin-top:2px;display:block}
  .tag{font-size:10px;padding:1px 6px;border-radius:99px;border:1px solid var(--line);
       color:var(--dim);align-self:flex-start;margin-top:2px}
  .tag.VM{color:var(--vm);border-color:var(--vm)}
  .tag.BM{color:var(--bm);border-color:var(--bm)}
  .tag.IPMI{color:var(--warn);border-color:var(--warn)}
  footer{display:flex;gap:10px;align-items:center;padding:12px 18px;
         border-top:1px solid var(--line);flex-wrap:wrap}
  button{background:#1e1e25;color:var(--ink);border:1px solid var(--line);
         border-radius:6px;padding:7px 14px;cursor:pointer;font-size:13px}
  button:hover{border-color:var(--accent)}
  button.pri{background:var(--accent);border-color:var(--accent);color:#06121f;font-weight:600}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
  .seg button{border:0;border-radius:0}
  .seg button.sel{background:#2a3a4d;color:var(--accent)}
  .spacer{flex:1}
  .caption{color:var(--dim);font-size:12px}
  text{font-family:"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  .node rect{fill:#191920;stroke:var(--line);stroke-width:1.5;rx:8}
  .node.hot rect{stroke:var(--accent);stroke-width:2.5;fill:#1b2838}
  .node.done rect{stroke:#2f5d48}
  .node text{fill:var(--ink);font-size:13px;font-weight:500}
  .node tspan.s{fill:var(--dim);font-size:11px;font-weight:400}
  .group rect{fill:none;stroke:var(--line);stroke-dasharray:4 4;rx:10}
  .group text{fill:var(--dim);font-size:11px;letter-spacing:1px}
  .edge{stroke:#3a3a46;stroke-width:1.5;fill:none}
  .edge.hot{stroke:var(--accent);stroke-width:2.5}
  .elab{fill:var(--accent);font-size:11.5px;font-weight:500}
  #dot{fill:var(--accent);filter:drop-shadow(0 0 6px var(--accent))}
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <div class="sub">__SUB__</div>
</header>

<div class="wrap">
  <div class="stage">
    <svg id="svg" viewBox="0 0 1000 560"
         xmlns="http://www.w3.org/2000/svg" aria-label="Workflow diagram"></svg>
    <div class="detail" id="detail"></div>
  </div>
  <aside class="side">
    <h2>Steps</h2>
    <div id="steps"></div>
  </aside>
</div>

<footer>
  <button class="pri" id="play">Play</button>
  <button id="prev">Prev</button>
  <button id="next">Next</button>
  <button id="rst">Restart</button>
  <span id="modes" style="display:none">
    <span class="caption">__MODE_CAPTION__</span>
    <span class="seg">
      <button id="mBM" class="sel">__MODE_A__</button>
      <button id="mVM">__MODE_B__</button>
    </span>
  </span>
  <div class="spacer"></div>
  <span class="caption" id="cap"></span>
</footer>

<script>
const NODES = __NODES__;
const GROUPS = __GROUPS__;
const RAW   = __STEPS__;
const HAS_MODES = __MODES__;
const STEPS = RAW.map(r => ({f:r[0], t:r[1], b:r[2], n:r[3], d:r[4], x:r[5]||null}));
const esc = s => String(s).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));

function showDetail(s){
  const box=document.getElementById("detail");
  if(!s){ box.innerHTML='<div class="dh">Exchange</div>'+
      '<div class="empty">Pick a step, or press play.</div>'; return; }
  if(!s.x){ box.innerHTML='<div class="dh">Exchange &mdash; '+esc(s.n)+'</div>'+
      '<div class="empty">Not documented yet for this step.</div>'; return; }
  let h='<div class="dh">Exchange &mdash; '+esc(s.n)+'</div>';
  if(s.x.call) h+='<span class="k">Call</span><pre class="call">'+esc(s.x.call)+'</pre>';
  if(s.x.send) h+='<span class="k">Sends</span><pre>'+esc(s.x.send)+'</pre>';
  if(s.x.recv) h+='<span class="k">Receives</span><pre>'+esc(s.x.recv)+'</pre>';
  if(s.x.warn) h+='<span class="k">Watch out</span><pre class="warn">'+esc(s.x.warn)+'</pre>';
  box.innerHTML=h;
}

const svg = document.getElementById("svg");
const NS = "http://www.w3.org/2000/svg";
const el = (n,a={}) => { const e=document.createElementNS(NS,n);
  for(const k in a) e.setAttribute(k,a[k]); return e; };
const cx = n => NODES[n].x + NODES[n].w/2;
const cy = n => NODES[n].y + NODES[n].h/2;

let mode="BM", idx=-1, playing=false, timer=null;
const vis = s => s.b==="both" || s.b===mode || (s.b==="IPMI" && mode==="BM");
const active = () => STEPS.map((s,i)=>i).filter(i=>vis(STEPS[i]));

function drawStatic(){
  svg.innerHTML="";
  GROUPS.forEach(G=>{
    const g = el("g",{class:"group"});
    g.appendChild(el("rect",{x:G.x,y:G.y,width:G.w,height:G.h}));
    const gt = el("text",{x:G.x+14,y:G.y+20}); gt.textContent=G.label;
    g.appendChild(gt); svg.appendChild(g);
  });
  svg.appendChild(el("g",{id:"edges"}));
  for(const k in NODES){
    const d=NODES[k];
    const n=el("g",{class:"node",id:"n_"+k});
    n.appendChild(el("rect",{x:d.x,y:d.y,width:d.w,height:d.h}));
    const t=el("text",{x:d.x+d.w/2,y:d.y+d.h/2-3,"text-anchor":"middle"});
    t.textContent=d.t;
    if(d.s){ const s=el("tspan",{x:d.x+d.w/2,dy:"15",class:"s"}); s.textContent=d.s;
             t.appendChild(s); }
    n.appendChild(t); svg.appendChild(n);
  }
  svg.appendChild(el("circle",{id:"dot",r:7,opacity:0}));
}

function path(a,b){
  if(a===b){ // self-loop: below the node when it sits near the top edge
    const d=NODES[a], x=cx(a);
    if(d.y < 72){ const y=d.y+d.h;
      return `M ${x-28} ${y} C ${x-40} ${y+46} ${x+40} ${y+46} ${x+28} ${y}`; }
    const y=d.y;
    return `M ${x-28} ${y} C ${x-40} ${y-46} ${x+40} ${y-46} ${x+28} ${y}`;
  }
  const x1=cx(a), y1=cy(a), x2=cx(b), y2=cy(b);
  const mx=(x1+x2)/2, my=(y1+y2)/2;
  const dx=x2-x1, dy=y2-y1, len=Math.hypot(dx,dy)||1;
  const bow=Math.min(46,len*0.12);
  return `M ${x1} ${y1} Q ${mx - dy/len*bow} ${my + dx/len*bow} ${x2} ${y2}`;
}

function render(){
  document.querySelectorAll(".node").forEach(n=>n.classList.remove("hot","done"));
  const edges=document.getElementById("edges"); edges.innerHTML="";
  document.getElementById("dot").setAttribute("opacity",0);

  const act=active(), here=act.indexOf(idx);
  act.forEach((si,pos)=>{ if(here>=0 && pos<here)
    document.getElementById("n_"+STEPS[si].t)?.classList.add("done"); });

  if(idx>=0 && STEPS[idx]){
    const s=STEPS[idx];
    const p=el("path",{class:"edge hot",d:path(s.f,s.t)});
    edges.appendChild(p);
    document.getElementById("n_"+s.f).classList.add("hot");
    document.getElementById("n_"+s.t).classList.add("hot");

    const total=p.getTotalLength();
    const mid=p.getPointAtLength(total*0.5);
    const a=p.getPointAtLength(Math.max(0,total*0.5-6));
    const b=p.getPointAtLength(Math.min(total,total*0.5+6));
    const tx=b.x-a.x, ty=b.y-a.y, tl=Math.hypot(tx,ty)||1;
    const off=16, lx=mid.x+(-ty/tl*off), ly=mid.y+(tx/tl*off);
    const w=s.n.length*6.4+14;
    edges.appendChild(el("rect",{x:lx-w/2,y:ly-11,width:w,height:18,rx:4,
      fill:"#0e0e11",stroke:"#2c2c35","stroke-width":1}));
    const lab=el("text",{x:lx,y:ly+2,"text-anchor":"middle",class:"elab"});
    lab.textContent=s.n; edges.appendChild(lab);

    const dot=document.getElementById("dot");
    dot.setAttribute("opacity",1);
    const t0=performance.now(), dur=900;
    (function anim(now){
      const k=Math.min(1,(now-t0)/dur);
      const pt=p.getPointAtLength(total*k);
      dot.setAttribute("cx",pt.x); dot.setAttribute("cy",pt.y);
      if(k<1) requestAnimationFrame(anim);
    })(t0);
  }

  document.querySelectorAll(".step").forEach(n=>{
    const i=+n.dataset.i;
    n.classList.toggle("on", i===idx);
    n.classList.toggle("off", !vis(STEPS[i]));
  });
  showDetail(idx>=0 ? STEPS[idx] : null);
  document.getElementById("cap").textContent =
    idx<0 ? act.length+" steps" : "Step "+(act.indexOf(idx)+1)+" of "+act.length;
}

function buildList(){
  const box=document.getElementById("steps"); box.innerHTML="";
  STEPS.forEach((s,i)=>{
    const d=document.createElement("div");
    d.className="step"; d.dataset.i=i;
    d.innerHTML='<span class="num">'+(i+1)+'</span><span class="txt">'+
      '<span class="nm">'+s.n+'</span><span class="nt">'+s.d+'</span></span>'+
      (s.b!=="both"?'<span class="tag '+s.b+'">'+s.b+'</span>':'');
    d.onclick=()=>{ if(vis(s)){ idx=i; stop(); render(); } };
    box.appendChild(d);
  });
}

function go(dir){
  const act=active(); if(!act.length) return;
  let p=act.indexOf(idx);
  p = p<0 ? (dir>0?0:act.length-1) : p+dir;
  if(p>=act.length){ stop(); idx=act[act.length-1]; render(); return; }
  if(p<0) p=0;
  idx=act[p]; render();
  document.querySelector('.step[data-i="'+idx+'"]')
    ?.scrollIntoView({block:"nearest",behavior:"smooth"});
}
function stop(){ playing=false; clearInterval(timer);
  document.getElementById("play").textContent="Play"; }
function play(){
  if(playing){ stop(); return; }
  playing=true; document.getElementById("play").textContent="Pause";
  const act=active();
  if(idx===act[act.length-1]) idx=-1;
  go(1);
  timer=setInterval(()=>{ const a=active();
    if(idx===a[a.length-1]){ stop(); return; } go(1); },1600);
}
function setMode(m){
  mode=m; stop(); idx=-1;
  document.getElementById("mBM").classList.toggle("sel",m==="BM");
  document.getElementById("mVM").classList.toggle("sel",m==="VM");
  render();
}

document.getElementById("play").onclick=play;
document.getElementById("next").onclick=()=>{stop();go(1)};
document.getElementById("prev").onclick=()=>{stop();go(-1)};
document.getElementById("rst").onclick=()=>{stop();idx=-1;render()};
if(HAS_MODES){
  document.getElementById("modes").style.display="";
  document.getElementById("mBM").onclick=()=>setMode("BM");
  document.getElementById("mVM").onclick=()=>setMode("VM");
}
document.addEventListener("keydown",e=>{
  if(e.key==="ArrowRight"){stop();go(1)} if(e.key==="ArrowLeft"){stop();go(-1)}
  if(e.key===" "){e.preventDefault();play()}
});

// Build FIRST. setMode() calls render(), which needs the SVG and the step list
// to exist — doing this earlier throws and aborts the rest of the script.
drawStatic(); buildList();

// Deep link: #step=7, and #vm to open on the virtual branch. Mode before step,
// because switching mode resets the position.
(function(){
  const h=location.hash.slice(1);
  if(HAS_MODES && /vm/i.test(h)) setMode("VM");
  const m=h.match(/step=(\d+)/);
  if(m){ const i=+m[1]-1; if(STEPS[i] && vis(STEPS[i])) idx=i; }
})();

render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    for name, cfg in WORKFLOWS.items():
        html = page(cfg["title"], cfg["subtitle"], cfg["nodes"],
                    cfg["group"], cfg["steps"],
                    cfg.get("mode_labels", ("Pool", "Bare metal", "Virtual")),
                    cfg.get("tags"), cfg.get("look"))
        (HERE / f"{name}.html").write_text(html, encoding="utf-8")
        print(f"wrote {name}.html")
    print(f"\n{len(WORKFLOWS)} animations generated.")
