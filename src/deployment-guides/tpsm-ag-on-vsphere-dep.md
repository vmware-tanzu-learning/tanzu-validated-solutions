# Deploy Tanzu Platform Self-Managed on vSphere in an Air-Gapped Environment  
This document details the procedures for enabling and deploying the following components:  

- Contour Supervisor Service  
- Harbor Supervisor Service  
- Tanzu Kubernetes Cluster (TKC)  
- Configure and Deploy TPSM 

It is assumed that the IaaS Control Plane has already been enabled, utilizing vSphere Distributed Switch (VDS) networking and NSX Advanced Load Balancer (ALB) Enterprise Edition for L4 load balancing.

The procedure to install TPSM on a Tanzu Kubernetes Cluster involves the following major steps:

1. **Deploy Harbor OVA**: Used exclusively for storing the binaries required for Supervisor services.  
1. **Enable and Install Contour Supervisor Service**: A prerequisite for installing the Harbor Supervisor service.  
1. **Enable and Install Harbor Supervisor Service**: Used to store Tanzu vSphere Plugins and TPSM bundles.  
1. **Deploy the Tanzu Kubernetes Cluster (TKC)**  
1. **Deploy the TPSM bundle on TKC**

> **Note**  If a stable image repository is already available in the environment, the deployment of Harbor OVA, Contour, and Harbor Supervisor services can be skipped. 

Several packages and plugins need to be downloaded to deploy and configure the components mentioned above. For this purpose, we will utilize a bastion host. A bastion host is a server that has internet access. For the purposes of this document, it is assumed that only the bastion host has internet connectivity, while no other infrastructure VMs or workload VMs have internet access.

