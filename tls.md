# Setting up your own certificate authority

Disclaimer: This setup is only for development purposes.
For a production CA, you want to keep the root certificate on another secure
computer that is not connected to the internet.

## Prerequisites for macOS

Install OpenSSL via Homebrew. The version that comes with the operating system
doesn't like environment variables in the config files which our setup makes
use of.

```zsh
brew install openssl
```

## Prerequisites for Windows

As Windows’ TLS components are only part of Windows server, you need to get
OpenSSL in another way. You can don this by deploying a pod into your Kubernetes
cluster for that purpose.

```powershell
# ProgramData is at C:\ProgramData by default.
${CA_BASE_DIR}="${env:ProgramData}\CA"
New-Item -ItemType directory -Path "${CA_BASE_DIR}"

Write-Output @"
apiVersion: v1
kind: Pod
metadata:
  namespace: default
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
    workingDir: "/ca"
    volumeMounts:
    - mountPath: "/ca"
      name: caBaseDir
    env:
    - name: CA_BASE_DIR
      value: /ca
  volumes:
  - name: caBaseDir
    hostPath:
      path: "${CA_BASE_DIR}"
"@ | kubectl create -f -

# Attach to OpenSSL pod.
kubectl attach --namespace "${K8S_NAMESPACE}" openssl -i -t

# After you are done with this, you can remove this pod. As you mounted your
# Host folder into your pod, you data will not be deleted.
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

## Set up certificate authorities

```zsh
# In case we use this shell interactively, set path to Homebrew's OpenSSL.
export PATH="/usr/local/opt/openssl/bin:${PATH}"

# Directory that contains all CAs.
export CA_BASE_DIR="/usr/local/etc/openssl/ca"

# Save PS1 to restore it later.
if [ -z "${PS1_ORIGINAL}" ]; then PS1_ORIGINAL="${PS1}"; fi

# Sets the CA, CA_DIR and CA_PASSWORD variables.
# Prefixes your PS1 with your current CA.
function ca_set_context() {
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
}

# Initializes a CA.
function ca_init() {
  mkdir -p "${CA_DIR}"/{certs,csr,newcerts,private}/
  chmod 0700 "${CA_DIR}/private"
  touch "${CA_DIR}/index.txt"
  echo 1000 > "${CA_DIR}/serial"
  openssl genrsa \
  -aes256 \
  -passout "pass:${CA_PASSWORD}" \
  -out "${CA_DIR}/private/${CA}.key.pem" 4096
  ln -s "${CA}.key.pem" "${CA_DIR}/private/key.pem"
  chmod 0400 "${CA_DIR}/private/${CA}.key.pem"
  if [ -z "${PARENT_CA}" ]; then
    openssl req \
      -new \
      -x509 \
      -days 7300 \
      -sha256 \
      -extensions "${CA} Extensions" \
      -key "${CA_DIR}/private/${CA}.key.pem" \
      -passin "pass:${CA_PASSWORD}" \
      -out "${CA_DIR}/certs/${CA}.cert.pem" \
      -subj "/C=DE/ST=Hamburg/L=Hamburg/O=$(id -F)/CN=${CA}"
    chmod 0444 "${CA_DIR}/certs/${CA}.cert.pem"
    touch "${CA_DIR}/chain.pem"
    cat "${CA_DIR}/certs/${CA}.cert.pem" >> "${CA_DIR}/fullchain.pem"
  else
    openssl req \
      -new \
      -sha256 \
      -extensions "${CA} Extensions" \
      -key "${CA_DIR}/private/key.pem" \
      -passin "pass:${CA_PASSWORD}" \
      -out "${CA_DIR}/csr/${CA}.csr.pem" \
      -subj "/C=DE/ST=Hamburg/L=Hamburg/O=$(id -F)/CN=${CA}"
    cp "${CA_DIR}/csr/${CA}.csr.pem" "${CA_BASE_DIR}/${PARENT_CA}/csr/"
    (
      CSR_DN="${CA}"
      CA="${PARENT_CA}"
      ca_set_context
      openssl ca \
        -name "${CA}" \
        -extensions "${CSR_DN} Extensions" \
        -days 3650 \
        -notext \
        -md sha256 \
        -passin "pass:${CA_PASSWORD}" \
        -in "${CA_DIR}/csr/${CSR_DN}.csr.pem" \
        -out "${CA_DIR}/certs/${CSR_DN}.cert.pem"
      chmod 0444 "${CA_DIR}/certs/${CSR_DN}.cert.pem"
      cp "${CA_DIR}/certs/${CSR_DN}.cert.pem" "${CA_BASE_DIR}/${CSR_DN}/certs/"
    )
    cat "${CA_DIR}/certs/${CA}.cert.pem" >> "${CA_DIR}/chain.pem"
    cat "${CA_BASE_DIR}/${PARENT_CA}/chain.pem" >> "${CA_DIR}/chain.pem"

    cat "${CA_DIR}/certs/${CA}.cert.pem" >> "${CA_DIR}/fullchain.pem"
    cat "${CA_BASE_DIR}/${PARENT_CA}/fullchain.pem" >> "${CA_DIR}/fullchain.pem"
  fi
  ln -s "certs/${CA}.cert.pem" "${CA_DIR}/cert.pem"
  chmod 0444 "${CA_DIR}/fullchain.pem"
  chmod 0444 "${CA_DIR}/chain.pem"
}

