# Datalake Labfaber

This repo contains all components of a data lakehouse to be installed on a kubernetes cluster on ./infrastructure folder.

It also contains data-pipelines to be instantiated on airflow inside ./data-pipelines.

## Installation

### Global Certificate

It is necessary to create a wildcard CERTI chain certificate to be used on every application.

```bash
kubectl create secret tls streaming-tls-scret \
  --cert=infrastructure/keys/certi-chain.crt \
  --key=infrastructure/keys/certi.key \
  -n cert-manager
```

### Custom Default Certificate for Traefik

1. Create a Secret with Your TLS Certificate and Key

    ```bash
    kubectl create secret tls tls-secret --cert=infrastructure/keys/certi-chain.crt --key=infrastructure/keys/certi.key -n kube-system
    ```

    This command creates a secret called tls-secret in the kube-system namespace, which is where Traefik runs in k3s by default.

2. Create a ConfigMap for traefik-config Configuration

    Create a ConfigMap that contains the traefik-config TLS configuration for Traefik. This configuration will tell Traefik to use the wildcard certificate as the default.

    Create a file named traefik-config.yaml with the following content or use infrastructure/yamls/ingress/traefik-config.yaml:

    ```yaml
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: traefik-config
      namespace: kube-system
    data:
      traefik-config.yaml: |
        tls:
          stores:
            default:
              defaultCertificate:
                certFile: "/certs/tls.crt"
                keyFile: "/certs/tls.key"
    ```

    Apply the ConfigMap:

    ```bash
    kubectl apply -f traefik-config.yaml
    ```

    This creates a ConfigMap named traefik-config in the kube-system namespace with the necessary TLS configuration.

3. Modify Traefik Deployment to Use the ConfigMap and Secret

    Now, modify the Traefik deployment to mount the ConfigMap and Secret as volumes and use the traefik-config configuration file.

    Edit the default Traefik deployment in k3s. Run:

    ```bash
    export EDITOR=nano
    kubectl edit deployment traefik -n kube-system
    ```

    Make the following modifications:

    * Add volumes to mount the tls-secret and traefik-config ConfigMap.
    * Update the args section to include the traefik-config configuration file.

    Update the deployment to look similar to this:

    ```yaml
    spec:
      containers:
      - args:
        - --configFile=/config/traefik.yaml
        - --providers.file.filename=/config/traefik-config.yaml  # Add this line to point to the traefik-config config file
        name: traefik
        volumeMounts:
        - mountPath: /config
          name: traefik-config
        - mountPath: /certs
          name: tls-secret
      volumes:
      - name: traefik-config
        configMap:
          name: traefik-config
      - name: tls-secret
        secret:
          secretName: tls-secret
    ```

    * args:
      * Add the argument --providers.file.filename=/config/traefik-config.yaml to point Traefik to the traefik-config configuration file.

    * volumeMounts:
      * Mount /config to traefik-config to make the configuration available.
      * Mount /certs to tls-secret so that Traefik can access the certificate and key.

    * volumes:
      * Use a ConfigMap volume named traefik-config.
      * Use a Secret volume named tls-secret.

4. Restart Traefik Pods
    After editing the deployment, restart the Traefik pods to apply the changes:

    ```bash
    kubectl rollout restart deployment traefik -n kube-system
    ```

    This command will restart Traefik, causing it to read the new dynamic configuration and load the custom wildcard certificate.

5. Verify the Configuration
    Check Logs: Check Traefik logs to see if there are any errors loading the certificate:

    ```bash
    kubectl logs -l app=traefik -n kube-system
    ```

References:

1. <https://github.com/traefik/traefik-helm-chart/issues/187#issuecomment-700933892>

2. <https://blog.kronis.dev/tutorials/how-to-add-a-wildcard-ssl-tls-certificate-for-your-k3s-cluster>

### Longhorn

Longhorn is an open-source, distributed block storage system for Kubernetes that provides persistent storage for containerized applications. Developed by Rancher Labs, it simplifies managing persistent volumes by offering a lightweight, reliable, and high-availability solution. Longhorn runs directly on Kubernetes and creates storage volumes that can be replicated across multiple nodes, ensuring resilience against hardware failures. It features an easy-to-use interface, snapshot capabilities, and built-in backup and restoration, making it a robust choice for managing stateful workloads in Kubernetes environments. Longhorn is particularly useful for users seeking scalable storage solutions that are fully integrated with Kubernetes and optimized for cloud-native applications.

