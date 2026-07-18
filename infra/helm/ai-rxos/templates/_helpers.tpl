{{/* Chart name, truncated for k8s name limits. */}}
{{- define "ai-rxos.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully qualified app name: <release>-<chart> unless fullnameOverride is set. */}}
{{- define "ai-rxos.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "ai-rxos.namespace" -}}
{{- default .Release.Namespace .Values.namespaceOverride -}}
{{- end -}}

{{- define "ai-rxos.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels applied to every resource. */}}
{{- define "ai-rxos.labels" -}}
helm.sh/chart: {{ include "ai-rxos.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: ai-rxos
{{ include "ai-rxos.selectorLabels" . }}
{{- end -}}

{{/* Selector labels for a specific service, called with (dict "root" $ "service" $svcName). */}}
{{- define "ai-rxos.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ai-rxos.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "ai-rxos.serviceLabels" -}}
{{ include "ai-rxos.labels" .root }}
app.kubernetes.io/component: {{ .service }}
{{- end -}}

{{- define "ai-rxos.serviceSelectorLabels" -}}
{{ include "ai-rxos.selectorLabels" .root }}
app.kubernetes.io/component: {{ .service }}
{{- end -}}

{{- define "ai-rxos.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "ai-rxos.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* Name of the Secret to mount — externalSecret.name in prod, or the chart-managed one. */}}
{{- define "ai-rxos.secretName" -}}
{{- if .Values.externalSecret.enabled -}}
{{- .Values.externalSecret.name -}}
{{- else -}}
{{- printf "%s-secrets" (include "ai-rxos.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/* Full image reference for a service entry, e.g. (dict "root" $ "svc" $svc). */}}
{{- define "ai-rxos.image" -}}
{{- $registry := .root.Values.global.imageRegistry -}}
{{- if $registry -}}
{{- printf "%s/%s:%s" $registry .svc.image.repository .svc.image.tag -}}
{{- else -}}
{{- printf "%s:%s" .svc.image.repository .svc.image.tag -}}
{{- end -}}
{{- end -}}
