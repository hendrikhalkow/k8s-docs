# Set up Kubernetes development environment on macOS

## TODO

- brew tap for coredns
-
- document why ssl in docker
- reboot on hypervisor change due to messed up network configuration
- ingress for dashboard
- install VMWare unified driver

## Prerequisites

```zsh
# Homebrew
/usr/bin/ruby -e "$(curl -fsSL \
  https://raw.githubusercontent.com/Homebrew/install/master/install)"

# Install required packages.
brew install kubernetes-cli kubernetes-helm jq

# Install at least one of the following 3:
# 1) VMware Fusion and Docker Machine driver for VMware
brew cask install minikube vmware-fusion
DMDVM_VERSION_URL="https://api.github.com/repos/machine-drivers"
DMDVM_VERSION_URL="${DMDVM_VERSION_URL}/docker-machine-driver-vmware"
DMDVM_VERSION_URL="${DMDVM_VERSION_URL}/releases/latest"
DMDVM_VERSION="$(curl -Ls ${DMDVM_VERSION_URL}| jq -r '.tag_name')"
DMDVM_URL="https://github.com/machine-drivers/docker-machine-driver-vmware"
DMDVM_URL="${DMDVM_URL}/releases/download/${DMDVM_VERSION}"
DMDVM_URL="${DMDVM_URL}/docker-machine-driver-vmware_darwin_amd64"
curl -L -o docker-machine-driver-vmware "${DMDVM_URL}"
chmod +x docker-machine-driver-vmware \
mv docker-machine-driver-vmware /usr/local/bin/
MINIKUBE_VM_DRIVER="vmware"

# 2) VirtualBox (driver comes with Minikube). Be aware that VirtualBox does not
# work with nested virtualization that you need for Kata Containers.
brew cask install minikube virtualbox
MINIKUBE_VM_DRIVER="virtualbox"

# 3) Hyperkit (driver only as Hyperkit is part of macOS). Be aware that routing
# into HyperKit does not work.
brew install docker-machine-driver-hyperkit
DMDHK_PATH="/usr/local/opt/docker-machine-driver-hyperkit/bin"
DMDHK_PATH="${DMDHK_PATH}/docker-machine-driver-hyperkit"
sudo chown root:wheel "${DMDHK_PATH}"
sudo chmod u+s "${DMDHK_PATH}"
MINIKUBE_VM_DRIVER="hyperkit"
```

## Start up Minikube

```zsh
# Ensure that your software is up to date.
brew update
brew upgrade
brew cask upgrade

# In case you want to start freshly, remove your old minikube.
minikube delete
rm -rf "${HOME}/.minikube"
rm -rf "${HOME}/.kube"

# Set your Kubernetes version variable to an appropriate value. It might be a
# good idea to use the same version as kubectl ...
K8S_VERSION="$(kubectl version --client --output json | \
  jq -r '.clientVersion.gitVersion')"

# ... or the latest stable version
K8S_VERSION="$(curl -s \
  https://storage.googleapis.com/kubernetes-release/release/stable.txt)"

# ... or another version that you can pick from the list of all versions.
curl -Ls https://api.github.com/repos/kubernetes/kubernetes/releases | \
  jq -r '.[].name'

# Start Minikube. Adjust CPU cores and memory to your needs. If you are unsure,
# leave these parameters out. The following examples uses half of the logical
# CPU cores and half of total RAM.
minikube start \
  --vm-driver="${MINIKUBE_VM_DRIVER}" \
  --kubernetes-version="${K8S_VERSION}" \
  --cpus="$(( $(sysctl -n hw.ncpu) / 2 ))" \
  --memory="$(( $(sysctl -n hw.memsize) / 1024**2 / 2 ))"

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
K8S_NAMESPACE="yournamespace"
kubectl create namespace "${K8S_NAMESPACE}"

# In another shell, watch your namespace.
watch -n1 kubectl get all,pvc,secret --namespace="${K8S_NAMESPACE}"
```

## Make Minikube domain resolvable from host

```zsh
brew tap "coredns/deployment" "https://github.com/coredns/deployment"
brew install  coredns

# Create a CoreDNS config file at `/usr/local/etc/coredns/Corefile` with the
# following content.
cat <<EOD >/usr/local/etc/coredns/Corefile
.:53 {
  proxy . 8.8.8.8:53 8.8.4.4:53 {
    protocol https_google
  }
  auto minikube.local {
    directory /usr/local/etc/coredns
    reload 10s
  }
  errors
  cache
}
EOD

# Start CoreDNS service. Make sure that you have your firewall enabled to avoid
# exposing your DNS server. The log file will be available at
# `/usr/local/var/log/coredns.log`.
sudo brew services start coredns/deployment/coredns

# Create /etc/resolver if it doesn't exist.
if [ ! -d /etc/resolver ]
then
  sudo mkdir -p /etc/resolver
fi

# Put your nameserver into /etc/resolver/minikube.local to make macOS use it as
# a resolver for your minikube.local domain.
echo "nameserver 127.0.0.1" | sudo tee /etc/resolver/minikube.local

# Each time Minikube is started, it's IP must be written to the zone file with
# the following command. This will fail if the file does not exist, but
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
```

