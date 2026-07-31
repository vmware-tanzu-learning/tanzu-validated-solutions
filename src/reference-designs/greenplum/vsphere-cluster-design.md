# vSphere Cluster and Compute Design

This section defines the vSphere compute cluster design required to host Tanzu Greenplum for high-intensity analytical workloads. The objective is predictable performance, controlled failure behavior, and a clear operational boundary between what the infrastructure does and what the database team does. It deliberately avoids generic vSphere build guidance and focuses only on where Tanzu Greenplum requires something different from vSphere defaults.

The design is built around three objectives:

* **Predictable performance.** No scheduler surprises, no overcommit, and no memory reclaim that would undermine query runtimes.  
* **Controlled failure behavior.** Clear, well-understood outcomes when a host or VM fails, aligned with how Tanzu Greenplum itself behaves.  
* **Operational clarity.** A firm line between infrastructure responsibilities (restart, capacity, placement) and database responsibilities (cluster integrity, recovery).

Two assumptions carry through the section. The cluster is dedicated to Tanzu Greenplum, which is strongly recommended, and the workload is a low-to-medium concurrency mix that is predominantly analytical (OLAP). The high-availability topology itself is not restated as an assumption here; it is established in [When Mirroring Is Still the Right Choice](./resilience-topology.md#when-mirroring-is-still-the-right-choice), and this section builds on the mirrorless baseline defined there.

## vSphere Cluster Topology

### Dedicated Tenancy Requirement

Tanzu Greenplum should always run on a vSphere cluster dedicated to it. Co-locating Tanzu Greenplum with other workloads introduces CPU scheduling contention, memory pressure, NUMA imbalance, and unpredictable latency, all of which act directly on query execution. The relationship also runs the other way: because Tanzu Greenplum consumes CPU, memory, and network aggressively by design, it will disrupt any neighbor sharing the same hosts.

This requirement maps directly to the workload characteristics established earlier in [Tanzu Greenplum Workload Characteristics](./workload-characteristics.md#tanzu-greenplum-workload-characteristics):

* From the [Concurrency and Parallelism](./workload-characteristics.md#concurrency-and-parallelism), [CPU Usage Patterns](./workload-characteristics.md#cpu-usage-patterns), and [Memory Usage Patterns](./workload-characteristics.md#memory-usage-patterns) sections, segment hosts run at sustained high CPU and consume memory aggressively, so any competing workload induces CPU ready time and memory contention.  
* From the [Network Traffic Characteristics](./workload-characteristics.md#network-traffic-characteristics) section, the interconnect will use all the network throughput available to it and is intolerant of the packet loss and latency variance that a noisy neighbor introduces.

The **design position** is therefore **Tanzu Greenplum cluster = vSphere cluster.** The Tanzu Greenplum system runs in a dedicated cluster or workload domain with no non-Tanzu Greenplum workloads, and general-purpose or shared virtualization clusters are not an acceptable platform for it.

**Consequences of mixing workloads:**

* CPU scheduler "fairness" penalizes CPU-heavy Tanzu Greenplum VMs in favor of lighter workloads.  
* Memory pressure from other tenants can trigger ballooning or compressed memory unless fully disabled, causing spills and query collapse.  
* DRS will attempt to optimize placement across all workloads, undermining NUMA and cache affinity for segment hosts.

### Host Count and Configuration Model

Host counts are tunable per environment, but the following baselines apply:

* **Non-production or proof-of-concept:** 3 to 4 ESXi hosts, primarily for functional validation rather than performance representative of production.  
* **Recommended production baseline:** 6 to 8 ESXi hosts per Tanzu Greenplum cluster, which gives enough hosts to absorb an N-1 or N-2 failure while still maintaining performance.

The reason the production baseline is six hosts rather than four is not only about compute headroom, it is driven by what the storage layer can protect against, which matters more in a mirrorless design where vSAN is the sole copy of the data. The achievable vSAN failure tolerance is bounded by host count:

* A **4-host** cluster can achieve at most **FTT=1**. It survives a single failure, but a second failure before the rebuild completes means data loss and escalation to disaster recovery. This is acceptable for functional validation, which is why "four hosts" is positioned as a PoC or development floor rather than production.  
* A **5-host** cluster can reach **FTT=2, but only through RAID-1 mirroring** (three copies, ~3x capacity). RAID-6 is not yet available at this host count. Five hosts is therefore a viable production size for an environment that needs two-failure tolerance and accepts the mirroring capacity cost, but it is not the efficient path.  
* A **6-host** cluster is the first point at which **FTT=2 via RAID-6** becomes achievable, at 1.5x, and it is also the point at which FTT=1 RAID-5 improves to the 4+1 scheme at 1.25x. The step from single to double failure tolerance therefore costs only 20 percent more raw capacity here, which is what makes six hosts the efficient production baseline rather than merely a possible one.

Because a mirrorless production cluster should be able to survive a second failure inside a rebuild window (the reasoning is developed in [Minimum Disk Layout and SPBM Guidelines](./storage-architecture.md#minimum-disk-layout-and-spbm-guidelines)), and because FTT=2 through RAID-6 requires six hosts, six hosts is the true production baseline. Four hosts is a valid POC size precisely because POC and development workloads might not require FTT=2. This links the compute sizing here to the storage protection policy in [Minimum Disk Layout and SPBM Guidelines](./storage-architecture.md#minimum-disk-layout-and-spbm-guidelines) and the admission-control matching rule in [vSphere HA Configuration Recommendations](#vsphere-ha-configuration-recommendations).

**Note:** The number of Tanzu Greenplum segment hosts is not the same as the number of ESXi hosts. Because segment VMs are aligned to NUMA nodes ([CPU Architecture, NUMA Awareness, and vNUMA Configuration](#cpu-architecture-numa-awareness-and-vnuma-configuration)), a dual-socket ESXi host runs one segment VM per NUMA node. As a working rule, the segment-host count is roughly the ESXi host count multiplied by the NUMA nodes per host, reduced by the capacity set aside for the coordinators and for failover headroom. This relationship should be applied consistently wherever host and segment counts appear, including the rack designs in [Rack Design for Tanzu Greenplum Clusters](./rack-design.md#rack-design-for-tanzu-greenplum-clusters).

Every ESXi host in the cluster should be identical, because Tanzu Greenplum's slowest-segment behavior turns any hardware asymmetry into systematic skew. Hosts should match on:

* CPU model, stepping, and core count  
* NUMA topology, meaning sockets and cores per socket  
* Memory capacity per host  
* Network bandwidth and NIC layout  
* Storage throughput and availability

Beyond the skew it causes, heterogeneity also complicates NUMA-aware sizing and raises the risk of accidental configurations where a segment VM's vCPU count no longer fits inside a single NUMA node.

## CPU Architecture, NUMA Awareness, and vNUMA Configuration

Tanzu Greenplum execution benefits directly from NUMA-aware placement, because segment processes and their shared memory need to sit close to the cores running them. On a virtual platform, NUMA alignment is not a tuning nicety; it is a primary design input.

### NUMA Design Principles

The principles are:

* **Each segment VM fits entirely within a single physical NUMA node.** Size the VM's vCPUs and memory so it can be scheduled inside one node, which avoids remote memory access and reduces latency during parallel execution.  
* **Multiple segment VMs may share a NUMA node** if capacity allows. A single node can host several small or medium segment VMs as long as their combined vCPU and memory allocation stays within the node's physical resources and each VM remains NUMA-local.  
* **No segment VM should have more vCPUs than there are physical cores in one NUMA node.** Crossing that line forces the VM to span nodes and reintroduces remote-memory latency.  
* **The Coordinator and Standby Coordinator VMs are also sized to stay NUMA-local.**

Mapping back to [Tanzu Greenplum Workload Characteristics](./workload-characteristics.md#tanzu-greenplum-workload-characteristics): from the [Concurrency and Parallelism](./workload-characteristics.md#concurrency-and-parallelism), [CPU Usage Patterns](./workload-characteristics.md#cpu-usage-patterns), and [Memory Usage Patterns](./workload-characteristics.md#memory-usage-patterns) sections, high concurrency and heavy memory use are the normal state, so cross-NUMA memory access shows up as consistent extra latency, visible as query elongation and skew rather than as a clean failure. From the [Why Generic Virtualization Defaults Fail](./workload-characteristics.md#why-generic-virtualization-defaults-fail) section, generic overcommit and NUMA-agnostic placement are not acceptable defaults here.

### vNUMA Configuration

The requirement is that vNUMA remains enabled for segment VMs so the guest sees a NUMA topology that matches the physical one. vSphere exposes vNUMA automatically to larger VMs (by default, those with more than 8 vCPUs), and this behavior should be left in place for any multi-vCPU segment VM that approaches NUMA-node size. Exact default thresholds vary by vSphere version, so the specific setting should be confirmed against the deployed version rather than assumed.

The sizing rules that make vNUMA meaningful are:

* vCPUs per segment VM no greater than the physical cores in one NUMA node  
* vRAM per segment VM no greater than the memory attached to a single NUMA node

NUMA misconfiguration is one of the most common causes of otherwise unexplained Tanzu Greenplum slowness on virtual platforms, which is why this architecture treats NUMA alignment as mandatory rather than best-effort.

**Architectural Note: Sub-NUMA Clustering (SNC / NPS)** On modern multi-core processors, a physical CPU socket is split into multiple hardware NUMA nodes. When sizing Segment Host VMs, ensure the VM fits within the **individual NUMA node boundary**, not just the physical CPU socket.

## Memory Management and Scheduling

Tanzu Greenplum uses memory as a primary performance tool and is highly sensitive to any form of reclaim. The design goal for this layer is that a Tanzu Greenplum VM's memory is always physically present and never taken back by the hypervisor while queries are running.

### Memory Reservation

**Requirements:**

* 100% memory reservation for:  
  * Primary Coordinator VM.  
  * Standby Coordinator VM.  
  * All segment VMs.  
* Disable or avoid:  
  * Ballooning (no balloon driver effect on Tanzu Greenplum VMs).  
  * Transparent page sharing / memory compression for these VMs.  
  * Host swapping under all normal operating conditions.

This maps to [Memory Usage Patterns](./workload-characteristics.md#memory-usage-patterns) and [Storage Access Patterns](./workload-characteristics.md#storage-access-patterns), once memory is constrained or reclaimed, queries spill to disk, and those spills add storage and network I/O that degrades performance across the whole cluster rather than on one VM. From [Why Generic Virtualization Defaults Fail](./workload-characteristics.md#why-generic-virtualization-defaults-fail), memory overcommit and reclaim conflict directly with Tanzu Greenplum's execution model.

### Overcommit Policy

CPU overcommit is strongly discouraged on both segment hosts and coordinators. If used, it must be minimal (near 1:1 vCPU:pCPU only) and validated through workload testing, rather than assumed safe.   
Memory overcommit is strictly prohibited for any Tanzu Greenplum VM.

Taken together with the reservations above, this is the concrete infrastructure enforcement of the principle from [Tanzu Greenplum Workload Characteristics](./workload-characteristics.md#tanzu-greenplum-workload-characteristics) that Tanzu Greenplum assumes predictable CPU and memory availability throughout query execution.

## vSphere High Availability (HA)

This subsection clarifies what vSphere HA does and does not do for a Tanzu Greenplum cluster, mapping back to the failure sensitivity described in [Failure Sensitivity](./workload-characteristics.md#failure-sensitivity). It also draws the responsibility boundary that the rest of the section depends on.

### Scope and Intent of vSphere HA

vSphere HA is an infrastructure-level restart mechanism. It detects a host failure, or specific VM failures where configured, and restarts the affected VMs on surviving hosts.

It is equally important to be clear about what it does not do:

* It does not understand Tanzu Greenplum roles, so it does not distinguish a coordinator VM from a segment VM.  
* It does not preserve query state or guarantee transactional continuity.  
* It does not perform database failover or segment recovery.  
* It does not check Tanzu Greenplum cluster consistency before or after a restart.

The conclusion is that vSphere HA is not a database HA mechanism. It reduces the time to restart a failed VM, and nothing more. Database-level recovery is handled by Tanzu Greenplum's own mechanisms, including the Fault Tolerance Server and, for mirrorless clusters, the high availability service introduced in [The Tanzu Greenplum High Availability Service for Mirrorless Clusters](./resilience-topology.md#the-tanzu-greenplum-high-availability-service-for-mirrorless-clusters). This split is the responsibility boundary at the center of this section: the infrastructure restores VMs and capacity, and the database team owns cluster integrity and recovery.

### Coordinator and Standby Semantics

Tanzu Greenplum runs one active Primary Coordinator and one Standby Coordinator kept current by WAL streaming. Promotion of the standby is explicit, not automatic. This aligns with [Failure Sensitivity](./workload-characteristics.md#failure-sensitivity): a coordinator failure is visible to users as dropped connections and aborted queries, and recovery is a deliberate action rather than a transparent one.

#### Primary Coordinator VM Restart

The scenario is that the Primary Coordinator VM crashes, or its ESXi host fails, and vSphere HA restarts the VM on another host.

**vSphere behavior:**

* On the infrastructure side, vSphere HA detects the failure and restarts the Coordinator VM on a surviving host, subject to HA policy and available capacity.

**Tanzu Greenplum behavior:**

* All client connections drop and all running queries abort at the moment of failure.  
* After the operating system boots:   
  * The postmaster process starts automatically.   
  * All required Tanzu Greenplum Coordinator services are brought up.   
  * The Coordinator reconnects to segment instances.   
  * The Fault Tolerance Service (FTS) continues normal probing of segments.

**Cluster State** 

* No catalog inconsistency is introduced.   
* No Coordinator role change occurs.   
* Once the Coordinator is fully initialized:   
  * The cluster returns to a normal operational state   
  * Applications can reconnect and resume operations

**Operational requirement**

* No manual DBA intervention is required in the normal case. If coordinator services are not configured to start automatically on boot, the operator runs `gpstart` to bring the cluster back up.  
* DBAs may optionally:   
  * Verify cluster health (for example, Coordinator availability, FTS status).   
  * Confirm application connectivity.   
  * Standby promotion is not required unless the Primary Coordinator fails to restart or is deemed permanently unavailable.

#### Primary Coordinator Permanent Failure

The scenario here is that the Primary Coordinator VM is lost, corrupted, or intentionally not brought back.

System Behavior

* All client connections to the Primary Coordinator fail immediately.   
* The Standby Coordinator continues running independently.   
* No automatic promotion occurs.   
* Tanzu Greenplum intentionally avoids implicit Coordinator role changes to protect catalog consistency.

Required Administrative Action

* Recovery is a controlled role transition, initiated with `gpactivatestandby`.   
* This promotes the Standby Coordinator to become the new Primary Coordinator.   
* Application connection endpoints (DNS, virtual IP, or load balancer) must be updated to point to the new Primary Coordinator.

Operational Safeguards 

* After promotion, the original Primary Coordinator VM must remain powered off.   
* Restarting the old Primary Coordinator without reinitialization can result in:   
  * Split-brain at the Coordinator level   
  * Catalog divergence   
  * Irreversible metadata corruption

## Segment VM Restart Semantics

Two segment failure classes matter here: 

* The loss of a segment process while its VM stays up, and   
* The loss of the segment VM or its host. 

The heavier host and disk failure classes are addressed later, host failure with the HA-DRS interaction in [Physical Host Failure and Recovery](#physical-host-failure-and-recovery), and disk failure with the storage design in [Storage Failure Behavior: Physical Disk Failure](./storage-architecture.md#storage-failure-behavior-physical-disk-failure).

**Segment process failure.** When a single segment's process fails, for example on an out-of-memory kill or a backend crash, but the VM itself stays healthy, recovery is local and no vSphere action is involved. 

The mirrorless high availability service "`greenplum-postmaster`" on that VM restarts the segment, and on restart the segment replays its write-ahead log from vSAN-backed storage to reach its last committed state. FTS probes during the outage, so the segment is briefly marked down and any in-flight query touching it aborts; the next successful probe marks it up and it rejoins the cluster. 

Operationally this class is close to self-healing: an alert fires, and the database team's job is to verify state and find the root cause, such as memory pressure, rather than to run a recovery procedure.

**Segment VM or host failure.** The scenario is a segment VM restarted by vSphere HA after its ESXi host fails. 

**vSphere Behavior:**

* The Segment VM is restarted on an available ESXi host.   
* The operating system boots and is considered healthy at the infrastructure layer.

**Tanzu Greenplum Behavior:**

* When the segment became unavailable:   
  * The Fault Tolerance Service (FTS) marks the segment as DOWN (Post Probe Interval)   
  * New queries referencing that segment fail or stall based on workload and retry logic  
* While the VM is restarting:   
  * The segment remains unavailable to the cluster   
  * New queries referencing that segment fail or stall based on workload and retry logic

**Post-Restart Recovery Flow:** 

* After the VM boots:   
  * The postmaster process on the segment VM starts automatically   
  * Postmaster brings up all required segment services locally   
  * FTS continues probing the segment at the configured interval   
  * Once FTS receives successful heartbeats and verifies service readiness:   
    * The segment is marked UP   
    * The segment automatically rejoins the cluster

Postmaster Role:

* Starts and supervises all segment processes within the VM   
* Restarts backend processes as needed   
* It does not:   
  * Control VM restarts   
  * Perform cluster-level recovery decisions   
* Cluster membership is governed by FTS, not postmaster alone

## Impact on Query Execution

For any coordinator or segment failure:

* All in-flight queries referencing the failed process/segment are aborted.  
* Tanzu Greenplum does not retry queries automatically.  
* Query restart is driven by:  
  * Application retry logic, or  
  * Explicit user / scheduler re-execution.

Reason:

* Avoid duplicate writes, partial transactions, and inconsistent analytical results in complex query graphs.

The rule across every coordinator and segment failure above is consistent and worth stating on its own, because it shapes how applications must be built around the cluster:

* Any in-flight query referencing the failed process or segment is aborted.  
* Tanzu Greenplum does not retry queries automatically.  
* Query restart is driven either by application retry logic or by explicit user or scheduler re-execution.

This is a deliberate design choice, not a limitation. Automatically retrying a failed query in a complex distributed plan risks duplicate writes, partial transactions, and inconsistent analytical results. Leaving re-execution to the application or operator keeps those outcomes correct. The practical implication for the platform is that recovery mechanisms should be tuned and scheduled so they do not repeatedly interrupt long-running, motion-heavy queries, which is picked up in the HA and DRS configuration in the following sections.

## vSphere HA Configuration Recommendations

| Area  | Recommended setting for Tanzu Greenplum on vSphere 9 | Rationale |
| ----- | ----- | ----- |
| HA   | Enabled  | Required to restart failed coordinator/segment VMs after host loss. |
| Admission control  | "Host failures the cluster tolerates" or dedicated failover hosts | Enforces real capacity reserve for Tanzu Greenplum VM restart. |
| Failures cluster tolerates | Small clusters (4 to 5 hosts): 1. Production clusters (6+ hosts): 2 | Implements N+1 / N+2. This must be matched to the vSAN FTT policy ([Minimum Disk Layout and SPBM Guidelines](./storage-architecture.md#minimum-disk-layout-and-spbm-guidelines)): N+1 pairs with FTT=1, N+2 pairs with FTT=2. Setting N+2 on FTT=1 storage is inconsistent in a mirrorless design. |
| Dedicated failover hosts  | Optional, recommended for most critical clusters  | Reserves whole hosts for HA restart rather than relying on spare capacity spread across busy hosts. |
| VM restart priority  | Coordinator and Standby: High.  Segment VMs: Medium.  Utility VMs: Low  | Ensures the coordinators come up first, then segments, then everything else. |
| VM / Application monitoring  | Disabled for Tanzu Greenplum VMs  | Avoids infrastructure-driven restarts on transient database conditions. Tanzu Greenplum services are managed by the database team. |
| Host isolation response  | Leave VMs powered on (default recommendation).  Power off and restart as an option in validated environments | See below Notes. |
| Datastore heartbeating  | Use vSAN defaults; no additional heartbeat datastores | vSAN ESA/vSAN Storage Cluster is the main datastore considered in this RA; HA uses vSAN + mgmt network; no extra VMFS/NFS is required. Configure one or more *das.isolationaddress* values, so that transient vCenter/management issues do not trigger isolation when the host still has data-plane connectivity.  |

Two areas regarding HA configuration and Host Isolation Response need more than a one-line setting, so they are expanded below.

**Admission control, reserved capacity, and matching to FTT**

The capacity reserved for HA is not a spare pool that Tanzu Greenplum can borrow against; it must be genuine, unused headroom, because Tanzu Greenplum runs with zero CPU and memory overcommit. The reservation math from [Memory Management and Scheduling](#memory-management-and-scheduling) is what makes this work, because every Tanzu Greenplum VM has a full memory reservation, HA can only restart a failed host's VMs if that much capacity genuinely exists elsewhere.

* For 4-5 host clusters, configure   
  * "Host failures cluster tolerates = 1" or define 1 dedicated failover host.   
  * Capacity planning must assume N+1 with zero CPU/memory overcommit for Tanzu Greenplum VMs.  
* For 6+ host clusters, configure   
  * "Host failures cluster tolerates = 2" or 2 dedicated failover hosts, achieving N+2 redundancy.  
  * Capacity planning must assume N-2 with zero CPU/memory overcommit for Tanzu Greenplum VMs.

**Note:** 

**Admission control must be set in step with the vSAN FTT policy**, as these two protect different layers and a mismatch is governed by the weaker one. Admission control reserves compute capacity so VMs can restart; FTT reserves storage redundancy so the data survives.   
In a mirrorless design, N+2 compute reservation is only meaningful if the storage is also FTT=2. Otherwise the second host failure loses the data before the reserved compute can be used, and the reserved compute is wasted.   
Since FTT=2 through RAID-6 requires six hosts, N+2 admission control is a property of the six-plus-host production baseline, and the 4 to 5 host clusters run N+1 with FTT=1. The full rationale for pairing the compute and storage layers is in [Minimum Disk Layout and SPBM Guidelines](./storage-architecture.md#minimum-disk-layout-and-spbm-guidelines).

**vSAN Storage Cluster and datastore heartbeat:**

* For vSAN ESA/vSAN Storage Cluster clusters, you do not configure separate heartbeat datastores. HA uses vSAN itself plus the management network, no extra VMFS/NFS datastores are added purely for heartbeating.  
* If the default gateway is not a reliable isolation check, configure one or more *das.isolationaddress* addresses.

**Host Isolation Response**

* Configure one or more *das.isolationaddress* values, so that transient vCenter/management Network issues do not trigger isolation when the host still has data-plane connectivity.  
* In environments where HA isolation detection has been validated, host isolation response may be set to "Power off and restart VMs" to accelerate recovery.   
  Tanzu Greenplum FTS will still mark segments down and DBAs must perform segment recovery before resuming full workload.  
* For the most conservative deployments, "Leave VMs powered on" can be used to avoid hypervisor initiated power-off decisions under ambiguous failure conditions, accepting longer time to clear a bad host.

## vSphere DRS - Tanzu Greenplum-Specific Configuration

DRS is valuable to Tanzu Greenplum for one thing above all: getting initial placement right. It becomes a liability if it is allowed to migrate running segment VMs for the sake of cluster balance, because every such migration disturbs NUMA locality and briefly steals CPU, network, and buffer capacity from a workload that has none to spare. The configuration below keeps the useful half and suppresses the harmful half.

| Area  | Recommended setting for Tanzu Greenplum on vSphere 9 | Rationale |
| ----- | ----- | ----- |
| DRS enabled  | Enabled, cluster-wide  | Required for initial placement and controlled balancing.  |
| Automation level | Manual or Partially Automated | Accept DRS recommendations for initial placement. Avoid automatic runtime migrations.  |
| Migration threshold | Low / Conservative | Minimize vMotion events. Preserve NUMA locality.  |
| VM-level DRS overrides  | Override GP VMs to Manual/Partially Automated  | Isolates the Tanzu Greenplum VMs from any more aggressive cluster-wide DRS policy. |

This maps back to the workload characteristics directly. From the [Concurrency and Parallelism](./workload-characteristics.md#concurrency-and-parallelism) and [Network Traffic Characteristics](./workload-characteristics.md#network-traffic-characteristics) sections, a runtime vMotion breaks the NUMA locality that segment performance depends on and temporarily consumes the CPU and network headroom that motion-heavy queries need. From the [Why Generic Virtualization Defaults Fail](./workload-characteristics.md#why-generic-virtualization-defaults-fail) section, the generic "optimize for balance" behavior that suits mixed workloads is exactly what should not be applied to a Tanzu Greenplum cluster.

## Physical Host Failure and Recovery

The moment that most tests a Tanzu Greenplum cluster's design is a physical ESXi host failure, because it is where HA, DRS, vSAN, and Tanzu Greenplum recovery all act at once. Understanding that interaction is what keeps the recovery orderly rather than turning it into churn.

When a physical host fails, several Tanzu Greenplum VMs are lost together. vSphere HA restarts them on the surviving hosts using the N-1 or N-2 capacity reserved for exactly this, and it honors the restart priority from [vSphere HA Configuration Recommendations](#vsphere-ha-configuration-recommendations), so the coordinators come back before the segments. 

The storage layer does the decisive work underneath, because 

* vSAN holds redundant components of every affected VM's storage on other hosts.  
* Each restarted VM is served with its complete, current data despite the loss of the failed host. 

Each restarted segment VM then recovers exactly as described in [Segment VM Restart Semantics](#segment-vm-restart-semantics), replaying its WAL from vSAN-backed storage and rejoining once FTS marks it up. The difference at host scale is orchestration rather than mechanism. Many VMs recover at once, the coordinators are restarted ahead of the segments by HA priority, and query interruption follows the [vSphere High Availability (HA)](#vsphere-high-availability-ha) through [Impact on Query Execution](#impact-on-query-execution) sections.

In the background, vSAN rebuilds the components that were lost with the host onto healthy capacity, to restore full policy compliance. This rebuild competes for I/O with the recovering workload, which is one of the reasons the storage design keeps capacity headroom in reserve. That behavior belongs to the storage layer and is covered in [Storage Architecture - vSAN & vSAN Storage Cluster](./storage-architecture.md#storage-architecture-vsan-vsan-storage-cluster).

The interaction to manage deliberately is between HA and DRS during this window:

* HA actions take precedence. Restarting the failed VMs is the priority, not rebalancing the cluster.  
* DRS must not aggressively rebalance while the cluster is still degraded and the database team is running recovery. HA has just placed VMs where capacity allowed; DRS immediately churning them for the sake of balance would compound the disruption.  
* The operational stance during recovery is therefore to relax or temporarily suspend DRS migrations, and to prioritize stability, meaning correct placement and sufficient capacity, over perfect balance.

Once the failed host is repaired and returns, rebalancing can resume under the conservative DRS policy from [vSphere DRS - Tanzu Greenplum-Specific Configuration](#vsphere-drs-tanzu-greenplum-specific-configuration), at a time that does not collide with active query windows.

## VM Placement and Anti-Affinity Rules

Placement is what preserves Tanzu Greenplum's failure domains on the virtual platform. Left to default balancing, vSphere has no reason to keep the components that matter apart, so the separation has to be expressed explicitly through affinity rules.

The placement goals are:

* Keep the Primary and Standby Coordinator on different ESXi hosts, so that no single host failure can take both. This is a hard anti-affinity requirement.  
* Distribute segment VMs evenly across hosts, and across racks where the topology spans more than one, to avoid concentrating too much of the cluster's data on any single failure domain.  
* Where a deployment does use mirrored segments, apply anti-affinity between the primary and mirror of the same content so they never share a host. In the mirrorless baseline of this architecture there are no mirror pairs to separate, but the even-distribution rule still applies so that a single host failure removes only a small, evenly-sized slice of the segments.

These rules also interact with the capacity reservations from [vSphere HA Configuration Recommendations](#vsphere-ha-configuration-recommendations): anti-affinity constraints where HA can restart a VM, so the reserved failover capacity has to exist on hosts that satisfy the rules. The rack-level and availability-zone dimension of placement is developed further in [Rack Design for Tanzu Greenplum Clusters](./rack-design.md#rack-design-for-tanzu-greenplum-clusters).

## Section Summary

The through-line of this section is a clean division of roles. The vSphere cluster, HA, and DRS provide infrastructure resilience and fast VM restarts, but they do not provide database continuity, and the design never asks them to.

Tanzu Greenplum availability and data consistency rest instead on:

* Correct sizing with strict CPU and memory reservations, so the cluster behaves predictably and HA always has real capacity to restart into.  
* Conservative HA and DRS policies that respect NUMA locality and never overcommit, so recovery does not create fresh contention.  
* Explicit, database-team-led recovery after a failure, so cluster integrity and query correctness are owned by the layer that understands them.

Held together, these give the outcome the section set out to achieve: predictable performance in normal operation, controlled and well-understood behavior during a failure, and an operational boundary that leaves no ambiguity about who does what. The storage layer that underpins the durability this all depends on is the subject of [Storage Architecture - vSAN & vSAN Storage Cluster](./storage-architecture.md#storage-architecture-vsan-vsan-storage-cluster), and the network design that carries the interconnect is [Virtual Distributed Switch (vDS) Design](./vds-design.md#virtual-distributed-switch-vds-design).
