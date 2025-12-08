{{/* _helpers.tpl file for common Helm template helpers */}}

{{/* Generate the full name of the release, including the name of the chart and release. */}}
{{- define "hive-metastore.fullname" -}}
{{- if .Values.fullnameOverride -}}
  {{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
  {{- $name := default .Chart.Name .Values.nameOverride -}}
  {{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/* Generate the name of the chart based on nameOverride or the chart's name. */}}
{{- define "hive-metastore.chartName" -}}
{{- default .Chart.Name .Values.nameOverride -}}
{{- end -}}

{{/* Labels for common resources */}}
{{- define "hive-metastore.labels" -}}
  app.kubernetes.io/name: {{ include "hive-metastore.chartName" . }}
  helm.sh/chart: {{ include "hive-metastore.chartName" . }}-{{ .Chart.Version }}
  app.kubernetes.io/instance: {{ .Release.Name }}
  app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Selector labels for workload resources */}}
{{- define "hive-metastore.selectorLabels" -}}
  app: {{ include "hive-metastore.chartName" . }}
{{- end -}}
