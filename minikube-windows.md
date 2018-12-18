# Set up Kubernetes development environment on Windows

## Prerequisites

To make Minikube use your local storage instead of your network storage,
define a user-scoped environment variable `MINIKUBE_HOME=%USERPROFILE%`.
Your Minikube VMs will now be creates on your C: drive instead G:.

To install the tools we need, we use [Chocolatey](https://chocolatey.org),
a package manager for Windows.
Besides the tools mentioned in this guide, you can set up your whole development
environment with it.
Make sure that you update your packages regularly using `choco upgrade all`.

Run the following commands in an administrative PowerShell.

```powershell
# Set execution policy to a defined value.
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned

# Install Chocolatey.
Set-ExecutionPolicy Bypass -Scope Process -Force; `
  iex ((New-Object System.Net.WebClient).DownloadString(`
  'https://chocolatey.org/install.ps1'))

# Re-open your shell

# Install packages
choco install minikube
choco install kubernetes-helm
choco install jq
choco install git
choco install vscode
choco install openjdk
choco install gradle
choco install nssm
choco install 7zip
choco install docker

# Enable Hyper-V.
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All

# Put yourself into the Hyper-V Administrators group. This allows working with Hyper-V and Hyper-V-based applications
# like Minikube without administrative shells.
Add-LocalGroupMember -Group "Hyper-V Administrators" `
  -Member "$([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)"

# Reboot your machine.
Restart-Computer
```

## Create virtual switch for Hyper-V

From here, you can use with a non-administrative shell. Almost ...

```powershell
# List your network adapters, note down the name of your Ethernet adapter.
Get-NetAdapter

# If you don't like the name your 'Ethernet' adapter has, you can rename it.
# You need an administrative Shell for that.
Get-NetAdapter -Name "Ethernet Whatever" | Rename-NetAdapter -NewName Ethernet

# Import Hyper-V module to make the `New-VMSwitch` function available.
Import-Module Hyper-V

# Create virtual switch. Name it like this as we refer to that name later.
# Do not name it Minikube or similar as this switch is not specific to Minikube.
New-VMSwitch -Name "External Switch" -NetAdapterName Ethernet `
  -AllowManagementOS $true
```

## Start up Minikube

```powershell
# Get latest Kubernetes version from GitHub.
${K8S_VERSION} = $(Invoke-RestMethod -Uri `
  https://api.github.com/repos/kubernetes/kubernetes/releases/latest).name

Write-Host "Using Kubernetes version ${K8S_VERSION}"

# Start Minikube. Adjust CPU cores and memory to your needs and add them as parameters.
# --cpus=6 --memory=16384
minikube start --vm-driver=hyperv --kubernetes-version="${K8S_VERSION}"
```

```bash
# Check if everything is working. The following command prints the kubectl
# client and the Kubernetes server version. Ideally, both are equal.
kubectl version -o json | jq

# Verify that Kubernetes is running by printing the master URL.
kubectl cluster-info

# Monitor cluster objects. Run this in a separate shell. Before you continue,
# wait until everything is ready and running.
watch -n1 kubectl get all --namespace=kube-system

# Enable ingress add-on.
minikube addons enable ingress

# Set up Helm.
helm init
helm repo update

# Create namespace.
${K8S_NAMESPACE}="yournamespace"
kubectl create namespace "${K8S_NAMESPACE}"
```

## Make Minikube domain resolvable from host

Download CoreDNS from <https://coredns.io>.
At the time of writing, there is no Chocolatey package for it yet.
Unpack downloaded tarball via 7zip to `C:\ProgramData\CoreDNS`.
That directory should contain one file, `coredns.exe`.
Create a CoreDNS config file at `C:\ProgramData\CoreDNS\Corefile` with the
following content.
We will patch this file later to make Kubernetes services domain
`.svc.cluster.local.` resolvable from host.

TODO: Describe proxying mechanism.

```caddy
. {
  proxy . 10.79.255.100 10.79.255.200
  auto minikube.local {
    directory {$ProgramData}\CoreDNS
    reload 10s
  }
  errors
  cache
  reload
}
```

```powershell
# Install CoreDNS as windows service via NSSM.
nssm install CoreDNS "C:\Program Files\CoreDNS\coredns.exe"
nssm set CoreDNS AppParameters "-conf C:\ProgramData\CoreDNS\Corefile"
nssm set CoreDNS AppDirectory "C:\Program Files\CoreDNS"
nssm set CoreDNS AppExit Default Restart
nssm set CoreDNS AppStdout C:\Windows\Logs\CoreDNS\stdout.log
nssm set CoreDNS AppStderr C:\Windows\Logs\CoreDNS\stderr.log
nssm set CoreDNS AppTimestampLog 1
nssm set CoreDNS Description "CoreDNS: DNS and Service Discovery"
nssm set CoreDNS DisplayName CoreDNS
nssm set CoreDNS ObjectName LocalSystem
nssm set CoreDNS Start SERVICE_AUTO_START
nssm set CoreDNS Type SERVICE_WIN32_OWN_PROCESS

# Start CoreDNS service.
nssm start CoreDNS

# Use CoreDNS instead of regular DNS.
Set-DnsClientServerAddress `
  -InterfaceIndex $(Get-NetAdapter `
  -Name "vEthernet (External Switch)").ifIndex `
  -ServerAddresses ("::1")
```

Each time Minikube is started, it's IP must be written to the zone file with
the following command.

```bash
# Get current serial. This command will fail if the file does not exist, but
# it doesn't matter.
SERIAL=$(grep '@ IN SOA' /usr/local/etc/coredns/db.minikube.local \
  | awk '{ print $6 }')

# Update zone file.
cat <<EOD >/usr/local/etc/coredns/db.minikube.local
\$ORIGIN minikube.local.
\$TTL 5
@ IN SOA   @ mail $(( SERIAL + 1 )) 60 30 120 5
     NS    @
     A     $(minikube ip)
* IN CNAME @
EOD

# Wait until Minikube IP is resolved correctly.
while [[ "$(dig @127.0.0.1 -p 5300 +short minikube.local. A)" !=
    "$(minikube ip)" ]]; do
  sleep 1
done

Resolve-DnsName -DnsOnly -Name minikube.local. -Type A -Server ::1
New-Service -Name "CoreDNS" -BinaryPathName "$env:ProgramFiles\CoreDNS\coredns.exe -conf $env:ProgramData\CoreDNS\Corefile"
```

## Make Minikube domain resolvable from inside Kubernetes

```zsh
kubectl delete configmap --namespace kube-system coredns
cat <<EOD | kubectl create -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns
  namespace: kube-system
data:
  Corefile: |
    .:53 {
        errors
        health
        kubernetes cluster.local in-addr.arpa ip6.arpa {
           pods insecure
           upstream
           fallthrough in-addr.arpa ip6.arpa
        }
        prometheus :9153
        proxy . $(ifconfig vmnet8 | grep 'inet ' | awk '{ print $2 }'):5300
        cache 30
        loop
        reload
        loadbalance
    }
EOD

# Run container with interactive shell.
kubectl run -i --tty centos --image=centos --restart=Never -- bash

# Inside that container, try pinging the minikube hostname.
ping minikube.local
```

## Misc

[1]: https://github.com/kubernetes/ingress-nginx/tree/master/docs/examples/customization/ssl-dh-param
[2]: https://kubernetes.io/docs/tasks/administer-cluster/dns-custom-nameservers/
[3]: https://confluence.atlassian.com/kb/how-to-create-an-unproxied-application-link-719095740.html

- base64 for windows (keycloak)
