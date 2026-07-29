# Scalability and Capacity Planning

## Overview

This section covers sizing a Greenplum cluster at the outset and growing it once the workload outgrows that sizing. One constraint from [CPU Architecture, NUMA Awareness, and vNUMA Configuration](./vsphere-cluster-design.md#cpu-architecture-numa-awareness-and-vnuma-configuration) shapes everything: segment and coordinator VMs are sized so that each VM fits within a single NUMA node. This is a ceiling on the size of an individual VM, not a limit of one VM per node. A NUMA node can hold as many VMs as fit within its cores and memory. What it must never hold is a single VM larger than the node, because that VM would straddle two nodes and pay cross-node memory latency.

That ceiling determines what vertical scaling can mean, makes horizontal scaling the primary growth path, and ties every sizing decision back to the ESXi host geometry underneath. All scaling decisions must also preserve the invariants established earlier: zero CPU and memory overcommit ([Memory Management and Scheduling](./vsphere-cluster-design.md#memory-management-and-scheduling)), admission control matched to the vSAN failure tolerance (the [vSphere HA Configuration Recommendations](./vsphere-cluster-design.md#vsphere-ha-configuration-recommendations) and [Minimum Disk Layout and SPBM Guidelines](./storage-architecture.md#minimum-disk-layout-and-spbm-guidelines) sections), NUMA fit, and vSAN rebuild slack ([Platform-Level vSAN Configuration](./storage-architecture.md#platform-level-vsan-configuration)).

## Compute Sizing: CPU and Memory

### Key Terminology

The following terms recur throughout sizing and scalability discussions and are used consistently in this document.

| Term | Meaning | Relevance to sizing |
| :---- | :---- | :---- |
| Segment | One database process holding a slice of the data and performing part of the work of every query | The unit that resources are allocated to |
| Segment host | The virtual machine that runs several segments | The unit that is placed on an ESXi host |
| Concurrency | How many queries run at the same time | Each running query holds memory on every segment, so concurrency multiplies memory demand |
| Table scan | Reading through a table to find matching rows | Sequential read work, consumes storage bandwidth and CPU |
| Index | A lookup structure allowing the database to jump to specific rows rather than reading everything | Analytical queries usually do not use indexes, so they read far more data than transactional queries |
| Join | Combining rows from two or more tables that relate to each other, such as orders matched to customers | Memory-intensive, and often requires moving data between segments |
| Hash join | The common method Greenplum uses to join, building an in-memory lookup structure from one side and probing it with the other | The largest single consumer of query memory |
| Aggregation | Summarizing many rows into fewer, such as totals, averages, or counts grouped by category | Memory-intensive, and requires gathering partial results from all segments |
| Sort | Ordering rows | Memory-intensive, spills to disk when memory runs short |
| Spill | An operation running out of memory and writing intermediate results to disk in order to continue | The primary symptom of undersizing, and it degrades the whole cluster rather than only the query that spilled |
| Heavy analytical query | A query scanning large volumes without indexes, then joining and aggregating the results | The workload class this architecture is sized for |
| Functional unit | The set of resources required by one Greenplum segment | The building block for all compute sizing |

An analytical workload therefore behaves very differently from a transactional one. A transactional query uses an index to touch a handful of rows and completes in milliseconds.   
A heavy analytical query reads large portions of one or more tables, joins them, aggregates the result, and runs for seconds or minutes while holding significant memory on every segment in the cluster. Sizing is driven almost entirely by the second kind.

### The Functional Unit

Greenplum on vSphere is sized using a functional unit, the set of resources one segment requires. Resources required per primary segment, at five concurrent users:

| Resource | Quantity | Ratio to vCPU |
| :---- | :---- | :---- |
| vCPU | 8 |  |
| Memory | 32 GB | 4 GB per vCPU |
| Usable storage | 1024 GiB | 128 GB per vCPU |
| Network, interconnect only | 4 Gbps | 0.5 Gbps per vCPU |
| Storage read | 300 MB/s | 38 MB/s per vCPU |
| Storage write | 300 MB/s | 38 MB/s per vCPU |

Resources required for the coordinator, at five concurrent users:

| Resource | Quantity |
| :---- | :---- |
| vCPU | 16 |
| Memory | 256 GB |
| Usable storage | 1024 GiB |
| Network, interconnect only | 4 Gbps |
| Storage read and write | 300 MB/s each |

The baseline ratio is **4 GB of memory per vCPU**. This is the starting point for an analytical workload at moderate concurrency, and the figure to use when the workload is not yet well characterized. The following sections cover when and how far to raise it.

Two notes on application. The storage figure is a minimum per segment and may be increased. The network and storage throughput ratios should be held rather than reduced, because they are what prevent motion operations and scans from becoming the bottleneck.

### Sizing the Segment Host VM

A segment host VM is sized as a multiple of the functional unit (the set of resources required by one Greenplum segment/Database Process), multiplied by the number of segments the VM will run. The recommended range is two to four segments per VM.

| Segments per VM | vCPU | Memory at baseline ratio | Characteristics |
| :---- | :---- | :---- | :---- |
| 2 | 16 | 64 GB | Smaller unit, more VMs, finer placement granularity, better failover packing |
| 3 | 24 | 96 GB | Common baseline |
| 4 | 32 | 128 GB | Larger unit, fewer VMs |

The VM must then satisfy two checks:

* **NUMA fit.** The VM must fit within a single NUMA node, per [CPU Architecture, NUMA Awareness, and vNUMA Configuration](./vsphere-cluster-design.md#cpu-architecture-numa-awareness-and-vnuma-configuration). Several such VMs may share a node.  
  **Key NUMA Note: Sub-NUMA Clustering (SNC / NPS)** On modern multi-core processors, a physical CPU socket is split into multiple hardware NUMA nodes. When sizing Segment Host VMs, ensure the VM fits within the **individual NUMA node boundary**, not just the physical CPU socket.  
* **Even distribution across nodes.** The VM count per physical host must divide evenly across that host's NUMA nodes. On a two-socket host the segment VM count per host should therefore be even. Because query time is set by the slowest segment ([Greenplum Architecture Overview](./workload-characteristics.md#greenplum-architecture-overview)), uneven distribution translates directly into uneven query performance, so this architecture treats even distribution as a requirement rather than a preference.

A third check, on failover capacity, is covered in "[Capacity Planning Method](#capacity-planning-method)".

### Hyperthreading

Hyperthreading presents each physical core to the operating system as two logical processors, which share that core's execution resources and cache. Whether to use it is not a single decision but two: whether to enable it, and how much of it to budget as usable capacity.

**Why it can help.** Greenplum runs many parallel processes that stall frequently waiting on memory. Hyperthreading fills those stall cycles with the sibling thread's work, which is the case where it pays off. It also does not disturb NUMA alignment, because hyperthread siblings sit on the same physical core and therefore within the same NUMA node.

**Why it can hurt a resource intensive cluster.** Three mechanisms matter, and they compound under the sustained saturation described in [CPU Usage Patterns](./workload-characteristics.md#cpu-usage-patterns).

* **Shared execution resources.** Two threads on one core contend for the same execution units. Instead of doubling throughput, work queues behind other work, and the effect is most pronounced when both threads are busy continuously, which is the normal state for Greenplum during a query window.  
* **Cache contention.** A physical core has a fixed amount of fast cache. Two demanding threads evict each other's data from it, so the processor spends more time fetching from slower main memory. This is significant for Greenplum because hash join build and probe operations depend on their working structures staying resident in cache.  
* **Memory bandwidth.** Large sequential scans are usually limited by memory bandwidth rather than by core count. Hyperthreading does not add bandwidth, so on a bandwidth-bound scan the sibling thread adds contention without adding throughput.

The net effect on a saturated cluster is not usually a loss of raw throughput but an increase in runtime variance, and variance is what damages a synchronized MPP query, because every stage waits for its slowest participant.

**Recommendation by deployment type:**

| Deployment | Hyperthreading | vCPU budgeted per physical core | Rationale |
| :---- | :---- | :---- | :---- |
| Dedicated cluster, high intensity or unpredictable concurrency | Disabled at host | 1 : 1, logical equals physical | Every VM is Greenplum, so there is no other workload to benefit. Disabling removes variance and makes the capacity arithmetic unambiguous. |
| Dedicated cluster, moderate and predictable concurrency | Enabled | Up to 2 : 1, the functional unit baseline | Density and cost efficiency where the load is well understood and some variance is acceptable |
| Shared cluster (See [Capacity Planning Method](#capacity-planning-method) for more info) | Enabled at host, hyperthread core sharing restricted for the Greenplum VMs | 1 : 1 for the Greenplum VMs | Other tenants keep the benefit while the Greenplum VMs get exclusive physical cores |
| Development, test, proof of concept | Enabled | 2 : 1 or higher | Functional validation rather than performance representation |

The default for this architecture is the first row: hyperthreading disabled on a dedicated high-intensity cluster. Beyond the performance reasoning, this removes an operational ambiguity. With hyperthreading disabled, the core count seen in vCenter is the core count available, and there is no later temptation to treat logical processors as spare capacity.

### Adjusting for Concurrency and Query Load

Concurrency is the dimension that moves the requirement most, because every simultaneously running query holds memory on every segment.

Query load grows along three independent dimensions, and each calls for a different response.

| Dimension | Meaning | Primary resource consumed |
| :---- | :---- | :---- |
| Concurrency | How many queries run at the same time | Memory per host, divided across active queries |
| Query complexity | How much memory a single query needs for joins, sorts, and aggregation | Memory per query, on every segment |
| Query mix | The blend of short lookups, long analytical scans, and ETL | Both, plus interconnect during data movement |

**Concurrency and parallelism scale in opposite directions.** [Concurrency and Parallelism](./workload-characteristics.md#concurrency-and-parallelism) separated these: parallelism comes from segment count, concurrency comes from resources per segment. The consequence for sizing is easy to get backwards. Adding segments makes an individual query faster, but every query spawns worker processes on every segment it touches, so a higher segment count per host means each concurrent query consumes more memory and more processes on that host. Scaling out for speed can therefore reduce the number of queries that fit at once. Segment count should be chosen for the parallelism the workload needs, and concurrency capacity should be bought with memory rather than with additional segments.

**The practical ceiling is the spill threshold.** The limit on query load is not CPU utilization but the point at which concurrent queries exhaust memory and begin spilling. From the [Memory Usage Patterns](./workload-characteristics.md#memory-usage-patterns) and [Storage Access Patterns](./workload-characteristics.md#storage-access-patterns) sections, spilling does not degrade gracefully: it adds random I/O, lengthens queries, and compounds across the cluster. The sizing target is that the intended concurrency, at the intended query complexity, completes without routine spilling.

[Bare-metal sizing guidance](https://www.linkedin.com/pulse/vmware-tanzu-greenplum-2025-sizing-guide-ai-driven-prompting-novick-gzadc) expresses the concurrency relationship as cores and memory required per host against the number of concurrent heavy analytical queries at peak:

| Concurrent heavy queries at peak | Physical cores per host | Memory per host |
| :---- | :---- | :---- |
| 1 | 16 | 256 GB |
| 10 | 28 | 512 GB |
| 20 | 32 | 640 GB |
| 40 | 51 | 768 GB |
| 80 | 128 | 1024 GB |
| 120 | 224 | 1536 GB |
| 200 or more | 360 | 1536 GB |

Three qualifications apply. The table assumes Greenplum resource groups are managing concurrency, and beyond roughly 200 concurrent queries further queries are queued rather than admitted. The core counts are physical cores. And for a two-socket server the total is divided by two to give cores per socket, which on this platform is the same arithmetic as sizing a VM to fit one NUMA node.

Read alongside the functional unit, the pattern is that memory per vCPU rises above the 4 GB baseline as concurrency increases, then flattens at very high concurrency where the constraint shifts from memory to CPU. The practical guidance is therefore:

* Use **4 GB per vCPU** as the baseline for moderate analytical concurrency.  
* **Raise memory per vCPU** where the workload runs many concurrent heavy queries, or where individual queries are unusually memory-intensive, such as large hash joins across wide tables. Values in the range of 8 to 16 GB per vCPU are reasonable for high-concurrency analytical clusters.  
* **Do not reduce below the baseline.** Undersized memory does not simply slow queries, it causes spilling, and spilling degrades the entire cluster rather than the individual query.

### Resource Groups in Greenplum

Resource groups are Greenplum's in-database workload management feature. They divide the database's CPU and memory among named groups, assign users or roles to those groups, and cap how many queries each group may run at once. They are implemented on operating system control groups.

A resource group controls four things:

| Control | Function |
| :---- | :---- |
| Concurrency limit | The maximum number of queries the group may run simultaneously. Queries beyond the limit queue rather than start. |
| CPU allocation | The share of CPU the group receives, or a pinned set of cores |
| Memory allocation | The share of memory available to the group, and therefore to each query within it |
| Role assignment | Which database users or applications belong to the group |

A typical design uses a small number of groups, for example ETL, scheduled reporting, ad-hoc analysis, and administration, each with different limits, so that a batch load cannot starve interactive reporting and a single user cannot consume the cluster.

**Why this matters to the platform design.** The sizing in the previous section is built against a stated peak concurrency, and the concurrency table there explicitly assumes resource groups are enforcing that figure. Without them, the concurrency number used in sizing is an expectation rather than a limit. Nothing prevents fifty users each launching a heavy query on a cluster sized for forty, and the failure mode is the spill cascade described in the [Memory Usage Patterns](./workload-characteristics.md#memory-usage-patterns) and [Storage Access Patterns](./workload-characteristics.md#storage-access-patterns) sections, where memory exhaustion degrades every query on the cluster rather than only the excess ones.

Resource groups are therefore the database-layer counterpart to the controls this architecture applies at the platform layer.   
Memory reservations and admission control (the [Memory Management and Scheduling](./vsphere-cluster-design.md#memory-management-and-scheduling) and [vSphere HA Configuration Recommendations](./vsphere-cluster-design.md#vsphere-ha-configuration-recommendations) sections) guarantee that a virtual machine's resources cannot be taken away by the hypervisor. Resource groups guarantee that the resources inside that virtual machine cannot be over-consumed by the database's own users.   
Both are required, because the platform guarantees can be defeated from within the database if nothing caps concurrency.

### Sizing Checklist

The following inputs should be established before sizing a Greenplum platform. Each maps to a specific sizing decision.

| Input | Determines |
| :---- | :---- |
| Peak concurrent users or applications | Concurrency, the primary driver of memory |
| Proportion running heavy analytical queries rather than small lookups | The concurrency figure that applies to the table in [Adjusting for Concurrency and Query Load](#adjusting-for-concurrency-and-query-load) |
| Current raw dataset size and expected growth over two to three years | Storage sizing and host count |
| Proportion of append-optimized or columnar data versus heap | Compression expectations, and whether incremental backups are worthwhile ([Greenplum Backup and Restore](./backup-and-restore.md#greenplum-backup-and-restore)) |
| Whether queries typically join several large tables | Memory per query, and interconnect load from data movement |
| Presence of large sorts or aggregations over wide result sets | Memory per query, and spill risk |
| Batch or ETL windows with a different resource profile from daytime queries | Whether the cluster must be sized for a peak that occurs only at certain times |
| Whether resource groups will cap concurrency, and how many workload classes are planned | Whether the concurrency figure is enforced or merely expected |
| Acceptable runtime for the most important queries | Whether parallelism, and therefore segment count, must increase beyond what capacity alone requires |
| Availability expectations under host failure | Admission control level, and therefore the failover capacity reserve |

The most common sizing failure is treating average load as the design point. Greenplum should be sized for concurrency and query complexity at peak, because the failure mode when undersized is spilling, and spilling degrades every query on the cluster rather than only the one that exceeded its memory.

## Storage Sizing

Storage sizing is a two-layer calculation, and keeping the layers separate is what prevents redundancy being counted twice. The Greenplum layer determines how much usable space the data needs. The vSAN layer determines how much raw capacity that usable space consumes once platform overhead and the failure tolerance policy are applied.

**Greenplum usable requirement.** Adapted for the mirrorless design used here:

```
Usable = U + U/3
```

where `U` is the user data size and `U/3` is the working area reserved for temporary and transaction files. Two adjustments from the generic formula apply: the database-mirror term is dropped because this design has no database mirrors, and raw data expands by roughly 1.4 times when loaded, so `U` should be estimated from raw source data with that expansion in mind, before any table compression is credited back.

This aligns with the platform guidance to reserve 30 percent of usable storage per functional unit for temporary and transaction files. The two expressions describe the same reservation.

**vSAN overhead and failure tolerance.** Raw capacity is reduced first by vSAN's own overhead and then by the failure tolerance policy. For a single-tier design, vSAN consumes approximately 10 percent of CPU, 20 percent of memory, and 30 percent of raw storage capacity. The remaining capacity is then divided by the policy overhead from [Minimum Disk Layout and SPBM Guidelines](./storage-architecture.md#minimum-disk-layout-and-spbm-guidelines).

The ESA overhead factors, for the erasure coding schemes that vSAN ESA actually uses:

| Policy | vSAN implementation | Overhead | Minimum hosts |
| :---- | :---- | :---- | :---- |
| FTT=1, RAID-5 | Erasure coding, 2+1 scheme | 1.5x | 4 to 5 |
| FTT=1, RAID-5 | Erasure coding, 4+1 scheme | 1.25x | 6 or more |
| FTT=1, RAID-1 | Mirroring, 2 copies | 2x | 4 |
| FTT=2, RAID-6 | Erasure coding, 4+2 scheme | 1.5x | 6 or more |
| FTT=2, RAID-1 | Mirroring, 3 copies | 3x | 5 |

Two observations follow from this table and both reinforce decisions made earlier. At six or more hosts, moving from FTT=1 RAID-5 to FTT=2 RAID-6 costs 1.25x rather than 1.5x, a premium of 20 percent for a full additional host failure tolerance, which is inexpensive insurance in a mirrorless design where vSAN holds the only copy.   
And below six hosts, RAID-5 at FTT=1 already costs 1.5x, the same as RAID-6, without the additional protection. A small cluster therefore pays RAID-6 overhead for RAID-5 resilience, which is a further reason six hosts are the production floor (see [Host Count and Configuration Model](./vsphere-cluster-design.md#host-count-and-configuration-model)).

**Two headroom pools, kept separate.** The Greenplum 70 percent guideline exists so that remaining space absorbs temporary and spill files, and is a data-volume concern. The vSAN rebuild reserve (see [Platform-Level vSAN Configuration](./storage-architecture.md#platform-level-vsan-configuration)) exists so the cluster can rebuild after a host failure, and is a resilience concern at the datastore level. They stack rather than overlap.

**Per-VMDK sizing.** The layout from [Minimum Disk Layout and SPBM Guidelines](./storage-architecture.md#minimum-disk-layout-and-spbm-guidelines), comprising OS, Segment Data, WAL, and Temp, means storage is sized per class rather than as a single pool, because each class carries a different policy and growth pattern. Segment Data grows with the dataset, WAL and Temp are sized to workload behavior, and OS is effectively fixed. Minimum Disk Layout and SPBM Guidelines remains the authority for the per-VMDK policies.

**Key Storage Policy Note: Greenplum AO Compression vs. vSAN ESA Inline Compression:** To avoid redundant CPU cycles from double-compression, establish a clear compression policy:

* **Database-Led Compression:** Use `zstd` at the Greenplum table level for historical AO partitions, and disable compression on the vSAN VMDK Storage Policy for data drives.  
* **Infrastructure-Led Compression:** Keep Greenplum tables uncompressed and allow vSAN ESA's inline compression engine to handle block-level compression transparently.

## Scaling Model: Vertical and Horizontal

Greenplum scales along two axes, and they are complementary rather than competing. Vertical scaling increases the resources of existing segment VMs and preserves the segment topology. Horizontal scaling adds hosts and segment VMs, and is the only path that adds MPP parallelism.

### Vertical Scaling

Vertical scaling is the preferred response when the bottleneck is resource pressure on otherwise well-balanced hosts: memory-bound concurrency, temp spill pressure, or storage growth at an unchanged segment count.

* **CPU and memory changes are a cold operation** in this design. Hot-add is not used because it disturbs vNUMA presentation and full reservations. The sequence is to stop the database, power off the segment VMs in a maintenance window, resize, verify the new size still fits within a single NUMA node, and re-apply 100 percent CPU and memory reservations.  
* **Disk changes are online.** Segment Data, WAL, and Temp VMDKs can be grown and their guest filesystems extended without downtime, and storage policy changes apply online while vSAN resynchronises in the background.  
* **Database follow-up is required.** After a memory increase, the Greenplum memory limits must be raised so the database uses the added RAM, then validated with a controlled workload replay. Adding memory without this step changes nothing the database can see.

The ceiling is the NUMA size. Once a VM would need to span across NUMA nodes, or host memory, further vertical growth erodes the predictability this architecture is built on. That is the signal to scale horizontally.

### Horizontal Scaling

Horizontal scaling adds ESXi hosts to the dedicated cluster and new segment VMs on top of them, then redistributes data with `gpexpand`. It increases aggregate parallelism, I/O bandwidth, and capacity together.   
Adding nodes achieves approximately linear scaling of capacity and performance. 

### Choosing between Vertical and Horizontal Scaling

The two approaches compared:

| Dimension | Vertical | Horizontal |
| :---- | :---- | :---- |
| What grows | CPU, memory, disk of existing segment VMs | Number of segment hosts and segments |
| MPP parallelism | Unchanged | Increases |
| Downtime | Maintenance window for CPU and memory; disk online | Cluster online, redistribution window required |
| Data movement | None | `gpexpand` redistribution |
| Backup impact | None | Invalidates incremental chains, requires a new full backup |
| Limit | NUMA envelope and host hardware | Rack, network, and budget |
| Best for | Memory or spill pressure, storage growth | Sustained data and concurrency growth |

Symptoms point to different remedies, and reading them correctly prevents scaling the wrong axis.

| Symptom | Likely cause | Correct response |
| :---- | :---- | :---- |
| Queries queuing while CPU is not saturated | Concurrency slots exhausted | Add memory per host, or rebalance workload classes through resource groups. Not more segments. |
| Spill volume growing and runtimes elongating at steady data volume | Memory per query insufficient for the concurrency | Add memory, reduce concurrency, or lower per-query memory. Not more segments. |
| A single query slow while memory is comfortable | Insufficient parallelism for the data size | Horizontal, more segments |
| All queries slow with CPU saturated across hosts | Compute exhausted | Horizontal, more hosts |
| Runtimes growing in step with data volume | Data has outgrown the segment count | Horizontal, gpexpand |
| Runtime variance and skew without a clear database cause | Platform contention such as CPU ready time, cross-NUMA access, or interconnect pressure | Revisit the [CPU Architecture, NUMA Awareness, and vNUMA Configuration](./vsphere-cluster-design.md#cpu-architecture-numa-awareness-and-vnuma-configuration), [Memory Management and Scheduling](./vsphere-cluster-design.md#memory-management-and-scheduling), and [Virtual Distributed Switch (vDS) Design](./vds-design.md#virtual-distributed-switch-vds-design) sections before scaling anything |

Because concurrency growth is fundamentally a memory problem, and memory per VM cannot exceed one NUMA node, a cluster whose query load keeps rising will eventually find the vertical answer unavailable and the only remaining path horizontal. This should be anticipated in planning rather than discovered at the ceiling.

Two second-order effects accompany growth in segment count. Interconnect fan-out grows faster than linearly ([Network Traffic Characteristics](./workload-characteristics.md#network-traffic-characteristics)), placing more demand on the network design in [Virtual Distributed Switch (vDS) Design](./vds-design.md#virtual-distributed-switch-vds-design). And higher process density per host raises CPU scheduling pressure, which makes the no-overcommit rule more important as the cluster grows.

## Capacity Planning Method

Capacity planning follows a small set of rules and then a repeatable derivation.

* **Plan segments per host around NUMA, not raw core count.** The segment count per host is fixed by the VM shape chosen in [vSphere Cluster and Compute Design](./vsphere-cluster-design.md#vsphere-cluster-and-compute-design). Growth planning should change the number of hosts, not the shape of a proven segment VM.  
* **Reserve failure capacity first.** The admission control reserve from [vSphere HA Configuration Recommendations](./vsphere-cluster-design.md#vsphere-ha-configuration-recommendations) is an input to capacity, not a leftover. Usable capacity is what remains after it.  
* **Verify the failover fit.** The steady-state placement must be checked against the failure case, so that when hosts fail and their VMs restart elsewhere, the surviving hosts can run the additional VMs without overcommit. This check is described below and is frequently missed.  
* **Track vSAN slack explicitly.** Keep sustained utilization below the recommended free-capacity threshold so rebuilds, resyncs, and policy changes always have room.  
* **Trigger expansion early.** Treat roughly 70 percent sustained storage utilization, or sustained concurrency saturation visible as queued queries or growing spill, as the planning trigger, because the scale-out workflow including redistribution and a fresh full backup takes time to execute safely.

The derivation is to fix the segment VM shape first, check it against NUMA and failover, derive cluster capacity from host count, and subtract failure reserve and vSAN slack before committing capacity.

### Operational Thresholds and Capacity Triggers

Infrastructure administrators should establish automated alerts based on the following operational thresholds:

* **Storage Expansion Trigger (70% Usable Capacity):** When vSAN usable datastore capacity reaches 70%, trigger a storage expansion. The scale-out process involving `gpexpand` and the subsequent mandatory full backup requires operational buffer time.  
* **Memory Spill Alert:** Monitor database system views for disk spill activity. Sustained spilling indicates that query concurrency or complexity has outgrown available RAM. Address this by allocating more RAM per VM (Vertical Scale) or adjusting Resource Group limits.  
* **The 1:1 Physical Core Rule:** In dedicated production clusters, always match 1 vCPU to 1 physical CPU core. Never rely on hyperthreading logical processors as extra compute capacity for Greenplum workloads.  
* **vSAN Rebuild Reserve:** Always maintain enough unallocated physical storage on the vSAN cluster to allow a complete automatic rebuild if a single physical ESXi host fails.

## Horizontal Expansion with gpexpand

Adding segments to a running cluster uses the `gpexpand` utility. On this platform there is a vSphere dimension, so the platform steps come first.

**Platform preparation:**

* Add ESXi hosts to the dedicated cluster, or free capacity on existing hosts, so new segment VMs can be placed with each VM fitting within a NUMA node and the VM count per host dividing evenly across nodes.  
* Confirm the placement preserves coordinator and segment anti-affinity ([VM Placement and Anti-Affinity Rules](./vsphere-cluster-design.md#vm-placement-and-anti-affinity-rules)).  
* Re-run the failover fit check from "Operational Thresholds and Capacity Triggers" for the new host and VM counts.  
* Recompute admission control for the new host count and confirm the storage policy remains consistent with it. Crossing certain host counts raises the achievable failure tolerance, so an expansion can improve resilience as well as capacity.  
* Ensure the vSAN datastore has capacity for the added segments plus the rebuild reserve ([Platform-Level vSAN Configuration](./storage-architecture.md#platform-level-vsan-configuration)).

**Greenplum expansion.** The utility is typically run in four passes:

```
gpexpand -f hosts_file              # 1. create the expansion input file
gpexpand -i input_file -D database  # 2. initialize new segments, create expansion schema
gpexpand -d duration                # 3. redistribute tables across the new segments
gpexpand -c                         # 4. remove the expansion schema when complete
```

What matters at the architecture level:

* **Brief downtime, then online.** Initialising the new segments requires a short scheduled restart whose length is unrelated to cluster size. Afterwards the new segments participate immediately.  
* **An interim redistribution window.** Until redistribution runs, existing data remains concentrated on the original segments, and tables are temporarily set to random distribution. During this window some queries are less efficient and unique constraints are not enforced. Redistribution returns each table to its original distribution policy, and performance improves incrementally as each table completes.  
* **Redistribution is heavy but resumable.** It generates substantial disk and network activity and can run for a long time on large datasets, but it can be paused, resumed, and prioritized per table, so it can be fitted around business hours. Each table is unavailable for reads and writes only while it is being redistributed.  
* **Recent releases have improved expansion performance materially**, including compression of the catalog template distributed to expansion hosts, parallel ledger initialization, and connection pooling during redistribution. Expansion timings from older releases should not be assumed to still apply.

**Backup consequence.** Changing the segment configuration invalidates existing incremental backup chains. After expansion completes and the expansion schema is removed, a fresh full backup must be taken before any further incremental backup ([Greenplum Backup and Restore](./backup-and-restore.md#greenplum-backup-and-restore)). This belongs in the expansion runbook.

This is distinct from the resize restore path in [Greenplum Backup and Restore](./backup-and-restore.md#greenplum-backup-and-restore). `gpexpand` grows the current cluster in place; resize restore moves a backup onto a separately built cluster of a different size. Both change segment counts, but only the latter is a restore operation.

## Capacity Planning for Shared Clusters

[Dedicated Tenancy Requirement](./vsphere-cluster-design.md#dedicated-tenancy-requirement) establishes that Greenplum should run on a dedicated vSphere cluster. Where constraints genuinely rule that out, the objective becomes recreating dedicated-like guarantees inside a shared cluster. This is a fallback rather than an equal alternative.

A terminology note: the mechanisms below are vSphere level infrastructure controls. Greenplum also has an in-database feature called resource groups, which governs concurrency and memory per workload class inside the database. They are different layers.

| Mechanism | Function | Relevance |
| :---- | :---- | :---- |
| Host groups with VM-Host affinity, using "must" rules | Confines Greenplum VMs to a defined subset of hosts | Creates a bounded performance and failure domain, so placement and failover occur within a known host set |
| Full CPU and memory reservations | Guarantees resources regardless of co-tenants | Enforces the zero-overcommit requirement from [Memory Management and Scheduling](./vsphere-cluster-design.md#memory-management-and-scheduling) on shared hardware |
| Admission control planned within the host subset | Reserves failover capacity inside the Greenplum host group | Keeps restart behavior correct when the surrounding cluster is not dedicated |
| Hyperthread core sharing restricted for Greenplum VMs | Gives the Greenplum VMs exclusive physical cores | Delivers the benefit of disabling hyperthreading without imposing it on other tenants |

The essential idea is that host groups carve out a bounded set of hosts that behave, for Greenplum, like a small dedicated cluster, and full reservations guarantee the resources within it. The failure math is then tractable, because the failover reserve is planned across the confined subset rather than the shared cluster at large. Without the affinity confinement, a failed Greenplum VM could restart onto a busy general-purpose host, and the zero-overcommit guarantee would be lost precisely when it is most needed.

Two cautions. The isolation is only as strong as the affinity rules and reservations, so "should" rules or partial reservations leave Greenplum exposed to the contention that [Greenplum Workload Characteristics](./workload-characteristics.md#greenplum-workload-characteristics) shows it cannot tolerate. And a shared cluster still carries the lifecycle coupling of its other tenants, including patching windows and change schedules that Greenplum does not control. These controls make a shared cluster workable; however, they do not make it equivalent to a dedicated one.

### Mandatory Controls for Shared vSphere Clusters

If Greenplum must share physical ESXi hosts with other enterprise workloads, administrators must configure the following vSphere controls to emulate a dedicated environment:

* **VM-Host "Must" Affinity Rules:** Create dedicated host groups that strictly confine Greenplum VMs to a specific subset of ESXi hosts.  
* **100% Explicit Resource Reservations:** Set 100% reservations for both CPU and RAM on all Greenplum VMs. Memory overcommit must be 0%.  
* **Restricted Hyperthread Sharing:** Set the HT Sharing Policy on Greenplum VMs to **"Internal"** or **"None"** so other virtual machines cannot run on the same physical cores.  
* **Dedicated Resource Groups:** Enforce database-level concurrency limits using Greenplum Resource Groups to protect the infrastructure from unconstrained query execution.

## Section Summary

* Compute sizing starts from the functional unit, 8 vCPU and 32 GB per segment at moderate concurrency, giving a baseline of 4 GB of memory per vCPU. Memory per vCPU rises with concurrency, commonly to 8 to 16 GB per vCPU for high-concurrency analytical clusters, and should not be reduced below the baseline.  
* A segment host VM is two to four functional units, must fit within one NUMA node, and the VM count per host must divide evenly across that host's NUMA nodes.  
* Hyperthreading is disabled on dedicated high-intensity clusters, where vCPU is budgeted one to one against physical cores. It is retained with restricted core sharing on shared clusters, and may be budgeted up to two to one where concurrency is moderate and predictable.  
* Storage sizing is two-layered: Greenplum's working reservation on top of user data, then vSAN overhead and the failure tolerance policy for raw capacity. At six or more hosts, FTT=2 RAID-6 costs 1.5x against 1.25x for FTT=1 RAID-5, a 20 percent premium for an additional failure tolerance.  
* Vertical scaling is capped at one NUMA node per VM. Horizontal scaling is the primary growth path and scales approximately linearly.  
* Capacity planning fixes the VM shape first, verifies it against NUMA fit and the failover case, then derives cluster capacity and subtracts reserves.  
* `gpexpand` grows the running cluster, must respect NUMA and anti-affinity placement, and invalidates incremental backups, requiring a fresh full backup afterwards.  
* Where a dedicated cluster is impossible, host groups, full reservations, restricted hyperthread sharing, and admission control planned within the confined subset recreate dedicated-like guarantees as a documented fallback.
