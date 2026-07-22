import { api } from './api.js';
import { escapeHtml, toast, viewHeader } from './components.js';

function patternSvg(antenna) {
  const gain = Math.max(-20, Math.min(40, Number(antenna.gain_dbi || 0)));
  const beam = Math.max(1, Math.min(360, Number(antenna.beamwidth_azimuth_deg || 360)));
  const points = [];
  for (let deg = 0; deg <= 360; deg += 4) {
    const delta = Math.min(Math.abs(deg), Math.abs(360 - deg));
    const normalized = beam >= 359 ? 1 : Math.max(0.08, Math.pow(Math.cos((delta / Math.max(1, beam / 2)) * Math.PI / 2), 2));
    const r = 26 + 62 * normalized * (0.75 + Math.max(0, gain) / 100);
    const angle = (deg - 90) * Math.PI / 180;
    points.push(`${100 + r * Math.cos(angle)},${100 + r * Math.sin(angle)}`);
  }
  return `<svg viewBox="0 0 200 200" role="img" aria-label="Analytical antenna pattern preview"><circle cx="100" cy="100" r="70" fill="none" stroke="var(--border)"></circle><circle cx="100" cy="100" r="35" fill="none" stroke="var(--border)"></circle><line x1="20" y1="100" x2="180" y2="100" stroke="var(--border)"></line><line x1="100" y1="20" x2="100" y2="180" stroke="var(--border)"></line><polygon points="${points.join(' ')}" fill="rgba(10,95,168,.16)" stroke="var(--primary)" stroke-width="2"></polygon><circle cx="100" cy="100" r="4" fill="var(--primary)"></circle></svg>`;
}

