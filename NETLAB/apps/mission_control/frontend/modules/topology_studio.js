import { api } from './api.js';
import { escapeHtml, prettyJson, toast, viewHeader } from './components.js';

const presets = {
  chain(relayCount) { return [Array.from({ length: relayCount }, (_, i) => i + 1)]; },
  parallel(relayCount, branchCount = 2) {
    const branches = Array.from({ length: Math.max(1, branchCount) }, () => []);
    for (let i = 1; i <= relayCount; i += 1) branches[(i - 1) % branches.length].push(i);
    return branches.filter(branch => branch.length);
  },
  forest(relayCount, branchCount = 3) {
    if (relayCount < 2) return [[1]];
    const roots = Math.min(2, relayCount);
    const branches = Array.from({ length: Math.max(1, branchCount) }, (_, i) => [1 + (i % roots)]);
    for (let i = roots + 1; i <= relayCount; i += 1) branches[(i - roots - 1) % branches.length].push(i);
    return branches;
  },
};

function edgesFromTopology(topology) {
  if (topology.mode === 'manual' && topology.manual_edges?.length) return topology.manual_edges.map(edge => Array.isArray(edge) ? edge : [edge.src, edge.dst]);
  const edges = [];
  for (const branch of topology.branches || []) {
    let previous = topology.source || 'station';
    for (const index of branch) {
      const next = `drone_${Number(index)}`;
      edges.push([previous, next]);
      previous = next;
    }
  }
  return edges;
}

