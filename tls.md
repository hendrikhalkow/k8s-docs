# Transport Layer Security all in One

```zsh
brew install openssl
export PATH="/usr/local/opt/openssl/bin:${PATH}"
PS1="${PS1_ORIGINAL}"
PS1="%{$fg[red]%}${CA}${PS1_ORIGINAL}"
```

This guide is inspired by
<https://jamielinux.com/docs/openssl-certificate-authority/>.

## TODO

- Create DH params for perfect forward secrecy using
  `openssl dhparam 4096  -out dhparam.pem`. See [1].
- Describe TLS_DIR="..."
- move configs to cfg folder
- auto-generate config

## Windows considerations

```zsh
cat <<EOD | kubectl create -f -
apiVersion: v1
kind: Pod
metadata:
  namespace: ${K8S_NAMESPACE}
  name: openssl
spec:
  containers:
  - name: fedora
    image: fedora
    args:
    - bash
    stdin: true
    stdinOnce: true
    tty: true
    workingDir: "/tls"
    volumeMounts:
    - mountPath: "/tls"
      name: tls
    env:
    - name: TLS_DIR
      value: /tls
  volumes:
  - name: tls
    hostPath:
      path: "${TLS_DIR}"
EOD

# Attach to OpenSSL pod.
kubectl attach --namespace "${K8S_NAMESPACE}" openssl -i -t

# After you are done with this, you can remove this pod:
kubectl delete --namespace "${K8S_NAMESPACE}" pod openssl
```

## Generate secure passwords

To generate a secure password, we use random data from /dev/random.
If we use lowercase letters a-z, uppercase letters A-Z and digits 0-9, we have
62 different symbols.

Every symbol contains log2(62) = 5.954 bits of information. To get a password
with 256 bits of entropy, we need ceiling(256 / 5.954) = 43 symbols length
created out of perfectly random data.

You can get these passwords with the following command.

```zsh
cat /dev/random | LC_ALL=C tr -dc a-zA-Z0-9 | head -c 32; echo
```

We will use these kind of passwords when we set up our certificate authority.
If you don't like this, you can also create your own passwords.

```zsh
# Generate passwords.
ROOT_CA_PASSWORD="$(cat /dev/random \
  | LC_ALL=C tr -dc a-zA-Z0-9 | head -c 43)"
INTERMEDIATE_CA_PASSWORD="$(cat /dev/random \
  | LC_ALL=C tr -dc a-zA-Z0-9 | head -c 43)"
MINIKUBE_CERTIFICATE_PASSWORD="$(cat /dev/random \
  | LC_ALL=C tr -dc a-zA-Z0-9 | head -c 43)"

# Add key passwords to Keychain.
security add-generic-password \
  -a "${USER}" -s "$(id -F) Root CA" -w "${ROOT_CA_PASSWORD}"
security add-generic-password \
  -a "${USER}" -s "$(id -F) Intermediate CA" -w "${INTERMEDIATE_CA_PASSWORD}"
security add-generic-password \
  -a "${USER}" -s "minikube.local" -w "${MINIKUBE_CERTIFICATE_PASSWORD}"

# If you generated these passwords before, you can load them from the keychain
# Instead of re-generating them.
ROOT_CA_PASSWORD="$(security find-generic-password -a ${USER} \
  -s "$(id -F) Root CA" -w)"
INTERMEDIATE_CA_PASSWORD="$(security find-generic-password -a ${USER} \
  -s "$(id -F) Intermediate CA" -w)"
MINIKUBE_CERTIFICATE_PASSWORD="$(security find-generic-password -a ${USER} \
  -s "minikube.local" -w)"
```

## Root CA

