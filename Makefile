start: start-edge start-cloud

CLOUD_CONTEXT := do-nyc1-k8s-cluster
EDGE_CONTEXT := streaming-cluster

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

destroy-cloud-infra:
	cd terraform/cloud-deploy && terraform destroy --var-file=env.tfvars

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
	cd terraform/edge-services && terraform destroy --var-file=secret.tfvars
	helm uninstall argocd -n cicd
	kubectl delete ns monitoring

destroy-edge-infra:
	cd terraform/edge-deploy && terraform destroy --var-file=secret.tfvars

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

build-producer-rust:
	docker build -t arthurkretzer/streaming-producer-rust:latest -f ./docker/rust-producer.Dockerfile .
	# docker push arthurkretzer/streaming-producer-rust:latest

produce-rust-cloud:
	-docker rm -f producer-rust-cloud
	docker run -d --name producer-rust-cloud --net=host --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 1 --dataset-path /app/data/robot_data.parquet

produce-100-rust-cloud:
	-docker rm -f producer-rust-cloud
	docker run -d --name producer-rust-cloud --net=host --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 100 --dataset-path /app/data/robot_data.parquet

stop-produce-rust-cloud:
	-docker stop producer-rust-cloud
	-docker rm -f producer-rust-cloud

produce-10-rust-cloud:
	-docker rm -f producer-rust-cloud
	docker run -d --name producer-rust-cloud --net=host --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 10 --dataset-path /app/data/robot_data.parquet

produce-50-rust-cloud:
	-docker rm -f producer-rust-cloud
	docker run -d --name producer-rust-cloud --net=host --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 50 --dataset-path /app/data/robot_data.parquet

produce-100-20hz-rust-cloud:
	-docker rm -f producer-rust-cloud
	docker run -d --name producer-rust-cloud --net=host --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 100 --frequency 20 --dataset-path /app/data/robot_data.parquet

produce-100-50hz-rust-cloud:
	-docker rm -f producer-rust-cloud
	docker run -d --name producer-rust-cloud --net=host --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 100 --frequency 50 --dataset-path /app/data/robot_data.parquet

produce-100-100hz-rust-cloud:
	-docker rm -f producer-rust-cloud
	docker run -d --name producer-rust-cloud --net=host --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 100 --frequency 100 --dataset-path /app/data/robot_data.parquet

produce-rust-edge:
	-docker rm -f producer-rust-edge
	docker run -d --name producer-rust-edge --net=host --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 1 --dataset-path /app/data/robot_data.parquet

produce-10-rust-edge:
	-docker rm -f producer-rust-edge
	docker run -d --name producer-rust-edge --net=host --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 10 --dataset-path /app/data/robot_data.parquet

produce-50-rust-edge:
	-docker rm -f producer-rust-edge
	docker run -d --name producer-rust-edge --net=host --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 50 --dataset-path /app/data/robot_data.parquet

produce-100-rust-edge:
	-docker rm -f producer-rust-edge
	docker run -d --name producer-rust-edge --net=host --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 100 --dataset-path /app/data/robot_data.parquet

produce-100-20hz-rust-edge:
	-docker rm -f producer-rust-edge
	docker run -d --name producer-rust-edge --net=host --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 100 --frequency 20 --dataset-path /app/data/robot_data.parquet

produce-100-50hz-rust-edge:
	-docker rm -f producer-rust-edge
	docker run -d --name producer-rust-edge --net=host --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 100 --frequency 50 --dataset-path /app/data/robot_data.parquet

produce-100-100hz-rust-edge:
	-docker rm -f producer-rust-edge
	docker run -d --name producer-rust-edge --net=host --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer-rust:latest ./rust_producer --robots 100 --frequency 100 --dataset-path /app/data/robot_data.parquet

stop-produce-rust-edge:
	-docker stop producer-rust-edge
	-docker rm -f producer-rust-edge

setup-robot-data-cloud:
	-docker rm -f producer-robot-data-cloud
	docker run --name producer-robot-data-cloud --env-file=./src/cloud.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py setup robot_data

setup-robot-data-edge:
	-docker rm -f producer-robot-data-edge
	docker run --name producer-robot-data-edge --env-file=./src/edge.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py setup robot_data

produce-robot-data-cloud:
	-docker rm -f producer-robot-data-cloud
	docker run -d --name producer-robot-data-cloud --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 1

stop-produce-robot-data-cloud:
	-docker stop producer-robot-data-cloud
	-docker rm -f producer-robot-data-cloud

produce-robot-data-edge: 
	docker rm -f producer-robot-data-edge
	docker run -d --name producer-robot-data-edge --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 1

stop-produce-robot-data-edge:
	-docker stop producer-robot-data-edge
	docker rm -f producer-robot-data-edge

produce-10-robots-cloud:
	-docker rm -f producer-robot-data-cloud
	docker run -d --name producer-robot-data-cloud --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 10

produce-50-robots-cloud:
	-docker rm -f producer-robot-data-cloud
	docker run -d --name producer-robot-data-cloud --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 50

produce-100-robots-cloud:
	-docker rm -f producer-robot-data-cloud
	docker run -d --name producer-robot-data-cloud --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 100

produce-100-robots-20hz-cloud:
	-docker rm -f producer-robot-data-cloud
	docker run -d --name producer-robot-data-cloud --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 100 --frequency 20

produce-100-robots-50hz-cloud:
	-docker rm -f producer-robot-data-cloud
	docker run -d --name producer-robot-data-cloud --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 100 --frequency 50

