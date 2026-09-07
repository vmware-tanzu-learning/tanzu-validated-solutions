# Tanzu GemFire Locators

A Tanzu GemFire Locator is a lightweight process that provides system coordination. The Locator enables new members, such as servers, other locators, and clients, to discover the existing members of a cluster. The Locator also provides load-balancing information that steers client connections to servers.  
A Locator performs two core functions. A concurrent service running inside the same process handles each function:

- **Peer Locator.** Handles cluster member discovery. The Peer Locator helps new servers and locators find and join the distributed system, and it maintains the membership list and a consistent, shared view of the cluster.

- **Server Locator.** Handles client connection routing. The Server Locator directs clients to the most suitable cache server, typically the one with the least load. This routing enables client-side load balancing and high availability for client-to-server connections.

## <a id="split-brain-protection"></a> Locators and network-partition ("split-brain") protection

Running two or more locators removes the Locator tier as a single point of failure for discovery and coordination. Locator redundancy alone does not prevent a split-brain. GemFire's network-partition detection, not locator redundancy, provides split-brain protection. The `enable-network-partition-detection` property enables this detection by default. Clusters that use partitioned or persistent regions require this detection to be enabled. Under this mechanism, the oldest member acts as the membership coordinator, preferably a Locator. Each member contributes a weight to quorum calculations: a Locator weighs 3, a cache server weighs 10, and the lead server weighs 15. If a single membership-view change causes a loss of 51 percent or more of the total member weight, GemFire declares a network partition. The losing side then shuts down to preserve consistency. Deploying multiple locators and at least three cache servers gives this weighting mechanism enough members to make a correct, deterministic decision.  
For more information, see the [VMware Tanzu GemFire](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-gemfire/10-1/gf/managing-network_partitioning-membership_coordinators_lead_members_and_weighting.html) documentation.

## <a id="locator-recommendations"></a> Recommendations for deploying Locators

- **Minimum of two locators, one per AZ.** This minimum locator count removes the single point of failure for membership and client discovery.

  This deployment also provides the coordinator redundancy on which the partition-detection logic relies.

- **Run locators on separate VMs from cache servers.** Cache servers can experience long garbage-collection pauses under heavy data load.

  Isolating locators from cache servers ensures that such a pause cannot stall the coordinator and trigger cluster-wide membership timeouts.

- **WAN environments.** Locators discover the locators of remote clusters across the WAN. Low, stable latency on these links is important for reliable multi-site discovery and replication.

By acting as the discovery, coordination, and client-routing layer, the Locator forms the foundation of a cluster's connectivity. A well-configured locator topology keeps the distributed system connected, balanced, and resilient as the distributed system scales across zones, regions, and data centers.

