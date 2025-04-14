start: terraform-init services-external-ips

clean:
	cd terraform && terraform destroy

terraform-init:
	cd terraform && terraform init
	cd terraform && terraform plan
	cd terraform && terraform apply

services-external-ips:
	@echo "ArgoCD Password"
	@kubectl get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' -n cicd | base64 -d && echo
	@echo "Listing all services with External IPs:"
	@kubectl get svc --all-namespaces -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,TYPE:.spec.type,EXTERNAL-IP:.status.loadBalancer.ingress[0].ip,PORT(S):.spec.ports[*].port" | \
		grep -v '<none>' | column -t