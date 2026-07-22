import { api } from './api.js';
import {
  escapeHtml,
  formatDuration,
  formatNumber,
  prettyJson,
  setBusy,
  statusChip,
  toast,
  viewHeader,
} from './components.js';

function defaultParameters(manifest = {}) {
  const properties = manifest.parameter_schema?.properties || manifest.parameters || {};
  return Object.fromEntries(Object.entries(properties).map(([name, schema]) => [name, schema?.default ?? (schema?.type === 'boolean' ? false : schema?.type === 'array' ? [] : schema?.type === 'object' ? {} : schema?.type === 'string' ? '' : 0)]));
}

function parameterControl(name, schema, value) {
  const id = `algorithm-param-${name}`;
  const label = escapeHtml(name.replaceAll('_', ' '));
  const description = schema?.description ? `<div class="field-help">${escapeHtml(schema.description)}</div>` : '';
  if (Array.isArray(schema?.enum)) {
    return `<label class="field"><span><strong>${label}</strong></span><select id="${id}" data-param="${escapeHtml(name)}">${schema.enum.map(item => `<option value="${escapeHtml(item)}" ${String(item) === String(value) ? 'selected' : ''}>${escapeHtml(item)}</option>`).join('')}</select>${description}</label>`;
  }
  if (schema?.type === 'boolean') {
    return `<label class="checkbox-field"><input id="${id}" data-param="${escapeHtml(name)}" type="checkbox" ${value ? 'checked' : ''}><span>${label}</span></label>`;
  }
  if (['object', 'array'].includes(schema?.type)) {
    return `<label class="field span-2"><span><strong>${label}</strong></span><textarea id="${id}" data-param="${escapeHtml(name)}" data-json="true" rows="4">${escapeHtml(JSON.stringify(value, null, 2))}</textarea>${description}</label>`;
  }
  const type = ['integer', 'number'].includes(schema?.type) ? 'number' : 'text';
  return `<label class="field"><span><strong>${label}</strong>${schema?.unit ? ` <span class="unit">${escapeHtml(schema.unit)}</span>` : ''}</span><input id="${id}" data-param="${escapeHtml(name)}" type="${type}" value="${escapeHtml(value)}" ${schema?.minimum !== undefined ? `min="${escapeHtml(schema.minimum)}"` : ''} ${schema?.maximum !== undefined ? `max="${escapeHtml(schema.maximum)}"` : ''} ${type === 'number' ? 'step="any"' : ''}>${description}</label>`;
}

function collectParameters(root, manifest) {
  const properties = manifest.parameter_schema?.properties || manifest.parameters || {};
  const result = {};
  root.querySelectorAll('[data-param]').forEach(input => {
    const name = input.dataset.param;
    const schema = properties[name] || {};
    if (input.dataset.json === 'true') {
      result[name] = JSON.parse(input.value || (schema.type === 'array' ? '[]' : '{}'));
    } else if (schema.type === 'boolean') {
      result[name] = input.checked;
    } else if (['number', 'integer'].includes(schema.type)) {
      result[name] = schema.type === 'integer' ? Math.trunc(Number(input.value)) : Number(input.value);
    } else {
      result[name] = input.value;
    }
  });
  return result;
}

function algorithmStatus(packageInfo, selectedId) {
  if (!packageInfo.valid) return statusChip('INVALID', 'error', (packageInfo.errors || []).join('; '));
  if (packageInfo.manifest.algorithm_id === selectedId) return statusChip('SELECTED', 'info');
  return statusChip('VALID', 'ready');
}

function workflowCard(step, title, description, complete, active = false) {
  return `<div class="workflow-step ${complete ? 'complete' : active ? 'active' : ''}"><div class="workflow-index">${complete ? '✓' : step}</div><div><strong>${escapeHtml(title)}</strong><div class="small-text muted">${escapeHtml(description)}</div></div></div>`;
}

