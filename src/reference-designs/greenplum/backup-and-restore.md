# Greenplum Backup and Restore

## Overview

vSAN protects the data against hardware failure in place ([Storage Architecture - vSAN & vSAN Storage Cluster](./storage-architecture.md#storage-architecture-vsan-vsan-storage-cluster)), but it cannot protect against logical or human error, or against total loss of the cluster or rack, because it replicates a mistaken deletion as faithfully as good data. Backup and restore is the layer that covers those gaps, and it is the mechanism behind the DR escalation paths in the [Storage Failure Behavior: Physical Disk Failure](./storage-architecture.md#storage-failure-behavior-physical-disk-failure) and [Rack Design for Greenplum Clusters](./rack-design.md#rack-design-for-greenplum-clusters) sections. The two layers are complementary; neither replaces the other.

Greenplum uses a parallel, MPP-aware framework, `gpbackup` and `gprestore`, in which the coordinator captures metadata while every segment writes its own slice of data in parallel, to local storage or a storage plugin. This scales with the cluster instead of bottlenecking on the coordinator, which is why it is the method used throughout this architecture. The non-parallel `pg_dump` utilities route everything through the coordinator and are special-case only.

Command syntax and configuration beyond the workflows shown here are in the Tanzu Greenplum Backup and Restore documentation.

**Backup and Restore Design Decisions**

| Consideration | Options | Decision | Driver |
| :---- | :---- | :---- | :---- |
| Backup framework | Parallel (gpbackup) vs non-parallel (pg_dump) | Parallel gpbackup/gprestore | Only the parallel model scales with segment count; non-parallel funnels through the coordinator. |
| Role vs vSAN | Replaces vSAN vs complements it | Complementary; both required | Different failure classes: vSAN covers hardware, backup covers logical error and total cluster loss. |
| Primary storage target | Local / S3-compatible / Data Domain | S3-compatible object storage | Independent of the protected cluster and vendor-neutral. Data Domain supported where already standard. |
| Storage path | Plugin vs local | Plugin (S3) | Plugin places segment data automatically on restore, including onto a differently-sized cluster; local needs manual per-segment placement. |
| Off-site protection | None / replicated copy | Off-site copy for region DR | Stretched clusters survive AZ loss, not region loss. |
| Monitoring | Best-effort vs mandatory | Mandatory, automated failure alerts | A silent backup failure is an invisible DR exposure. |

## Backup Types

| Type | Captures | Notes |
| :---- | :---- | :---- |
| Full | All objects and data, point-in-time | Self-contained; base for any incremental set. |
| Incremental | Changed append-optimized data only | Heap tables always backed up in full. Efficient only for AO-heavy, low-change data. |
| Metadata-only / Data-only | Schema or data separately | Useful for staging restores. |
| Filtered | Selected schemas, tables, or leaf partitions | Basis for same-cluster logical recovery (see [Restore Scenarios](#restore-scenarios)). |

Two rules govern incremental sets and are treated as constraints:

* All backups in a set must share consistent options and one storage target; `gpbackup` enforces this.  
* Changing the segment configuration (a `gpexpand`, covered in [Horizontal Expansion with gpexpand](./scalability-capacity-planning.md#horizontal-expansion-with-gpexpand)) invalidates the incremental chain. A fresh full backup is required afterward.

On restore, `gprestore` resolves the chain from a single target timestamp: it restores each append-optimized table from its most recent version in the set and heap tables from the latest backup.

### Understanding Table Storage in Greenplum 7: Heap vs. AO

To understand how backups behave, one must first understand Greenplum's two underlying storage engine formats: Heap and Append-Optimized (AO).

| Feature | Heap Tables (Row-Store) | Append-Optimized (AO) Tables |
| :---- | :---- | :---- |
| Primary Use Case | Small lookup tables, metadata, operational tables with frequent UPDATE/DELETE. | Large fact tables, data warehouse historical logs, bulk INSERT workloads. |
| Storage Mechanism | Standard PostgreSQL 8 KB pages.  | Custom Greenplum block storage. Data is appended sequentially to file segments. |
| Greenplum 7 Syntax | Default, or CREATE TABLE ... USING heap; | CREATE TABLE ... WITH (appendonly=true); (Or GP7 syntax: USING ao_row / USING ao_column) |
| Incremental Backup Behavior | ALWAYS backed up 100% in full. | Backed up incrementally. Only changed AO file segments/partitions are copied. |

**What does `APPENDONLY=TRUE` do under the hood?**

When a database developer or admin creates a table with `WITH (appendonly=true)` (or `USING ao_row` / `USING ao_column` in Greenplum 7), it tells the database engine to:

* Bypass standard PostgreSQL row editing: Data blocks are written sequentially. Modifying data does not overwrite existing disk blocks; instead, changes are appended as new segment files or tracked in visibility maps.  
* Enable Compression & Columnar Storage: It opens up options for heavy compression algorithms (for example, `zstd, zlib`) and columnar layouts (`orientation=column`), drastically reducing S3/disk footprint.  
* Enable Backup Modification Tracking: Greenplum maintains explicit metadata maps for AO segment files. This metadata allows `gpbackup` to instantly query: "Has this specific table or partition changed since Timestamp X?"

Because Heap tables lack this sequential block modification map, `gpbackup` cannot determine which individual Heap pages changed. Therefore, every "incremental" backup silently performs a 100% full dump of all Heap tables.

### Cons and Operational "Gotchas" of Incremental Backups

While incremental backups reduce daily backup windows and network bandwidth, they introduce distinct operational trade-offs that infrastructure and operations teams must account for:

* The "Hidden Heap" Storage Inflation If application teams create large tables as default Heap tables instead of AO tables, your "incremental" backup size will not shrink as expected. If 40% of your total database volume is in Heap tables, your daily incremental backup will always be at least 40% of the full backup size.  
* Chain Dependency & Increased Failure Risk An incremental set forms a strict chain: `[Full Base] -> [Inc 1] -> [Inc 2] -> [Inc 3]`.  
  * Restore Complexity: Restoring to Inc 3 requires every single preceding backup in the chain to be present and uncorrupted.  
  * Blast Radius: If `Inc 1` becomes corrupted on S3 or storage, `Inc 2` and `Inc 3` become unrestorable.  
* Invalidation by Cluster Scale-Out (`gpexpand`) Performing a cluster expansion (`gpexpand`) to add segment hosts alters the physical segment distribution. This immediately invalidates all existing incremental chains. The first backup following a `gpexpand` must be a full backup.  
* Strict Target & Parameter Locking All backups within an incremental chain must share identical configuration options (for example, `--leaf-partition-data` and `--plugin-config`) and reside on the exact same storage target/S3 bucket. You cannot mix storage targets mid-chain.  
* Restore Time Overhead (RTO Impact) A full restore from a single Full backup is a direct stream. A restore from an incremental chain requires `gprestore` to parse multiple metadata files, stitch together pointers across daily snapshots, and reconstruct tables layer-by-layer, which can increase Recovery Time Objective (RTO).

## Backup Cadence

A common baseline is a **weekly full plus daily incrementals**, but the RA does not fix this because it depends on inputs the deploying organization owns.

**Parameter-Driven Choices (no fixed RA value)**

| Choice | Derived from |
| :---- | :---- |
| Full vs incremental cadence | Proportion of append-optimized vs heap data, and change rate between backups. |
| Backup frequency | Recovery Point Objective (RPO): tighter RPO -> more frequent backups. |
| Retention depth | Recovery window needed, plus any compliance requirement. Retained per whole set. |
| DR cluster sizing | Recovery Time Objective (RTO) and cost tolerance (see [Recovery Prerequisites](#recovery-prerequisites)). |
| Storage target sizing | Dataset size x retention x change rate, less any target-side dedup/compression. |

Retention operates on **whole sets**: a restore needs the base full plus every intervening incremental, so a set is retained and archived as a unit and a missing link breaks the chain from that point on.

#### Choose Daily Full Backups when:

* The database is under ~2-3 TB: The network and S3 storage can comfortably finish a full dump within the nightly maintenance window.  
* Workload is Heap-Heavy: If more than 20-30% of active data resides in Heap tables, incremental backups offer diminishing returns.  
* RTO (Speed of Recovery) is Paramount: Restoring a single Full backup is faster and less prone to missing-link errors during a disaster.  
* Post-Maintenance Events: Always force a Full backup immediately after gpexpand, major database upgrades, or massive batch ETL runs.

#### Choose Weekly Full + Daily Incremental when:

* Data Warehouse is Very Large (5 TB+): Taking a full backup every night would breach the daily backup window or saturate network bandwidth.  
* Data is Partitioned and AO-Heavy: Historical partitions (for example, past months/years) are AO and never modified; only the active daily partition receives new INSERTs.  
* Strict RPO Requirements: You need frequent recovery points (for example, every 4 hours) where taking full backups is physically impossible due to time constraints.

## Backup Storage

| Target | Nature | Position in this RA |
| :---- | :---- | :---- |
| S3-compatible object storage | Plugin, streams per-segment data to a bucket | Preferred. Independent of the cluster, vendor-neutral, automatic restore placement. |
| Dell EMC Data Domain (DD Boost / BoostFS) | Plugin or mounted filesystem, with dedup/compression and remote replication | Supported alternative where Data Domain is the enterprise standard. Vendor-specific. |
| Local segment storage | Default, per-host filesystem | Only for backups promptly archived elsewhere. |

S3 is the design default: it sits on infrastructure independent of the vSAN cluster it protects, it is not tied to a vendor, and its plugin places each segment's data on the correct destination segment automatically. Data Domain adds inline dedup and off-site replication and is a strong choice where already deployed. 

## Restore Scenarios

Restore runs through `gprestore`, which loads metadata via the coordinator and drives segment restores in parallel. What differs by scenario is the *target*.

| Scenario | Situation | Segment count | Path |
| :---- | :---- | :---- | :---- |
| Same running cluster | Logical recovery (dropped table, bad ETL) | Unchanged | Filtered restore of affected objects. Fastest, most common. |
| Same-shape replacement | Cluster lost, new cluster rebuilt with same layout | Matches source | Standard full same-size restore, no redistribution. |
| Differently-sized cluster | DR onto smaller/cheaper hardware, or migration | Differs from source | Resize restore (--resize-cluster). Redistributes data, see [Workflow: Resize and Restore to a Differently-Sized Cluster (Scenario 3)](#workflow-resize-and-restore-to-a-differently-sized-cluster-scenario-3). |

Scenario 1 recovers from exactly what vSAN cannot help with. Scenario 2 is the simplest DR path and the reason many keep a same-shape standby. Scenario 3 is what lets a DR target be sized differently from production, and it is detailed as a workflow in [Workflow: Resize and Restore to a Differently-Sized Cluster (Scenario 3)](#workflow-resize-and-restore-to-a-differently-sized-cluster-scenario-3).

## Recovery Prerequisites

For any restore to succeed, the destination must meet the following. This is the checklist a DR plan is built against.

| Prerequisite | Requirement | Must match the source? |
| :---- | :---- | :---- |
| Greenplum major version | Same major version as the backup | Yes. Cross-version is a migration capability, not a DR path. |
| Backup/restore tooling | Recent enough to support the operation (resize restore needs current tooling) | Yes (version floor) |
| Storage capacity | Enough to hold the restored data | Adequate, not identical |
| Compute / memory | Enough to run the workload, sized per [vSphere Cluster and Compute Design](./vsphere-cluster-design.md#vsphere-cluster-and-compute-design) and [Storage Architecture - vSAN & vSAN Storage Cluster](./storage-architecture.md#storage-architecture-vsan-vsan-storage-cluster) | Adequate, not identical |
| Segment count | Must match only for a same-size restore (Scenario 2) | No for resize restore (Scenario 3) |
| Hardware sizing | Host count, segments per host, node spec may differ | No |
| Backup access | Destination can reach the backup (same bucket/credentials for S3) | Yes |

The short version: the recovery cluster must be a **capacity-adequate, same-major-version** home for the data with access to the backup. It does **not** need to be a hardware-identical twin of production. That freedom is what makes an economically smaller DR cluster viable.

## Workflow: Resize and Restore to a Differently-Sized Cluster (Scenario 3)

This is the Scenario 3 DR / migration path: a backup taken on the source cluster is restored onto a separate cluster with a different segment count, using the S3 plugin so that per-segment placement is automatic.  
The local-backup equivalent requires an operator to manually relocate every segment's files onto the correct destination segment following the tool's mapping rules; it is slow and error-prone at scale, and it is the direct reason this architecture standardizes on the S3 plugin path. Local resize restore is therefore noted only as a fallback and is not detailed here.

**Prerequisites (from [Recovery Prerequisites](#recovery-prerequisites)), plus:**

* Backup was taken with `--leaf-partition-data` where partitioned tables are involved.  
* The same S3 plugin configuration (bucket, credentials, endpoint) is available on the destination cluster. See Appendix A.

**Steps:**

1. **Back up the source** through the S3 plugin (this is the normal production backup; no special resize flag is needed at backup time, only recent tooling):

```
   gpbackup --dbname <db> --leaf-partition-data --plugin-config /path/s3.yaml
```

Note the backup timestamp from the output.

2. **Stand up the destination cluster** at its own segment count (M), meeting all prerequisites defined in the previous section, with the S3 plugin config in place.  
3. **Restore with resize** onto the destination, pointing at the same bucket and timestamp:

```
   gprestore --timestamp <YYYYMMDDHHMMSS> --resize-cluster --create-db --plugin-config /path/s3.yaml
```

The plugin retrieves each segment's data from S3 and places it correctly; `--resize-cluster` redistributes the data across the M destination segments.

4. **Validate**: confirm the return code is "success", check row counts on a sample of tables, and run `ANALYZE` (or restore with `--run-analyze`) so planner statistics reflect the new segment layout.

**Direction matters for time:** restoring from a larger source onto a smaller destination funnels several source segments' data into each destination segment sequentially, so it takes longer than the reverse. Factor this into the RTO.

## Backup Monitoring

Because backup underpins the DR path, monitoring is mandatory, not best-effort.

| Mechanism | Use |
| :---- | :---- |
| Return codes | Every scheduled job checks for clean success; alert on anything else. |
| Report files | Per-operation record (options, type, timing, object counts) on the coordinator. |
| Email notifications | Fire on failure into the operations alerting path. |
| History database | System of record for which sets exist, how they chain, and which succeeded. |
| gpbackup_manager | List, report, find-table, and whole-set retention/deletion (commercial release). |

The operational standard: every backup monitored on return code and history status, failures alerting automatically, and the existence of a current restorable set verified rather than presumed. Periodic **test restores onto a recovery cluster** are the only proof the DR path works.
