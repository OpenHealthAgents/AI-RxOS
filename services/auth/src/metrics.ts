const metricsStore: Record<string, number> = {};

export function incrementMetric(name: string, value = 1) {
  metricsStore[name] = (metricsStore[name] ?? 0) + value;
}

export function setMetric(name: string, value: number) {
  metricsStore[name] = value;
}

export function getMetrics() {
  return { ...metricsStore };
}

export function resetMetrics() {
  Object.keys(metricsStore).forEach((key) => delete metricsStore[key]);
}
