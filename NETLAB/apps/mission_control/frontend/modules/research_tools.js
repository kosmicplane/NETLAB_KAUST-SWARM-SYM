import { api } from './api.js';
import { card, escapeHtml, field, prettyJson, toast, viewHeader } from './components.js';

function readNumber(root, id, fallback) {
  const value = Number(root.querySelector(`#${id}`)?.value);
  return Number.isFinite(value) ? value : fallback;
}

export async function renderResearchTools(root) {
  root.innerHTML = `${viewHeader('Research Tools', 'Analytical, stochastic, NTN, calibration, radio-map, edge-offloading, and uncertainty utilities with explicit model provenance.')}
  <div class="grid two">
    ${card('Air-to-ground propagation', 'Probabilistic LoS/NLoS reference model for rapid design-space exploration.', `<div class="form-grid">
      ${field({ id:'a2g-distance', label:'Horizontal distance', value:100, type:'number', min:0, step:1, unit:'m' })}
      ${field({ id:'a2g-altitude', label:'UAV altitude', value:60, type:'number', min:1, step:1, unit:'m' })}
      ${field({ id:'a2g-frequency', label:'Carrier frequency', value:3.5e9, type:'number', min:1e6, step:1e6, unit:'Hz' })}
      ${field({ id:'a2g-environment', label:'Environment', value:'urban', options:['suburban','urban','dense_urban','highrise_urban'] })}
    </div><button id="run-a2g" class="button primary" type="button">Evaluate A2G model</button>`)}
    ${card('Non-terrestrial geometry', 'Compute slant range and propagation delay for HAPS/LEO research geometry.', `<div class="form-grid">
      ${field({ id:'ntn-altitude', label:'Platform altitude', value:600000, type:'number', min:1000, step:1000, unit:'m' })}
      ${field({ id:'ntn-elevation', label:'Elevation angle', value:45, type:'number', min:1, max:90, step:1, unit:'deg' })}
    </div><button id="run-ntn" class="button primary" type="button">Evaluate NTN geometry</button>`)}
    ${card('Edge offloading', 'Compare local and edge execution latency and energy under the selected radio link.', `<button id="run-offload" class="button primary" type="button">Compare local and edge execution</button>`)}
    ${card('Measured-trace calibration', 'Fit the log-distance path-loss exponent against distance/loss measurements.', `<button id="run-calibration" class="button primary" type="button">Fit calibration example</button>`)}
    ${card('Radio environment map', 'Interpolate measured samples without presenting the result as ray tracing.', `<button id="run-radio-map" class="button primary" type="button">Interpolate reference map</button>`)}
    ${card('Model provenance', 'Every result declares the active fidelity and assumptions.', '<div id="research-result" class="code-block">Select an analysis.</div>')}
  </div>`;

  const output = root.querySelector('#research-result');
  const run = async operation => {
    output.textContent = 'Evaluating…';
    try {
      const result = await operation();
      output.innerHTML = prettyJson(result);
      toast('Research evaluation completed.', 'success');
    } catch (error) {
      output.textContent = error.message;
      toast(error.message, 'error');
    }
  };
  root.querySelector('#run-a2g').addEventListener('click', () => run(() => api.researchA2G({
    distance_2d_m: readNumber(root, 'a2g-distance', 100),
    altitude_m: readNumber(root, 'a2g-altitude', 60),
    frequency_hz: readNumber(root, 'a2g-frequency', 3.5e9),
    environment: root.querySelector('#a2g-environment').value,
  })));
  root.querySelector('#run-ntn').addEventListener('click', () => run(() => api.researchNtn({
    altitude_m: readNumber(root, 'ntn-altitude', 600000),
    elevation_deg: readNumber(root, 'ntn-elevation', 45),
  })));
  root.querySelector('#run-offload').addEventListener('click', () => run(() => api.researchOffload({
    local_cycles:1e9, cpu_local_hz:1.5e9, input_bits:8e6, uplink_mbps:20,
    edge_cpu_hz:10e9, output_bits:1e6, downlink_mbps:50, tx_power_w:1,
  })));
  root.querySelector('#run-calibration').addEventListener('click', () => run(() => api.researchCalibrate({ frequency_hz:3.5e9, samples:[[10,65],[30,76],[60,85],[100,92]] })));
  root.querySelector('#run-radio-map').addEventListener('click', () => run(() => api.researchRadioMap({ samples:[[0,0,-70],[100,0,-80],[0,100,-77]], points:[[25,25],[50,50],[75,25]], power:2 })));
}
