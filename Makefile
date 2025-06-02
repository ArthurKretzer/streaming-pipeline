start: kube-context terraform-init services-external-ips

clean: kube-context
	cd terraform && terraform destroy

kube-context:
	kubectx do-nyc1-k8s-cluster

terraform-init:
	cd terraform && terraform init
	cd terraform && terraform plan -target=kubernetes_namespace.monitoring -target=helm_release.argocd 
	cd terraform && terraform apply -target=kubernetes_namespace.monitoring -target=helm_release.argocd
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

build-spark:
	docker build -t arthurkretzer/spark:3.5.4 -f ./docker/spark.Dockerfile
	docker push arthurkretzer/spark:3.5.4

build-producer:
	docker build -t arthurkretzer/streaming-producer:3.5.4 -f ./docker/streaming-producer.Dockerfile ./src
	docker push arthurkretzer/streaming-producer:3.5.4

produce-control-power-cloud:
	docker rm -f producer-control-power-cloud
	docker run -d --name producer-control-power-cloud --env-file=./src/cloud.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power avro

stop-produce-control-power-cloud:
	docker rm -f producer-control-power-cloud

produce-control-power-edge: 
	docker rm -f producer-control-power-edge
	docker run -d --name producer-control-power-edge --env-file=./src/edge.env arthurkretzer/streaming-producer:3.5.4 uv run /app/main.py produce control_power control_power avro

stop-produce-control-power-edge:
	docker rm -f producer-control-power-edge

start-produce: build-producer produce-control-power-cloud produce-control-power-edge

stop-produce: stop-produce-control-power-cloud stop-produce-control-power-edge

build-consumer:
	docker build -t arthurkretzer/streaming-consumer:3.5.4 -f ./docker/streaming-consumer.Dockerfile ./src
	docker push arthurkretzer/streaming-consumer:3.5.4

consume-control-power-cloud:
	kubectx do-nyc1-k8s-cluster
	kubectl apply -f ./kubernetes/yamls/consumer.yaml

stop-consume-control-power-cloud:
	kubectx do-nyc1-k8s-cluster
	kubectl delete -f ./kubernetes/yamls/consumer.yaml
	
consume-control-power-edge:
	kubectx labfaber
	kubectl apply -f ./kubernetes/yamls/consumer-edge.yaml

stop-consume-control-power-edge:
	kubectx labfaber
	kubectl delete -f ./kubernetes/yamls/consumer-edge.yaml

start-consume: consume-control-power-edge consume-control-power-cloud 

stop-consume: stop-consume-control-power-cloud stop-consume-control-power-edge