```zsh
CA="Hendrik M Halkow Root CA"
PARENT_CA=""

# Set context variables.
CA_DIR="${CA_BASE_DIR}/${CA}"
CA_PASSWORD="$(security find-generic-password -a ${USER} -s "${CA}" -w)"
if [ -z "${CA_PASSWORD}" ]; then
  CA_PASSWORD="$(cat /dev/random | LC_ALL=C tr -dc a-zA-Z0-9 | head -c 43)"
  security add-generic-password -a "${USER}" -s "${CA}" -w "${CA_PASSWORD}"
fi
echo "${CA}"
echo "Directory: ${CA_DIR}"
echo "Password: ${CA_PASSWORD}"
PS1="%{$fg[red]%}${CA}${PS1_ORIGINAL}"

# Initialize CA.
mkdir -p "${CA_DIR}"/{certs,crl,csr,newcerts,private}/
chmod 0700 "${CA_DIR}/private"
touch "${CA_DIR}/index.txt"
echo 1000 > "${CA_DIR}/serial"
openssl genrsa \
  -aes256 \
  -passout "pass:${CA_PASSWORD}" \
  -out "${CA_DIR}/private/${CA}.key.pem" 4096
ln -s "${CA}.key.pem" "${CA_DIR}/private/key.pem"
chmod 0400 "${CA_DIR}/private/${CA}.key.pem"

# Copy in openssl.cnf
cp "${CA_BASE_DIR}/${CA}.cnf" "${CA_DIR}/openssl.cnf"

# Create root certificate.
openssl req \
  -config "${CA_DIR}/openssl.cnf" \
  -key "${CA_DIR}/private/${CA}.key.pem" \
  -passin "pass:${CA_PASSWORD}" \
  -new \
  -x509 \
  -days 7300 \
  -sha256 \
  -extensions v3_ca \
  -out "${CA_DIR}/certs/${CA}.cert.pem"
ln -s "${CA}.cert.pem" "${CA_DIR}/certs/cert.pem"
chmod 0444 "${CA_DIR}/certs/${CA}.cert.pem"

# Create certificate chains.
cat "${CA_DIR}/certs/${CA}.cert.pem" > "${CA_DIR}/certs/${CA}.fullchain.pem"
if [ -z "${PARENT_CA}" ]; then
  echo -n > "${CA_DIR}/certs/${CA}.chain.pem"
else
  cat \
  "${CA_DIR}/certs/${CA}.cert.pem" \
  "${CA_BASE_DIR}/${PARENT_CA}/certs/${PARENT_CA}.chain.pem" \
    > "${CA_DIR}/certs/${CA}.chain.pem"

  cat "${CA_BASE_DIR}/${PARENT_CA}/certs/${PARENT_CA}.fullchain.pem" \
    >> "${CA_DIR}/certs/${CA}.fullchain.pem"
fi
chmod 0444 "${CA_DIR}/certs/${CA}.chain.pem"
chmod 0444 "${CA_DIR}/certs/${CA}.fullchain.pem"


chmod 0444 "${CA_DIR}/certs/${CA}.chain.pem"

cp "${CA_DIR}/certs/${CA}.cert.pem" "${CA_DIR}/certs/${CA}.fullchain.pem"
chmod 0444 "${CA_DIR}/certs/${CA}.fullchain.pem"

# View root certificate.
openssl x509 -noout -text -in "${CA_DIR}/certs/cert.pem"

# Add certificate to keychain.
sudo security add-trusted-cert -d -k /Library/Keychains/System.keychain \
  "${CA_DIR}/certs/cert.pem"
```

To make your browsers trust that certificate, restart Chrome or Safari. If you
use Firefox, you need to import this certificate via -> Preferences -> Privacy
and Security -> View Certificates -> Import.

## Minikube CA

