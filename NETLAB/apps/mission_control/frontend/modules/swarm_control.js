import { api } from './api.js';
import { escapeHtml, toast, viewHeader } from './components.js';

export async function renderSwarmControl(root) {
  const response = await api.config();
  let config = structuredClone(response.config);
  const drones = config.swarm.drones;
  const render = () => {
    root.innerHTML = `${viewHeader('Swarm Control', 'Issue acknowledged mission commands and edit exact UAV coordinates. Every accepted state change is persisted, sent to ROS 2, and synchronized with Isaac Sim.', `<button class="button secondary" id="swarm-refresh">Refresh</button><button class="button primary" id="swarm-save">Apply Coordinates + Sync</button>`)}
    <div class="grid four">
      <article class="card metric-card"><div class="metric-label">Total UAVs</div><div class="metric-value">${config.swarm.drone_count}</div><div class="metric-detail">Configured inventory</div></article>
      <article class="card metric-card"><div class="metric-label">Active relays</div><div class="metric-value">${config.swarm.relay_count}</div><div class="metric-detail">Eligible for active paths</div></article>
      <article class="card metric-card"><div class="metric-label">Standby UAVs</div><div class="metric-value">${config.swarm.standby_count}</div><div class="metric-detail">Recovery reserve</div></article>
      <article class="card metric-card"><div class="metric-label">Minimum separation</div><div class="metric-value">${config.swarm.minimum_separation_m} <span class="metric-unit">m</span></div><div class="metric-detail">Physical validation threshold</div></article>
    </div>
    <section class="card" style="margin-top:16px">
      <div class="card-header"><div><h2>Mission commands</h2><p class="card-description">Success is displayed only after the backend or ROS runtime acknowledges the action.</p></div></div>
      <div class="row">
        ${['takeoff','hold','resume','land','return_home','emergency_stop'].map(name => `<button class="button ${name === 'emergency_stop' ? 'danger' : name === 'takeoff' ? 'primary' : 'secondary'}" data-command="${name}">${name.replaceAll('_',' ').replace(/\b\w/g, c => c.toUpperCase())}</button>`).join('')}
        <button class="button warning" data-command="recompute_topology">Recompute Topology</button>
        <button class="button secondary" data-command="sync_isaac">Synchronize Isaac</button>
      </div>
    </section>
    <section class="card" style="margin-top:16px">
      <div class="card-header"><div><h2>Exact UAV state editor</h2><p class="card-description">Coordinates use ${escapeHtml(config.world.coordinate_frame)}. Physical and communication validation remain independent.</p></div><button class="button secondary small" id="formation-chain">Generate Chain</button></div>
      <div class="table-wrap"><table>
        <thead><tr><th>UAV</th><th>Role</th><th>Active</th><th>X (m)</th><th>Y (m)</th><th>Z (m)</th><th>Battery (%)</th><th>Failure / Recovery</th></tr></thead>
        <tbody>${drones.map((drone, index) => `<tr data-index="${index}">
          <td><strong>${escapeHtml(drone.id)}</strong><div class="small-text muted">index ${drone.index}</div></td>
          <td><select data-key="role"><option value="relay" ${drone.role === 'relay' ? 'selected' : ''}>Relay</option><option value="standby" ${drone.role === 'standby' ? 'selected' : ''}>Standby</option><option value="source" ${drone.role === 'source' ? 'selected' : ''}>Source</option><option value="sink" ${drone.role === 'sink' ? 'selected' : ''}>Sink</option></select></td>
          <td><input data-key="active" type="checkbox" ${drone.active !== false ? 'checked' : ''}></td>
          <td><input data-key="x" type="number" step="any" value="${drone.position[0]}"></td>
          <td><input data-key="y" type="number" step="any" value="${drone.position[1]}"></td>
          <td><input data-key="z" type="number" step="any" value="${drone.position[2]}"></td>
          <td><input data-key="battery" type="number" min="0" max="100" step="0.1" value="${drone.battery_soc_pct ?? 100}"></td>
          <td><div class="row"><button class="button danger small" data-fail="${drone.index}">Fail</button><button class="button secondary small" data-heal="${drone.index}">Heal</button>${drone.role === 'standby' ? `<button class="button success small" data-promote="${drone.index}">Promote</button>` : ''}</div></td>
        </tr>`).join('')}</tbody>
      </table></div>
      <div class="callout warning" style="margin-top:14px"><div class="callout-title">Automatic synchronization</div><div>Applying this table writes the authoritative configuration, publishes a runtime update to ROS 2 when available, requests an Isaac scene revision, and records evidence. A saved configuration may still be offline until runtime acknowledgement is available.</div></div>
    </section>`;

    const collect = () => {
      root.querySelectorAll('tbody tr[data-index]').forEach(row => {
        const drone = drones[Number(row.dataset.index)];
        drone.role = row.querySelector('[data-key="role"]').value;
        drone.active = row.querySelector('[data-key="active"]').checked;
        drone.position = ['x','y','z'].map(key => Number(row.querySelector(`[data-key="${key}"]`).value));
        drone.battery_soc_pct = Number(row.querySelector('[data-key="battery"]').value);
      });
      return drones;
    };
    root.querySelector('#swarm-save').addEventListener('click', async event => {
      event.currentTarget.disabled = true;
      try {
        const result = await api.saveSwarm(collect());
        config = structuredClone(result.config);
        toast(result.committed ? 'UAV state committed across ROS 2, Sionna, and Isaac.' : `UAV draft saved; runtime state is ${result.synchronization?.state || 'PENDING_RUNTIME_APPLY'}.`, result.committed ? 'success' : 'warning', 8000);
        render();
      } catch (error) { toast(error.message, 'error'); }
      finally { event.currentTarget.disabled = false; }
    });
    root.querySelector('#swarm-refresh').addEventListener('click', () => renderSwarmControl(root));
    root.querySelector('#formation-chain').addEventListener('click', () => {
      const spacing = Math.min(config.communication.operational_range_m * 0.6, 35);
      drones.forEach((drone, index) => { drone.position = [(index + 1) * spacing, 0, 25 + (index % 3)]; });
      render();
    });
    root.querySelectorAll('[data-command]').forEach(button => button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        const result = await api.command(button.dataset.command, {});
        if (result.job) document.dispatchEvent(new CustomEvent('netlab:job', { detail: result.job }));
        toast(`${button.textContent.trim()} was accepted.`, 'success');
      } catch (error) { toast(error.message, 'error'); }
      finally { button.disabled = false; }
    }));
    root.querySelectorAll('[data-fail]').forEach(button => button.addEventListener('click', () => executeUav('fail_uav', button.dataset.fail)));
    root.querySelectorAll('[data-heal]').forEach(button => button.addEventListener('click', () => executeUav('heal_uav', button.dataset.heal)));
    root.querySelectorAll('[data-promote]').forEach(button => button.addEventListener('click', () => executeUav('promote_standby', button.dataset.promote)));
    async function executeUav(command, index) {
      try { await api.command(command, { index: Number(index) }); toast(`${command.replaceAll('_',' ')} acknowledged for UAV ${index}.`, 'success'); }
      catch (error) { toast(error.message, 'error'); }
    }
  };
  render();
}
