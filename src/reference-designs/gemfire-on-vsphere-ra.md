# Tanzu GemFire on VMware Cloud Foundation

The *Tanzu GemFire on VMware Cloud Foundation* reference architecture describes the deployment and management of VMware Tanzu GemFire on self-managed, multi-region vSphere infrastructure. The reference architecture uses a vSphere Distributed Switch (vDS) for network virtualization and NSX Advanced Load Balancer for traffic distribution and high availability. This reference architecture provides architectural best practices, deployment strategies, and operational recommendations to support a Tanzu GemFire deployment that is scalable, high-performance, and fault-tolerant. These recommendations apply to an enterprise-grade vSphere environment.

## <a id="intended-audience"></a> Intended Audience

This document is intended for all stakeholders involved in the adoption and management of Tanzu GemFire, as described in the following table.

|Persona|Objective|
|---|---|
|Executives and IT decision-makers|Align in-memory data management strategies with business objectives and digital transformation initiatives.|
|Infrastructure and cloud architects|Design resilient, scalable, and secure platforms to support distributed caching, real-time analytics, and data replication across environments.|
|Platform engineers and DevOps teams|Deploy, operate, and maintain Tanzu GemFire on Kubernetes and virtualized infrastructure.|
|Application owners and developers|Use in-memory data grids to enhance application speed, fault tolerance, and horizontal scalability.|
|Enterprise modernization teams|Transform legacy architectures by implementing low-latency, high-availability data layers to support modern, cloud-native workloads.|
|Multiple personas|Drive strategic efforts to improve data availability, performance, and operational efficiency across hybrid and multi-site deployments.|

## <a id="vsphere-bill-of-materials"></a> Bill Of Materials

The following infrastructure components and software versions validate the procedures in this document. You can use these versions to install Tanzu GemFire in a vSphere environment:

| Software Components  | Version  |
| :---- | :---- |
| vSphere ESXi | 8.0.3 |
| vCenter | 8.0.3 |
| NSX Advanced Load Balancer | 22.1.5 |
| Tanzu GemFire | 10.1.3 |
| Tanzu GemFire Management Console | 1.3.1 |


## <a id="general-references"></a> General References

The following reference materials complement the procedures in the *Deploy and Manage VMware Tanzu GemFire on vSphere* reference architecture.

- [About Tanzu GemFire](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-gemfire/10-3/gf/getting_started-gemfire_overview.html) in the Tanzu GemFire 10.3 documentation.
- [Installing VMware Tanzu GemFire from a Compressed TAR File on Windows, Unix, and Linux](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-gemfire/10-3/gf/getting_started-installation-install_standalone.html) in the Tanzu GemFire 10.3 documentation.
- [Tanzu GemFire Management Console Installation](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-gemfire-management-console/1-4/gf-mc/install.html) in the Tanzu GemFire Management Console 1.4 documentation.
- [How do I manually download and install Java for my Windows computer?](https://www.java.com/en/download/help/windows_manual_download.html) in the Java 8.0 documentation.
- [Apache Maven Installation ](https://maven.apache.org/install.html) in the Apache Maven documentation.