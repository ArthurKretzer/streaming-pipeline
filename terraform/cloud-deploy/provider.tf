terraform {
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
  }
}

variable "do_token" {
  description = "DigitalOcean API Token"
  type        = string
  sensitive   = true
}

provider "digitalocean" {
  token = var.do_token
}

variable "region" {
  description = "Region to deploy the Kubernetes cluster"
  type        = string
  default     = "nyc1"
}

variable "node_size" {
  description = "Droplet size for Kubernetes nodes"
  type        = string
  default     = "s-4vcpu-16gb-amd"
}

resource "digitalocean_kubernetes_cluster" "k8s_cluster" {
  name    = "k8s-cluster"
  region  = var.region
  version = "1.32.10-do.2"

  node_pool {
    name       = "worker-pool"
    size       = var.node_size
    node_count = 4
    auto_scale = false
  }
}

output "cluster_id" {
  description = "Kubernetes cluster ID"
  value       = digitalocean_kubernetes_cluster.k8s_cluster.id
}

resource "local_file" "kubeconfig" {
  content  = digitalocean_kubernetes_cluster.k8s_cluster.kube_config[0].raw_config
  filename = "${path.module}/kubeconfig.yaml"
}

resource "null_resource" "update_kubeconfig" {
  provisioner "local-exec" {
    command = "mkdir -p ~/.kube && cp ${local_file.kubeconfig.filename} ~/.kube/config"
  }
  depends_on = [local_file.kubeconfig]
}

output "cluster_endpoint" {
  description = "Kubernetes cluster endpoint"
  value       = digitalocean_kubernetes_cluster.k8s_cluster.endpoint
}
