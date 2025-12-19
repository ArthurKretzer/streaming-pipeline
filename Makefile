start: start-edge start-cloud

clean: clean-edge clean-cloud

start-edge: kube-context-edge provision-edge-services services-edge-ips

clean-edge: kube-context-edge destroy-edge-services

start-cloud: kube-context-cloud provision-cloud-infra provision-cloud-services services-external-ips

clean-cloud: kube-context-cloud destroy-cloud-services destroy-cloud-infra

# Cloud Provisioning
provision-cloud-infra:
	cd terraform/cloud-deploy && terraform init
	cd terraform/cloud-deploy && terraform apply --var-file=env.tfvars

provision-cloud-services:
	cd terraform/cloud-services && terraform init
	cd terraform/cloud-services && terraform apply -target=kubernetes_namespace_v1.monitoring -target=helm_release.argocd
	@echo "Waiting 30s for resources to stabilize..."
	sleep 30
	cd terraform/cloud-services && terraform apply

destroy-cloud-services: kube-context-cloud
	cd terraform/cloud-services && terraform destroy
	helm uninstall argocd -n cicd
	kubectl delete ns monitoring

destroy-cloud-infra:
	cd terraform/cloud-deploy && terraform destroy

# Edge Provisioning
provision-edge-infra:
	cd terraform/edge-deploy && terraform init
	cd terraform/edge-deploy && terraform apply --var-file=env.tfvars

provision-edge-services:
	cd terraform/edge-services && terraform init
	cd terraform/edge-services && terraform apply -target=kubernetes_namespace_v1.monitoring -target=helm_release.argocd
	@echo "Waiting 30s for resources to stabilize..."
	sleep 30
	cd terraform/edge-services && terraform apply

destroy-edge-services: kube-context-edge
	cd terraform/edge-services && terraform destroy
	helm uninstall argocd -n cicd
	kubectl delete ns monitoring

destroy-edge-infra:
	cd terraform/edge-deploy && terraform destroy

# Utilities
kube-context-cloud:
	kubectx do-nyc1-k8s-cluster

kube-context-edge:
	kubectx streaming-cluster
	
services-external-ips: kube-context-cloud
	@echo "\033[0;34mFetching ArgoCD password..."
	@kubectl get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' -n cicd | base64 -d && echo
	@echo "\033[0m\033[0;32mListing all services with Nodeports:"
	@kubectl get svc --all-namespaces -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,TYPE:.spec.type,PORT(S):.spec.ports[*].nodePort" | \
		grep NodePort | column -t
	@echo "\033[0m\033[0;33mListing all droplets public IPs:"
	@doctl compute droplet list --format Name,PublicIPv4

services-edge-ips: kube-context-edge
	@echo "\033[0;34mFetching ArgoCD password..."
	@kubectl get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' -n cicd | base64 -d && echo
	@echo "\033[0m\033[0;32mListing all services with Nodeports:"
	@kubectl get svc --all-namespaces -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,TYPE:.spec.type,PORT(S):.spec.ports[*].nodePort" | \
		grep NodePort | column -t
	@echo "\033[0m\033[0;33mListing all nodes/IPs:"
	@kubectl get nodes -o wide

build-spark:
	docker build -t arthurkretzer/spark:3.5.4 -f ./docker/spark.Dockerfile .
	docker push arthurkretzer/spark:3.5.4

build-producer:
	docker build -t arthurkretzer/streaming-producer:3.5.4 -f ./docker/streaming-producer.Dockerfile ./src
	docker push arthurkretzer/streaming-producer:3.5.4

setup-control-power-cloud:
	-docker rm -f producer-control-power-cloud
	docker run --name producer-control-power-cloud --env-file=./src/cloud.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py setup control_power

setup-control-power-edge:
	-docker rm -f producer-control-power-edge
	docker run --name producer-control-power-edge --env-file=./src/edge.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py setup control_power

produce-control-power-cloud:
	-docker rm -f producer-control-power-cloud
	docker run -d --name producer-control-power-cloud --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 1

stop-produce-control-power-cloud:
	-docker stop producer-control-power-cloud
	-docker rm -f producer-control-power-cloud

produce-control-power-edge: 
	docker rm -f producer-control-power-edge
	docker run -d --name producer-control-power-edge --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 1

stop-produce-control-power-edge:
	-docker stop producer-control-power-edge
	docker rm -f producer-control-power-edge