export async function renderAntennaLab(root) {
  const response = await api.config();
  let config = structuredClone(response.config);
  let selected = 0;
  const definitions = config.antennas.definitions;
  const entities = [config.station.id, ...config.swarm.drones.map(d => d.id)];

  const render = () => {
    const antenna = definitions[selected] || definitions[0];
    root.innerHTML = `${viewHeader('Antenna Lab', 'Configure RF models, patterns, arrays, mounting poses, and per-entity assignments. Coverage previews are not presented as proven RF coverage.', `<button class="button secondary" id="antenna-add">Add Antenna</button><button class="button primary" id="antenna-save">Apply + Recalculate</button>`)}
    <div class="grid sidebar-layout">
      <section class="card">
        <div class="card-header"><div><h2>Antenna registry</h2><p class="card-description">Every definition records provenance and fidelity limitations.</p></div></div>
        <div class="table-wrap"><table><thead><tr><th>ID</th><th>Model</th><th>Gain</th><th>Frequency</th><th>Provenance</th><th></th></tr></thead><tbody>
          ${definitions.map((item, index) => `<tr class="${index === selected ? 'selected' : ''}"><td><button class="button ghost small" data-select="${index}">${escapeHtml(item.id)}</button></td><td>${escapeHtml(item.model)}</td><td>${Number(item.gain_dbi || 0).toFixed(2)} dBi</td><td>${(Number(item.center_frequency_hz || 0) / 1e9).toFixed(3)} GHz</td><td>${escapeHtml(item.provenance || 'unknown')}</td><td><button class="button danger small" data-delete="${index}" ${definitions.length <= 1 ? 'disabled' : ''}>Delete</button></td></tr>`).join('')}
        </tbody></table></div>
        <h3 style="margin-top:18px">Entity assignments</h3>
        <div class="table-wrap"><table><thead><tr><th>Entity</th><th>Antenna</th></tr></thead><tbody>${entities.map(entity => `<tr><td>${escapeHtml(entity)}</td><td><select data-assignment="${escapeHtml(entity)}">${definitions.map(item => `<option value="${escapeHtml(item.id)}" ${config.antennas.assignments[entity] === item.id ? 'selected' : ''}>${escapeHtml(item.name || item.id)}</option>`).join('')}</select></td></tr>`).join('')}</tbody></table></div>
      </section>
      <aside class="card raised">
        <div class="eyebrow">PATTERN PREVIEW</div><h2>${escapeHtml(antenna?.name || antenna?.id || 'No antenna')}</h2>
        <div class="chart">${antenna ? patternSvg(antenna) : ''}</div>
        <div class="callout warning" style="margin-top:12px"><div class="callout-title">Analytical preview</div><div>This drawing reflects the configured beamwidth abstraction. It is not a measured or full-wave pattern unless the provenance explicitly says so.</div></div>
      </aside>
    </div>
    ${antenna ? `<section class="card" style="margin-top:16px"><div class="card-header"><div><h2>Selected antenna properties</h2><p class="card-description">Pose and orientation must be applied in the entity coordinate frame.</p></div></div><div class="form-grid">
      ${input('antenna-id','ID',antenna.id,'text')}${input('antenna-name','Name',antenna.name || antenna.id,'text')}${select('antenna-model','Model',antenna.model,['omnidirectional','isotropic','dipole','patch','sector','directional','array','imported_pattern','plugin'])}
      ${input('antenna-frequency','Center frequency',antenna.center_frequency_hz,'number','Hz')}${input('antenna-bandwidth','Bandwidth',antenna.bandwidth_hz,'number','Hz')}${input('antenna-gain','Gain',antenna.gain_dbi,'number','dBi')}
      ${input('antenna-efficiency','Efficiency',antenna.efficiency,'number','ratio')}${select('antenna-polarization','Polarization',antenna.polarization,['vertical','horizontal','circular_rhcp','circular_lhcp','dual','custom'])}${input('antenna-cable-loss','Cable loss',antenna.cable_loss_db || 0,'number','dB')}
      ${input('antenna-beam-az','Azimuth beamwidth',antenna.beamwidth_azimuth_deg || 360,'number','deg')}${input('antenna-beam-el','Elevation beamwidth',antenna.beamwidth_elevation_deg || 120,'number','deg')}${input('antenna-fbr','Front-to-back ratio',antenna.front_to_back_ratio_db || 0,'number','dB')}
      ${input('antenna-offset','Mounting offset [x,y,z]',JSON.stringify(antenna.position_offset_m || [0,0,0]),'text','m')}${input('antenna-rotation','Rotation [roll,pitch,yaw]',JSON.stringify(antenna.rotation_rpy_deg || [0,0,0]),'text','deg')}${select('antenna-provenance','Provenance',antenna.provenance || 'user_defined',['analytical_reference','measured','literature_derived','sionna_default','estimated','user_defined','unknown'])}
    </div></section>` : ''}`;

    function input(id,label,value,type='text',unit='') { return `<label class="field"><span><strong>${escapeHtml(label)}</strong> <span class="unit">${escapeHtml(unit)}</span></span><input id="${id}" type="${type}" step="any" value="${escapeHtml(value)}"></label>`; }
    function select(id,label,value,options) { return `<label class="field"><span><strong>${escapeHtml(label)}</strong></span><select id="${id}">${options.map(v => `<option value="${v}" ${String(value)===v?'selected':''}>${escapeHtml(v)}</option>`).join('')}</select></label>`; }
    function collectSelected() {
      const item = definitions[selected]; if (!item) return;
      const oldId = item.id;
      item.id = root.querySelector('#antenna-id').value.trim();
      item.name = root.querySelector('#antenna-name').value.trim();
      item.model = root.querySelector('#antenna-model').value;
      item.center_frequency_hz = Number(root.querySelector('#antenna-frequency').value);
      item.bandwidth_hz = Number(root.querySelector('#antenna-bandwidth').value);
      item.gain_dbi = Number(root.querySelector('#antenna-gain').value);
      item.efficiency = Number(root.querySelector('#antenna-efficiency').value);
      item.polarization = root.querySelector('#antenna-polarization').value;
      item.cable_loss_db = Number(root.querySelector('#antenna-cable-loss').value);
      item.beamwidth_azimuth_deg = Number(root.querySelector('#antenna-beam-az').value);
      item.beamwidth_elevation_deg = Number(root.querySelector('#antenna-beam-el').value);
      item.front_to_back_ratio_db = Number(root.querySelector('#antenna-fbr').value);
      item.position_offset_m = JSON.parse(root.querySelector('#antenna-offset').value);
      item.rotation_rpy_deg = JSON.parse(root.querySelector('#antenna-rotation').value);
      item.provenance = root.querySelector('#antenna-provenance').value;
      if (oldId !== item.id) for (const entity of Object.keys(config.antennas.assignments)) if (config.antennas.assignments[entity] === oldId) config.antennas.assignments[entity] = item.id;
      root.querySelectorAll('[data-assignment]').forEach(control => { config.antennas.assignments[control.dataset.assignment] = control.value === oldId ? item.id : control.value; });
    }
    root.querySelectorAll('[data-select]').forEach(button => button.addEventListener('click', () => { try { collectSelected(); } catch {} selected = Number(button.dataset.select); render(); }));
    root.querySelectorAll('[data-delete]').forEach(button => button.addEventListener('click', () => { const deleted = definitions.splice(Number(button.dataset.delete),1)[0]; for (const entity of Object.keys(config.antennas.assignments)) if (config.antennas.assignments[entity] === deleted.id) config.antennas.assignments[entity] = definitions[0].id; selected = 0; render(); }));
    root.querySelector('#antenna-add').addEventListener('click', () => { definitions.push({id:`antenna_${definitions.length+1}`,name:'New Research Antenna',model:'omnidirectional',provenance:'user_defined',center_frequency_hz:3.5e9,bandwidth_hz:20e6,gain_dbi:0,efficiency:1,polarization:'vertical',beamwidth_azimuth_deg:360,beamwidth_elevation_deg:180,front_to_back_ratio_db:0,cable_loss_db:0,position_offset_m:[0,0,0],rotation_rpy_deg:[0,0,0]}); selected=definitions.length-1; render(); });
    root.querySelector('#antenna-save').addEventListener('click', async event => { event.currentTarget.disabled=true; try { collectSelected(); root.querySelectorAll('[data-assignment]').forEach(control => config.antennas.assignments[control.dataset.assignment]=control.value); const result=await api.saveConfig(config,true); config=structuredClone(result.config); toast(result.committed?'Antenna registry, link state, and Isaac visualization committed under one revision.':`Antenna draft saved; runtime state is ${result.synchronization?.state || 'PENDING_RUNTIME_APPLY'}.`,result.committed?'success':'warning',8000); render(); } catch(error){toast(error.message,'error');} finally{event.currentTarget.disabled=false;} });
  };
  render();
}
