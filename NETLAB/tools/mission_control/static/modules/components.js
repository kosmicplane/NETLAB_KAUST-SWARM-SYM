export function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

export function formatNumber(value, digits = 2, fallback = '—') {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return number.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

export function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value)) return '—';
  if (value < 1) return `${formatNumber(value * 1000, 1)} ms`;
  if (value < 60) return `${formatNumber(value, 1)} s`;
  return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
}

export function sourceBadge(source = 'OFFLINE') {
  const normalized = String(source).toLowerCase();
  return `<span class="source-badge ${escapeHtml(normalized)}">${escapeHtml(String(source).toUpperCase())}</span>`;
}

export function statusChip(label, state = 'neutral', title = '') {
  return `<span class="status-chip ${escapeHtml(state)}" title="${escapeHtml(title)}">${escapeHtml(label)}</span>`;
}

export function metricCard(label, value, unit = '', detail = '') {
  return `<article class="card metric-card">
    <div class="metric-label">${escapeHtml(label)}</div>
    <div class="metric-value">${escapeHtml(value)} ${unit ? `<span class="metric-unit">${escapeHtml(unit)}</span>` : ''}</div>
    ${detail ? `<div class="metric-detail">${escapeHtml(detail)}</div>` : ''}
  </article>`;
}

export function viewHeader(title, description, actions = '') {
  return `<div class="view-header">
    <div><h1 class="view-title">${escapeHtml(title)}</h1><p class="view-description">${escapeHtml(description)}</p></div>
    <div class="view-actions">${actions}</div>
  </div>`;
}

export function card(title, description, content, actions = '', extraClass = '') {
  return `<section class="card ${escapeHtml(extraClass)}">
    <div class="card-header"><div><h2>${escapeHtml(title)}</h2>${description ? `<p class="card-description">${escapeHtml(description)}</p>` : ''}</div>${actions}</div>
    ${content}
  </section>`;
}

export function field({ id, label, value = '', type = 'text', unit = '', min = '', max = '', step = '', help = '', span = 1, options = null, checked = false, readonly = false }) {
  const spanClass = span > 1 ? ` span-${span}` : '';
  let control;
  if (options) {
    control = `<select id="${escapeHtml(id)}" data-field="${escapeHtml(id)}">${options.map(option => {
      const item = typeof option === 'string' ? { value: option, label: option } : option;
      return `<option value="${escapeHtml(item.value)}" ${String(item.value) === String(value) ? 'selected' : ''}>${escapeHtml(item.label)}</option>`;
    }).join('')}</select>`;
  } else if (type === 'textarea') {
    control = `<textarea id="${escapeHtml(id)}" data-field="${escapeHtml(id)}" ${readonly ? 'readonly' : ''}>${escapeHtml(value)}</textarea>`;
  } else if (type === 'checkbox') {
    return `<div class="field${spanClass}"><label class="checkbox-field"><input id="${escapeHtml(id)}" data-field="${escapeHtml(id)}" type="checkbox" ${checked ? 'checked' : ''}><span>${escapeHtml(label)}</span></label>${help ? `<div class="field-help">${escapeHtml(help)}</div>` : ''}</div>`;
  } else {
    control = `<input id="${escapeHtml(id)}" data-field="${escapeHtml(id)}" type="${escapeHtml(type)}" value="${escapeHtml(value)}" ${min !== '' ? `min="${escapeHtml(min)}"` : ''} ${max !== '' ? `max="${escapeHtml(max)}"` : ''} ${step !== '' ? `step="${escapeHtml(step)}"` : ''} ${readonly ? 'readonly' : ''}>`;
  }
  return `<div class="field${spanClass}"><label for="${escapeHtml(id)}"><span>${escapeHtml(label)}</span>${unit ? `<span class="unit">${escapeHtml(unit)}</span>` : ''}</label>${control}${help ? `<div class="field-help">${escapeHtml(help)}</div>` : ''}<div class="field-error" data-error-for="${escapeHtml(id)}"></div></div>`;
}

export function setBusy(button, busy, label = '') {
  if (!button) return;
  if (busy) {
    button.dataset.originalLabel = button.textContent;
    button.disabled = true;
    button.textContent = label || 'Working…';
  } else {
    button.disabled = false;
    button.textContent = button.dataset.originalLabel || button.textContent;
  }
}

export function toast(message, type = 'success', timeout = 5000) {
  const region = document.getElementById('toast-region');
  if (!region) return;
  const element = document.createElement('div');
  element.className = `toast ${type}`;
  element.innerHTML = `<div class="row space-between"><strong>${escapeHtml(type === 'error' ? 'Operation failed' : type === 'warning' ? 'Attention' : 'Operation acknowledged')}</strong><button class="icon-button" aria-label="Dismiss notification">×</button></div><div class="small-text" style="margin-top:5px">${escapeHtml(message)}</div>`;
  element.querySelector('button').addEventListener('click', () => element.remove());
  region.appendChild(element);
  setTimeout(() => element.remove(), timeout);
}

