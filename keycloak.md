# Keycloak

Install Keycloak as described below.
As soon as your resources are ready, Keycloak is available at
<https://keycloak.minikube.local>.
Optionally, you can integrate Keycloak with LDAP, for example
[OpenLDAP](openldap.md).

## macOS / Linux

```zsh
# Install Keycloak via Helm.
helm install --namespace "${K8S_NAMESPACE}" --name keycloak stable/keycloak

# Add ingress.
cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: ${K8S_NAMESPACE}
  name: keycloak
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "keycloak-http"
spec:
  tls:
    - hosts:
      - keycloak.${K8S_NAMESPACE}.minikube.local
      secretName: minikube-tls
  rules:
  - host: keycloak.${K8S_NAMESPACE}.minikube.local
    http:
      paths:
      - path: /
        backend:
          serviceName: keycloak-http
          servicePort: http
EOD
```

## Windows

```powershell
# Install Keycloak via Helm.
helm install --namespace "${K8S_NAMESPACE}" --name keycloak stable/keycloak

# Add ingress.
Write-Output @"
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: ${K8S_NAMESPACE}
  name: web
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "keycloak-http"
spec:
  tls:
    - hosts:
      - keycloak.minikube.local
      secretName: minikube-tls
  rules:
  - host: keycloak.minikube.local
    http:
      paths:
      - path: /
        backend:
          serviceName: keycloak-http
          servicePort: http
EOD
"@ | kubectl create -f -
```
