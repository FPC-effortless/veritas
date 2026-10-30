'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {releases:[],jobs:[],token:'',busy:false,workspace_errors:0,view:'library',filter:'all',selected:new Set(),detail:null,tab:'overview',preview:null,pending:null};
const specFields = {'dataset_id':'dataset-name','adapter':'adapter','source_id':'source-id','source_version':'source-version','license_id':'license-id','provenance_uri':'provenance-uri','split_salt':'split-salt'};
let source = null;
let sourceVersion=0,specVersion=0,inputTasks=0,submitting=false;
let signature = '';
let previewRequest = 0;
const number = value => Number(value || 0).toLocaleString();
const date = value => value ? new Date(value).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : 'Not yet checked';
const badge = record => `<span class="status ${record.integrity === 'valid' ? 'succeeded' : 'failed'}">${record.integrity === 'valid' ? 'Verified' : 'Needs attention'}</span>`;
function notice(message, error=false) { $('#notice').textContent=message; $('#notice').hidden=!message; $('#notice').setAttribute('role',error?'alert':'status'); $('#notice').classList.toggle('error-notice',error); }
async function request(path, payload, binary=false) {
  const options = payload===undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-TrainLab-Token':state.token},body:JSON.stringify(payload)};
  const response=await fetch('/api/forge/'+path,{cache:'no-store',...options});
  if(!response.ok) { let value; try { value=await response.json(); } catch { value={error:'The workspace could not complete this request.'}; } throw new Error(value.error); }
  return binary ? response.blob() : response.json();
}
function download(name, content, mime='application/json') {
  const blob=content instanceof Blob?content:new Blob([content],{type:mime});
  const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function applyTracks(root=document) {
  // Native SVG avoids inline style attributes under the shared strict CSP.
  root.querySelectorAll('[data-splits]').forEach(node=>{
    const counts=JSON.parse(node.dataset.splits),total=Math.max(counts.train+counts.validation+counts.test,1);
    let offset=0;const colors={train:'#75995d',validation:'#c3a374',test:'#acb8c4'};
    node.innerHTML=`<svg viewBox="0 0 100 10" preserveAspectRatio="none" width="100%" height="100%" aria-hidden="true">${Object.keys(colors).map(key=>{const width=counts[key]/total*100;const rect=`<rect x="${offset}" width="${width}" height="10" fill="${colors[key]}"></rect>`;offset+=width;return rect;}).join('')}</svg>`;
  });
}
function track(record) {return `<div class="split-track" data-splits="${esc(JSON.stringify(record.split_records))}" role="img" aria-label="Train ${record.split_records.train}, validation ${record.split_records.validation}, TEST ${record.split_records.test}"></div>`;}
function visibleDatasets() {
  const query=$('#search').value.trim().toLowerCase(),sort=$('#sort').value;
  return state.releases.filter(row=>(state.filter==='all'||row.integrity===state.filter)&&`${row.name} ${row.source_name} ${row.id}`.toLowerCase().includes(query)).sort((a,b)=>sort==='name'?a.name.localeCompare(b.name):sort==='records'?b.records-a.records:b.created_at.localeCompare(a.created_at));
}
function selectionChanged() {$('#selected-count').textContent=state.selected.size?`(${state.selected.size})`:'';$('#compare-button').disabled=state.selected.size<2||state.selected.size>8;}
function renderLibrary() {
  const visible=visibleDatasets();
  $('#stat-releases').textContent=number(state.releases.length);$('#stat-records').textContent=number(state.releases.reduce((sum,row)=>sum+row.records,0));
  $('#stat-valid').textContent=number(state.releases.filter(row=>row.integrity==='valid').length);
  $('#stat-attention').textContent=number(state.releases.filter(row=>row.integrity!=='valid').length+state.jobs.filter(job=>job.status==='failed').length+state.workspace_errors);
  $('#nav-count').textContent=state.releases.length;$('#library-count').textContent=state.releases.length;
  $('#datasets-body').innerHTML=visible.map(row=>`<tr class="${state.selected.has(row.id)?'selected':''}"><td class="check-col"><input type="checkbox" data-select="${row.id}" aria-label="Select ${esc(row.name)}" ${state.selected.has(row.id)?'checked':''}></td><td><button class="run-name" data-open="${row.id}">${esc(row.name)}</button>${row.source_kind==='CONSTRUCTED'?'<span class="source-tag">Constructed</span>':''}<span class="run-meta">${esc(row.source_name)} · ${row.manifest_sha256.slice(0,10)}</span></td><td><span class="metric">${number(row.records)}</span><span class="metric-label">${row.split_records.train} train · ${row.split_records.validation} validation · ${row.split_records.test} TEST</span>${track(row)}</td><td>${badge(row)}<span class="run-meta">${esc(date(row.last_verified_at))}</span></td><td>${esc(date(row.created_at))}</td><td><button class="arrow-button" data-open="${row.id}" aria-label="Open ${esc(row.name)}">→</button></td></tr>`).join('');
  applyTracks($('#datasets-body'));
  $('#empty-state').hidden=visible.length>0;
  $('#empty-state h3').textContent=state.releases.length?'No datasets match this view.':'Your next experiment starts with a dataset.';
  $('#empty-state p').textContent=state.releases.length?'Try another integrity filter or search term.':'Upload chronological JSONL or take a tour with constructed sensor observations.';
  $('#empty-state .empty-actions').hidden=state.releases.length>0;
  $('#table-count').textContent=`${visible.length} of ${state.releases.length} dataset releases${state.selected.size?` · ${state.selected.size} selected`:''}`;
  const selected=visible.filter(row=>state.selected.has(row.id)).length;
  $('#select-all').checked=visible.length>0&&selected===visible.length;$('#select-all').indeterminate=selected>0&&selected<visible.length;
  selectionChanged();
}
function renderActivity() {
  const names={queued:'Queued',running:'Running',succeeded:'Completed',failed:'Failed'};
  $('#activity-list').innerHTML=(state.workspace_errors?`<p class="workspace-error">${state.workspace_errors} library metadata record(s) need operator attention. Existing files were preserved.</p>`:'')+(state.jobs.length?state.jobs.map(job=>`<article class="panel activity-item"><div class="activity-icon">${job.status==='succeeded'?'✓':job.status==='failed'?'!':'◷'}</div><div><h3>${esc(job.name)}</h3><p>${esc(date(job.created_at))}${job.finished_at?' · finished '+esc(date(job.finished_at)):''}</p>${job.error?`<p class="error-text">${esc(job.error)}</p>`:''}${job.status==='succeeded'&&state.releases.some(row=>row.id===job.release_id)?`<button class="text-button activity-open" data-open="${esc(job.release_id)}">Open dataset →</button>`:''}</div><span class="status ${job.status}">${['queued','running'].includes(job.status)&&!job.active?'Unfinished':names[job.status]||'Unfinished'}</span></article>`).join(''):'<div class="panel empty"><span class="empty-symbol">◷</span><h3>Your workspace history starts here.</h3><p>Create a release or verify an existing dataset to record an operation.</p><a class="button primary" href="#create">Create dataset →</a></div>');
}
async function refresh() {
  try {
    const response=await request('state');state.token=response.token;$('#connection-label').textContent='Workspace connected';
    $('#trainlab-link').hidden=!response.trainlab_url;
    if(response.trainlab_url)$('#trainlab-link').href=response.trainlab_url;
    const next=JSON.stringify([response.releases,response.jobs,response.busy,response.workspace_errors]);
    if(next!==signature) {
      signature=next;Object.assign(state,response);
      for(const id of state.selected)if(!state.releases.some(row=>row.id===id))state.selected.delete(id);
      renderLibrary();renderActivity();
      if(state.view==='compare')await renderComparison();
      if(state.pending) {
        const job=state.jobs.find(row=>row.release_id===state.pending);
        if(job?.status==='succeeded') {const id=state.pending;state.pending=null;notice('Dataset release created. Its exact file identity is now pinned.');location.hash='dataset/'+id;}
        else if(job?.status==='failed') {state.pending=null;notice(job.error||'Dataset creation failed. Review the source and try again.',true);location.hash='activity';}
      }
    }
    if(state.view==='detail'&&state.detail) {
      const updated=state.releases.find(row=>row.id===state.detail.id);
      if(updated&&updated.last_verified_at!==state.detail.last_verified_at) {
        Object.assign(state.detail,updated);
        const current=$('.dataset-actions .status');if(current)current.outerHTML=badge(updated);
        if(updated.integrity==='failed') {
          notice(updated.verification_error||'The release no longer matches its saved identity.',true);
          if($('#preview-result'))$('#preview-result').textContent='Preview withheld: release integrity verification failed.';
        }
      }
    }
    $('#submit-release').disabled=state.busy||inputTasks>0||submitting;
  } catch(error) {$('#connection-label').textContent='Workspace disconnected';notice(error.message,true);}
}
function navigate() {
  const route=location.hash.slice(1)||'library';const parts=route.split('/');
  state.view=parts[0]==='dataset'?'detail':['library','create','compare','activity'].includes(parts[0])?parts[0]:'library';
  for(const view of ['library','create','detail','compare','activity'])$(`#${view}-view`).hidden=state.view!==view;
  for(const link of document.querySelectorAll('[data-view]')){const active=link.dataset.view===(state.view==='detail'?'library':state.view);link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');}
  const titles={library:['Better data. A clearer beginning.','Create an immutable release. Know exactly what enters your next experiment.','Dataset library'],create:['Make your next dataset intentional.','A source, its context, and a frozen identity you can return to.','Create dataset'],compare:['Compare the data. Keep the context.','See what changed between release identities, source versions, and splits.','Compare datasets'],activity:['Every operation, accounted for.','A persistent record of creation, verification, and work that needs attention.','Workspace activity']};
  if(titles[state.view]){const [title,subtitle,crumb]=titles[state.view];$('#page-title').textContent=title;$('#page-subtitle').textContent=subtitle;$('#breadcrumb').textContent=crumb;}
  $('#create-button').hidden=state.view==='create';
  if(state.view==='detail')openDetail(parts[1]).catch(error=>notice(error.message,true));
  if(state.view==='compare')renderComparison().catch(error=>notice(error.message,true));
  if(state.view==='activity')renderActivity();
  window.scrollTo(0,0);
}
function sourceBase64(value) {
  const bytes=value.bytes||new TextEncoder().encode(value.text);let text='';
  for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));
  return btoa(text);
}
function cell(value) {
  const text=typeof value==='object'?JSON.stringify(value):String(value??'');
  return esc(text.length>512?text.slice(0,512)+'…':text)+(text.length>512?'<small>Display truncated; export retains the full value.</small>':'');
}
function fillSpec(spec) {
  for(const [key,id] of Object.entries(specFields))$('#'+id).value=spec[key]??'';
  $('#ai-use').checked=spec.ai_use_allowed===true;$('#redistribution').checked=spec.redistribution_allowed===true;$('#privacy').checked=spec.privacy_reviewed===true;
}
function pendingInput(delta) {inputTasks+=delta;$('#submit-release').disabled=state.busy||inputTasks>0||submitting;}
function clearDeclarations() {for(const id of ['ai-use','redistribution','privacy'])$('#'+id).checked=false;}
async function loadExample() {
  const version=++sourceVersion,metadata=++specVersion;pendingInput(1);
  try {
    const value=await request('example');if(version!==sourceVersion||metadata!==specVersion)return;
    source={name:value.source_name,text:value.source_jsonl};fillSpec(value.spec);
    $('#source-file').value='';$('#source-paste').value='';$('#source-file-label').textContent=value.source_name;
    $('#source-state').hidden=false;$('#source-state').className='source-state example';$('#source-state').textContent='Constructed example loaded · 30 sensor records · no real-world data or verified labels.';
    location.hash='create';notice('The example is ready to review. Create an immutable release when you are ready.');
  } finally {pendingInput(-1);}
}
$('#source-file').addEventListener('change',async event=>{
  const version=++sourceVersion;const file=event.target.files[0];if(!file)return;
  source=null;clearDeclarations();pendingInput(1);
  try {
    if(file.size>8*1024*1024)throw new Error('Choose a UTF-8 JSONL file up to 8 MiB.');
    const bytes=new Uint8Array(await file.arrayBuffer());if(version!==sourceVersion)return;
    source={name:file.name,bytes};$('#source-paste').value='';$('#source-file-label').textContent=file.name;
    $('#source-state').hidden=false;$('#source-state').className='source-state';$('#source-state').textContent=`${file.name} · ${number(file.size)} bytes · ready for source validation`;
    notice('Source file loaded. Confirm its use permissions or import its matching source specification.');
  }catch(error){if(version===sourceVersion){source=null;notice(error.message,true);}}
  finally{pendingInput(-1);}
});
$('#source-paste').addEventListener('input',()=>{sourceVersion++;clearDeclarations();});
$('#spec-file').addEventListener('change',async event=>{
  const file=event.target.files[0];if(!file)return;const version=++specVersion,currentSource=sourceVersion;pendingInput(1);
  try {
    if(file.size>16384)throw new Error('Source specification must be at most 16 KiB.');
    const spec=JSON.parse(await file.text());if(version!==specVersion||currentSource!==sourceVersion)return;
    fillSpec(spec);notice('Source specification loaded. Review its permissions against this source.');
  }catch(error){notice(error.message,true);}finally{pendingInput(-1);}
});
$('#create-form').addEventListener('submit',async event=>{
  event.preventDefault();try {
    if(inputTasks>0)throw new Error('Wait for source and specification loading to finish.');
    const pasted=$('#source-paste').value;if(pasted.trim())source={name:'pasted-source.jsonl',text:pasted};
    if(!source)throw new Error('Choose a JSONL file, paste source records, or load the constructed example.');
    const spec=Object.fromEntries(Object.entries(specFields).map(([key,id])=>[key,$('#'+id).value.trim()]));
    Object.assign(spec,{ai_use_allowed:$('#ai-use').checked,redistribution_allowed:$('#redistribution').checked,privacy_reviewed:$('#privacy').checked});
    submitting=true;$('#submit-release').disabled=true;
    const job=await request('releases',{source_name:source.name,source_base64:sourceBase64(source),spec});state.pending=job.release_id;
    notice('Validating and freezing the source. The operation is recorded in Activity.');location.hash='activity';await refresh();
  }catch(error){notice(error.message,true);}finally{submitting=false;$('#submit-release').disabled=state.busy||inputTasks>0;}
});
async function openDetail(id) {
  const detail=await request('detail?id='+encodeURIComponent(id));
  if(location.hash!=='#dataset/'+id)return;
  state.detail=detail;state.tab='overview';state.preview=null;
  $('#page-title').textContent=detail.name;$('#page-subtitle').textContent=`${detail.manifest.source_id} · ${detail.manifest.source_version} · ${number(detail.records)} records`;$('#breadcrumb').textContent='Dataset / '+detail.name;
  renderDetail();
}
function renderDetail() {
  const d=state.detail,m=d.manifest;
  $('#dataset-detail').innerHTML=`<div class="dataset-actions"><a class="button" href="#library">← Dataset library</a>${badge(d)}${d.source_kind==='CONSTRUCTED'?'<span class="source-tag">Constructed data</span>':''}<button class="button" id="verify-dataset">✓ Verify integrity</button><button class="button" id="download-manifest">↓ Download manifest</button></div><div class="pin-label"><strong>MANIFEST SHA-256</strong><code>${esc(d.manifest_sha256)}</code><button class="button" id="copy-pin">Copy</button></div><div class="detail-tabs" role="group" aria-label="Dataset sections">${[['overview','Overview'],['explorer','Data explorer'],['provenance','Files & provenance']].map(([id,label])=>`<button data-tab="${id}" class="${state.tab===id?'active':''}" aria-pressed="${state.tab===id}">${label}</button>`).join('')}</div><div id="detail-tab-content"></div>`;
  const content=$('#detail-tab-content');
  if(state.tab==='overview') {
    content.innerHTML=`<div class="overview-grid"><section class="panel"><h2>A cohort, with clear boundaries.</h2><p class="hint">Subjects stay in one split. Release files are frozen and verified against this manifest identity.</p><div class="distribution">${track(d)}</div><div class="split-numbers">${['train','validation','test'].map(split=>`<div><small>${split==='test'?'TEST · withheld':split[0].toUpperCase()+split.slice(1)}</small><strong>${number(d.split_records[split])}</strong><span class="hint">records</span></div>`).join('')}</div><div class="split-legend"><span><i class="split-train"></i>Train</span><span><i class="split-validation"></i>Validation</span><span><i class="split-test"></i>TEST</span></div></section><section class="panel"><h2>Release context</h2>${fact('Adapter',m.adapter==='robot-jsonl'?'Decoded robot · relative seconds':'Operations · UTC timestamps')}${fact('Source version',m.source_version)}${fact('Source file',d.source_name)}${fact('Created',date(d.created_at))}${fact('Last integrity check',date(d.last_verified_at))}${fact('Split method','Deterministic subject assignment')}<p class="hint">Qualification: NOT_QUALIFIED. A valid file identity does not independently establish source authenticity, label truth, or predictive skill.</p></section></div>`;
    applyTracks(content);
  } else if(state.tab==='provenance') {
    content.innerHTML=`<section class="panel provenance-panel"><h2>Source identity & declarations</h2>${fact('Source identifier',m.source_id)}${fact('Source version',m.source_version)}${fact('License / permission reference',m.license_id)}${fact('Provenance reference',m.provenance_uri)}${fact('AI use / redistribution / privacy','Operator declared')}${fact('Frozen split salt',m.split_salt)}<p class="hint">Declarations are retained with this release. They are not independent verification of source permissions.</p><h2>Immutable file identities</h2>${Object.entries(m.file_sha256).map(([name,pin])=>`<div class="hash-row"><span>${esc(name)}</span><code>${esc(pin)}</code></div>`).join('')}<div class="hash-row"><span>Original source SHA-256</span><code>${esc(m.source_sha256)}</code></div><div class="hash-row"><span>Source specification SHA-256</span><code>${esc(m.source_spec_sha256)}</code></div></section>`;
  } else renderExplorer(content);
}
function fact(label,value){return `<div class="fact"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;}
function renderExplorer(content) {
  const p=state.detail.profile,relative=p.temporal_basis==='relative_seconds';
  content.innerHTML=`<section class="panel profile-panel"><h2>Choose what was available.</h2><p class="hint">Select up to 12 observation fields. Actions are excluded. This explorer withholds TEST rows.</p><div class="feature-choices">${p.fields.map((field,index)=>`<label><input type="checkbox" data-feature="${esc(field)}" aria-label="Feature ${esc(field)}" ${index<4?'checked':''}><span>${esc(field)}</span></label>`).join('')||'<p class="hint">No common observation fields are available in train and validation.</p>'}</div>${p.fields_truncated?'<p class="hint">Showing the first 128 common fields. Use the CLI for wider schemas.</p>':''}<div class="clock-controls"><label>Split<select id="preview-split" aria-label="Preview split"><option value="train">Train</option><option value="validation">Validation</option></select></label><label>Feature visibility cutoff (${relative?'relative seconds':'UTC'})<input id="feature-cutoff" aria-label="Feature visibility cutoff" value="${esc(p.feature_cutoff)}" placeholder="${relative?'Nonnegative seconds':'YYYY-MM-DDTHH:mm:ssZ'}"></label><label class="target-toggle"><input type="checkbox" id="target-toggle">Choose a separate outcome cutoff</label><label>Outcome visibility cutoff (${relative?'relative seconds':'UTC'})<input id="target-cutoff" aria-label="Outcome visibility cutoff" value="${esc(p.target_cutoff??p.feature_cutoff)}" disabled></label></div><div class="explorer-actions"><p class="hint">Outcomes remain hidden until their availability cutoff.</p><button class="button" id="export-jsonl">↓ Export JSONL</button><button class="button" id="export-csv">↓ Export CSV</button><button class="button primary" id="preview-button">Apply preview →</button></div></section><div class="panel"><div id="preview-result" class="empty"><span class="empty-symbol">≋</span><h3>Explore the visible examples.</h3><p>Apply your feature and clock choices to preview this release.</p></div></div>`;
  preview(0).catch(error=>notice(error.message,true));
}
function projection(offset=0) {
  return {id:state.detail.id,split:$('#preview-split').value,fields:[...document.querySelectorAll('[data-feature]:checked')].map(node=>node.dataset.feature),cutoff:$('#feature-cutoff').value.trim(),target_cutoff:$('#target-toggle').checked?$('#target-cutoff').value.trim():null,offset,limit:25};
}
async function preview(offset=0) {
  const sequence=++previewRequest,id=state.detail.id,payload=projection(offset);$('#preview-button').disabled=true;
  try {
    const value=await request('preview',payload);
    if(sequence!==previewRequest||state.view!=='detail'||state.tab!=='explorer'||state.detail.id!==id)return;
    state.preview={...value,payload};const fields=payload.fields;
    $('#preview-result').className='';
    $('#preview-result').innerHTML=`<div class="table-scroll"><table class="data-table"><thead><tr><th>RECORD / SUBJECT</th>${fields.map(field=>`<th>${esc(field)}</th>`).join('')}<th>OUTCOME</th></tr></thead><tbody>${value.rows.map(row=>`<tr><td>${cell(row.record_id)}<div class="row-identity">${cell(row.subject_id)}</div></td>${fields.map(field=>`<td>${cell(row.features[field])}</td>`).join('')}<td>${row.target?`${cell(row.target.value)}<small>Source verified flag: ${esc(row.target.verified)}</small>`:'<span class="muted">Not available at cutoff</span>'}</td></tr>`).join('')||`<tr><td colspan="${fields.length+2}">No examples were available at this cutoff.</td></tr>`}</tbody></table></div><div class="preview-pagination"><span>${value.total?value.offset+1:0}–${Math.min(value.offset+value.rows.length,value.total)} of ${number(value.total)} visible examples</span><div><button class="button" id="preview-prev" ${value.offset===0?'disabled':''}>← Previous</button><button class="button" id="preview-next" ${value.offset+value.rows.length>=value.total?'disabled':''}>Next →</button></div></div>`;
    notice('');
  } finally {if($('#preview-button'))$('#preview-button').disabled=false;}
}
async function exportRows(format) {
  const payload={...projection(0),format};const blob=await request('export',payload,true);
  download(`forge-${state.detail.id.slice(0,8)}-${payload.split}.${format}`,blob);notice(`Exported ${payload.split} examples using the selected fields and visibility cutoffs.`);
}
async function renderComparison() {
  const ids=[...state.selected];
  if(ids.length<2){$('#comparison').innerHTML='<div class="panel empty"><span class="empty-symbol">⇄</span><h3>See what changed between releases.</h3><p>Select two to eight datasets in the library.</p><a class="button primary" href="#library">Choose datasets →</a></div>';return;}
  const comparison=await request('compare',{ids});state.comparison=comparison;
  if(ids.join()!==[...state.selected].join())return;
  $('#comparison').innerHTML=`<div class="comparison-top"><h2>${comparison.releases.length} releases, in context.</h2><button class="button" id="export-comparison">↓ Export comparison JSON</button></div><div class="comparison-note ${comparison.differences.length?'warning':''}"><strong>${comparison.differences.length?'Source or release conditions differ.':'Declared source and split conditions match.'}</strong><br>${comparison.differences.length?'Differences: '+esc(comparison.differences.join(', '))+'.':'Input identities, source version, adapter, split salt, and license declarations match.'} This comparison does not establish a scientific winner.</div><section class="panel comparison-chart"><h3>Records by split</h3>${comparison.releases.map(row=>`<div class="bar-row"><span class="bar-label" title="${esc(row.name)}">${esc(row.name)}</span>${track(row)}<span class="bar-value">${number(row.records)}</span></div>`).join('')}<div class="split-legend"><span><i class="split-train"></i>Train</span><span><i class="split-validation"></i>Validation</span><span><i class="split-test"></i>TEST</span></div></section><section class="panel table-scroll"><table class="compare-table compare-datasets"><thead><tr><th>Dataset</th><th>Source version</th><th>Train</th><th>Validation</th><th>TEST</th><th>Source SHA-256</th></tr></thead><tbody>${comparison.releases.map(row=>`<tr><td><button class="run-name" data-open="${row.id}">${esc(row.name)}</button><span class="run-meta">${row.manifest_sha256.slice(0,12)}</span></td><td>${esc(row.manifest.source_version)}</td><td>${number(row.split_records.train)}</td><td>${number(row.split_records.validation)}</td><td>${number(row.split_records.test)}</td><td><code title="${esc(row.manifest.source_sha256)}">${row.manifest.source_sha256.slice(0,12)}</code></td></tr>`).join('')}</tbody></table></section><p class="hint section-intro">TEST counts are aggregate only. Dataset and source qualification remain separate.</p>`;
  applyTracks($('#comparison'));
}
document.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  try {
    if(button.dataset.example!==undefined)return await loadExample();
    if(button.dataset.open){location.hash='dataset/'+button.dataset.open;return;}
    if(button.dataset.filter){state.filter=button.dataset.filter;for(const node of document.querySelectorAll('[data-filter]')){node.classList.toggle('active',node===button);node.setAttribute('aria-pressed',String(node===button));}renderLibrary();return;}
    if(button.dataset.tab){state.tab=button.dataset.tab;renderDetail();return;}
    if(button.id==='compare-button'){location.hash='compare';return;}
    if(['guide-button','help-button'].includes(button.id)){$('#guide-dialog').showModal();return;}
    if(button.id==='close-guide'){$('#guide-dialog').close();return;}
    if(button.id==='preview-button')return await preview(0);
    if(button.id==='preview-prev')return await preview(Math.max(0,state.preview.offset-state.preview.limit));
    if(button.id==='preview-next')return await preview(state.preview.offset+state.preview.limit);
    if(button.id==='export-jsonl')return await exportRows('jsonl');
    if(button.id==='export-csv')return await exportRows('csv');
    if(button.id==='download-manifest'){const blob=await request('manifest?id='+encodeURIComponent(state.detail.id),undefined,true);download('manifest.json',blob);return;}
    if(button.id==='copy-pin'){if(navigator.clipboard)await navigator.clipboard.writeText(state.detail.manifest_sha256);notice('Manifest SHA-256: '+state.detail.manifest_sha256);return;}
    if(button.id==='verify-dataset'){button.disabled=true;await request('verify',{id:state.detail.id});notice('Rechecking every release file against the pinned manifest.');await refresh();const job=state.jobs.find(row=>row.release_id===state.detail.id);if(job?.status==='failed')notice(job.error,true);else notice('Integrity verification is recorded in Activity.');button.disabled=false;return;}
    if(button.id==='export-comparison')download('forge-comparison.json',JSON.stringify(state.comparison,null,2));
  }catch(error){notice(error.message,true);button.disabled=false;}
});
document.addEventListener('change',event=>{
  const node=event.target;
  if(node.dataset.select){if(node.checked)state.selected.add(node.dataset.select);else state.selected.delete(node.dataset.select);renderLibrary();}
  if(node.id==='select-all'){for(const row of visibleDatasets()){if(node.checked)state.selected.add(row.id);else state.selected.delete(row.id);}renderLibrary();}
  if(node.id==='sort')renderLibrary();
  if(node.id==='target-toggle')$('#target-cutoff').disabled=!node.checked;
});
$('#search').addEventListener('input',renderLibrary);
window.addEventListener('hashchange',navigate);
navigate();refresh();setInterval(refresh,2000);
