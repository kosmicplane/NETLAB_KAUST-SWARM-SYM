import { api } from './api.js';
import { preferences } from './storage.js';
import { downloadJson, escapeHtml, field, getByPath, prettyJson, setByPath, toast, viewHeader } from './components.js';
import { state } from './state.js';

const sections = [
  {
    title: 'Experiment identity', level: 'basic', fields: [
      ['experiment.id', 'Scenario ID', 'text', '', '', '', '', 'Stable identifier used in evidence manifests.'],
      ['experiment.name', 'Experiment name', 'text', '', '', '', '', 'Human-readable name.'],
      ['experiment.description', 'Description', 'textarea', '', '', '', 3, 'Purpose, hypotheses, and expected behavior.'],
      ['experiment.author', 'Author', 'text', '', '', '', '', 'Researcher or team.'],
      ['experiment.seed', 'Deterministic seed', 'number', '', 0, 2147483647, '', 'Controls reproducible stochastic behavior.'],
      ['experiment.duration_s', 'Duration', 'number', 's', 0.1, 86400, 0.1, 'Nominal simulation duration.'],
      ['experiment.replications', 'Replications', 'number', 'runs', 1, 10000, 1, 'Independent repetitions for statistical analysis.'],
      ['experiment.fidelity_profile', 'Fidelity profile', 'select', '', '', '', '', 'Results must state the active fidelity profile.', [
        {value:'F0_PREVIEW',label:'F0 — UI preview'}, {value:'F1_ANALYTICAL',label:'F1 — Analytical'}, {value:'F2_STOCHASTIC',label:'F2 — Stochastic'}, {value:'F3_GEOMETRY_AWARE',label:'F3 — Geometry-aware / ray-traced'}, {value:'F4_AUTOPILOT',label:'F4 — Autopilot-integrated'}, {value:'F5_HARDWARE_ASSISTED',label:'F5 — Hardware-assisted'}
      ]],
    ]
  },
  {
    title: 'World and coordinate system', level: 'basic', fields: [
      ['world.template', 'World template', 'text', '', '', '', '', 'Built-in template or research scenario name.'],
      ['world.coordinate_frame', 'Coordinate frame', 'select', '', '', '', '', 'Frame conversion is explicit at subsystem boundaries.', ['ENU','NED','ECEF','WGS84','ISAAC_STAGE']],
      ['world.stage_units_m', 'Isaac stage unit', 'number', 'm/unit', 0.0001, 1000, 0.001, 'Physical scale of one stage unit.'],
      ['world.origin', 'Local origin', 'json', 'm', '', '', 3, 'Three-element origin vector.'],
      ['world.environment.wind_speed_mps', 'Wind speed', 'number', 'm/s', 0, 100, 0.1, 'Uniform reference wind speed.'],
      ['world.environment.wind_direction_deg', 'Wind direction', 'number', 'deg', -360, 360, 1, 'Direction in the configured frame.'],
      ['world.environment.turbulence_intensity', 'Turbulence intensity', 'number', 'ratio', 0, 2, 0.01, 'Dimensionless abstraction; document validity.'],
      ['world.environment.temperature_c', 'Temperature', 'number', '°C', -80, 80, 0.1, 'Environmental metadata and future model input.'],
      ['world.environment.humidity_pct', 'Relative humidity', 'number', '%', 0, 100, 0.1, 'Environmental metadata and future atmospheric model input.'],
      ['world.environment.rain_rate_mm_h', 'Rain rate', 'number', 'mm/h', 0, 500, 0.1, 'Used only by compatible attenuation models.'],
      ['world.environment.fog_visibility_m', 'Fog visibility', 'number', 'm', 1, 100000, 1, 'Visual/environmental configuration.'],
    ]
  },
  {
    title: 'Service region and geofence', level: 'basic', fields: [
      ['service_region.shape', 'Region shape', 'select', '', '', '', '', 'Operational region geometry.', ['rectangle','circle','polygon']],
      ['service_region.center', 'Region center', 'json', 'm', '', '', 3, 'Center coordinate.'],
      ['service_region.length_m', 'Length', 'number', 'm', 1, 100000, 0.1, 'Longitudinal dimension.'],
      ['service_region.width_m', 'Width', 'number', 'm', 1, 100000, 0.1, 'Lateral dimension.'],
      ['service_region.min_altitude_m', 'Minimum altitude', 'number', 'm', -1000, 100000, 0.1, 'Lower operational bound.'],
      ['service_region.max_altitude_m', 'Maximum altitude', 'number', 'm', -1000, 100000, 0.1, 'Upper operational bound.'],
      ['service_region.geofence_enabled', 'Enable geofence', 'checkbox', '', '', '', '', 'Reject commands outside the service region.'],
    ]
  },
  {
    title: 'UAV fleet and physical constraints', level: 'basic', fields: [
      ['swarm.drone_count', 'Total UAV count', 'number', 'UAVs', 1, 10000, 1, 'Active and standby inventory.'],
      ['swarm.relay_count', 'Active relay count', 'number', 'UAVs', 1, 10000, 1, 'UAVs eligible for active relay routes.'],
      ['swarm.standby_count', 'Standby count', 'number', 'UAVs', 0, 10000, 1, 'Reserve UAVs available to recovery policies.'],
      ['swarm.visual_asset_scale', 'Visual asset scale', 'number', 'scale', 0.001, 100, 0.001, 'Rendering scale only; default is 0.2 and is distinct from physical dimensions.'],
      ['swarm.physical_collision_dimensions_m', 'Collision dimensions', 'json', 'm', '', '', 3, 'Physical collision-box dimensions [x,y,z].'],
      ['swarm.reference_dimensions_m', 'Reference dimensions', 'json', 'm', '', '', 3, 'Aerodynamic/reference dimensions [x,y,z].'],
      ['swarm.mass_kg', 'Vehicle mass', 'number', 'kg', 0.01, 10000, 0.01, 'Mass used by supported dynamic and energy models.'],
      ['swarm.payload_mass_kg', 'Payload mass', 'number', 'kg', 0, 10000, 0.01, 'Additional payload mass.'],
      ['swarm.minimum_separation_m', 'Minimum separation', 'number', 'm', 0, 10000, 0.1, 'Collision and formation constraint.'],
      ['swarm.max_horizontal_speed_mps', 'Maximum horizontal speed', 'number', 'm/s', 0.01, 500, 0.1, 'Controller command limit.'],
      ['swarm.max_vertical_speed_mps', 'Maximum vertical speed', 'number', 'm/s', 0.01, 200, 0.1, 'Vertical controller command limit.'],
      ['swarm.max_acceleration_mps2', 'Maximum acceleration', 'number', 'm/s²', 0.01, 200, 0.1, 'Trajectory feasibility constraint.'],
      ['swarm.max_deceleration_mps2', 'Maximum deceleration', 'number', 'm/s²', 0.01, 200, 0.1, 'Braking constraint.'],
      ['swarm.max_jerk_mps3', 'Maximum jerk', 'number', 'm/s³', 0.01, 1000, 0.1, 'Trajectory smoothness constraint.'],
      ['swarm.max_yaw_rate_deg_s', 'Maximum yaw rate', 'number', 'deg/s', 0.01, 1000, 0.1, 'Attitude command limit.'],
      ['swarm.max_climb_rate_mps', 'Maximum climb rate', 'number', 'm/s', 0.01, 200, 0.1, 'Ascent limit.'],
      ['swarm.max_descent_rate_mps', 'Maximum descent rate', 'number', 'm/s', 0.01, 200, 0.1, 'Descent limit.'],
    ]
  },
  {
    title: 'Mobility and control', level: 'advanced', fields: [
      ['swarm.controller.type', 'Controller type', 'select', '', '', '', '', 'Built-in controller or plugin adapter.', ['communication_aware_formation','waypoint','external_ros2','plugin','hold_position']],
      ['swarm.controller.plugin_id', 'Controller plugin ID', 'text', '', '', '', '', 'Required when controller type is plugin.'],
      ['swarm.controller.update_rate_hz', 'Controller update rate', 'number', 'Hz', 0.01, 1000, 0.1, 'Command generation frequency.'],
      ['swarm.controller.command_timeout_s', 'Command timeout', 'number', 's', 0.01, 120, 0.01, 'Fallback threshold for stale commands.'],
      ['swarm.controller.collision_avoidance', 'Enable collision avoidance', 'checkbox', '', '', '', '', 'Apply supported separation policy.'],
      ['swarm.controller.safe_fallback', 'Safe fallback', 'select', '', '', '', '', 'Action after plugin timeout or invalid command.', ['hold_position','safe_land','return_home']],
      ['swarm.mobility.model', 'Mobility model', 'select', '', '', '', '', 'Nominal desired-motion policy.', ['hold','waypoint','linear','spline','orbit','grid','chain','parallel','forest','manual','formation','plugin']],
      ['swarm.mobility.formation', 'Formation', 'text', '', '', '', '', 'Formation preset or plugin-defined name.'],
      ['swarm.mobility.waypoint_smoothing', 'Enable waypoint smoothing', 'checkbox', '', '', '', '', 'Generate continuous bounded trajectories.'],
      ['swarm.mobility.wind_response', 'Enable wind response', 'checkbox', '', '', '', '', 'Allow compatible dynamics to respond to wind.'],
      ['clock.physics_step_s', 'Physics step', 'number', 's', 0.0001, 1, 0.0001, 'Embodied simulation integration step.'],
      ['clock.control_step_s', 'Control step', 'number', 's', 0.0001, 10, 0.0001, 'Controller update interval.'],
      ['clock.link_update_period_s', 'Link update period', 'number', 's', 0.01, 60, 0.01, 'Frequency of communication feasibility evaluation.'],
      ['clock.mode', 'Clock synchronization mode', 'select', '', '', '', '', 'Master simulation-clock behavior.', ['REAL_TIME','LOCKSTEP','FIXED_STEP','BEST_EFFORT','REPLAY']],
    ]
  },
  {
    title: 'Relay topology', level: 'basic', fields: [
      ['topology.mode', 'Topology mode', 'select', '', '', '', '', 'Chain, parallel branch, forest, or operator-defined graph.', ['chain','parallel','forest','manual']],
      ['topology.source', 'Source entity', 'text', '', '', '', '', 'Flow source node ID.'],
      ['topology.sinks', 'Sink entities', 'json', '', '', '', 3, 'Array of destination node IDs.'],
      ['topology.branches', 'Ordered relay branches', 'json', '', '', '', 3, 'Array of relay-index arrays. Topology Studio provides direct editing.'],
      ['topology.manual_edges', 'Manual directed edges', 'json', '', '', '', 3, 'Array of [source,destination] pairs for manual topology.'],
      ['topology.routing_policy', 'Routing policy', 'select', '', '', '', '', 'Route-selection method.', ['ordered_path','shortest_feasible','maximum_bottleneck','energy_aware','plugin']],
      ['topology.forwarding_policy', 'Forwarding policy', 'select', '', '', '', '', 'Packet forwarding behavior.', ['store_and_forward','cut_through','scheduled']],
      ['topology.queue_model', 'Queue model', 'select', '', '', '', '', 'Queue abstraction used at relay nodes.', ['fifo','priority','per_flow','bounded_fifo','plugin']],
      ['topology.recompute_on_failure', 'Recompute on failure', 'checkbox', '', '', '', '', 'Remove failed endpoints and search for a feasible replacement route.'],
      ['topology.redundancy_target', 'Redundancy target', 'number', 'paths', 1, 100, 1, 'Target number of alternate routes where supported.'],
      ['topology.update_period_s', 'Topology update period', 'number', 's', 0.01, 3600, 0.01, 'Re-evaluation interval.'],
    ]
  },
  {
    title: 'Communication and execution gate', level: 'basic', fields: [
      ['communication.model', 'Propagation model', 'select', '', '', '', '', 'Model label and validity are recorded with every result.', ['free_space','log_distance','probabilistic_air_to_ground','stochastic_shadowing','sionna_analytical','sionna_rt','trace_replay','plugin']],
      ['communication.carrier_frequency_hz', 'Carrier frequency', 'number', 'Hz', 1e6, 3e11, 1, 'Center frequency in SI units.'],
      ['communication.bandwidth_hz', 'Channel bandwidth', 'number', 'Hz', 1, 1e10, 1, 'Noise and capacity model input.'],
      ['communication.tx_power_dbm', 'Transmit power', 'number', 'dBm', -200, 200, 0.1, 'Power at the transmitter chain boundary.'],
      ['communication.receiver_noise_figure_db', 'Receiver noise figure', 'number', 'dB', 0, 100, 0.1, 'Receiver implementation noise.'],
      ['communication.implementation_loss_db', 'Implementation loss', 'number', 'dB', 0, 100, 0.1, 'Additional non-propagation link loss.'],
      ['communication.operational_range_m', 'Operational range', 'number', 'm', 0.1, 1e7, 0.1, 'Hard execution-gate predicate.'],
      ['communication.hard_outage_distance_m', 'Hard-outage distance', 'number', 'm', 0.1, 1e8, 0.1, 'Absolute safety cap; must be at least operational range.'],
      ['communication.min_snr_db', 'Minimum SNR', 'number', 'dB', -200, 200, 0.1, 'Execution-gate threshold.'],
      ['communication.min_sinr_db', 'Minimum SINR', 'number', 'dB', -200, 200, 0.1, 'Used when interference is enabled.'],
      ['communication.min_capacity_mbps', 'Minimum capacity', 'number', 'Mbps', 0, 1e9, 0.01, 'Execution-gate threshold.'],
      ['communication.spectral_efficiency_factor', 'Efficiency factor', 'number', 'ratio', 0, 1, 0.01, 'Explicit reduction from Shannon upper bound.'],
      ['communication.metric_ttl_s', 'Link metric TTL', 'number', 's', 0.01, 3600, 0.01, 'Stale metrics cannot authorize packet advancement.'],
      ['communication.path_loss_exponent', 'Path-loss exponent', 'number', '', 1, 8, 0.01, 'Used only by compatible analytical models.'],
      ['communication.shadowing_sigma_db', 'Shadowing sigma', 'number', 'dB', 0, 100, 0.1, 'Stochastic log-normal shadowing.'],
      ['communication.rain_enabled', 'Enable rain attenuation', 'checkbox', '', '', '', '', 'Requires a compatible model and valid frequency/rain-rate domain.'],
      ['communication.foliage_enabled', 'Enable foliage attenuation', 'checkbox', '', '', '', '', 'Requires material/environment parameters.'],
      ['communication.clutter_enabled', 'Enable clutter attenuation', 'checkbox', '', '', '', '', 'Do not double-count with selected base model.'],
      ['communication.interference_enabled', 'Enable interference abstraction', 'checkbox', '', '', '', '', 'Switch gate evaluation from SNR to SINR where supported.'],
      ['communication.interference_margin_db', 'Interference margin', 'number', 'dB', 0, 100, 0.1, 'Analytical interference abstraction.'],
      ['communication.allow_fallback', 'Allow explicit model fallback', 'checkbox', '', '', '', '', 'Fallback is reported and never silent.'],
      ['communication.fallback_model', 'Fallback model', 'select', '', '', '', '', 'Used only after a recorded primary-model failure.', ['free_space','log_distance','unavailable']],
    ]
  },
  {
    title: 'Energy model', level: 'advanced', fields: [
      ['swarm.energy.model', 'Energy model', 'select', '', '', '', '', 'Select disabled, budget, analytical rotary-wing, or imported measured profile.', ['disabled','simple_power_budget','rotary_wing_analytical','imported_profile']],
      ['swarm.energy.battery_capacity_wh', 'Battery capacity', 'number', 'Wh', 0.01, 100000, 0.1, 'Nominal battery energy.'],
      ['swarm.energy.initial_soc_pct', 'Initial state of charge', 'number', '%', 0, 100, 0.1, 'Initial energy state.'],
      ['swarm.energy.reserve_soc_pct', 'Reserve threshold', 'number', '%', 0, 100, 0.1, 'Safety reserve.'],
      ['swarm.energy.hover_power_w', 'Hover power', 'number', 'W', 0, 100000, 0.1, 'Simplified model parameter.'],
      ['swarm.energy.communication_power_w', 'Communication power', 'number', 'W', 0, 10000, 0.1, 'RF subsystem abstraction.'],
      ['swarm.energy.computing_power_w', 'Computing power', 'number', 'W', 0, 10000, 0.1, 'Onboard computing abstraction.'],
    ]
  },
  {
    title: 'Traffic and service requirements', level: 'advanced', fields: [
      ['traffic.scheduler', 'Scheduler', 'select', '', '', '', '', 'Service scheduling abstraction.', ['round_robin','weighted_round_robin','strict_priority','tdma','plugin']],
      ['traffic.queue_model', 'Default queue model', 'select', '', '', '', '', 'Queue behavior for flows without overrides.', ['fifo','priority','per_flow','bounded_fifo','plugin']],
      ['traffic.flows', 'Traffic flows', 'json', '', '', '', 3, 'Complete flow definitions: source, destination, packet model, rate, class, delay, throughput, reliability, and queue capacity.'],
    ]
  },
  {
    title: 'Failures and recovery', level: 'advanced', fields: [
      ['failures.schedule', 'Failure schedule', 'json', '', '', '', 3, 'Timestamped failure events with type, target, duration, and severity.'],
      ['failures.recovery_policy', 'Recovery policy', 'select', '', '', '', '', 'A route is recovered only after the normal gate passes.', ['none','topology_recomputation','standby_promotion','nearest_feasible_standby','energy_aware_standby','communication_aware_standby','plugin']],
      ['failures.failure_detection_s', 'Failure detection latency', 'number', 's', 0, 3600, 0.01, 'Detection abstraction or measured value.'],
      ['failures.recovery_timeout_s', 'Recovery timeout', 'number', 's', 0.01, 3600, 0.01, 'Maximum recovery attempt duration.'],
      ['failures.retry_limit', 'Recovery retry limit', 'number', 'attempts', 0, 1000, 1, 'Bounded recovery attempts.'],
      ['failures.operator_approval_required', 'Require operator approval', 'checkbox', '', '', '', '', 'Hold candidate recovery until approved.'],
    ]
  },
  {
    title: 'Visualization and evidence', level: 'advanced', fields: [
      ['visualization.custom_drone_usd', 'Drone USD asset', 'text', '', '', '', 3, 'Container path to the visual asset.'],
      ['visualization.visual_asset_scale', 'Drone visual scale', 'number', 'scale', 0.001, 100, 0.001, 'Default 0.2. This does not alter physical dimensions.'],
      ['visualization.show_service_region', 'Show service region', 'checkbox', '', '', '', '', 'Visualization only.'],
      ['visualization.show_link_lines', 'Show link lines', 'checkbox', '', '', '', '', 'Feasible and infeasible links are visually distinct.'],
      ['visualization.show_packet_markers', 'Show packet markers', 'checkbox', '', '', '', '', 'Markers derive from authoritative packet events.'],
      ['visualization.show_coverage_preview', 'Show coverage preview', 'checkbox', '', '', '', '', 'Geometric preview is not RF proof.'],
      ['visualization.coverage_opacity', 'Coverage opacity', 'number', 'ratio', 0, 1, 0.01, 'Rendering parameter.'],
      ['evidence.write_jsonl_events', 'Write JSONL events', 'checkbox', '', '', '', '', 'Append-only structured event evidence.'],
      ['evidence.write_csv_metrics', 'Write CSV metrics', 'checkbox', '', '', '', '', 'Tabular metrics for analysis.'],
      ['evidence.write_run_manifest', 'Write run manifest', 'checkbox', '', '', '', '', 'Preserve hashes, versions, seeds, and environment.'],
      ['evidence.record_rosbag', 'Record rosbag2', 'checkbox', '', '', '', '', 'Requires runtime storage capacity.'],
      ['evidence.capture_screenshots', 'Capture screenshots', 'checkbox', '', '', '', '', 'Visual evidence.'],
      ['evidence.record_video', 'Record video', 'checkbox', '', '', '', '', 'High storage and GPU cost.'],
      ['evidence.retention_policy', 'Retention policy', 'select', '', '', '', '', 'Artifact lifecycle.', ['keep_completed_runs','keep_failures_only','manual','ephemeral']],
    ]
  },
  {
    title: 'Runtime and health policy', level: 'expert', fields: [
      ['runtime.sionna_url', 'Sionna link endpoint', 'text', '', '', '', 2, 'Link-service URL as seen by the runtime.'],
      ['runtime.sionna_health_url', 'Sionna health endpoint', 'text', '', '', '', 2, 'Health/readiness URL.'],
      ['runtime.command_timeout_s', 'Command timeout', 'number', 's', 0.1, 3600, 0.1, 'Generic command acknowledgement timeout.'],
      ['runtime.startup_timeout_s', 'Startup timeout', 'number', 's', 1, 7200, 1, 'Maximum complete-stack startup duration.'],
      ['runtime.isaac_heartbeat_timeout_s', 'Isaac heartbeat timeout', 'number', 's', 0.1, 3600, 0.1, 'Stale scene threshold.'],
      ['runtime.packet_heartbeat_timeout_s', 'Packet heartbeat timeout', 'number', 's', 0.1, 3600, 0.1, 'Stale packet-runtime threshold.'],
      ['runtime.retry_count', 'Runtime retry count', 'number', 'attempts', 0, 100, 1, 'Bounded retry policy.'],
    ]
  },
  {
    title: 'Expert registries', level: 'expert', fields: [
      ['swarm.drones', 'UAV state definitions', 'json', '', '', '', 3, 'Exact initial state, role, antenna assignment, and battery for every UAV.'],
      ['antennas', 'Antenna registry', 'json', '', '', '', 3, 'Definitions and entity assignments. Antenna Lab provides structured editing.'],
      ['world.assets', 'World asset registry', 'json', '', '', '', 3, 'Assets, transforms, semantic categories, collisions, and electromagnetic materials.'],
      ['service_region.restricted_regions', 'Restricted regions', 'json', '', '', '', 3, 'Geofenced exclusions and no-fly zones.'],
    ]
  },
];

