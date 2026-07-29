# Greenplum Resilience Topology on vSphere: Mirrored and Mirrorless

## Overview

Greenplum and the vSphere platform each bring their own resilience mechanisms. Greenplum protects itself at the database layer through segment mirroring and a standby coordinator, while vSphere and vSAN protect the platform layer through storage redundancy, vSphere HA, and DRS. 

How these two layers are combined is one of the most consequential decisions in the whole architecture, because it determines how the cluster survives a failure, how quickly it returns to service, and how much of the hardware is spent on redundancy rather than on useful work.

This section introduces both Greenplum resilience topologies, **mirrored** and **mirrorless**, explains how each behaves on vSphere, and sets out why this reference architecture adopts the mirrorless topology as its validated baseline when Greenplum runs on vSphere with vSAN. It is a conceptual section rather than a configuration guide. The specific settings that implement the chosen topology, such as vSAN storage policies, vSphere HA admission control, and anti-affinity rules, are defined in the later compute, storage, and networking sections and are only referenced here.

A note on terminology used throughout: this section concerns Greenplum *segment* redundancy. The *standby coordinator* is a separate mechanism that protects the coordinator role, and it is retained in every design described in this document regardless of the segment topology chosen. Where this section says "mirrorless", it means segments without mirrors, not a cluster without any high availability.

## Two Layers of Protection: Durability and Availability

It helps to separate two ideas that are easy to conflate, because the mirrored versus mirrorless decision is really about which layer provides each one.

* **Durability** is protection of the data itself. If a disk or a host is lost, the data survives and can be read again. On this platform, durability is provided by vSAN, which keeps redundant copies of every storage object according to its configured policy.  
* **Availability** is the ability of the cluster to keep serving, or to return to service quickly, after a component fails. This is about how fast queries can run again, not about whether the data still exists.

The key insight is that Greenplum mirroring and vSAN redundancy both provide durability, but they provide availability very differently. Once vSAN is providing durability at the storage layer, the remaining question is how the cluster recovers its availability after a failure, and that is where the two topologies diverge.

## Mirrored Greenplum

In a mirrored deployment, high availability is handled inside Greenplum. Every primary segment has a corresponding mirror segment on a different host, and the primary continuously streams its changes to the mirror using write-ahead-log-based replication. If a primary segment fails, Greenplum detects the loss through its Fault Tolerance Server, promotes the mirror to primary automatically, and the cluster continues. In-flight queries on the failed segment are cancelled and must be retried, but they succeed on retry because the mirror takes over within seconds. An administrator later runs a recovery step to rebuild and resynchronize the downed segment and, if desired, restore segments to their original roles.

**Strengths:**

* Fast, automatic segment failover handled entirely within the database, with a recovery measured in seconds for the failover itself.  
* Protection is independent of the underlying storage platform, so mirroring works the same on local disks, SAN, or vSAN.  
* Well understood and long established as the default Greenplum HA model on bare metal.

**Costs:**

* Every primary segment needs a full mirror copy, which roughly doubles the segment count, the storage footprint, and the CPU and memory devoted to segment processes.  
* Continuous WAL replication between primaries and mirrors adds a steady stream of east-west network traffic and write activity on top of the query workload.  
* Mirror placement has to be planned carefully, using group or spread configurations, to make sure a single host failure does not overload the hosts that back it up.

## Mirrorless Greenplum on vSphere

In a mirrorless deployment, segments run as primaries only, with no mirror copies inside Greenplum. Data durability instead comes from vSAN, which keeps redundant copies of each segment's storage objects at the platform layer according to its storage policy. 

Because there is no mirror to fail over to, availability after a host failure is restored by the vSphere platform rather than by the database. vSphere HA restarts the affected segment and coordinator VMs on surviving hosts, and once those VMs are back the affected segments are recovered so the cluster can resume serving queries. Greenplum provides a dedicated high availability service for mirrorless deployments on vSphere that works together with vSphere HA to coordinate this recovery, bringing the restarted segments back to a serving state after a host failure.

