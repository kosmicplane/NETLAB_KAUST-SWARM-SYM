import { api, waitForJob } from './api.js';
import { card, escapeHtml, formatNumber, metricCard, prettyJson, sourceBadge, statusChip, toast, viewHeader } from './components.js';
import { state } from './state.js';

function readinessChip(label, value) {
  return statusChip(label, value ? 'ready' : 'error', value ? `${label} is ready.` : `${label} is not ready.`);
}

function serviceCard(label, service, detail) {
  const running = Boolean(service?.running || service?.ok);
  return `<article class="card metric-card">
    <div class="row space-between"><div class="metric-label">${escapeHtml(label)}</div>${statusChip(running ? 'READY' : 'NOT READY', running ? 'ready' : 'error')}</div>
    <div class="metric-detail" style="margin-top:12px">${escapeHtml(detail || service?.health || service?.error || 'No acknowledgement received.')}</div>
  </article>`;
}

function findLatestGate(runtime, telemetry) {
  return runtime?.packet?.last_gate || runtime?.services?.packet?.heartbeat?.last_gate || telemetry?.rows?.at(-1) || {};
}

export async function renderOverview(root) {
  const [readiness, runtime, telemetry] = await Promise.all([
    api.readiness().catch(error => ({ ok: false, error: error.message, services: {}, findings: [] })),
    api.status().catch(() => ({})),
    api.telemetry().catch(() => ({ source: { source: 'OFFLINE' }, rows: [], analytics: {} })),
  ]);
  state.patch({ readiness, runtime, telemetry });
  const services = readiness.services || {};
  const source = telemetry.source?.source || runtime.telemetry_source || 'OFFLINE';
  const analytics = telemetry.analytics || {};
  const latest = telemetry.rows?.at(-1) || {};
  const latestGate = findLatestGate(runtime, telemetry);
  const phase = runtime.phase || 'STOPPED';
  const packetReady = Boolean(readiness.packet_heartbeat?.fresh || runtime.readiness?.packet_runtime_ready);
  const packetAdvancing = Boolean(runtime.packet?.packet_advancing || ['forwarded', 'FEASIBLE'].includes(String(latest.decision || latest.gate_reason)));
  const findingRows = (readiness.findings || []).map(item => `<div class="callout ${item.severity === 'ERROR' ? 'error' : 'warning'}"><div class="callout-title">${escapeHtml(item.code)}</div><div>${escapeHtml(item.message || '')}</div>${item.action ? `<div class="small-text" style="margin-top:5px"><strong>Recommended action:</strong> ${escapeHtml(item.action)}</div>` : ''}</div>`).join('');

  root.innerHTML = `${viewHeader(
    'Mission overview',
    'Authoritative readiness, packet execution-gate state, experiment health, and direct operational controls.',
    `<button class="button secondary" id="overview-doctor">Run Diagnostics</button><button class="button primary" id="overview-start">Start Complete Stack</button>`
  )}
  <div class="grid four">
    ${metricCard('Runtime phase', phase, '', runtime.last_error ? 'A runtime error requires attention.' : 'Authoritative orchestration lifecycle.')}
    ${metricCard('Packet delivery ratio', `${formatNumber((analytics.packet_delivery_ratio || 0) * 100, 1)}%`, '', `${analytics.delivered_packets || 0} delivered / ${analytics.generated_packets || 0} generated`)}
    ${metricCard('Link feasibility ratio', `${formatNumber((analytics.link_feasibility_ratio || 0) * 100, 1)}%`, '', `${analytics.feasible_samples || 0} feasible samples`)}
    ${metricCard('Live metric samples', analytics.samples ?? 0, '', source === 'LIVE' ? 'Fresh measured runtime samples.' : `Source classified as ${source}.`)}
  </div>
  <div class="grid four" style="margin-top:16px">
    ${serviceCard('Isaac Sim', services.isaac, readiness.isaac_sync?.state || 'No scene acknowledgement')}
    ${serviceCard('ROS 2', services['ros2-core'], packetReady ? 'Packet runtime heartbeat is fresh.' : 'ROS container and packet runtime are distinct readiness conditions.')}
    ${serviceCard('Sionna link service', services['sionna-engine'], readiness.sionna_api?.ok ? 'Health endpoint acknowledged.' : 'Link-service API is not ready.')}
    <article class="card metric-card"><div class="row space-between"><div class="metric-label">Telemetry source</div>${sourceBadge(source)}</div><div class="metric-detail" style="margin-top:12px">${escapeHtml(telemetry.source?.reason || 'Source classification unavailable.')}</div></article>
  </div>

  <div class="grid two" style="margin-top:16px">
    ${card('Execution Gate Readiness', 'Packet advancement is permitted only after every predicate passes.', `
      <div class="grid two">
        <div class="stack">
          ${readinessChip('Packet runtime', packetReady)}
          ${readinessChip('Source endpoint', !['SOURCE_FAILED','SOURCE_INACTIVE'].includes(String(latestGate.reason || latest.gate_reason)))}
          ${readinessChip('Destination endpoint', !['DESTINATION_FAILED','DESTINATION_INACTIVE'].includes(String(latestGate.reason || latest.gate_reason)))}
          ${readinessChip('Range predicate', !['OUT_OF_RANGE','HARD_OUTAGE_DISTANCE'].includes(String(latestGate.reason || latest.gate_reason)))}
        </div>
        <div class="stack">
          ${readinessChip('SNR / SINR predicate', !['SNR_BELOW_THRESHOLD','SINR_BELOW_THRESHOLD'].includes(String(latestGate.reason || latest.gate_reason)))}
          ${readinessChip('Capacity predicate', String(latestGate.reason || latest.gate_reason) !== 'CAPACITY_BELOW_THRESHOLD')}
          ${readinessChip('Isaac acknowledgement', Boolean(readiness.isaac_sync?.acknowledged || runtime.readiness?.isaac_scenario_acknowledged))}
          ${readinessChip('Packet advancing', packetAdvancing)}
        </div>
      </div>
      <div class="callout ${packetAdvancing ? 'success' : packetReady ? 'warning' : 'error'}" style="margin-top:16px">
        <div class="callout-title">${packetAdvancing ? 'Packet advancement observed' : packetReady ? 'Packet runtime is active but forwarding is paused or not yet observed' : 'No live packet runtime'}</div>
        <div>Current gate reason: <strong>${escapeHtml(latest.gate_reason || latestGate.reason || runtime.packet?.outage_reason || 'UNAVAILABLE')}</strong>.</div>
      </div>
    `)}
    ${card('Current Link / SLA Telemetry', 'Latest measured hop; no synthetic preview is labeled as live.', telemetry.rows?.length ? `
      <div class="table-wrap"><table><tbody>
        <tr><th>Source</th><td>${escapeHtml(latest.src || '—')}</td><th>Destination</th><td>${escapeHtml(latest.dst || '—')}</td></tr>
        <tr><th>Distance</th><td>${formatNumber(latest.distance_m, 2)} m</td><th>Range margin</th><td>${formatNumber(latest.range_margin_m, 2)} m</td></tr>
        <tr><th>SNR</th><td>${formatNumber(latest.snr_db, 2)} dB</td><th>SINR</th><td>${formatNumber(latest.sinr_db, 2)} dB</td></tr>
        <tr><th>Capacity</th><td>${formatNumber(latest.capacity_mbps, 2)} Mbps</td><th>Total delay</th><td>${formatNumber(latest.total_delay_ms || latest.delay_ms, 3)} ms</td></tr>
        <tr><th>Path loss</th><td>${formatNumber(latest.path_loss_db, 2)} dB</td><th>Received power</th><td>${formatNumber(latest.rx_power_dbm, 2)} dBm</td></tr>
        <tr><th>Decision</th><td colspan="3"><strong>${escapeHtml(latest.gate_reason || latest.decision || 'UNAVAILABLE')}</strong></td></tr>
      </tbody></table></div>
    ` : `<div class="empty-state"><div><div class="empty-icon">⇢</div><strong>No live link samples</strong><div class="small-text">Start the complete stack and packet runtime. Mission Control will not fabricate link telemetry.</div></div></div>`)}
  </div>

  <div class="grid two" style="margin-top:16px">
    ${card('Quick operations', 'Each control waits for a backend or runtime acknowledgement.', `
      <div class="row">
        <button class="button primary" data-command="start_experiment">Start Experiment</button>
        <button class="button secondary" data-command="sync_isaac">Synchronize Isaac</button>
        <button class="button warning" data-command="recompute_topology">Recompute Topology</button>
        <button class="button danger" data-command="stop_stack">Stop Stack</button>
      </div>
    `)}
    ${card('Findings and required actions', 'Diagnostics report state divergence and stale components explicitly.', findingRows || `<div class="callout success"><div class="callout-title">No blocking diagnostic findings</div><div>All currently observable readiness checks are coherent.</div></div>`)}
  </div>
  <details class="card" style="margin-top:16px"><summary><strong>Advanced authoritative state</strong></summary><div style="margin-top:14px">${prettyJson(runtime)}</div></details>`;

  const startButton = root.querySelector('#overview-start');
  startButton.addEventListener('click', async () => {
    startButton.disabled = true;
    try {
      const response = await api.command('start_stack', { build: true });
      toast('Start Stack was accepted. Progress is available in the Activity drawer.', 'success');
      document.dispatchEvent(new CustomEvent('netlab:job', { detail: response.job }));
    } catch (error) { toast(error.message, 'error'); }
    finally { startButton.disabled = false; }
  });
  root.querySelector('#overview-doctor').addEventListener('click', () => state.navigate('diagnostics'));
  root.querySelectorAll('[data-command]').forEach(button => button.addEventListener('click', async () => {
    const name = button.dataset.command;
    button.disabled = true;
    try {
      const response = await api.command(name, {});
      if (response.job) document.dispatchEvent(new CustomEvent('netlab:job', { detail: response.job }));
      toast(`${name.replaceAll('_', ' ')} was acknowledged by Mission Control.`, 'success');
    } catch (error) { toast(error.message, 'error'); }
    finally { button.disabled = false; }
  }));
}