function renderField(config, descriptor) {
  const [path, label, kind, unit, min, max, span, help, options] = descriptor;
  const value = getByPath(config, path, kind === 'checkbox' ? false : '');
  if (kind === 'json') {
    return field({ id: path, label, value: JSON.stringify(value, null, 2), type: 'textarea', unit, help, span: span || 1 });
  }
  return field({ id: path, label, value, type: kind === 'select' ? 'text' : kind, unit, min, max, step: kind === 'number' ? 'any' : '', help, span: span || 1, options: kind === 'select' ? options : null, checked: Boolean(value) });
}

function parseField(control, descriptor) {
  const kind = descriptor[2];
  if (kind === 'checkbox') return control.checked;
  if (kind === 'number') return Number(control.value);
  if (kind === 'json') return JSON.parse(control.value || 'null');
  return control.value;
}

export async function renderMissionDesigner(root) {
  const response = await api.config();
  let config = structuredClone(response.config);
  let activeLevel = preferences.get('netlab.mission.level') || 'basic';
  state.patch({ config, configHash: response.hash });

  const render = validation => {
    const levels = ['basic','advanced','expert'];
    const visibleIndex = levels.indexOf(activeLevel);
    root.innerHTML = `${viewHeader('Mission Designer', 'The authoritative experiment editor. Every value is validated, versioned, persisted, synchronized, and included in reproducibility evidence.', `
      <input type="file" id="mission-import" accept="application/json" hidden>
      <button class="button secondary" id="mission-import-button">Import</button>
      <button class="button secondary" id="mission-export">Export</button>
      <button class="button secondary" id="mission-validate">Validate</button>
      <button class="button primary" id="mission-save">Save + Synchronize</button>
    `)}
    <div class="row" style="margin-bottom:16px">
      ${levels.map(level => `<button class="button ${activeLevel === level ? 'primary' : 'secondary'} small" data-level="${level}">${level[0].toUpperCase() + level.slice(1)}</button>`).join('')}
      <span class="muted small-text">Basic shows core experiment inputs. Advanced adds model and evidence controls. Expert exposes runtime and complete registries.</span>
    </div>
    ${validation && !validation.ok ? `<div class="callout error" style="margin-bottom:16px"><div class="callout-title">Configuration contains ${validation.errors.length} validation error(s)</div><div>Correct the highlighted fields before launching the experiment.</div></div>` : validation?.warnings?.length ? `<div class="callout warning" style="margin-bottom:16px"><div class="callout-title">${validation.warnings.length} scientific or configuration warning(s)</div><div>Review model validity and compatibility before publication.</div></div>` : `<div class="callout success" style="margin-bottom:16px"><div class="callout-title">Configuration is structurally valid</div><div>Runtime readiness and scientific validation remain separate acceptance conditions.</div></div>`}
    <form id="mission-form" class="stack">
      ${sections.filter(section => levels.indexOf(section.level) <= visibleIndex).map(section => `<section class="card form-section"><h2 class="form-section-title">${escapeHtml(section.title)}</h2><div class="form-grid">${section.fields.map(descriptor => renderField(config, descriptor)).join('')}</div></section>`).join('')}
    </form>
    <details class="card"><summary><strong>Current schema validation details</strong></summary><div style="margin-top:14px">${prettyJson(validation || response.validation)}</div></details>`;

    const allDescriptors = sections.flatMap(section => section.fields);
    const collect = () => {
      const next = structuredClone(config);
      const parseErrors = [];
      for (const descriptor of allDescriptors) {
        const control = root.querySelector(`[data-field="${CSS.escape(descriptor[0])}"]`);
        if (!control) continue;
        try {
          setByPath(next, descriptor[0], parseField(control, descriptor));
          root.querySelector(`[data-error-for="${CSS.escape(descriptor[0])}"]`).textContent = '';
        } catch (error) {
          parseErrors.push({ path: descriptor[0], message: error.message });
          root.querySelector(`[data-error-for="${CSS.escape(descriptor[0])}"]`).textContent = error.message;
        }
      }
      if (parseErrors.length) throw new Error(`${parseErrors.length} field(s) contain invalid JSON or numeric values.`);
      next.experiment.updated_at = Date.now() / 1000;
      // Keep both visual-scale locations coherent.
      next.visualization.visual_asset_scale = Number(next.swarm.visual_asset_scale);
      return next;
    };

    root.querySelectorAll('[data-level]').forEach(button => button.addEventListener('click', () => {
      try { config = collect(); } catch {}
      activeLevel = button.dataset.level;
      preferences.set('netlab.mission.level', activeLevel);
      render(validation);
    }));
    root.querySelector('#mission-validate').addEventListener('click', async () => {
      try {
        config = collect();
        const result = await api.validateConfig(config);
        render(result);
        toast(result.ok ? 'Configuration validation passed.' : 'Configuration validation found errors.', result.ok ? 'success' : 'warning');
      } catch (error) { toast(error.message, 'error'); }
    });
    root.querySelector('#mission-save').addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        config = collect();
        const result = await api.saveConfig(config, true);
        config = structuredClone(result.config);
        state.patch({ config, configHash: result.config_hash });
        toast(`Configuration saved under revision ${(result.revision?.revision_id || 'pending').slice(0, 12)}…`, result.committed ? 'success' : 'warning', 8000);
        render(result.validation);
      } catch (error) {
        const validationDetails = error.payload?.error?.details;
        toast(error.message, 'error');
        if (validationDetails) render(validationDetails);
      } finally { button.disabled = false; }
    });
    root.querySelector('#mission-export').addEventListener('click', () => {
      try { config = collect(); downloadJson(`${config.experiment.id || 'netlab_experiment'}.json`, config); } catch (error) { toast(error.message, 'error'); }
    });
    root.querySelector('#mission-import-button').addEventListener('click', () => root.querySelector('#mission-import').click());
    root.querySelector('#mission-import').addEventListener('change', async event => {
      const file = event.target.files?.[0];
      if (!file) return;
      try {
        config = JSON.parse(await file.text());
        const validationResult = await api.validateConfig(config);
        render(validationResult);
        toast('Experiment file imported into the editor. Save to make it authoritative.', validationResult.ok ? 'success' : 'warning');
      } catch (error) { toast(`Import failed: ${error.message}`, 'error'); }
    });
  };
  render(response.validation);
}