- [Bill of Materials](#bill-of-materials)
- [Download all required Plugins and Binaries](#download-all-required-plugins-and-binaries)
  - [Download Binaries and YAML files required for Supervisor Services](#download-binaries-and-yaml-files-required-for-supervisor-services)
    - [Download Contour Binaries and associated YAML files](#download-contour-binaries-and-associated-yaml-files)
    - [Download Harbor Binaries and associated YAML files](#download-harbor-binaries-and-associated-yaml-files)
  - [Download Tanzu CLI and Tanzu Plugins](#download-tanzu-cli-and-tanzu-plugins)
  - [Download Tanzu Packages](#download-tanzu-packages)
  - [Download Trivy DB Bundle](#download-trivy-db-bundle)
  - [Summary](#summary)
- [Deploy Harbor OVA in vCenter](#deploy-harbor-ova-in-vcenter)
- [Configure Admin Machine](#configure-admin-machine)
  - [Install Carvel Tools](#install-carvel-tools)
  - [Download and Install kubectl and kubectl-vsphere CLI](#download-and-install-kubectl-and-kubectl-vsphere-cli)
  - [Add the Harbor OVA certificate to Trust Store](#add-the-harbor-ova-certificate-to-trust-store)
- [Install Contour as a Supervisor Service](#install-contour-as-a-supervisor-service)
  - [Upload Contour Binaries to Harbor](#upload-contour-binaries-to-harbor)
  - [Register Contour Supervisor Service to vCenter](#register-contour-supervisor-service-to-vcenter)
  - [Install Contour Service](#install-contour-service)
- [Install Harbor as a Supervisor Service](#install-harbor-as-a-supervisor-service)
  - [Upload Harbor Binaries to Harbor(VM)](#upload-harbor-binaries-to-harbor\(vm\))
  - [Register Harbor Supervisor Service to vCenter](#register-harbor-supervisor-service-to-vcenter)
  - [Install Harbor Service](#install-harbor-service)
- [Install Tanzu CLI and Plugins on Admin Machine](#install-tanzu-cli-and-plugins-on-admin-machine)
- [Upload Tanzu Packages to Harbor(Supervisor Service)](#upload-tanzu-packages-to-harbor\(supervisor-service\))
- [Deploy Tanzu Kubernetes Cluster(TKC)](#deploy-tanzu-kubernetes-cluster\(tkc\))
  - [Install cert Manager](#install-cert-manager)
- [Upload TPSM Bundle to Harbor Repo(Supervisor Service)](#upload-tpsm-bundle-to-harbor-repo\(supervisor-service\))
  - [Upload Tanzu Platform-SM Binaries](#upload-tanzu-platform-sm-binaries)
  - [Upload TMC Extensions](#upload-tmc-extensions)
  - [Upload Collector Bundle](#upload-collector-bundle)
  - [Upload Trivy DB Bundle](#upload-trivy-db-bundle)
- [Deploy TPSM on Tanzu Kubernetes Cluster](#deploy-tpsm-on-tanzu-kubernetes-cluster)

## <a id=bill-of-materials> </a> Bill of Materials

| Component | Version |
| :---- | :---- |
| vCenter | 8.0.3 |
| TPSM | 1.0.0-sep-2024-rc.21-v88282bc |
| NSX ALB | 22.1.5 |
| Tanzu Kubernetes Grid Service  | 3.0.0 |
| TKC | v1.28.8---vmware.1-fips.1-tkg.2 |

## <a id=download-all-required-plugins-and-binaries> </a> Download all required Plugins and Binaries  

The **bastion host** serves as the machine with internet access, enabling it to download all the necessary plugins, binaries, and packages required to configure and manage various components. In this document, an **Ubuntu 22.04.4-based Bastion Host** is utilized for this purpose.  
Below are the key plugins and packages that must be downloaded, each playing a critical role at different stages of the TPSM deployment process:

* **Download Harbor OVA**: Before enabling Supervisor services in an air-gapped environment, the necessary images for each service must be uploaded to an image repository. For this, the Harbor OVA (Photon v4 Harbor v2.10.3 OVA) provided by the Tanzu platform will be used as the image repository.  
  Photon v4 Harbor v2.10.3 OVA can be downloaded from the [broadcom support portal](https://support.broadcom.com/group/ecx/productfiles?subFamily=VMware%20Tanzu%20Kubernetes%20Grid&displayGroup=VMware%20Tanzu%20Kubernetes%20Grid&release=2.5.2&os=&servicePk=520705&language=EN)  
  > **Note** This repository will be exclusively used for uploading the binaries necessary to enable Supervisor services like Contour and Harbor.It will not be utilized for any other purpose.  
     
* **Download binaries required for Supervisor Services:**  This document focuses on enabling the Contour and Harbor Supervisor Services. For the full list of other supported Supervisor Services, refer to the [vSphere Supervisor Services](https://vsphere-tmm.github.io/Supervisor-Services/) documentation.    
  * **Download YAML files**: along with the binaries, obtain the necessary YAML files to enable Supervisor services in the IaaS control plane.

  See the section titled “[Download Binaries and YAML files required for Supervisor Services](#download-binaries-and-yaml-files-required-for-supervisor-services)” below for instructions on obtaining the necessary binaries.

* **Download TPSM bundle**: TPSM Bundle includes all necessary binaries to deploy TPSM on a given Tanzu Kubernetes Cluster. It also includes carvel tools which are required are various stages of the deployment.  
  Download the TPSM package from the [Broadcom Support Portal](https://support.broadcom.com/group/ecx/productfiles?subFamily=Tanzu%20Platform%20Self%20Managed&displayGroup=Tanzu%20Platform%20Self%20Managed&release=September%20Beta&os=&servicePk=524525&language=EN).

* **Download trivy-db bundle**: TPSM makes use of trivy scanner for detecting vulnerabilities in the platform and deployed applications.

* **Download Tanzu CLI and Tanzu Plugins**: Tanzu CLI and Plugins allows admins/users to manage and interact with the Tanzu Kubernetes Grid (TKG) environment.   
  See the section titled “[Download Tanzu CLI and Tanzu Plugins](#download-tanzu-cli-and-tanzu-plugins)” below for instructions on obtaining the Tanzu CLI and Tanzu Plugins

* **Download Tanzu Packages**: Tanzu Packages enable administrators and users to use the Tanzu CLI or Carvel Custom Resources to add and manage common services and add-ons on Kubernetes clusters. See the section titled “[Download Tanzu Packages](#download-tanzu-packages)” below for instructions on obtaining the Tanzu Packages.

The following sections provide details on how to download the components mentioned above.

### <a id=download-binaries-and-yaml-files-required-for-supervisor-services> </a> Download Binaries and YAML files required for Supervisor Services 

This document focuses on enabling the Contour and Harbor Supervisor Services. For the full list of other supported Supervisor Services, refer to the [vSphere Supervisor Services](https://vsphere-tmm.github.io/Supervisor-Services/) documentation. 

“imgpkg” tool which is part of the Carvel toolbox is required to download the required tar bundles, below instructions provides required instructions to install this tool on the bastion host. Follow the [official documentation](https://carvel.dev/imgpkg/docs/v0.43.x/) for more details

```
wget https://github.com/carvel-dev/imgpkg/releases/download/v0.43.1/imgpkg-linux-amd64
mv ./imgpkg-linux-amd64 /usr/local/bin/imgpkg
chmod +x /usr/local/bin/imgpkg
```

#### <a id=download-contour-binaries-and-associated-yaml-files> </a> Download Contour Binaries and associated YAML files  

At the time of writing this document, the latest available version of the Contour Supervisor Service is “v1.28.2”. Refer to ​​[vSphere Supervisor Services](https://vsphere-tmm.github.io/Supervisor-Services/#contour-versions) page to check for the updated versions.  
From the bastion, execute the following command to download the tarball.

```
##Download Contour Binaries
imgpkg copy -b projects.packages.broadcom.com/tkg/packages/standard/contour:v1.28.2_vmware.1-tkg.1 --to-tar contour-v1.28.2.tar --cosign-signatures
```

Download the `contour.yml` and `contour-data-values.yml` files required for enabling the Contour Supervisor Service. These files can be accessed through the [vSphere Supervisor Services](https://vsphere-tmm.github.io/Supervisor-Services/#contour-versions)  page. The `contour.yml` file can be obtained by selecting the appropriate Contour version, and the `contour-data-values.yml` can be downloaded from the "Contour Sample values.yaml" section in the same vSphere Supervisor Services page.

#### <a id=download-harbor-binaries-and-associated-yaml-files> </a> Download Harbor Binaries and associated YAML files  

At the time of writing this document, the latest available version of the Harbor Supervisor Service is “v2.9.1”. Refer to ​​[vSphere Supervisor Services](https://vsphere-tmm.github.io/Supervisor-Services/#harbor-versions) page to check for the compatibility/availability of updated versions.  
From the bastion, execute the following command to download the tarball:

```
##Download Harbor Binaries
imgpkg copy -b projects.packages.broadcom.com/tkg/packages/standard/harbor:v2.9.1_vmware.1-tkg.1 --to-tar ./harbor-v2.9.1.tar --cosign-signatures
```

Download the `harbor.yml` and `harbor-data-values.yml` files required for enabling the Contour Supervisor Service. These files can be accessed through the [vSphere Supervisor Services](https://vsphere-tmm.github.io/Supervisor-Services/#cloud-native-registry-service)  page. The `harbor.yml` file can be obtained by selecting the appropriate harbor version, and the `harboe-data-values.yml` can be downloaded from the "Harbor Sample values.yaml" section in the same vSphere Supervisor Services page.

### <a id=download-tanzu-cli-and-tanzu-plugins> </a> Download Tanzu CLI and Tanzu Plugins  

Tanzu CLI allows admins/users to manage and interact with the Tanzu Kubernetes Grid (TKG) environment. Tanzu CLI supports a plugin architecture, where additional functionalities can be enabled through plugins. These plugins allow the CLI to handle more specialized tasks, typically related to specific components or services in the Tanzu ecosystem.

For example:

* **Tanzu Cluster Management** plugin: For managing cluster lifecycle operations.  
* **Tanzu Package Management** plugin: For managing Kubernetes packages.  
* **Tanzu Diagnostics**: For troubleshooting and inspecting clusters.

At the time of writing this document, Tanzu CLI v1.1.0 is supported with vSphere 8.0.3. For updated information, refer [here](https://docs.vmware.com/en/VMware-Tanzu-CLI/index.html#compatibility-with-vmware-tanzu-products-1). 

Download the Tanzu CLI on the bastion host using the commands provided below. Below steps involves installing the Tanzu CLI on the bastion host, which is necessary for downloading the Tanzu Plugins.

```
## Download Tanzu CLI
wget https://github.com/vmware-tanzu/tanzu-cli/releases/download/v1.1.0/tanzu-cli-linux-amd64.tar.gz

##Install Tanzu CLI on the bastion host
tar -xzvf ./tanzu-cli-linux-amd64.tar.gz

##Move to Taznu CLI to Executable Path
mv ./v1.1.0/tanzu-cli-linux_amd64 /usr/local/bin/tanzu
```

Now we have the Tanzu CLI installed on the bastion host, we can download the Tanzu vSphere Plugins using the Tanzu CLI command

```
##Command to list all available plugins
tanzu plugin group search --show-details

##Command to list the Plugins specifc to vSphere
tanzu plugin group search -n vmware-vsphere/default --show-details

##Command to Download Tanzu vSphere Plugins
tanzu plugin download-bundle --group vmware-vsphere/default:v8.0.3 --to-tar  ./vmware-vsphere-plugin.tar.gz
```

### <a id=download-tanzu-packages> </a> Download Tanzu Packages  

Tanzu Packages enable administrators and users to use the Tanzu CLI or Carvel Custom Resources to add and manage common services and add-ons on Kubernetes clusters. With Tanzu Packages, you can deploy various packages to Tanzu Kubernetes Clusters, such as cert-manager, Contour, Prometheus, Grafana, and more.

To install Tanzu Platform for Kubernetes (TPSM), cert-manager must be installed on the TKC. In this section, we will download the Tanzu packages, which can later be uploaded to Harbor(deployed as Supervisor Service) and used to install cert-manager on the TKC.

```
## Find the Latest Package version by executing below command
imgpkg tag list -i projects.registry.vmware.com/tkg/packages/standard/repo

## At the time on this document, the latest version is v2024.8.21, use below command to download the package

imgpkg copy -b projects.registry.vmware.com/tkg/packages/standard/repo:v2024.8.21 --to-tar ./tanzu-packages.tar
```

### <a id=download-trivy-db-bundle> </a> Download Trivy DB Bundle  

TPSM makes use of trivy scanner for detecting vulnerabilities in the platform and deployed applications. Since the deployment is in Internet Restricted environment, we need to download the bundle from [ghcr.io/aquasecurity/trivy-db](http://ghcr.io/aquasecurity/trivy-db) and later upload it to Harbor repository.

```
imgpkg copy -i ghcr.io/aquasecurity/trivy-db:2 --to-tar trivy-db.tar
```

### <a id=summary> </a> Summary  

In this section, the following files, binaries, and packages have been successfully downloaded and need to be transferred to the Admin host.   
The Admin host, which is a server or VM with access to the vSphere infrastructure, is assumed to have no internet connectivity, so all necessary files were downloaded using the bastion host.

* `Harbor OVA`   
* Supervisor Service packages and YAML Files  
  * Contour  
    * `contour-v1.28.2.tar`  
    * `contour.yml` and `contour-data-values.ym`l  
  * Harbor  
    * `harbor-v2.9.1.tar`  
    * `harbor.yml` and `harbor-data-values.yml`  
* Tanzu CLI `(tanzu-cli-linux_amd64)`  
* Tanzu vSphere Plugin `(vmware-vsphere-plugin.tar.gz)`  
* Tanzu Packages `(tanzu-packages.tar)`  
* TPSM bundle `(tp-k8s-1.0.0-sep-2024-rc.21-v88282bc.tar.gz)`  
* Trivy DB `(trivy-db.tar)`


## <a id=deploy-harbor-ova-in-vcenter> </a> Deploy Harbor OVA in vCenter  

Deploying the Harbor OVA follows the same process as deploying any other OVA in vCenter. During the "Customize Template" step, provide the following required details:

* All necessary passwords  
* Hostname: If using auto-generated certificates, this hostname will be included in the Subject Alt Names section, and a DNS record mapping to the corresponding IP address must be created.  
* Network Configuration (not necessary if DHCP is being used)

Additionally, the “Use Self-signed Certificate for Harbor” option can be unchecked to upload custom certificates for Harbor. If no custom certificates are uploaded, Harbor will default to using its auto-generated self-signed certificate.

![](./img/tpsm-ag-on-vsphere/deploy-harbor-ova.png)

Once Harbor is deployed and in running state, we need to obtain the harbor certificate, which is required to add it to the Admin host. To download the Harbor certificate, log in to the Harbor endpoint, navigate to *Configuration* \> *System settings*, and download the “Registry Root Certificate”.

![](./img/tpsm-ag-on-vsphere/harbor-configuration.png)

**This repository will be exclusively used for uploading the binaries necessary to enable Supervisor services like Contour and Harbor. It will not be utilized for any other purpose.**

## <a id=configure-admin-machine> </a> Configure Admin Machine  

The Admin host is essential to the deployment process, performing crucial tasks such as uploading binaries and image bundles to the repository, deploying Tanzu Kubernetes Clusters, and configuring the TPSM platform. Serving as the control center, this machine enables effective deployment management and repository coordination. 

In this document, an Ubuntu 22.04.4 machine with **Docker installed** is used as the Admin host. If Docker is not installed, refer to the [official documentation](https://docs.docker.com/engine/install/ubuntu/#install-from-a-package) for installation guidance. The recommended system configuration is as follows:

* **CPU:** 2 vCPUs  
* **Memory:** 4 GB  
* **Storage:** 150–200 GB of free space

> **Note** Before moving forward, verify that all the files mentioned in the Summary section above have been successfully copied to the Admin host.  

The Harbor OVA does not need to be transferred to this Admin host; however, it should be placed in a location accessible from vCenter to allow for direct deployment of the OVA on vCenter.

### <a id=install-carvel-tools> </a> Install Carvel Tools  

Carvel packages are essential at different stages of the TPSM deployment process. The TPSM bundle includes the necessary Carvel packages. 

```
### Untar the TPSM Bundle
tar -xvzf /<path-to-bundle>/tp-k8s-1.0.0-sep-2024-rc.21-v88282bc.tar.gz
```

After extracting the TPSM package, all necessary `tanzusm binaries` will be available, and the required Carvel packages can be found in the "`additional-resources`" folder.   
The current focus is on installing the Carvel packages. In a later section, after the Harbor Supervisor Service is enabled, the `tanzusm binaries` will be uploaded to the Harbor Supervisor Service repository.

> **Note** Avoid copying the Tanzu and kubectl binaries. Instead, utilize the vSphere-supported Tanzu version downloaded earlier, along with the “`kubectl`” and “`kubectl-vsphere`” binaries provided by the Workload Control Plane/Supervisor Cluster.  

```
cd /<path-to-bundle>/additional-resources/binaries/linux/amd64

##Copy below binaries to executable path or binary path 

cp crashd /usr/local/bin/
cp imgpkg /usr/local/bin/
cp kctrl /usr/local/bin/
cp kapp /usr/local/bin/
cp tanzu /usr/local/bin/
cp kbld /usr/local/bin/
cp velero /usr/local/bin/

##Verify the version by executing below commands
crashd version 
imgpkg version 
kctrl version
kapp version
tanzu version
kbld version
velero version
```

### <a id=download-and-install-kubectl-and-kubectl-vsphere-cli> </a> Download and Install kubectl and kubectl-vsphere CLI  

“`kubectl`” is the command-line tool used to interact with Kubernetes clusters. It allows users to manage and inspect resources within a Kubernetes environment.  
“`kubectl-vsphere`” is a VMware-specific plugin for `kubectl` that allows administrators and developers to manage VMware Tanzu Kubernetes clusters (TKC) running on vSphere. It integrates with the Supervisor Cluster (the control plane that manages Tanzu clusters) and extends `kubectl` with commands specific to VMware's Tanzu Kubernetes Grid Service.

Download the `kubectl` and `kubectl-vsphere` plugins to your Admin host by accessing the Supervisor Cluster Kube-API server endpoint, or use the command provided below.

```
wget https://<Supervisor-KubeAPI-Endpoint>/wcp/plugin/linux-amd64/vsphere-plugin.zip --no-check-certificate
```

After downloading the `vsphere-plugin.zip` file, use the following commands to unzip it and add the binaries to the executable path.

```
unzip ./vsphere-plugin.zip
cd ./bin
cp * /usr/local/bin

##Verify the version by executing below commands
kubectl version
kubectl vsphere version
```

### <a id=add-the-harbor-ova-certificate-to-trust-store> </a> Add the Harbor OVA certificate to Trust Store  

Use below commands to add the harbor certificate to Admin host's trust store. 

```
sudo cp harbor-ova.crt /usr/local/share/ca-certificates 
sudo update-ca-certificates
```

Once the certificate is added to the trust store, log in to the Harbor endpoint using Docker. If Docker is not already installed on your Admin host, follow the procedure provided [here](https://docs.docker.com/engine/install/ubuntu/#install-from-a-package) to install it.

```
##Restart Docker Service
systemctl reload docker
systemctl restart docker

##Command to Login to Harbor Endpoint
docker login <repo-endpoint>

##Enter the username and password when prompted. The expected output is shown below:
=====
WARNING! Your password will be stored unencrypted in /root/.docker/config.json.
Configure a credential helper to remove this warning. See
https://docs.docker.com/engine/reference/commandline/login/#credential-stores

Login Succeeded
=====
```

## <a id=install-contour-as-a-supervisor-service> </a> Install Contour as a Supervisor Service  

Before enabling the Harbor Supervisor Service, it is required to first enable the Contour Supervisor Service. The following steps provide the necessary guidance for enabling the Contour service in an internet-restricted environment. 

### <a id=upload-contour-binaries-to-harbor> </a> Upload Contour Binaries to Harbor  

The initial step involves uploading the Contour binaries to the Harbor image repository that was previously deployed. Follow the instructions below to upload the Contour binaries. Before uploading the Contour Binaries, create a public repo in Harbor.

![](./img/tpsm-ag-on-vsphere/new-project-sup-svcs.png)
​​  
Ensure that the “`contour-v1.28.2.tar`” has been successfully copied to the Admin host. Then, execute the following commands from the Admin host to upload the contour package to the Harbor repository:

```
##Set Environment Variables
export IMGPKG_REGISTRY_HOSTNAME_0=<repo_url>
export IMGPKG_REGISTRY_USERNAME_0=<username>
export IMGPKG_REGISTRY_PASSWORD_0=<password>


##Upload the Images to Harbor Repository

imgpkg copy --tar /<path-to-bundle>/contour-v1.28.2.tar --to-repo $IMGPKG_REGISTRY_HOSTNAME_01/<project_name>/contour-1.28.2 --cosign-signatures
```

### <a id=register-contour-supervisor-service-to-vcenter> </a> Register Contour Supervisor Service to vCenter  

Once the images have been uploaded to the local image repo, the next step is to register Contour as a Supervisor Service in vCenter. Verify that the “`contour.yml`” file has been successfully copied.

​​Update the “*template.spec.fetch.imgpkgBundle.image*” section in the `contour.yml` file as shown below, while leaving all other content unchanged. This modification redirects the images to be pulled from the local repository instead of the public repository.

```
##Original Content
 template:
   spec:
     fetch:
       - imgpkgBundle:
           image: projects.packages.broadcom.com/tkg/packages/standard/contour:v1.28.2_vmware.1-tkg.1


##Modified Content
 template:
   spec:
     fetch:
       - imgpkgBundle:
           image: <repo_url>/<project_name>/contour-1.28.2:v1.28.2_vmware.1-tkg.1

```

To add Contour as a Supervisor Service, log in to vCenter and navigate to **Workload Management** \-\> **Services**. Click on **Add New Service**, upload the modified `contour.yml` file, and then click **Finish**. The Contour service will now be active, with a status of "Active" and "1" Active Version.

![](./img/tpsm-ag-on-vsphere/add-contour-service.png)

### <a id=install-contour-service> </a> Install Contour Service  

The next step is to install the Contour Supervisor Service. Before proceeding, ensure that the `contour-data-values.yml` file has been successfully copied, as it is required for the installation.

To install the Contour Supervisor Service, click on the **ACTIONS** dropdown under the Contour service, then select **Manage Service**. Select the Supervisor Cluster and click **Next**. On the Review page, upload the contents of the `contour-data-values.yml` file in the **YAML Service Config (optional)** section, and click on **FINISH**

![](./img/tpsm-ag-on-vsphere/contour-yaml-config.png)

You will now see a new Supervisor namespace named “svc-contour-domain-xyz” created, along with the necessary Contour and Envoy vsphere pods deployed. You can check the status of this service in the **Supervisor Services Overview section** by navigating to **Workload Management** \-\> **Supervisors** \-\> Select the appropriate Supervisor Cluster \-\> **Configure**.

![](./img/tpsm-ag-on-vsphere/supervisor-services-ovw.png)

In NSX ALB, a new virtual service named ”`domain-xyz--svc-contour-domain-xyz-envoy`” will be created. The service state will appear as degraded, which is expected. Note the Virtual Service IP, as it will be needed to create a DNS record.

![](./img/tpsm-ag-on-vsphere/virtual-svcs.png)

## <a id=install-harbor-as-a-supervisor-service> </a> Install Harbor as a Supervisor Service  

The Harbor Supervisor Service provides a robust and scalable container image registry integrated with the Tanzu platform. It enables secure storage, management, and distribution of container images and Helm charts, ensuring that deployments are reliable and consistent.   
The following steps provide the necessary guidance for enabling the Harbor service in an internet-restricted environment. 

### <a id=upload-harbor-binaries-to-harbor(vm)> </a> Upload Harbor Binaries to Harbor(VM)  

During the setup of Contour, a public project was created in the temporary image repository to store the binaries needed for enabling the Supervisor Services. This existing project can be used, or a new project may be created. For the purposes of this document, the previously created project will be utilized.

Ensure that the “`harbor-v2.9.1.tar`” has been successfully copied to the Admin host. Then, execute the following commands from the Admin host to upload the harbor package to the Harbor repository:

```
##Set Environment Variables
export IMGPKG_REGISTRY_HOSTNAME_0=<repo_url>
export IMGPKG_REGISTRY_USERNAME_0=<username>
export IMGPKG_REGISTRY_PASSWORD_0=<password>


##Upload the Images to Harbor Repository

imgpkg copy --tar /<path-to-bundle>/harbor-v2.9.1.tar --to-repo $IMGPKG_REGISTRY_HOSTNAME_1/<project_name>/harbor-v2.9.1 --cosign-signatures
```

### <a id=register-harbor-supervisor-service-to-vcenter> </a> Register Harbor Supervisor Service to vCenter  

Once the images have been uploaded to the local image repo, the next step is to register Harbor as a Supervisor Service in vCenter. Verify that the “`harbor.yml`” file has been successfully copied.

​​Update the “*template.spec.fetch.imgpkgBundle.image*” section in the `harbor.yml` file as shown below, while leaving all other content unchanged. This modification redirects the images to be pulled from the local repository instead of the public repository.

```
##Original Content
 template:
   spec:
     fetch:
       - imgpkgBundle:
           image: projects.packages.broadcom.com/tkg/packages/standard/harbor:v2.9.1_vmware.1-tkg.1


##Modified Content
 template:
   spec:
     fetch:
       - imgpkgBundle:
           image: <repo_url>/<project_name>/harbor-v2.9.1:v2.9.1_vmware.1-tkg.1

```

To add Harbor as a Supervisor Service, log in to vCenter and navigate to **Workload Management** \-\> **Services**. Click on **Add New Service**, upload the modified `harbor.yml` file, and then click **Finish**. Now we have the harbor service added and the status of "Active" and "1" Active Version  
![](./img/tpsm-ag-on-vsphere/sup-svc-harbor-registered.png)

### <a id=install-harbor-service> </a> Install Harbor Service  

The next step is to install the Harbor Supervisor Service. Before proceeding, ensure that the `harbor-data-values.yml` file has been successfully copied, as it is required for the installation.

Below fields of the `harbor-data-values.yml` file must be modified as per your environment:

* `hostname` \- The fully qualified domain name (FQDN) assigned to access the Harbor UI. **The domain should be configured in an external DNS server so that it resolves to the Envoy Service IP created by Contour.**  
  In this lab setup, the Envoy Service IP obtained from NSX ALB is “192.168.21.104,” and the hostname for Harbor is set to “harbor-wcp.tanzu.lab,” with a corresponding DNS record created for it.  
* `harborAdminPassword` \- Specify a password for the Harbor Admin  
* `database.password` \- Specify a password for the PostgreSQL database  
* Provide secrets for the core service, job service, and registry service  
  * `core.secret`  
  * `jobservice.secret`  
  * `registry.secret`  
* `persistence.persistentVolumeClaim.registry.size`: The default size is 10Gi, which is insufficient for the Tanzu Plugin and TPSM binaries. It is recommended to increase it to at least 150GB, plus any additional space needed for application images.  
* For the following fields, provide the storage class name utilized for the Harbor registry PVCs.  
  * `persistence.persistentVolumeClaim.registry.storageClass`  
  * `persistence.persistentVolumeClaim.jobservice.jobLog.storageClass`  
  * `persistence.persistentVolumeClaim.database.storageClass`  
  * `persistence.persistentVolumeClaim.redis.storageClass`  
  * `persistence.persistentVolumeClaim.trivy.storageClass`

Below is a sample modified `harbor-data-values.yml` file for reference, with the modified fields highlighted.

```
#! The FQDN for accessing Harbor admin UI and Registry service.
hostname: harbor-wcp.tanzu.lab
#! The network port of the Envoy service in Contour or other Ingress Controller.
port:
 https: 443

#! Do not change tlsSecretLabels. It is required for TKG  integration to work.
tlsCertificate:
 tlsSecretLabels: {"managed-by": "vmware-vRegistry"}

#! [Required] The initial password of Harbor admin.
harborAdminPassword: VMware1!

#! [Required] The secret key used for encryption. Must be a string of 16 chars.
secretKey: 0123456789ABCDEF

database:
 #! if external database is used, set "type" to "external"
 #! and fill the connection information in "external" section
 type: internal
 #! [Required] The initial password of the internal postgres database.
 #! if external database is used, fill the external.password
 password: VMware1!

core:
 replicas: 1
 #! [Required] Secret is used when core server communicates with other components.
 secret: VMware1!
 #! [Required] The XSRF key. Must be a string of 32 chars.
 xsrfKey: 0123456789ABCDEF0123456789ABCDEF
jobservice:
 replicas: 1
 #! [Required] Secret is used when job service communicates with other components.
 secret: VMware1!
registry:
 replicas: 1
 #! [Required] Secret is used to secure the upload state from client
 #! and registry storage backend.
 #! See: https://github.com/docker/distribution/blob/master/docs/configuration.md#http
 secret: VMware1!

#! The persistence is always enabled and a default StorageClass
#! is needed in the k8s cluster to provision volumes dynamically.
#! Specify another StorageClass in the "storageClass" or set "existingClaim"
#! if you have already existing persistent volumes to use
#!
#! For storing images and charts, you can also use "azure", "gcs", "s3",
#! "swift" or "oss". Set it in the "imageChartStorage" section
persistence:
 persistentVolumeClaim:
   registry:
     #! Use the existing PVC which must be created manually before bound,
     #! and specify the "subPath" if the PVC is shared with other components
     existingClaim: ""
     #! Specify the "storageClass" used to provision the volume. Or the default
     #! StorageClass will be used(the default).
     #! Set it to "-" to disable dynamic provisioning
     storageClass: "vsan-policy-custom"
     subPath: ""
     accessMode: ReadWriteOnce
     size: 300Gi
   jobservice:
     jobLog:
       existingClaim: ""
       storageClass: "vsan-policy-custom"
       subPath: ""
       accessMode: ReadWriteOnce
       size: 1Gi
   database:
     existingClaim: ""
     storageClass: "vsan-policy-custom"
     subPath: ""
     accessMode: ReadWriteOnce
     size: 1Gi
   redis:
     existingClaim: ""
     storageClass: "vsan-policy-custom"
     subPath: ""
     accessMode: ReadWriteOnce
     size: 1Gi
   trivy:
     existingClaim: ""
     storageClass: "vsan-policy-custom"
     subPath: ""
     accessMode: ReadWriteOnce
     size: 5Gi
 #! The metrics used by core, registry and exporter
metrics:
 enabled: true
 core:
   path: /metrics
   port: 8001
 registry:
   path: /metrics
   port: 8001
 exporter:
   path: /metrics
   port: 8001

#! Default [] is equivalent to have both ["IPv4","IPv6"]. Or you can choose one of ["IPv4"] or ["IPv6"]
network:
 ipFamilies: ["IPv4"]

#! cache layer configurations
#! if this feature enabled, harbor will cache the resource
#! `project/project_metadata/repository/artifact/manifest` in the redis
#! which help to improve the performance of high concurrent pulling manifest.
cache:
 #! default is not enabled.
 enabled: false
 #! default keep cache for one day.
 expireHours: 24

```

To install the Harbor Supervisor Service, click on the **ACTIONS** dropdown under the Harbor service, then select **Manage Service**. Select the Supervisor Cluster and click **Next**. On the Review page, upload the contents of the modified `harbor-data-values.yml` file in the **YAML Service Config (optional)** section, and click on **FINISH**

![](./img/tpsm-ag-on-vsphere/harbor-yaml-config.png)

You will now see a new Supervisor namespace named “svc-harbor-domain-xyz” created, along with the necessary harbor vsphere pods deployed. You can check the status of this service in the **Supervisor Services Overview section** by navigating to **Workload Management** \-\> **Supervisors** \-\> Select the appropriate Supervisor Cluster \-\> **Configure**.

![](./img/tpsm-ag-on-vsphere/supervisor-svc-harbor.png)

With the DNS records properly configured, the Harbor Supervisor Service repository should now be accessible using the configured hostname (e.g., [https://harbor-wcp.tanzu.lab](https://harbor-wcp.tanzu.lab)).

![](./img/tpsm-ag-on-vsphere/harbor-projects-new.png)

Now we have the harbor supervisor service up and running, to ensure that harbor is trusted by the admin VM, add the Harbor certificate to the trust store. To download the Harbor certificate, log in to the Harbor endpoint, navigate to *Configuration* \> *System Settings*, and download the Registry Root Certificate.

![](./img/tpsm-ag-on-vsphere/harbor-configuration.png)

Add certificates to Admin host trust store:

```
sudo cp harbor-wcp.crt /usr/local/share/ca-certificates 
sudo update-ca-certificates
```

Once the certificate is added to the trust store, log in to the Harbor endpoint using Docker. If Docker is not already installed on your Admin host, follow the procedure provided [here](https://docs.docker.com/engine/install/ubuntu/#install-from-a-package) to install it.

```
##Restart Docker Service
systemctl reload docker
systemctl restart docker

##Command to Login to Harbor Endpoint
docker login <repo-endpoint>

##Enter the username and password when prompted. The expected output is shown below:
=====
WARNING! Your password will be stored unencrypted in /root/.docker/config.json.
Configure a credential helper to remove this warning. See
https://docs.docker.com/engine/reference/commandline/login/#credential-stores

Login Succeeded
=====
```

## <a id=install-tanzu-cli-and-plugins-on-admin-machine> </a> Install Tanzu CLI and Plugins on Admin Machine  

The “`tanzu-cli-linux_amd64`” and ”`vmware-vsphere-plugin.tar.gz`” files downloaded in the previous section will be utilized here.

Ensure that both “`tanzu-cli-linux_amd64`” and ”`vmware-vsphere-plugin.tar.gz`” files are copied from the bastion host to the Admin host. Use the following command to install the Tanzu CLI:

```
##Install Tanzu CLI on the Admin host
tar -xzvf /<path-to-bundle>/tanzu-cli-linux-amd64.tar.gz

##Move to Tanzu CLI to Executable Path
mv /<path-to-bundle>/v1.1.0/tanzu-cli-linux_amd64 /usr/local/bin/tanzu

##Verify the install using below command
tanzu version
```

With the Tanzu CLI now installed, the next step is to proceed with the Tanzu Plugin installation. First, the Tanzu plugin bundle, “`vmware-vsphere-plugin.tar.gz`,” must be uploaded to the Harbor repository before it can be installed on the local Admin host.  
> **Note** These packages are uploaded to the Harbor instance running as a Supervisor service, not to the Harbor OVA instance.  

Log in to Admin VM and perform below steps to upload the `vmware-vsphere-plugin.tar.gz` to Harbor repository (Supervisor Service)

```
##If not yet done, login to Harbor endpoint
docker login <repo-endpoint>

## Upload the Plugins to Harbor repo
tanzu plugin upload-bundle --tar <path-to-bundle>/vmware-vsphere-plugin.tar.gz --to-repo <repo-endpoint>/<project-name>/plugins

##Sample Command: 
tanzu plugin upload-bundle --tar ./vmware-vsphere-plugin.tar.gz --to-repo harbor-wcp.tanzu.lab/vsphere-tanzu-plugins/plugins	
```

Update the source repo, by default Tanzu CLI points to public repository to search/install the plugins, updating the source repo instructs Tanzu CLI to leverage the local repository

```
##Command to update the source repo
tanzu plugin source update default --uri <repo-endpoint>/<project-name>/plugins/plugin-inventory:latest


##Sample Command:
tanzu plugin source update default --uri harbor-wcp.tanzu.lab/vsphere-tanzu-plugins/plugins/plugin-inventory:latest

##Expected O/P:
[i] Reading plugin inventory for "harbor-wcp.tanzu.lab/vsphere-tanzu-plugins/plugins/plugin-inventory:latest", this will take a few seconds.
[ok] updated discovery source default
```

Install Tanzu plugins on the Admin host

```
##Command to Install Tanzu vSphere Plugins
tanzu plugin install --group vmware-vsphere/default

##Expected O/P
[i] The following plugins will be installed from plugin group 'vmware-vsphere/default:v8.0.3'
  NAME           TARGET      VERSION  
  imgpkg         global      v0.3.5   
  package        kubernetes  v0.32.1  
  pinniped-auth  global      v0.33.1  
  secret         kubernetes  v0.32.0  
[i] Installing plugin 'imgpkg:v0.3.5' with target 'global' 
[i] Installing plugin 'package:v0.32.1' with target 'kubernetes' 
[i] Installing plugin 'pinniped-auth:v0.33.1' with target 'global' 
[i] Installing plugin 'secret:v0.32.0' with target 'kubernetes' 
[ok] successfully installed all plugins from group 'vmware-vsphere/default:v8.0.3'

##Verify the plugin installation using below command
tanzu plugin list
```

## <a id=upload-tanzu-packages-to-harbor(supervisor-service)> </a> Upload Tanzu Packages to Harbor(Supervisor Service)  

Tanzu Packages enable administrators and users to use the Tanzu CLI or Carvel Custom Resources to add and manage common services and add-ons on Kubernetes clusters. With Tanzu Packages, you can deploy various packages to Tanzu Kubernetes Clusters(TKC), such as cert-manager, Contour, Prometheus, Grafana and more.

To install Tanzu Platform for Kubernetes (TPSM), “`cert-manager`” must be installed on the TKC. In this section, we will upload the Tanzu packages to the local repository, which can later be used to install ”`cert-manager`” on the TKC.

To upload Tanzu Packages to Harbor, ensure that the “`tanzu-packages.tar`” file is copied from the bastion host to the Admin host. 

> **Note** These packages are uploaded to the Harbor instance running as a Supervisor service, not to the Harbor OVA instance.  

Create a new public project in Harbor Repository(Supervisor Service)  
![](./img/tpsm-ag-on-vsphere/new-proj-tanzu-packages.png)

Copy the package to Harbor Repository(Supervisor Service)

```
##Set Environment Variables
export IMGPKG_REGISTRY_HOSTNAME_1=<repo_url>
export IMGPKG_REGISTRY_USERNAME_1=<username>
export IMGPKG_REGISTRY_PASSWORD_1=<password>

##Command to copy the binaries to local Image repositort
imgpkg copy --tar /<path-to-tarball>/tanzu-packages.tar --to-repo $IMGPKG_REGISTRY_HOSTNAME_1/<project-name>/packages/standard/repo

##Sample Command
admin	imgpkg copy --tar tanzu-packages.tar --to-repo harbor-wcp.tanzu.lab/tanzu-packages/packages/standard/repo
```

## <a id=deploy-tanzu-kubernetes-cluster(tkc)> </a> Deploy Tanzu Kubernetes Cluster (TKC)  

In this section, we will create a new Tanzu Kubernetes Cluster where the TPSM components will be installed.  
Before proceeding, ensure the following prerequisites are met:

1. A **Local Content Library** is created. Refer to the "[Create a Local Content Library (for Air-Gapped Cluster Provisioning)](https://docs.vmware.com/en/VMware-vSphere/8.0/vsphere-with-tanzu-tkg/GUID-19E8E034-5256-4EFC-BEBF-D4F17A8ED021.html)" document for instructions on creating and importing Tanzu Kubernetes Release (TKR) images into the content library.  
  > **Note** For TPSM components, Kubernetes version 1.28.x is required. You can download one of the following TKRs:  
      * ob-23661201-photon-5-amd64-vmi-k8s-v1.28.8---vmware.1-fips.1-tkg.2  
      * ob-23661482-ubuntu-2204-amd64-vmi-k8s-v1.28.8---vmware.1-fips.1-tkg.2  
2. **Tanzu Platform Self-Managed Deployment Guide for Air-Gapped Environments vSphere Namespace**: A vSphere namespace should be created (resource requirements are yet to be defined).  
   * Refer to "[Create a vSphere Namespace for Hosting TKG Service Clusters](https://docs.vmware.com/en/VMware-vSphere/8.0/vsphere-with-tanzu-tkg/GUID-525F5A4D-875B-4FA5-911D-B2D18ED00136.html)" for instructions on creating the vSphere Namespace.  
   * Refer to "[Configure a vSphere Namespace for TKG Service Clusters](https://docs.vmware.com/en/VMware-vSphere/8.0/vsphere-with-tanzu-tkg/GUID-1F93941C-75CF-4522-94B4-64B96962CDAA.html#GUID-1F93941C-75CF-4522-94B4-64B96962CDAA)" to configure the vSphere Namespace.

To deploy Tanzu Kubernetes Cluster follow below instructions

* To ensure that Tanzu Kubernetes Cluster nodes and the “kapp” controller trust the Harbor certificate, you must first create a secret in the vSphere Namespace and reference it in the TKC cluster YAML file.   
  Import the Harbor(Supervisor Service) certificate to the Admin host, and then use the following command to perform double base64 encoding:

```
base64 -w 0 /<path-to-certificate>/harbor.crt | base64 -w 0
```

* Connect to vSphere Supervisor Namespace using kubectl vsphere utility

```
##Connect to vSphere Namespace using kubectl vsphere cli
kubectl vsphere login --vsphere-username <sso_username> --server=https://<SupervisorAPIEndpoint> --insecure-skip-tls-verify --tanzu-kubernetes-cluster-namespace <vsphere-namespace>

##Sample Command
kubectl vsphere login --vsphere-username administrator@vsphere.local --server=https://w01c01-wcp.tanzu.lab --insecure-skip-tls-verify --tanzu-kubernetes-cluster-namespace ns01


##Ensure that context is set to the vSphere Namespace
kubectl config use-context <vSphere-Namespace-Name>
```

* Create an “additional-ca-1.yaml” file that includes the double base64-encoded data of the Harbor certificate. Modify the highlighted sections as necessary.   
  This parameter will be included in the TKC cluster file. Refer to the sample TKC YAML file provided in the next step for guidance.

```
##additional-ca-1.yaml
apiVersion: v1
data:
  <certName>: <Harbor Cert that is double base64-encoded>
kind: Secret
metadata:
  name: <clusterName>-user-trusted-ca-secret
  namespace: <vSphereNamespaceName>
type: Opaque


##Create create
kubectl create -f  additional-ca-1.yaml



##Sample File
------------------------
apiVersion: v1
data:
  harbor-cert: TFMwdExTMUNSVWRKVGlCRFJWSlVTVVpKUTBGVVJTMHRMUzB0Q2sxSlNVUkxSRU5EUVdoRFowRjNTVUpCWjBsUlMwNXJRMVo1VkZaWldERXhOV3c1ZG5aS1prTlhla0ZPUW1kcmNXaHJhVWM1ZHpCQ1FWRnpSa0ZFUVZVS1RWSkpkMFZCV1VSV1VWRkVSWGRzU1ZsWVNtbGlNMGxuVVRCRmQwaG9ZMDVOYWxGNFRVUkZNVTFVWjNsUFZGVjVWMmhqVGsxNlVYaE5SRVY2VFZSbmVRcFBWRlY1VjJwQlZVMVNTWGRGUVZsRVZsRlJSRVYzYkVsWldFcHBZak5KWjFFd1JYZG5aMFZwVFVFd1IwTlRjVWRUU1dJelJGRkZRa0ZSVlVGQk5FbENDa1IzUVhkblowVkxRVzlKUWtGUlJFRjBVMWN6Y0ZkVk0xRmhWM05hUlZwTFYxSnRTRU5hWlROb01EUldlRXR0YzJwMVVrdFlURzl1ZEhoM1Uxa3ZkbUlLY2xwTEswbERVRTgyZURGalpUaHRWbTlZY0dkNVJtVllSM296ZUVJM1JYcFNja1JSZUc0NGEyWnFSeko1UlRGeGIyRXJOMmxVUTFoUVEwTk5jakphWmdwRFIyRnJUVk5XY2xObmEwaEdjM3BvYjFWbVFUWmphRzlaWlhoUGN6Y3JZVVptVW5sR2NUVm1ZV3BUUjJwTVZ6RTJNbGt4V21OQ016aFRUakpzU21WdkNsaEtSa1U0YmxZNWRqWlpkamQ0Um14M1pVMVZTbXBvUjFoTVVVTXlkMVpoZVhaak1HTlJhakp3Wm1SNVJXcHZTMUJKZEVGNVYyOUtSMnRJU0VndlMyTUtRVmtyTkM5RE1FdzFXREJFTmtsSFdGcDZiMGs0VUc1WFoyZHhPVU12UW1oRlEwTlhMME42YVhadmRUQlpTbkpLY1ZwdVRuZFdkbWRrWWpjemJVdHhid281UWs4eFUzUnROVTh5V1dsTFMwRnVhemwwWkM5RFJIVnZLMFp4UkVOM1pGbGpSek5CWjAxQ1FVRkhhbVJxUWpCTlFUUkhRVEZWWkVSM1JVSXZkMUZGQ2tGM1NVTkNSRUZrUW1kT1ZraFRWVVZHYWtGVlFtZG5ja0puUlVaQ1VXTkVRVkZaU1V0M1dVSkNVVlZJUVhkSmQwUjNXVVJXVWpCVVFWRklMMEpCVlhjS1FYZEZRaTk2UVdSQ1owNVdTRkUwUlVablVWVm1jbUp2VkhkTU5XRkZjR1F6Um1KU2MzZzFTMkkwUkZvMk5UaDNSWGRaUkZaU01GSkNRWGQzUTI5SlNRcGhSMFo1V1cwNWVWa3lSWGRFVVZsS1MyOWFTV2gyWTA1QlVVVk1RbEZCUkdkblJVSkJTMGxuWTFWa2FFeEpOVXBUZGxsYVZWZEROSHBrYTNoSlNEVnNDbkJ4ZFhabFRsQnpVM0UzZDBNMFZFeFZhVWxuTWtwMmIyWlVWVXhZYzBkcFYxQjRTVmxYU1M5bVQxSXlkRzR3V1RSdWFHcGxkMmxCYTJaeVJscFFLM01LTDBsWFZtOHhUbmd6TTFrdk1qTmlaamMwUW5Od0swZzFOVVYwVTNSUlVVSm9iMUJrYVhSTVJHVkRVRXBaZUVweFQyUnhPVzlQVEhvcmJrb3JSRFpYV2dwWWMyeFZObGgwV25Oa1NXaE9kMFpZTDJka1lXMXFVbloxZFV0ckwyOU1NM0ZFSzNSc1ZVSjJWRVZWVkVRclVuUjBjV3hNTVhWaFUwZzVWRU51V0daT0NtcE1VWFpNVUU1cU5tSm5PVnBLTHpReU4xUkZXRmxVVWxsT2RVOVJhbEpCVkdWUlYybDFVMEpHZUdoT2JGcE5WUzlqWTNwTFNVMUNkbEJ6TjBGTE5VY0tSM3A1YTFadVVuaHdUakp4YUhrM01ra3pSamN2VVhCUk4wSTJibkJxV2xaU1dGZzFiQ3R1WlZkTmFsQkhNM2xHWldrNGJYZDFNV2RxUm1zOUNpMHRMUzB0UlU1RUlFTkZVbFJKUmtsRFFWUkZMUzB0TFMwSw== 
kind: Secret
metadata:
  name: ns01tkc01-user-trusted-ca-secret
  namespace: ns01
type: Opaque
------------------------
```

* Below is a sample file that can be used to deploy a Tanzu Kubernetes Cluster (using Ubuntu image). At minimum, **review each section and adjust the necessary fields as required**. For more configuration options refer “[Using the Cluster v1beta1 API](https://docs.vmware.com/en/VMware-vSphere/8.0/vsphere-with-tanzu-tkg/GUID-69E52B31-6DEC-412D-B60E-FE733156F708.html)” documentation.  
  > **Note** For the current TPSM release, it is recommended to configure 3 Control Plane nodes and 10 Worker Nodes.   
    * **Control Plane Size**:    
      * Nodes: 3 for high availability   
      * vCPUs: 4, Memory: 16GB, Storage: 40GB  
    * **Worker Node Size**:   
      * Nodes: 10 for a standard size stack   
      * vCPUs: 8, Memory: 32GB, Storage: 70GB

```
apiVersion: cluster.x-k8s.io/v1beta1
kind: Cluster
metadata:
  name: ns01tkc01
  namespace: ns01
spec:
  clusterNetwork:
    services:
      cidrBlocks: ["172.28.0.0/16"]
    pods:
      cidrBlocks: ["172.29.0.0/16"]
    serviceDomain: "cluster.local"
  topology:
    class: tanzukubernetescluster
    version: v1.28.8---vmware.1-fips.1-tkg.2
    controlPlane:
      replicas: 3
      metadata:
        annotations:
          run.tanzu.vmware.com/resolve-os-image: os-name=ubuntu
    workers:
      machineDeployments:
        - class: node-pool
          name: worker-np-gold
          replicas: 10
          metadata:
            annotations:
              run.tanzu.vmware.com/resolve-os-image: os-name=ubuntu
          variables:
            overrides:
            - name: vmClass
              value: tpk8s-best-effort
    variables:
      - name: vmClass
        value: best-effort-medium
      - name: storageClass
        value: vsan-policy-custom
      - name: defaultStorageClass
        value: vsan-policy-custom
      - name: nodePoolVolumes
        value:
          - name: containerd
            capacity:
              storage: 70Gi
            mountPath: /var/lib/containerd
            storageClass: vsan-policy-custom
          - name: kubelet
            capacity:
              storage: 15Gi
            mountPath: /var/lib/kubelet
            storageClass: vsan-policy-custom
      - name: kubeAPIServerFQDNs
        value:
          - ns01tkc01.tanzu.lab
      - name: trust
        value: 
          additionalTrustedCAs:
          - name: harbor-cert
```

* Create TKC using below command	

```
kubectl create -f <pathToTkcCofig.yaml>

##Command to check the staus of Cluster Creation
Kubectl get cluster
kubectl describe cluster <Cluster-Name>
```

### <a id=install-cert-manager> </a> Install cert Manager  

To install the cert-manager, we need to first add the package repository to the Tanzu Kubernetes Cluster

Login to TKC using the kubectl-vsphere CLI from Admin host

```
##Login to TKC
kubectl vsphere login --vsphere-username <sso_username> --server=https://<SupervisorAPIEndpoint> --insecure-skip-tls-verify --tanzu-kubernetes-cluster-namespace <vsphere-namespace> --tanzu-kubernetes-cluster-name <tkc-name>

##Sample Command
kubectl vsphere login --vsphere-username administrator@vsphere.local --server=https://w01c01-wcp.tanzu.lab --insecure-skip-tls-verify --tanzu-kubernetes-cluster-namespace ns01 --tanzu-kubernetes-cluster-name ns01tkc01
```

Add Package repository

```
##Command to add Package repository 
tanzu package repository add tanzu-standard --url <harbor-fqdn>/<project-name>/packages/standard/repo --namespace tkg-system

##Sample Command
tanzu package repository add tanzu-standard --url harbor-wcp.tanzu.lab/tanzu-packages/packages/standard/repo --namespace tkg-system
```

Ensure that the package repository is Reconciled successfully 

```
tanzu package repository list -n tkg-system

```

Create a new namespace and set the PSA to privileged

```
##Create new namespace
kubectl create ns <namespaceName>
##Set PSA to privileged
kubectl label --overwrite ns <namespaceName> pod-security.kubernetes.io/enforce=privileged

##Sample Commands
kubectl create ns my-packages
kubectl label --overwrite ns my-packages pod-security.kubernetes.io/enforce=privileged

```

Install cert-manager using below commands

```
##Command to List the versions of Cert-Manager Available
tanzu package available list cert-manager.tanzu.vmware.com -A

##Command to install the cert-manager
tanzu package install cert-manager --package cert-manager.tanzu.vmware.com --namespace <namespaceName> --version 1.7.2+vmware.3-tkg.3

##Sample Command
tanzu package install cert-manager --package cert-manager.tanzu.vmware.com --namespace my-packages --version 1.7.2+vmware.3-tkg.3
```

> **Note** In the sample commands provided, the `cert-manager` application will be deployed in the `mypackages` namespace, with all required pods created in the `cert-manager` namespace. If a namespace named `cert-manager` already exists, the package deployment will use that existing namespace.  

In case the package installation fails, label the `cert-manager` namespace with `pod-security.kubernetes.io/enforce=privileged` and delete all the ReplicaSets under the `cert-manager` namespace. This will prompt the deployment to recreate the ReplicaSets and the necessary pods.

## <a id=upload-tpsm-bundle-to-harbor-repo(supervisor-service)> </a> Upload TPSM Bundle to Harbor Repo(Supervisor Service)  

To deploy TPSM, the `tp-k8s-1.0.0-sep-2024-rc.21-v88282bc.tar.gz` and `trivy-db.tar`  
 ​​binaries that were downloaded earlier need to be uploaded to Harbor Supervisor Service Repo. Follow the instructions below to complete this step.

If not done already, ensure the `tp-k8s-1.0.0-sep-2024-rc.21-v88282bc.tar.gz` file has been copied to the Admin host, then extract the bundle using the commands provided below.

> **Note** This step may have been completed earlier during the [installation of Carvel tools](#install-carvel-tools) in the "Configure Admin Machine" section.  

```
## Extract the TPSM Bundle
tar -xvzf /<path-to-bundle>/tp-k8s-1.0.0-sep-2024-rc.21-v88282bc.tar.gz
```

Once the `tp-k8s-1.0.0-sep-2024-rc.21-v88282bc.tar.gz` file is extracted, you will find below tar bundles:

* `tanzusm-1.0.0-sep-2024-rc.21-v88282bc.tar`  
* `agent-images.tar`  
* `tanzusm-collector.tar`

All the specified tar bundles, including the **Trivy DB** bundle, must be uploaded to the Harbor repository. Before uploading the TPSM binaries, ensure that a public project is created in Harbor.

![](./img/tpsm-ag-on-vsphere/new-proj-tp4k8s.png)

### <a id=upload-tanzu-platform-sm-binaries> </a> Upload Tanzu Platform-SM Binaries  

Execute the following commands from the Admin host to upload the TPSM package to the Harbor Supervisor Service repository.

```
##Set Environment Variables
export IMGPKG_REGISTRY_HOSTNAME_1=<repo_url>
export IMGPKG_REGISTRY_USERNAME_1=<username>
export IMGPKG_REGISTRY_PASSWORD_1=<password>

## Upload the TPSM Bundle
imgpkg copy --tar /<path-to-bundle>/tanzusm-1.0.0-sep-2024-rc.21-v88282bc.tar --to-repo=$IMGPKG_REGISTRY_HOSTNAME_1/<project-name>/<TPSM-version>/repo

##Sample Commands
imgpkg copy --tar ./tanzusm-1.0.0-sep-2024-rc.21-v88282bc.tar --to-repo=harbor-wcp.tanzu.lab/tp4k8s/1.0.0-sep-2024-rc.21-v88282bc/repo
```

### <a id=upload-tmc-extensions> </a> Upload TMC Extensions  

Use the `tanzu-sm-installer` CLI to push TMC extensions(`agent-images.tar`). Within the directory where the `tp-k8s-1.0.0-sep-2024-rc.21-v88282bc.tar.gz` file was extracted, the tanzu-sm-installer CLI can be found at `./cli_bundle/linux/amd64`

```
## Set Environment Variable
export REGISTRY_USERNAME=<REGISTRY_USERNAME>
export REGISTRY_PASSWORD=<REGISTRY_PASSWORD>
export REGISTRY_ENDPOINT=<REGISTRY_URL>

##Push TMC Binaris to Repo
./cli_bundle/linux/amd64/tanzu-sm-installer push-tmc-extensions -a "${REGISTRY_USERNAME}:${REGISTRY_PASSWORD}" -r "${REGISTRY_ENDPOINT}/<project-name><tp4k8s-version>/repo" -f /<path-to-file>/agent-images.tar

##Sample Command
./cli_bundle/linux/amd64/tanzu-sm-installer push tmc-extensions -a "admin:VMware1!" -r "${REGISTRY_ENDPOINT}> </a>/tp4k8s/1.0.0-sep-2024-rc.21-v88282bc/repo" -f ./agent-images.tar
```

### <a id=upload-collector-bundle> </a> Upload Collector Bundle  

Use the `tanzu-sm-installer` CLI to push the collector bundle (`tanzusm-collector.tar`).

```
## Set Environment Variable
export REGISTRY_USERNAME=<REGISTRY_USERNAME>
export REGISTRY_PASSWORD=<REGISTRY_PASSWORD>
export REGISTRY_ENDPOINT=<REGISTRY_URL>

##Push TMC Binaris to Repo
./cli_bundle//linux/amd64/tanzu-sm-installer push collectors -a "${REGISTRY_USERNAME}> </a>:{$REGISTRY_PASSWORD}" -r "${REGISTRY_ENDPOINT}/<project-name><tp4k8s-version>/repo" -f /<path-to-file>/agent-images.tar 


##Sample Command
./cli_bundle/linux/amd64/tanzu-sm-installer push images -a "${REGISTRY_USERNAME}:${REGISTRY_PASSWORD}" -r "${REGISTRY_ENDPOINT}/tp4k8s/1.0.0-sep-2024-rc.21-v88282bc/repo" -f ./tanzusm-collector.tarls -lrth

```

### <a id=upload-trivy-db-bundle> </a> Upload Trivy DB Bundle  

Use following imgpkg command to upload the Trivy DB to Harbor Repo

```
##Set Environment Variables
export IMGPKG_REGISTRY_HOSTNAME_1=<repo_url>
export IMGPKG_REGISTRY_USERNAME_1=<username>
export IMGPKG_REGISTRY_PASSWORD_1=<password>


##Command to push the tar Bundle to Image repository
imgpkg copy --tar /<path-to-bundle>/<path-to-file.trivy-db.tar> --to-repo=$IMGPKG_REGISTRY_HOSTNAME_1/<project-name>/<tp4k8s-version>/aquasecurity/trivy-db



##Sample Commands
imgpkg copy --tar trivy-db.tar --to-repo=$IMGPKG_REGISTRY_HOSTNAME_1/tp4k8s/aquasecurity/trivy-db
```

## <a id=deploy-tpsm-on-tanzu-kubernetes-cluster> </a> Deploy TPSM on Tanzu Kubernetes Cluster  

Now we have all the required packages pushed to Harbor Supervisor repo, follow below instructions to deploy the TPSM.

​​In the folder where `tp-k8s-1.0.0-sep-2024-rc.21-v88282bc.tar.gz` was extracted, you'll find the `config.yaml` file. This file can be customized to meet specific deployment needs. At a minimum, the following sections should be modified:

1. **Ingress Configuration:**  
   * `loadBalancerIP`: Specify the static IP address for the Contour LoadBalancer, as the Contour service will be installed during the TPSM installation.  
     The IP specified here must be a free IP which is part of the VIP network range used for IaaS Control plane  
   * `host`: Provide the hostname to access the TPSM platform.  
   * `tls.certificate`: If using a custom CA certificate, provide the certificate and private key here. If left unset, TPSM will utilize cert-manager to generate self-signed certificates.  
     Private key must use PKCS8 format, otherwise we have the error \[failed to parse RSA private key\]  
     openssl pkcs8 \-topk8 \-inform PEM \-outform PEM \-nocrypt \-in $HUB\_FQDN.key \-out $HUB\_FQDN.pkcs8.key  
   *   
   * **Create a DNS record** that maps the `loadBalancerIP` to the specified hostname under the `host` section.  
2. **Storage Class (if not using a default storage class):**  
   Specify the storage class (accessible by the vSphere Namespace) for the following components:  
   * `postgresql`  
   * `clickhouse`  
   * `redis`  
   * `opensearch`  
   * `seaweedfsS3`  
   * `prometheus`  
   * `kafka`  
   * `zookeeper`  
3. **Image Registry Configuration:**  
   * `server`: Provide the image registry server details.  
   * `username` and `password`: Credentials for the registry.  
   * `CustomRegistryCertificate`: Add the registry's custom certificate.

4. Trivy Configuration: In the "trivy" section, provide the repository details for the dbRepository field to specify where the Trivy DB will be retrieved from.

```
trivy:
dbRepository: "harbor-wcp.tanzu.lab/tp4k8s/aquasecurity/trivy-db:2"
# When using SSL/TLS, Trivy can be configured to allow insecure connections to a container registry if there is no valid certificate available
# Set allowInsecureConnections to true to allow insecure server connections; false, otherwise
allowInsecureConnections: true
```

5. **Login Configuration:**  
   * You can configure either `oauth` or `ldap` (or both) for user authentication. Ensure at least one is configured.  
     If not using `oauth`, comment/remove out the relevant section, and similarly for `ldap` if not in use.  
   * If you are using any OIDC provider for authentication purpose, configure `oauth` section accordingly, you may refer to below sample configuration

```
login:
  oauthProviders:
    - name: okta.test
      configUrl: 'https://dev-1234567.okta.com/.well-known/openid-configuration'
      issuerUrl: 'https://dev-1234567.okta.com'
      scopes:
        - openid
        - email
        - groups
      loginPageLinkText: Login with Dev Okta
      clientId: 0abcdefghijkLmnOP1Q2
      secret: a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b_c3d4_1b2c3d4
      attributeMappings:
        username: email
        groups: groups
      groupMapping:
        tpAdminGroupNames:
          - 'ensemble:admin'
        tpViewerGroupNames:
          - 'ensemble:viewer'
```

   * If using LDAP, refer to below sample configuration below

```
login:
  ldap:
    url: "ldap://openldap:1389/"
    credentials:
      userDN: "cn=admin,dc=tanzu,dc=lab"
      password: password
    users:
      baseDN: "dc=tanzu,dc=lab"
      searchFilter: "cn={0}"
      mailAttribute: mail
    groups:
      baseDN: "dc=tanzu,dc=lab"
      searchFilter: "member={0}"
      searchDepth: 10
    groupMapping:
      tpAdminGroupDNs:
        - "cn=tpadmins,dc=tanzu,dc=lab"
        - "cn=tpadmins2,dc=tanzu,dc=lab"
      tpViewerGroupDNs:
        - "cn=tpviewer,dc=tanzu,dc=lab"
        - "cn=tpadmins,dc=tanzu,dc=lab"

```

> **Note** Modify the searchFiler attributes as required.

* To use Active Directory over LDAP, refer to below sample configuration below

```
login:
  ldap:
    url: "ldap://ad-dns.tanzu.lab"
    credentials:
      userDN: "cn=Administrator,cn=Users,dc=tanzu,dc=lab"
      password: "VMware1!"
    users:
      baseDN: "dc=tanzu,dc=lab"
      searchFilter: 'sAMAccountName={0}'
      mailAttribute: "mail"
    groups:
      baseDN: "dc=tanzu,dc=lab"
      searchFilter: 'member={0}'
      searchDepth: 10
    groupMapping:
      tpAdminGroupDNs:
      - 'cn=tanzuadmins,cn=Users,dc=tanzu,dc=lab'
      tpViewerGroupDNs:
```

> **Note** Modify the searchFiler attributes as required.

Below is the entire modified `config.yaml` for reference.

```
profile: standard
k8sopsProfile: standard
observabilityProfile: standard
version: '1.0.0-sep-2024-rc.21-v88282bc'
ingress:
loadBalancerIP: "192.168.21.110"
host: "tp.tanzu.lab"
tls:
  certificate: |
    -----BEGIN CERTIFICATE-----
    MIIDdjCCAl6gAwIBAgIURWTgZ7RDvcL/YhXNsaEBjbrSO1cwDQYJKoZIhvcNAQEL
    BQAwZzELMAkGA1UEBhMCSU4xCzAJBgNVBAgMAktBMRIwEAYDVQQHDAlCZW5nYWx1
    cnUxETAPBgNVBAoMCHRhbnp1bGFiMQ4wDAYDVQQLDAV0YW56dTEUMBIGA1UEAwwL
    Ki50YW56dS5sYWIwHhcNMjQwMjE4MDYwNTU2WhcNMjUwMjE3MDYwNTU2WjBnMQsw
    CQYDVQQGEwJJTjELMAkGA1UECAwCS0ExEjAQBgNVBAcMCUJlbmdhbHVydTERMA8G
    A1UECgwIdGFuenVsYWIxDjAMBgNVBAsMBXRhbnp1MRQwEgYDVQQDDAsqLnRhbnp1
    LmxhYjCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBANa/xxd7G4kxIV9A
    UH6rqsHc0zPRNTzDkO0OOLqpQHO6gpV6HMgMasCdLZPFJj9EACvtmkrSIDI9aYz+
    PSGNfoPOjMKD9PRVyfhjHskZ21oLWLNQutSfCO3SlEo3KbOoauJSZouCecL6bwhv
    niuoCGpmOdELm8sPCTbgRxT7YJBkYpuRh7PSG94t9fcfuF/FcgCGdaj+hnwgwvIP
    r4o3ckCGt34wQzp5ZLp6vHW0KcxAiIUlahVoAGMCwWtXoJuq9li1e6uGXT/4+pkk
    Hr1G3nkdrFiwWiRHoyrgIHNbFq3EQSjkFSyN+vwrAVbje3+7Bes4C7tKLi/jpPY1
    7ODuVVkCAwEAAaMaMBgwFgYDVR0RBA8wDYILKi50YW56dS5sYWIwDQYJKoZIhvcN
    AQELBQADggEBAAF2V8n0l1N/GmObHNuD154Ddion9sQ3X8ZZXhngv8jQCGjDPwHK
    c2B+F5KPKdjJQNYmge6HE9zhva/JdQsAiU+XwODfcl+4vMn6Xxb7C5c9Btn4J+WH
    ivURJ4E5OTShtjjhCgwxycZg0z/ii0vV9dl6SMSXMm04PmF1rEm08WGy3zIM1h/a
    xmRPJlCgTArx0S3qzG3F+9KGriIzg4oUD3DxnK2DUVRH7aDCGJ1xhqyhnZ7G23ng
    9VhfnGm2hkwar3NZUBqE1K2X+5lOXJgcBOMuWonMXFM6ST/R1ySM4WGVSkcb0RVI
    rYd6wObgAhAVyT9n8klVG1082/ZM48W75C4=
    -----END CERTIFICATE-----
  privateKey: |
    -----BEGIN PRIVATE KEY-----
    MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDWv8cXexuJMSFf
    QFB+q6rB3NMz0TU8w5DtDji6qUBzuoKVehzIDGrAnS2TxSY/RAAr7ZpK0iAyPWmM
    /j0hjX6DzozCg/T0Vcn4Yx7JGdtaC1izULrUnwjt0pRKNymzqGriUmaLgnnC+m8I
    b54rqAhqZjnRC5vLDwk24EcU+2CQZGKbkYez0hveLfX3H7hfxXIAhnWo/oZ8IMLy
    D6+KN3JAhrd+MEM6eWS6erx1tCnMQIiFJWoVaABjAsFrV6CbqvZYtXurhl0/+PqZ
    JB69Rt55HaxYsFokR6Mq4CBzWxatxEEo5BUsjfr8KwFW43t/uwXrOAu7Si4v46T2
    Nezg7lVZAgMBAAECggEAAfbzDYuX/UWyzutmznTA58TUGVJpz2WvBVcRe1Kw/imb
    XXq/eXc4K9uG7kmPRPngDM3xm5mLVarGaisJcXEZEoALhHw3tKKZdH+FUJ9tZOD7
    Y81bUG92+sRZtzRhPZunxJA1yRiYMfDN9Aw8JYfZf/ixzz5bvHNTznYs5TE7YjD/
    gZv7wsRMWu0m/ls7aCyMB+ezLHN8bIMqikuj+gDJu9N31SZzpJsn1wL4xJTn219C
    yJ2+y4Ydlh96C80+6LMCQXXWpWQhSUPQMP6WC+Ury7rWSSoZTrDzc52dZhqY+2mh
    AzQSx6cQxi4xIp3kZZE2LbuOSnql7iIgSaJs27oxsQKBgQD7As+ZfJsQE5GjwJQB
    6PIDhlR+ag0d0E5f2WUUqGtl/bZhF5Gc/dl6Jb+b2iDpP9emxa30u///DKGXzB7J
    AqV/oxFdmbsvsaWGPiPGIO8OF6z1I6ZzlIkIcRoZsFGNDQVIss62nnv3SLV3tCsh
    AYVmWhIlvoibts2cVgbIkJ8E6QKBgQDbBHW/YQb4q+gpLCkZmoD2RPBBZEVC+skG
    TKmELF/ttRpimiNp4mfmMUFo37K7Z26iAOZWWxlV9ceR4tgE4uSkP6xcyLFrKwAc
    1Lx5u5pesB/f6s/5i3EMPIkKR6rTV3X46xW58wbL0phfhikZJ1//B/dCYedSJxVL
    6TTbDutG8QKBgQCmgSHWrbpqeqCkYC2N6skHH4dS5+RVf4VNvXZ4spOzbw4Y77pu
    ylEF3p5wsswcDXZusTiIXGEe/XD/sa5GJpRDy5bMYRqzM4MaPoQafGQ3E+tuHTzf
    9IrF58ipe7VM/HMh20KWDyEqUrfVdNUbKtgjoeHh2bbim+teJg6P4qcpaQKBgCAY
    czjsex0N9CO0eQFrhuKQD7VFgHDkV3k42s6nwhcPpyIz/GST7S3qoe9AeOzFp4zO
    HPMivn++WNSkLYvpxB/dxOCD+Jv/3TBcbJJaT7D4lnM18exb5uEoLdz3y6zU8FDe
    An0RhDlyTyoQew1Ym9S/0hhESKXdXF2Xe0tu0EPBAoGBAN8PGMIT/TwV6+4RemDR
    EMKaBcvI7LPKYjEHoKYWlBkI0Pdu6GNQ1krqz8CLiyI7p2mQ6vINIV/FXG8crHOr
    5036TXA7Ta68OliIV+8VW6hMrXTJz9yGKkZztpJ2afWZWwR3lxWDoNNNRiFRtPQ9
    CTby4yIk0RvSJcqsPzMBLJl+
    -----END PRIVATE KEY-----
deployment:
airGapped: true
trivy:
dbRepository: "harbor-wcp.tanzu.lab/tp4k8s-repo/aquasecurity/trivy-db:2"
allowInsecureConnections: true
postgresql:
storageClass: "vsan-policy-custom"
clickhouse:
storageClass: "vsan-policy-custom"
redis:
storageClass: "vsan-policy-custom"
opensearch:
storageClass: "vsan-policy-custom"
seaweedfsS3:
storageClass: "vsan-policy-custom"
prometheus:
storageClass: "vsan-policy-custom"
kafka:
storageClass: "vsan-policy-custom"
zookeeper:
storageClass: "vsan-policy-custom"
idpGroups:
adminGroup: tanzuhubadmin
viewerGroup: tanzuhubviewer
imageRegistry:
server: "harbor-wcp.tanzu.lab"
username: "admin"
password: "VMware1!"
CustomRegistryCertificate: |
-----BEGIN CERTIFICATE-----
MIIDKDCCAhCgAwIBAgIQKNkCVyTVYX115l9vvJfCWzANBgkqhkiG9w0BAQsFADAU
MRIwEAYDVQQDEwlIYXJib3IgQ0EwHhcNMjQxMDE1MTgyOTUyWhcNMzQxMDEzMTgy
OTUyWjAUMRIwEAYDVQQDEwlIYXJib3IgQ0EwggEiMA0GCSqGSIb3DQEBAQUAA4IB
DwAwggEKAoIBAQDAtSW3pWU3QaWsZEZKWRmHCZe3h04VxKmsjuRKXLontxwSY/vb
rZK+ICPO6x1ce8mVoXpgyFeXGz3xB7EzRrDQxn8kfjG2yE1qoa+7iTCXPCCMr2Zf
CGakMSVrSgkHFszhoUfA6choYexOs7+aFfRyFq5fajSGjLW162Y1ZcB38SN2lJeo
XJFE8nV9v6Yv7xFlweMUJjhGXLQC2wVayvc0cQj2pfdyEjoKPItAyWoJGkHHH/Kc
AY+4/C0L5X0D6IGXZzoI8PnWggq9C/BhECCW/Czivou0YJrJqZnNwVvgdb73mKqo
9BO1Stm5O2YiKKAnk9td/CDuo+FqDCwdYcG3AgMBAAGjdjB0MA4GA1UdDwEB/wQE
AwICBDAdBgNVHSUEFjAUBggrBgEFBQcDAQYIKwYBBQUHAwIwDwYDVR0TAQH/BAUw
AwEB/zAdBgNVHQ4EFgQUfrboTwL5aEpd3FbRsx5Kb4DZ658wEwYDVR0RBAwwCoII
aGFyYm9yY2EwDQYJKoZIhvcNAQELBQADggEBAKIgcUdhLI5JSvYZUWC4zdkxIH5l
pquveNPsSq7wC4TLUiIg2JvofTULXsGiWPxIYWI/fOR2tn0Y4nhjewiAkfrFZP+s
/IWVo1Nx33Y/23bf74Bsp+H55EtStQQBhoPditLDeCPJYxJqOdq9oOLz+nJ+D6WZ
XslU6XtZsdIhNwFX/gdamjRvuuKk/oL3qD+tlUBvTEUTD+RttqlL1uaSH9TCnXfN
jLQvLPNj6bg9ZJ/427TEXYTRYNuOQjRATeQWiuSBFxhNlZMU/cczKIMBvPs7AK5G
GzykVnRxpN2qhy72I3F7/QpQ7B6npjZVRXX5l+neWMjPG3yFei8mwu1gjFk=
-----END CERTIFICATE-----
login:
ldap:
  url: "ldap://ad-dns.tanzu.lab"
  credentials:
    userDN: "cn=Administrator,cn=Users,dc=tanzu,dc=lab"
    password: "VMware1!"
  users:
    baseDN: "dc=tanzu,dc=lab"
    searchFilter: 'sAMAccountName={0}'
    mailAttribute: "mail"
  groups:
    baseDN: "dc=tanzu,dc=lab"
    searchFilter: 'member={0}'
    searchDepth: 10
  groupMapping:
    tpAdminGroupDNs:
    - 'cn=tanzuadmins,cn=Users,dc=tanzu,dc=lab'
    tpViewerGroupDNs:
    - 'cn=tanzuview,cn=Users,dc=tanzu,dc=lab'
organization:
name: "poc0f1a"
internal:
excludedComponents:
  - raas
  - ucp
  - ucp-repos
  - ucp-ingestion-service
  - ensemble-ucp
  - ensemble-build-service
  - ensemble-provider-service
  - ensemble-tac


```

Now the config.yaml file is ready, we can perform the pre-check and proceed with the deployment

* Ensure that you are logged into the Tanzu Kubernetes Cluster with the kubectl context set for the cluster.

```
##Login to TKC
kubectl vsphere login --vsphere-username <sso_username> --server=https://<SupervisorAPIEndpoint> --insecure-skip-tls-verify --tanzu-kubernetes-cluster-namespace <vsphere-namespace> --tanzu-kubernetes-cluster-name <tkc-name>

##Sample Command
kubectl vsphere login --vsphere-username administrator@vsphere.local --server=https://w01c01-wcp.tanzu.lab --insecure-skip-tls-verify --tanzu-kubernetes-cluster-namespace ns01 --tanzu-kubernetes-cluster-name ns01tkc01
```

* Perform Pre-Check validation

```

export TANZU_SM_VERSION=1.0.0-sep-2024-rc.21-v88282bc
export REGISTRY_USERNAME=<REGISTRY_USERNAME>
export REGISTRY_PASSWORD=<REGISTRY_PASSWORD>
export REGISTRY_ENDPOINT=<REGISTRY_URL>

##Command to perform pre-verify
./cli_bundle/linux/amd64/tanzu-sm-installer verify -f ./config.yaml -u "${REGISTRY_USERNAME}:${REGISTRY_PASSWORD}" -r ${REGISTRY_ENDPOINT}/<Repo/ProjectName>/${TANZU_SM_VERSION}/repo --install-version ${TANZU_SM_VERSION}


##Sample Command
./cli_bundle/linux/amd64/tanzu-sm-installer verify -f ./config.yaml -u "${REGISTRY_USERNAME}:${REGISTRY_PASSWORD}" -r ${REGISTRY_ENDPOINT}/tp4k8s/${TANZU_SM_VERSION}/repo --install-version ${TANZU_SM_VERSION}

##Sample Command without using Env Variables
./cli_bundle/linux/amd64/tanzu-sm-installer verify -f ./config.yaml -u "admin:VMware1!" -r harbor-wcp.tanzu.lab/tp4k8s/1.0.0-sep-2024-rc.21-v88282bc/repo --install-version 1.0.0-sep-2024-rc.21-v88282bc
```

* Initiate the TPSM Deployment

```
##Command to Initiate the Installation

./cli_bundle/linux/amd64/tanzu-sm-installer install -f ./config.yaml -u "${REGISTRY_USERNAME}:${REGISTRY_PASSWORD}" -r ${REGISTRY_ENDPOINT}/<Repo/ProjectName>/${TANZU_SM_VERSION}/repo --install-version ${TANZU_SM_VERSION}


##Sample Command
./cli_bundle/linux/amd64/tanzu-sm-installer install -f ./config.yaml -u "${REGISTRY_USERNAME}:${REGISTRY_PASSWORD}" -r ${REGISTRY_ENDPOINT}/tp4k8s/${TANZU_SM_VERSION}/repo --install-version ${TANZU_SM_VERSION}

##Sample Command without using Env Variables
./cli_bundle/linux/amd64/tanzu-sm-installer install -f ./config.yaml -u "admin:VMware1!" -r harbor-wcp.tanzu.lab/tp4k8s/1.0.0-sep-2024-rc.21-v88282bc/repo --install-version 1.0.0-sep-2024-rc.21-v88282bc
```

* After successfully deploying TPSM, use the following commands to verify that all required applications/packages have been installed and are in a "`Reconcile succeeded`" state.

```
##Command to check the status of Applications/Packages
kubectl get apps -n tanzusm
```

* Next, access the TPSM portal using the hostname specified in the configuration file:

```
https://<Host-FQDN>/hub
```

* To begin administrative tasks, log in with users who are part of the `tpAdminGroupDNs` group. For view-only access, log in with users associated with the `tpViewerGroupDNs` group.

![](./img/tpsm-ag-on-vsphere/tpsm-home.png)


&nbsp; 
