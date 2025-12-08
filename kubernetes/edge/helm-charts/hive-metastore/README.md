# Hive Metastore Helm Chart

This Helm chart is used to deploy the [Hive Metastore](https://hive.apache.org/) on Kubernetes. The Hive Metastore is a critical component of the Apache Hive architecture, used to manage metadata for Hive tables, and it supports various data lake integrations.

## Prerequisites

- Kubernetes 1.16+
- Helm 3+
- Persistent Volume provisioner support in the underlying infrastructure

## Installation

To install the chart with the release name `hive-metastore`:

```sh
helm dependency build infrastructure/helm-charts/my-hive
helm install hive-metastore -n hive-metastore infrastructure/helm-charts/my-hive --create-namespace
```

The command deploys the Hive Metastore on the Kubernetes cluster with the default configuration. The [Parameters](#parameters) section lists the configuration options that can be customized.

## Uninstallation

To uninstall/delete the `hive-metastore` deployment:

```sh
helm uninstall hive-metastore
```

This command removes all the Kubernetes components associated with the chart and deletes the release.

## Parameters

### Global Configuration

| Parameter                     | Description                                     | Default               |
|-------------------------------|-------------------------------------------------|-----------------------|
| `global.database.port`        | Port for database connection                    | `5432`                |
| `global.database.db`          | Database name                                   | `metastore`           |
| `global.database.user`        | Database user                                   | `hiveuser`            |
| `global.database.passwordSecretName` | Secret name containing the database password  | `hive-metastore-db-secret` |
| `global.database.internal.enabled` | Enable internal PostgreSQL                    | `true`                |
| `global.database.external.enabled` | Use an external database                      | `false`               |
| `global.database.external.host` | External database host                         | `""`                  |
| `global.database.persistence.size` | Storage size for database persistence         | `10Gi`                |
| `global.database.persistence.storageClass` | Storage class for persistence              | `""`                  |

### Hive Metastore Configuration

| Parameter                     | Description                                     | Default               |
|-------------------------------|-------------------------------------------------|-----------------------|
| `hiveMetastore.image.repository` | Docker repository for the Hive Metastore image | `your-docker-repo/hive-metastore` |
| `hiveMetastore.image.tag`     | Image tag/version                               | `4.0.0`               |
| `hiveMetastore.image.pullPolicy` | Image pull policy                              | `IfNotPresent`        |
| `hiveMetastore.service.type`  | Kubernetes service type                         | `ClusterIP`           |
| `hiveMetastore.service.port`  | Service port for Thrift communication           | `9083`                |
| `hiveMetastore.s3.bucket`     | S3 bucket name for storage                      | `your-s3-bucket`      |
| `hiveMetastore.s3.prefix`     | S3 prefix for storage                           | `your-s3-prefix`      |
| `hiveMetastore.s3.endpointUrl` | Custom S3 endpoint URL                          | `your-s3-endpoint`    |
| `hiveMetastore.s3.accessKeySecretName` | Secret name for S3 access keys               | `hive-metastore-s3-secret` |
| `hiveMetastore.healthCheck.command` | Command for service health check             | `sh -c netstat -ln | grep 9083` |
| `hiveMetastore.ingress.enabled` | Enable/disable Ingress                          | `false`               |
| `hiveMetastore.ingress.hosts` | Hosts for Ingress                               | `hive-metastore.local`|
| `hiveMetastore.ingress.annotations` | Annotations for Ingress                      | `{}`                  |
| `hiveMetastore.ingress.labels` | Labels for Ingress                              | `{}`                  |
| `hiveMetastore.ingress.ingressClassName` | Ingress class name                           | `""`                  |

### Database Secret

The database password should be stored in a Kubernetes secret. The secret must have a key named `password` that stores the database password.

Example command to create the secret:

```sh
kubectl create secret generic hive-metastore-db-secret --from-literal=password=<your-password>
```

## Persistence

The chart mounts a Persistent Volume for the Hive Metastore to store metadata. By default, a PersistentVolumeClaim is created and mounted into the container. You can change the storage class and size by configuring the `global.database.persistence` values.

## Ingress

To enable Ingress for external access, set `hiveMetastore.ingress.enabled` to `true` and configure the hosts and paths as needed. You can also provide custom annotations and labels for the Ingress resource.

## License

[Apache 2.0 License](https://www.apache.org/licenses/LICENSE-2.0)

