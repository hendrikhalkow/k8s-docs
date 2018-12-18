# Set up Kubernetes development environment on macOS

## TODO

- brew tap for coredns
- /etc/resolver/minikube.local
- don't use hyperkit vm driver
- document why ssl in docker
- reboot on hypervisor change due to messed up network configuration
- ingress for dashboard

## Prerequisites

```zsh
# Homebrew
/usr/bin/ruby -e "$(curl -fsSL \
  https://raw.githubusercontent.com/Homebrew/install/master/install)"

# Homebrew Cask
brew tap caskroom/cask

# SDKMAN!
curl -s "https://get.sdkman.io" | bash

# Install required packages.
brew install kubernetes-cli jq coredns
sdk install java
sdk install gradle

# Install at least one of the following 3:
# 1)
brew cask install minikube vmware-fusion
# 2)
brew cask install minikube virtualbox
# 3)
brew install docker-machine-driver-hyperkit
DMDH_PATH="/usr/local/opt/docker-machine-driver-hyperkit/bin"
DMDH_PATH="${DMDH_PATH}/docker-machine-driver-hyperkit"
sudo chown root:wheel "${DMDH_PATH}"
sudo chmod u+s "${DMDH_PATH}"
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

# List all Kubernetes versions
curl -Ls https://api.github.com/repos/kubernetes/kubernetes/releases | \
  jq -r '.[].name'

# Choose your desired version, for example
K8S_VERSION="v1.13.1"

# Start Minikube. Adjust CPU cores and memory to your needs. If you are unsure,
# leave these parameters out. The following examples uses half of the logical
# CPU cores and half of total RAM.
minikube start \
  --vm-driver=vmwarefusion \
  --kubernetes-version="${K8S_VERSION}" \
  --cpus="$(( $(sysctl -n hw.ncpu) / 2 ))" \
  --memory="$(( $(sysctl -n hw.memsize) / 1024**2 / 2 ))"

# Alternatively, use VirtualBox. Be aware that VirtualBox does not work with
# nested virtualization.
minikube start \
  --vm-driver=virtualbox \
  --kubernetes-version="${K8S_VERSION}" \
  --cpus="$(( $(sysctl -n hw.ncpu) / 2 ))" \
  --memory="$(( $(sysctl -n hw.memsize) / 1024**2 / 2 ))"

# ... or HyperKit. Be aware that routing into HyperKit does not work.
minikube start \
  --vm-driver=hyperkit \
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
watch -n1 kubectl get all,ing,pvc,secret --namespace="${K8S_NAMESPACE}"
```

## Make Minikube domain resolvable from host

Create a CoreDNS config file at `/usr/local/etc/coredns/Corefile` with the
following content.

```txt
.:5300 {
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
```

Start CoreDNS service with `brew services start coredns`. The log file is
available at `/usr/local/var/log/coredns.log`.

Each time Minikube is started, it's IP must be written to the zone file with
the following command.

```zsh
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
```

## Resolve Kubernetes services from host

Attention: The following does not work with the HyperKit driver.

```zsh
# Install minikube-lb-patch to make load balancers get an IP address
cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
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
cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: kube-system
  name: kubernetes-dashboard
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "kubernetes-dashboard"
spec:
  tls:
  - hosts:
    - dashboard.kube-system.minikube.local
    secretName: minikube-tls
  rules:
  - host: dashboard.kube-system.minikube.local
    http:
      paths:
      - path: /
        backend:
          serviceName: kubernetes-dashboard
          servicePort: 80
EOD
```
