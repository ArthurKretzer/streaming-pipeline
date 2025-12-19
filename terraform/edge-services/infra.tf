terraform {
  required_providers {
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = ">= 1.14.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.0.0"
    }
  }
}

provider "kubernetes" {
  config_path    = "~/.kube/config"
  config_context = "streaming-cluster"
}

provider "helm" {
  kubernetes = {
    config_path    = "~/.kube/config"
    config_context = "streaming-cluster"
  }
}

resource "helm_release" "argocd" {
  name      = "argocd"
  namespace = "cicd"
  chart     = "../../kubernetes/edge/helm-charts/argo-cd"
  version   = "7.6.5"

  create_namespace = true

  values = [
    file("../../kubernetes/edge/helm-charts/argo-cd/values.yaml") # optional if you have custom config
  ]
}

# Wait for Argo CD CRDs to be available
resource "time_sleep" "wait_for_crds" {
  depends_on = [helm_release.argocd]

  create_duration = "30s"
}

# Create required namespaces
resource "kubernetes_namespace_v1" "deepstorage" {
  metadata {
    name = "deepstorage"
  }

  lifecycle {
    ignore_changes = [
      metadata[0].labels,
      metadata[0].annotations,
    ]
  }
}

resource "kubernetes_namespace_v1" "ingestion" {
  metadata {
    name = "ingestion"
  }

  lifecycle {
    ignore_changes = [
      metadata[0].labels,
      metadata[0].annotations,
    ]
  }
}

resource "kubernetes_namespace_v1" "monitoring" {
  metadata {
    name = "monitoring"
  }

  lifecycle {
    ignore_changes = [
      metadata[0].labels,
      metadata[0].annotations,
    ]
  }
}

resource "kubernetes_namespace_v1" "spark_operator" {
  metadata {
    name = "spark-operator"
  }

  lifecycle {
    ignore_changes = [
      metadata[0].labels,
      metadata[0].annotations,
    ]
  }
}

resource "kubernetes_namespace_v1" "spark_jobs" {
  metadata {
    name = "spark-jobs"
  }

  lifecycle {
    ignore_changes = [
      metadata[0].labels,
      metadata[0].annotations,
    ]
  }
}

# Load and apply all YAML files from deepstorage directory
data "kubectl_file_documents" "deepstorage" {
  content = join("\n---\n", [for f in fileset("../../kubernetes/edge/app-manifests/deepstorage", "*.yaml") : file("../../kubernetes/edge/app-manifests/deepstorage/${f}")])
}

resource "kubernetes_manifest" "deepstorage" {
  for_each   = data.kubectl_file_documents.deepstorage.manifests
  manifest   = yamldecode(each.value)
  depends_on = [kubernetes_namespace_v1.deepstorage, helm_release.argocd]
}

# Load and apply all YAML files from ingestion directory
data "kubectl_file_documents" "ingestion" {
  content = join("\n---\n", [for f in fileset("../../kubernetes/edge/app-manifests/ingestion", "*.yaml") : file("../../kubernetes/edge/app-manifests/ingestion/${f}")])
}

resource "kubernetes_manifest" "ingestion" {
  for_each   = data.kubectl_file_documents.ingestion.manifests
  manifest   = yamldecode(each.value)
  depends_on = [kubernetes_namespace_v1.ingestion, helm_release.argocd]
}

# Load and apply all YAML files from monitoring directory
data "kubectl_file_documents" "monitoring" {
  content = join("\n---\n", [for f in fileset("../../kubernetes/edge/app-manifests/monitoring", "*.yaml") : file("../../kubernetes/edge/app-manifests/monitoring/${f}")])
}

resource "kubernetes_manifest" "monitoring" {
  for_each   = data.kubectl_file_documents.monitoring.manifests
  manifest   = yamldecode(each.value)
  depends_on = [kubernetes_namespace_v1.monitoring, helm_release.argocd]
}

# Load and apply all YAML files from spark-operator directory
data "kubectl_file_documents" "spark_operator" {
  content = join("\n---\n", [for f in fileset("../../kubernetes/edge/app-manifests/spark-operator", "*.yaml") : file("../../kubernetes/edge/app-manifests/spark-operator/${f}")])
}

resource "kubernetes_manifest" "spark_operator" {
  for_each   = data.kubectl_file_documents.spark_operator.manifests
  manifest   = yamldecode(each.value)
  depends_on = [kubernetes_namespace_v1.spark_operator, kubernetes_namespace_v1.spark_jobs, helm_release.argocd]
}

# Load and apply all YAML files from deploy directory
data "kubectl_file_documents" "deploy" {
  content = join("\n---\n", [for f in fileset("../../kubernetes/edge/deploy", "*.yaml") : file("../../kubernetes/edge/deploy/${f}")])
}

resource "kubernetes_manifest" "deploy" {
  for_each   = data.kubectl_file_documents.deploy.manifests
  manifest   = yamldecode(each.value)
  depends_on = [kubernetes_namespace_v1.spark_operator, kubernetes_namespace_v1.spark_jobs, helm_release.argocd]
}