produce-10-robots-cloud:
	-docker rm -f producer-control-power-cloud
	docker run -d --name producer-control-power-cloud --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 10

produce-50-robots-cloud:
	-docker rm -f producer-control-power-cloud
	docker run -d --name producer-control-power-cloud --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 50

produce-100-robots-cloud:
	-docker rm -f producer-control-power-cloud
	docker run -d --name producer-control-power-cloud --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 100

produce-10-robots-edge:
	docker rm -f producer-control-power-edge
	docker run -d --name producer-control-power-edge --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 10

produce-50-robots-edge:
	docker rm -f producer-control-power-edge
	docker run -d --name producer-control-power-edge --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 50

produce-100-robots-edge:
	docker rm -f producer-control-power-edge
	docker run -d --name producer-control-power-edge --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power --num-robots 100

produce-10-robots: produce-10-robots-cloud produce-10-robots-edge
produce-50-robots: produce-50-robots-cloud produce-50-robots-edge
produce-100-robots: produce-100-robots-cloud produce-100-robots-edge

start-produce: build-producer produce-control-power-cloud produce-control-power-edge

stop-produce: stop-produce-control-power-cloud stop-produce-control-power-edge

experiment-cloud: kube-context-cloud 
	@echo "Starting consumer..."
	$(MAKE) consume-control-power-cloud
	@echo "Waiting 5 minutes for consumer start..."
	sleep 300
	@echo "Starting experiment with 1 robot..."
	$(MAKE) produce-control-power-cloud
	@echo "Running for 30 minutes..."
	sleep 1800
	$(MAKE)stop-produce-control-power-cloud
	@echo "Starting experiment with 10 robots..."
	$(MAKE) produce-10-robots-cloud
	@echo "Running for 30 minutes..."
	sleep 1800
	$(MAKE) stop-produce-control-power-cloud
	@echo "Starting experiment with 50 robots..."
	$(MAKE) produce-50-robots-cloud
	@echo "Running for 30 minutes..."
	sleep 1800
	$(MAKE) stop-produce-control-power-cloud
	@echo "Starting experiment with 100 robots..."
	$(MAKE) produce-100-robots-cloud
	@echo "Running for 30 minutes..."
	sleep 1800
	$(MAKE) stop-produce-control-power-cloud
	@echo "Experiment finished."

experiment-edge: kube-context-edge
	@echo "Starting consumer..."
	$(MAKE) consume-control-power-edge
	@echo "Waiting 5 minutes for consumer start..."
	sleep 300
	@echo "Starting experiment with 1 robot..."
	$(MAKE) produce-control-power-edge
	@echo "Running for 30 minutes..."
	sleep 1800
	$(MAKE)stop-produce-control-power-edge
	@echo "Starting experiment with 10 robots..."
	$(MAKE) produce-10-robots-edge
	@echo "Running for 30 minutes..."
	sleep 1800
	$(MAKE) stop-produce-control-power-edge
	@echo "Starting experiment with 50 robots..."
	$(MAKE) produce-50-robots-edge
	@echo "Running for 30 minutes..."
	sleep 1800
	$(MAKE) stop-produce-control-power-edge
	@echo "Starting experiment with 100 robots..."
	$(MAKE) produce-100-robots-edge
	@echo "Running for 30 minutes..."
	sleep 1800
	$(MAKE) stop-produce-control-power-edge
	@echo "Experiment finished."

build-consumer:
	docker build -t arthurkretzer/streaming-consumer:3.5.4 -f ./docker/streaming-consumer.Dockerfile ./src
	docker push arthurkretzer/streaming-consumer:3.5.4

consume-control-power-cloud: kube-context-cloud
	kubectl apply -f ./kubernetes/cloud/yamls/consumer.yaml

stop-consume-control-power-cloud: kube-context-cloud
	kubectl delete -f ./kubernetes/cloud/yamls/consumer.yaml

consume-control-power-edge: kube-context-edge
	kubectl apply -f ./kubernetes/edge/yamls/consumer.yaml

stop-consume-control-power-edge: kube-context-edge
	kubectl delete -f ./kubernetes/edge/yamls/consumer.yaml

start-consume: consume-control-power-edge consume-control-power-cloud 

stop-consume: stop-consume-control-power-cloud stop-consume-control-power-edge

# Data Collection
collect-metrics:
	uv run src/prometheus_metrics.py --edge-ip=$(EDGE_IP) --cloud-ip=$(CLOUD_IP) --experiment-name=$(EXP_NAME)