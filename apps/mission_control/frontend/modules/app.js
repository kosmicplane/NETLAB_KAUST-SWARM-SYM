import { api } from './api.js';
import { preferences } from './storage.js';
import { escapeHtml, sourceBadge, statusChip, toast } from './components.js';
import { state } from './state.js';
import { renderOverview } from './overview.js';
import { renderGuidedDemo } from './guided_demo.js';
import { renderMissionDesigner } from './mission_designer.js';
import { renderExperimentManager } from './experiment_manager.js';
import { renderSwarmControl } from './swarm_control.js';
import { renderTopologyStudio } from './topology_studio.js';
import { renderAntennaLab } from './antenna_lab.js';
import { renderWorldLab } from './world_lab.js';
import { renderAlgorithmLab } from './algorithm_lab.js';
import { renderResearchTools } from './research_tools.js';
import { renderTrafficServices } from './traffic_services.js';
import { renderFaultRecovery } from './fault_recovery.js';
import { renderLiveTelemetry } from './live_telemetry.js';
import { renderSynchronization } from './synchronization.js';
import { renderEvidence } from './evidence.js';
import { renderDiagnostics } from './diagnostics.js';
import { renderSettings } from './settings.js';

// Machine-readable page inventory retained for build, release, and button
// contract tests. Every identifier maps to modules/<identifier>.js.
export const pageManifest = [
  ['overview','Overview'],
  ['guided_demo','Guided Demo'],
  ['mission_designer','Mission Designer'],
  ['experiment_manager','Experiment Manager'],
  ['swarm_control','Swarm Control'],
  ['topology_studio','Topology Studio'],
  ['antenna_lab','Antenna Lab'],
  ['world_lab','World Lab'],
  ['algorithm_lab','Algorithm Lab'],
  ['research_tools','Research Tools'],
  ['traffic_services','Traffic & Services'],
  ['fault_recovery','Fault & Recovery'],
  ['live_telemetry','Live Telemetry'],
  ['synchronization','Synchronization'],
  ['evidence','Evidence'],
  ['diagnostics','Diagnostics'],
  ['settings','Settings'],
];

const navigation = [
  { section: 'Operations', items: [
    ['overview', 'Overview', '◫'],
    ['guided-demo', 'Guided Demo', '▷'],
    ['mission', 'Mission Designer', '✦'],
    ['experiments', 'Experiment Manager', '▦'],
  ]},
  { section: 'Simulation', items: [
    ['swarm', 'Swarm Control', '⌁'],
    ['topology', 'Topology Studio', '⌘'],
    ['antenna', 'Antenna Lab', '⌁'],
    ['world', 'World Lab', '▧'],
    ['algorithm', 'Algorithm Lab', 'ƒ'],
    ['research', 'Research Tools', '∑'],
  ]},
  { section: 'Network', items: [
    ['traffic', 'Traffic & Services', '⇄'],
    ['fault', 'Fault & Recovery', '⚠'],
    ['telemetry', 'Live Telemetry', '⌗'],
    ['synchronization', 'Synchronization', '↻'],
  ]},
  { section: 'Assurance', items: [
    ['evidence', 'Evidence', '☷'],
    ['diagnostics', 'Diagnostics', '✚'],
    ['settings', 'Settings', '⚙'],
  ]},
];

const renderers = {
  overview: renderOverview,
  'guided-demo': renderGuidedDemo,
  mission: renderMissionDesigner,
  experiments: renderExperimentManager,
  swarm: renderSwarmControl,
  topology: renderTopologyStudio,
  antenna: renderAntennaLab,
  world: renderWorldLab,
  algorithm: renderAlgorithmLab,
  research: renderResearchTools,
  traffic: renderTrafficServices,
  fault: renderFaultRecovery,
  telemetry: renderLiveTelemetry,
  synchronization: renderSynchronization,
  evidence: renderEvidence,
  diagnostics: renderDiagnostics,
  settings: renderSettings,
};

const viewRoot = document.getElementById('view-root');
const navRoot = document.getElementById('primary-nav');
const sidebar = document.getElementById('sidebar');
const drawer = document.getElementById('command-drawer');
let rendering = false;
let refreshTimer = null;

function renderNavigation() {
  navRoot.innerHTML = navigation.map(group => `<div class="nav-section">${escapeHtml(group.section)}</div>${group.items.map(([id,label,icon]) => `<button class="nav-item ${state.currentView===id?'active':''}" data-view="${id}" type="button"><span class="nav-icon">${icon}</span><span>${escapeHtml(label)}</span></button>`).join('')}`).join('');
  navRoot.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => {
    state.navigate(button.dataset.view);
    sidebar.classList.remove('open');
  }));
}

async function renderCurrentView() {
  if (rendering) return;
  rendering = true;
  renderNavigation();
  const label = navigation.flatMap(group => group.items).find(item => item[0] === state.currentView)?.[1] || 'view';
  viewRoot.innerHTML = `<div class="card"><div class="empty-state"><div><strong>Loading ${escapeHtml(label)}…</strong></div></div></div>`;
  try {
    const renderer = renderers[state.currentView] || renderOverview;
    await renderer(viewRoot);
    document.getElementById('main-content').focus({ preventScroll: true });
  } catch (error) {
    viewRoot.innerHTML = `<div class="callout error"><div class="callout-title">The view could not be rendered</div><div>${escapeHtml(error.message)}</div><div class="small-text" style="margin-top:7px">Open Diagnostics for service and API details.</div></div>`;
    window.__NETLAB_FRONTEND_FAILURE__?.(error);
    console.error(error);
  } finally {
    rendering = false;
  }
}