produce-100-robots-100hz-cloud:
	-docker rm -f producer-robot-data-cloud
	docker run -d --name producer-robot-data-cloud --env-file=./src/cloud.env -v $(CURDIR)/data/tcp_dump_cloud:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 100 --frequency 100

produce-10-robots-edge:
	docker rm -f producer-robot-data-edge
	docker run -d --name producer-robot-data-edge --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 10

produce-50-robots-edge:
	docker rm -f producer-robot-data-edge
	docker run -d --name producer-robot-data-edge --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 50

produce-100-robots-edge:
	docker rm -f producer-robot-data-edge
	docker run -d --name producer-robot-data-edge --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 100

produce-100-robots-20hz-edge:
	docker rm -f producer-robot-data-edge
	docker run -d --name producer-robot-data-edge --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 100 --frequency 20

produce-100-robots-50hz-edge:
	docker rm -f producer-robot-data-edge
	docker run -d --name producer-robot-data-edge --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 100 --frequency 50

produce-100-robots-100hz-edge:
	docker rm -f producer-robot-data-edge
	docker run -d --name producer-robot-data-edge --env-file=./src/edge.env -v $(CURDIR)/data/tcp_dump_edge:/app/data arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce robot_data robot_data --num-robots 100 --frequency 100

produce-10-robots: produce-10-robots-cloud produce-10-robots-edge
produce-50-robots: produce-50-robots-cloud produce-50-robots-edge
produce-100-robots: produce-100-robots-cloud produce-100-robots-edge

start-produce: build-producer produce-robot-data-cloud produce-robot-data-edge

stop-produce: stop-produce-robot-data-cloud stop-produce-robot-data-edge

experiment-cloud: 
	@echo "Starting consumer..."
	$(MAKE) consume-robot-data-cloud
	@echo "Waiting 5 minutes for consumer start..."
	sleep 300
	@echo "Starting experiment with 1 robot..."
	$(MAKE) produce-robot-data-cloud
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-cloud
	@echo "Starting experiment with 10 robots..."
	$(MAKE) produce-10-robots-cloud
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-cloud
	@echo "Starting experiment with 50 robots..."
	$(MAKE) produce-50-robots-cloud
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-cloud
	@echo "Starting experiment with 100 robots..."
	$(MAKE) produce-100-robots-cloud
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-cloud
	@echo "Starting experiment with 100 - 20hz robots..."
	$(MAKE) produce-100-robots-20hz-cloud
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-cloud
	@echo "Starting experiment with 100 - 50hz robots..."
	$(MAKE) produce-100-robots-50hz-cloud
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-cloud
	@echo "Starting experiment with 100 - 100hz robots..."
	$(MAKE) produce-100-robots-100hz-cloud
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-cloud
	@echo "Experiment finished."

experiment-edge:
	@echo "Starting consumer..."
	$(MAKE) consume-robot-data-edge
	@echo "Waiting 5 minutes for consumer start..."
	sleep 300
	@echo "Starting experiment with 1 robot..."
	$(MAKE) produce-robot-data-edge
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-edge
	@echo "Starting experiment with 10 robots..."
	$(MAKE) produce-10-robots-edge
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-edge
	@echo "Starting experiment with 50 robots..."
	$(MAKE) produce-50-robots-edge
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-edge
	@echo "Starting experiment with 100 robots..."
	$(MAKE) produce-100-robots-edge
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-edge
	@echo "Starting experiment with 100 - 20hz robots..."
	$(MAKE) produce-100-robots-20hz-edge
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-edge
	@echo "Starting experiment with 100 - 50hz robots..."
	$(MAKE) produce-100-robots-50hz-edge
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-edge
	@echo "Starting experiment with 100 - 100hz robots..."
	$(MAKE) produce-100-robots-100hz-edge
	@echo "Running for 15 minutes..."
	sleep 900
	$(MAKE) stop-produce-robot-data-edge
	@echo "Experiment finished."

start-experiments: experiment-cloud experiment-edge

build-consumer:
	docker build -t arthurkretzer/streaming-consumer:3.5.4 -f ./docker/streaming-consumer.Dockerfile ./src
	docker push arthurkretzer/streaming-consumer:3.5.4

consume-robot-data-cloud:
	kubectl --context $(CLOUD_CONTEXT) apply -f ./kubernetes/cloud/yamls/consumer.yaml

stop-consume-robot-data-cloud:
	kubectl --context $(CLOUD_CONTEXT) delete -f ./kubernetes/cloud/yamls/consumer.yaml

consume-robot-data-edge:
	kubectl --context $(EDGE_CONTEXT) apply -f ./kubernetes/edge/yamls/consumer.yaml

stop-consume-robot-data-edge:
	kubectl --context $(EDGE_CONTEXT) delete -f ./kubernetes/edge/yamls/consumer.yaml

start-consume: consume-robot-data-edge consume-robot-data-cloud 

stop-consume: stop-consume-robot-data-cloud stop-consume-robot-data-edge

# Data Collection
collect-metrics:
	uv run src/prometheus_metrics.py --edge-ip=$(EDGE_IP) --cloud-ip=$(CLOUD_IP) --experiment-name=$(EXP_NAME)

spark-pods:
	kubectl --context $(CLOUD_CONTEXT) get pods -n spark-jobs
	kubectl --context $(EDGE_CONTEXT) get pods -n spark-jobs

spark-logs:
	kubectl --context $(CLOUD_CONTEXT) logs streaming-pipeline-kafka-avro-to-delta-driver -n spark-jobs
	kubectl --context $(EDGE_CONTEXT) logs streaming-pipeline-kafka-avro-to-delta-driver -n spark-jobs