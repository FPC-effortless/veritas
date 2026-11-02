"use strict";
const $ = id => document.getElementById(id);
let latest = null;
function element(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
async function get(path) { const r = await fetch(path, {cache: "no-store"}); if (!r.ok) throw new Error("Research evidence is unavailable. The saved record has been retained."); return r.json(); }
function renderTasks() {
  $("tasks").replaceChildren();
  for (const t of latest.tasks.filter(t => !$("filter").value || t.status === $("filter").value)) {
    const tr = element("tr");
    for (const v of [t.id, t.role]) tr.append(element("td", v));
    const cell = element("td"); cell.append(element("span", t.status, `badge ${t.status}`)); tr.append(cell);
    for (const v of [t.owner || "—", `${t.attempt} / ${t.max_attempts}`, `${t.seconds} s × ${t.slots}`]) tr.append(element("td", v));
    $("tasks").append(tr);
  }
}
async function synthesis() {
  const id = $("protocol").value; if (!id) return;
  try {
    const s = await get(`/api/lab/synthesis?id=${encodeURIComponent(id)}`); const box = $("synthesis"); box.replaceChildren(element("h3", s.conclusion.replaceAll("_", " ")));
    box.append(element("p", `Replay: ${s.replicated ? "matched" : "pending or differs"} · Independent review: ${s.reviewed ? "clean" : "pending or blocking"}`));
    for (const x of s.seed_effects) box.append(element("p", `Seed ${x.seed}: ${x.candidate.toFixed(4)} vs ${x.control.toFixed(4)} · effect ${x.effect.toFixed(4)}`));
    box.append(element("p", s.uncertainty)); const ul = element("ul"); for (const x of s.limitations) ul.append(element("li", x)); box.append(ul, element("h3", "Next discriminating test"), element("p", s.next_discriminating_test));
  } catch(e) { $("synthesis").textContent = e.message; }
}
async function knowledge() {
  try { const g = await get(`/api/lab/knowledge?q=${encodeURIComponent($("search").value)}`); $("knowledge").replaceChildren();
    for (const n of g.nodes) { const d = element("div", undefined, "node"); d.append(element("small", n.kind), element("strong", n.body.title || n.body.question || n.id), element("p", n.body.summary || n.body.status || n.body.hypothesis || n.body.next_test || "Source and evidence retained in the research record.")); $("knowledge").append(d); }
  } catch(e) { $("knowledge").textContent = e.message; }
}
async function refresh() {
  try {
    latest = await get("/api/lab/state"); $("error").hidden = true; $("updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
    const count = s => latest.tasks.filter(t => t.status === s).length;
    $("cards").replaceChildren(); for (const [v,l] of [[latest.programs.length,"Research programs"],[count("running"),"Running tasks"],[count("succeeded"),"Completed tasks"],[count("failed")+count("lost")+count("blocked"),"Failures & blockers"]]) { const c = element("div",undefined,"card"); c.append(element("strong",String(v)), element("span",l)); $("cards").append(c); }
    $("programs").replaceChildren(); for (const p of latest.programs) { const d = element("div",undefined,"program"); d.append(element("h3",p.id),element("p",p.objective), element("p",`${p.charged_seconds.toFixed(2)} s charged · ${p.reserved_seconds.toFixed(2)} s reserved / ${p.cap_seconds} s cap`)); const b=element("div",undefined,"bar"),fill=element("div"); fill.style.width=`${Math.min(100,100*(p.charged_seconds+p.reserved_seconds)/p.cap_seconds)}%`; b.append(fill);d.append(b);$("programs").append(d); }
    renderTasks(); const selection=$("protocol").value; $("protocol").replaceChildren(element("option","Choose a protocol")); $("protocol").firstChild.value=""; for(const p of latest.protocols.filter(p=>p.spec.schema==="research_lab.protocol.v1")){const o=element("option",p.id);o.value=p.id;$("protocol").append(o);} $("protocol").value=selection;
    $("workers").replaceChildren(); for(const w of latest.workers) $("workers").append(element("p",`${w.id} · ${w.role} · ${w.resource} · ${w.liveness}${w.activity ? ` · PID ${w.activity.pid} · ${w.activity.host} · last heartbeat ${new Date(w.activity.last_seen*1000).toISOString()}` : ""}`));
    $("lanes").replaceChildren(); for(const lane of latest.autonomous_lanes || []) $("lanes").append(element("p",`${lane.id} · ${lane.phase} · ${lane.reason}`));
    $("compute").textContent=`Host CPUs: ${latest.compute_observation.host_cpus ?? "unavailable"} · GPU observation: ${latest.compute_observation.gpu_observation}. Queue slots are declared capacity; GPU use is shown only when measured.`;
    if(selection) await synthesis();
  } catch(e) { $("error").hidden=false;$("error").textContent=e.message;$("updated").textContent="Connection interrupted"; }
}
$("filter").addEventListener("change",renderTasks);$("protocol").addEventListener("change",synthesis);let timer;$("search").addEventListener("input",()=>{clearTimeout(timer);timer=setTimeout(knowledge,180);});
refresh();knowledge();setInterval(refresh,3000);
