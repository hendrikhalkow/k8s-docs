# Confluent Platform

## macOS / Linux

```zsh
# Install Confluent Platform.
helm install confluent/cp-helm-charts \
  --name confluent \
  --namespace "${K8S_NAMESPACE}" \
  --set cp-zookeeper.servers=1

# Provide Kafka and Zookeeper with external IP addresses to make them accessible
# from host.
kubectl --namespace "${K8S_NAMESPACE}" patch service confluent-cp-zookeeper -p \
  '{"spec": {"type": "LoadBalancer"}}'
kubectl --namespace "${K8S_NAMESPACE}" patch service confluent-cp-kafka -p \
  '{"spec": {"type": "LoadBalancer"}}'

# List Kafka brokers.
kubectl run zookeeper-shell --generator=run-pod/v1 \
  --namespace "${K8S_NAMESPACE}" --rm --tty -i \
  --image confluentinc/cp-zookeeper -- \
  zookeeper-shell confluent-cp-zookeeper:2181 ls /brokers/ids

# List topics.
kubectl run kafka-shell --generator=run-pod/v1 \
  --namespace "${K8S_NAMESPACE}" --rm --tty -i \
  --image confluentinc/cp-kafka -- \
  kafka-topics --list --zookeeper confluent-cp-zookeeper:2181

# Play with your Kafka cluster

# Create virtual Python environment.
python -m venv "${HOME}/.venv/otto"

# Activate virtual Python environment.
source "${HOME}/.venv/otto/bin/activate"

# Install confluent-kafka. See
# <https://github.com/confluentinc/confluent-kafka-python>.
pip install confluent-kafka
```

## Kafka REST

```zsh
# Set up some variables.
KAFKA_REST_HOST="kafka-rest.minikube.local"
KAFKA_REST_URL="https://${KAFKA_REST_HOST}"
KAFKA_TOPIC="yet_another_json_topic"
KAFKA_CONSUMER="yet_another_json_consumer"
KAFKA_INSTANCE="yet_another_consumer_instance"

# Create ingress.
cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: ${K8S_NAMESPACE}
  name: kafka-rest
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "confluent-cp-kafka-rest"
spec:
  tls:
    - hosts:
      - ${KAFKA_REST_HOST}
      secretName: minikube-tls
  rules:
  - host: ${KAFKA_REST_HOST}
    http:
      paths:
      - path: /
        backend:
          serviceName: confluent-cp-kafka-rest
          servicePort: rest-proxy
EOD

# Get a list of topics.
curl "${KAFKA_REST_URL}/topics" | jq

# Produce a message with JSON data.
curl --request POST \
  "${KAFKA_REST_URL}/topics/${KAFKA_TOPIC}" \
  --header "Content-Type: application/vnd.kafka.json.v2+json" \
  --data @- <<EOD | jq
{
  "records": [
    {
      "value": {
        "foo": "bar"
      }
    }
  ]
}
EOD

# Create a consumer for JSON data, starting at the beginning of the topic's
# log. The consumer group is called "${KAFKA_CONSUMER}" and the instance is "${KAFKA_INSTANCE}".
curl --request POST \
  "${KAFKA_REST_URL}/consumers/${KAFKA_CONSUMER}" \
  --header "Accept: application/vnd.kafka.v2+json" \
  --header "Content-Type: application/vnd.kafka.v2+json" \
  --data @- <<EOD | jq
{
  "name": "${KAFKA_INSTANCE}",
  "format": "json",
  "auto.offset.reset": "earliest"
}
EOD

# Subscribe the consumer to a topic.
curl --request POST \
  "${KAFKA_REST_URL}/consumers/${KAFKA_CONSUMER}/instances/${KAFKA_INSTANCE}/subscription" \
  --header "Accept: application/vnd.kafka.v2+json" \
  --header "Content-Type: application/vnd.kafka.v2+json" \
  --data @- <<EOD
{
  "topics": [
    "${KAFKA_TOPIC}"
  ]
}
EOD

# Then consume some data from a topic using the base URL in the first response.
curl --request GET \
  "${KAFKA_REST_URL}/consumers/${KAFKA_CONSUMER}/instances/${KAFKA_INSTANCE}/records" \
  --header "Accept: application/vnd.kafka.json.v2+json" \
  | jq

# Finally, close the consumer with a DELETE to make it leave the group and clean up
# its resources.
curl --request DELETE \
  "${KAFKA_REST_URL}/consumers/${KAFKA_CONSUMER}/instances/${KAFKA_INSTANCE}" \
  --header "Accept: application/vnd.kafka.json.v2+json" \
 | jq
```

## Schema registry

```zsh
# Create ingress.
cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: ${K8S_NAMESPACE}
  name: schema-registry
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "confluent-cp-schema-registry"
spec:
  tls:
    - hosts:
      - schema-registry.minikube.local
      secretName: minikube-tls
  rules:
  - host: schema-registry.minikube.local
    http:
      paths:
      - path: /
        backend:
          serviceName: confluent-cp-schema-registry
          servicePort: schema-registry
EOD

# Test.
curl https://schema-registry.minikube.local/subjects | jq
```

## Grafana and Prometheus

```zsh
helm install --namespace otto stable/grafana --name grafana
cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: ${K8S_NAMESPACE}
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
          servicePort: 80
EOD
kubectl get secret --namespace otto grafana -o jsonpath='{.data.admin-password}' | base64 --decode

helm install --namespace otto stable/prometheus --name prometheus
cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: ${K8S_NAMESPACE}
  name: prometheus
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "prometheus-server"
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
          serviceName: prometheus-server
          servicePort: 80
EOD
```
