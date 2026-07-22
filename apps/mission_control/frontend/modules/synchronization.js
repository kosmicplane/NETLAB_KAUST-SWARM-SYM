import { api } from './api.js';
import { card, escapeHtml, prettyJson, statusChip, toast, viewHeader } from './components.js';

export async function renderSynchronization(root) {
  const response = await api.synchronization();
  const synchronization = response.synchronization || {};
  const participants = synchronization.participants || {};
  const participantRows = ['ros','sionna','isaac'].map(name => {
    const item = participants[name] || {};
    const state = item.state || 'PENDING';
    return `<tr><td><strong>${escapeHtml(name.toUpperCase())}</strong></td><td>${statusChip(state, state === 'ACKNOWLEDGED' ? 'ready' : state === 'FAILED' ? 'error' : 'warning')}</td><td>${escapeHtml(item.observed_revision || '—')}</td><td>${item.timestamp ? new Date(item.timestamp * 1000).toISOString() : '—'}</td></tr>`;
  }).join('');
  root.innerHTML = `${viewHeader('Synchronization', 'Desired/observed revision reconciliation across Mission Control, ROS 2, Sionna, and Isaac Sim.', '<button id="sync-refresh" class="button secondary" type="button">Refresh</button><button id="sync-reconcile" class="button primary" type="button">Reconcile revision</button>')}
  <div class="grid two">
    ${card('Revision state', 'A revision is committed only after every required participant acknowledges the same revision and component hashes.', `<div class="metric-grid four">
      <div class="metric-card"><div class="metric-label">State</div><div class="metric-value">${escapeHtml(synchronization.state || 'NO_REVISION')}</div></div>
      <div class="metric-card"><div class="metric-label">Desired</div><div class="metric-value small-code">${escapeHtml(response.desired?.revision_id || '—')}</div></div>
      <div class="metric-card"><div class="metric-label">Committed</div><div class="metric-value small-code">${escapeHtml(response.committed?.revision_id || '—')}</div></div>
      <div class="metric-card"><div class="metric-label">Drift</div><div class="metric-value">${escapeHtml((synchronization.drift_participants || []).join(', ') || 'none')}</div></div>
    </div>`)}
    ${card('Participant acknowledgements', 'Observed revisions must match the desired revision exactly.', `<div class="table-wrap"><table><thead><tr><th>Participant</th><th>State</th><th>Observed revision</th><th>Acknowledged</th></tr></thead><tbody>${participantRows}</tbody></table></div>`)}
    ${card('Advanced reconciliation inspector', 'Raw revision evidence is available for reproducibility and diagnostics.', prettyJson(response), '', 'span-2')}
  </div>`;
  root.querySelector('#sync-refresh').addEventListener('click', () => renderSynchronization(root));
  root.querySelector('#sync-reconcile').addEventListener('click', async () => {
    try {
      const result = await api.command('reconcile', {});
      toast(`Reconciliation queued: ${result.job?.job_id || 'accepted'}`, 'success');
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}