The key behavior to understand is the difference in recovery path. When a host fails:

* In-flight queries that were using segments on that host fail, in the same way they would in any segment-loss scenario.  
* The data is safe throughout, because vSAN has maintained redundant copies at the storage layer.  
* vSphere HA restarts the affected VMs on other hosts in the cluster, which is why the cluster must always keep enough spare capacity to absorb a host's worth of VMs.  
* The cluster returns to service once those VMs restart and the segments recover, which is a platform-driven recovery window rather than the near-instant in-database failover that mirroring provides.

**Strengths:**

* No mirror segments means a smaller segment count and a smaller storage footprint, and it frees the CPU, memory, and network that mirror segments and WAL replication would have consumed. That capacity goes to query performance instead.  
* Durability is not weakened, because vSAN is maintaining redundant copies of the data at the storage layer.  
* The design is simpler to operate, with no primary-mirror role management or mirror placement planning to maintain.

**Costs and things to plan for:**

* Recovery from a host failure is a platform-driven restart-and-recover cycle rather than a sub-second database failover, so the recovery window is longer than mirroring's. This must be acceptable to the workload's availability expectations.  
* The cluster depends on vSphere HA having reserved enough capacity to restart a failed host's VMs, so admission control and placement have to be configured deliberately.  
* Because there is no mirror as a second in-database copy, the design leans entirely on vSAN's storage redundancy for durability, which makes correct vSAN policy and sufficient rebuild headroom essential rather than optional.

### The Greenplum High Availability Service for Mirrorless Clusters

As a mirrorless cluster has no mirror segment to fail over to, it needs a mechanism that notices when a primary segment has become unavailable and drives its recovery. Greenplum provides this as a dedicated high availability service for mirrorless deployments, implemented as a lightweight systemd service, `greenplum-postmaster`, that runs on the cluster hosts. The `greenplum-postmaster` service monitors the primary segments of a Greenplum cluster to initiate automatic recovery if they become unavailable. This is required if running Greenplum without mirroring.

Understanding how it fits together depends on separating three roles that each do one part of the work:

* **Fault detection** is owned by Greenplum's Fault Tolerance Server (FTS) on the coordinator. FTS probes the segments and decides cluster membership, marking a segment down when it stops responding. This is what causes in-flight queries touching a lost segment to fail.  
* **Durability** is owned by vSAN. Every segment's data, WAL, and catalog volumes are protected by vSAN storage policies, so the persisted state survives the loss of a process, a VM, or a host. This is the property that makes recovery possible without a database mirror.  
* **Recovery** is owned by the high availability service together with the platform. When a segment or its VM returns, the segment's PostgreSQL instance replays its write-ahead log from the vSAN-backed storage to reach a consistent state and rejoins the cluster, and the high availability service is what drives that primary-segment recovery automatically rather than leaving it as a manual step.

The essential idea is that durability and recovery are handled at different layers but rely on each other. vSAN guarantees the data is always intact and current; the high availability service and the database's own crash-recovery machinery use that intact data to bring a returned segment back into service. This is why a mirrorless cluster can recover from segment and host failures without a second in-database copy: the authoritative copy is the vSAN-protected data, and the service automates the work of reconnecting a recovered segment to the cluster.

