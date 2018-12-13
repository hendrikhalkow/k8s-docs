# Linkerd

```zsh
cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: linkerd
  name: web
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "web"
spec:
  tls:
    - hosts:
      - linkerd-dashboard.minikube.local
      secretName: minikube-tls
  rules:
  - host: linkerd-dashboard.minikube.local
    http:
      paths:
      - path: /
        backend:
          serviceName: web
          servicePort: http
EOD
```
