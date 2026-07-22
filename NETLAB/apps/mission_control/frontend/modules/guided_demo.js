import { api, waitForJob } from './api.js';
import { preferences } from './storage.js';
import { escapeHtml, prettyJson, toast, viewHeader } from './components.js';

const storedKey = 'netlab.guidedDemo.state.v1';

function loadProgress() { return preferences.getJson(storedKey, {}); }
function saveProgress(value) { preferences.setJson(storedKey, value); }

export async function renderGuidedDemo(root) {
  const guide = await api.guide();
  const progress = loadProgress();
  guide.steps = Array.isArray(guide.steps) && guide.steps.length ? guide.steps : [{ id: 'guide_unavailable', title: 'Guided sequence unavailable', description: 'The server returned no guided-demo steps. Open Diagnostics and verify the Mission Control API version.', automatic: false }];
  let selected = guide.steps.find(step => !progress[step.id])?.id || guide.steps[0].id;
  root.innerHTML = `${viewHeader('Guided Demo', 'A first-run operator sequence that executes safe actions, waits for acknowledgements, and explains why packet forwarding advances or pauses.', `<button class="button secondary" id="demo-reset">Reset Demo</button><button class="button primary" id="demo-run-next">Run Next Step</button>`)}
  <div class="grid sidebar-layout">
    <section class="card">
      <div class="card-header"><div><h2>First simulation sequence</h2><p class="card-description">Every automatic step is connected to the real control plane. Manual observation steps never fabricate completion.</p></div></div>
      <div class="progress-list" id="demo-steps">
        ${guide.steps.map((step, index) => `<button class="progress-item ${progress[step.id]?.status === 'complete' ? 'complete' : progress[step.id]?.status === 'failed' ? 'failed' : ''} ${step.id === selected ? 'running' : ''}" data-step="${escapeHtml(step.id)}" type="button">
          <span class="progress-index">${progress[step.id]?.status === 'complete' ? '✓' : progress[step.id]?.status === 'failed' ? '!' : index + 1}</span>
          <span><span class="progress-title">${escapeHtml(step.title)}</span><span class="progress-description">${escapeHtml(step.description)}</span></span>
          <span class="status-chip ${progress[step.id]?.status === 'complete' ? 'ready' : progress[step.id]?.status === 'failed' ? 'error' : 'neutral'}">${escapeHtml(progress[step.id]?.status?.toUpperCase() || (step.automatic ? 'AUTOMATIC' : 'OBSERVE'))}</span>
        </button>`).join('')}
      </div>
    </section>
    <aside class="card raised" id="demo-inspector"></aside>
  </div>`;

  const steps = new Map(guide.steps.map(step => [step.id, step]));
  const inspector = root.querySelector('#demo-inspector');
  const renderInspector = () => {
    const step = steps.get(selected);
    const record = progress[selected];
    inspector.innerHTML = `<div class="eyebrow">CURRENT STEP</div><h2 style="margin-top:5px">${escapeHtml(step.title)}</h2><p class="muted">${escapeHtml(step.description)}</p>
      <div class="callout ${record?.status === 'failed' ? 'error' : record?.status === 'complete' ? 'success' : ''}">
        <div class="callout-title">${step.automatic ? 'Executable from Mission Control' : 'Operator observation'}</div>
        <div>${step.automatic ? 'Run this step and wait for an explicit acknowledgement.' : 'Open the indicated module, inspect the live state, then mark the step complete.'}</div>
      </div>
      <div class="row" style="margin-top:16px">
        ${step.automatic ? `<button class="button primary" id="demo-execute">Execute Step</button>` : `<button class="button success" id="demo-mark">Mark Observation Complete</button>`}
        <button class="button secondary" id="demo-skip">Skip with Record</button>
      </div>
      ${record ? `<hr class="separator"><h3>Last result</h3>${prettyJson(record.result || record)}` : ''}`;
    inspector.querySelector('#demo-execute')?.addEventListener('click', () => execute(selected));
    inspector.querySelector('#demo-mark')?.addEventListener('click', () => complete(selected, { observation: 'operator_confirmed' }));
    inspector.querySelector('#demo-skip')?.addEventListener('click', () => complete(selected, { skipped: true, reason: 'operator_selected_skip' }, 'complete'));
  };

  const refreshClasses = () => {
    root.querySelectorAll('[data-step]').forEach(element => {
      const id = element.dataset.step;
      element.classList.toggle('running', id === selected);
      element.classList.toggle('complete', progress[id]?.status === 'complete');
      element.classList.toggle('failed', progress[id]?.status === 'failed');
      const badge = element.querySelector('.status-chip');
      const index = element.querySelector('.progress-index');
      badge.className = `status-chip ${progress[id]?.status === 'complete' ? 'ready' : progress[id]?.status === 'failed' ? 'error' : 'neutral'}`;
      badge.textContent = progress[id]?.status?.toUpperCase() || (steps.get(id).automatic ? 'AUTOMATIC' : 'OBSERVE');
      index.textContent = progress[id]?.status === 'complete' ? '✓' : progress[id]?.status === 'failed' ? '!' : guide.steps.findIndex(item => item.id === id) + 1;
    });
    renderInspector();
  };

  const complete = (id, result, status = 'complete') => {
    progress[id] = { status, completed_at: Date.now() / 1000, result };
    saveProgress(progress);
    const next = guide.steps.find(step => !progress[step.id]);
    if (next) selected = next.id;
    refreshClasses();
  };

  const execute = async id => {
    const button = inspector.querySelector('#demo-execute');
    if (button) { button.disabled = true; button.textContent = 'Waiting for acknowledgement…'; }
    try {
      const response = await api.guidedDemo(id, {});
      let acknowledged = response;
      if (response.job) {
        document.dispatchEvent(new CustomEvent('netlab:job', { detail: response.job }));
        acknowledged = await waitForJob(response.job.job_id, {
          intervalMs: 1000,
          timeoutMs: 15 * 60 * 1000,
          onUpdate: job => {
            document.dispatchEvent(new CustomEvent('netlab:job', { detail: job }));
            const activeButton = inspector.querySelector('#demo-execute');
            if (activeButton) activeButton.textContent = `Waiting: ${job.progress?.at(-1)?.stage || job.status}…`;
          },
        });
        if (acknowledged.status !== 'COMPLETED') {
          const message = acknowledged.error?.message || `${steps.get(id).title} failed before acknowledgement.`;
          const failure = new Error(message);
          failure.payload = acknowledged;
          throw failure;
        }
      }
      complete(id, acknowledged, 'complete');
      toast(`${steps.get(id).title} completed with runtime acknowledgement.`, 'success');
    } catch (error) {
      progress[id] = { status: 'failed', completed_at: Date.now() / 1000, result: error.payload || { message: error.message } };
      saveProgress(progress);
      refreshClasses();
      toast(error.message, 'error');
    }
  };

  root.querySelectorAll('[data-step]').forEach(element => element.addEventListener('click', () => { selected = element.dataset.step; refreshClasses(); }));
  root.querySelector('#demo-reset').addEventListener('click', () => { preferences.remove(storedKey); location.reload(); });
  root.querySelector('#demo-run-next').addEventListener('click', () => {
    const step = steps.get(selected);
    if (step.automatic) execute(selected); else complete(selected, { observation: 'operator_confirmed_from_next' });
  });
  renderInspector();
}