Create TLS certificate

```bash
k create namespace longhorn-system

kubectl get secret streaming-tls-scret -n kube-system -o yaml | \
  sed -e "s/namespace: kube-system/namespace: longhorn-system /" \
      -e 's/name: streaming-tls-scret/name: streaming-tls-scret/' \
      -e '/resourceVersion/d' \
      -e '/uid/d' \
      -e '/creationTimestamp/d' | \
  kubectl apply -n longhorn-system -f -
```

To install Longhorn, execute the following line:

```bash
helm install longhorn -n longhorn-system infrastructure/helm-charts/longhorn --values=infrastructure/helm-charts/longhorn/values.yaml --create-namespace
```

Then change the local-path default storage to not default.

```bash
kubectl patch storageclass local-path -p '{"metadata": {"annotations": {"storageclass.kubernetes.io/is-default-class": "false"}}}'
```

After installation, go to the web interface Setting > General and change the Default Replica Count for 1 and Snapshot Max Quantity to 2.

Specially Minio does not need the replication as it does for itself, but if you have a dedicated storage for this platform you can maintain the default configuration.

### ArgoCD

ArgoCD is a declarative, GitOps continuous delivery tool for Kubernetes. It allows you to manage and deploy Kubernetes applications using manifests in Git repositories. ArgoCD continuously monitors your Git repository for changes and syncs those changes to your Kubernetes cluster, making it easier to manage infrastructure and application deployment with a "source of truth" approach.

#### Features of ArgoCD

* **Declarative GitOps**: Tracks the desired state of your Kubernetes resources defined in Git.
* **Application Deployment**: Supports Helm, Kustomize, and raw Kubernetes manifests.
* **Automated Rollbacks**: Automatically rollbacks on deployment failures.
* **Monitoring and Health Checks**: Real-time status and health assessments of applications.

#### Installation using Helm Chart

To install ArgoCD from a local Helm chart, follow these steps:

1. **Install ArgoCD using Helm**:
    ArgoCD is configured to use traefik ingress. So you should visit and alter infrastructure/helm-charts/argo-cd/values.yaml to adjust your domain name.

    ```yaml
        ## Globally shared configuration
        global:
            # -- Default domain used by all components
            ## Used for ingresses, certificates, SSO, notifications, etc.
            domain: cicd-kube-cpc.certi.org.br
    ```

    Create TLS secret from base streaming-tls-scret.

    ```bash
    k create namespace cicd
    kubectl get secret streaming-tls-scret -n kube-system -o yaml | \
      sed -e "s/namespace: kube-system/namespace: cicd /" \
          -e 's/name: streaming-tls-scret/name: argocd-server-tls/' \
          -e '/resourceVersion/d' \
          -e '/uid/d' \
          -e '/creationTimestamp/d' | \
      kubectl apply -n cicd -f -
    ```

   * Use the `helm install` command to install ArgoCD in the Kubernetes cluster, specifying the namespace, the chart path, and the values file.
   * Here's the command:

     ```sh
     helm install argocd -n cicd infrastructure/helm-charts/argo-cd --values=infrastructure/helm-charts/argo-cd/values.yaml --create-namespace
     ```

   * Breakdown of the command:

   * **`helm install argocd`**: Installs the Helm release named "argocd".
   * **`-n cicd`**: Specifies the namespace for ArgoCD (`cicd`). If the namespace doesn't exist, it will be created.
   * **`infrastructure/helm-charts/argo-cd`**: Path to the local Helm chart for ArgoCD.
   * **`--values=.../values.yaml`**: Specifies custom values to override the default chart values.
   * **`--create-namespace`**: Creates the namespace (`cicd`) if it does not exist.

2. **Verify the Installation**:

   * Check the status of the ArgoCD pods to ensure they are running:

     ```sh
     kubectl get pods -n cicd
     ```

3. **Get Initial Admin Password**

   * The initial admin password is stored in a Kubernetes secret called `argocd-initial-admin-secret`. You can retrieve it using the following command:

     ```sh
     kubectl get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" -n cicd | base64 -d && echo
     ```

   * **Explanation**:
     * **`kubectl get secret argocd-initial-admin-secret`**: Retrieves the secret that contains the ArgoCD admin password.
     * **`-o jsonpath="{.data.password}"`**: Extracts the `password` field.
     * **`base64 -d`**: Decodes the base64-encoded password.
     * **`&& echo`**: Prints a newline for better readability.

