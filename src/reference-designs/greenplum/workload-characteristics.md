# Tanzu Greenplum Workload Characteristics

This section describes the workload characteristics of Tanzu Greenplum that directly drive infrastructure design decisions on vSphere. Tanzu Greenplum behaves very differently from Online Transaction Processing (OLTP) databases and from typical application workloads. Because of that, generic virtualization defaults are usually not a strong fit to an optimal Tanzu Greenplum cluster. Every design recommendation in the rest of this Reference Architecture maps back to the behaviors described here.

## Tanzu Greenplum Architecture Overview

The previous section introduced the Tanzu Greenplum components and showed how they map onto vSphere. This section looks at the same components with a different question in mind, not what they are, but how they consume CPU, memory, storage, and network resources while queries are running. That behavior is what the rest of this document is designed around.

Tanzu Greenplum is a shared-nothing MPP database. A query arrives at the Coordinator, where it is parsed and planned centrally, and is then broken into fragments that run in parallel across every participating segment. Each segment works only on the slice of data it owns locally, and segments exchange intermediate results with one another over the interconnect as the plan requires. The Coordinator (called the master in Tanzu Greenplum 6 and earlier) performs very little data-intensive work of its own. It acts as the control and orchestration point rather than a place where large volumes of data are processed.

The components behave as follows during a workload:

The **Coordinator** is the entry point for all client connections, whether from SQL clients, JDBC or ODBC applications, or ETL tools. It parses queries, builds the distributed plan, and dispatches that plan to the segments. Its resource footprint is light compared to a segment, but it is a single, central point that every query passes through.

The **Standby** **Coordinator** holds a synchronously maintained replica of the Coordinator's metadata and provides coordinator-level availability. Promotion of the standby is an explicit, operator-driven action rather than an automatic one, which is an important detail for the availability design in [Coordinator and Standby Semantics](./vsphere-cluster-design.md#coordinator-and-standby-semantics).

