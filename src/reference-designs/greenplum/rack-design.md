# Rack Design for Greenplum Clusters

This section describes rack-level deployment models for Greenplum on vSphere, focusing on performance, availability, and operational predictability. Two designs are presented, aligned to different availability requirements. Both make concrete, at the rack level, the placement and capacity rules established in the [vSphere HA Configuration Recommendations](./vsphere-cluster-design.md#vsphere-ha-configuration-recommendations) and [VM Placement and Anti-Affinity Rules](./vsphere-cluster-design.md#vm-placement-and-anti-affinity-rules) sections.

## Design 1 - Single Rack Greenplum (Recommended Baseline)

In this design the entire Greenplum cluster sits in one rack, optimized for low latency, predictable performance, and simple operations. Availability is provided at the host and storage layers, and a rack-level failure is handled through disaster recovery rather than in-cluster.

This is the default and recommended design for most Greenplum deployments. It suits environments where performance consistency is the primary requirement, where a rack-level failure is treated as a rare but catastrophic event, and where recovery from such a failure is handled outside the primary cluster. The rack is treated as a single availability zone and failure domain, and a DR strategy handles its loss.

**Rack and host design.** All ESXi hosts hosting Greenplum are in a single rack. Each host has dual power supplies, redundant top-of-rack connectivity, and NUMA-aligned CPU and memory. Network connectivity follows the 4 or 6-uplink design in [Virtual Distributed Switch (vDS) Design](./vds-design.md#virtual-distributed-switch-vds-design) rather than a simple dual-uplink layout, since the interconnect and vSAN separation defined there is what protects motion and storage traffic.

**Coordinator placement.** The primary and standby coordinators sit on different ESXi hosts within the rack, per the anti-affinity rule in [VM Placement and Anti-Affinity Rules](./vsphere-cluster-design.md#vm-placement-and-anti-affinity-rules). Both coordinators are in the same rack in this design, which is accepted because a full rack loss is a DR event, not an in-cluster recovery.

**Host-failure capacity.** vSphere HA is configured per [vSphere HA Configuration Recommendations](./vsphere-cluster-design.md#vsphere-ha-configuration-recommendations), with the failure tolerance matched to both the host count and the vSAN FTT policy.   
A production cluster of six or more hosts runs N+2 admission control paired with FTT=2 (RAID-6) storage, so that compute and storage are designed to survive the same two failures; a smaller cluster runs N+1 paired with FTT=1. The reserved capacity follows from the admission-control policy in [vSphere HA Configuration Recommendations](./vsphere-cluster-design.md#vsphere-ha-configuration-recommendations) rather than a fixed percentage.   
DRS runs in Partially Automated mode to preserve NUMA locality. Together these let a failed host be absorbed by the survivors, allow segment VMs to restart without excessive contention, and keep NUMA alignment intact through the expected failure scenarios. Because N+2 and FTT=2 both require the six-host production baseline, this pairing is a property of the production design and not of the POC scale cluster.

**Rack-failure semantics.** A rack failure is treated as an AZ or region failure. Losing the rack means losing all ESXi hosts, vSphere HA cannot recover the workload within the same cluster, and the primary cluster is considered unavailable. Recovery is performed against a secondary Greenplum DR cluster using data replication or restore and defined DR procedures.

This model fits when performance predictability is critical, query latency must be minimized, recovery via DR is acceptable, and business SLAs tolerate short query interruptions during host failures.

## Design 2 - Rack / AZ Failure Resilient Deployment Using vSphere Stretched Cluster

This design is optional and intended only where rack or AZ-level failure tolerance is a hard business requirement. It uses a vSphere stretched cluster with each rack acting as an independent failure domain or availability zone.

Before the mechanics, one Greenplum-specific caution that should drive the decision. A stretched cluster places inter-AZ network latency directly into the interconnect path for any motion operator whose data crosses AZs. As established in [Network Traffic Characteristics](./workload-characteristics.md#network-traffic-characteristics), the interconnect is acutely sensitive to latency variance and jitter, not just average latency, and motion is where query pace is decided. Cross-AZ motion therefore has a materially larger performance impact on Greenplum than the "network hop" framing suggests for general workloads. This is the core reason single-rack is the baseline and stretched is the exception: the stretch buys AZ survivability at a real and query-visible interconnect cost. It should be chosen for availability requirements, never for performance.

**Rack and fault-domain design.** ESXi hosts are split across two racks or AZs. Where the stretched cluster spans sites, the hosts at each site still reside in a single rack. Each host has dual power, redundant top-of-rack connectivity following the [Virtual Distributed Switch (vDS) Design](./vds-design.md#virtual-distributed-switch-vds-design) uplink design, and NUMA-aligned CPU and memory. Each rack or AZ is a vSAN fault domain, and a vSAN witness appliance is deployed in a third location separate from both. This preserves storage quorum and lets compute restart in the surviving AZ if one is lost.

**Coordinator placement across AZs.** The standby coordinator is placed in the opposite AZ from the primary, so that the loss of either AZ leaves a coordinator surviving. This is the rack-level application of the [VM Placement and Anti-Affinity Rules](./vsphere-cluster-design.md#vm-placement-and-anti-affinity-rules) anti-affinity rule and is what lets the coordinator role survive an AZ failure rather than merely a host failure.

**Compute capacity.** The cluster is sized so all Greenplum workloads can run within a single AZ, which reserves roughly 50 percent of CPU and memory. This reservation is intentional and mandatory: it guarantees no overcommit during an AZ failure and predictable performance under failover. The consequence is lower normal-state utilization and reduced hardware efficiency in exchange for AZ survivability.

**vSAN protection in a stretched cluster.** Data is mirrored across the two AZs for site-level protection, and a local protection policy is applied within each AZ on top of that. The two combine multiplicatively, which is what drives the efficiency numbers in [Design Options comparison table](#design-options-comparison-table).   
Setting local protection to FTT=0 maximizes capacity by relying solely on the cross-AZ mirror, though this trade-off should be weighed against the impact on inter-site rebuild traffic during local host failures.

**Rack/AZ-failure semantics.** When an AZ goes down, vSAN quorum is preserved via the witness, vSphere HA restarts the affected VMs in the surviving AZ, the Greenplum segments restart, and FTS recovers the cluster to an operational state. This still involves temporary query failures, and the recovery time depends on segment count. The design is not zero-downtime; it provides infrastructure-level survivability of an AZ loss, not continuous availability through it.

**DR still applies.** Even with a stretched cluster, a separate Greenplum DR cluster in another region is recommended, because the stretch protects against a single AZ loss but not against a region-wide outage or a network partition affecting both AZs. The stretched cluster addresses AZ failure; DR addresses region failure.

## Design Options comparison table

Single-rack delivers maximum performance and simplicity, with rack failure handled through DR. The stretched cluster delivers AZ-level availability at the cost of efficiency, complexity, and interconnect performance.

| Dimension | Design 1, Single Rack/Fault Domain | Design 2 - Stretched Cluster |
| :---- | :---- | :---- |
| Failure domains | 1 | 2 |
| Performance | High | Reduced; cross-AZ motion adds interconnect latency  |
| Compute Efficiency | High | ~50% Usable |
| Storage efficiency (ESA, 6 or more hosts) |  1.25x for FTT=1 RAID-5,  1.5x for FTT=2 RAID-6,  2x for FTT=1 RAID-1 | Site mirror (2x) multiplied by the local policy 2.5x for local FTT=1 RAID-5,  3x for local FTT=2 RAID-6,  4x for local FTT=1 RAID-1 |
| Query Interruption on Rack/AZ failure | Yes | Yes |
| Operational Complexity | Low | High |

**Key Note:** 

* Single-rack deployments provide the highest performance and simplicity for Greenplum workloads, with rack-level failures handled through DR. Stretched clusters provide higher availability at significant cost, complexity, and resource overhead.  
* Stretched storage figures: A stretched cluster mirrors data across both AZs and then applies a local policy within each AZ, so the overhead is the product of the two. Running local FTT=0 within each AZ, as noted in [Design 2 - Rack / AZ Failure Resilient Deployment Using vSphere Stretched Cluster](#design-2-rack-az-failure-resilient-deployment-using-vsphere-stretched-cluster), reduces the stretched multiplier toward the site-mirror factor alone.  
* The choice between these designs must be driven by business availability requirements, not by infrastructure capability alone, and for Greenplum specifically, by whether the workload can accept cross-AZ interconnect latency in exchange for AZ survivability.