export async function renderTopologyStudio(root) {
  const [topologyResponse, configResponse] = await Promise.all([api.topology(), api.config()]);
  let topology = structuredClone(topologyResponse.topology);
  let drones = structuredClone(configResponse.config.swarm.drones);
  const station = structuredClone(configResponse.config.station);
  let validation = topologyResponse.validation;
  let selectedNode = null;
  let selectedEdgeSource = null;

  const render = () => {
    const nodes = [{ id: station.id || 'station', role: 'ground_station', position: station.position }, ...drones];
    const xs = nodes.map(node => Number(node.position[0]));
    const ys = nodes.map(node => Number(node.position[1]));
    const minX = Math.min(...xs) - 20, maxX = Math.max(...xs) + 20;
    const minY = Math.min(...ys) - 20, maxY = Math.max(...ys) + 20;
    const toScreen = position => [60 + ((position[0] - minX) / Math.max(1, maxX - minX)) * 760, 560 - ((position[1] - minY) / Math.max(1, maxY - minY)) * 500];
    const fromScreen = (x, y) => [minX + ((x - 60) / 760) * (maxX - minX), minY + ((560 - y) / 500) * (maxY - minY)];
    const byId = Object.fromEntries(nodes.map(node => [node.id, node]));
    const edges = edgesFromTopology(topology);
    const statusBlocks = [
      ['STRUCTURALLY VALID', validation?.structurally_valid],
      ['PHYSICALLY VALID', validation?.physically_valid],
      ['COMMUNICATION FEASIBLE', validation?.communication_feasible],
      ['OPERATIONAL', validation?.operational],
    ];

    root.innerHTML = `${viewHeader('Topology Studio', 'Create, position, and validate chain, parallel, forest, and arbitrary manual relay graphs. Structural validity is distinct from communication feasibility.', `<button class="button secondary" id="topology-validate">Validate</button><button class="button primary" id="topology-save">Apply + Synchronize</button>`)}
    <div class="row" style="margin-bottom:14px">
      <label class="field" style="min-width:180px"><span class="small-text"><strong>Topology mode</strong></span><select id="topology-mode"><option value="chain" ${topology.mode === 'chain' ? 'selected' : ''}>Chain</option><option value="parallel" ${topology.mode === 'parallel' ? 'selected' : ''}>Parallel</option><option value="forest" ${topology.mode === 'forest' ? 'selected' : ''}>Forest</option><option value="manual" ${topology.mode === 'manual' ? 'selected' : ''}>Manual graph</option></select></label>
      <button class="button secondary small" data-preset="chain">Chain preset</button><button class="button secondary small" data-preset="parallel">Parallel preset</button><button class="button secondary small" data-preset="forest">Forest preset</button>
      <button class="button secondary small" id="topology-add-edge">Create Manual Edge</button><button class="button danger small" id="topology-delete-edge">Delete Selected Edge</button>
      ${statusBlocks.map(([label, value]) => `<span class="status-chip ${value === true ? 'ready' : value === false ? 'error' : 'warning'}">${escapeHtml(label)}</span>`).join('')}
    </div>
    <div class="topology-workspace">
      <div class="topology-canvas"><svg class="topology-svg" viewBox="0 0 880 620" id="topology-svg">
        <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#6c8198"></path></marker></defs>
        ${edges.map(([src,dst], index) => {
          if (!byId[src] || !byId[dst]) return '';
          const [x1,y1] = toScreen(byId[src].position); const [x2,y2] = toScreen(byId[dst].position);
          return `<line class="topology-edge" data-edge="${index}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" marker-end="url(#arrow)"></line>`;
        }).join('')}
        ${nodes.map(node => {
          const [x,y] = toScreen(node.position); const color = node.role === 'standby' ? '#a45a00' : node.role === 'ground_station' ? '#4b4fc1' : '#0a5fa8';
          return `<g class="topology-node" data-node="${escapeHtml(node.id)}" transform="translate(${x},${y})"><circle class="node-body" r="24" fill="${color}" stroke="white"></circle><text class="node-label" text-anchor="middle" y="4" style="fill:white">${escapeHtml(node.id.replace('drone_','U'))}</text><text class="node-subtitle" text-anchor="middle" y="38">${escapeHtml(node.role || 'relay')}</text></g>`;
        }).join('')}
      </svg></div>
      <aside class="topology-inspector">
        <div class="eyebrow">GRAPH INSPECTOR</div><h2>${selectedNode ? escapeHtml(selectedNode) : selectedEdgeSource ? 'Select edge destination' : 'Topology configuration'}</h2>
        ${selectedNode ? nodeInspector(byId[selectedNode]) : `<div class="stack">
          <label class="field"><span><strong>Ordered branches (JSON)</strong></span><textarea id="topology-branches">${escapeHtml(JSON.stringify(topology.branches || [], null, 2))}</textarea><span class="field-help">Relay indices in source-to-sink order.</span></label>
          <label class="field"><span><strong>Manual edges (JSON)</strong></span><textarea id="topology-edges">${escapeHtml(JSON.stringify(topology.manual_edges || [], null, 2))}</textarea><span class="field-help">Directed [source,destination] pairs.</span></label>
          <label class="field"><span><strong>Routing policy</strong></span><select id="topology-routing"><option>${escapeHtml(topology.routing_policy)}</option><option value="ordered_path">ordered_path</option><option value="shortest_feasible">shortest_feasible</option><option value="maximum_bottleneck">maximum_bottleneck</option><option value="energy_aware">energy_aware</option><option value="plugin">plugin</option></select></label>
          <div class="callout warning"><div class="callout-title">Operational status is feasibility-gated</div><div>A graph can be structurally valid and still remain unavailable when any required link violates range, hard-outage, SNR/SINR, capacity, endpoint, or freshness constraints.</div></div>
        </div>`}
      </aside>
    </div>
    <div class="grid two" style="margin-top:16px"><section class="card"><h2>Coordinate table</h2><div class="table-wrap"><table><thead><tr><th>Node</th><th>Role</th><th>X (m)</th><th>Y (m)</th><th>Z (m)</th></tr></thead><tbody>${nodes.map(node => `<tr><td>${escapeHtml(node.id)}</td><td>${escapeHtml(node.role)}</td><td>${Number(node.position[0]).toFixed(3)}</td><td>${Number(node.position[1]).toFixed(3)}</td><td>${Number(node.position[2]).toFixed(3)}</td></tr>`).join('')}</tbody></table></div></section><section class="card"><h2>Validation evidence</h2>${prettyJson(validation)}</section></div>`;

    function nodeInspector(node) {
      return `<div class="stack"><div class="callout"><div class="callout-title">${escapeHtml(node.role || 'relay')}</div><div>Drag the node on the canvas or type exact coordinates.</div></div>
        <label class="field"><span><strong>X coordinate</strong> <span class="unit">m</span></span><input id="node-x" type="number" step="any" value="${node.position[0]}"></label>
        <label class="field"><span><strong>Y coordinate</strong> <span class="unit">m</span></span><input id="node-y" type="number" step="any" value="${node.position[1]}"></label>
        <label class="field"><span><strong>Z coordinate</strong> <span class="unit">m</span></span><input id="node-z" type="number" step="any" value="${node.position[2]}"></label>
        <button class="button primary" id="apply-node-coordinate">Apply Coordinate</button></div>`;
    }

    root.querySelector('#topology-mode').addEventListener('change', event => { topology.mode = event.target.value; if (topology.mode !== 'manual') topology.branches = presets[topology.mode](configResponse.config.swarm.relay_count, topology.branch_count || 2); render(); });
    root.querySelectorAll('[data-preset]').forEach(button => button.addEventListener('click', () => { topology.mode = button.dataset.preset; topology.branches = presets[button.dataset.preset](configResponse.config.swarm.relay_count, topology.branch_count || 3); render(); }));
    root.querySelector('#topology-add-edge').addEventListener('click', () => { topology.mode = 'manual'; selectedEdgeSource = null; toast('Select a source node, then select a destination node.', 'warning'); });
    root.querySelector('#topology-delete-edge').addEventListener('click', () => { if (topology.mode === 'manual' && topology.manual_edges?.length) { topology.manual_edges.pop(); render(); } else toast('Manual mode has no selected edge to delete.', 'warning'); });
    root.querySelectorAll('.topology-node').forEach(group => {
      group.addEventListener('pointerdown', event => {
        const id = group.dataset.node;
        if (topology.mode === 'manual' && root.dataset.edgeMode === 'true') return;
        selectedNode = id;
        const svg = root.querySelector('#topology-svg');
        group.setPointerCapture(event.pointerId);
        const move = moveEvent => {
          const point = svg.createSVGPoint(); point.x = moveEvent.clientX; point.y = moveEvent.clientY;
          const local = point.matrixTransform(svg.getScreenCTM().inverse());
          const node = byId[id]; const [nx, ny] = fromScreen(local.x, local.y);
          node.position[0] = Math.round(nx * 1000) / 1000; node.position[1] = Math.round(ny * 1000) / 1000;
          group.setAttribute('transform', `translate(${local.x},${local.y})`);
        };
        const up = () => { group.removeEventListener('pointermove', move); group.removeEventListener('pointerup', up); if (id !== station.id) { const source = byId[id]; const drone = drones.find(item => item.id === id); if (drone) drone.position = [...source.position]; } render(); };
        group.addEventListener('pointermove', move); group.addEventListener('pointerup', up);
      });
      group.addEventListener('click', () => {
        const id = group.dataset.node;
        if (root.dataset.edgeMode === 'true') {
          if (!selectedEdgeSource) { selectedEdgeSource = id; toast(`Edge source selected: ${id}. Select a destination.`, 'warning'); }
          else if (selectedEdgeSource !== id) { topology.mode = 'manual'; topology.manual_edges = topology.manual_edges || []; topology.manual_edges.push([selectedEdgeSource, id]); selectedEdgeSource = null; root.dataset.edgeMode = 'false'; render(); }
        } else { selectedNode = id; render(); }
      });
    });
    root.querySelector('#topology-add-edge').onclick = () => { topology.mode = 'manual'; root.dataset.edgeMode = 'true'; selectedEdgeSource = null; toast('Select source and destination nodes on the canvas.', 'warning'); };
    root.querySelector('#apply-node-coordinate')?.addEventListener('click', () => {
      const node = byId[selectedNode]; node.position = [Number(root.querySelector('#node-x').value), Number(root.querySelector('#node-y').value), Number(root.querySelector('#node-z').value)];
      const drone = drones.find(item => item.id === selectedNode); if (drone) drone.position = [...node.position];
      render();
    });
    root.querySelector('#topology-validate').addEventListener('click', async () => {
      try {
        collectTextareas();
        const result = await api.validateTopology(topology);
        validation = result.validation;
        render();
        toast(validation.structurally_valid && validation.physically_valid ? 'Topology validation passed structural and physical checks.' : 'Topology validation found errors.', validation.structurally_valid && validation.physically_valid ? 'success' : 'warning');
      } catch (error) { toast(error.message, 'error'); }
    });
    root.querySelector('#topology-save').addEventListener('click', async event => {
      event.currentTarget.disabled = true;
      try {
        collectTextareas();
        const result = await api.saveTopology(topology, drones, station, true);
        topology = structuredClone(result.config.topology);
        drones = structuredClone(result.config.swarm.drones);
        validation = result.topology_validation;
        toast(
          result.committed
            ? 'Topology, coordinates, Sionna state, and Isaac scene committed under one acknowledged revision.'
            : `Topology draft saved; runtime state is ${result.synchronization?.state || 'PENDING_RUNTIME_APPLY'}.`,
          result.committed ? 'success' : 'warning',
          8000,
        );
        render();
      } catch (error) { toast(error.message, 'error'); }
      finally { event.currentTarget.disabled = false; }
    });
    function collectTextareas() {
      const branchText = root.querySelector('#topology-branches'); if (branchText) topology.branches = JSON.parse(branchText.value);
      const edgeText = root.querySelector('#topology-edges'); if (edgeText) topology.manual_edges = JSON.parse(edgeText.value);
      const routing = root.querySelector('#topology-routing'); if (routing) topology.routing_policy = routing.value;
      topology.branch_count = topology.branches?.length || 1;
    }
  };
  render();
}