The **Segment** **instances** are where the real work happens. Each segment host runs several segment instances, and each instance owns its portion of the data and executes its fragment of the query in parallel with all the others. These are the components that consume the bulk of the CPU, memory, storage, and network resources on the platform. The decision on whether segments are deployed with an accompanying redundancy topology is a separate decision covered in [Tanzu Greenplum Resilience Topology on vSphere: Mirrored and Mirrorless](./resilience-topology.md#tanzu-greenplum-resilience-topology-on-vsphere-mirrored-and-mirrorless), the workload behavior described here applies to the segments that perform the query work in either case.

The **Interconnect** is the high-speed, all-to-all fabric segments used to communicate during query execution. It carries the motion operators that redistribute intermediate results between segments, and its characteristics are examined in detail in [Network Traffic Characteristics](#network-traffic-characteristics).

The single most important behavior to take away from this section is the following. Because a query stage is not complete until every segment assigned to it has finished, Tanzu Greenplum performance is governed by the slowest participating segment. If one segment is short on CPU, low on memory, waiting on storage, or blocked on the network, the entire query slows down or stalls along with it. The faster segments cannot make up for a slow one; they wait.

This is why balance across segments matters far more in Tanzu Greenplum than peak performance on any single node, and it is the reason several themes recur throughout this document. Segments need uniform and predictable resources, contention between segment VMs has to be avoided, and noisy-neighbor effects are considerably more damaging here than in most virtualized workloads. The subsections that follow examine how this plays out for query execution, concurrency, CPU, memory, storage, and network, and then explain why generic virtualization defaults fall short.

## Query Execution and Motion

A Tanzu Greenplum query moves through a predictable set of phases. The Coordinator parses and plans the query, then dispatches the plan to the segments. The segments run their portion of the plan in parallel against local data, exchanging intermediate results with one another as needed, and the final results are gathered back to the Coordinator and returned to the client.

What makes this different from a single-node database is how the plan is broken up. Tanzu Greenplum divides a query plan into slices, and it creates a new slice boundary wherever the plan requires data to move between segments. The set of worker processes running the same slice across all the segments is called a gang, and as each gang finishes its portion of work, tuples flow up to the next gang through the interconnect. This inter-process, segment-to-segment communication is the interconnect at work, and it is the phase of query execution that depends most heavily on the underlying infrastructure.

It is worth noting that not every query triggers this. A targeted query, such as a single-row insert or a query that filters on the table's distribution key, is dispatched to a single segment and completes without any motion across the interconnect. Interconnect load is therefore driven by the query mix, not by every statement that runs. Large analytical joins and aggregations are the queries that generate heavy motion, and they are the ones this architecture is built to serve well.

**Motion operators**

When a plan does require data to move, it does so through one of a few motion operators:

* Redistribute motion reshuffles rows across the segments based on a hash of the distribution or join key. This is common when two tables are distributed on different keys and need to be joined.  
* Broadcast motion sends a copy of one segment's rows to all other segments, typically when one side of a join is small.  
* Gather motion consolidates rows from all segments up to the Coordinator, usually as the final step before results are returned to the client.

Each of these produces intense, bursty, all-to-all east-west traffic between segment VMs. Because the traffic is generated by many gangs exchanging tuples at the same slice boundary at once, it arrives in short, high-volume bursts rather than a steady stream.

**Infrastructure implication**

The motion phase is the most infrastructure-sensitive part of Tanzu Greenplum query execution, and it is sensitive to more than just average latency. It is affected by:

* Latency variance and jitter, not only mean latency, because a query stage waits for the slowest exchange to complete.  
* Packet loss and the TCP retransmissions that follow, which stall the gang waiting on the missing tuples.  
* Microbursts and queue drops at the NIC or switch, which are easy to miss in average utilization figures but directly hit motion-heavy queries.

In practice, parallel queries rely on real-time synchronization across nodes; while minor network jitter is absorbed automatically, unrecovered network packet loss or storage stalls will trigger interconnect timeouts and abort the query.   
Progress is bounded by the slowest communication path, so the design goal for the network and storage layers is not just high bandwidth but consistent, low-variance behavior under bursty load. The network design that follows from this is detailed in [Network Traffic Characteristics](#network-traffic-characteristics) and [Virtual Distributed Switch (vDS) Design](./vds-design.md#virtual-distributed-switch-vds-design), and the storage latency considerations in [Storage Architecture - vSAN & vSAN Storage Cluster](./storage-architecture.md#storage-architecture-vsan-vsan-storage-cluster).

## Concurrency and Parallelism

Tanzu Greenplum achieves parallelism with distributed data processing across segments. Two related but distinct ideas drive Tanzu Greenplum's scaling behavior.

* **Parallelism** is how much of a *single* query runs at once. It comes from the number of segments, so adding segments makes an individual query faster.  
* **Concurrency** is how many queries run at the *same time*. It is a function of the CPU and memory available per segment, so it improves by giving segments more resources.

This architecture is designed to support both scaling directions without one starving the other.

The defining characteristic on a segment host is **process density**, which refers to the number of individual segment database instances running on a single physical host or Virtual Machine (VM). At peak concurrency:

* Each segment host runs dozens to hundreds of backend and worker processes simultaneously.  
* These processes are long-lived for the duration of a query and run in parallel.  
* Host-level parallelism is therefore expressed as a large number of concurrent processes.

This density is not incidental; it is fundamental to how Tanzu Greenplum's MPP model achieves throughput. It is also the root cause of the CPU and memory behavior detailed in the next two sections.

**Infrastructure implication:** Tanzu Greenplum assumes near-exclusive, predictable access to CPU and memory on segment hosts during active queries. Shared or heavily overcommitted models break that assumption. The same process density is why scheduling and placement matter so much, and why segment VMs are aligned to NUMA boundaries in [CPU Architecture, NUMA Awareness, and vNUMA Configuration](./vsphere-cluster-design.md#cpu-architecture-numa-awareness-and-vnuma-configuration).

## CPU Usage Patterns

Tanzu Greenplum is a CPU-intensive analytical engine whose executor is built to consume CPU aggressively so queries finish quickly. CPU behavior on the segment hosts ends up governing 

* Query runtime  
* Memory pressure and spill behavior  
* Network motion efficiency, and   
* Overall cluster throughput.

Key characteristics define this behavior:

* **Sustained CPU saturation.** During active workloads, segment hosts run at high and continuous CPU utilization. Idle CPU time is not a design objective, queries are expected to consume available compute during their execution windows. Tanzu Greenplum treats CPU as a dedicated execution resource, not a shared or elastic one.  
* **High process concurrency.** Following directly from the process density in the previous section, each segment process runs its own plan fragment. This produces frequent context switching, heavy scheduler involvement, and real sensitivity to CPU scheduling latency.  
* **Tight coupling between CPU progress and query progress.** Query stages are synchronized   
  * Motion operators wait for all senders   
  * Aggregations wait for all inputs   
  * Final stages wait for the slowest segment

A CPU slowdown on one segment does not stay local; it elongates the entire query.

**Infrastructure implication:** 

Segment hosts must be provisioned with dedicated, non-overcommitted physical CPU. Any overcommitment or uncontrolled scheduling contention shows up as variable query latency and unstable throughput.   
vCPUs should map to physical cores within a NUMA node, and oversubscription must be avoided.   
The vNUMA configuration and CPU reservation that enforce this are defined in [CPU Architecture, NUMA Awareness, and vNUMA Configuration](./vsphere-cluster-design.md#cpu-architecture-numa-awareness-and-vnuma-configuration) and [Memory Management and Scheduling](./vsphere-cluster-design.md#memory-management-and-scheduling).

## Memory Usage Patterns

Tanzu Greenplum uses **memory** as its **primary performance accelerator**. Query performance depends on keeping working sets resident in memory and on fast, predictable access to that memory throughout execution. Rather than using memory conservatively, Tanzu Greenplum deliberately allocates large amounts to analytic operators to minimize disk I/O, reduce network wait, and preserve parallelism.

**Key Characteristics:**

* **Large per-operator allocations.** Hash joins, hash aggregations, and large sorts receive substantial memory per operator, and these allocations directly affect query efficiency and completion time.  
* **High operator concurrency per host.** Each segment process may run several operators at once, and each host runs many segment processes in parallel, so aggregate memory consumption per host climbs quickly during complex or concurrent queries.  
* **Strong NUMA sensitivity.** Tanzu Greenplum relies on fast local memory access. Cross-NUMA or remote access adds latency and can become a bottleneck during memory-intensive phases such as hash table builds and probes.

The failure mode to understand is **spilling**. When enough memory is not available, operators spill intermediate data to temporary disk space. Spilling lets a query complete, but it carries compounding penalties:

* Significant added I/O load that is often random and bursty.  
* Elevated storage latency that affects not only the spilling query but other concurrent work.  
* Longer query lifetimes, which increase interconnect traffic because motion operations run for longer.

When spills occur across multiple hosts at once, the impact is cluster-wide rather than an isolated slowdown: execution skew grows, contention amplifies, and throughput collapses.

**Infrastructure implication:** 

Segment hosts must be provisioned with **fully reserved, physically available memory**. Memory overcommit, ballooning, compression, and swapping must be disabled by reserving 100% of the VM's memory, and NUMA alignment with full reservation is a prerequisite. The reservation and overcommit policy that enforce this are defined in [Memory Management and Scheduling](./vsphere-cluster-design.md#memory-management-and-scheduling).

## Storage Access Patterns

Tanzu Greenplum's storage behavior is very different from a transactional database tuned for small, random I/O at low average latency. As a parallel analytical system, it generates large, sustained, highly concurrent I/O across all segment hosts at once. 

What matters is not peak IOPS or average latency, but how consistent and predictable the latency stays while the whole cluster reads and writes in parallel.

**Read patterns** are dominated by large sequential reads:

* Parallel table scans, partition scans, and block or column-oriented reads depending on table layout.  
  Each segment scans its own local data independently, producing large sequential streams rather than small random reads.  
* High throughput demand/High concurrency per host  
  * On each segment host:   
    * Multiple segments read concurrently   
    * Each segment may issue multiple read streams   
    * Reads are sustained for the full duration of the query 

  This creates aggregate throughput pressure on the storage subsystem, even if individual reads are sequential and efficient.

**Write patterns** come in three distinct forms:

* **Bulk writes** from initial loads, ETL batches, and large INSERT, COPY, or CREATE TABLE AS operations. Typically large and sequential, but concurrent across many segments and hosts.  
* **WAL writes**, used for durability and recovery. Smaller in size but highly latency-sensitive, because they are synchronous, a WAL latency spike can stall commit and query progress even when bulk I/O looks healthy.  
* **Temporary spill writes.** As mentioned in the previous section, these are random and bursty, and self-reinforcing, since slower I/O lengthens the query, which produces still more spill.

The characteristic that ties this together is that **query execution is synchronized across segments**, so query performance is governed by the consistency of storage latency rather than its average. A single segment hitting even a brief latency spike can stall a motion operator, elongate the whole query, and create execution skew. Background storage operations are the usual source of such spikes, and in Tanzu Greenplum they surface directly to users as query stalls and inconsistent runtimes for identical queries. Typical culprits include:

* RAID or vSAN rebuilds and disk resyncs  
* Object storage rebalancing  
* Snapshot merges or garbage collection

**Infrastructure implication:** Storage platforms tuned for small random I/O and judged mainly on average latency tend to underperform for Tanzu Greenplum. The design priority is consistent, predictable latency under sustained parallel load and the avoidance of latency spikes, not a headline IOPS figure. The storage architecture that follows is covered in [Storage Architecture - vSAN & vSAN Storage Cluster](./storage-architecture.md#storage-architecture-vsan-vsan-storage-cluster).

## Network Traffic Characteristics

Tanzu Greenplum generates intense east-west traffic during query execution, concentrated in the motion phases where data is redistributed, broadcast, or gathered across segment hosts. Unlike north-south application traffic, interconnect traffic is highly synchronized, throughput sensitive, and bursty depending on the query.

Key attributes:

* **All-to-all communication.** Redistribution for joins, broadcast of small tables, and gather for final aggregation all mean every segment sends data to many or all of the others at once.  
* **Non-linear fan-out with scale.** Traffic scales with both data volume and segment count, so as the cluster grows the fan-out grows faster than linearly, placing real stress on the interconnect.  
* **Sensitivity beyond bandwidth.** Because motion is synchronized, the interconnect is sensitive to packet loss, latency variance across paths, and microbursts that briefly overflow buffers, often more than to average throughput.

The failure behavior is that congestion does not degrade Tanzu Greenplum gracefully. When motion traffic is dropped or delayed, the affected operators stall, and because stages are synchronized, a stalled operator holds up the whole stage. A single congested NIC or oversubscribed uplink can therefore turn into a cluster wide performance problem, and queries may abort rather than slow cleanly.

**Infrastructure implication:** For the interconnect, low loss and predictable latency matter as much as bandwidth. The network should be designed to behave in an effectively lossless way for interconnect traffic under bursty load. The vDS design, traffic-class separation, and teaming policy that deliver this are covered in [Virtual Distributed Switch (vDS) Design](./vds-design.md#virtual-distributed-switch-vds-design).

## Failure Sensitivity

Tanzu Greenplum's MPP model makes query execution sensitive to the health of every participating segment, because a stage cannot complete until all of its segments finish. The loss of a single segment mid-query usually causes that in-flight query to fail rather than degrade. How the cluster returns to service afterward depends on the high-availability topology and the platform recovery mechanisms, covered in the next [Tanzu Greenplum Resilience Topology on vSphere: Mirrored and Mirrorless](./resilience-topology.md#tanzu-greenplum-resilience-topology-on-vsphere-mirrored-and-mirrorless).

The failure types worth calling out:

* **CPU starvation.** Increases query duration on the affected segment.  
* **Transient network loss.** Can hang or fail motion operators, queries may abort.  
* **Storage latency spikes.** Increases query duration on affected segments.  
* **Host failure.** Takes its segments offline, so active queries using them fail. The cluster must then detect the failure, mark segments down, restart or recover the affected VMs, and resynchronize before normal service resumes.

**Infrastructure implication:** Recovery mechanisms, including vSphere HA, DRS, and vSAN rebuild, must be designed and scheduled so they do not repeatedly interrupt motion-heavy queries. These behaviors and the recovery windows they imply are detailed in the high-availability topology section that follows and in [vSphere High Availability (HA)](./vsphere-cluster-design.md#vsphere-high-availability-ha) through [Impact on Query Execution](./vsphere-cluster-design.md#impact-on-query-execution), with storage rebuild considerations in [Storage Failure Behavior: Physical Disk Failure](./storage-architecture.md#storage-failure-behavior-physical-disk-failure).

## Why Generic Virtualization Defaults Fail

The design conventions that make a shared, mixed-workload vSphere cluster efficient are the same conventions that undermine Tanzu Greenplum. The table below summarizes the mismatch.

| Generic Assumption | Tanzu Greenplum Reality |
| :---- | :---- |
| CPU can be overcommitted across VMs | Segment hosts run at sustained high CPU during query windows, so overcommit produces scheduling contention and variable query times |
| Unused memory can be reclaimed | Any reclaim, whether ballooning, compression, or swapping, triggers cascading performance degradation |
| Occasional network drops are tolerable | Unrecovered network drops stall synchronized motion and can cause queries to fail |
| Average storage latency is a sufficient measure | Consistency matters more than the average; latency spikes degrade queries and must be avoided, especially during background storage operations |

The takeaway is that standard vSphere cluster templates built for mixed workloads are not an appropriate baseline for Tanzu Greenplum. 

This architecture calls for a tuned cluster profile with more restrictive policies on CPU, memory, network, and storage behavior than a general purpose cluster would use.

## Design Takeaways for the RA

The workload characteristics above converge on a small set of design imperatives. Each one traces back to the behavior that raised it and forward to the section of this architecture that implements it.

Taken together, these imperatives are the reason this document does not treat Tanzu Greenplum as just another virtualized workload. They shape the vSphere cluster configuration, the vDS design, the vSAN and vSAN storage-cluster architecture, and the rack topology that the remaining sections define.

| Design imperative | Driven by | Implemented in |
| :---- | :---- | :---- |
| Predictable CPU scheduling with NUMA locality, and no CPU overcommit | [Concurrency and Parallelism](#concurrency-and-parallelism), [CPU Usage Patterns](#cpu-usage-patterns) | [CPU Architecture, NUMA Awareness, and vNUMA Configuration](./vsphere-cluster-design.md#cpu-architecture-numa-awareness-and-vnuma-configuration), [Memory Management and Scheduling](./vsphere-cluster-design.md#memory-management-and-scheduling) |
| Zero memory overcommit, with full reservation and no reclaim | [Memory Usage Patterns](#memory-usage-patterns) | [Memory Management and Scheduling](./vsphere-cluster-design.md#memory-management-and-scheduling) |
| Effectively lossless, low-variance east-west networking | [Query Execution and Motion](#query-execution-and-motion), [Network Traffic Characteristics](#network-traffic-characteristics) | [Virtual Distributed Switch (vDS) Design](./vds-design.md#virtual-distributed-switch-vds-design) |
| Storage designed for latency consistency rather than peak IOPS | [Storage Access Patterns](#storage-access-patterns) | [Storage Architecture - vSAN & vSAN Storage Cluster](./storage-architecture.md#storage-architecture-vsan-vsan-storage-cluster) |
| Recovery mechanisms that respect running queries | [Failure Sensitivity](#failure-sensitivity) | HA topology section, the [Mirrorless Tanzu Greenplum on vSphere](./resilience-topology.md#mirrorless-tanzu-greenplum-on-vsphere) through [When Mirroring Is Still the Right Choice](./resilience-topology.md#when-mirroring-is-still-the-right-choice) sections, [Virtual Distributed Switch (vDS) Design](./vds-design.md#virtual-distributed-switch-vds-design) |
| Placement that preserves Tanzu Greenplum's failure domains | [Tanzu Greenplum Architecture Overview](#tanzu-greenplum-architecture-overview), [Failure Sensitivity](#failure-sensitivity) | [VM Placement and Anti-Affinity Rules](./vsphere-cluster-design.md#vm-placement-and-anti-affinity-rules), [Storage Architecture - vSAN & vSAN Storage Cluster](./storage-architecture.md#storage-architecture-vsan-vsan-storage-cluster) |
