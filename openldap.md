# OpenLDAP

## macOS / Linux

```zsh
# Install OpenLDAP.
helm install stable/openldap \
  --set env.LDAP_ORGANISATION="Otto (GmbH & Co KG)" \
  --set env.LDAP_DOMAIN=otto.de \
  --namespace "${K8S_NAMESPACE}" \
  --name openldap

# Turn service into LoadBalancer to make it reachable from host
kubectl --namespace "${K8S_NAMESPACE}" patch svc openldap -p \
  '{"spec": {"type": "LoadBalancer"}}'

# Extract LDAP admin password.
LDAP_ADMIN_PASSWORD="$(kubectl get secret --namespace ${K8S_NAMESPACE} \
  openldap -o jsonpath="{.data.LDAP_ADMIN_PASSWORD}" | base64 --decode)"
echo "${LDAP_ADMIN_PASSWORD}"

# Do a search query.
ldapsearch \
  -H "ldap://openldap.${K8S_NAMESPACE}.svc.cluster.local" \
  -x \
  -D "cn=admin,dc=otto,dc=de" \
  -w "${LDAP_ADMIN_PASSWORD}" \
  -b dc=otto,dc=de

# Add entries.
ldapadd \
  -H "ldap://openldap.${K8S_NAMESPACE}.svc.cluster.local" \
  -x \
  -D "cn=admin,dc=otto,dc=de" \
  -w "${LDAP_ADMIN_PASSWORD}" <<-EOD
dn: ou=users,dc=otto,dc=de
ou: users
objectClass: organizationalUnit

dn: uid=hehalkow,ou=users,dc=otto,dc=de
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Hendrik M Halkow
sn: Halkow
givenName: Hendrik
uid: hehalkow
ou: People
mail: hendrik.halkow@otto.de
description: This is Hendrik.
telephoneNumber: +49 163 5696969
userPassword: {SSHA}dcWy5Ph0Ub0TA5dL94FXArc5GMZEzbcG

dn: ou=groups,dc=otto,dc=de
ou: groups
objectClass: organizationalUnit

dn: cn=admins,ou=groups,dc=otto,dc=de
objectClass: groupOfNames
cn: admins
description: Administrators
member: uid=hehalkow,ou=users,dc=otto,dc=de
EOD
```

## Windows

```powershell
# Install OpenLDAP.
helm install stable/openldap `
  --set env.LDAP_ORGANISATION=h5k `
  --set env.LDAP_DOMAIN=otto.de `
  --namespace "${K8S_NAMESPACE}" `
  --name openldap
```
