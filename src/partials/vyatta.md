# Simulating TKO on vSphere with Tanzu networking utilizing Vyatta

> **Note**: this alternative networking implementation is intended for **testing purposes only**.

vSphere distributed switches operate at Layer 2. Therefore, you might need to provision a router that can create the network in the guide that you are following.

[Vyatta VyOS](https://vyos.io) is a lightweight network OS that provides packet forwarding and DHCP services. This section will guide you through setting up a simple Vyatta router in your lab that can simulate the reference architecture network diagram.

Out-of-scope alternatives:

* VMware NSX-T
* [Enable IP packet forwarding](https://linuxhint.com/enable_ip_forwarding_ipv4_debian_linux/)

[Download](https://vyos.net/get/nightly-builds/) the ISO for the latest rolling release and [follow the instructions](https://docs.vyos.io/en/latest/installation/install.html#live-installation) to install it onto an ESXi VM.

Ensure that this VM:

* Has at least two vCPUs,
* Has one NIC per port group created in the guide that you are following, and
* That all NICs are para-virtual VMXNET NICs

If you have `govc` installed, you can use the command below to generate this
VM for your specific guide. For example, if you are using the
'tko-with-vsphere' deployment guide, the command below will generate a VM
appropriate for this lab:

```sh
DEPLOYMENT_GUIDE="tko-on-sphere.md" # <-- change this
VM_NAME="tkg-router"
govc vm.create -annotation="TKG Networking Fabric" \
  -c=2 -iso=isos/vyos.iso \
  -m=2048 \
  -disk=20GB \
  -net="VM Network" \
  -net.adapter=vmxnet3 "$VM_NAME";
while read -r net; \
do \
  name="$(awk -F '|' '{print $3}' <<< "$net" | sed 's/management/mgmt/g' | tr -d ' ')"; \
  if test "$(wc -c <<< "$name")" -gt 12; then name=$(head -c 10 <<< "$name"); fi; \
  cidr="$(awk -F '|' '{print $4}' <<< "$net" | sed -E 's/ +//' | tr -d ' ' | tr '/' '_')"; \
  cmd="govc host.portgroup.add -vswitch vSwitch0 ${name}-${cidr}"; \
  echo "--> $cmd"; \
  $cmd; \
  govc host.portgroup.change -allow-promiscuous=true -forged-transmits=true -mac-changes=true "${name}-${cidr}"; \
  govc vm.network.add -vm="$VM_NAME" -net="${name}-${cidr}" -net.adapter=vmxnet3; \
done < <(grep --color -E 'Network([ ]{1,})?\|.*_pg([ ]{1,})?\|([ ]{1,})?172.*' "src/deployment-guides/${DEPLOYMENT_GUIDE}.md")
```
>
If your VM's NICs are connected to a port group on a distributed virtual
switch, use this instead:
>
```sh
DEPLOYMENT_GUIDE="tko-on-sphere.md" # <-- change this
VM_NAME="tkg-router"
govc vm.create -annotation="TKG Networking Fabric" \
  -c=2 -iso=isos/vyos.iso \
  -m=2048 \
  -disk=20GB \
  -net="VM Network" \
  -net.adapter=vmxnet3 "$VM_NAME";
while read -r net; \
do \
  name="$(awk -F '|' '{print $3}' <<< "$net" | sed 's/management/mgmt/g' | tr -d ' ')"; \
  if test "$(wc -c <<< "$name")" -gt 12; then name=$(head -c 10 <<< "$name"); fi; \
  cidr="$(awk -F '|' '{print $4}' <<< "$net" | sed -E 's/ +//' | tr -d ' ' | tr '/' '_')"; \
  cmd="govc dvs.portgroup.add -dvs vSwitch0 ${name}-${cidr}"; \
  echo "--> $cmd"; \
  $cmd; \
  govc vm.network.add -vm="$VM_NAME" -net="${name}-${cidr}" -net.adapter=vmxnet3; \
done < <(grep --color -E 'Network([ ]{1,})?\|.*_pg([ ]{1,})?\|([ ]{1,})?172.*' "src/deployment-guides/${DEPLOYMENT_GUIDE}.md")
```

Next, go into the vCenter portal and connect to the VM's console. Log in with the username `vyos` and the password `vyos`.

Next, install VyOS onto the machine's disk. Type `install image`, follow the instructions, then shut the machine down, disconnect its CD-ROM drive, then power it on and log in again.

Next, configure your WAN interface. We'll assume that the externally-accessible network is on subnet `10.213.234.0/24`

Next, run `ifconfig eth0`. Take note of the MAC address for this interface. In vCenter, ensure that the NIC created for this VM with this MAC address is connected to your external network.

We'll assume that your externally-accessible NIC is `eth0`.

Once confirmed, assign this interface with a static IP address in its subnet:

```text
configure
set interface loopback lo # Might already exist
set interface ethernet eth0 address 10.213.234.4/24
set interfaces ethernet eth0 description WAN
set protocols static route 0.0.0.0/0 next-hop 10.213.234.1
```

Next, turn on SSH:

```text
set service ssh
```

Finally, commit and save your changes:

```text
commit
save
```

Run `ifconfig eth0` again. Verify that its `inet` address matches the IP address
you provided earlier (`10.213.234.4` in this case).

Next, verify that your router can communicate with the Internet by using
`traceroute` to a known IP address, like 1.1.1.1:

```text
traceroute to 1.1.1.1 (1.1.1.1), 30 hops max, 60 byte packets
 1  10.213.234.1 (10.213.234.1)  0.257 ms  0.248 ms  0.224 ms
...more hops
15  1.1.1.1 (1.1.1.1)  5.170 ms 172.68.188.20 (172.68.188.20)  5.717 ms 1.1.1.1 (1.1.1.1)  5.179 ms
```

Next, SSH into the router from your machine:

```sh
# password is vyos
ssh vyos@10.213.234.4
```

Once connected, configure the rest of the interfaces. First, run `ifconfig` to
see which device corresponds to each MAC address. Take note of this.

Next, enter configuration mode:

```text
configure
```

then repeat the block below for each interface.

```text
set interface eth1 address 172.16.10.1/24
# Name this after the port group for each subnet
set interface eth1 description "nsx_alb_management_pg"
```

If you have `govc`, `jq` and `sshpass` installed, you can do this easily with
this block of code. This code assumes that your port groups were created using
the block of code above.
>
```sh
VYOS_IP=10.220.3.252
ifaces=$(sshpass -p vyos ssh vyos@$VYOS_IP
  find /sys/class/net -mindepth 1 -maxdepth 1
  -not -name lo -printf "%P: " -execdir 'cat {}/address \;')
govc vm.info -json=true $VM_NAME |
  jq -r '.VirtualMachines[0].Config.Hardware.Device[] | \
select(.MacAddress != null and .DeviceInfo.Summary != "VM Network") | \
.MacAddress + ";" + .DeviceInfo.Summary' |
  while read -r line;
  do
    mac=$(echo "$line" | cut -f1 -d ';');
    pg=$(echo "$line" | cut -f2 -d ';');
    gw=$(echo "$pg" | cut -f2 -d '-' | cut -f1 -d '_');
    eth=$(grep "$mac" <<< "$ifaces" | cut -f1 -d ':');
    echo "set interface ethernet $eth ${gw}/27";
    echo "set interface ethernet description $pg";
  done
```
>
If your NICs are connected to a distributed vSwitch, use this instead:
>
```sh
VYOS_IP=10.220.8.189
>&2 echo '---> Grabbing portgroup names';
portgroupNamesToKeys=$(h2o_govc find / -type DistributedVirtualPortgroup | \
  while read -r pg; \
  do \
    h2o_govc object.collect -json=true "$pg" | jq -r '.[] |
select(.Name == "config") | .Val.Key + ":" + .Val.Name'; \
  done
);
>&2 echo '---> Grabbing interfaces';
ifaces=$(sshpass -p vyos ssh vyos@$VYOS_IP find /sys/class/net -mindepth 1 -maxdepth 1 \
  -not -name lo -printf "%P: " -execdir 'cat {}/address \;');
>&2 echo '---> Forming vyos interface commands';
h2o_govc vm.info -json=true $VM_NAME |
  jq -r '.VirtualMachines[0].Config.Hardware.Device[] |
select(.MacAddress != null) |
.MacAddress + ";" + .Backing.Port.PortgroupKey' |
  while read -r line;
  do
    mac=$(echo "$line" | cut -f1 -d ';');
    pgKey=$(echo "$line" | cut -f2 -d ';');
    pg=$(grep -E "^$pgKey" <<< "$portgroupNamesToKeys" | cut -f2 -d ':');
    gw=$(echo "$pg" | cut -f2 -d '-' | cut -f1 -d '_');
    eth=$(grep "$mac" <<< "$ifaces" | cut -f1 -d ':');
    test "$eth" == "eth0" && continue;
    echo "set interface ethernet $eth ${gw}/27";
    echo "set interface ethernet description $pg";
  done
```

Run `show interface ethernet` once done. Confirm that your result looks something like
the below:

```text
 ethernet eth0 {
     address 10.213.234.4/24
     description WAN
     hw-id 00:50:56:be:3c:b9
 }
 ethernet eth1 {
+    address 172.16.80.1/27
+    description "NSX ALB Management Network"
     hw-id 00:50:56:be:9a:f9
 }
 ethernet eth2 {
+    address 172.16.81.1/27
+    description "TKG Management Network"
     hw-id 00:50:56:be:85:fc
 }
 ethernet eth3 {
+    address 172.16.82.1/27
+    description "TKG VIP Network"
     hw-id 00:50:56:be:b5:fc
 }
 ethernet eth4 {
+    address 172.16.83.1/27
     hw-id 00:50:56:be:6b:c9
 }
[edit]
```

Next, enable the DHCP service and create two DHCP pools:

<!-- markdownlint-disable-->
```sh
NSX_ALB_MGMT_NETWORK_PREFIX="172.16.10"
TKG_MGMT_NETWORK_PREFIX="172.16.40"
TKG_WORKLOAD_NETWORK_PREFIX="172.160.70"
NAMESERVERS="8.8.8.8,4.4.4.4" # Replace these with your actual nameservers
set service dhcp-server dynamic-dns-update
set service dhcp-server shared-network-name nsx-alb-mgmt-network subnet $NSX_ALB_MGMT_NETWORK_PREFIX.0/24
set service dhcp-server shared-network-name nsx-alb-mgmt-network subnet $NSX_ALB_MGMT_NETWORK_PREFIX.0/24 default-router $NSX_ALB_MGMT_NETWORK_PREFIX.1
set service dhcp-server shared-network-name nsx-alb-mgmt-network subnet $NSX_ALB_MGMT_NETWORK_PREFIX.0/24 range 0 start $NSX_ALB_MGMT_NETWORK_PREFIX.200
set service dhcp-server shared-network-name nsx-alb-mgmt-network subnet $NSX_ALB_MGMT_NETWORK_PREFIX.0/24 range 0 stop $NSX_ALB_MGMT_NETWORK_PREFIX.252

set service dhcp-server shared-network-name tkg-mgmt-network subnet $TKG_MGMT_NETWORK_PREFIX.0/24
set service dhcp-server shared-network-name tkg-mgmt-network subnet $TKG_MGMT_NETWORK_PREFIX.0/24 default-router $TKG_MGMT_NETWORK_PREFIX.1
set service dhcp-server shared-network-name tkg-mgmt-network subnet $TKG_MGMT_NETWORK_PREFIX.0/24 range 0 start $TKG_MGMT_NETWORK_PREFIX.200
set service dhcp-server shared-network-name tkg-mgmt-network subnet $TKG_MGMT_NETWORK_PREFIX.0/24 range 0 stop $TKG_MGMT_NETWORK_PREFIX.252

set service dhcp-server shared-network-name tkg-workload-network subnet $TKG_WORKLOAD_NETWORK_PREFIX.0/24
set service dhcp-server shared-network-name tkg-workload-network subnet $TKG_WORKLOAD_NETWORK_PREFIX.0/24 default-router $TKG_WORKLOAD_NETWORK_PREFIX.1
set service dhcp-server shared-network-name tkg-workload-network subnet $TKG_WORKLOAD_NETWORK_PREFIX.0/24 range 0 start $TKG_WORKLOAD_NETWORK_PREFIX.200
set service dhcp-server shared-network-name tkg-workload-network subnet $TKG_WORKLOAD_NETWORK_PREFIX.0/24 range 0 stop $TKG_WORKLOAD_NETWORK_PREFIX.252

echo "$NAMESERVERS" | tr ',' '\n' | while read -r nameserver
do
  for net in nsx-alb-mgmt-network tkg-mgmt-network tkg-workload-network
  do set service dhcp-server shared-network-name "$net" name-server "$nameserver"
  done
done
```
<!-- markdownlint-enable-->

Confirm that this is correct with `show service dhcp-server`. Your output should
look like the below:

```
 shared-network-name nsx-alb-mgmt-network {
     authoritative
     name-server 10.213.234.252
     subnet 172.16.80.0/24 {
         default-router 172.16.80.1
         domain-name tkg.local
         domain-search tkg.local,pez.vmware.com
         name-server 10.213.234.252
         range 0 {
             start 172.16.80.200
             stop 172.16.80.252
         }
     }
 }
 shared-network-name tkg-mgmt-network {
     authoritative
     domain-name tkg.local
     domain-search tkg.local,pez.vmware.com
     name-server 10.213.234.252
     name-server 10.192.2.10
     name-server 10.192.2.11
     subnet 172.16.81.0/24 {
         default-router 172.16.81.1
         range 0 {
             start 172.16.81.200
             stop 172.16.81.252
         }
     }
 }
 shared-network-name tkg-workload-network {
     authoritative
     subnet 172.16.82.0/24 {
         default-router 172.16.82.1
         domain-name tkg.local
         domain-search tkg.local,pez.vmware.com
         name-server 10.213.234.252
         name-server 10.192.2.10
         name-server 10.192.2.11
         range 0 {
             start 172.16.82.200
             stop 172.16.82.252
         }
     }
 }
```

Next, enable NAT so that machines connected to these networks can access the
Internet through the externally-accessible interface:

```text
set nat source rule 1 description "allow nat outbound"
set nat source rule 1 outbound-interface eth0
set nat source rule 1 translation address masquerade
```

Confirm that this is correct with `show nat`. Your output should look like the
below:

```text
+source {
+    rule 1 {
+        description "allow nat outbound"
+        outbound-interface eth0
+        translation {
+            address masquerade
+        }
+    }
+}
[edit]
```

Finally, commit and save your changes.

```sh
commit
save
```

You can terminate your SSH session once finished.
