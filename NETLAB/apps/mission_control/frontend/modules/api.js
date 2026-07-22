export class ApiError extends Error {
  constructor(message, payload = null, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.payload = payload;
    this.status = status;
  }
}

async function request(path, options = {}, { allowApplicationFailure = false } = {}) {
  const response = await fetch(path, {
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const raw = await response.text();
  let payload;
  try {
    payload = raw ? JSON.parse(raw) : {};
  } catch {
    throw new ApiError(`The server returned non-JSON content for ${path} (${response.status}).`, { raw }, response.status);
  }
  if (!response.ok || (!allowApplicationFailure && payload?.ok === false)) {
    const error = payload?.error || {};
    throw new ApiError(error.message || payload?.message || `Request failed with HTTP ${response.status}.`, payload, response.status);
  }
  return payload;
}

const post = (path, body = {}) => request(path, { method: 'POST', body: JSON.stringify(body) });

export const api = {
  get: path => request(path),
  post,
  health: () => request('/api/health'),
  readiness: () => request('/api/readiness'),
  status: () => request('/api/status'),
  config: () => request('/api/config'),
  saveConfig: (config, sync = true) => post('/api/config', { config, sync }),
  validateConfig: config => post('/api/config/validate', { config }),
  command: (name, payload = {}) => post('/api/command', { name, payload }),
  topology: () => request('/api/topology'),
  saveTopology: (topology, drones = undefined, station = undefined, replaceInventory = true, sync = true) => post('/api/topology', {
    topology,
    ...(drones ? { drones } : {}),
    ...(station ? { station } : {}),
    replace_inventory: replaceInventory,
    sync,
  }),
  validateTopology: topology => post('/api/topology/validate', { topology }),
  saveSwarm: (drones, sync = true) => post('/api/swarm', { drones, sync }),
  saveAntennas: (antennas, sync = true) => post('/api/antennas', { antennas, sync }),
  saveWorld: (world, sync = true) => post('/api/world', { world, sync }),
  saveTraffic: (traffic, sync = true) => post('/api/traffic', { traffic, sync }),
  saveFailures: (failures, sync = true) => post('/api/failures', { failures, sync }),
  telemetry: () => request('/api/telemetry'),
  telemetryStream: () => '/api/telemetry/stream',
  events: (limit = 100) => request(`/api/events?limit=${encodeURIComponent(limit)}`),
  diagnostics: () => request('/api/diagnostics', {}, { allowApplicationFailure: true }),
  packetDoctor: () => request('/api/packet-doctor', {}, { allowApplicationFailure: true }),
  synchronization: () => request('/api/synchronization'),
  revisions: () => request('/api/revisions'),
  plugins: () => request('/api/plugins'),
  actions: () => request('/api/actions'),
  algorithms: () => request('/api/algorithms'),
  algorithm: id => request(`/api/algorithms/${encodeURIComponent(id)}`),
  algorithmSelection: () => request('/api/algorithm/selection'),
  algorithmRuns: () => request('/api/algorithm/runs'),
  createAlgorithm: (algorithmId, name = '', category = 'controller') => post('/api/algorithm/create', { algorithm_id: algorithmId, name, category }),
  validateAlgorithm: algorithmId => post('/api/algorithm/validate', { algorithm_id: algorithmId }),
  algorithmSource: algorithmId => request(`/api/algorithm/source?algorithm_id=${encodeURIComponent(algorithmId)}`),
  saveAlgorithmSource: (algorithmId, source) => post('/api/algorithm/source', { algorithm_id: algorithmId, source }),
  dryRunAlgorithm: (algorithmId, parameters = {}, negativeTest = false, observation = undefined) => post('/api/algorithm/dry-run', { algorithm_id: algorithmId, parameters, negative_test: negativeTest, ...(observation ? { observation } : {}) }),
  activateAlgorithm: (algorithmId, parameters = {}, sync = true) => post('/api/algorithm/activate', { algorithm_id: algorithmId, parameters, sync }),
  deactivateAlgorithm: (sync = true) => post('/api/algorithm/deactivate', { sync }),
  compareAlgorithms: (algorithmIds, parameters = {}, replications = 3, seed = undefined) => post('/api/algorithm/compare', { algorithm_ids: algorithmIds, parameters, replications, ...(seed === undefined ? {} : { seed }) }),
  exportAlgorithmRun: runId => post('/api/algorithm/export', { run_id: runId }),
  evidence: () => request('/api/evidence'),
  guide: () => request('/api/guide'),
  guidedDemo: (step, payload = {}) => post('/api/guided-demo', { step, payload }),
  previewLink: payload => post('/api/link/preview', payload),
  jobs: () => request('/api/jobs'),
  job: id => request(`/api/jobs/${encodeURIComponent(id)}`),
  logs: (service, tail = 200) => request(`/api/logs/${encodeURIComponent(service)}?tail=${encodeURIComponent(tail)}`),
  invokePlugin: (plugin, hook, context, timeoutS = 0.25) => post('/api/plugin/invoke', { plugin, hook, context, timeout_s: timeoutS }),
  createPluginTemplate: filename => post('/api/plugin/template', { filename }),
  researchA2G: payload => post('/api/research/a2g', payload),
  researchNtn: payload => post('/api/research/ntn', payload),
  researchOffload: payload => post('/api/research/offload', payload),
  researchRadioMap: payload => post('/api/research/radio-map', payload),
  researchCalibrate: payload => post('/api/research/calibrate', payload),
};

export async function waitForJob(jobId, { onUpdate = () => {}, intervalMs = 750, timeoutMs = 20 * 60 * 1000 } = {}) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const response = await api.job(jobId);
    const job = response.job;
    onUpdate(job);
    if (['COMPLETED', 'FAILED'].includes(job.status)) return job;
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
  throw new ApiError(`Job ${jobId} did not complete within ${Math.round(timeoutMs / 1000)} seconds.`);
}
