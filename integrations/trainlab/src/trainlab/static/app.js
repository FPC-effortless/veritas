'use strict';
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const state = {runs: [], experiments: [], token: '', busy: false, filter: 'all', selected: new Set(), view: 'runs', comparison: null};
const statusNames = {succeeded:'Completed', running:'Running', failed:'Failed', timed_out:'Timed out', interrupted:'Interrupted'};
let signature = '';
let detailRun = null;
const metricValue = value => typeof value === 'number' ? (Number.isInteger(value) ? String(value) : Number(value.toPrecision(5)).toString()) : '—';
const duration = value => value == null ? '—' : value < 1 ? `${Math.round(value * 1000)} ms` : value < 60 ? `${value.toFixed(2)} s` : `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
const timestamp = value => new Date(value).toLocaleString(undefined, {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
const badge = run => `<span class="status ${esc(run.status)}">${esc(statusNames[run.status] || run.status)}</span>`;

async function api(path, options) {
  const response = await fetch(path, {cache: 'no-store', ...options});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'The request could not be completed.');
  return body;
}
function notice(message) {
  $('#notice').textContent = message;
  $('#notice').hidden = !message;
}
function selectionChanged() {
  $('#selected-count').textContent = state.selected.size ? `(${state.selected.size})` : '';
  $('#compare-button').disabled = state.selected.size < 2;
}
function filteredRuns() {
  const query = $('#search').value.toLowerCase().trim();
  const sort = $('#sort').value;
  return state.runs.filter(run => {
    const matches = state.filter === 'all' || run.status === state.filter || (state.filter === 'attention' && !['succeeded','running'].includes(run.status));
    return matches && `${run.name} ${run.id} ${run.source_kind} ${run.seed}`.toLowerCase().includes(query);
  }).sort((a,b) => sort === 'name' ? a.name.localeCompare(b.name) : sort === 'oldest' ? a.started_at.localeCompare(b.started_at) : b.started_at.localeCompare(a.started_at));
}
function renderRuns() {
  const visible = filteredRuns();
  $('#stat-total').textContent = state.runs.length;
  $('#stat-completed').textContent = state.runs.filter(run => run.status === 'succeeded').length;
  $('#stat-running').textContent = state.runs.filter(run => run.status === 'running').length;
  $('#stat-failed').textContent = state.runs.filter(run => !['succeeded','running'].includes(run.status)).length;
  $('#run-total').textContent = state.runs.length;
  $('#nav-count').textContent = state.runs.length;
  $('#table-count').textContent = `${visible.length} of ${state.runs.length} runs${state.selected.size ? ` · ${state.selected.size} selected` : ''}`;
  $('#runs-body').innerHTML = visible.map(run => {
    const name = Object.keys(run.metric_directions)[0];
    return `<tr class="${state.selected.has(run.id) ? 'selected' : ''}"><td class="check-col"><input type="checkbox" data-select="${esc(run.id)}" aria-label="Select ${esc(run.name)}" ${state.selected.has(run.id) ? 'checked' : ''}></td><td><button class="run-name" data-detail="${esc(run.id)}">${esc(run.name)}</button><span class="run-meta">${esc(run.id.slice(-12))} &nbsp;·&nbsp; seed ${run.seed} &nbsp;·&nbsp; ${esc(run.source_kind === 'CONSTRUCTED' ? 'constructed' : 'authentic candidate')}</span></td><td>${badge(run)}</td><td><span class="metric">${esc(metricValue(run.metrics[name]))}</span><div class="metric-label">${esc(name)} ${run.metric_directions[name] === 'min' ? '↓' : '↑'}</div></td><td>${duration(run.elapsed_seconds)}</td><td>${esc(timestamp(run.started_at))}</td><td><button class="arrow-button" data-detail="${esc(run.id)}" aria-label="View ${esc(run.name)}">→</button></td></tr>`;
  }).join('');
  $('#empty-state').hidden = visible.length > 0;
  $('#empty-state h3').textContent = state.runs.length ? 'No runs match this view.' : 'Your next discovery starts here.';
  $('#empty-state p').textContent = state.runs.length ? 'Try another status filter or search term.' : 'Launch a registered experiment or save your first run with the CLI.';
  $('#empty-state code').hidden = state.runs.length > 0;
  $('#empty-run').hidden = state.runs.length > 0;
  const selectedVisible = visible.filter(run => state.selected.has(run.id)).length;
  $('#select-all').checked = visible.length > 0 && selectedVisible === visible.length;
  $('#select-all').indeterminate = selectedVisible > 0 && selectedVisible < visible.length;
  selectionChanged();
}
function renderRecipes() {
  $('#recipes').innerHTML = state.experiments.length ? state.experiments.map(recipe => `<article class="recipe"><span class="recipe-icon">⌘</span><h3>${esc(recipe.name)}</h3><p>${esc(recipe.description)}</p><div class="recipe-meta"><span>SEED ${recipe.seed}</span><span>${esc(recipe.source_kind)}</span><span>TIMEOUT ${recipe.timeout_seconds}s</span></div><code>${recipe.command.map(esc).join(' ')}</code><button class="button primary" data-launch="${esc(recipe.id)}" ${state.busy ? 'disabled' : ''}>${state.busy ? 'An experiment is running…' : 'Run experiment'} <span>→</span></button></article>`).join('') : `<div class="panel empty"><span class="empty-symbol">⌘</span><h3>Register your first experiment.</h3><p>Restart the dashboard with a directory of trusted JSON recipes.</p><code>trainlab serve --experiments examples</code><button class="button" id="recipe-guide">View quick start →</button></div>`;
}
async function refresh() {
  try {
    const response = await api('/api/state');
    state.token = response.token;
    $('#forge-workbench-link').hidden = !response.forge_enabled;
    if (response.job_error) notice(response.job_error);
    $('#connection-label').textContent = 'Local runtime connected';
    const next = JSON.stringify([response.runs,response.experiments,response.busy]);
    if (next !== signature) {
      signature = next;
      Object.assign(state,response);
      for (const id of state.selected) if (!state.runs.some(run => run.id === id)) state.selected.delete(id);
      renderRuns(); renderRecipes();
      if (state.view === 'compare') await renderComparison();
    }
  } catch (error) {
    $('#connection-label').textContent = 'Runtime disconnected';
    notice(`Could not refresh the workspace. ${error.message}`);
  }
}
function navigate() {
  const target = location.hash.slice(1);
  state.view = ['runs','experiments','compare'].includes(target) ? target : 'runs';
  for (const view of ['runs','experiments','compare']) $(`#${view}-view`).hidden = state.view !== view;
  for (const link of document.querySelectorAll('[data-view]')) {
    link.classList.toggle('active',link.dataset.view === state.view);
    if (link.dataset.view === state.view) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current');
  }
  const headings = {runs:['A clearer view of every run.','Run locally. Compare carefully. Keep the evidence.','Overview'],experiments:['Make your next run intentional.','Reusable recipes. Explicit inputs. A record you can return to.','Experiments'],compare:['Compare the work. Keep the context.','Side-by-side metrics, with declared conditions in view.','Compare runs']};
  const [title,subtitle,crumb] = headings[state.view];
  $('#page-title').textContent = title; $('#page-subtitle').textContent = subtitle; $('#breadcrumb').textContent = crumb;
  if (state.view === 'compare') renderComparison().catch(error => notice(error.message));
}
async function launch(id) {
  try {
    await api('/api/run', {method:'POST',headers:{'Content-Type':'application/json','X-TrainLab-Token':state.token},body:JSON.stringify({experiment:id})});
    notice('Experiment started. Its run record will appear as soon as inputs are captured.');
    location.hash = 'runs';
    await refresh();
  } catch (error) { notice(error.message); }
}
function hashes(title, entries) {
  return `<section class="detail-section"><h3>${title}</h3>${Object.entries(entries).map(([name,hash]) => `<div class="hash-row"><span>${esc(name)}</span><code>${esc(hash)}</code></div>`).join('') || '<p class="muted">No artifacts recorded.</p>'}</section>`;
}
function download(name, value, mime='application/json') {
  const url = URL.createObjectURL(new Blob([value],{type:mime}));
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url),1000);
}
function openDetail(id) {
  const run = state.runs.find(item => item.id === id); if (!run) return;
  detailRun = run;
  $('#detail-name').textContent = run.name;
  $('#detail-content').innerHTML = `<div class="detail-summary">${badge(run)}<span class="muted">${esc(timestamp(run.started_at))} · ${duration(run.elapsed_seconds)}</span></div>${run.error ? `<p class="error-text">${esc(run.error)}</p>` : ''}<div class="detail-actions"><button class="button" id="download-run">↓ Export record</button><button class="button" id="verify-run" ${run.status === 'running' ? 'disabled' : ''}>◈ Verify saved files</button><button class="button" data-log="stdout.log">View output</button><button class="button" data-log="stderr.log">View errors</button></div><div id="verification" hidden></div><pre id="log-content" class="log-view" hidden></pre><div class="detail-grid"><div><small>Run ID</small><code>${esc(run.id)}</code></div><div><small>Source & split</small><code>${esc(run.source_kind)} · ${esc(run.split_identity)}</code></div><div><small>Seed & declared budget</small><code>${run.seed} · ${esc(JSON.stringify(run.budget))}</code></div><div><small>Source commit</small><code>${esc(run.git.commit || 'Not a Git checkout')}${run.git.dirty ? ' · working tree modified' : ''}</code></div><div><small>Command</small><code>${esc(JSON.stringify(run.command))}</code></div><div><small>Execution environment</small><code>Python ${esc(run.runtime.python)} · ${esc(run.runtime.platform)}</code></div></div><section class="detail-section"><h3>Recorded metrics</h3>${Object.entries(run.metric_directions).map(([name,direction]) => `<div class="hash-row"><span>${esc(name)} (${direction === 'min' ? 'lower' : 'higher'} is preferred)</span><strong>${esc(metricValue(run.metrics[name]))}</strong></div>`).join('')}</section>${hashes('Declared input identities · SHA-256',run.inputs)}${hashes('Output artifacts · SHA-256',run.artifacts)}<p class="muted">Qualification: NOT_QUALIFIED. File verification checks stored bytes against the record; it does not authenticate the record or independently validate source rights, metrics, or capability.</p>`;
  $('#detail-dialog').showModal();
}
async function renderComparison() {
  const ids = [...state.selected];
  if (ids.length < 2) {
    $('#comparison').innerHTML = `<div class="panel empty"><span class="empty-symbol">⇄</span><h3>Put your runs side by side.</h3><p>Select at least two runs in Overview to compare metrics and declared conditions.</p><a class="button primary" href="#runs">Select runs →</a></div>`;
    return;
  }
  const result = await api('/api/compare?' + ids.map(id => 'id=' + encodeURIComponent(id)).join('&'));
  if (ids.join() !== [...state.selected].join()) return;
  state.comparison = result;
  const metrics = [...new Set(result.runs.flatMap(run => Object.keys(run.metric_directions)))];
  const previous = $('#compare-metric')?.value;
  $('#comparison').innerHTML = `<div class="comparison-top"><h2>${result.runs.length} runs, in context.</h2><div class="detail-actions"><select id="compare-metric" aria-label="Metric to visualize">${metrics.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join('')}</select><button class="button" id="export-comparison">↓ Export CSV</button></div></div><div class="comparison-note ${result.matched_declared_conditions ? '' : 'warning'}"><strong>${result.matched_declared_conditions ? 'Declared comparison conditions match.' : 'These runs differ in their declared conditions.'}</strong><br>${result.matched_declared_conditions ? 'Inputs, source class, split, metric definitions, budget, and seed match.' : `Differences: ${result.mismatches.map(esc).join(', ')}.`} This does not establish equal actual compute or a scientific winner.</div><section class="panel comparison-chart"><h3 id="chart-label"></h3><div id="bars"></div></section><section class="panel table-scroll"><table class="compare-table"><thead><tr><th>Run</th><th>Status</th>${metrics.map(name=>`<th>${esc(name)}</th>`).join('')}<th>Duration</th><th>Seed</th></tr></thead><tbody>${result.runs.map(run=>`<tr><td><button class="run-name" data-detail="${esc(run.id)}">${esc(run.name)}</button><span class="run-meta">${esc(run.id.slice(-12))}</span></td><td>${badge(run)}</td>${metrics.map(name=>`<td class="metric">${metricValue(run.metrics[name])}</td>`).join('')}<td>${duration(run.elapsed_seconds)}</td><td>${run.seed}</td></tr>`).join('')}</tbody></table></section><p class="muted section-intro">Metrics are local, self-reported measurements. Scientific qualification: NOT_QUALIFIED.</p>`;
  if (metrics.includes(previous)) $('#compare-metric').value = previous;
  renderBars();
}
function renderBars() {
  const name = $('#compare-metric').value;
  const runs = state.comparison.runs;
  const maximum = Math.max(...runs.map(run => Math.abs(run.metrics[name] || 0)), Number.EPSILON);
  const negative = runs.some(run => run.metrics[name] < 0);
  $('#chart-label').textContent = `${name} · ${negative ? 'bar length shows absolute magnitude; values retain their sign' : 'recorded values, starting at zero'}`;
  $('#bars').innerHTML = runs.map(run => {
    const value = run.metrics[name];
    const width = typeof value === 'number' ? (Math.abs(value) / maximum) * 100 : 0;
    return `<div class="bar-row"><span class="bar-label" title="${esc(run.name)}">${esc(run.name)}</span><div class="bar-track" aria-hidden="true"><svg viewBox="0 0 100 20" preserveAspectRatio="none"><rect width="${width}" height="20" fill="${value < 0 ? '#b58b64' : '#81a764'}" rx="1"/></svg></div><span class="bar-value">${metricValue(value)}</span></div>`;
  }).join('');
}
function exportComparison() {
  const runs = state.comparison.runs;
  const names = [...new Set(runs.flatMap(run => Object.keys(run.metric_directions)))];
  // Spreadsheet consumers must not interpret experiment names as formulas.
  const csv = value => '"' + String(value ?? '').replace(/^(?:\s*[=+@\-]|[\t\r\n])/, "'$&").replaceAll('"','""') + '"';
  const rows = [['run_id','name','status','seed',...names,'elapsed_seconds','qualification'],...runs.map(run => [run.id,run.name,run.status,run.seed,...names.map(name=>run.metrics[name]),run.elapsed_seconds,'NOT_QUALIFIED'])];
  download('trainlab-comparison.csv',rows.map(row=>row.map(csv).join(',')).join('\r\n'),'text/csv;charset=utf-8');
}
document.addEventListener('click', async event => {
  const button = event.target.closest('button'); if (!button) return;
  if (button.classList.contains('close-dialog')) return button.closest('dialog').close();
  if (['guide-button','help-button','recipe-guide'].includes(button.id)) return $('#guide-dialog').showModal();
  if (button.id === 'new-button' || button.id === 'empty-run') { location.hash='experiments'; return; }
  if (button.id === 'compare-button') { location.hash='compare'; return; }
  if (button.dataset.detail) return openDetail(button.dataset.detail);
  if (button.dataset.launch) return launch(button.dataset.launch);
  if (button.dataset.status) {
    state.filter = button.dataset.status;
    for (const item of document.querySelectorAll('[data-status]')) {
      item.classList.toggle('active',item===button); item.setAttribute('aria-pressed',String(item===button));
    }
    renderRuns();
  }
  if (button.id === 'download-run') download(`trainlab-${detailRun.id}.json`,JSON.stringify(detailRun,null,2));
  if (button.id === 'export-comparison') exportComparison();
  try {
    if (button.id === 'verify-run') {
      button.disabled = true; button.textContent = 'Checking file hashes…';
      const result = await api('/api/verify?id=' + encodeURIComponent(detailRun.id));
      $('#verification').hidden = false; $('#verification').className='verification';
      $('#verification').textContent = result.valid ? 'Saved file hashes match this record. This is a byte-integrity check, not authentication.' : `File integrity mismatch: ${result.mismatches.join(', ')}`;
      button.disabled = false; button.textContent = '◈ Verify saved files';
    }
    if (button.dataset.log) {
      const result = await api('/api/log?id=' + encodeURIComponent(detailRun.id) + '&name=' + encodeURIComponent(button.dataset.log));
      $('#log-content').hidden = false; $('#log-content').textContent = (result.truncated ? '[Last 64 KiB]\n' : '') + (result.text || '(No output recorded)');
    }
  } catch (error) {
    $('#verification').hidden = false; $('#verification').textContent = error.message;
    if (button.id === 'verify-run') { button.disabled=false; button.textContent='Retry verification'; }
  }
});
document.addEventListener('change',event => {
  const element=event.target;
  if (element.dataset.select) { if (element.checked) state.selected.add(element.dataset.select); else state.selected.delete(element.dataset.select); renderRuns(); }
  if (element.id === 'select-all') { for (const run of filteredRuns()) { if (element.checked) state.selected.add(run.id); else state.selected.delete(run.id); } renderRuns(); }
  if (element.id === 'sort') renderRuns();
  if (element.id === 'compare-metric') renderBars();
});
$('#search').addEventListener('input',renderRuns);
window.addEventListener('hashchange',navigate);
navigate(); renderRuns(); renderRecipes(); refresh();
setInterval(refresh,3000);