## Resolve Kubernetes services from host

Attention: The following does not work with the HyperKit driver.

```zsh
# Install minikube-lb-patch to make load balancers get an IP address
cat <<EOD | kubectl create -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  namespace: kube-system
  name: minikube-lb-patch
  labels:
    run: minikube-lb-patch
spec:
  replicas: 1
  selector:
    matchLabels:
      run: minikube-lb-patch
  template:
    metadata:
      labels:
        run: minikube-lb-patch
    spec:
      containers:
      - image: elsonrodriguez/minikube-lb-patch:0.1
        imagePullPolicy: IfNotPresent
        name: minikube-lb-patch
EOD

# Route service CIDR into minikube
sudo route add \
  -net $(cat ${HOME}/.minikube/profiles/minikube/config.json \
    | jq -r ".KubernetesConfig.ServiceCIDR") \
  $(minikube ip)

# Create DNS service that is resolvable from host
cat <<EOD | kubectl create -f -
apiVersion: v1
kind: Service
metadata:
  name: kube-dns-external
  namespace: kube-system
spec:
  ports:
  - name: dns
    port: 53
    protocol: UDP
    targetPort: 53
  selector:
    k8s-app: kube-dns
  sessionAffinity: None
  type: LoadBalancer
EOD

# Use minikube DNS service on host system for domain svc.cluster.local
echo "nameserver $(kubectl get svc kube-dns-external --namespace kube-system \
  -o jsonpath='{.spec.clusterIP}')" | sudo tee /etc/resolver/svc.cluster.local

# Test
dig "@$(kubectl get svc kube-dns-external --namespace kube-system \
  -o jsonpath='{.spec.clusterIP}')" svc.cluster.local. SOA
```

## Optional: Make minikube domain resolvable from inside Kubernetes

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
        proxy . $(ifconfig $(route -n get $(minikube ip) | grep interface \
          | awk '{ print $2 }') | grep 'inet ' | awk '{ print $2 }'):5300
        cache 30
        loop
        reload
        loadbalance
    }
EOD

# Run container with interactive shell.
kubectl run ping \
--namespace "${K8S_NAMESPACE}" \
--generator=run-pod/v1 \
--rm --tty -i \
--image centos -- \
bash

# Inside that container, try pinging the minikube hostname.
ping minikube.local
```

## Dashboard ingress

If you haven't done so, create a TLS certificate for your domain and import it
into your cluster as described in the [custom CA documentation](tls.md).
In this example, we use `kube-system.minikube.local` as our domain.

```zsh
# Set up variables.
K8S_NAMESPACE="kube-system"
TLS_CERT_DOMAIN="${K8S_NAMESPACE}.minikube.local"
TLS_CERT_PASSWORD_NAME="TLS certificate key password for ${TLS_CERT_DOMAIN}"
TLS_CERT_PASSWORD="$(security find-generic-password -a ${USER} \
  -s "${TLS_CERT_PASSWORD_NAME}" -w)"

# Issue and import certificate.
kubectl --namespace "${K8S_NAMESPACE}" create secret tls minikube-tls \
  --key <(openssl rsa \
    -in "${CA_DIR}/private/${TLS_CERT_DOMAIN}.key.pem" \
    -passin "pass:${TLS_CERT_PASSWORD}") \
  --cert <(cat \
    "${CA_DIR}/certs/${TLS_CERT_DOMAIN}.cert.pem" \
    "${CA_DIR}/chain.pem")

# Create ingress.
K8S_DASHBOARD_HOST="dashboard.${TLS_CERT_DOMAIN}"
K8S_DASHBOARD_URL="https://${K8S_DASHBOARD_HOST}"
cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: ${K8S_NAMESPACE}
  name: kubernetes-dashboard
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "kubernetes-dashboard"
spec:
  tls:
  - hosts:
    - ${K8S_DASHBOARD_HOST}
    secretName: minikube-tls
  rules:
  - host: ${K8S_DASHBOARD_HOST}
    http:
      paths:
      - path: /
        backend:
          serviceName: kubernetes-dashboard
          servicePort: 80
EOD
echo "Kubernetes dashboard URL: ${K8S_DASHBOARD_URL}"
```
