start: start-edge start-cloud

clean: clean-edge clean-cloud

start-edge: kube-context-edge provision-edge-services

clean-edge: kube-context-edge destroy-edge-services

start-cloud: kube-context-cloud provision-cloud-infra provision-cloud-services services-external-ips

clean-cloud: kube-context-cloud destroy-cloud-services destroy-cloud-infra

# Cloud Provisioning
provision-cloud-infra:
	cd terraform/cloud-deploy && terraform init
	cd terraform/cloud-deploy && terraform apply

provision-cloud-services:
	cd terraform/cloud-services && terraform init
	cd terraform/cloud-services && terraform apply -target=kubernetes_namespace.monitoring -target=helm_release.argocd
	cd terraform/cloud-services && terraform apply

destroy-cloud-services:
	cd terraform/cloud-services && terraform destroy

destroy-cloud-infra:
	cd terraform/cloud-deploy && terraform destroy

# Edge Provisioning
provision-edge-infra:
	cd terraform/edge-deploy && terraform init
	cd terraform/edge-deploy && terraform apply

provision-edge-services:
	cd terraform/edge-services && terraform init
	cd terraform/edge-services && terraform apply -target=kubernetes_namespace.monitoring -target=helm_release.argocd
	cd terraform/edge-services && terraform apply

destroy-edge-services:
	cd terraform/edge-services && terraform destroy

destroy-edge-infra:
	cd terraform/edge-deploy && terraform destroy

# Utilities
kube-context-cloud:
	kubectx do-nyc1-k8s-cluster

kube-context-edge:
	kubectx streaming-cluster
	
services-external-ips:
	@echo "\033[0;34mFetching ArgoCD password..."
	@kubectl get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' -n cicd | base64 -d && echo
	@echo "\033[0m\033[0;32mListing all services with Nodeports:"
	@kubectl get svc --all-namespaces -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,TYPE:.spec.type,PORT(S):.spec.ports[*].nodePort" | \
		grep NodePort | column -t
	@echo "\033[0m\033[0;33mListing all droplets public IPs:"
	@doctl compute droplet list --format Name,PublicIPv4

build-spark:
	docker build -t arthurkretzer/spark:3.5.4 -f ./docker/spark.Dockerfile
	docker push arthurkretzer/spark:3.5.4

build-producer:
	docker build -t arthurkretzer/streaming-producer:3.5.4 -f ./docker/streaming-producer.Dockerfile ./src
	docker push arthurkretzer/streaming-producer:3.5.4

produce-control-power-cloud:
	docker rm -f producer-control-power-cloud
	docker run -d --name producer-control-power-cloud --env-file=./src/cloud.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 1

stop-produce-control-power-cloud:
	docker rm -f producer-control-power-cloud

produce-control-power-edge: 
	docker rm -f producer-control-power-edge
	docker run -d --name producer-control-power-edge --env-file=./src/edge.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 1

stop-produce-control-power-edge:
	docker rm -f producer-control-power-edge

produce-10-robots-cloud:
	docker rm -f producer-control-power-cloud
	docker run -d --name producer-control-power-cloud --env-file=./src/cloud.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 10

produce-50-robots-cloud:
	docker rm -f producer-control-power-cloud
	docker run -d --name producer-control-power-cloud --env-file=./src/cloud.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 50

produce-100-robots-cloud:
	docker rm -f producer-control-power-cloud
	docker run -d --name producer-control-power-cloud --env-file=./src/cloud.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 100

produce-10-robots-edge:
	docker rm -f producer-control-power-edge
	docker run -d --name producer-control-power-edge --env-file=./src/edge.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 10

produce-50-robots-edge:
	docker rm -f producer-control-power-edge
	docker run -d --name producer-control-power-edge --env-file=./src/edge.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 50

produce-100-robots-edge:
	docker rm -f producer-control-power-edge
	docker run -d --name producer-control-power-edge --env-file=./src/edge.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 100

produce-10-robots: produce-10-robots-cloud produce-10-robots-edge
produce-50-robots: produce-50-robots-cloud produce-50-robots-edge
produce-100-robots: produce-100-robots-cloud produce-100-robots-edge

start-produce: build-producer produce-control-power-cloud produce-control-power-edge

stop-produce: stop-produce-control-power-cloud stop-produce-control-power-edge

build-consumer:
	docker build -t arthurkretzer/streaming-consumer:3.5.4 -f ./docker/streaming-consumer.Dockerfile ./src
	docker push arthurkretzer/streaming-consumer:3.5.4

consume-control-power-cloud: kube-context-cloud
	kubectl apply -f ./kubernetes/yamls/consumer.yaml

stop-consume-control-power-cloud: kube-context-cloud
	kubectl delete -f ./kubernetes/yamls/consumer.yaml

consume-control-power-edge: kube-context-edge
	kubectl apply -f ./kubernetes/yamls/consumer-edge.yaml

stop-consume-control-power-edge: kube-context-edge
	kubectl delete -f ./kubernetes/yamls/consumer-edge.yaml

start-consume: consume-control-power-edge consume-control-power-cloud 

stop-consume: stop-consume-control-power-cloud stop-consume-control-power-edge

# Data Collection
collect-metrics:
	python3 data/prometheus_metrics.py --edge-ip=$(EDGE_IP) --cloud-ip=$(CLOUD_IP) --experiment-name=$(EXP_NAME)