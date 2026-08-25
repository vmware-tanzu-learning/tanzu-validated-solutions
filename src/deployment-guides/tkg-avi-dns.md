# AVI DNS Virtual Service with Tanzu Kubernetes Grid 

The Purpose of the Document is to demonstrate how we can leverage AVI DNS Virtual Service to as a DNS Server for workload application.For More information Please refer [**Product Documentation**](https://docs.vmware.com/en/VMware-Tanzu-Mission-Control/services/tanzumc-using/GUID-EF35646D-8762-41F1-95E5-D2F35ED71BA1.html) .

AVI DNS Virtual Service is available only in **AVI Enterprise** license or more.For more information about AVI DNS Architecture please refer product [documentation](https://avinetworks.com/docs/latest/avi-dns-architecture/) 

## General Instructions for Installing AVI DNS and L7 Ingress Service Provider.

NSX ALB as in **L7 Ingress Service Provider**

We will be Deploying NSX ALB L7 ingress in NodePortLocal mode in our infrastructure, For more information please refer NSX ALB as in L4+L7 Ingress Service Provider Session in Reference Architecture.


Link will be given here to our RA 

L7 functionality will be enabled using AKO configuration files as part of the Management cluster deployment. 

Deployment file will given here for reference.
### Create a Service Engine Group.
To create or edit an SE group:

1. Select Infrastructure > **Cloud Resources** and click on the cloud name (for example, sfow01vc01).
2. Click on **CREATE** 

   * Update the Service Engine Group Name.
   * Select High Availability to Active/Active.
   * VS Placement across Service Engines should be Compact.
### Update IPAM Profile

We will be using **sfo01-w01-vds01-albmanagement** network for DNS virtual Service IP.

Navigate to **Templates** > **IPAM/DNS Profiles** and Edit the IPAM Profile.

Add the Network by selecting cloud under **Cloud** > **ADD** Select **sfo01-w01-vds01-albmanagement** > **SAVE**

### Configuring DNS Virtual Service

Starting with release 18.1.2, the DNS virtual service can be configured with IPv4 VIP, IPv6 VIP, or a dual VIP.

Navigate to **Applications** > **Virtual Services** and click on **CREATE VIRTUAL SERVICE** (Advanced Setup) Select the Cloud Click **NEXT**. Configuration tabs associated with DNS are as explained below.

Settings
*  Update **Name**
*  VS 
*  **Application Profiles** Select Select System-DNS.
*  **TCP/UDP Profile** Select System-UDP-Per-Pkt.
*  In **VS VIP**  Select **Create VS VIP** Enter Name & under **General** Select **ADD** to add **VIP**
   * **Enable VIP**
   * **Private IP** > **Auto-Allocate**
   * **IP Protocol** > **V4 Only**
   * **VIP Address Allocation Network** > **sfo01-w01-vds01-albmanagement**
   * **IPv4 Subnet** > Select the Defined network
* Click **SAVE**

### Configuring DNS Name

DNS Profile will be created as part of the Management cluster creation.

Navigate to **Templates** > **IPAM/DNS Profiles** and Select the DNS **Virtual Service**
by using the drop-down option.

* Update the DNS Name for AVI DNS by Selecting **ADD** > **SAVE**

### Update AVI DNS Service

Navigate to **Administration** > **DNS Service** and Select the DNS profile **Click** on pencil icon to **EDIT**.