export function prettyJson(value) {
  return `<pre class="code-block">${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
}

export function lineChart(values, { width = 680, height = 210, label = '', unit = '' } = {}) {
  const numeric = values.map(Number).filter(Number.isFinite);
  if (!numeric.length) return `<div class="empty-state"><div><div class="empty-icon">⌁</div><strong>No live samples</strong><div class="small-text">The chart remains empty until the runtime produces measured samples.</div></div></div>`;
  const min = Math.min(...numeric);
  const max = Math.max(...numeric);
  const range = max - min || 1;
  const pad = 28;
  const points = numeric.map((value, index) => {
    const x = pad + (index / Math.max(1, numeric.length - 1)) * (width - 2 * pad);
    const y = height - pad - ((value - min) / range) * (height - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)} chart">
    <line class="chart-grid" x1="${pad}" y1="${pad}" x2="${pad}" y2="${height - pad}"></line>
    <line class="chart-grid" x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}"></line>
    <text class="chart-label" x="${pad + 4}" y="${pad + 11}">${escapeHtml(formatNumber(max, 2))} ${escapeHtml(unit)}</text>
    <text class="chart-label" x="${pad + 4}" y="${height - pad - 5}">${escapeHtml(formatNumber(min, 2))} ${escapeHtml(unit)}</text>
    <polyline class="chart-line" points="${points}"></polyline>
  </svg>`;
}


export function barChart(entries, { width = 680, height = 230, label = '', unit = '', limit = 12 } = {}) {
  const data = (Array.isArray(entries) ? entries : Object.entries(entries || {}))
    .map(item => Array.isArray(item) ? [String(item[0]), Number(item[1])] : [String(item.label), Number(item.value)])
    .filter(item => Number.isFinite(item[1]))
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
  if (!data.length) return `<div class="empty-state"><div><div class="empty-icon">▥</div><strong>No measured distribution</strong><div class="small-text">Bars appear only after runtime samples exist.</div></div></div>`;
  const padLeft = 112, padRight = 28, padTop = 18, padBottom = 24;
  const innerWidth = width - padLeft - padRight;
  const rowHeight = (height - padTop - padBottom) / data.length;
  const max = Math.max(...data.map(item => Math.abs(item[1])), 1);
  const bars = data.map(([name, value], index) => {
    const y = padTop + index * rowHeight + 3;
    const barHeight = Math.max(5, rowHeight - 7);
    const barWidth = Math.max(1, Math.abs(value) / max * innerWidth);
    return `<g><text class="chart-label" x="${padLeft - 7}" y="${y + barHeight * .72}" text-anchor="end">${escapeHtml(name.slice(0, 18))}</text><rect class="chart-bar" x="${padLeft}" y="${y}" width="${barWidth.toFixed(1)}" height="${barHeight.toFixed(1)}" rx="3"></rect><text class="chart-label" x="${Math.min(width - padRight - 2, padLeft + barWidth + 5)}" y="${y + barHeight * .72}">${escapeHtml(formatNumber(value, 2))} ${escapeHtml(unit)}</text></g>`;
  }).join('');
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)} bar chart"><line class="chart-grid" x1="${padLeft}" y1="${padTop}" x2="${padLeft}" y2="${height - padBottom}"></line>${bars}</svg>`;
}