export async function renderAlgorithmLab(root) {
  let [registry, configResponse, selectionResponse, runsResponse] = await Promise.all([
    api.algorithms(),
    api.config(),
    api.algorithmSelection(),
    api.algorithmRuns(),
  ]);
  let algorithms = registry.algorithms || [];
  let config = structuredClone(configResponse.config || {});
  let selection = selectionResponse.selection || {};
  let runs = runsResponse.runs || [];
  let selectedId = selection.algorithm_id || config.algorithm?.algorithm_id || algorithms.find(item => item.manifest?.algorithm_id === 'connectivity_aware_formation')?.manifest?.algorithm_id || algorithms[0]?.manifest?.algorithm_id || '';
  let parameters = {};
  let source = '';
  let sourceHash = '';
  let validation = null;
  let dryRun = null;
  let negativeTest = null;
  let comparison = null;
  let lastExport = null;
  let sourceDirty = false;

  async function loadSelected() {
    const packageInfo = algorithms.find(item => item.manifest?.algorithm_id === selectedId);
    parameters = {
      ...defaultParameters(packageInfo?.manifest),
      ...(config.algorithm?.algorithm_id === selectedId ? config.algorithm?.parameters || {} : {}),
      ...(selection.algorithm_id === selectedId ? selection.parameters || {} : {}),
    };
    source = '';
    sourceHash = packageInfo?.manifest?.source_hash || '';
    sourceDirty = false;
    if (selectedId) {
      try {
        const response = await api.algorithmSource(selectedId);
        source = response.source || '';
        sourceHash = response.source_hash || sourceHash;
      } catch (error) {
        source = `# Source is not editable for this execution mode.\n# ${error.message}`;
      }
    }
  }

  await loadSelected();

  const render = () => {
    const packageInfo = algorithms.find(item => item.manifest?.algorithm_id === selectedId) || algorithms[0];
    if (!packageInfo) {
      root.innerHTML = `${viewHeader('Algorithm Lab', 'Create, validate, dry-run, execute, and compare researcher-defined swarm algorithms.', '<button class="button primary" id="algorithm-create">Create Algorithm Project</button>')}<section class="card"><div class="empty-state"><div><strong>No algorithm packages found</strong><div class="small-text">Create the first isolated Python algorithm project.</div></div></div></section>`;
      root.querySelector('#algorithm-create')?.addEventListener('click', createProject);
      return;
    }
    const manifest = packageInfo.manifest || {};
    const parameterProperties = manifest.parameter_schema?.properties || manifest.parameters || {};
    const active = selection.algorithm_id === selectedId;
    const workflow = {
      package: packageInfo.valid,
      validation: Boolean(validation?.ok),
      dry: Boolean(dryRun?.shield || dryRun?.pending_external_ros2),
      negative: Boolean(negativeTest?.negative_test_passed),
      active,
      synchronized: Boolean(config.algorithm?.algorithm_id === selectedId && (configResponse?.synchronization?.state === 'IN_SYNC' || selection.algorithm_id === selectedId)),
    };

    root.innerHTML = `${viewHeader(
      'Algorithm Lab',
      'Run researcher-defined controllers, trajectory planners, topology policies, schedulers, optimizers, safety filters, MARL policies, and replay packages through the same ROS 2, Sionna, Isaac, safety, telemetry, and evidence pipeline as native algorithms.',
      '<button class="button secondary" id="algorithm-refresh">Refresh Registry</button><button class="button primary" id="algorithm-create">Create Algorithm Project</button>',
    )}
    <div class="grid sidebar-layout algorithm-layout">
      <section class="card">
        <div class="card-header"><div><h2>Research algorithm registry</h2><p class="card-description">API ${escapeHtml(registry.api_version || '2.0')} · ${algorithms.length} packages · ${registry.valid_count || 0} valid</p></div></div>
        <div class="table-wrap algorithm-registry"><table><thead><tr><th>Algorithm</th><th>Category</th><th>Mode</th><th>Status</th></tr></thead><tbody>
          ${algorithms.map(item => `<tr class="${item.manifest?.algorithm_id === selectedId ? 'selected-row' : ''}"><td><button class="button ghost small" data-algorithm="${escapeHtml(item.manifest?.algorithm_id || '')}">${escapeHtml(item.manifest?.name || item.manifest?.algorithm_id)}</button><div class="small-text muted">${escapeHtml(item.manifest?.algorithm_id || '')} · v${escapeHtml(item.manifest?.version || '—')}</div></td><td>${escapeHtml(item.manifest?.category || '—')}</td><td>${escapeHtml(item.manifest?.execution_mode || '—')}</td><td>${algorithmStatus(item, selectedId)}</td></tr>`).join('')}
        </tbody></table></div>
      </section>
      <aside class="card raised">
        <div class="eyebrow">RESEARCHER WORKFLOW</div><h2>Execution gates</h2>
        <div class="workflow-list">
          ${workflowCard(1, 'Package', 'Manifest, source, license, schemas, and resource budget.', workflow.package, true)}
          ${workflowCard(2, 'Validate', 'Static contract and package validation.', workflow.validation, workflow.package && !workflow.validation)}
          ${workflowCard(3, 'Dry run', 'Isolated execution against an authoritative snapshot.', workflow.dry, workflow.validation && !workflow.dry)}
          ${workflowCard(4, 'Negative test', 'Invalid output must be rejected by the shield.', workflow.negative, workflow.dry && !workflow.negative)}
          ${workflowCard(5, 'Activate', 'Create a revision and apply through ROS, Sionna, and Isaac.', workflow.active, workflow.negative && !workflow.active)}
          ${workflowCard(6, 'Compare and export', 'Paired seeds, runtime cost, fallback rate, and evidence.', Boolean(comparison || lastExport), workflow.active)}
        </div>
        <div class="button-stack" style="margin-top:14px">
          <button class="button secondary" id="algorithm-validate">Validate Package</button>
          <button class="button secondary" id="algorithm-dry">Run Deterministic Dry Run</button>
          <button class="button secondary" id="algorithm-negative">Run Invalid-Output Test</button>
          <button class="button primary" id="algorithm-activate">${active ? 'Reapply Active Algorithm' : 'Activate and Synchronize'}</button>
          <button class="button secondary" id="algorithm-compare">Compare with Chain Baseline</button>
          <button class="button ghost" id="algorithm-deactivate">Deactivate Algorithm</button>
        </div>
      </aside>
    </div>

    <div class="grid two" style="margin-top:16px">
      <section class="card">
        <div class="card-header"><div><h2>${escapeHtml(manifest.name)}</h2><p class="card-description">${escapeHtml(manifest.description || '')}</p></div>${active ? statusChip('ACTIVE', 'ready') : statusChip('INACTIVE', 'neutral')}</div>
        <div class="kpi-grid compact">
          <div><span>Source hash</span><strong class="mono">${escapeHtml((sourceHash || manifest.source_hash || '—').slice(0, 16))}</strong></div>
          <div><span>Fidelity</span><strong>${escapeHtml((manifest.supported_fidelity_profiles || []).join(', ') || '—')}</strong></div>
          <div><span>Deadline</span><strong>${escapeHtml(formatDuration(manifest.resource_budget?.timeout_s || 0))}</strong></div>
          <div><span>Fallback</span><strong>${escapeHtml(manifest.safety_fallback || 'hold_position')}</strong></div>
        </div>
        <h3 style="margin-top:16px">Assumptions and validity</h3>
        <ul class="compact-list">${(manifest.assumptions || []).map(item => `<li>${escapeHtml(item)}</li>`).join('') || '<li>No assumptions declared.</li>'}</ul>
        <div class="callout info"><div class="callout-title">Validity domain</div><div>${escapeHtml(manifest.validity_domain || 'Not declared')}</div></div>
        ${(manifest.citations || []).length ? `<h3 style="margin-top:16px">Scientific basis</h3><div class="stack-list">${manifest.citations.map(citation => `<div class="list-row"><div><strong>${escapeHtml(citation.title || 'Untitled source')}</strong><div class="small-text muted">${escapeHtml(citation.authors || '')} ${citation.year ? `(${escapeHtml(citation.year)})` : ''}</div></div><span class="mono small-text">${escapeHtml(citation.doi || citation.arxiv || citation.venue || '')}</span></div>`).join('')}</div>` : ''}
      </section>
      <section class="card">
        <div class="card-header"><div><h2>Parameters</h2><p class="card-description">Generated directly from the manifest JSON Schema. Values become part of the experiment revision and evidence.</p></div><button class="button ghost small" id="algorithm-reset-params">Reset Defaults</button></div>
        <div class="form-grid">${Object.entries(parameterProperties).map(([name, schema]) => parameterControl(name, schema, parameters[name])).join('') || '<div class="empty-state"><div><strong>No configurable parameters</strong></div></div>'}</div>
      </section>
    </div>

    <section class="card" style="margin-top:16px">
      <div class="card-header"><div><h2>Algorithm source</h2><p class="card-description">Researcher source is executed outside Mission Control with timeout, memory, output, and network policy enforcement. Saving source never activates it automatically.</p></div><div><button class="button secondary" id="algorithm-save-source" ${sourceDirty ? '' : 'disabled'}>Save and Revalidate Source</button></div></div>
      <textarea class="source-editor" id="algorithm-source" spellcheck="false" aria-label="Algorithm source code">${escapeHtml(source)}</textarea>
    </section>

    <div class="grid two" style="margin-top:16px">
      <section class="card"><div class="card-header"><div><h2>Validation and dry-run evidence</h2><p class="card-description">The dry run uses a typed snapshot and the same Safety and Feasibility Shield used by live execution.</p></div></div>
        ${validation ? `<h3>Package validation</h3>${prettyJson(validation)}` : '<div class="empty-state"><div><strong>Validation not run</strong><div class="small-text">Run package validation before activation.</div></div></div>'}
        ${dryRun ? `<h3 style="margin-top:16px">Dry run</h3>${prettyJson({ok:dryRun.ok,run_id:dryRun.run_id,invocation:dryRun.invocation,shield:dryRun.shield})}` : ''}
        ${negativeTest ? `<h3 style="margin-top:16px">Invalid-output rejection</h3>${prettyJson({passed:negativeTest.negative_test_passed,shield:negativeTest.shield,error:negativeTest.error})}` : ''}
      </section>
      <section class="card"><div class="card-header"><div><h2>Paired comparison and exports</h2><p class="card-description">Algorithms are compared using the same scenario revision, fidelity profile, and seed set.</p></div></div>
        ${comparison ? prettyJson(comparison) : '<div class="empty-state"><div><strong>No comparison results</strong><div class="small-text">Activate or dry-run the algorithm, then compare it against researcher_chain_spacing.</div></div></div>'}
        ${runs.length ? `<h3 style="margin-top:16px">Recent algorithm runs</h3><div class="table-wrap"><table><thead><tr><th>Run</th><th>Mode</th><th>Result</th><th>Evidence</th></tr></thead><tbody>${runs.slice(0,8).map(run => `<tr><td class="mono">${escapeHtml(run.run_id)}</td><td>${escapeHtml(run.result?.mode || 'comparison')}</td><td>${run.result?.ok ? statusChip('PASS','ready') : statusChip('REJECTED/FAILED','warning')}</td><td><button class="button ghost small" data-export-run="${escapeHtml(run.run_id)}">Export</button></td></tr>`).join('')}</tbody></table></div>` : ''}
        ${lastExport ? `<div class="callout success" style="margin-top:12px"><div class="callout-title">Evidence bundle created</div><div class="mono small-text">${escapeHtml(lastExport.path)} · ${escapeHtml(lastExport.sha256)}</div></div>` : ''}
      </section>
    </div>

    <section class="card" style="margin-top:16px"><div class="card-header"><div><h2>Advanced manifest inspector</h2><p class="card-description">Complete machine-readable package contract.</p></div></div>${prettyJson(packageInfo)}</section>`;

    root.querySelectorAll('[data-algorithm]').forEach(button => button.addEventListener('click', async () => {
      selectedId = button.dataset.algorithm;
      validation = null; dryRun = null; negativeTest = null; comparison = null; lastExport = null;
      await loadSelected(); render();
    }));
    root.querySelectorAll('[data-param]').forEach(input => input.addEventListener('change', () => {
      try { parameters = collectParameters(root, manifest); } catch (error) { toast(error.message, 'error'); }
    }));
    root.querySelector('#algorithm-source')?.addEventListener('input', event => { source = event.target.value; sourceDirty = true; root.querySelector('#algorithm-save-source').disabled = false; });
    root.querySelector('#algorithm-reset-params')?.addEventListener('click', () => { parameters = defaultParameters(manifest); render(); });
    root.querySelector('#algorithm-refresh')?.addEventListener('click', async event => {
      setBusy(event.currentTarget, true, 'Refreshing…');
      try { registry = await api.algorithms(); algorithms = registry.algorithms || []; await loadSelected(); toast('Algorithm registry refreshed.', 'success'); render(); } catch (error) { toast(error.message, 'error'); } finally { setBusy(event.currentTarget, false); }
    });
    root.querySelector('#algorithm-create')?.addEventListener('click', createProject);
    root.querySelector('#algorithm-save-source')?.addEventListener('click', async event => {
      setBusy(event.currentTarget, true, 'Saving…');
      try { const response = await api.saveAlgorithmSource(selectedId, source); sourceHash = response.source_hash; sourceDirty = false; registry = await api.algorithms(); algorithms = registry.algorithms || []; validation = response; toast('Source saved and package revalidated.', 'success'); render(); } catch (error) { toast(error.message, 'error', 8000); } finally { setBusy(event.currentTarget, false); }
    });
    root.querySelector('#algorithm-validate')?.addEventListener('click', async event => {
      setBusy(event.currentTarget, true, 'Validating…');
      try { parameters = collectParameters(root, manifest); validation = await api.validateAlgorithm(selectedId); toast('Algorithm package validation completed.', validation.ok ? 'success' : 'error'); render(); } catch (error) { toast(error.message, 'error'); } finally { setBusy(event.currentTarget, false); }
    });
    root.querySelector('#algorithm-dry')?.addEventListener('click', async event => {
      setBusy(event.currentTarget, true, 'Executing isolated dry run…');
      try { parameters = collectParameters(root, manifest); dryRun = await api.dryRunAlgorithm(selectedId, parameters, false); runs = (await api.algorithmRuns()).runs || []; toast(dryRun.shield?.accepted ? 'Dry run accepted by the safety and feasibility shield.' : 'Dry run completed with a safe rejection or fallback.', dryRun.shield?.accepted ? 'success' : 'warning', 8000); render(); } catch (error) { dryRun = error.payload || {error:error.message}; toast(error.message, 'error', 8000); render(); } finally { setBusy(event.currentTarget, false); }
    });
    root.querySelector('#algorithm-negative')?.addEventListener('click', async event => {
      setBusy(event.currentTarget, true, 'Testing rejection…');
      try { parameters = collectParameters(root, manifest); negativeTest = await api.dryRunAlgorithm(selectedId, parameters, true); runs = (await api.algorithmRuns()).runs || []; toast(negativeTest.negative_test_passed ? 'Invalid algorithm output was rejected as required.' : 'Negative test did not produce the expected rejection.', negativeTest.negative_test_passed ? 'success' : 'error', 8000); render(); } catch (error) { negativeTest = error.payload || {error:error.message}; toast(error.message, 'error'); render(); } finally { setBusy(event.currentTarget, false); }
    });
    root.querySelector('#algorithm-activate')?.addEventListener('click', async event => {
      setBusy(event.currentTarget, true, 'Creating revision…');
      try { parameters = collectParameters(root, manifest); const response = await api.activateAlgorithm(selectedId, parameters, true); selection = response.activation?.selection || selection; config.algorithm = {algorithm_id:selectedId,parameters}; toast(response.committed ? 'Algorithm committed across ROS 2, Sionna, and Isaac.' : 'Algorithm selected; runtime revision remains pending until all participants acknowledge it.', response.committed ? 'success' : 'warning', 10000); render(); } catch (error) { toast(error.message, 'error', 10000); } finally { setBusy(event.currentTarget, false); }
    });
    root.querySelector('#algorithm-deactivate')?.addEventListener('click', async event => {
      setBusy(event.currentTarget, true, 'Deactivating…');
      try { await api.deactivateAlgorithm(true); selection = {}; toast('Research algorithm deactivated; conservative hold-position control selected.', 'success'); render(); } catch (error) { toast(error.message, 'error'); } finally { setBusy(event.currentTarget, false); }
    });
    root.querySelector('#algorithm-compare')?.addEventListener('click', async event => {
      setBusy(event.currentTarget, true, 'Running paired comparison…');
      try { parameters = collectParameters(root, manifest); const ids = [...new Set([selectedId, 'researcher_chain_spacing'])]; comparison = await api.compareAlgorithms(ids, {[selectedId]:parameters}, 5); runs = (await api.algorithmRuns()).runs || []; toast('Paired comparison completed using identical seeds.', 'success'); render(); } catch (error) { toast(error.message, 'error', 8000); } finally { setBusy(event.currentTarget, false); }
    });
    root.querySelectorAll('[data-export-run]').forEach(button => button.addEventListener('click', async event => {
      setBusy(event.currentTarget, true, 'Exporting…');
      try { lastExport = await api.exportAlgorithmRun(event.currentTarget.dataset.exportRun); toast('Algorithm evidence bundle exported.', 'success'); render(); } catch (error) { toast(error.message, 'error'); } finally { setBusy(event.currentTarget, false); }
    }));
  };

  async function createProject() {
    const algorithmId = prompt('Algorithm ID (lower_snake_case)', 'my_swarm_controller');
    if (!algorithmId) return;
    const name = prompt('Display name', algorithmId.replaceAll('_', ' ')) || algorithmId;
    try {
      const response = await api.createAlgorithm(algorithmId, name, 'controller');
      registry = await api.algorithms(); algorithms = registry.algorithms || [];
      selectedId = response.algorithm?.manifest?.algorithm_id || algorithmId;
      await loadSelected();
      toast('Research algorithm project created. Edit only step(snapshot, parameters), then validate and dry-run.', 'success', 8000);
      render();
    } catch (error) {
      toast(error.message, 'error', 8000);
    }
  }

  render();
}
