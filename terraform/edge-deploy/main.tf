terraform {
  required_providers {
    proxmox = {
      source  = "Telmate/proxmox"
      version = "3.0.2-rc07"
    }
  }
}

variable "proxmox_api_token_id" {
  type = string
}

variable "proxmox_api_token_secret" {
  type      = string
  sensitive = true
}

provider "proxmox" {
  pm_api_url          = "http://172.16.208.240:8006/api2/json"
  pm_api_token_id     = var.proxmox_api_token_id
  pm_api_token_secret = var.proxmox_api_token_secret
  pm_tls_insecure     = true # Disables SSL verification
}

# User must have sudo permissions and NOPASSWD enabled.
variable "ssh_user" {
  type = string
}
variable "ssh_port" {
  type = string
}

variable "cipassword" {
  type      = string
  sensitive = true
}

variable "new_cluster_name" {
  type    = string
  default = "new-cluster-name"
}

locals {
  starting_vmid = 9100
  workers = {
    "01" = { ip = "172.16.208.242", mac = "6C:32:4B:0B:B6:9B" }
    "02" = { ip = "172.16.208.243", mac = "A2:43:DF:FC:C0:46" }
    "03" = { ip = "172.16.208.244", mac = "F8:47:C7:EE:72:20" }
    "04" = { ip = "172.16.208.245", mac = "78:97:8F:39:2C:EF" }
  }
}

# If new master clones are to be created for redundancy, AD on template should be reconfigured.
resource "proxmox_vm_qemu" "kubernetes-master" {
  name        = "server-k8s-m01"
  target_node = "proxmox-cdm"
  boot        = "order=scsi0;ide2"
  scsihw      = "virtio-scsi-pci"
  clone       = "cloud-init-ubuntu-20.04-template"
  cores       = 3
  memory      = 8192
  agent       = 1 #qemu
  tags        = "k8s,project"
  vmid        = local.starting_vmid + 1

  #### Cloud init configs
  os_type   = "cloud-init"
  ciupgrade = "true"
  # SSH configs
  ssh_forward_ip = "172.16.208.241"
  # Your Terraform host public key(s)
  sshkeys = <<EOF
  ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj+NdBrCFBMv33OHEwLghK9dxFjMjgprT2M9ATMOL6bTX/lVNly8oFnRS3Hf8vj7UadXMKiBOkGbw4Q3wOBzlZUOS7XuLb3tEg4nPwl5/HWiRZXJrLUQMr+lITlmddK9/26363dNY+mD23dQ6jS2XUmzsUQX6KQH7+MsQCoz9NR0owUvppCxzTMefGT0RcBXyNKaTCTTh1KVOrOD0tx0cMVHSc2GTMdtUC8N4lOGLKC054PmqvvFz86M9paMQvNuORMDR90PSe+0aH42go+OtK/GuLZx+BgWSs2ZuBMQy1OAc12ozLEg3k/pgvV5wHgjgcUP29HAddHVhLyklw2ZCss+jCyBUAcqnfPz5edwlsmwoNB1t0sV205UIRZRrdjT+AjWBsc8nTpVrOPb8sCeKAH3E8tbbWI0zNJ6SAYG7Q6iAl6dTe+fux/5LT3R99Isv9bxlVtPsZ5WwqlfoeoyvgEWktUyGiGFVmdHBWvUZpF27I/l9o3JGpKFqyOzpfUp0= arthur@CPC-12806
  EOF
  # Ip configs
  ipconfig0  = "ip=172.16.208.241/24,gw=172.16.208.1"
  nameserver = "8.8.8.8,8.8.4.4"
  # User configs
  ciuser     = var.ssh_user
  cipassword = var.cipassword

  disks {
    scsi {
      scsi0 {
        disk {
          size    = "300G"
          storage = "local-lvm"
          # emulatessd = true # Optional: Good for performance if underlying storage is SSD
          # discard    = true # Optional: Good for freeing up space (TRIM)
        }
      }
    }
    # Keep the cloud-init drive as is
    ide {
      ide2 {
        cloudinit {
          storage = "local-lvm"
        }
      }
    }
  }
  # Network configuration
  network {
    id      = 0
    model   = "virtio"
    bridge  = "vmbr1" # Replace with the actual bridge name
    macaddr = "BC:24:11:CF:6F:92"
    tag     = 28
  }

  provisioner "remote-exec" {
    inline = [
      # --- System Prep ---
      "sudo ufw disable",
      "sudo hostnamectl set-hostname ${self.name}",
      "echo '127.0.1.1 ${self.name}' | sudo tee -a /etc/hosts",
      "sudo swapoff -a",

      # --- K3s Installation (Embedded Etcd) ---
      # --cluster-init: Initializes the embedded etcd so you can add more masters later
      # --tls-san: (Optional but recommended) Adds the IP to the cert so you can kubectl from outside
      "curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=\"v1.32.10+k3s1\" INSTALL_K3S_EXEC=\"server --cluster-init --tls-san ${self.ssh_forward_ip}\" sh -",

      # --- Wait for K3s Startup ---
      # Critical: Give K3s time to generate the config files before we try to copy them
      "echo 'Waiting for K3s to initialize...'",
      "sleep 10",

      # --- Node Taint ---
      "sudo kubectl taint nodes $(hostname) node-role.kubernetes.io/master=:NoSchedule",

      # --- Token & Config Copy ---
      "sudo cp /var/lib/rancher/k3s/server/node-token /home/${var.ssh_user}/node-token",
      "sudo chown ${var.ssh_user}:${var.ssh_user} /home/${var.ssh_user}/node-token",

      "sudo cp /etc/rancher/k3s/k3s.yaml /home/${var.ssh_user}/k3s.yaml",
      "sudo chown ${var.ssh_user}:${var.ssh_user} /home/${var.ssh_user}/k3s.yaml"
    ]
    connection {
      type        = "ssh"
      user        = var.ssh_user
      host        = self.ssh_forward_ip
      private_key = file("~/.ssh/id_rsa") # This key should be previously added to the templates
      port        = 22
    }
  }
}