4. **Access the ArgoCD UI**:
    ArgoCD will be available at your domain name, but if you don't have it yet you can use port-forward.

   * Forward the ArgoCD server port to access the ArgoCD web UI on `<server-ip>:8080`:

     ```sh
     kubectl port-forward svc/argocd-server -n cicd 8080:443
     ```

   * Open your browser and navigate to `http://<server-ip>:8080`.

5. **Log in**:
   * Username: `admin`
   * Password: Use the password retrieved from the secret.

This process installs ArgoCD from a local Helm chart, sets it up in a Kubernetes namespace, and enables access to the ArgoCD UI. Once installed, you can start configuring your applications, linking them to Git repositories, and managing deployments using GitOps practices.

### Configure Bitbucket repos via SSH

To add a Git repository to ArgoCD using SSH, you'll need to generate a private SSH key pair, add the public key to your repository, and configure ArgoCD to use the private key for authentication. Below are detailed steps to achieve this.

### Step-by-Step Guide:

#### 1. Create an SSH Key Pair

1. **Generate an SSH key pair** on your local machine. This key pair will be used for authentication with your Git repository:

   ```sh
   ssh-keygen -t ed25519 -C "argocd" -f infrastructure/keys
   ```

   * **`-t ed25519`**: Specifies the key type (Ed25519 is a secure modern key type).
   * **`-C "argocd-access"`**: A comment to identify the key.
   * **`-f ~/.ssh/argocd`**: The file name for the private key (`argocd`), and the public key will be saved as `argocd.pub`.

   You can choose a different key type, such as RSA (`-t rsa`), if needed.

2. You will now have two files:
   * **`argocd`**: The private key.
   * **`argocd.pub`**: The public key.

#### 2. Add the Public SSH Key to the Git Repository

* Go to your Git provider's web UI (e.g., GitHub, GitLab, Bitbucket).
* Navigate to the repository or user settings where you can add SSH keys.
* **Add the content of `argocd.pub`** to the SSH keys section in your Git provider. This allows the repository to accept connections from the corresponding private key.

##### For Bitbucket:

