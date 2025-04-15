start: terraform-init services-external-ips

clean:
	cd terraform && terraform destroy

terraform-init:
	cd terraform && terraform init
	cd terraform && terraform plan -target=helm_release.argocd
	cd terraform && terraform apply -target=helm_release.argocd
	cd terraform && terraform plan
	cd terraform && terraform apply
	
services-external-ips:
	@echo "\033[0;34mFetching ArgoCD password..."
	@kubectl get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' -n cicd | base64 -d && echo
	@echo "\033[0m\033[0;32mListing all services with Nodeports:"
	@kubectl get svc --all-namespaces -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,TYPE:.spec.type,PORT(S):.spec.ports[*].nodePort" | \
		grep NodePort | column -t
	@echo "\033[0m\033[0;33mListing all droplets public IPs:"
	@doctl compute droplet list --format Name,PublicIPv4

build-consumer:
	docker build -t arthurkretzer/streaming-consumer:3.5.4 -f ./docker/streaming-consumer.Dockerfile ./src
	docker push arthurkretzer/streaming-consumer:3.5.4

build-producer:
	docker build -t arthurkretzer/streaming-producer:3.5.4 -f ./docker/streaming-producer.Dockerfile ./src
	docker push arthurkretzer/streaming-producer:3.5.4

produce-control-power:
	docker rm -f producer-control-power
	docker run -d --name producer-control-power --env-file=./src/.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power avro