```zsh
CA="Hendrik M Halkow Minikube CA"
PARENT_CA="Hendrik M Halkow Root CA"

# Set context variables.
CA_DIR="${CA_BASE_DIR}/${CA}"
CA_PASSWORD="$(security find-generic-password -a ${USER} -s "${CA}" -w)"
if [ -z "${CA_PASSWORD}" ]; then
  CA_PASSWORD="$(cat /dev/random | LC_ALL=C tr -dc a-zA-Z0-9 | head -c 43)"
  security add-generic-password -a "${USER}" -s "${CA}" -w "${CA_PASSWORD}"
fi
echo "${CA}"
echo "Directory: ${CA_DIR}"
echo "Password: ${CA_PASSWORD}"
PS1="%{$fg[red]%}${CA}${PS1_ORIGINAL}"

# Initialize CA.
mkdir -p "${CA_DIR}"/{certs,crl,csr,newcerts,private}/
chmod 0700 "${CA_DIR}/private"
touch "${CA_DIR}/index.txt"
echo 1000 > "${CA_DIR}/serial"
openssl genrsa \
  -aes256 \
  -passout "pass:${CA_PASSWORD}" \
  -out "${CA_DIR}/private/${CA}.key.pem" 4096
ln -s "${CA}.key.pem" "${CA_DIR}/private/key.pem"
chmod 0400 "${CA_DIR}/private/${CA}.key.pem"

# Copy in openssl.cnf
cp "${CA_BASE_DIR}/${CA}.cnf" "${CA_DIR}/openssl.cnf"

openssl req \
  -config "${CA_DIR}/openssl.cnf" \
  -new \
  -sha256 \
  -passin "pass:${CA_PASSWORD}" \
  -key "${CA_DIR}/private/key.pem" \
  -out "${CA_DIR}/csr/${CA}.csr.pem"

# Copy CSR from CA to it's parent.

CA_PARENT="Hendrik M Halkow Root CA"
cp "${CA_DIR}/csr/${CA}.csr.pem" "${CA_BASE_DIR}/${CA_PARENT}/csr/"


CSR_DN="${CA}"

CA="Hendrik M Halkow Root CA"

# Set context variables.
CA_DIR="${CA_BASE_DIR}/${CA}"
CA_PASSWORD="$(security find-generic-password -a ${USER} -s "${CA}" -w)"
if [ -z "${CA_PASSWORD}" ]; then
  CA_PASSWORD="$(cat /dev/random | LC_ALL=C tr -dc a-zA-Z0-9 | head -c 43)"
  security add-generic-password -a "${USER}" -s "${CA}" -w "${CA_PASSWORD}"
fi
echo "${CA}"
echo "Directory: ${CA_DIR}"
echo "Password: ${CA_PASSWORD}"
PS1="%{$fg[red]%}${CA}${PS1_ORIGINAL}"

openssl ca \
  -config "${CA_DIR}/openssl.cnf" \
  -extensions v3_intermediate_ca \
  -days 3650 \
  -notext \
  -md sha256 \
  -passin "pass:${CA_PASSWORD}" \
  -in "${CA_DIR}/csr/${CSR_DN}.csr.pem" \
  -out "${CA_DIR}/certs/${CSR_DN}.cert.pem"


CA="Hendrik M Halkow Minikube CA"

# Set context variables.
CA_DIR="${CA_BASE_DIR}/${CA}"
CA_PASSWORD="$(security find-generic-password -a ${USER} -s "${CA}" -w)"
if [ -z "${CA_PASSWORD}" ]; then
  CA_PASSWORD="$(cat /dev/random | LC_ALL=C tr -dc a-zA-Z0-9 | head -c 43)"
  security add-generic-password -a "${USER}" -s "${CA}" -w "${CA_PASSWORD}"
fi
echo "${CA}"
echo "Directory: ${CA_DIR}"
echo "Password: ${CA_PASSWORD}"
PS1="%{$fg[red]%}${CA}${PS1_ORIGINAL}"


cp "${CA_BASE_DIR}/${CA_PARENT}/certs/${CSR_DN}.cert.pem" "${CA_DIR}/certs/"
cp "${CA_BASE_DIR}/${CA_PARENT}/certs/cert.pem" "${CA_DIR}/certs/${CA_PARENT}.cert.pem"

openssl verify -CAfile "${CA_DIR}/certs/${CA_PARENT}.cert.pem" \
  "${CA_DIR}/certs/cert.pem"

cat "${CA_DIR}/certs/cert.pem" "${CA_DIR}/certs/${CA_PARENT}.cert.pem" \
  > "${CA_DIR}/certs/${CA}.fullchain.pem"

cat "${CA_DIR}/certs/cert.pem" \
  > "${CA_DIR}/certs/${CA}.chain.pem"

chmod 444 certs/ca-chain.cert.pem
```

## Minikube certificate

```zsh
cd "${INTERMEDIATE_CA_DIR}"

# Create private key for minikube certificate.
openssl genrsa \
  -aes256 \
  -passout "pass:${MINIKUBE_CERTIFICATE_PASSWORD}" \
  -out "private/${K8S_NAMESPACE}.minikube.local.key.pem" 2048
chmod 0400 "private/${K8S_NAMESPACE}.minikube.local.key.pem"
```

