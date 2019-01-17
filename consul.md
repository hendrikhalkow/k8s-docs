# Consul

## macOS / Linux

```zsh
# Clone Helm chart repository.
git clone https://github.com/hashicorp/consul-helm.git

# Install Consul via Helm chart.
helm install \
  --namespace "${K8S_NAMESPACE}" \
  --name consul \
  --set server.replicas=1 \
  --set server.bootstrapExpect=1 \
  --set server.disruptionBudget.enabled=false \
  ./consul-helm

# Create ingress.
CONSUL_HOST="consul.${K8S_NAMESPACE}.minikube.local"
CONSUL_URL="https://${CONSUL_HOST}"
cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: ${K8S_NAMESPACE}
  name: consul-ui
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "consul-ui"
spec:
  tls:
    - hosts:
      - ${CONSUL_HOST}
      secretName: minikube-tls
  rules:
  - host: ${CONSUL_HOST}
    http:
      paths:
      - path: /
        backend:
          serviceName: consul-ui
          servicePort: http
EOD

# Print Consul UI URL.
echo "Consul UI URL: ${CONSUL_URL}"

# When all resources are ready, open your browser.
open "${CONSUL_URL}"
```

## Windows

```powershell
# Clone Helm chart repository.
git clone https://github.com/hashicorp/consul-helm.git

# Install Consul via Helm chart.
helm install `
  --namespace "${K8S_NAMESPACE}" `
  --name consul `
  --set server.replicas=1 `
  --set server.bootstrapExpect=1 `
  --set server.disruptionBudget.enabled=false `
  .\consul-helm

# Define variables.
${CONSUL_HOST}="consul.minikube.local"
${CONSUL_URL}="https://${CONSUL_HOST}"

# Create ingress.
Write-Output @"
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: ${K8S_NAMESPACE}
  name: consul-ui
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "consul-ui"
spec:
  tls:
    - hosts:
      - ${CONSUL_HOST}
      secretName: minikube-tls
  rules:
  - host: ${CONSUL_HOST}
    http:
      paths:
      - path: /
        backend:
          serviceName: consul-ui
          servicePort: http
"@ | kubectl create -f -

# Print Consul UI URL.
Write-Verbose "Consul UI URL: ${CONSUL_URL}"

# When all resources are ready, open your browser.
Start-Process -Path "${CONSUL_URL}"
```
