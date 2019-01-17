# Linkerd

```zsh
# Set up variables.
K8S_NAMESPACE="linkerd"
TLS_CERT_DOMAIN="${K8S_NAMESPACE}.minikube.local"

# Issue and import certificate.

# Create ingress.
LINKERD_DASHBOARD_HOST="dashboard.${TLS_CERT_DOMAIN}"
LINKERD_DASHBOARD_URL="https://${LINKERD_DASHBOARD_HOST}"
cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: ${K8S_NAMESPACE}
  name: dashboard
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "linkerd-web"
spec:
  tls:
    - hosts:
      - ${LINKERD_DASHBOARD_HOST}
      secretName: minikube-tls
  rules:
  - host: ${LINKERD_DASHBOARD_HOST}
    http:
      paths:
      - path: /
        backend:
          serviceName: linkerd-web
          servicePort: http
EOD
```