resource "null_resource" "get_node_token" {
  provisioner "local-exec" {
    command = "scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ~/.ssh/id_rsa -P ${var.ssh_port} ${var.ssh_user}@${proxmox_vm_qemu.kubernetes-master.ssh_forward_ip}:/home/${var.ssh_user}/node-token ./node-token"
  }
  depends_on = [proxmox_vm_qemu.kubernetes-master]
}

resource "null_resource" "get_kubeconfig" {
  provisioner "local-exec" {
    command = <<-EOT
      scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ~/.ssh/id_rsa -P ${var.ssh_port} ${var.ssh_user}@${proxmox_vm_qemu.kubernetes-master.ssh_forward_ip}:/home//${var.ssh_user}/k3s.yaml ./k3s.yaml && \
      sed -i 's/127.0.0.1/${proxmox_vm_qemu.kubernetes-master.ssh_forward_ip}/' ./k3s.yaml && \
      sed -i 's/name: default/name: ${var.new_cluster_name}/' ./k3s.yaml && \
      sed -i 's/cluster: default/cluster: ${var.new_cluster_name}/' ./k3s.yaml && \
      sed -i 's/user: default/user: ${var.new_cluster_name}/' ./k3s.yaml && \
      sed -i 's/current-context: default/current-context: ${var.new_cluster_name}/' ./k3s.yaml && \
      export KUBECONFIG=~/.kube/config:./k3s.yaml && \
      kubectl config view --merge --flatten > ~/.kube/config
    EOT
  }

  depends_on = [proxmox_vm_qemu.kubernetes-master]
}

