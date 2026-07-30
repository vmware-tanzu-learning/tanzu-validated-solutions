# Document Overview

This reference architecture defines the infrastructure design principles, configuration guidance, and tuning considerations required to run Tanzu Greenplum 7.x on VMware vSphere Foundation (VVF) 9 or VMware Cloud Foundation (VCF) 9. 

The platform is designed to provide Tanzu Greenplum with: 

* Predictable performance for large-scale analytical workloads   
* Minimal latency across the compute, storage, and network layers   
* Linear scalability as cluster size and workload intensity grow   
* Failure domains aligned with Greenplum's MPP architecture   
* Data durability and query availability delivered through an integrated platform design

This architecture adopts a platform-integrated design philosophy; it harnesses the resilience capabilities of both Tanzu Greenplum and the underlying vSphere and vSAN platform, combining them so that each layer reinforces the other and protection is delivered without unnecessary duplication.

## Scope

**In scope:** 

* vSphere cluster and compute design as it relates to Greenplum MPP workloads   
* ESXi host sizing and placement considerations   
* vSphere Distributed Switch (vDS) design for Greenplum traffic classes   
* vSAN ESA and vSAN storage-cluster configuration for analytical and mixed read/write workloads   
* Rack and fault domain aware placement strategies   
* Selection of the Greenplum high-availability topology and its infrastructure implications   
* Backup and restore architecture at the platform level

**Out of scope:**

* Generic vSphere hardening and security baselines   
* vCenter sizing and deployment considerations   
* Identity management, authentication, and platform RBAC   
* Application-level query tuning, data distribution, and schema design 

## Intended Audience and Assumptions

This document is intended for the following personas: 

| Persona | Objective |
| ----- | ----- |
| Infrastructure and platform architects | Design vSphere and vSAN infrastructure that meets the performance, scalability, and resiliency requirements of production-grade Greenplum MPP deployments |
| Database platform engineers | Deploy, configure, and operate Tanzu Greenplum clusters on the underlying vSphere and vSAN platform |
| Site Reliability Engineering (SRE) and operations teams | Maintain the availability, performance, and operational health of Greenplum environments running on vSphere infrastructure |

It assumes the reader has working knowledge of: 

* Greenplum architecture and MPP concepts   
* VMware vSphere Foundation, ESXi, vSAN and vSAN Storage Cluster 

This reference architecture does not attempt to reintroduce these technologies, but instead focuses on how they should be combined and configured to support production-grade Greenplum deployments.

## Bill Of Materials (BOM)

| Component | Version/Requirement | Notes |
| ----- | ----- | ----- |
| VMware vSphere | Minimum: VMware vSphere Foundation (VVF). Supported: VMware Cloud Foundation (VCF) | Required for compute virtualization, Networking, HA, and DRS |
| vCenter Server | 9.x | Required for centralized management, lifecycle operations, and cluster services |
| ESXi Hosts | 9.x  | Aligned with VVF/VCF |
| Storage | vSAN ESA or vSAN Storage Cluster | vSAN ESA and Storage-only cluster (vSAN Max) supported for high-throughput analytics workloads |
| Tanzu Greenplum  | 7.x | This reference architecture is validated against Greenplum 7.x |
| Guest Operating System | Supported Linux OS for Greenplum 7.x | Refer to [Tanzu Greenplum requirements](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-greenplum/7/greenplum-database/install_guide-platform-requirements-overview.html) |