How this plays out for each class of failure, a single segment process, a segment VM, a physical ESXi host, and a physical disk, is examined in the compute and high availability design in [vSphere High Availability (HA)](./vsphere-cluster-design.md#vsphere-high-availability-ha), and the storage behavior that underpins it in [Storage Failure Behavior: Physical Disk Failure](./storage-architecture.md#storage-failure-behavior-physical-disk-failure). The key point for this section is that mirrorless Greenplum is not unmanaged: it pairs vSAN durability with a purpose-built recovery service so that the absence of a database mirror does not mean the absence of automated recovery.

## Why This Architecture Recommends Mirrorless on vSphere with vSAN

The reason mirroring exists is to give Greenplum a durable second copy of segment data and a way to keep serving when a copy is lost. On a vSphere platform with vSAN, the storage layer already provides the durable second copy. Layering Greenplum mirroring on top of vSAN redundancy therefore means the same data is protected twice by two independent mechanisms: 

* vSAN keeps redundant copies of the storage objects, and   
* Greenplum keeps a second full copy in its mirror segments. 

That is a large amount of hardware, and a continuous replication overhead, spent protecting against something the platform is already protecting against.

Removing the Greenplum mirror when vSAN is present is therefore not a reduction in data protection. The durability that mirroring would have provided is still there, delivered once by vSAN instead of twice. What changes is the availability recovery path, which moves from an in-database failover to a vSphere-HA-driven restart, and this reference architecture treats that as an acceptable and deliberate trade for analytical and batch workloads that can tolerate a short, platform-driven recovery window. This direction is supported by the vSphere deployment guidance for Greenplum, which identifies vSAN's aggregated, redundant storage as what enables mirrorless architectures and provides a dedicated high availability service to coordinate mirrorless recovery on vSphere. 

The benefits of this choice compound across the rest of the design:

* **Efficiency.** Not duplicating segments frees roughly half of what a mirrored cluster spends on segment redundancy, and that CPU, memory, storage, and network capacity is redirected to query throughput.  
* **Simplicity.** There are no primary-mirror roles, no group or spread mirror placement, and no WAL replication between segments to plan and operate.  
* **Consistency.** Durability lives entirely at the vSAN layer, where the storage policies and rebuild behavior are managed uniformly for the whole cluster rather than split between two mechanisms.

For these reasons, the mirrorless topology is the validated baseline for this architecture, and the compute, storage, and networking sections that follow are sized and tuned around it.

## When Mirroring Is Still the Right Choice

Mirrorless is the recommended baseline for this platform, but it is not universally correct, and the RA should be explicit about the conditions that point the other way. Segment mirroring remains the better choice when:

* The workload cannot tolerate the platform-driven recovery window that follows a host failure, and needs the near-instant, automatic segment failover that only in-database mirroring provides.  
* Greenplum is deployed on storage that does not provide its own redundancy, in which case mirroring is the mechanism providing durability and is not optional.  
* Organizational or contractual requirements mandate database-layer replication independent of the storage platform.

Where these conditions apply, mirroring should be used, and the platform sizing has to account for the additional segment, storage, and network overhead it brings. This document does not size for that case; it focuses on the mirrorless baseline established above.

## Section Summary

The two topologies differ less in the durability they provide than in how they restore availability after a failure and in what they cost to run.

| Consideration | Mirrored Greenplum | Mirrorless Greenplum on vSAN |
| :---- | :---- | :---- |
| Data durability | Greenplum mirror copy, plus vSAN redundancy if on vSAN | vSAN storage redundancy |
| Segment failover after host loss | Automatic in-database failover to mirror, seconds | vSphere HA restarts VMs, then segment recovery; platform-driven window |
| Segment footprint | Roughly doubled by mirrors | Primaries only |
| Ongoing overhead | Continuous WAL replication between segments | None at the database segment layer |
| Operational model | Manage primary-mirror roles and mirror placement | Simpler; no mirror role management |
| Coordinator protection | Standby coordinator | Standby coordinator (unchanged) |
| Best fit | Tight-RTO workloads, or storage without its own redundancy | Analytical and batch workloads on vSphere with vSAN |

With the mirrorless baseline established here, the following sections define how it is realized on the platform: the vSphere cluster and compute design, including how vSphere HA and DRS deliver the recovery behavior described above; the vSAN storage design that provides the durability this topology depends on; and the network design that carries the interconnect traffic.