resource "proxmox_vm_qemu" "kubernetes-workers" {
  for_each = local.workers

  name        = "server-k8s-w${each.key}"
  tags        = "k8s,project"
  target_node = "proxmox-cdm"
  clone       = "cloud-init-ubuntu-20.04-template"

  # Boot
  boot   = "order=scsi0;ide2"
  scsihw = "virtio-scsi-pci"

  vmid = local.starting_vmid + 1 + tonumber(each.key)
  # Resources
  cores         = 4
  memory        = 8192
  agent         = 1 #qemu
  agent_timeout = 240

  #### Cloud init configs
  os_type   = "cloud-init"
  ciupgrade = "true"
  # SSH configs
  ssh_forward_ip = each.value.ip
  # Your Terraform host public key(s)
  sshkeys = <<EOF
  ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj+NdBrCFBMv33OHEwLghK9dxFjMjgprT2M9ATMOL6bTX/lVNly8oFnRS3Hf8vj7UadXMKiBOkGbw4Q3wOBzlZUOS7XuLb3tEg4nPwl5/HWiRZXJrLUQMr+lITlmddK9/26363dNY+mD23dQ6jS2XUmzsUQX6KQH7+MsQCoz9NR0owUvppCxzTMefGT0RcBXyNKaTCTTh1KVOrOD0tx0cMVHSc2GTMdtUC8N4lOGLKC054PmqvvFz86M9paMQvNuORMDR90PSe+0aH42go+OtK/GuLZx+BgWSs2ZuBMQy1OAc12ozLEg3k/pgvV5wHgjgcUP29HAddHVhLyklw2ZCss+jCyBUAcqnfPz5edwlsmwoNB1t0sV205UIRZRrdjT+AjWBsc8nTpVrOPb8sCeKAH3E8tbbWI0zNJ6SAYG7Q6iAl6dTe+fux/5LT3R99Isv9bxlVtPsZ5WwqlfoeoyvgEWktUyGiGFVmdHBWvUZpF27I/l9o3JGpKFqyOzpfUp0= arthur@CPC-12806
  EOF
  # Ip configs
  ipconfig0  = "ip=${each.value.ip}/24,gw=172.16.208.1" # Fixed IP
  nameserver = "8.8.8.8,8.8.4.4"
  # User configs
  ciuser     = var.ssh_user
  cipassword = var.cipassword

  disks {
    scsi {
      scsi0 {
        disk {
          size    = "300G"
          storage = "local-lvm"
          # emulatessd = true # Optional: Good for performance if underlying storage is SSD
          # discard    = true # Optional: Good for freeing up space (TRIM)
        }
      }
    }
    # Keep the cloud-init drive as is
    ide {
      ide2 {
        cloudinit {
          storage = "local-lvm"
        }
      }
    }
  }

  # Network configuration
  network {
    id      = 0
    model   = "virtio"
    bridge  = "vmbr1" # Replace with the actual bridge name
    macaddr = each.value.mac
    tag     = 28
  }
  provisioner "file" {
    source      = "~/.ssh/id_rsa"
    destination = "/home/${var.ssh_user}/.ssh/id_rsa"

    connection {
      type        = "ssh"
      user        = var.ssh_user
      host        = self.ssh_forward_ip
      private_key = file("~/.ssh/id_rsa") # Use your local Terraform host key to connect to the VM
      port        = 22
    }
  }

  provisioner "file" {
    source      = "~/.ssh/id_rsa.pub"
    destination = "/home/${var.ssh_user}/.ssh/id_rsa.pub"

    connection {
      type        = "ssh"
      user        = var.ssh_user
      host        = self.ssh_forward_ip
      private_key = file("~/.ssh/id_rsa") # Use your local Terraform host key to connect to the VM
      port        = 22
    }
  }

  provisioner "file" {
    source      = "./node-token"
    destination = "/home/${var.ssh_user}/node-token"

    connection {
      type        = "ssh"
      user        = var.ssh_user
      host        = self.ssh_forward_ip
      private_key = file("~/.ssh/id_rsa") # Use your local Terraform host key to connect to the VM
      port        = 22
    }
  }

  provisioner "remote-exec" {
    inline = [
      "sudo apt update && sudo apt install -y nfs-common", # For longhorn ReadWriteMany
      "sudo ufw disable",                                  # Necessary since kubernetes will manage ip tables
      "sudo swapoff -a",                                   # Disable swap. K8s requirement.
      "chmod 600 /home/${var.ssh_user}/.ssh/id_rsa",
      "export K3S_TOKEN=$(cat /home/${var.ssh_user}/node-token)",
      "export K3S_URL=https://${proxmox_vm_qemu.kubernetes-master.ssh_forward_ip}:6443",
      "curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=\"v1.32.10+k3s1\" K3S_URL=$K3S_URL K3S_TOKEN=$K3S_TOKEN sh -", # Install k3s and join the cluster
    ]
    connection {
      type        = "ssh"
      user        = var.ssh_user
      host        = self.ssh_forward_ip
      private_key = file("~/.ssh/id_rsa") # This key should be previously added to the templates
      port        = 22
    }
  }

  depends_on = [null_resource.get_node_token, null_resource.get_kubeconfig]
}

resource "null_resource" "remote_exec_k8s_join" {
  for_each = local.workers
  provisioner "remote-exec" {

    inline = [
      "sudo apt update && sudo apt install -y nfs-common", # For longhorn ReadWriteMany
      "sudo ufw disable",
      "sudo swapoff -a", # Disable swap. K8s requirement.
      "chmod 600 /home/${var.ssh_user}/.ssh/id_rsa",
      "export K3S_TOKEN=$(cat /home/${var.ssh_user}/node-token)",
      "export K3S_URL=https://${proxmox_vm_qemu.kubernetes-master.ssh_forward_ip}:6443",
      "curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=\"v1.32.10+k3s1\" K3S_URL=$K3S_URL K3S_TOKEN=$K3S_TOKEN sh -",
    ]
    connection {
      type        = "ssh"
      user        = var.ssh_user
      host        = each.value.ip
      private_key = file("~/.ssh/id_rsa")
      port        = 22
    }
  }

  depends_on = [proxmox_vm_qemu.kubernetes-workers]
}