export function empiricalCdf(values, { width = 680, height = 230, label = '', unit = '' } = {}) {
  const data = values.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
  if (!data.length) return `<div class="empty-state"><div><div class="empty-icon">⌁</div><strong>No samples for empirical CDF</strong><div class="small-text">A distribution is shown only from measured samples.</div></div></div>`;
  const pad = 30;
  const min = data[0], max = data.at(-1), range = max - min || 1;
  const points = data.map((value, index) => {
    const x = pad + ((value - min) / range) * (width - 2 * pad);
    const y = height - pad - ((index + 1) / data.length) * (height - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)} empirical CDF"><line class="chart-grid" x1="${pad}" y1="${pad}" x2="${pad}" y2="${height-pad}"></line><line class="chart-grid" x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}"></line><text class="chart-label" x="${pad}" y="${height-8}">${escapeHtml(formatNumber(min,2))} ${escapeHtml(unit)}</text><text class="chart-label" x="${width-pad}" y="${height-8}" text-anchor="end">${escapeHtml(formatNumber(max,2))} ${escapeHtml(unit)}</text><text class="chart-label" x="5" y="${pad+4}">1.0</text><text class="chart-label" x="5" y="${height-pad}">0.0</text><polyline class="chart-line" points="${points}"></polyline></svg>`;
}

export function linkBudgetWaterfall(sample = {}, { width = 680, height = 250 } = {}) {
  const stages = [
    ['TX power', Number(sample.tx_power_dbm)],
    ['TX antenna gain', Number(sample.tx_gain_dbi)],
    ['Path loss', Number.isFinite(Number(sample.path_loss_db)) ? -Math.abs(Number(sample.path_loss_db)) : NaN],
    ['Environmental loss', Number.isFinite(Number(sample.environmental_loss_db)) ? -Math.abs(Number(sample.environmental_loss_db)) : NaN],
    ['RX antenna gain', Number(sample.rx_gain_dbi)],
    ['Received power', Number(sample.rx_power_dbm)],
  ].filter(([, value]) => Number.isFinite(value));
  if (!stages.length) return `<div class="empty-state"><div><div class="empty-icon">⇣</div><strong>No link-budget components</strong><div class="small-text">The active link model has not emitted budget components.</div></div></div>`;
  const min = Math.min(...stages.map(item => item[1]), -120), max = Math.max(...stages.map(item => item[1]), 30), range = max-min || 1;
  const padLeft=130, padRight=28, padTop=18, padBottom=28, row=(height-padTop-padBottom)/stages.length;
  const zeroX=padLeft + ((0-min)/range)*(width-padLeft-padRight);
  const rendered=stages.map(([name,value],index)=>{const y=padTop+index*row+4;const x=padLeft+((Math.min(0,value)-min)/range)*(width-padLeft-padRight);const x2=padLeft+((Math.max(0,value)-min)/range)*(width-padLeft-padRight);return `<g><text class="chart-label" x="${padLeft-8}" y="${y+row*.48}" text-anchor="end">${escapeHtml(name)}</text><rect class="chart-bar ${value<0?'negative':''}" x="${Math.min(x,x2).toFixed(1)}" y="${y}" width="${Math.max(2,Math.abs(x2-x)).toFixed(1)}" height="${Math.max(8,row-8).toFixed(1)}" rx="3"></rect><text class="chart-label" x="${Math.min(width-padRight-2,Math.max(x,x2)+5).toFixed(1)}" y="${y+row*.48}">${escapeHtml(formatNumber(value,2))} dB${name.includes('power')||name==='Received power'?'m':''}</text></g>`}).join('');
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Link budget waterfall"><line class="chart-zero" x1="${zeroX}" y1="${padTop}" x2="${zeroX}" y2="${height-padBottom}"></line>${rendered}</svg>`;
}

export function eventTimeline(events = [], { width = 1000, height = 190 } = {}) {
  const normalized = events.map((event, index) => ({ ...event, _index: index, _time: Number(event.timestamp) })).filter(event => Number.isFinite(event._time));
  if (!normalized.length) return `<div class="empty-state"><div><div class="empty-icon">⋯</div><strong>No runtime events</strong><div class="small-text">Outages, recovery, packet, and revision events will appear here.</div></div></div>`;
  const min=Math.min(...normalized.map(e=>e._time)), max=Math.max(...normalized.map(e=>e._time)), range=max-min||1, pad=34;
  const markers=normalized.slice(-80).map((event,index)=>{const x=pad+((event._time-min)/range)*(width-2*pad);const lane=index%3;const y=55+lane*38;const type=String(event.event_type||'EVENT');const cls=/FAIL|OUTAGE|BLOCK/i.test(type)?'error':/RECOVER|PROMOT|DELIVER/i.test(type)?'success':/REVISION|SYNC/i.test(type)?'warning':'info';return `<g class="timeline-marker ${cls}"><line x1="${x.toFixed(1)}" y1="34" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"></line><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5"><title>${escapeHtml(type)}${event.reason?`: ${escapeHtml(event.reason)}`:''}</title></circle><text class="chart-label" x="${x.toFixed(1)}" y="${y+15}" text-anchor="middle">${escapeHtml(type.slice(0,14))}</text></g>`}).join('');
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Packet outage and recovery event timeline"><line class="chart-grid" x1="${pad}" y1="34" x2="${width-pad}" y2="34"></line><text class="chart-label" x="${pad}" y="20">${escapeHtml(new Date(min*1000).toLocaleTimeString())}</text><text class="chart-label" x="${width-pad}" y="20" text-anchor="end">${escapeHtml(new Date(max*1000).toLocaleTimeString())}</text>${markers}</svg>`;
}

export function downloadJson(filename, value) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function getByPath(object, path, fallback = undefined) {
  let value = object;
  for (const part of path.split('.')) {
    if (value == null || typeof value !== 'object') return fallback;
    value = value[part];
  }
  return value === undefined ? fallback : value;
}

export function setByPath(object, path, value) {
  const parts = path.split('.');
  let cursor = object;
  for (const part of parts.slice(0, -1)) {
    if (!cursor[part] || typeof cursor[part] !== 'object') cursor[part] = {};
    cursor = cursor[part];
  }
  cursor[parts.at(-1)] = value;
}