# The OpenSSL config file we will use.
OPENSSL_CONFIG_FILE=/usr/local/etc/openssl/openssl.cnf

# Create backup of OpenSSL config file.
if [ ! -f "${OPENSSL_CONFIG_FILE}.original" ]; then
  cp "${OPENSSL_CONFIG_FILE}" "${OPENSSL_CONFIG_FILE}.original"
fi

# Create new OpenSSL config.
cat <<EOD | >"${OPENSSL_CONFIG_FILE}"
[ ca ]
default_ca = $(id -F) Minikube CA

[ $(id -F) Root CA ]
dir = \$ENV::CA_BASE_DIR/\$ENV::CA
certs = \$dir/certs
crl_dir = \$dir/crl
database = \$dir/index.txt
new_certs_dir = \$dir/newcerts
certificate = \$dir/cert.pem
serial = \$dir/serial
crlnumber = \$dir/crlnumber
crl = \$dir/crl.pem
private_key = \$dir/private/key.pem
RANDFILE = \$dir/private/.rand
name_opt = ca_default
cert_opt = ca_default
default_days = 375
default_crl_days = 30
default_md = sha256
policy = policy_match
crl_extensions = crl_ext
preserve = no
email_in_dn = no
unique_subject = no

[ $(id -F) Minikube CA ]
dir = \$ENV::CA_BASE_DIR/\$ENV::CA
certs = \$dir/certs
crl_dir = \$dir/crl
database = \$dir/index.txt
new_certs_dir = \$dir/newcerts
certificate = \$dir/cert.pem
serial = \$dir/serial
crlnumber = \$dir/crlnumber
crl = \$dir/crl.pem
private_key = \$dir/private/key.pem
RANDFILE = \$dir/private/.rand
name_opt = ca_default
cert_opt = ca_default
default_days = 375
default_crl_days = 30
default_md = sha256
policy = policy_anything
crl_extensions = crl_ext
preserve = no
email_in_dn = no
copy_extensions = copy
unique_subject = no

[ policy_match ]
countryName = match
stateOrProvinceName = match
organizationName = match
organizationalUnitName = optional
commonName = supplied
emailAddress = optional

[ policy_anything ]
countryName = optional
stateOrProvinceName = optional
localityName = optional
organizationName = optional
organizationalUnitName = optional
commonName = supplied
emailAddress = optional

[ req ]
default_bits = 4096
distinguished_name = req_distinguished_name
string_mask = utf8only
default_md = sha256
x509_extensions = $(id -F) Minikube CA Extensions
req_extensions = v3_req

[ $(id -F) Root CA Extensions ]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true
keyUsage = critical, digitalSignature, cRLSign, keyCertSign

[ $(id -F) Minikube CA Extensions ]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true, pathlen:0
keyUsage = critical, digitalSignature, cRLSign, keyCertSign

[ req_distinguished_name ]
countryName = Country Name (2 letter code)
stateOrProvinceName = State or Province Name (full name)
localityName = Locality Name (eg, city)
0.organizationName = Organization Name (eg, company)
commonName = Common Name (e.g. server FQDN or YOUR name)

countryName_default = DE
stateOrProvinceName_default = Hamburg
localityName_default = Hamburg
0.organizationName_default = $(id -F)

[ v3_req ]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
EOD

# Create Root CA.
export CA="$(id -F) Root CA"
ca_set_context
PARENT_CA="" ca_init

# Delete old certificate if it exists.
sudo security delete-certificate -c "${CA}" -t

# Add root CA to key chain.
sudo security add-trusted-cert -d -k /Library/Keychains/System.keychain \
  "${CA_DIR}/cert.pem"
```

To make your browsers trust that certificate, restart Chrome or Safari. If you
use Firefox, you need to import this certificate via -> Preferences -> Privacy
and Security -> View Certificates -> Import.

```zsh
# Minikube CA.
export CA="$(id -F) Minikube CA"
ca_set_context
PARENT_CA="$(id -F) Root CA" ca_init
```

## Issue certificate and import it into K8s

```zsh
# Switch to the last CA in your chain.
export CA="$(id -F) Minikube CA"
ca_set_context

