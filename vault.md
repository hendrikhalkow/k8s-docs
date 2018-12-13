# Vault

## macOS / Linux

```zsh
# Add incubator Helm repository.
helm repo add incubator \
  http://storage.googleapis.com/kubernetes-charts-incubator
helm repo update

# Install Vault.
helm install incubator/vault \
--set vault.dev=false \
--set replicaCount=1 \
--set consulAgent.join=\
"consul-server.${K8S_NAMESPACE}.svc.cluster.local" \
--set vault.config.ui=true \
--set vault.config.storage.consul.address=\
"consul-server.${K8S_NAMESPACE}.svc.cluster.local:8500" \
--set vault.config.storage.consul.path=vault/ \
--set vault.readiness.readyIfSealed=true \
--namespace "${K8S_NAMESPACE}" \
--name vault

# Create ingress with TLS.
VAULT_HOST="vault.minikube.local"
VAULT_URL="https://${VAULT_HOST}"
cat <<EOD | kubectl create -f -
apiVersion: extensions/v1beta1
kind: Ingress
metadata:
  namespace: ${K8S_NAMESPACE}
  name: vault
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.org/ssl-services: "vault-vault"
spec:
  tls:
    - hosts:
      - vault.minikube.local
      secretName: minikube-tls
  rules:
  - host: vault.minikube.local
    http:
      paths:
      - path: /
        backend:
          serviceName: vault-vault
          servicePort: api
EOD
echo "Vault URL: ${VAULT_URL}"
```

## Integrate Vault with OpenLDAP

```zsh
# In a separate shell, tunnel a port into the Vault pod
kubectl port-forward --namespace "${K8S_NAMESPACE}" "$(kubectl get pods \
  --namespace ${K8S_NAMESPACE} -l app=vault \
  -o jsonpath='{.items[0].metadata.name}')" \
  8200:8200

# In your working shell, you can now access vault.
export VAULT_ADDR=http://127.0.0.1:8200
vault status

# If necessary, unseal vault. You can also to this on the web interface.
vault operator unseal ...
vault operator unseal ...

vault login ROOT_TOKEN

# Enable LDAP auth backend
vault auth enable ldap

# Configure LDAP auth backend to integrate with OpenLDAP
vault write auth/ldap/config \
  url="ldap://openldap.${K8S_NAMESPACE}.svc.cluster.local" \
  userattr="uid" \
  binddn="cn=admin,dc=otto,dc=de" \
  bindpass="${LDAP_ADMIN_PASSWORD}" \
  userdn="ou=users,dc=otto,dc=de" \
  groupdn="ou=groups,dc=otto,dc=de" \
  starttls=false

# Create policy
# TODO: Check policy. I just copied it from
# https://learn.hashicorp.com/vault/identity-access-management/iam-policies
cat <<EOD | vault policy write admin -
# Manage auth methods broadly across Vault
path "auth/*"
{
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# Create, update, and delete auth methods
path "sys/auth/*"
{
  capabilities = ["create", "update", "delete", "sudo"]
}

# List auth methods
path "sys/auth"
{
  capabilities = ["read"]
}

# List existing policies
path "sys/policy"
{
  capabilities = ["read"]
}

# Create and manage ACL policies via CLI
path "sys/policy/*"
{
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# Create and manage ACL policies via API & UI
path "sys/policies/acl/*"
{
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# List, create, update, and delete key/value secrets
path "secret/*"
{
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# Manage secret engines
path "sys/mounts/*"
{
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# List existing secret engines.
path "sys/mounts"
{
  capabilities = ["read"]
}

# Read health checks
path "sys/health"
{
  capabilities = ["read", "sudo"]
}
EOD

# Apply policy
vault write auth/ldap/groups/admins policies=admin
```
