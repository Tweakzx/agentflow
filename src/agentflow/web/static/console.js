    const state = {
      projects: [],
      tasks: [],
      filtered: [],
      selectedTask: null,
      autoTimer: null,
      fallbackTimer: null,
      eventSource: null,
      streamReconnectTimer: null,
      streamLastEventId: 0,
      recentRuns: [],
      audit: [],
      stageOpen: {
        todo: true,
        ready: true,
        in_progress: true,
        review: true,
        blocked: true,
        done: false,
        dropped: false,
      },
    };

    async function api(url, opts) {
      const res = await fetch(url, opts);
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }

    function statusClass(status) {
      return `status-${String(status || 'unknown').replaceAll('_', '-')}`;
    }

    function stageClass(stage) {
      return `stage-${String(stage || 'other')}`;
    }

    function stageOf(status) {
      if (status === 'todo') return 'todo';
      if (status === 'ready') return 'ready';
      if (status === 'in_progress') return 'in_progress';
      if (status === 'review') return 'review';
      if (status === 'done') return 'done';
      if (status === 'dropped') return 'dropped';
      if (status === 'blocked') return 'blocked';
      return 'other';
    }

    function statusOrder() {
      return ['todo', 'ready', 'in_progress', 'review', 'blocked', 'done', 'dropped'];
    }

    async function loadProjects() {
      const data = await api('/api/projects');
      state.projects = data.projects || [];
      const sel = document.getElementById('projectSelect');
      const current = sel.value;
      sel.innerHTML = state.projects.map(p => `<option value="${p}">${p}</option>`).join('');
      if (!state.projects.length) {
        return;
      }
      if (current && state.projects.includes(current)) sel.value = current;
      sel.onchange = async () => {
        await refreshAll();
        restartStream();
      };
    }

    function currentProject() {
      return document.getElementById('projectSelect').value;
    }

    async function loadTasks() {
      const data = await api(`/api/tasks?project=${encodeURIComponent(currentProject())}`);
      state.tasks = data.tasks || [];
      const sources = [...new Set(state.tasks.map(t => t.source || 'unknown'))].sort();
      const sourceSel = document.getElementById('sourceFilter');
      const oldSource = sourceSel.value;
      sourceSel.innerHTML = '<option value="">all sources</option>' + sources.map(s => `<option value="${s}">${s}</option>`).join('');
      if (sources.includes(oldSource)) sourceSel.value = oldSource;
      renderTaskList();
    }

    async function loadStatsAndRuns() {
      const project = currentProject();
      const runsData = await api(`/api/runs/recent?project=${encodeURIComponent(project)}&limit=20`);
      const auditData = await api(`/api/audit?project=${encodeURIComponent(project)}&limit=30`);
      state.recentRuns = runsData.runs || [];
      state.audit = auditData.events || [];
      renderRecentRuns();
      renderAudit();
    }

    function renderTaskList() {
      const q = document.getElementById('q').value.trim().toLowerCase();
      const source = document.getElementById('sourceFilter').value;
      state.filtered = state.tasks.filter(t => {
        if (source && (t.source || 'unknown') !== source) return false;
        if (q && !t.title.toLowerCase().includes(q)) return false;
        return true;
      });
      const root = document.getElementById('taskList');
      if (!state.filtered.length) {
        root.innerHTML = '<div class="task"><span class="sub">No tasks</span></div>';
        return;
      }
      const grouped = {};
      for (const st of statusOrder()) grouped[st] = [];
      for (const t of state.filtered) {
        const st = stageOf(t.status);
        if (!grouped[st]) grouped[st] = [];
        grouped[st].push(t);
      }
      root.innerHTML = `<div class="status-accordion">${statusOrder().map(st => {
        const tasks = grouped[st] || [];
        const isOpen = state.stageOpen[st] !== undefined ? state.stageOpen[st] : tasks.length > 0;
        const tasksHtml = tasks.length
          ? tasks.map(t => `
            <div class="task ${state.selectedTask && state.selectedTask.id === t.id ? 'active' : ''}" onclick="openTask(${t.id})">
              <div class="task-title">#${t.id} ${t.title}</div>
              <div class="meta">
                <span>p${t.priority}/i${t.impact}/e${t.effort}</span>
                <span>${t.assigned_agent || '-'}</span>
              </div>
            </div>`).join('')
          : '<div class="task"><span class="sub">No tasks</span></div>';
        return `
          <details class="status-group" ${isOpen ? 'open' : ''} ontoggle="onStageToggle('${st}', this.open)">
            <summary class="status-summary">
              <span class="status-heading"><span class="badge-chip ${stageClass(st)}">${st}</span></span>
              <span class="status-count">${tasks.length}</span>
            </summary>
            <div class="group-body">${tasksHtml}</div>
          </details>`;
      }).join('')}</div>`;
    }

    function onStageToggle(stage, open) {
      state.stageOpen[stage] = Boolean(open);
    }

    function renderRecentRuns() {
      const root = document.getElementById('recentRuns');
      if (!state.recentRuns.length) {
        root.innerHTML = '<div class="sub">No runs yet</div>';
        return;
      }
      root.innerHTML = state.recentRuns.map(r => `
        <div class="run-item">
          <div><strong>#${r.id}</strong> task #${r.task_id} ${r.task_title || ''}</div>
          <div class="meta"><span class="${statusClass(r.status)}">${r.status}</span><span>${r.adapter}</span><span>${r.agent_name}</span><span>${r.started_at}</span></div>
        </div>
      `).join('');
    }

    function renderAudit() {
      const root = document.getElementById('auditList');
      if (!state.audit.length) {
        root.innerHTML = '<div class="sub">No audit events yet</div>';
        return;
      }
      root.innerHTML = state.audit.map(e => `
        <div class="run-item">
          <div><strong>#${e.task_id || '-'}</strong> ${e.event_type || 'event'}</div>
          <div class="meta"><span>${e.event_family || '-'}</span><span class="${statusClass(e.status_from || '')}">${e.status_from || '-'}</span><span>-></span><span class="${statusClass(e.status_to || '')}">${e.status_to || '-'}</span><span>${e.occurred_at || e.recorded_at || '-'}</span></div>
          <div class="sub">${e.summary || '-'}</div>
        </div>
      `).join('');
    }

    async function openTask(taskId) {
      const data = await api(`/api/task/${taskId}`);
      state.selectedTask = data.task;
      renderTaskList();
      renderDetail(data);
    }

    function renderDetail(data) {
      const t = data.task;
      const links = data.links || {};
      const pr = data.pr_summary || {};
      const issueUrl = links.issue_url || '';
      const prUrl = links.pr_url || '';
      const repo = links.repo || '';
      const prCandidates = links.pr_candidates || [];
      const latestRuns = (data.runs || []).slice(0, 5);
      const historyRows = (data.history || []).slice(0, 12);
      const detail = document.getElementById('detail');
      detail.innerHTML = `
        <div class="detail-top">
          <span class="badge">task #${t.id}</span>
          <span class="badge-chip ${stageClass(stageOf(t.status))}">${stageOf(t.status)}</span>
          <span class="badge-chip ${statusClass(t.status)}">status: ${t.status}</span>
        </div>
        <div class="detail-title">${t.title}</div>
        <div class="sub">source: ${t.source || '-'} ${t.external_id || ''} · agent: ${t.assigned_agent || '-'} · lease: ${t.lease_until || '-'}</div>
        <div class="detail-grid">
          <div class="stat"><div class="k">Priority / Impact / Effort</div><div class="v">${t.priority} / ${t.impact} / ${t.effort}</div></div>
          <div class="stat"><div class="k">Runs</div><div class="v">${pr.run_count || 0}</div></div>
          <div class="stat"><div class="k">Latest Gate</div><div class="v">${pr.latest_gate_passed === null || pr.latest_gate_passed === undefined ? '-' : (pr.latest_gate_passed ? 'pass' : 'fail')}</div></div>
        </div>
        <div class="history">
          <h4 style="margin:0 0 8px">PR Detail</h4>
          <div class="timeline-item">PR summary: ${pr.latest_result_summary || 'No execution summary yet'}</div>
          <div class="timeline-item">Latest run status: ${pr.latest_run_status || '-'}</div>
          <div class="timeline-item">Repo: ${repo ? `<a href="https://github.com/${repo}" target="_blank">${repo}</a>` : '-'}</div>
          <div class="timeline-item">Issue: ${issueUrl ? `<a href="${issueUrl}" target="_blank">${issueUrl}</a>` : '-'}</div>
          <div class="timeline-item">Primary PR: ${prUrl ? `<a href="${prUrl}" target="_blank">${prUrl}</a>` : '-'}</div>
          <div class="timeline-item">Related PR Links: ${prCandidates.length ? prCandidates.map(u => `<a href="${u}" target="_blank">${u}</a>`).join('<br/>') : '-'}</div>
        </div>
        <div class="detail-actions">
          <select id="adapterSel"><option value="mock">mock</option></select>
          <input id="agentInput" placeholder="agent name" value="web-console-agent" />
          <button onclick="runTask(${t.id})">Run Task</button>
        </div>
        <div class="detail-actions">
          <select id="moveStatusSel">
            <option value="todo">todo</option>
            <option value="ready">ready</option>
            <option value="in_progress">in_progress</option>
            <option value="review">review</option>
            <option value="done">done</option>
            <option value="dropped">dropped</option>
            <option value="blocked">blocked</option>
          </select>
          <input id="moveNoteInput" placeholder="note for manual transition" />
          <label class="sub" style="display:flex;align-items:center;gap:4px;"><input id="moveForceCk" type="checkbox" style="width:auto;" />force</label>
          <button class="secondary" onclick="moveTask(${t.id}, null, null, null)">Update Flow</button>
        </div>
        <div class="history">
          <h4 style="margin:0 0 8px">Flow History</h4>
          ${historyRows.map(h => `<div class="timeline-item">${h.changed_at}: ${h.from_status || '-'} -> ${h.to_status} ${h.note ? `| ${h.note}` : ''}</div>`).join('') || '<div class="sub">No history</div>'}
        </div>
        <div class="history">
          <h4 style="margin:0 0 8px">Recent Runs (Top 5)</h4>
          ${latestRuns.map(r => `
            <div class="timeline-item">
              <span class="${r.status === 'failed' ? 'err' : 'ok'}">run #${r.id} ${r.status}</span>
              <div class="sub">${r.trigger_type} | ${r.adapter} | ${r.agent_name} | gate=${r.gate_passed ? 'pass' : 'fail'}</div>
              <div class="sub">${(r.steps || []).map(s => `${s.step_name}:${s.status}`).join(' | ') || 'no steps'}</div>
            </div>
          `).join('') || '<div class="sub">No runs yet</div>'}
        </div>
      `;
      const moveSel = document.getElementById('moveStatusSel');
      if (moveSel) moveSel.value = t.status;
    }

    async function runTask(taskId) {
      const project = currentProject();
      const adapter = document.getElementById('adapterSel').value;
      const agent = document.getElementById('agentInput').value || 'web-console-agent';
      try {
        const res = await api(`/api/task/${taskId}/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project, adapter, agent })
        });
        await refreshAll();
        await openTask(taskId);
        alert(res.message || 'run completed');
      } catch (err) {
        alert(`run failed: ${err}`);
      }
    }

    async function moveTask(taskId, forcedStatus, forcedNote, forcedForce) {
      const toStatus = forcedStatus || document.getElementById('moveStatusSel').value;
      const note = forcedNote !== null && forcedNote !== undefined ? forcedNote : (document.getElementById('moveNoteInput').value || '');
      const force = forcedForce !== null && forcedForce !== undefined ? Boolean(forcedForce) : Boolean(document.getElementById('moveForceCk')?.checked);
      try {
        const res = await api(`/api/task/${taskId}/move`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ to_status: toStatus, note, force })
        });
        await refreshAll();
        await openTask(taskId);
        alert(res.message || 'task moved');
      } catch (err) {
        alert(`move failed: ${err}`);
      }
    }

    async function refreshAll() {
      if (!currentProject()) {
        await loadProjects();
      }
      if (!currentProject()) {
        document.getElementById('taskList').innerHTML = '<div class="task"><span class="sub">No projects yet. Create one via CLI first.</span></div>';
        document.getElementById('recentRuns').innerHTML = '<div class="item sub">No project selected.</div>';
        document.getElementById('auditList').innerHTML = '<div class="item sub">No project selected.</div>';
        return;
      }
      await loadTasks();
      await loadStatsAndRuns();
      if (state.selectedTask) {
        const exists = state.tasks.find(t => t.id === state.selectedTask.id);
        if (exists) await openTask(state.selectedTask.id);
      }
    }

    function setConnState(text) {
      const el = document.getElementById('connState');
      if (el) el.textContent = text;
    }

    function stopFallbackPolling() {
      if (state.fallbackTimer) {
        clearInterval(state.fallbackTimer);
        state.fallbackTimer = null;
      }
    }

    function startFallbackPolling() {
      if (state.fallbackTimer) return;
      state.fallbackTimer = setInterval(() => {
        refreshAll().catch(err => console.error(err));
      }, 15000);
    }

    function closeStream() {
      if (state.eventSource) {
        state.eventSource.close();
        state.eventSource = null;
      }
      if (state.streamReconnectTimer) {
        clearTimeout(state.streamReconnectTimer);
        state.streamReconnectTimer = null;
      }
    }

    async function onStreamEvent(raw) {
      let evt = null;
      try {
        evt = JSON.parse(raw.data || '{}');
      } catch (_err) {
        return;
      }
      if (evt && Number.isFinite(Number(evt.id))) {
        state.streamLastEventId = Math.max(state.streamLastEventId, Number(evt.id));
      }
      await refreshAll();
    }

    function restartStream() {
      closeStream();
      const project = currentProject();
      if (!project) return;
      const url = `/api/events?project=${encodeURIComponent(project)}&last_event_id=${state.streamLastEventId || 0}`;
      const es = new EventSource(url);
      state.eventSource = es;

      es.onopen = () => {
        stopFallbackPolling();
        setConnState('Stream: LIVE');
      };
      es.onmessage = (ev) => {
        onStreamEvent(ev).catch(err => console.error(err));
      };
      es.onerror = () => {
        setConnState('Stream: RETRY');
        startFallbackPolling();
        if (state.streamReconnectTimer) return;
        state.streamReconnectTimer = setTimeout(() => {
          state.streamReconnectTimer = null;
          restartStream();
        }, 3000);
      };
    }

    function toggleAuto() {
      const btn = document.getElementById('autoBtn');
      if (state.autoTimer) {
        clearInterval(state.autoTimer);
        state.autoTimer = null;
        btn.textContent = 'Auto: OFF';
        return;
      }
      state.autoTimer = setInterval(() => {
        refreshAll().catch(err => console.error(err));
      }, 15000);
      btn.textContent = 'Auto: ON';
    }

    async function boot() {
      let lastErr = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          await loadProjects();
          await refreshAll();
          restartStream();
          return;
        } catch (err) {
          lastErr = err;
          const delay = 1000 * Math.pow(2, attempt);
          await new Promise((resolve) => setTimeout(resolve, delay));
        }
      }
      throw lastErr || new Error('boot failed');
    }

    window.addEventListener('beforeunload', () => {
      closeStream();
      stopFallbackPolling();
    });

    boot().catch(err => {
      document.body.innerHTML = `
        <div style="padding:24px">
          <h3 style="margin:0 0 10px">Console load failed</h3>
          <pre class="err" style="white-space:pre-wrap">${String(err)}</pre>
          <button class="secondary" onclick="window.location.reload()">Retry</button>
        </div>
      `;
    });
