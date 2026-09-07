# Tanzu GemFire WAN and Multi-AZ Deployments

Tanzu GemFire supports flexible deployment topologies to meet a variety of availability, latency and disaster recovery (DR) requirements. Two primary deployment models are commonly used: WAN replication for geographically distributed clusters and Multi-AZ deployments for fault-tolerant clusters within a single region.

## <a id="wan-replication"></a> WAN Replication (Geographical Level)

WAN replication enables Tanzu GemFire clusters located in different geographic regions to exchange data asynchronously.  
Each site runs as an independent GemFire cluster, with its own locators, servers, and regions, and uses Gateway Senders and Gateway Receivers to replicate events between clusters over a wide-area network. Use this model when sites are far enough apart that a single synchronous, or stretched, cluster is impractical. In practice, this means round-trip latency above the single-cluster ceiling described in [Multi-AZ Deployment](#multi-az-deployment) below, commonly tens of milliseconds or more between regions. Because WAN replication is asynchronous, local performance is unaffected by network latency.

Key characteristics:

- Designed for disaster recovery (DR) and cross-region data sharing between geographically distant data centers.

- Replication is asynchronous, ensuring local performance is unaffected by WAN network delay.

- Each site can continue to process transactions independently if WAN connectivity is temporarily lost.

Example:

- A GemFire cluster in London acts as the primary production site, asynchronously replicating region updates to a DR cluster in New York.

- The New York cluster may also replicate back (active–active) or remain in standby (active–passive), depending on business continuity policies.

- If the primary site fails, clients can connect to the secondary cluster to maintain operations with minimal downtime.

Design considerations:

- WAN links should have sufficient bandwidth and packet reliability to handle replication traffic.

- Use Gateway Sender queues with persistence enabled to prevent event loss during network disruptions.

- Use event conflation to optimize queue efficiency for high-throughput applications.

## <a id="multi-az-deployment"></a> Multi-AZ Deployment (Local Cluster Level)

A Multi-AZ deployment provides fault isolation and high availability within a single region or vSphere environment. Rather than separate clusters, all members belong to one logical cluster that spans multiple availability zones (AZs). Choose a Multi-AZ deployment when inter-zone latency is very low, because low latency allows synchronous redundancy without a performance penalty.

Key characteristics:

- Provides intra-region fault tolerance by distributing members across independent fault domains.

- Maintains synchronous data redundancy across zones for partitioned regions.

- Removes the need for separate WAN replication infrastructure within a region.

- Keeps the cluster available even if an entire zone fails.

- Aligns with cloud and on-prem architectures where multiple AZs share one region.

Example:

- A cluster is deployed across three zones in one region (Zone A, Zone B, Zone C).

- Each partitioned region is configured with a redundancy level of 1.

- With the `redundancy-zone` configured correctly, GemFire places primary and redundant copies in different zones.

  See [Configuring Redundancy Zones](#redundancy-zones).

- If one zone fails, the cluster continues operating from replicas in the surviving zones.

Design considerations:

- Keep RTT latency under 2 ms between AZs for synchronous performance, with a hard ceiling around 5 ms.

  Members separated by more than roughly 5 ms of latency risk communication deadlocks.

- Keep members of a single, stretched, cluster within a low-latency envelope.

  A single cluster requires round-trip latency below 5 ms between members. Beyond roughly 5 ms, GemFire communication deadlocks can occur. If separation exceeds this envelope, use WAN replication with separate clusters rather than one stretched cluster.

- Combine redundancy zones with vSphere anti-affinity rules to keep redundant members off the same ESXi host.

- Use consistent zone naming across the environment to simplify automation and monitoring.

- Validate failover regularly by simulating zone-level outages.

## <a id="redundancy-zones"></a> Configuring Redundancy Zones

The `redundancy-zone` property explicitly maps a member to a physical zone or fault domain, ensuring that redundant copies of a partitioned region's data are placed in separate zones. This mapping protects against the simultaneous loss of both the primary and backup copies.

Set the property in each member's `gemfire.properties`:

```
# Assign this GemFire member to a specific Availability Zone or fault domain 
redundancy-zone=zone-a
```

When multiple zones are defined, GemFire automatically distributes redundant copies across those zones during region creation and data rebalancing.  
Benefits:

- Improves resiliency by isolating redundancy across distinct infrastructure domains.

- Provides deterministic replica placement for predictable failover.

- Complements vSphere DRS anti-affinity rules for host-level fault isolation.

Reference: [Set Redundancy Zones for Partitioned Regions](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-gemfire/10-3/gf/developing-partitioned_regions-set_redundancy_zones.html)