* Bitbucket has specific instructions for adding SSH keys. You can follow the official documentation:
  [Bitbucket Documentation on Adding SSH Keys](https://support.atlassian.com/bitbucket-cloud/docs/set-up-an-ssh-key/)

#### 3. Add the Private Key to ArgoCD

1. **Create a Kubernetes secret** to store the SSH private key. ArgoCD will use this secret to authenticate with the Git repository. Replace `path/to/argocd` with the actual path to your private key:

   ```sh
   kubectl create secret generic git-repo-ssh-key \
     --from-file=sshPrivateKey=infrastructure/keys/argocd \
     -n cicd
   ```

   * **`<repo-secret-name>`**: A name for the secret, such as `git-repo-ssh-key`.
   * **`<argocd-namespace>`**: The namespace where ArgoCD is installed (e.g., `cicd`).

2. **Add the repository to ArgoCD** by using the following command:

   ```sh
   argocd repo add git@bitbucket.org:certi_repos/datalake-labfaber.git \
     --ssh-private-key-path infrastructure/keys/argocd \
     --name datalake
   ```

   * **`git@bitbucket.org:<username>/<repository>.git`**: The SSH URL of your repository.
   * **`--ssh-private-key-path infrastructure/keys/argocd`**: The path to your private key.
   * **`--name <repository-name>`**: A name for the repository in ArgoCD.

Alternatively, you can add the repository via the **ArgoCD Web UI**:

* Go to the **Repositories** section.
* Click **Add Repository**.
* Select **SSH** as the type.
* Enter the SSH URL and upload the private key file.
* Finish setup clicking "CONNECT".

If everything was ok CONNECTION STATUS for the repo will be "Sucessful".

#### 4. Verify Access and Sync

1. After adding the repository, **verify** that ArgoCD has successfully connected by checking the repository's sync status.
2. You can test deploying an application from this repository to ensure everything is configured correctly.

## Setup Environment

Before creating apps, you should visit every folder inside infrastructure/app-manifests and create a secret.yaml file from the secret.yaml-example.

For trino there is a special case where you also need to create a password DB.

```bash
htpasswd -nb admin your_password_here > infrastructure/app-manifests/querying/password.db
k create namespace querying
k create secret generic trino-password-auth -n querying --from-file=infrastructure/app-manifests/querying/password.db
```

For airflow there is a special case where webserver needs to be configured as a secret. Run the code below and copy past the result to the secret file.

``` bash
cat infrastructure/app-manifests/orchestrator/webserver_config.py | base64 -w 0
```

Then you should create other namespaces, copy TLS certificates and apply all app manifests for ArgoCD to manage. It will install all Helms available at infrastructure/helm-charts.

```bash
k create namespace governance && \
k create secret generic mysql-secrets -n governance --from-literal=openmetadata-mysql-password=openmetadata_password && \
k create secret generic airflow-secrets -n governance --from-literal=openmetadata-airflow-password=admin && \
k create secret generic airflow-mysql-secrets -n governance --from-literal=airflow-mysql-password=airflow_pass && \
k create namespace data-viz && \
k create namespace deepstorage && \
k create namespace iam && \
k create namespace ingestion && \
k create namespace harbor && \
k create namespace monitoring && \
k create namespace orchestrator && \
k create namespace datastore && \
k create namespace spark-jobs && \
k create namespace spark-operator && \
k create namespace analytics
```

After creating namespaces, copy the TLS to each namespace.

```bash
namespaces=("governance" "data-viz" "querying" "deepstorage" "iam" "datastore" "ingestion" "harbor" "monitoring" "spark-jobs" "orchestrator" "analytics" "longhorn-system" "spark-operator" "kube-system")

for ns in "${namespaces[@]}"; do
  kubectl get secret streaming-tls-scret -n kube-system -o yaml | \
  sed -e "s/namespace: kube-system/namespace: ${ns}/" \
      -e '/resourceVersion/d' \
      -e '/uid/d' \
      -e '/creationTimestamp/d' | \
  kubectl apply -n ${ns} -f -
done

kubectl get secret streaming-tls-scret -n kube-system -o yaml | \
sed -e "s/namespace: kube-system/namespace: cicd /" \
    -e 's/name: streaming-tls-scret/name: argocd-server-tls/' \
    -e '/resourceVersion/d' \
    -e '/uid/d' \
    -e '/creationTimestamp/d' | \
kubectl apply -n cicd -f -

kubectl get secret streaming-tls-scret -n kube-system -o yaml | \
sed -e "s/namespace: kube-system/namespace: querying /" \
    -e 's/name: streaming-tls-scret/name: trino-tls-secret/' \
    -e '/resourceVersion/d' \
    -e '/uid/d' \
    -e '/creationTimestamp/d' | \
kubectl apply -n querying -f -
```

Then finish app creation by executing:

```bash
k apply -R -f infrastructure/app-manifests
```

Now you should visit ArgoCD and see the applications starting.

## Harbor

Latency issues causes images to not be pushed to harbor. Prefer to build and push images from build servers, but if you don't have that option you may opt for exposing the unsecure http port via node port to reduce overhead.

So a patch is necessary for exposing the registry http port as nodePort.

```bash
kubectl patch svc harbor-registry -p '{
  "spec": {
    "type": "NodePort",
    "ports": [
      {
        "port": 8080,
        "targetPort": 8080,
        "protocol": "TCP",
        "name": "http",
        "nodePort": 32428
      }
    ]
  }
}'
```

Docker will complain about an insecure registry, so edit the daemon configuration:

```bash
sudo nano /etc/docker/daemon.json
```

And add the following configuration:

```json
{
  "insecure-registries": ["registry-cpc.certi.org.br:32428"]
}
```

```bash
sudo systemctl restart docker
```

Now you can log to the registry by providing your credentials:

```bash
docker login registry-cpc.certi.org.br
```

And you can push an image by:

```bash
docker push registry-cpc:32428/<\project>/<\image>:<\tag>
```

If the problem persists you should consider the safe way using HTTPS and a build server.

## Keycloak

### Manually Importing Realms on Keycloak UI

This guide will walk you through the steps needed to manually import realms into the Keycloak admin console. You can use this method when you need to migrate configurations from one Keycloak instance to another or set up a new realm from an existing JSON file.

### Step-by-Step Instructions

1. **Log in to Keycloak Admin Console**
   * Open your browser and navigate to your Keycloak instance URL (e.g., `http://https://iam-cpc.certi.org.br/auth`).
   * Log in using your admin credentials.

2. **Navigate to Realm Management**
   * On the left-hand side menu, click the dropdown at the top where the realm name is displayed.
   * Click **“Add Realm”** to create a new realm.

3. **Import Realm**
   * In the **Add Realm** screen, you'll see an option labeled **“Import”**.
   * Get default realm files from infrastructure/app-manifests/iam/keycloak-realms
   * Copy paste the content from the .json or click the **“Select file”** button and browse to the location where you have stored the realm JSON file.
   * Select the file and click **“Upload”**.

4. **Review and Adjust Configuration**
   * After uploading the file, Keycloak will display the details of the imported realm.
   * Verify all the settings, such as realm name, clients, roles, and users. Remove or adjust any incorrect configurations or conflicts (e.g., duplicate clients).

5. **Save the Realm**
   * Click the **“Create”** button at the bottom to create the new realm.
   * After saving, you will be redirected to the newly imported realm in the admin console.

### Common Issues and Tips

* **UUID Errors**: If your JSON file was exported from another Keycloak instance, remove any UUID fields to avoid conflicts.
* **Credential Secrets**: Credentials for users and clients may not import correctly, and may need to be reconfigured manually after importing.
* **Redirect URIs**: Check that client redirect URIs are correctly set for your environment.

### Verification

* Test the imported realm by logging into it.
* Verify that all the expected clients, roles, groups, and users have been imported correctly.

## Kubelens

Kubelens is a Kubernetes monitoring tool that provides a visual interface to help troubleshoot issues within Kubernetes clusters. It offers features like detailed pod information, logs, metrics, and insights into cluster health.

### Installation Steps

#### On Linux:

1. **Install via Binary**:

   * Visit the [Kubelens GitHub releases page](https://github.com/kubelens/kubelens/releases).
   * Download the appropriate Linux binary (`kubelens-linux`).
   * Make the binary executable:

    ```sh
    chmod +x kubelens-linux
    ```

   * Move it to a directory in your `PATH`:

    ```sh
    sudo mv kubelens-linux /usr/local/bin/kubelens
    ```

   * Verify the installation:

    ```sh
    kubelens --version
    ```

2. **Run Kubelens**:
   * Start Kubelens by running:

    ```sh
    kubelens
    ```

   * Then access it via the browser at `http://localhost:8080`.

#### On Windows

1. **Install via Binary**:
   * Visit the [Kubelens GitHub releases page](https://github.com/kubelens/kubelens/releases).
   * Download the Windows binary (`kubelens.exe`).
   * Place the executable in a directory that is in your system `PATH`.

2. **Run Kubelens**:
   * Open a command prompt and start Kubelens by running:

    ```sh
    kubelens.exe
    ```

   * Access Kubelens in your web browser at `http://localhost:8080`.

After installing, you will need to configure access to your Kubernetes cluster. Make sure you have the correct kubeconfig file to authenticate with your cluster, as Kubelens uses this configuration for connecting.

### 1. **Create a User Certificate for `kubelens`**

If you haven’t already, follow these steps to create a user certificate for `kubelens`. This user will be authenticated using TLS certificates.

### Step 1: Generate the Key and CSR

Run the following commands to create a private key and a certificate signing request (CSR) for the `kubelens` user:

```bash
openssl genrsa -out infrastructure/keys/kubelens.key 2048
openssl req -new -key infrastructure/keys/kubelens.key -out infrastructure/keys/kubelens.csr -subj "/CN=kubelens"

```

### Step 2: Create the CertificateSigningRequest Resource in Kubernetes

Submit the CSR to Kubernetes to request a signed certificate:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: certificates.k8s.io/v1
kind: CertificateSigningRequest
metadata:
  name: kubelens
spec:
  request: $(cat infrastructure/keys/kubelens.csr | base64 | tr -d '\n')
  signerName: kubernetes.io/kube-apiserver-client
  usages:
  - client auth
EOF
```

### Step 3: Approve the CSR

Once the CSR is submitted, approve it:

```bash
kubectl certificate approve kubelens

```

### Step 4: Get the Signed Certificate

After the CSR has been approved, retrieve the signed certificate:

```bash
kubectl get csr kubelens -o jsonpath='{.status.certificate}' | base64 --decode > infrastructure/keys/kubelens.crt

```

Now you have the following:

* `infrastructure/keys/kubelens.key` (Private key)
* `infrastructure/keys/kubelens.crt` (Signed certificate)

### 2. **Create Full Permission Role and RoleBinding for `kubelens`**

### Step 1: Create a ClusterRoleBinding for the `kubelens` User

To grant `kubelens` full access to the cluster, you can bind the user to the built-in `cluster-admin` role, which has full administrative privileges.

Create a **ClusterRoleBinding** for `kubelens` using this YAML:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: kubelens-admin-binding
subjects:
- kind: User
  name: kubelens
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: rbac.authorization.k8s.io
EOF

```

This will bind the `kubelens` user to the `cluster-admin` ClusterRole, effectively giving the user full access to the Kubernetes cluster.

### 2. **Configure `kubelens` on windows**

Copy files:

* `infrastructure/keys/kubelens.key` (Private key)
* `infrastructure/keys/kubelens.crt` (Signed certificate)

To:

```text
%appdata%\Lens\kubeconfigs
```

Then you should add on kubelens the following kubeconfig template.

Substitute cluster IP and user for your context.

```yaml
apiVersion: v1
clusters:
- cluster:
    server: https://<your-cluster-ip>:6443
    insecure-skip-tls-verify: true
  name: labfaber
contexts:
- context:
    cluster: labfaber
    user: kubelens
  name: labfaber
current-context: labfaber
kind: Config
preferences: {}
users:
- name: kubelens
  user:
    client-certificate: C:\Users\<user>\AppData\Roaming\Lens\kubeconfigs\kubelens.crt
    client-key: C:\Users\<user>\AppData\Roaming\Lens\kubeconfigs\kubelens.key
```

### 3. **Configure the kubeconfig File for `kubelens` on Linux or WSL for testing**

To allow the `kubelens` user to connect to the Kubernetes API using the new certificate, update the `kubeconfig` file to use the newly created certificate and key.

Run the following commands to set up `kubelens` in your kubeconfig:

```bash
kubectl config set-credentials kubelens --client-certificate=infrastructure/keys/kubelens.crt --client-key=infrastructure/keys/kubelens.key
kubectl config set-context kubelens-context --cluster=labfaber --user=kubelens
kubectl config use-context kubelens-context

```

### 4. **Verify Permissions**

You can verify that the `kubelens` user has full permissions by running a command like the following:

```bash
kubectl --context kubelens-context get pods --all-namespaces

```

This command should list all pods in all namespaces if the `kubelens` user has full permissions.

### 5. **Using the User in Lens**

1. **Pass the kubeconfig** to **Lens**, as mentioned in the previous steps.
2. Ensure that `kubelens` is the active user within Lens, and Lens should have full access to the Kubernetes cluster using the permissions of `kubelens`.

This setup gives the `kubelens` user full permissions within your Kubernetes cluster by binding them to the `cluster-admin` role.

## Update TLS Certificate

First delete all the certificate secrets.

```bash
for ns in $(kubectl get namespaces -o jsonpath='{.items[*].metadata.name}'); do
  kubectl delete secret streaming-tls-scret -n $ns --ignore-not-found
done
```

Then create a new one with the new certificate.

```bash
kubectl create secret tls streaming-tls-scret \
  --cert=infrastructure/keys/certi-chain.crt \
  --key=infrastructure/keys/certi.key \
  -n kube-system
```

Then reacreate all secrets in namespaces.

```bash
namespaces=("deepstorage" "ingestion" "monitoring" "spark-jobs" "longhorn-system" "spark-operator")

for ns in "${namespaces[@]}"; do
  kubectl get secret streaming-tls-scret -n kube-system -o yaml | \
  sed -e "s/namespace: kube-system/namespace: ${ns}/" \
      -e '/resourceVersion/d' \
      -e '/uid/d' \
      -e '/creationTimestamp/d' | \
  kubectl apply -n ${ns} -f -
done

kubectl get secret streaming-tls-scret -n kube-system -o yaml | \
sed -e "s/namespace: kube-system/namespace: cicd /" \
    -e 's/name: streaming-tls-scret/name: argocd-server-tls/' \
    -e '/resourceVersion/d' \
    -e '/uid/d' \
    -e '/creationTimestamp/d' | \
kubectl apply -n cicd -f -
```

### Use harbor registry

Orchestrator needs to use harbor registry for some pipelines. You need to create the following secret:

```bash
kubectl create secret docker-registry harbor-robot-secret -n orchestrator \
    --docker-server=https://registry-cpc.certi.org.br \
    --docker-username=admin \
    --docker-password=<password> \
    --docker-email=<email>@certi.org.br
```

## Troubleshooting

1. **Error:** longhorn already mounted or mount point busy. dmesg(1) may have more information after failed mount system call.
  **Solution**: <https://longhorn.io/kb/troubleshooting-volume-with-multipath/>