function updateGlobalStatus(readinessPayload, telemetry, health) {
  // The authoritative API returns current observations through readiness?.readiness when wrapped, or readiness directly.
  // No view derives ROS or Isaac readiness from container liveness alone.
  const readinessEnvelope = readinessPayload?.readiness;
  const readiness = readinessEnvelope?.readiness || readinessEnvelope || readinessPayload?.state?.readiness || {};
  const source = telemetry?.source?.source || telemetry?.source || readinessPayload?.state?.telemetry_source || 'OFFLINE';
  const chips = [
    ['Sionna', readiness.sionna_ready],
    ['ROS 2', readiness.ros_graph_ready],
    ['Packet', readiness.packet_runtime_ready],
    ['Isaac', readiness.isaac_scene_ready],
    ['Sync', readiness.synchronized || readiness.isaac_scenario_acknowledged],
  ];
  document.getElementById('global-status').innerHTML = chips.map(([label, ready]) => statusChip(`${label} ${ready ? 'ready' : 'waiting'}`, ready ? 'ready' : 'warning')).join('') + sourceBadge(source);
  const badge = document.getElementById('sidebar-source');
  badge.className = `source-badge ${String(source).toLowerCase()}`;
  badge.textContent = String(source).toUpperCase();
  document.getElementById('sidebar-version').textContent = health ? `NETLAB ${health.version} · API ${health.api_version}` : 'NETLAB';
}

function renderJobs(jobs = []) {
  document.getElementById('activity-count').textContent = jobs.filter(job => ['QUEUED','RUNNING','FAILED'].includes(job.status)).length;
  document.getElementById('command-list').innerHTML = jobs.length ? jobs.map(job => `<div class="command-item"><div class="row space-between"><strong>${escapeHtml(job.name)}</strong><span class="status-chip ${job.status==='COMPLETED'?'ready':job.status==='FAILED'?'error':'warning'}">${escapeHtml(job.status)}</span></div><div class="small-text muted" style="margin-top:5px">${escapeHtml(job.job_id)} · ${(job.progress || []).length} progress stages</div>${job.error ? `<div class="callout error" style="margin-top:8px"><div>${escapeHtml(job.error.message || String(job.error))}</div></div>` : ''}</div>`).join('') : '<div class="empty-state"><div><strong>No command jobs</strong><div class="small-text">Long-running actions appear here.</div></div></div>';
}

async function refreshGlobal() {
  try {
    const [health, readiness, telemetry, jobs] = await Promise.all([
      api.health(), api.readiness(), api.telemetry(), api.jobs(),
    ]);
    state.patch({ health, readiness, telemetry, jobs: jobs.jobs || [] });
    updateGlobalStatus(readiness, telemetry, health);
    renderJobs(jobs.jobs || []);
  } catch (error) {
    updateGlobalStatus(null, { source: 'OFFLINE' }, state.health);
    console.warn('Global refresh failed:', error);
  }
}

function installHandlers() {
  document.addEventListener('netlab:job', event => {
    const job = event.detail;
    state.jobs = [job, ...state.jobs.filter(item => item.job_id !== job.job_id)];
    renderJobs(state.jobs);
    drawer.classList.add('open');
  });
  state.addEventListener('navigate', event => {
    state.currentView = event.detail;
    location.hash = event.detail;
    renderCurrentView();
  });
  window.addEventListener('hashchange', () => {
    const view = location.hash.replace(/^#\/?/, '');
    if (view && renderers[view] && view !== state.currentView) {
      state.currentView = view;
      renderCurrentView();
    }
  });
  document.getElementById('nav-toggle').addEventListener('click', () => sidebar.classList.toggle('open'));
  document.getElementById('command-drawer-open').addEventListener('click', () => drawer.classList.add('open'));
  document.getElementById('command-drawer-close').addEventListener('click', () => drawer.classList.remove('open'));
  document.getElementById('refresh-all').addEventListener('click', async () => {
    await refreshGlobal();
    await renderCurrentView();
    toast('Mission Control state refreshed.', 'success');
  });
  document.getElementById('start-stack-global').addEventListener('click', async event => {
    event.currentTarget.disabled = true;
    try {
      const response = await api.command('start_stack', { build: true });
      document.dispatchEvent(new CustomEvent('netlab:job', { detail: response.job }));
      toast('Start Stack accepted. Readiness stages are visible in Command Activity.', 'success', 8000);
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      event.currentTarget.disabled = false;
    }
  });
  document.getElementById('theme-toggle').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    preferences.set('netlab.theme', next);
    document.getElementById('theme-toggle').textContent = next === 'dark' ? 'Light theme' : 'Dark theme';
  });
}

async function bootstrap() {
  const initialTheme = preferences.get('netlab.theme') || 'light';
  document.documentElement.dataset.theme = initialTheme;
  document.getElementById('theme-toggle').textContent = initialTheme === 'dark' ? 'Light theme' : 'Dark theme';
  const hashView = location.hash.replace(/^#\/?/, '');
  if (hashView && renderers[hashView]) state.currentView = hashView;
  installHandlers();
  renderNavigation();
  await renderCurrentView();
  await refreshGlobal();
  refreshTimer = window.setInterval(refreshGlobal, Math.max(1000, Number(preferences.get('netlab.refreshMs') || 2000)));
  window.__NETLAB_APP_READY__ = true;
  window.dispatchEvent(new CustomEvent('netlab:ready'));
}

bootstrap().catch(error => {
  window.__NETLAB_FRONTEND_FAILURE__?.(error);
  console.error('NETLAB frontend bootstrap failed:', error);
});
