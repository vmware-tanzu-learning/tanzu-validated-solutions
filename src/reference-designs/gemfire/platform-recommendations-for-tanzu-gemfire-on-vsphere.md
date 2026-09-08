# Platform Recommendations for Tanzu GemFire on vSphere

This section provides platform-level recommendations for running Tanzu GemFire on vSphere, covering BIOS, virtual machine configuration, high availability, storage, and performance tuning.

## <a id="bios-settings"></a> BIOS Settings

For latency-sensitive, data-intensive workloads such as **Tanzu GemFire cache servers and locators**, ESXi host BIOS settings play a critical role in ensuring deterministic CPU behavior and minimizing jitter.

| BIOS Category | Recommended Setting | Purpose |
| ----- | ----- | ----- |
| Power Management Mode | Maximum Performance / High Performance | Ensures CPUs run at the highest consistent frequency; disables OS-directed power saving. |
| Turbo Boost | Enabled | Allows CPU cores to opportunistically use higher frequencies for short bursts, improving throughput. |
| C-States | Disabled (C0 Only) | Prevents deep sleep states that introduce wake-latency spikes. |
| P-States / Frequency Scaling | Disabled | Keeps frequency fixed to avoid per-thread latency variance. |
| Node Interleaving | Disabled | Preserves NUMA locality; required for predictable memory access latency. |
| Hyper-Threading | Enabled | GEMFire benefits from additional logical threads for serialization, messaging, and GC activity. |

Settings may vary slightly depending on your hardware make and model. Use the settings above or equivalents as needed.

## <a id="vm-configuration"></a> Virtual Machine Configuration Guidelines (Tanzu GemFire Cache Servers & Locators)

The following configurations apply to GemFire VMs running in a vSphere environment. The following sections describe key points for performance tuning and configuration. For more information, see the [VMware Tanzu GemFire](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-gemfire/10-2/gf/managing-monitor_tune-chapter_overview.html) documentation.

### <a id="cpu-numa"></a> CPU and NUMA Configuration

Efficient CPU allocation is critical for stable and predictable Tanzu GemFire performance.

- Enable hyper-threading and avoid CPU overcommitment to maintain consistent latency.

- Allocate dedicated CPU resources, and ensure that the number of vCPUs assigned aligns with the physical cores available.

- Follow the NUMA best practices described in the following section.

### <a id="vm-cpu-reservations"></a> Virtual Machine CPU Reservations

To minimize jitter:

- Assign 100% CPU reservation for GemFire cache servers.

- Avoid CPU overcommitment on hosts that run GemFire VMs.

### <a id="vcpu-sizing"></a> vCPU Sizing

- Allocate a minimum of 4 vCPUs per GemFire VM.

  This minimum provides ample CPU cycles for the garbage collector, with the remainder for user transactions. The official general floor is two vCPUs, but four is the recommended minimum for a server running in one JVM.

