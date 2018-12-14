# Prometheus Operator

```zsh
git clone git@github.com:coreos/prometheus-operator.git
cd prometheus-operator/contrib/kube-prometheus
kubectl create -f manifests/

cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: monitoring
  name: grafana
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "grafana"
spec:
  tls:
    - hosts:
      - grafana.minikube.local
      secretName: minikube-tls
  rules:
  - host: grafana.minikube.local
    http:
      paths:
      - path: /
        backend:
          serviceName: grafana
          servicePort: http
EOD

cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: monitoring
  name: alertmanager
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "alertmanager-main"
spec:
  tls:
    - hosts:
      - alertmanager.minikube.local
      secretName: minikube-tls
  rules:
  - host: alertmanager.minikube.local
    http:
      paths:
      - path: /
        backend:
          serviceName: alertmanager-main
          servicePort: web
EOD

cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: monitoring
  name: prometheus
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "prometheus-k8s"
spec:
  tls:
    - hosts:
      - prometheus.minikube.local
      secretName: minikube-tls
  rules:
  - host: prometheus.minikube.local
    http:
      paths:
      - path: /
        backend:
          serviceName: prometheus-k8s
          servicePort: web
EOD
```