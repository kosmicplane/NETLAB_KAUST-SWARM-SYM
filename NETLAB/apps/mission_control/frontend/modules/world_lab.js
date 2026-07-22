import { api } from './api.js';
import { escapeHtml, prettyJson, toast, viewHeader } from './components.js';

export async function renderWorldLab(root) {
  const response = await api.config();
  let config = structuredClone(response.config || {});
  config.world ||= {};
  config.world.assets = Array.isArray(config.world.assets) ? config.world.assets : [];
  config.world.electromagnetic_materials = Array.isArray(config.world.electromagnetic_materials) ? config.world.electromagnetic_materials : [];
  config.world.environment ||= { wind_speed_mps: 0, wind_direction_deg: 0, gust_speed_mps: 0, turbulence_intensity: 0, rain_rate_mm_h: 0, fog_visibility_m: 10000, temperature_c: 20, humidity_pct: 40 };
  config.communication ||= {};
  let selected = 0;
  const assets = config.world.assets;
  const materialOptions = ['concrete','glass','metal','vegetation','water','road','soil','dry_ground','wet_ground','unknown'];
  const render = () => {
    const asset = assets[selected];
    root.innerHTML = `${viewHeader('World Lab', 'Import, transform, classify, and version 3D environments. Visual, physical, and electromagnetic materials are managed separately.', `<button class="button secondary" id="world-add">Add Asset</button><button class="button primary" id="world-save">Apply World + Recalculate</button>`)}
    <div class="grid four">
      <article class="card metric-card"><div class="metric-label">World template</div><div class="metric-value" style="font-size:20px">${escapeHtml(config.world.template)}</div><div class="metric-detail">${escapeHtml(config.world.coordinate_frame)} / ${config.world.stage_units_m} m per unit</div></article>
      <article class="card metric-card"><div class="metric-label">Assets</div><div class="metric-value">${assets.length}</div><div class="metric-detail">Geometry records</div></article>
      <article class="card metric-card"><div class="metric-label">EM materials</div><div class="metric-value">${config.world.electromagnetic_materials?.length || 0}</div><div class="metric-detail">Propagation mappings</div></article>
      <article class="card metric-card"><div class="metric-label">Ray-tracing compatibility</div><div class="metric-value" style="font-size:20px">${config.communication.model === 'sionna_rt' ? (assets.length ? 'REVIEW' : 'INVALID') : 'NOT ACTIVE'}</div><div class="metric-detail">Geometry and material provenance are required for F3.</div></article>
    </div>
    <div class="grid sidebar-layout" style="margin-top:16px">
      <section class="card">
        <div class="card-header"><div><h2>World asset registry</h2><p class="card-description">Supported asset formats depend on the Isaac importer and deployment image.</p></div></div>
        <div class="table-wrap"><table><thead><tr><th>ID</th><th>Asset path</th><th>Semantic type</th><th>EM material</th><th>Scale</th><th></th></tr></thead><tbody>
          ${assets.length ? assets.map((item,index)=>`<tr><td><button class="button ghost small" data-world-select="${index}">${escapeHtml(item.id || `asset_${index+1}`)}</button></td><td>${escapeHtml(item.path || item.asset_path || '')}</td><td>${escapeHtml(item.semantic_type || 'unknown')}</td><td>${escapeHtml(item.electromagnetic_material || 'unknown')}</td><td>${escapeHtml(JSON.stringify(item.scale || [1,1,1]))}</td><td><button class="button danger small" data-world-delete="${index}">Delete</button></td></tr>`).join('') : `<tr><td colspan="6"><div class="empty-state"><div><div class="empty-icon">▧</div><strong>No world assets configured</strong><div class="small-text">Add an asset or use the open reference environment.</div></div></div></td></tr>`}
        </tbody></table></div>
        <div class="callout warning" style="margin-top:14px"><div class="callout-title">Material provenance</div><div>NETLAB does not infer electromagnetic properties from render colors. Every propagation material must be measured, literature-derived, a documented Sionna default, estimated, user-defined, or unknown.</div></div>
      </section>
      <aside class="card raised">
        <div class="eyebrow">ENVIRONMENT</div><h2>Atmosphere and wind</h2>
        <div class="stack">
          ${input('world-wind','Wind speed',config.world.environment.wind_speed_mps,'m/s')}${input('world-gust','Gust speed',config.world.environment.gust_speed_mps,'m/s')}${input('world-turbulence','Turbulence intensity',config.world.environment.turbulence_intensity,'ratio')}${input('world-rain','Rain rate',config.world.environment.rain_rate_mm_h,'mm/h')}${input('world-temperature','Temperature',config.world.environment.temperature_c,'°C')}${input('world-humidity','Humidity',config.world.environment.humidity_pct,'%')}
        </div>
      </aside>
    </div>
    ${asset ? `<section class="card" style="margin-top:16px"><div class="card-header"><div><h2>Selected asset transform and semantics</h2><p class="card-description">All vectors use the configured world coordinate frame.</p></div></div><div class="form-grid">
      ${text('asset-id','Asset ID',asset.id || `asset_${selected+1}`)}${text('asset-path','Asset path',asset.path || asset.asset_path || '')}${select('asset-semantic','Semantic category',asset.semantic_type || 'unknown',['terrain','building','concrete','glass','metal','vegetation','water','road','vehicle','indoor_wall','unknown'])}
      ${text('asset-position','Position [x,y,z]',JSON.stringify(asset.position || [0,0,0]))}${text('asset-rotation','Rotation [roll,pitch,yaw]',JSON.stringify(asset.rotation_rpy_deg || asset.rotation || [0,0,0]))}${text('asset-scale','Scale [x,y,z]',JSON.stringify(asset.scale || [1,1,1]))}
      ${select('asset-em-material','Electromagnetic material',asset.electromagnetic_material || 'unknown',materialOptions)}${select('asset-provenance','Material provenance',asset.material_provenance || 'unknown',['measured','literature_derived','sionna_default','estimated','user_defined','unknown'])}${checkbox('asset-collision','Enable collision',asset.collision !== false)}
    </div></section>`:''}
    <details class="card" style="margin-top:16px"><summary><strong>World configuration inspector</strong></summary><div style="margin-top:14px">${prettyJson(config.world)}</div></details>`;
    function input(id,label,value,unit){return `<label class="field"><span><strong>${label}</strong> <span class="unit">${unit}</span></span><input id="${id}" type="number" step="any" value="${value}"></label>`}
    function text(id,label,value){return `<label class="field"><span><strong>${label}</strong></span><input id="${id}" value="${escapeHtml(value)}"></label>`}
    function select(id,label,value,options){return `<label class="field"><span><strong>${label}</strong></span><select id="${id}">${options.map(v=>`<option value="${v}" ${v===value?'selected':''}>${escapeHtml(v)}</option>`).join('')}</select></label>`}
    function checkbox(id,label,value){return `<label class="checkbox-field"><input id="${id}" type="checkbox" ${value?'checked':''}><span>${label}</span></label>`}
    function collect(){
      config.world.environment.wind_speed_mps=Number(root.querySelector('#world-wind').value); config.world.environment.gust_speed_mps=Number(root.querySelector('#world-gust').value); config.world.environment.turbulence_intensity=Number(root.querySelector('#world-turbulence').value); config.world.environment.rain_rate_mm_h=Number(root.querySelector('#world-rain').value); config.world.environment.temperature_c=Number(root.querySelector('#world-temperature').value); config.world.environment.humidity_pct=Number(root.querySelector('#world-humidity').value);
      if(asset){asset.id=root.querySelector('#asset-id').value; asset.path=root.querySelector('#asset-path').value; asset.semantic_type=root.querySelector('#asset-semantic').value; asset.position=JSON.parse(root.querySelector('#asset-position').value); asset.rotation_rpy_deg=JSON.parse(root.querySelector('#asset-rotation').value); asset.scale=JSON.parse(root.querySelector('#asset-scale').value); asset.electromagnetic_material=root.querySelector('#asset-em-material').value; asset.material_provenance=root.querySelector('#asset-provenance').value; asset.collision=root.querySelector('#asset-collision').checked;}
    }
    root.querySelectorAll('[data-world-select]').forEach(button=>button.addEventListener('click',()=>{try{collect()}catch{} selected=Number(button.dataset.worldSelect);render()}));
    root.querySelectorAll('[data-world-delete]').forEach(button=>button.addEventListener('click',()=>{assets.splice(Number(button.dataset.worldDelete),1);selected=0;render()}));
    root.querySelector('#world-add').addEventListener('click',()=>{assets.push({id:`asset_${assets.length+1}`,path:'',position:[0,0,0],rotation_rpy_deg:[0,0,0],scale:[1,1,1],semantic_type:'building',collision:true,electromagnetic_material:'unknown',material_provenance:'unknown'});selected=assets.length-1;render()});
    root.querySelector('#world-save').addEventListener('click',async event=>{event.currentTarget.disabled=true;try{collect();const result=await api.saveConfig(config,true);config=structuredClone(result.config);toast(result.committed?'World, propagation state, and Isaac scene committed under one revision.':`World draft saved; runtime state is ${result.synchronization?.state || 'PENDING_RUNTIME_APPLY'}.`,result.committed?'success':'warning',8000);render()}catch(error){toast(error.message,'error')}finally{event.currentTarget.disabled=false}});
  };
  render();
}
