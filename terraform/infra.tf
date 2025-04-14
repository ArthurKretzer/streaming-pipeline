provider "kubernetes" {
  config_path = "~/.kube/config" # or a path to a kubeconfig file
}

provider "helm" {
  kubernetes {
    config_path = "~/.kube/config" # or an absolute path like "/home/youruser/.kube/config"
  }
}

resource "helm_release" "argocd" {
  name      = "argocd"
  namespace = "cicd"
  chart     = "../kubernetes/helm-charts/argo-cd"
  version   = "5.51.6" # check for the latest stable

  create_namespace = true

  values = [
    file("../kubernetes/helm-charts/argo-cd/values-cloud.yaml") # optional if you have custom config
  ]
}

resource "null_resource" "argocd-password" {
  provisioner "local-exec" {
    command = "kubectl get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' -n cicd | base64 -d && echo"
  }

  depends_on = [helm_release.argocd]
}

resource "null_resource" "minio" {
  provisioner "local-exec" {
    command = "kubectl create namespace deepstorage --dry-run=client -o yaml | kubectl apply -f - && kubectl apply -f ../kubernetes/app-manifests/deepstorage/"
  }

  depends_on = [helm_release.argocd]
}

resource "null_resource" "ingestion" {
  provisioner "local-exec" {
    command = "kubectl create namespace ingestion --dry-run=client -o yaml | kubectl apply -f - && kubectl apply -f ../kubernetes/app-manifests/ingestion/"
  }

  depends_on = [helm_release.argocd]
}

resource "null_resource" "monitoring" {
  provisioner "local-exec" {
    command = "kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f - && kubectl apply -f ../kubernetes/app-manifests/monitoring/"
  }

  depends_on = [helm_release.argocd]
}

resource "null_resource" "spark-operator" {
  provisioner "local-exec" {
    command = "kubectl create namespace spark-operator --dry-run=client -o yaml | kubectl apply -f - && kubectl create namespace spark-jobs --dry-run=client -o yaml | kubectl apply -f - && kubectl apply -f ../kubernetes/app-manifests/spark-operator/"
  }

  depends_on = [helm_release.argocd]
}

resource "null_resource" "deploy" {
  provisioner "local-exec" {
    command = "kubectl create namespace spark-operator --dry-run=client -o yaml | kubectl apply -f - && kubectl create namespace spark-jobs --dry-run=client -o yaml | kubectl apply -f - && kubectl apply -f ../kubernetes/deploy/"
  }

  depends_on = [helm_release.argocd]
}