- You may use larger VMs, from 8 to 16 vCPUs, for higher-throughput clusters, as long as the VM fits entirely inside one NUMA node.

  See [NUMA and vNUMA Considerations for GemFireVMs](#numa-vnuma) in this document for more information.

- Avoid unnecessary oversizing to reduce CPU Ready time and scheduling delays.

### <a id="cpu-steal-time"></a> CPU Steal Time Monitoring

To monitor CPU scheduling delays caused by hypervisor contention, enable steal-time tracking in the GemFire VM configuration.

Steal-time tracking helps detect situations where the guest OS is ready to run but the physical CPU is unavailable because of oversubscription or resource contention from other VMs on the host.

### <a id="steal-time-config"></a> Configuration

```
stealclock.enable = "TRUE"
```

When this parameter is set, Tanzu GemFire records CPU steal time within its metrics, allowing operators to identify and mitigate host contention.

### <a id="memory-configuration"></a> Memory Configuration

Efficient memory allocation is critical for stable and predictable Tanzu GemFire performance.

- Reserve full memory for each GemFire virtual machine to prevent ballooning or swapping.

  Once reserved, ESXi locks this memory, and ESXi cannot reclaim it.

- Avoid memory overcommitment on hosts running GemFire workloads.

- Follow the NUMA best practices described in the sections below.

### <a id="vm-memory-reservation"></a> Virtual Machine Memory Reservation

You must provide full memory reservation for GemFire components:

- Configure a **100% memory reservation** for every GemFire VM.

- ESXi locks reserved memory during VM power-on, preventing ballooning, swapping, and host-level memory reclamation.

- Memory reservation ensures stable latency and consistent GC performance.

### <a id="avoid-overcommitment"></a> Avoid Memory Overcommitment

- **Do not** overcommit memory on ESXi hosts running GemFire clusters.

- Overcommitment causes unpredictable performance and GC pauses.

### <a id="large-pages"></a> Use of Large Pages

Enable Java Large Pages (Huge Pages) inside the guest OS:

```
-XX:+UseLargePages
```

Large pages reduce TLB misses and improve garbage-collection efficiency for large heaps. Large pages require a supporting operating-system limit. Raise the locked-memory limit, shown by `ulimit -l` as "max locked memory", to at least the total heap memory that the member locks. The default is typically 32 KB or 64 KB, which is far too low. Unless you raise this limit, large pages will not engage.

### <a id="gc-selection"></a> Garbage Collector Selection and Tuning

The choice of garbage collector directly affects pause times. A long pause can make a data node unresponsive long enough that the cluster suspects the node and expels it, a process governed by `member-timeout`. Proper heap sizing together with the recommended collector is the primary defense against pause-induced membership loss.

Although G1GC is the Java default, VMware recommends the Z Garbage Collector (ZGC) for most applications on JDK 17, and Generational ZGC on JDK 21 and later:

| JDK | Java Default | Recommended for Gemfire |
| ----- | ----- | ----- |
| 17 | G1GC | ZGC |
| 21 | G1GC | Generational ZGC |
| 25 | G1GC | Generational ZGC |

There is an important heap-size trade-off. On a 64-bit JVM with a heap smaller than 32 GB, switching from G1GC to ZGC can increase the cache's heap usage by up to 80%. The exact impact depends on the nature of the cached data. On a heap of 32 GB or larger, switching to ZGC does not increase heap usage. ZGC is therefore a clear choice for large heaps. For smaller heaps, size for the additional overhead or evaluate retaining G1GC.

If you retain G1GC, for example for storage efficiency on smaller heaps, start mixed collections early with `-XX:InitiatingHeapOccupancyPercent=25`. Heaps under 32 GB also benefit from `-XX:+UseCompressedOops`, which the JVM applies automatically when applicable, but which is not available with ZGC or with heaps of 32 GB or larger. Using G1GC together with GemFire heap LRU eviction requires additional testing and tuning, primarily to avoid humongous-object penalties.



### <a id="low-latency-settings"></a> Low-Latency Workload Settings (vSphere Level)

Apply the following on the GemFire VMs:

- Use **VMXNET3** network adapters.

- Consider disabling **interrupt coalescing** for ultra-low-latency deployments.

- Enable **High Performance power policy** in ESXi: Host Client -> Manage -> Hardware -> Power Management -> High Performance.

- Disable unnecessary guest OS background services to reduce jitter.

### <a id="optional-advanced-ops"></a> Optional (Advanced Operations Only)

- You may use CPU Affinity or NUMA Node Pinning to eliminate cross-node scheduling, but apply this only when strictly required and tested.



### <a id="os-java-requirements"></a> Operating System & Java Runtime Requirements

Supported Java versions for Tanzu GemFire 10.3. JDK 17 is the minimum and baseline version; the supported set is JDK 17, 21, and 25.

| JDK | Recommended Version | Minimum Version |
| ----- | ----- | ----- |
| 17 | latest | 17 |
| 21 | latest | 21 |
| 25 | latest | 25 |

#### <a id="virtual-threads-support"></a> Java virtual threads support

Tanzu GemFire runs on JDK 21 and JDK 25 but does not support virtual threads on those versions.

### <a id="systemd-prerequisite"></a> systemd Prerequisite

Configure systemd on Linux. GemFire requires the udev device manager, which is part of systemd, and which maintains the device nodes under /dev. This configuration is a baseline requirement. It is also the mechanism that GemFire uses for automatic member restart, as described under vSphere High Availability, Automatic Restart, and systemd.

### <a id="os-resource-limits"></a> Guest OS Level Resource Limits

To support high concurrency and I/O workloads, configure appropriate user and process limits on Unix/Linux hosts in `/etc/security/limits.conf`: 

| Parameter | Recommended Soft Limit | Recommended Hard Limit |
| ----- | ----- | ----- |
| File Descriptors (nofile) | 8,192 | 81,920 |
| Number of Processes (nproc) | 501,408 | Unlimited |

These limits prevent resource contention for GemFire threads, connections, and file handles under high concurrency.

### <a id="jvm-recommendation"></a> JVM Recommendation per Tanzu GemFire Virtual Machines

Each Tanzu GemFire cache server or locator should run as a single JVM instance inside a dedicated virtual machine. A strict **1:1:1 mapping of VM to JVM to GemFire member** provides the following benefits:

- Eliminates resource contention between multiple JVMs.

- Simplifies CPU, memory, GC behavior, and NUMA tuning.

- Improves fault isolation, so the failure of one JVM affects only one GemFire member.

- Enhances operational workflows such as rolling upgrades, monitoring, and failure recovery.

If more capacity is needed, increase the JVM heap rather than adding a second JVM to the same VM. If increasing the heap is not an option, place the second JVM on a separate, newly created VM to preserve the 1:1:1 ratio and promote horizontal scalability.

### <a id="network-time-sync"></a> Network & Time Synchronization Requirements

This section describes network adapter configuration, TCP tuning, NIC interrupt settings, and time synchronization requirements for Tanzu GemFire VMs deployed in vSphere.

- Ensure consistent time across all GemFire nodes using NTP or chrony. Consistent time is critical for log correlation, WAN replication event ordering, and cluster membership.

- Validate hostname resolution and /etc/hosts entries on every VM.

- Ensure that the TCP/IP stack is fully enabled and configured for throughput and low latency.

### <a id="physical-nic"></a> Physical NIC Recommendations (ESXi Host Level)

For latency-sensitive GemFire workloads, consider tuning physical NIC interrupt settings. Disabling interrupt coalescing, optionally, for ultra-low latency, reduces receive interrupt delay and can improve round-trip latency:

```
ethtool -C vmnicX rx-usecs 0 rx-frames 1 rx-usecs-irq 0 rx-frames-irq 0
```

Replace vmnicX with your NIC name, which you can verify using `esxcli network nic list`. If you restart the ESXi host, you must reapply this configuration.

This type of tuning benefits Tanzu GemFire workloads, but it can negatively impact other non-GemFire workloads that are memory-throughput-bound rather than latency-sensitive. This tuning can also defeat the benefits of Large Receive Offload (LRO), because some physical NICs, such as Intel 10GbE NICs, automatically deactivate LRO when you deactivate interrupt coalescing. For more information, see [Understanding TCP Segmentation Offload (TSO) and Large Receive Offload (LRO) in the vSphere environment](https://knowledge.broadcom.com/external/article?articleNumber=318877).

### <a id="virtual-nic"></a> Virtual NIC Configuration (VM Level)

Use VMXNET3 for all GemFire VMs.

- VMXNET3 provides high throughput, low latency, and adaptive interrupt coalescing.

- The VMXNET3 adapter is the recommended adapter for all GemFire Cache Servers and Locators.

### <a id="disable-interrupt-coalescing"></a> Disable Virtual Interrupt Coalescing (For Ultra-Low Latency)

- You can disable virtual interrupt coalescing through the VM's `.vmx` configuration or through the vSphere API.

- VMware recommends disabling virtual interrupt coalescing only for extremely latency-sensitive deployments where you must minimize jitter.

### <a id="tcp-syn-cookie"></a> TCP SYN Cookie Configuration (Guest OS)

Many Linux distributions enable SYN cookies by default. SYN cookies are not compatible with stable, busy GemFire clusters. Normal GemFire traffic incorrectly triggers the SYN cookie protection, which severely limits bandwidth and new-connection rates. This problem is especially disruptive during:

- `gfsh` connect

- Locator handshake

- Heavy client connection bursts

- WAN gateway connections

### <a id="disable-syn-cookies"></a> Disable SYN cookies (Recommended for GemFire Clusters)

```
sudo vi /etc/sysctl.conf
  net.ipv4.tcp_syncookies = 0
sudo sysctl -p
```

### <a id="security-considerations"></a> Security considerations

To maintain protection against denial-of-service attacks, deploy GemFire clusters behind firewalls, load balancers, or network intrusion prevention systems (NIPS) instead of relying on SYN cookies.

### <a id="throughput-latency-config"></a> High throughput and latency configurations (Guest OS)

GemFire systems often handle extremely high transaction volumes and move large amounts of traffic through the network. Maximizing network throughput is therefore a primary design goal. The following options assume TCP over IPv4:

- Increasing TCP's initial congestion window enables TCP to transfer more data in the first round trip and accelerates window growth. This increase is especially important for bursty, short-lived connections.

- Increasing the size of the transmit queue can also help TCP throughput.

These two settings may require enabling the rc-local.service or creating a custom systemd service unit:

```
sudo vi /etc/rc.local
  defrt='ip route | grep "^default" | head -1'
  ip route change $defrt initcwnd 10
  /sbin/ifconfig eth0 txqueuelen 10000
```

Additional guest OS TCP tuning:

- Disabling TCP Slow-Start After Idle improves the performance of long-lived TCP connections that transfer data in bursts.

- Enabling Window Scaling (RFC 1323) increases the maximum receive window size and enables high-latency connections to achieve better throughput.

- Enabling TCP Low Latency tells the operating system to sacrifice throughput for lower latency. For latency-sensitive workloads like GemFire, this tradeoff is acceptable and can improve performance.

- Enabling TCP Fast Open enables the client to send application data in the initial SYN packet in certain situations. TFO is a newer optimization that requires support on both clients and servers, and it may not be available on all operating systems.

```
sudo vi /etc/sysctl.conf
  net.ipv4.tcp_slow_start_after_idle = 0
  net.ipv4.tcp_window_scaling = 1
  net.ipv4.tcp_low_latency = 1
  net.ipv4.tcp_fastopen = 1
sudo sysctl -p
```

### <a id="time-sync-requirements"></a> Time Synchronization Requirements

Accurate and consistent time across all GemFire members is mandatory. Use NTP or an equivalent time service on all GemFire VMs to ensure:

- Correct event sequencing across logs

- Predictable WAN replication ordering

- Consistent metric aggregation

- Proper functioning of distributed algorithms

### <a id="vsphere-recommended-practices"></a> Recommended Practices

- Enable NTP at both the ESXi host and VM operating system levels.

- Ensure all cluster nodes point to the same NTP server hierarchy.

- Avoid mixing different time sources, for example ESXi-based time sync combined with guest NTP.

### <a id="name-resolution"></a> Name Resolution & Host Configuration

To avoid locator or management endpoint failures:

- Ensure that DNS or `/etc/hosts` entries are accurate and consistent.

- Map hostnames correctly to the IP addresses used in the GemFire cluster configuration.

- Misconfigured host entries can break `gfsh` connectivity and management APIs.

### <a id="numa-vnuma"></a> NUMA and vNUMA Considerations for Tanzu GemFire VMs

GemFire cache servers are memory-intensive and latency-sensitive JVM processes. To avoid cross-NUMA memory access penalties, size each GemFire VM so that all of its vCPUs and memory fit within a single physical NUMA node of the ESXi host.

Sizing VMs within NUMA boundaries ensures:

- Consistent low-latency data access

- Stable Gateway Sender queue processing

- Predictable garbage-collection behavior for large JVM heaps

- No remote memory hops across NUMA interconnects

vSphere uses NUMA-aware scheduling to ensure that virtual machines receive CPU and memory resources from the same physical NUMA node whenever possible. The following sections describe vSphere behavior under two common sizing scenarios.

### <a id="numa-fits-node"></a> When a VM has fewer vCPUs and less memory than a single NUMA node provides

If the VM's CPU and memory footprint fits entirely inside one physical NUMA node, vSphere keeps the VM bound to that node. This configuration is the ideal configuration for GemFire. Key behaviors:

- Single NUMA placement: ESXi places the VM entirely on one NUMA node, so that node's local memory controller serves both CPU scheduling and memory allocations.

- No vNUMA exposure: because the VM does not need to span nodes, ESXi does not expose any vNUMA topology to the guest OS.

- Memory allocation locality: vSphere allocates all guest physical memory from the local memory of that NUMA node, providing optimal latency and cache locality.

- No manual NUMA configuration needed: ESXi automatically guarantees CPU and memory locality with no tuning required.

Results:

This scenario provides the best and most predictable performance. For GemFire locators and servers sized within this boundary, for example 4 to 16 vCPUs and 32 to 128 GB RAM depending on the host, cross-node memory access never causes latency spikes.

### <a id="numa-exceeds-node"></a> When a VM's vCPU count or memory requirement exceeds a single NUMA node

If a VM's CPU or memory usage cannot fit within a single physical NUMA node, ESXi must span the VM across multiple NUMA nodes, and vSphere automatically exposes a virtual NUMA (vNUMA) topology to the guest OS. Two independent triggers can cause NUMA spanning:

- vCPU count exceeds the physical cores in a single NUMA node. For example, with a NUMA node of 20 physical cores, a VM configured with 24 vCPUs spans nodes.

- Memory reservation exceeds the memory capacity of a single NUMA node. For example, with a NUMA node of 512 GB, a VM configured with 600 GB RAM spans nodes even if its vCPU count is below the per-node core threshold.

Key behaviors when the VM spans nodes:

- Multiple vNUMA nodes presented to the guest: ESXi generates a vNUMA topology that reflects how the VM is split across physical nodes. For example, a 24-vCPU VM may appear as two vNUMA nodes with 12 vCPUs each.

- Topology-aware scheduling by the guest OS: the guest OS recognizes the NUMA boundaries and places processes and threads on the appropriate vNUMA node, improving CPU-to-memory locality and reducing cross-node traffic.

- NUMA-aware memory allocation: ESXi sources memory allocations inside a vNUMA node from its corresponding physical NUMA node, keeping memory access latency low for the JVM and GemFire workload.

- Remote memory access still occurs: threads may still access memory belonging to another vNUMA node during uneven data access or garbage-collection cycles, which introduces additional latency and interconnect traffic.

- Avoid manual vNUMA overrides: ESXi's automatic vNUMA creation aligns with the hardware topology. Manual overrides typically lead to misalignment, increased remote memory access, and degraded performance.

Results:

This model is acceptable for large GemFire nodes that genuinely require high CPU or memory, but performance may become less predictable. Remaining within a single physical NUMA boundary is always preferred where possible.

### <a id="numa-sizing"></a> NUMA-Aware Sizing and Placement Recommendations for Tanzu GemFire Server Nodes

To achieve predictable low-latency performance, size GemFire VMs to maintain NUMA locality:

- Deploy GemFire VMs so that their total vCPU count and memory footprint fit entirely within a single physical NUMA node of the ESXi host.

- ESXi automatically places these VMs on a single NUMA node to ensure memory locality and minimize cross-node access penalties.

- When you size GemFire VMs below this threshold, for example 8 to 16 vCPUs on hosts with 20 or more cores per NUMA node, and 256 GB on hosts with 512 GB per NUMA node, vNUMA exposure is unnecessary, and ESXi schedules the VM entirely within one NUMA node.

- No manual NUMA configuration is needed for smaller VMs, and overriding NUMA placement is discouraged.

- If a VM must span NUMA nodes, at large sizes of 20 or more vCPUs, ESXi automatically generates a corresponding vNUMA topology so that the guest OS and GemFire can schedule threads and memory regions optimally.

| Scenario | vSphere Behavior | Guest OS View | Memory Behavior | Recommendation |
| ----- | ----- | ----- | ----- | ----- |
| VM fits within a single NUMA node (vCPUs less than physical cores per node, and RAM less than node memory capacity) | VM is pinned to one NUMA node automatically | Shows one NUMA node | All memory allocated locally | Preferred for GemFire. No manual config needed. |
| VM exceeds NUMA node CPU or memory limits | VM is split across multiple NUMA nodes and vNUMA is exposed | Multiple vNUMA nodes | Memory allocated per vNUMA node; cross-node access possible | Acceptable for large nodes; avoid unless necessary. |

## <a id="vmotion-drs-snapshots"></a> vMotion, DRS and Snapshots

vSphere features such as vMotion, DRS and snapshots can introduce instability or latency spikes if not managed carefully.

- Avoid automatic vMotion or DRS-triggered migrations for GemFire members. Set DRS to manual mode to prevent unplanned moves that affect transaction performance.

- Schedule vMotion migrations during periods of low activity or planned maintenance windows, preferably over 10 GbE or higher links. Expect a temporary drop in read and write performance during the migration. Performance resumes once the migration completes.

- Disable vSphere snapshots for all GemFire VMs. Snapshot operations freeze the VM and can cause the cluster to mark GemFire members unresponsive and force them out of the cluster, and GemFire artifacts do not show this cause.

- For backups, use GemFire persistence or external storage replication mechanisms instead of vSphere snapshots.

- Best practice: treat GemFire nodes as stateful components, and avoid any operation, such as cloning or snapshotting, that interrupts runtime memory state.


## <a id="vsphere-ha"></a> vSphere High Availability (HA), Automatic Restart, and systemd

This section covers the official recommendation for using vSphere HA with GemFire, along with the trade-offs if you choose to enable it.

### <a id="ha-recommendation"></a> Official Recommendation

The Tanzu GemFire 10.3 performance guidance is explicit: deactivate vSphere High Availability (HA) on GemFire virtual machines. If the GemFire cluster runs on a dedicated cluster, deactivate HA across that cluster. If the cluster runs on a shared cluster, exclude the GemFire VMs from vSphere HA. In addition, define VM-to-VM anti-affinity rules so that the cluster never places members holding redundant copies of the same data on the same ESXi host.

The rationale is that vSphere HA is an infrastructure-level mechanism with no knowledge of GemFire. vSphere HA does not understand redundant-copies settings, region types, that is, partitioned versus replicated and persistent versus non-persistent, the peer-to-peer distribution system and member roles, network-partition detection, or the internal recovery process, that is, secondary promotion, bucket rebalancing, and redundancy restoration. GemFire already provides application-level high availability through redundant copies. As a result, an HA-triggered VM restart can collide with GemFire's own recovery, produce a second rebalance, and introduce latency spikes. A restarted empty member also adds no data value if redundancy has already been restored on surviving members. For most deployments, the lowest-risk posture is therefore to exclude GemFire VMs from vSphere HA and rely on GemFire redundancy, persistence, and anti-affinity for availability.

### <a id="using-vsphere-ha"></a> Using vSphere HA (Supported, With Caveats)

Enabling vSphere HA for GemFire VMs is a deliberate trade-off rather than the default recommendation. Enabling vSphere HA can reduce mean time to repair for whole VM or host loss by rapidly restarting a failed VM on a surviving host, but this restart only helps if you configure the cluster to tolerate and coordinate it. If your operational goal is infrastructure-level VM restart in addition to GemFire's own redundancy, apply the following GemFire-side configuration:

- Set `redundant-copies` greater than 0 on all partitioned regions, so that a surviving secondary is promoted to primary on failure and no data is lost for that portion of the dataset.

- Configure region persistence, for example persistent-partition or persistent-replicate, so that a restarted member reloads its data from local disk instead of re-synchronizing everything over the network. This shortens the window during which the cluster runs with reduced redundancy and lowers the network load of rejoining.

- Keep the VM-to-VM anti-affinity rules, so that a single host loss can never take both the primary and its redundant copy at once.

#### Restarting GemFire Services After a Reboot (systemd)

Because systemd is already a GemFire prerequisite, running each member as a systemd service is the natural mechanism for restarting GemFire automatically after any VM reboot, whether vSphere HA or a planned maintenance action triggers that reboot. Adopt this practice even when you deactivate HA, so that a planned or accidental VM reboot brings the member back without manual intervention. The following recommendations describe what to do rather than how:

- Run one member per VM as one systemd service, consistent with the 1:1:1 model. This model keeps fault isolation and restart behavior simple.

- Order the service to start only after networking and time synchronization are available.

  Correct time, from NTP or chrony, and correct name resolution are prerequisites for cluster membership, WAN event ordering, and log correlation. A member that starts before these services are ready can join incorrectly or produce misleading timestamps.

- Bound the restart policy. Allow automatic restart on failure, but cap the number of attempts within a time window and use a restart delay, so that a member which cannot start cleanly does not enter a tight crash loop that repeatedly disturbs the surviving cluster.

- Keep the member's working directory and pid file stable across restarts, so that log files roll cleanly, with older logs renamed on restart, rather than colliding, and so that status and stop operations continue to work.

#### Coordinating GemFire Recovery Timing With the HA Restart Window

The central design point is making the surviving cluster wait long enough for an HA-restarted member to return before the cluster rebuilds redundancy, so that the cluster does not perform a full recovery and then a second rebalance when the member rejoins. Three GemFire settings govern this sequence.

- `member-timeout`, in `gemfire.properties`, default 5000 ms, determines how quickly the cluster suspects and then evicts an unresponsive member. This setting is the first timer in the sequence. Do not set `member-timeout` so low that a normal garbage-collection pause or a vMotion stun triggers a false eviction. `member-timeout` must comfortably exceed expected pauses. This requirement is also why the garbage-collector recommendation matters, since a long pause combined with a low `member-timeout` causes avoidable evictions.

- `recovery-delay`, a partitioned-region attribute with a default of -1, meaning no automatic redundancy recovery on member departure, determines how long the cluster waits after detecting a member's departure before restoring redundancy on the remaining members. To have the cluster wait for an HA-restarted member to return, set `recovery-delay` to at least the expected time for HA to detect the failure, restart the VM, boot the guest, and start the GemFire member. Within that window, the cluster does not promote or create new secondaries, so when the member returns there is no rebalance storm. The trade-off is that the cluster runs at reduced redundancy during that window, which is a risk only if a second failure occurs before the member returns.

- `startup-recovery-delay`, default 0, meaning immediate recovery when a member joins, determines how quickly the cluster restores buckets to the returning member once it rejoins. Keeping this setting low re-absorbs the member promptly. Raising it lets you control when the rejoin rebalance runs.

In combination, `member-timeout` decides how fast the cluster notices a loss, `recovery-delay` decides how long the cluster waits before acting, and persistence plus `startup-recovery-delay` decide how cheaply the returning member rejoins. Set `recovery-delay` from your measured HA-detection-plus-boot-plus-startup time and your tolerance for a temporary reduction in redundancy.

One caution is specific to HA VM Monitoring. Beyond restarting a VM after host loss, vSphere HA VM Monitoring can restart a VM whose guest heartbeat fails. VM Monitoring could restart a member that is alive but briefly unresponsive, for example during a long GC pause, at the same moment GemFire's own failure detection is acting, producing conflicting recovery. If you enable HA, set VM Monitoring sensitivity conservatively, and ensure that the HA and `member-timeout` timings do not work against each other.

#### Risks and Operational Overhead

Enabling vSphere HA for infrastructure-level restart introduces specific risks and configuration overhead that you must own. Excluding GemFire VMs from HA avoids all of these risks, because exclusion leaves a single recovery authority.

Risks to account for:

- Cascading double-recovery. If the VM restart time exceeds a positive `recovery-delay`, the surviving nodes begin redundancy recovery by promoting secondary buckets and creating new redundant copies. When the failed VM eventually restarts and rejoins, a second recovery and rebalance occurs as the cluster sheds the now-excess copies, re-elects primaries, and reloads the returning member's data. This second event is a full recovery-and-rebalance rather than an incremental redistribution, so the latency impact on latency-sensitive applications is effectively doubled. This risk is specific to setting `recovery-delay` to a positive value shorter than the real restart time, rather than to the feature generally. The default of -1 performs no automatic recovery on departure.

- Reduced-redundancy window. A longer `recovery-delay` avoids the double event but leaves the cluster exposed to a coincident second failure for the duration of the window.

- VM Monitoring false restart. HA VM Monitoring can restart a VM whose guest heartbeat fails, so a member that is alive but briefly unresponsive, for example during a long GC pause, can be restarted at the same moment GemFire's own failure detection is acting, producing conflicting recovery.

- Premature detection. An aggressive `member-timeout` can declare a loss during a transient stall, such as a GC pause or a vMotion stun, starting the recovery clock for a member that never actually left.

### <a id="ha-config-overhead"></a> Configuration overhead you take on when HA is enabled

- Set `redundant-copies` greater than 0 on all partitioned regions, so that a surviving secondary is promoted on failure with no data loss.

- Configure region persistence, so that the returning member reloads from local disk in seconds to minutes rather than re-synchronizing over the network. This behavior is what makes a generous `recovery-delay` safe rather than reckless, because it shortens the practical reduced-redundancy exposure.

- Set `recovery-delay` from a measured restart budget, not a guess. Time the real worst case in your environment, including HA failure detection, VM power-on, guest boot, systemd service start, JVM warm-up, and persistence reload. Take the upper end, and add margin, so that the surviving nodes never begin the first recovery.

- Keep `member-timeout` comfortably above expected pause times to prevent premature detection. This is also why the ZGC or Generational ZGC recommendation matters.

- Run each member as a bounded systemd service, ordered after networking and time synchronization.

- Set HA VM Monitoring sensitivity conservatively so that it does not fight GemFire's own failure detection.

- Monitor redundancy state so that an operator can see when the cluster is in the exposed window and when the cluster has fully recovered. Run any deliberate rebalance in a controlled, off-peak window rather than letting cascading recovery activity land during business hours.

### <a id="summary-recommendation"></a> Summary Recommendation

The product-default and lowest-risk posture is to exclude GemFire VMs from vSphere HA and rely on GemFire redundant-copies, region persistence, and VM-to-VM anti-affinity, using systemd to restart members automatically after planned VM reboots.   
If HA is enabled for infrastructure-level restart, retain redundancy, persistence, and anti-affinity, run each member under systemd, and set `recovery-delay` to span the measured restart window, accepting the risks and operational overhead above as the trade-off.

## <a id="storage-configuration"></a> Storage Configuration

For optimal I/O performance, follow these storage best practices:

- Use the PVSCSI adapter for all GemFire VMs handling persistence or write-heavy workloads.

- Provision GemFire VMDK files as eagerzeroedthick. This provisioning avoids lazy zeroing on first write, removing a first-touch latency penalty that is significant for persistence and write-heavy members.

- Align disk partitions at both the VMFS and guest OS levels.

- Use separate VMDKs for persistence files, application binaries, and logs and temporary data.

- Map a dedicated LUN to each VMDK where possible.

- In Linux guests, configure the NOOP I/O scheduler instead of CFQ to minimize scheduling overhead. For more information, see the [Performance Tuning for Latency-Sensitive Workloads on VMware vSphere 8 White Paper](https://www.vmware.com/docs/perf-latency-tuning-vsphere8).



## <a id="performance-tuning"></a> Performance Tuning for Tanzu GemFire on VMware vSphere

The following table provides a high-level overview of the best configurations for hosting GemFire instances on the VCF Platform. For more information, see the [VMware Tanzu GemFire](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-gemfire/10-3/gf/managing-monitor_tune-chapter_overview.html) documentation and the vSphere best practices [white paper](https://www.vmware.com/docs/perf-latency-tuning-vsphere8).

| Setting/Feature | Description | GemFire Impact & Recommendation |
| :---- | :---- | :---- |
| Latest Hardware & vSphere | Use most recent CPUs, BIOS, vSphere, VM Tools, and Virtual HW. | Minimizes latency and enables latest optimizations. Always run GemFire on supported, up-to-date infrastructure. |
| BIOS Power Settings | High Performance, Turbo Boost enabled, C/P/QPI states disabled, Node interleaving disabled. | Ensures maximum CPU frequency and NUMA locality, reducing compute and memory latency for GemFire. |
| EVC Mode | Disable or use the highest supported baseline for CPUs. | Avoid masking out advanced processor instructions; this benefits GemFire's multi-threaded performance. |
| vMotion & DRS Scheduling | Avoid live migrations (vMotion/DRS) for GemFire during busy periods. | vMotion introduces a "stun" risk of short outages; schedule migrations and DRS moves only in planned windows for GemFire VMs. |
| NIC Ring Buffers & SplitRX/TX | Increase ring buffer size, enable SplitRX and SplitTX for NICs. | Prevents packet drops during high-throughput operations. GemFire benefits from larger buffers for replication/traffic spikes. |
| Disable Queue Pairing | Separates transmit and receive threads in NIC driver. | Reduces risk of packet loss during transmit-heavy GemFire operations; monitor CPU usage with this change. |
| VM Right Sizing | Size VM vCPUs and memory to fit within a single NUMA node if possible. | Avoid oversized VMs; keep all resources local for in-memory GemFire workloads, lowering latency. |
| Virtual Hardware Version | Use latest version (vHW 21 or later). | Ensures VM gets latest CPU features and optimizations; GemFire can process more transactions per second. |
| Leverage vTopology | Match VM vCPU sockets/cores to host architecture. | Ensures guest OS (and GemFire JVM) sees the real processor topology; improves thread locality and performance. |
| Disable Hot-Add | Disabling CPU/mem hot-add exposes VM NUMA topology. | Allows GemFire to take advantage of NUMA awareness, reducing cross-node memory access delay. |
| Set VM Latency Sensitivity to High | Gives VM exclusive access to pCPU/memory. | Eliminates contention. Use for GemFire VMs with strict latency SLAs; set CPU/memory reservation fully. |
| Use VMXNET3 Adapter | VMware's high-perf paravirtualized network driver. | Always select VMXNET3 (with offload/tuning); handles GemFire's replication and client traffic efficiently. |
| Balance Tx/Rx and Thread Affinity | Multiply vNIC parallelism; affinitize Tx thread to NUMA node. | Allows GemFire networking (replication, client traffic) consistent, high-bandwidth and low-latency performance. |
| NUMA Node Affinity | Pin VM to a NUMA node | Ensures memory/network traffic stays local, again beneficial for GemFire's in-memory data grid behavior. |
| SR-IOV/DirectPath I/O (If Needed) | Direct VM to NIC access for highest throughput. | Recommended only if VMXNET3 does not meet GemFire networking needs; note trade-offs (losing vMotion, resource pooling). |
| Advanced VM Parameters | Set sched.cpu.affinity.exclusiveNoStats, monitor.forceEnableMPTI, timeTracker.lowLatency. | Further improves VM isolation and timing precision; useful for highly critical GemFire workloads. |
| Networking: Enhanced Datapath, DPUs | Offload VM networking to SmartNICs or DPUs. | Consider this for containerized or NFV-style GemFire deployments; may benefit multi-tenant and high-bandwidth clusters. |
| Guest OS Tuning | Kernel, driver, and stack optimization as per vendor. | Apply Linux or Photon OS tuning (real-time kernel etc.). For GemFire JVM, ensure OS is tuned for low latency and thread scheduling. |
| Operational Tools | esxcli, vsish, esxtop, net-stats for monitoring. | Use to observe GemFire VM resource utilization and drive continual tuning. Check for drops, network buffer sizes, CPU steal/waits. |

Additional recommendations for GemFire instances:

- Always test the effect of each change in staging before applying the change to production.

- Schedule maintenance, such as vMotion and DRS, outside GemFire's peak windows to avoid observable latency spikes.

- Pin GemFire JVM memory and threads to NUMA nodes by disabling hot-add and setting explicit affinity where possible.

- Reserve resources. GemFire needs dedicated CPU and memory, not just shares.

- Regularly monitor network and memory utilization using ESXi operational tools for proactive adjustment.

This mapping enables a targeted performance architecture for GemFire clusters on vSphere, tuned for memory intensity and latency sensitivity. System administrators and architects managing critical deployments can act on these recommendations directly.

