# ArgoCD

ArgoCD is a declarative, GitOps continuous delivery tool for Kubernetes. It allows you to manage and deploy Kubernetes applications using manifests in Git repositories. ArgoCD continuously monitors your Git repository for changes and syncs those changes to your Kubernetes cluster, making it easier to manage infrastructure and application deployment with a "source of truth" approach.

## Features of ArgoCD

- **Declarative GitOps**: Tracks the desired state of your Kubernetes resources defined in Git.
- **Application Deployment**: Supports Helm, Kustomize, and raw Kubernetes manifests.
- **Automated Rollbacks**: Automatically rollbacks on deployment failures.
- **Monitoring and Health Checks**: Real-time status and health assessments of applications.

### Installation using Helm Chart

To install ArgoCD from a local Helm chart, follow these steps:

1. **Install ArgoCD using Helm**:
    ArgoCD is configured to use traefik ingress. So you should visit and alter infrastructure/helm-charts/argo-cd/values.yaml to adjust your domain name.

    ```yaml
        ## Globally shared configuration
        global:
            # -- Default domain used by all components
            ## Used for ingresses, certificates, SSO, notifications, etc.
            domain: cicd.streaming-pipeline.com
    ```

    Create TLS secret from base streaming-pipeline-tls-secret.

    ```bash
    k create namespace cicd
    kubectl get secret streaming-pipeline-tls-secret -n kube-system -o yaml | \
      sed -e "s/namespace: kube-system/namespace: cicd /" \
          -e 's/name: streaming-pipeline-tls-secret/name: argocd-server-tls/' \
          -e '/resourceVersion/d' \
          -e '/uid/d' \
          -e '/creationTimestamp/d' | \
      kubectl apply -n cicd -f -
    ```

   - Use the `helm install` command to install ArgoCD in the Kubernetes cluster, specifying the namespace, the chart path, and the values file.
   - Here's the command:

     ```sh
     helm install argocd -n cicd infrastructure/helm-charts/argo-cd --values=infrastructure/helm-charts/argo-cd/values.yaml --create-namespace
     ```

   - Breakdown of the command:
     - **`helm install argocd`**: Installs the Helm release named "argocd".
     - **`-n cicd`**: Specifies the namespace for ArgoCD (`cicd`). If the namespace doesn't exist, it will be created.
     - **`infrastructure/helm-charts/argo-cd`**: Path to the local Helm chart for ArgoCD.
     - **`--values=.../values.yaml`**: Specifies custom values to override the default chart values.
     - **`--create-namespace`**: Creates the namespace (`cicd`) if it does not exist.

2. **Verify the Installation**:
   - Check the status of the ArgoCD pods to ensure they are running:

     ```sh
     kubectl get pods -n cicd
     ```

3. **Get Initial Admin Password**:
   - The initial admin password is stored in a Kubernetes secret called `argocd-initial-admin-secret`. You can retrieve it using the following command:

     ```sh
     kubectl get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" -n cicd | base64 -d && echo
     ```

   - **Explanation**:
     - **`kubectl get secret argocd-initial-admin-secret`**: Retrieves the secret that contains the ArgoCD admin password.
     - **`-o jsonpath="{.data.password}"`**: Extracts the `password` field.
     - **`base64 -d`**: Decodes the base64-encoded password.
     - **`&& echo`**: Prints a newline for better readability.

4. **Access the ArgoCD UI**:
    ArgoCD will be available at your domain name, but if you don't have it yet you can use port-forward.

   - Forward the ArgoCD server port to access the ArgoCD web UI on `<server-ip>:8080`:

     ```sh
     kubectl port-forward svc/argocd-server -n cicd 8080:443
     ```

   - Open your browser and navigate to `http://<server-ip>:8080`.

5. **Log in**:
   - Username: `admin`
   - Password: Use the password retrieved from the secret.

This process installs ArgoCD from a local Helm chart, sets it up in a Kubernetes namespace, and enables access to the ArgoCD UI. Once installed, you can start configuring your applications, linking them to Git repositories, and managing deployments using GitOps practices.

### Configure GitHub repos via SSH

To add a Git repository to ArgoCD using SSH, you'll need to generate a private SSH key pair, add the public key to your repository, and configure ArgoCD to use the private key for authentication. Below are detailed steps to achieve this.

### Step-by-Step Guide

#### 1. Create an SSH Key Pair

1. **Generate an SSH key pair** on your local machine. This key pair will be used for authentication with your Git repository:

   ```sh
   ssh-keygen -t ed25519 -C "argocd" -f infrastructure/keys
   ```

   - **`-t ed25519`**: Specifies the key type (Ed25519 is a secure modern key type).
   - **`-C "argocd-access"`**: A comment to identify the key.
   - **`-f ~/.ssh/argocd`**: The file name for the private key (`argocd`), and the public key will be saved as `argocd.pub`.

   You can choose a different key type, such as RSA (`-t rsa`), if needed.

2. You will now have two files:
   - **`argocd`**: The private key.
   - **`argocd.pub`**: The public key.

#### 2. Add the Public SSH Key to the Git Repository

- Go to your Git provider's web UI (e.g., GitHub, GitLab, Bitbucket).
- Navigate to the repository or user settings where you can add SSH keys.
- **Add the content of `argocd.pub`** to the SSH keys section in your Git provider. This allows the repository to accept connections from the corresponding private key.

##### For GitHub

- GitHub has specific instructions for adding SSH keys. You can follow the official documentation:
  [GitHub Documentation on Adding SSH Keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account)

#### 3. Add the Private Key to ArgoCD

1. **Create a Kubernetes secret** to store the SSH private key. ArgoCD will use this secret to authenticate with the Git repository. Replace `path/to/argocd` with the actual path to your private key:

   ```sh
   kubectl create secret generic git-repo-ssh-key \
     --from-file=sshPrivateKey=infrastructure/keys/argocd \
     -n cicd
   ```

   - **`<repo-secret-name>`**: A name for the secret, such as `git-repo-ssh-key`.
   - **`<argocd-namespace>`**: The namespace where ArgoCD is installed (e.g., `cicd`).

2. **Add the repository to ArgoCD** by using the following command:

   ```sh
    argocd repo add https://github.com/ArthurKretzer/streaming-pipeline.git \
      --ssh-private-key-path infrastructure/keys/argocd \
     --name datalake
   ```

   - **`git@bitbucket.org:<username>/<repository>.git`**: The SSH URL of your repository.
   - **`--ssh-private-key-path infrastructure/keys/argocd`**: The path to your private key.
   - **`--name <repository-name>`**: A name for the repository in ArgoCD.

Alternatively, you can add the repository via the **ArgoCD Web UI**:

- Go to the **Repositories** section.
- Click **Add Repository**.
- Select **SSH** as the type.
- Enter the SSH URL and upload the private key file.
- Finish setup clicking "CONNECT".

If everything was ok CONNECTION STATUS for the repo will be "Sucessful".

#### 4. Verify Access and Sync

1. After adding the repository, **verify** that ArgoCD has successfully connected by checking the repository's sync status.
2. You can test deploying an application from this repository to ensure everything is configured correctly.