Copy your [minikube.local.cnf](#minikube-certificate-configuration-file) to the
`${INTERMEDIATE_CA_DIR}` directory.
If you want to keep the domain minikube.local, no changes are required.

```zsh
# Create minikube certificate signing request.
openssl req -config "${K8S_NAMESPACE}.minikube.local.cnf" \
  -passin "pass:${MINIKUBE_CERTIFICATE_PASSWORD}" \
  -key "private/${K8S_NAMESPACE}.minikube.local.key.pem" \
  -new \
  -sha256 \
  -out "csr/${K8S_NAMESPACE}.minikube.local.csr.pem"

# Create minikube certificate.
openssl ca \
  -passin "pass:${INTERMEDIATE_CA_PASSWORD}" \
  -config ./${K8S_NAMESPACE}.minikube.local.cnf \
  -extensions server_cert \
  -days 375 \
  -notext \
  -md sha256 \
  -in "csr/${K8S_NAMESPACE}.minikube.local.csr.pem" \
  -out "certs/${K8S_NAMESPACE}.minikube.local.cert.pem"

# Set certificate permissions.
chmod 0444 "certs/${K8S_NAMESPACE}.minikube.local.cert.pem"

# View certificate.
openssl x509 -noout -text -in "certs/${K8S_NAMESPACE}.minikube.local.cert.pem"

# Import certificate chain and key into Kubernetes.
kubectl --namespace "${K8S_NAMESPACE}" create secret tls minikube-tls \
  --key <(openssl rsa \
    -in ${INTERMEDIATE_CA_DIR}/private/${K8S_NAMESPACE}.minikube.local.key.pem \
    -passin pass:${MINIKUBE_CERTIFICATE_PASSWORD}) \
  --cert <(cat \
    ${INTERMEDIATE_CA_DIR}/certs/${K8S_NAMESPACE}.minikube.local.cert.pem \
    ${INTERMEDIATE_CA_DIR}/certs/intermediate.cert.pem)
```

## Configuration files

### Root CA configuration file

```ini
# root-ca.cnf. Copy this file to "${TLS_HOME}/root-ca/".

[ ca ]
# `man ca`
default_ca = CA_default

[ CA_default ]
# Directory and file locations.
dir               = .
certs             = $dir/certs
crl_dir           = $dir/crl
new_certs_dir     = $dir/newcerts
database          = $dir/index.txt
serial            = $dir/serial
RANDFILE          = $dir/private/.rand

# The root key and root certificate.
private_key       = $dir/private/key.pem
certificate       = $dir/certs/cert.pem

# For certificate revocation lists.
crlnumber         = $dir/crlnumber
crl               = $dir/crl/crl.pem
crl_extensions    = crl_ext
default_crl_days  = 30

# SHA-1 is deprecated, so use SHA-2 instead.
default_md        = sha256

name_opt          = ca_default
cert_opt          = ca_default
default_days      = 375
preserve          = no
policy            = policy_strict

[ policy_strict ]
# The root CA should only sign intermediate certificates that match.
# See the POLICY FORMAT section of `man ca`.
countryName             = match
stateOrProvinceName     = match
organizationName        = match
organizationalUnitName  = optional
commonName              = supplied
emailAddress            = optional

[ policy_loose ]
# Allow the intermediate CA to sign a more diverse range of certificates.
# See the POLICY FORMAT section of the `ca` man page.
countryName             = optional
stateOrProvinceName     = optional
localityName            = optional
organizationName        = optional
organizationalUnitName  = optional
commonName              = supplied
emailAddress            = optional

[ req ]
# Options for the `req` tool (`man req`).
default_bits        = 2048
distinguished_name  = req_distinguished_name
string_mask         = utf8only

# SHA-1 is deprecated, so use SHA-2 instead.
default_md          = sha256

# Extension to add when the -x509 option is used.
x509_extensions     = v3_ca

[ req_distinguished_name ]
# See <https://en.wikipedia.org/wiki/Certificate_signing_request>.
countryName                     = Country Name (2 letter code)
stateOrProvinceName             = State or Province Name
localityName                    = Locality Name
0.organizationName              = Organization Name
organizationalUnitName          = Organizational Unit Name
commonName                      = Common Name
emailAddress                    = Email Address

# Optionally, specify some defaults.
countryName_default             = DE
stateOrProvinceName_default     = Hamburg
localityName_default            = Hamburg
0.organizationName_default      = Otto (GmbH & Co KG)
organizationalUnitName_default  = IT-KS-EI
emailAddress_default            = hendrik.halkow@otto.de
commonName_default              = Hendrik M Halkow Root CA

[ v3_ca ]
# Extensions for a typical CA (`man x509v3_config`).
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true
keyUsage = critical, digitalSignature, cRLSign, keyCertSign

[ v3_intermediate_ca ]
# Extensions for a typical intermediate CA (`man x509v3_config`).
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true, pathlen:0
keyUsage = critical, digitalSignature, cRLSign, keyCertSign

[ usr_cert ]
# Extensions for client certificates (`man x509v3_config`).
basicConstraints = CA:FALSE
nsCertType = client, email
nsComment = "OpenSSL Generated Client Certificate"
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
keyUsage = critical, nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth, emailProtection

[ server_cert ]
# Extensions for server certificates (`man x509v3_config`).
basicConstraints = CA:FALSE
nsCertType = server
nsComment = "OpenSSL Generated Server Certificate"
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer:always
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[ crl_ext ]
# Extension for CRLs (`man x509v3_config`).
authorityKeyIdentifier=keyid:always

[ ocsp ]
# Extension for OCSP signing certificates (`man ocsp`).
basicConstraints = CA:FALSE
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
keyUsage = critical, digitalSignature
extendedKeyUsage = critical, OCSPSigning
```

### Intermediate CA configuration file

```ini
# intermediate-ca.cnf. Copy this file to "${TLS_HOME}/intermediate-ca/".

[ ca ]
# `man ca`
default_ca = CA_default

[ CA_default ]
# Directory and file locations.
dir               = .
certs             = $dir/certs
crl_dir           = $dir/crl
new_certs_dir     = $dir/newcerts
database          = $dir/index.txt
serial            = $dir/serial
RANDFILE          = $dir/private/.rand

# The root key and root certificate.
private_key       = $dir/private/intermediate.key.pem
certificate       = $dir/certs/intermediate.cert.pem

# For certificate revocation lists.
crlnumber         = $dir/crlnumber
crl               = $dir/crl/intermediate.crl.pem
crl_extensions    = crl_ext
default_crl_days  = 30

# SHA-1 is deprecated, so use SHA-2 instead.
default_md        = sha256

name_opt          = ca_default
cert_opt          = ca_default
default_days      = 375
preserve          = no
policy            = policy_loose

[ policy_strict ]
# The root CA should only sign intermediate certificates that match.
# See the POLICY FORMAT section of `man ca`.
countryName             = match
stateOrProvinceName     = match
organizationName        = match
organizationalUnitName  = optional
commonName              = supplied
emailAddress            = optional

[ policy_loose ]
# Allow the intermediate CA to sign a more diverse range of certificates.
# See the POLICY FORMAT section of the `ca` man page.
countryName             = optional
stateOrProvinceName     = optional
localityName            = optional
organizationName        = optional
organizationalUnitName  = optional
commonName              = supplied
emailAddress            = optional

[ req ]
# Options for the `req` tool (`man req`).
default_bits        = 2048
distinguished_name  = req_distinguished_name
string_mask         = utf8only

# SHA-1 is deprecated, so use SHA-2 instead.
default_md          = sha256

# Extension to add when the -x509 option is used.
x509_extensions     = v3_ca

[ req_distinguished_name ]
# See <https://en.wikipedia.org/wiki/Certificate_signing_request>.
countryName                     = Country Name (2 letter code)
stateOrProvinceName             = State or Province Name
localityName                    = Locality Name
0.organizationName              = Organization Name
organizationalUnitName          = Organizational Unit Name
commonName                      = Common Name
emailAddress                    = Email Address

# Optionally, specify some defaults.
countryName_default             = DE
stateOrProvinceName_default     = Hamburg
localityName_default            = Hamburg
0.organizationName_default      = Otto (GmbH & Co KG)
organizationalUnitName_default  = IT-KS-EI
emailAddress_default            = hendrik.halkow@otto.de
commonName_default              = Hendrik M Halkow Intermediate CA

[ v3_ca ]
# Extensions for a typical CA (`man x509v3_config`).
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true
keyUsage = critical, digitalSignature, cRLSign, keyCertSign

[ v3_intermediate_ca ]
# Extensions for a typical intermediate CA (`man x509v3_config`).
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true, pathlen:0
keyUsage = critical, digitalSignature, cRLSign, keyCertSign

[ usr_cert ]
# Extensions for client certificates (`man x509v3_config`).
basicConstraints = CA:FALSE
nsCertType = client, email
nsComment = "OpenSSL Generated Client Certificate"
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
keyUsage = critical, nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth, emailProtection

[ server_cert ]
# Extensions for server certificates (`man x509v3_config`).
basicConstraints = CA:FALSE
nsCertType = server
nsComment = "OpenSSL Generated Server Certificate"
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer:always
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[ crl_ext ]
# Extension for CRLs (`man x509v3_config`).
authorityKeyIdentifier=keyid:always

[ ocsp ]
# Extension for OCSP signing certificates (`man ocsp`).
basicConstraints = CA:FALSE
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
keyUsage = critical, digitalSignature
extendedKeyUsage = critical, OCSPSigning
```

### Minikube certificate configuration file

```ini
# minikube.local.cnf. Copy this file to "${TLS_HOME}/intermediate-ca/".

[ ca ]
# `man ca`
default_ca = CA_default

[ CA_default ]
# Directory and file locations.
dir               = .
certs             = $dir/certs
crl_dir           = $dir/crl
new_certs_dir     = $dir/newcerts
database          = $dir/index.txt
serial            = $dir/serial
RANDFILE          = $dir/private/.rand

# The root key and root certificate.
private_key       = $dir/private/intermediate.key.pem
certificate       = $dir/certs/intermediate.cert.pem

# For certificate revocation lists.
crlnumber         = $dir/crlnumber
crl               = $dir/crl/intermediate.crl.pem
crl_extensions    = crl_ext
default_crl_days  = 30

# SHA-1 is deprecated, so use SHA-2 instead.
default_md        = sha256

name_opt          = ca_default
cert_opt          = ca_default
default_days      = 375
preserve          = no
policy            = policy_loose

[ policy_strict ]
# The root CA should only sign intermediate certificates that match.
# See the POLICY FORMAT section of `man ca`.
countryName             = match
stateOrProvinceName     = match
organizationName        = match
organizationalUnitName  = optional
commonName              = supplied
emailAddress            = optional

[ policy_loose ]
# Allow the intermediate CA to sign a more diverse range of certificates.
# See the POLICY FORMAT section of the `ca` man page.
countryName             = optional
stateOrProvinceName     = optional
localityName            = optional
organizationName        = optional
organizationalUnitName  = optional
commonName              = supplied
emailAddress            = optional

[ req ]
# Options for the `req` tool (`man req`).
default_bits        = 2048
distinguished_name  = req_distinguished_name
string_mask         = utf8only

# SHA-1 is deprecated, so use SHA-2 instead.
default_md          = sha256

# Extension to add when the -x509 option is used.
x509_extensions     = v3_ca

req_extensions = req_ext


[ req_distinguished_name ]
# See <https://en.wikipedia.org/wiki/Certificate_signing_request>.
countryName                     = Country Name (2 letter code)
stateOrProvinceName             = State or Province Name
localityName                    = Locality Name
0.organizationName              = Organization Name
organizationalUnitName          = Organizational Unit Name
commonName                      = Common Name
emailAddress                    = Email Address

# Optionally, specify some defaults.
countryName_default             = DE
stateOrProvinceName_default     = Hamburg
localityName_default            = Hamburg
0.organizationName_default      = Otto (GmbH & Co KG)
organizationalUnitName_default  = IT-KS-EI
emailAddress_default            = hendrik.halkow@otto.de
commonName_default              = minikube.local

[ v3_ca ]
# Extensions for a typical CA (`man x509v3_config`).
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true
keyUsage = critical, digitalSignature, cRLSign, keyCertSign

[ v3_intermediate_ca ]
# Extensions for a typical intermediate CA (`man x509v3_config`).
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true, pathlen:0
keyUsage = critical, digitalSignature, cRLSign, keyCertSign

[ usr_cert ]
# Extensions for client certificates (`man x509v3_config`).
basicConstraints = CA:FALSE
nsCertType = client, email
nsComment = "OpenSSL Generated Client Certificate"
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
keyUsage = critical, nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth, emailProtection

[ server_cert ]
# Extensions for server certificates (`man x509v3_config`).
basicConstraints = CA:FALSE
nsCertType = server
nsComment = "OpenSSL Generated Server Certificate"
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer:always
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName=@alt_names

[ crl_ext ]
# Extension for CRLs (`man x509v3_config`).
authorityKeyIdentifier=keyid:always

[ ocsp ]
# Extension for OCSP signing certificates (`man ocsp`).
basicConstraints = CA:FALSE
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
keyUsage = critical, digitalSignature
extendedKeyUsage = critical, OCSPSigning

[ req_ext ]
subjectAltName = @alt_names

[ alt_names ]
DNS.1 = minikube.local
DNS.2 = *.minikube.local
```

[1]: https://github.com/kubernetes/ingress-nginx/tree/master/docs/examples/customization/ssl-dh-param
