# Tanzu Validated Solutions

## Branch/Build

No versioning is used, `main` contains latest always.

[Staging](https://author-techdocs2-prod.adobecqms.net/content/broadcom/techdocs/us/en/vmware-tanzu/reference-architectures/tanzu-data-reference-architecture/documentation/tanzu-data-ra/reference-designs-index-tanzu-data.html)<br>
[Prod](https://techdocs.broadcom.com/us/en/vmware-tanzu/reference-architectures/tanzu-data-reference-architecture/documentation/tanzu-data-ra/reference-designs-index-tanzu-data.html)<br>
[DocWork Build](https://docworks.broadcom.net/one/scene?permalink=uniqueId%3DMarkdown-Project-5351)

## Overview

This repository provides Reference Designs and Deployment Guides for Tanzu products. This content represents best-practices advice for designing and deploying Tanzu solutions to production environments.

## Current Reference Designs

### Tanzu Kubernetes for Operations (TKO)

- [TKO Reference Architecture 1.6](./src/reference-designs/index.md)
- [TKO on Public Cloud Reference Designs and Deployment](./src/tko-cloud-section.md)
    - [TKO on VMware Cloud on AWS Reference Design](./src/reference-designs/tko-on-vmc-aws.md)
        - [Deploy TKOs on VMware Cloud on AWS](./src/deployment-guides/tko-in-vmc-aws.md)
    - [TKO on AWS Reference Design](./src/reference-designs/tko-on-aws.md)
        - [Deploy TKOs on AWS](./src/deployment-guides/tko-aws.md)
    - [TKO on Microsoft Azure Reference Design](./src/reference-designs/tko-on-azure.md)
        - [Deploy TKOs on Microsoft Azure](./src/deployment-guides/tko-on-azure.md)
- [TKO on vSphere Reference Designs and Deployment](./src/tko-vsphere-section.md)
    - [TKO on vSphere Reference Design](./src/reference-designs/tko-on-vsphere.md)
        - [Deploy TKOs on vSphere](./src/deployment-guides/tko-on-vsphere.md)
    - [TKO on vSphere with NSX-T Reference Design](./src/reference-designs/tko-on-vsphere-nsx.md)
        - [Deploy TKO on VMware vSphere with VMware NSX-T](./src/deployment-guides/tko-on-vsphere-nsxt.md)
- [TKO on vSphere with Tanzu Reference Designs and Deployment](./src/tko-vsphere-with-tanzu-section.md)
    - [TKO using vSphere with Tanzu Reference Design](./src/reference-designs/tko-on-vsphere-with-tanzu.md)
        - [Deploy TKOs using vSphere with Tanzu](./src/deployment-guides/tko-on-vsphere-with-tanzu.md)
    - [TKO using vSphere with Tanzu on NSX-T Reference Design](./src/reference-designs/tko-on-vsphere-with-tanzu-nsxt.md)

## Tanzu Kubernetes Grid (TKG)
- [Authentication with Pinniped](./src/reference-designs/pinniped-with-tkg.md)
- [Prepare External Identity Management](./src/deployment-guides/pinniped-with-tkg.md)
- [Enable Data Protection on a Workload Cluster and Configure Backup](./src/deployment-guides/tkg-data-protection.md)

> **NOTE**: An appendix containing additional helpful documents such as troubleshooting guides and recommended labs can be found [here](src/partials)

## Contributing

The tanzu-validated-solutions project team welcomes contributions from the community. Before you start working with tanzu-validated-solutions, please
read our [Developer Certificate of Origin](https://cla.vmware.com/dco). All contributions to this repository must be
signed as described on that page. Your signature certifies that you wrote the patch or have the right to pass it on
as an open-source patch. For more detailed information, refer to [CONTRIBUTING.md](CONTRIBUTING.md).

Please also review our [Contributing Guide](CONTRIBUTING.md) and [testing documentation](TESTING.md) for information on how to effectively provide content and feedback.

## License

This content in this repository is licensed under the [Creative Commons Attribution-ShareAlike 4.0 International Public License](LICENSE-CC-Attribution-ShareAlike4.0)
