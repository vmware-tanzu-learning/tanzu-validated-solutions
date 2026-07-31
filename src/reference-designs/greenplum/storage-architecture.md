# Storage Architecture - vSAN & vSAN Storage Cluster

This section describes how Tanzu Greenplum consumes vSAN ESA and the vSAN storage cluster (vSAN Max) for large-scale analytical workloads. It assumes the mirrorless segment configuration established in [Tanzu Greenplum Resilience Topology on vSphere: Mirrored and Mirrorless](./resilience-topology.md#tanzu-greenplum-resilience-topology-on-vsphere-mirrored-and-mirrorless) and, for the baseline, a single-rack failure domain. The design emphasizes deterministic latency, isolation of I/O patterns, and alignment of vSAN storage policies with Tanzu Greenplum's resiliency model. It builds directly on the workload storage characteristics in [Storage Access Patterns](./workload-characteristics.md#storage-access-patterns) and the recommended vSAN configuration settings, and it is where the durability that the mirrorless decision depends on is delivered.

## Design Philosophy - Storage for Mirrorless Tanzu Greenplum

In a mirrorless design, data resiliency lives entirely at the storage layer. This is the defining constraint for everything in this section as there is no second copy of segment data inside Tanzu Greenplum; vSAN is solely responsible for surviving a disk or host failure without data loss. The storage design therefore has to be more conservative than it would be under a mirrored database, not less.

Tanzu Greenplum's I/O profile, established in [Storage Access Patterns](./workload-characteristics.md#storage-access-patterns), shapes what the storage must deliver. It runs long parallel analytical queries with sustained large sequential reads, bursty temp-spill writes, and small synchronous WAL writes. From that profile, the storage layer must provide three things:

* **Predictable latency under failure, not just in the ideal case.** Because query pace is set by the slowest segment, a latency spike on one segment's storage during a rebuild elongates the whole query. The design has to hold up while vSAN is rebuilding, which is precisely when redundancy is thinnest.  
* **Isolation of I/O patterns**, so that a heavy temp spill or a WAL write burst on one VMDK does not degrade the scan latency of another.  
* **WAL durability without a bottleneck**, since a single slow WAL fsync can stall query execution across the cluster.

These are achieved through logical separation at the VMDK and storage-policy level rather than through physical LUNs. Different VMDKs on the same VM can carry different protection policies, RAID schemes, and stripe widths, which lets each class of Tanzu Greenplum I/O be matched to the protection and performance it needs. The subsections that follow define that per-VMDK layout and then the platform-level vSAN settings that support it.

## Minimum Disk Layout and SPBM Guidelines

Each Tanzu Greenplum VM separates its I/O onto dedicated VMDKs, and each VMDK gets a storage policy matched to its I/O pattern and its recoverability. These policies are applied per VMDK at provisioning and can be changed online later, since vSAN reconfigures policy without downtime.

| Disk Type | VMDK | FTT  | RAID | Justification |
| ----- | ----- | ----- | ----- | ----- |
| OS | Dedicated | 1 | RAID-1 or RAID-5 | Boot, binaries, logs. Low I/O intensity. Separate from database for management simplicity. Fast recovery; no query impact if degraded. |
| Segment Data | Dedicated | 2 recommended (1 acceptable for small or non-critical) | RAID-6 for FTT=2 (RAID-5 for FTT=1) | Primary user data: large sequential reads, mixed writes, latency-sensitive. This is the only copy of the data in a mirrorless design, so the FTT choice is the entire data-protection story. **See the FTT discussion below.** |
| WAL | Dedicated | 1 | RAID-1 | PostgreSQL WAL: small, synchronous, fsync-heavy writes that are extremely latency-sensitive, where a single slow fsync stalls queries cluster-wide. RAID-1 minimizes write-path fan-out and gives the lowest, most predictable fsync latency. RAID-5 is deliberately not used here because parity read-modify-write penalizes exactly this small-synchronous-write pattern. |
| Temp | Dedicated | 1 recommended  (0 as an explicit optimization) | RAID-1  (RAID-0 for FTT=0) | Hash joins, sorts, and spills: bursty, large, short-lived, and fully reconstructable from base tables. FTT=1 keeps spill behavior consistent with the rest of the failure model. FTT=0 saves write overhead but adds a new failure surface.  **See the temp discussion below.** |

**Note:** 

* These host-count minimums are why the production baseline is six hosts ([Host Count and Configuration Model](./vsphere-cluster-design.md#host-count-and-configuration-model)): FTT=2 via RAID-6, the efficient way to tolerate a failure during a rebuild, is only achievable at six hosts or more. A four-host cluster is limited to FTT=1 and is therefore positioned for PoC and development rather than production.  
* No performance implications when using erasure codes in the ESA. Refer to the [vSAN Space Efficiency](https://www.vmware.com/docs/vmw-vsan-space-efficiency) documentation for more details.

**On Write Ahead Log (WAL):** WAL is the one VMDK where the RAID choice is not a capacity-versus-performance preference but a correctness-of-design point. Its latency directly gates commit and query progress (see [Storage Access Patterns](./workload-characteristics.md#storage-access-patterns)), so it takes the lowest-latency, lowest-fan-out policy available, which is RAID-1.

**On FTT for segment data, the central mirrorless decision.** FTT=1 lets the cluster survive one host or disk failure. The exposure specific to a mirrorless design is what happens *during the rebuild* that follows: with FTT=1, the affected segment data runs with **no redundancy at all** until vSAN finishes rebuilding, and that rebuild competes for I/O and raises latency at the moment the workload is already degraded. If a second host fails inside that rebuild window, the segment data is lost. In a mirrorless cluster that is not an in-cluster recovery event - it is a disaster-recovery event, handled by the DR cluster described in [Rack Design for Tanzu Greenplum Clusters](./rack-design.md#rack-design-for-tanzu-greenplum-clusters). This is the plain meaning of FTT=1 for mirrorless Tanzu Greenplum, and it should be stated as such to the business, not left implicit.

FTT=2 removes that exposure by keeping redundancy through a single failure *and* its rebuild, so a second failure during the rebuild is survived rather than escalated to DR. For this reason **FTT=2 is the recommended policy for segment data on production mirrorless clusters**, with FTT=1 reserved for smaller or non-critical systems that accept the DR-escalation risk in exchange for lower capacity cost.

The capacity cost is the tradeoff to weigh, and it differs sharply by RAID scheme:

| Policy | vSAN implementation | Raw capacity overhead | Minimum hosts | Explanation |
| ----- | ----- | ----- | ----- | ----- |
| FTT=1, RAID-5 | Erasure Coding (2+1) *(ESA)* | ~1.5x | 4 to 5 | Adaptive RAID-5 in vSAN ESA dynamically selects 2+1 scheme for clusters containing **3 to 5 hosts**. The absolute technical minimum required by vSAN is **3 hosts**. However, 4 hosts are strongly recommended so the cluster can perform self-healing or host maintenance without losing compliance. |
| FTT=1, RAID-5 | Erasure Coding (4+1) *(ESA)* | 1.25x | 6 or more | In vSAN ESA, once a cluster reaches **6 or more hosts**, vSAN automatically transforms RAID-5 objects into the 4+1 scheme to optimize capacity efficiency down to 1.25x. |
| FTT=1, RAID-5 | Erasure Coding (3+1) *(OSA)* | 1.33x | 4 | In legacy vSAN OSA, RAID-5 does not use 2+1 or 4+1. Instead, it uses a fixed **3+1 scheme** (3 Data + 1 Parity), which yields a **1.33x (133%)** overhead and requires a minimum of **4 hosts**. |
| FTT=1, RAID-1 | Mirroring (2 replicas + witness) | ~2x | 6 | Standard FTT=1 RAID-1 mirroring requires 2 data replicas plus 1 witness component (2 * FTT + 1 = 3). While 4 hosts are standard practice for maintenance headroom, the official technical minimum requirement in vSphere is 3 hosts. |
| FTT=2, RAID-6 | Erasure Coding (4+2) | 1.5x | 3 | RAID-6 generates 6 components (4 data + 2 parity) which must be distributed across 6 separate fault domains/hosts. 7 hosts are recommended to maintain rebuild reservation. |
| FTT=2, RAID-1 | Mirroring (3 replicas + witness) | 3x | 5 | 2 * FTT + 1 = 2(2) + 1 = 5 hosts required to host 3 data replicas and witness components. |

The erasure-coding path is what makes FTT=2 affordable. At six or more hosts, FTT=1 RAID-5 costs 1.25x and FTT=2 RAID-6 costs 1.5x, so the additional failure tolerance is a premium of 20 percent on raw capacity.   
In a mirrorless design, where vSAN holds the only copy of the data, a second failure during a rebuild would otherwise force a disaster-recovery event. This is why RAID-6 at FTT=2 is the recommended segment-data policy wherever the six-host minimum is met.

Host count sets what is reachable, and it also changes the price of each option. A cluster of six or more hosts is recommended to use FTT=2 RAID-6 as the production policy, where the step up from FTT=1 costs 20 percent. A cluster of exactly five hosts that requires two-failure tolerance has one option, FTT=2 through RAID-1 mirroring at 3x capacity, because RAID-6 is unavailable below six hosts. A four-host cluster cannot reach FTT=2 by any scheme and is limited to FTT=1.

There is a further consequence at a small scale worth stating plainly. At four to five hosts, RAID-5 at FTT=1 uses the 2+1 scheme and already costs 1.5x, which is the same overhead as RAID-6 at FTT=2 but with only single-failure tolerance. A small cluster therefore pays RAID-6 overhead for RAID-5 resilience. This is an additional reason the production baseline is six hosts ([Host Count and Configuration Model](./vsphere-cluster-design.md#host-count-and-configuration-model)), beyond the availability argument made there.

**Matching storage protection to compute admission control.** FTT and vSphere HA admission control protect different layers and must be set to survive the *same* number of failures, or the design is internally inconsistent. Admission control ([vSphere HA Configuration Recommendations](./vsphere-cluster-design.md#vsphere-ha-configuration-recommendations)) reserves compute capacity so VMs can restart; FTT reserves storage redundancy so the data survives. If they disagree, the weaker one governs.   
Specifically, pairing N+2 admission control with FTT=1 makes no sense in a mirrorless design: on the second host failure the compute cluster still has reserved capacity to restart VMs, but the FTT=1 segment data has already lost its redundancy, so there is nothing healthy to restart against. The reserved compute is wasted because the data layer failed first. The rule is therefore to match the two layers:

* **N+1 admission control pairs with FTT=1** the cluster is designed to survive one failure at both the compute and storage layers, and a second failure is a DR event.  
* **N+2 admission control pairs with FTT=2 (RAID-6)**  the cluster is designed to survive two failures at both layers, and the compute reservation and the storage redundancy agree.

**On temp with FTT=1 or 0:** Temp data is short-lived and can always be regenerated from base tables, so FTT=0 (no redundancy) is technically defensible and saves overhead on a very write-heavy path. The reason this architecture still recommends FTT=1 for temp is about avoiding *new* failure modes, and it is simplest to see through the failure behavior:

* With temp at **FTT=1**, a single disk or component failure under a spilling query is absorbed by vSAN transparently. The query keeps running. Temp behaves like every other protected VMDK, and there are no surprises.  
* With temp at **FTT=0**, that same single component failure destroys the spill data, and any query currently spilling to it fails immediately, even though no segment or host has actually gone down.

That second case is the problem. FTT=0 introduces a way for a query to fail on an isolated storage-component failure that would otherwise have been invisible. A mirrorless design already accepts that queries fail when a *segment or host* is lost; it should not introduce a *new* class of failure where an isolated disk hiccup under a spill aborts a running query while the rest of the cluster remains healthy.   
Keeping temp at FTT=1 or FTT=2 (depending on the admission control policy) closes that gap, so a query only ever fails for reasons the failure model already accounts for. 

**On erasure coding on ESA.** vSAN ESA largely removes the historical write penalty of erasure coding, so RAID-5 on ESA is close to RAID-1 in write behavior while using far less capacity. This is what makes RAID-5 a reasonable default for segment data on ESA specifically, whereas on older OSA it would have been a harder tradeoff.   

As vSAN ESA's log-structured write path removes the erasure coding write penalty, both RAID-5 and RAID-6 deliver near-RAID-1 performance at a fraction of the raw capacity cost. Recommending RAID-5 on ESA for Tanzu Greenplum focuses on this performance efficiency; specifying RAID-6 (FTT=2) adds the higher fault tolerance needed for a mirrorless segment architecture. The two choices answer different requirements: performance versus resilience.

## Platform-Level vSAN Configuration

Beyond per-VMDK policy, a small set of cluster-wide vSAN settings matter specifically for Tanzu Greenplum and must be set consistently, since they interact directly with the mirrorless resiliency model.

* **Reserved rebuild capacity.** Enable both Operations Reserve and Host Rebuild Reserve so the cluster always retains enough free capacity to rebuild after a host failure. This is not optional for a mirrorless design; it is the headroom that lets vSAN restore redundancy after the one failure FTT=1 tolerates, and it is the direct mitigation for the during-rebuild exposure discussed above.  
* **Compression off.** Disable vSAN space-efficiency compression for Tanzu Greenplum. Tanzu Greenplum already stores data in compressed columnar form, so vSAN compression yields little and adds write latency that harms data loading and temp spills, the two most write-intensive Tanzu Greenplum operations.  
* **Thick provisioning (object space reservation).** Provision Tanzu Greenplum data VMDKs thick. A database doing large sequential writes should not incur first-write allocation latency, and thick provisioning also removes the risk of a capacity surprise on a growing analytical dataset.

## Storage Failure Behavior: Physical Disk Failure

This completes the failure-class walkthrough begun in [vSphere Cluster and Compute Design](./vsphere-cluster-design.md#vsphere-cluster-and-compute-design). That section walked through the failure classes as the compute and database layers experienced them. This section completes that walkthrough from the storage side, and it is the single place that maps each storage-failure scenario to its outcome, what vSAN heals on its own, what pulls in vSphere HA and Tanzu Greenplum recovery, and what escalates to disaster recovery. Because a mirrorless design places the entire data-protection load on vSAN, these boundaries are not academic. They are the definition of what the cluster can and cannot survive without a DR event.

Two ideas make the rest of this section readable. 

First, vSAN counts protection in terms of a **failure budget**: 

* FTT=2 tolerates two concurrent component failures.  
* FTT=1 tolerates one. 

Second, the *scope* of a failure matters as much as the count. A single disk failure leaves the Tanzu Greenplum VMs running and is handled purely in storage, whereas a host failure also takes down the VMs on that host and therefore engages the compute-recovery path from [Physical Host Failure and Recovery](./vsphere-cluster-design.md#physical-host-failure-and-recovery) at the same time. The scenarios below are organized around those two ideas.

**Single device (disk) failure**

This is the normal case, and it is a non-event for the database under either recommended policy (FTT=1 or FTT=2).

A failed NVMe device in a vSAN ESA host is masked completely by vSAN. It marks the device's components degraded and continues serving all reads and writes from the surviving replica or parity components on other hosts. The guest VMs, the database processes, and Tanzu Greenplum's FTS observe nothing beyond, at most, a brief latency increase. No segment is marked down, and no database-level recovery occurs.

vSAN then rebuilds the affected components onto healthy capacity, immediately for a genuinely failed device or after the repair-delay timer for a transient absence. This is self-healing in the truest sense: the cluster returns to full redundancy with no operator and no database action.   
Under both FTT=2/RAID-6 and FTT=1/RAID-1 or RAID-5, the single-disk case heals the same way; the difference between the policies only appears if a *second* failure arrives before this rebuild finishes, which is the next scenario.

**Second failure during the rebuild window**

This scenario is the reason that the production baseline is recommended to be set to FTT=2, and it is where the two recommended policies diverge completely.

Every rebuild has a window during which the failed components are being reconstructed and the affected data is running on reduced redundancy. What happens if a second, overlapping failure lands inside that window depends entirely on the failure budget:

* **On FTT=2 / RAID-6 (production baseline):** the first failure consumed one unit of the two-failure budget, leaving one in reserve. A second overlapping failure is still tolerated.   
  vSAN continues serving data and has more to rebuild. The event self-heals, and no DR is triggered. This is the concrete payoff of FTT=2 in a mirrorless design: it survives a failure *during* a rebuild, which is exactly the compounding scenario that most threatens a single-copy database.  
* **On FTT=1 / RAID-1 (small or non-critical clusters):** the first failure consumed the entire budget. A second overlapping failure means the affected segment data has no surviving copy, and it is lost. This is no longer an in-cluster recovery event; it is a **disaster-recovery event**, handled by the DR cluster in [Rack Design for Tanzu Greenplum Clusters](./rack-design.md#rack-design-for-tanzu-greenplum-clusters). The cluster does not self-heal out of this state.

There is a related nuance specific to the FTT=1 fallback. RAID-1 rebuilds faster than RAID-5, because it copies from an intact mirror rather than reconstructing from parity. The exposed window during which a second failure would mean data loss is therefore shorter with RAID-1 than with RAID-5. For a cluster that must run FTT=1, this shorter exposure is a genuine reason to prefer RAID-1 mirroring over RAID-5 erasure coding, on top of the host-count floor discussed in [Minimum Disk Layout and SPBM Guidelines](#minimum-disk-layout-and-spbm-guidelines).

**Whole-host failure**

A host failure is where the storage layer and the compute layer act together, and it is the storage-side companion to the recovery sequence in [Physical Host Failure and Recovery](./vsphere-cluster-design.md#physical-host-failure-and-recovery).

From the data-protection standpoint, losing a host is counted as a single failure, so both policies keep the data intact: FTT=1 survives it with its budget fully spent, and FTT=2 survives it with one unit of budget still in hand. The difference from a disk failure is scope. The Tanzu Greenplum VMs that were running on that host went down with it, so two independent recoveries now run at the same time. vSAN keeps the data available from surviving components and begins rebuilding the lost ones onto healthy capacity, exactly as in the disk case. In parallel, vSphere HA restarts the affected VMs on surviving hosts, and each restarted segment recovers as described in [Segment VM Restart Semantics](./vsphere-cluster-design.md#segment-vm-restart-semantics), replaying its WAL from the vSAN-backed storage that was never at risk.

The important architectural point is that these two recoveries are independent. The database does not wait on the vSAN rebuild to resume service; it needs its data *available*, which it is throughout, not its data *fully redundant*, which the rebuild restores in the background. The rebuild competes for I/O with the recovering workload, which is why the reserved rebuild capacity in [Platform-Level vSAN Configuration](#platform-level-vsan-configuration) exists. And the same second-failure logic from the previous scenario applies here too: on FTT=1, a second host failure during this rebuild is a DR event, and on FTT=2, it survives.

**Failure exceeding the budget in a single event**

The floor case is a simultaneous loss that exceeds the failure budget outright, two hosts at once on FTT=1, or three at once on FTT=2. Here the data is lost immediately, with no rebuild possible, and recovery is by definition a disaster-recovery event against the DR cluster in [Rack Design for Tanzu Greenplum Clusters](./rack-design.md#rack-design-for-tanzu-greenplum-clusters). This could be rare, and the N+2 with FTT=2 pairing from [vSphere HA Configuration Recommendations](./vsphere-cluster-design.md#vsphere-ha-configuration-recommendations) is specifically designed to make it require a rare coincidence on a production cluster, but the document states it plainly because it is the honest boundary of what the primary cluster can absorb.

**Summary: self-heal versus DR**

The table below is the decision reference for the whole section.

| Scenario | FTT=2 / RAID-6 (production) | FTT=1 / RAID-1 (small / non-critical) |
| :---- | :---- | :---- |
| Single disk failure | Self-heals, no DB impact | Self-heals, no DB impact |
| Second failure during rebuild | Survived, self-heals, no DR | Data loss -> DR  |
| Single host failure | Data safe, vSAN rebuilds while HA restarts VMs ([Physical Host Failure and Recovery](./vsphere-cluster-design.md#physical-host-failure-and-recovery)), self-heals | Data safe, same HA restart, self-heals, but now at zero remaining budget |
| Two concurrent host failures | Survived and self-heals | Data loss -> DR  |
| Failure exceeding budget in one event (3 hosts on FTT=2 / 2 hosts on FTT=1) | Data loss -> DR | Data loss -> DR |

Two observations to conclude the section. 

* First, the entire value of FTT=2 shows up in exactly one column of that table, the overlapping-failure rows, and those are the scenarios most dangerous to a mirrorless database, which is why production is FTT=2 and not FTT=1.   
* Second, every one of these events is invisible to Tanzu Greenplum monitoring by design, because vSAN handles data protection a layer below the database. A disk failure never appears in Tanzu Greenplum's own health view, and even a host failure surfaces there only as the segment restarts, not as the storage rebuild underneath it. That gap between what the database sees and what the storage layer is doing is precisely why the two-layer observability model is necessary; without the storage-layer view, an operator sees query latency during a rebuild with no visible cause.

**Note: On the vSAN object repair timer, FTT, and planned maintenance**

vSAN does not rebuild a missing component immediately. When a component becomes ***absent*** (a host rebooting, disconnected, or in maintenance) rather than ***degraded*** (a hard-failed device), vSAN waits for the object repair timer, 60 minutes by default, before rebuilding it elsewhere. This avoids wasteful rebuilds for absences that resolve on their own, at the cost of leaving the affected data at reduced redundancy for the length of the window. How much that matters depends almost entirely on the FTT policy:

* **On FTT=1**, an absent component means zero redundancy for that data for the whole window. Any second failure during it is data loss and a DR event. The timer is a real risk lever here.  
* **On FTT=2**, one unit of failure budget remains throughout the window, so a second failure is still survived. The timer only delays the return to full redundancy; it is an efficiency setting, not a risk one. This is a further reason FTT=2 is the calmer production choice.

**Planned maintenance (ESXi host or storage device):**

* **FTT=2 cluster:** default behavior is fine. Enter maintenance with "Ensure accessibility," keep the work within a reasonable window, and can leave the timer alone.  
* **FTT=1 cluster:** plan deliberately. For anything longer than a quick reboot, enter maintenance with **"Full data migration"** so the host's components are evacuated before it goes down and the cluster is never left at reduced redundancy. This needs spare capacity to hold the evacuated data. Where full migration is not possible (due to storage space constraints), treat the maintenance as a redundancy-reduced window, keep it short, work on only one fault domain at a time, and understand that a failure elsewhere during it is a DR scenario.  
* **Timer adjustment (FTT=1, long maintenance):** increasing the timer avoids a wasteful rebuild of a host you are about to return, but only do so after a full data migration, since otherwise it lengthens the exposed window. Decreasing it starts rebuilding sooner, shortening exposure at the cost of churn. Return it to default afterward. The cleaner answer is almost always to evacuate the host rather than sit exposed for longer.  
* **Storage-device maintenance:** same logic, finer grain. On FTT=1, service one device at a time and confirm vSAN is back to full compliance before the next, and on FTT=2 the same work retains a unit of budget and is lower-risk.

**In short:** on FTT=2 the repair timer is an efficiency setting, and on FTT=1 it is a risk setting, and any FTT=1 maintenance should either evacuate the fault domain first or be treated explicitly as a window in which a further failure means DR.

## vSAN ESA vs vSAN Storage Cluster - Decision Framework

Architectural Comparison

| Dimension | vSAN ESA | vSAN Storage Cluster |
| ----- | ----- | ----- |
| Architecture | Storage local to compute hosts. Storage and compute scale together. | Disaggregated storage, separate from compute |
| Latency | Lowest possible, local NVMe | Slightly higher, adds a network hop |
| Failure Domain | Host-level within the compute cluster | Storage pool level, decoupled from compute failures |
| Scaling | Linear: add a host to add both compute and storage | Independent: scale compute or storage separately |
| Best Fit | Latency-critical queries, temp-heavy workloads, small-to-medium clusters | Capacity-heavy analytics, independent scaling, multi-tenant scenarios |

For Tanzu Greenplum specifically:

* **ESA** co-locates segment CPU, memory, and storage, eliminating a network hop for every storage access. This is the stronger fit for latency-critical workloads and temp-heavy ETL, and it is the baseline this RA assumes.  
* **vSAN storage cluster** has segments that reach storage over a 25 to 100 Gbps fabric, enabling independent compute and storage scaling. It requires robust network design, and its extra hop puts a small amount of latency in the storage path, but it still delivers strong performance for most analytics workloads and is the right choice when independent scaling or a shared storage tier is a requirement.

The per-VMDK layout and storage policies in [Minimum Disk Layout and SPBM Guidelines](#minimum-disk-layout-and-spbm-guidelines), and the platform settings in [Platform-Level vSAN Configuration](#platform-level-vsan-configuration), apply to both architectures.