# The domain name the certificate will be issued to. If you want to use one
# certificate per namespace, you can use this:
TLS_CERT_DOMAIN="${K8S_NAMESPACE}.minikube.local"

# The name under which the certificate password is stored in Keychain.
TLS_CERT_PASSWORD_NAME="TLS certificate key password for ${TLS_CERT_DOMAIN}"

# Check if password is not in keychain, generate one if not.
TLS_CERT_PASSWORD="$(security find-generic-password -a ${USER} \
  -s "${TLS_CERT_PASSWORD_NAME}" -w || true)"
if [ -z "${TLS_CERT_PASSWORD}" ]; then
  TLS_CERT_PASSWORD="$(cat /dev/random | LC_ALL=C tr -dc a-zA-Z0-9 \
  | head -c 43)"
  security add-generic-password -a "${USER}" \
  -s "${TLS_CERT_PASSWORD_NAME}" -w "${TLS_CERT_PASSWORD}"
fi
echo "${TLS_CERT_PASSWORD_NAME}: ${TLS_CERT_PASSWORD}"

# Create TLS certificate key.
openssl genrsa \
  -aes256 \
  -passout "pass:${TLS_CERT_PASSWORD}" \
  -out "${CA_DIR}/private/${TLS_CERT_DOMAIN}.key.pem" 2048
chmod 0400 "${CA_DIR}/private/${TLS_CERT_DOMAIN}.key.pem"

# Create certificate signing request.
cat <<EOD | openssl req -config /dev/stdin \
  -passin "pass:${TLS_CERT_PASSWORD}" \
  -key "${CA_DIR}/private/${TLS_CERT_DOMAIN}.key.pem" \
  -new \
  -sha256 \
  -out "${CA_DIR}/csr/${TLS_CERT_DOMAIN}.csr.pem"
[ req ]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[ req_distinguished_name ]
C = DE
ST = Hamburg
L = Hamburg
O = $(id -F)
CN = ${TLS_CERT_DOMAIN}

[ v3_req ]
basicConstraints = CA:FALSE
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[ alt_names ]
DNS.1 = ${TLS_CERT_DOMAIN}
DNS.2 = *.${TLS_CERT_DOMAIN}
EOD

# View certificate signing request.
openssl req -in "${CA_DIR}/csr/${TLS_CERT_DOMAIN}.csr.pem" -text

# Issue certificate.
openssl ca \
  -name "${CA}" \
  -days 375 \
  -notext \
  -md sha256 \
  -passin "pass:${CA_PASSWORD}" \
  -in "${CA_DIR}/csr/${TLS_CERT_DOMAIN}.csr.pem" \
  -out "${CA_DIR}/certs/${TLS_CERT_DOMAIN}.cert.pem"
chmod 0444 "${CA_DIR}/certs/${TLS_CERT_DOMAIN}.cert.pem"

# View certificate.
openssl x509 -in "${CA_DIR}/certs/${TLS_CERT_DOMAIN}.cert.pem" \
  -text

# Verify certificate.
# Make sure that you use the same parent CA here as above.
PARENT_CA="$(id -F) Root CA"
openssl verify -CAfile "${CA_BASE_DIR}/${PARENT_CA}/fullchain.pem" \
  "${CA_DIR}/cert.pem"

# Delete old certificate if it exists.
kubectl --namespace "${K8S_NAMESPACE}" get secret minikube-tls 2>/dev/null && \
  kubectl --namespace "${K8S_NAMESPACE}" delete secret minikube-tls

# Import certificate into Kubernetes. We only import the chain, not the
# full chain.
kubectl --namespace "${K8S_NAMESPACE}" create secret tls minikube-tls \
  --key <(openssl rsa \
    -in "${CA_DIR}/private/${TLS_CERT_DOMAIN}.key.pem" \
    -passin "pass:${TLS_CERT_PASSWORD}") \
  --cert <(cat \
    "${CA_DIR}/certs/${TLS_CERT_DOMAIN}.cert.pem" \
    "${CA_DIR}/chain.pem")
```

## Create custom DH parameters for perfect forward secrecy

The following command will take a long time.

```zsh
cat <<EOD | kubectl create -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-configuration
  namespace: ${K8S_NAMESPACE}
  labels:
    app.kubernetes.io/name: ingress-nginx
    app.kubernetes.io/part-of: ingress-nginx
data:
  dhparam.pem: $(openssl dhparam 4096 2>/dev/null | base64)
EOD
```
