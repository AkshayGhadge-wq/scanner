// ===================== Tabs (robust) =====================
(() => {
  const tabs = document.querySelectorAll('.tab');
  const panes = document.querySelectorAll('.tabpane');

  function activate(name) {
    tabs.forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    panes.forEach(p => p.classList.toggle('active', p.id === name));
  }

  // Event delegation keeps it resilient even if nodes re-render
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.tab');
    if (!btn) return;
    const name = btn.dataset.tab;
    if (!name) return;
    activate(name);
  });

  // Default to URL pane
  activate('url');
})();

// ===================== Helpers =====================
const $  = (sel) => document.querySelector(sel);
const pre = (obj) => typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2);
const setDisabled = (el, v) => el && (el.disabled = v);

const fileBundle = (filesObj) => {
  if (!filesObj || typeof filesObj !== 'object') return 'N/A';
  return Object.entries(filesObj)
    .map(([name, content]) => `# ${name}\n${content}`)
    .join('\n\n');
};

// --- SVG diagram renderer for Architecture Flow ---
function renderFlowDiagram(containerSelector, items) {
  const container = $(containerSelector);
  if (!container) return;
  if (!Array.isArray(items) || !items.length) {
    container.textContent = 'N/A';
    return;
  }

  const nodeW = 180, nodeH = 56, gapX = 40, padX = 24, padY = 18, arrowLen = 20;
  const n = items.length;
  const width  = padX*2 + n*nodeW + (n-1)*(gapX + arrowLen);
  const height = padY*2 + nodeH;

  let svg = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Architecture flow">`;
  svg += `<defs>
    <marker id="arrow" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="currentColor"></polygon>
    </marker>
    <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000" flood-opacity="0.25"/>
    </filter>
  </defs>`;

  let x = padX;
  const y = padY;

  for (let i = 0; i < n; i++) {
    svg += `<g filter="url(#softShadow)">
      <rect x="${x}" y="${y}" rx="10" ry="10" width="${nodeW}" height="${nodeH}" fill="#0f172a" stroke="#334155" stroke-width="1"/>
      <foreignObject x="${x+10}" y="${y+10}" width="${nodeW-20}" height="${nodeH-20}">
        <div xmlns="http://www.w3.org/1999/xhtml"
             style="font: 14px/18px ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Ubuntu;
                    color:#e2e8f0; text-align:center; display:flex; align-items:center; justify-content:center; height:100%;">
          ${escapeHtml(items[i])}
        </div>
      </foreignObject>
    </g>`;

    if (i < n - 1) {
      const ax1 = x + nodeW + 5;
      const ax2 = ax1 + gapX;
      const midY = y + nodeH/2;
      svg += `<line x1="${ax1}" y1="${midY}" x2="${ax2}" y2="${midY}" stroke="currentColor" stroke-width="2" marker-end="url(#arrow)"/>`;
      x = ax2 + arrowLen - 5;
    }
  }

  svg += `</svg>`;
  container.innerHTML = svg;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ===================== URL Scanner =====================
$('#scanBtn')?.addEventListener('click', async () => {
  const api = $('#api').value.trim();
  const target = $('#urlInput').value.trim();

  if (!api || !target) {
    $('#output').textContent = '⚠️ Please enter both API base and URL.';
    return;
  }

  $('#output').textContent = '⏳ Scanning URL...';
  setDisabled($('#scanBtn'), true);

  try {
    const res = await fetch(`${api}/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: target })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    const data = await res.json();

    $('#output').textContent = pre(data);

    const plan = data.plan || {};
    const bom  = Array.isArray(plan.bill_of_materials) ? plan.bill_of_materials : [];

    $('#planMeta').textContent = plan.selected_plan || 'N/A';
    renderFlowDiagram('#diagram', bom);
    $('#files').textContent    = fileBundle(plan.provisioning?.files);
    $('#commands').textContent = (plan.provisioning?.commands || []).join('\n') || 'N/A';
  } catch (err) {
    $('#output').textContent = '❌ ' + (err?.message || String(err));
  } finally {
    setDisabled($('#scanBtn'), false);
  }
});

// ===================== Create Source (Agent/VM) =====================
$('#createSrcBtn')?.addEventListener('click', async () => {
  const api  = $('#api2').value.trim();
  const name = $('#vmname').value.trim() || 'my-vm';
  const os   = $('#vmos').value;

  if (!api) {
    $('#installOut').textContent = '⚠️ Please enter API base URL.';
    return;
  }

  $('#installOut').textContent = '⏳ Creating source...';
  setDisabled($('#createSrcBtn'), true);

  try {
    const res = await fetch(`${api}/sources`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, os })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    const data = await res.json();

    $('#installOut').textContent = pre(data);
    if (data.source?.source_id) $('#sid').value = data.source.source_id;
  } catch (err) {
    $('#installOut').textContent = '❌ ' + (err?.message || String(err));
  } finally {
    setDisabled($('#createSrcBtn'), false);
  }
});

// ===================== Agent (VM) Scan =====================
$('#scanHostBtn')?.addEventListener('click', async () => {
  const api = $('#api2').value.trim();
  const sourceId = $('#sid').value.trim();

  if (!api || !sourceId) {
    $('#jobStatus').textContent = '⚠️ Provide API base and Source ID.';
    return;
  }

  $('#jobStatus').textContent  = '⏳ Starting VM scan job...';
  $('#planMeta2').textContent  = '';
  $('#diagram2').textContent   = '';
  $('#files2').textContent     = '';
  $('#commands2').textContent  = '';
  $('#results2').textContent   = '';
  setDisabled($('#scanHostBtn'), true);

  try {
    const startRes = await fetch(`${api}/scanHost`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_id: sourceId })
    });
    if (!startRes.ok) {
      const t = await startRes.text();
      throw new Error(`HTTP ${startRes.status} ${startRes.statusText}\n${t}`);
    }
    const startData = await startRes.json();
    const jobId = startData.job_id;
    if (!jobId) {
      $('#jobStatus').textContent = `⚠️ No job_id returned.\n${pre(startData)}`;
      return;
    }
    $('#jobStatus').textContent = `Job: ${jobId}\nState: queued\nProgress: polling...`;

    let tries = 0, status;
    const maxTries = 120; // ~7 minutes @3.5s
    while (tries < maxTries) {
      await new Promise(r => setTimeout(r, 3500));
      const st = await fetch(`${api}/scanJobs/${encodeURIComponent(jobId)}/status`);
      if (!st.ok) throw new Error(`Status HTTP ${st.status} ${st.statusText}`);
      status = await st.json();
      const phase = status?.progress?.phase || 'unknown';
      const pct   = status?.progress?.pct ?? 0;
      $('#jobStatus').textContent = `Job: ${jobId}\nState: ${status.status || 'unknown'}\nProgress: {\n  "phase": "${phase}",\n  "pct": ${pct}\n}`;
      if ((status.status || '').toLowerCase() === 'done' || phase === 'complete' || pct === 100) break;
      tries++;
    }

    const resRes = await fetch(`${api}/scanJobs/${encodeURIComponent(jobId)}/results`);
    if (!resRes.ok) throw new Error(`Results HTTP ${resRes.status} ${resRes.statusText}`);
    const results = await resRes.json();

    $('#results2').textContent = pre(results);

    const plan = results.plan || {};
    const bom  = Array.isArray(plan.bill_of_materials) ? plan.bill_of_materials : [];
    $('#planMeta2').textContent = plan.selected_plan || 'N/A';
    renderFlowDiagram('#diagram2', bom);
    $('#files2').textContent    = fileBundle(plan.provisioning?.files);
    $('#commands2').textContent = (plan.provisioning?.commands || []).join('\n') || 'N/A';
  } catch (err) {
    $('#jobStatus').textContent = '❌ ' + (err?.message || String(err));
  } finally {
    setDisabled($('#scanHostBtn'), false);
  }
});
