    const state = {
      projects: [],
      adapters: [],
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

    async function loadAdapters() {
      const data = await api('/api/adapters');
      state.adapters = Array.isArray(data.adapters) ? data.adapters : [];
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
      const derived = data.derived_summary || {};
      const issueUrl = links.issue_url || '';
      const prUrl = links.pr_url || '';
      const repo = links.repo || '';
      const prCandidates = links.pr_candidates || [];
      const latestRuns = (data.recent_runs || data.runs || []).slice(0, 5);
      const timelineRows = (data.timeline || []).slice(0, 20);
      const recommendedActions = Array.isArray(derived.recommended_actions) ? derived.recommended_actions : [];
      const detail = document.getElementById('detail');
      const gatePassed = pr.latest_gate_passed;
      const gateClass = gatePassed === null || gatePassed === undefined ? '' : (gatePassed ? 'pass' : 'fail');
      const gateText = gatePassed === null || gatePassed === undefined ? '-' : (gatePassed ? 'Passed' : 'Failed');
      const runStatus = pr.latest_run_status || '';

      detail.innerHTML = `
        <!-- Header -->
        <div class="detail-header">
          <div class="detail-header-top">
            <div class="detail-title">${t.title}</div>
            <div class="detail-badges">
              <span class="badge">task #${t.id}</span>
              <span class="badge-chip ${stageClass(stageOf(t.status))}">${stageOf(t.status)}</span>
            </div>
          </div>
          <div class="detail-meta-row">
            <span class="meta-chip"><span class="meta-chip-label">Source</span> ${t.source || '-'}</span>
            ${t.external_id ? `<span class="meta-chip">${t.external_id}</span>` : ''}
            <span class="meta-chip"><span class="meta-chip-label">Agent</span> ${t.assigned_agent || '-'}</span>
            <span class="meta-chip"><span class="meta-chip-label">Lease</span> ${t.lease_until || '-'}</span>
          </div>
        </div>

        <!-- Stats Row -->
        <div class="detail-stats-row">
          <div class="stat-pill">
            <div class="stat-pill-label">Priority</div>
            <div class="stat-pill-value">${t.priority}</div>
          </div>
          <div class="stat-pill">
            <div class="stat-pill-label">Impact</div>
            <div class="stat-pill-value">${t.impact}</div>
          </div>
          <div class="stat-pill">
            <div class="stat-pill-label">Effort</div>
            <div class="stat-pill-value">${t.effort}</div>
          </div>
          <div class="stat-pill">
            <div class="stat-pill-label">Runs</div>
            <div class="stat-pill-value">${pr.run_count || 0}</div>
          </div>
          <div class="stat-pill">
            <div class="stat-pill-label">Gate</div>
            <div class="stat-pill-value ${gateClass}">${gateText}</div>
          </div>
        </div>

        <!-- Derived Signals -->
        <div class="detail-section">
          <div class="section-title">Signals</div>
          <div class="signal-grid">
            ${signalCard('Progress', derived.latest_progress, 'signal-progress')}
            ${signalCard('Handoff', derived.latest_handoff, 'signal-handoff')}
            ${signalCard('Risk', derived.latest_risk, 'signal-risk')}
          </div>
          ${recommendedActions.length ? `
            <div style="margin-top:10px">
              <div style="font-size:11px;color:var(--muted);font-weight:600;margin-bottom:4px;">RECOMMENDED ACTIONS</div>
              <div class="action-list">
                ${recommendedActions.map(a => `<span class="action-tag">${a.label || a.id || '-'}</span>`).join('')}
              </div>
            </div>
          ` : ''}
        </div>

        <!-- PR & Links -->
        <div class="detail-section">
          <div class="section-title">PR & Links</div>
          <div class="pr-summary-text">${pr.latest_result_summary || 'No execution summary yet'}</div>
          ${runStatus ? `<div class="pr-status-badge ${runStatus === 'completed' || runStatus === 'succeeded' ? 'status-pass' : runStatus === 'failed' ? 'status-fail' : 'status-neutral'}">Latest run: ${runStatus}</div>` : ''}
          <div class="link-list">
            <div class="link-row"><span class="link-label">Repo</span>${repo ? `<a href="https://github.com/${repo}" target="_blank">${repo}</a>` : '<span class="sub">-</span>'}</div>
            <div class="link-row"><span class="link-label">Issue</span>${issueUrl ? `<a href="${issueUrl}" target="_blank">${issueUrl}</a>` : '<span class="sub">-</span>'}</div>
            <div class="link-row"><span class="link-label">Primary PR</span>${prUrl ? `<a href="${prUrl}" target="_blank">${prUrl}</a>` : '<span class="sub">-</span>'}</div>
            ${prCandidates.length ? prCandidates.map(u => `<div class="link-row"><span class="link-label">Related PR</span><a href="${u}" target="_blank">${u}</a></div>`).join('') : ''}
          </div>
        </div>

        <!-- Actions -->
        <div class="detail-section">
          <div class="detail-actions-row">
            <button onclick="runTask(${t.id})">Run Task</button>
            <details class="action-card run-advanced-box">
              <summary class="run-advanced-summary">Advanced Route Override</summary>
              <div class="action-row">
                <label style="min-width:120px">Adapter</label>
                <select id="runAdapterSel">
                  ${(state.adapters.length ? state.adapters : ['openclaw']).map(a => `<option value="${a}">${a}</option>`).join('')}
                </select>
              </div>
              <div class="action-row">
                <label style="min-width:120px">Agent</label>
                <input id="runAgentInput" placeholder="optional agent name" />
              </div>
              <div class="action-row">
                <label><input id="runUseOverrideCk" type="checkbox" />use override for this run</label>
              </div>
            </details>
            <span class="action-divider"></span>
            <select id="moveStatusSel">
              <option value="todo">todo</option>
              <option value="ready">ready</option>
              <option value="in_progress">in_progress</option>
              <option value="review">review</option>
              <option value="done">done</option>
              <option value="dropped">dropped</option>
              <option value="blocked">blocked</option>
            </select>
            <input id="moveNoteInput" placeholder="note..." style="flex:1;min-width:100px" />
            <label class="force-label"><input id="moveForceCk" type="checkbox" />force</label>
            <button class="secondary" onclick="moveTask(${t.id}, null, null, null)">Move</button>
          </div>
        </div>

        <!-- Timeline -->
        <div class="detail-section">
          <div class="section-title">Timeline (Latest ${timelineRows.length})</div>
          <div class="timeline-list">
            ${timelineRows.map(e => {
              const to = e.status_to || '';
              const when = e.occurred_at || e.recorded_at || '';
              return `<div class="tl-item ${tlStatusClass(e)}">
                <span class="tl-event">${e.event_type || 'event'}</span>
                <span class="tl-time">${when}</span>
                <div class="tl-summary">${e.summary || '-'} &middot; ${e.status_from || '-'} &rarr; <span class="${statusClass(to)}">${to}</span></div>
              </div>`;
            }).join('') || '<div class="sub">No timeline events</div>'}
          </div>
        </div>

        <!-- Recent Runs -->
        <div class="detail-section">
          <div class="section-title">Recent Runs (Top ${latestRuns.length})</div>
          ${latestRuns.map(r => `
            <div class="run-card ${r.status === 'completed' || r.status === 'succeeded' ? 'run-ok' : r.status === 'failed' ? 'run-fail' : 'run-other'}">
              <div>
                <span class="run-id">#${r.id}</span>
                <span class="run-status ${statusClass(r.status)}">${r.status}</span>
              </div>
              <div style="flex:1;font-size:12px;color:var(--muted)">
                ${(r.steps || []).map(s => `${s.step_name}:${s.status}`).join(' &middot; ') || 'no steps'}
              </div>
              <div class="run-meta">
                ${r.adapter} &middot; ${r.agent_name}<br/>gate=${r.gate_passed ? 'pass' : 'fail'}
              </div>
            </div>
          `).join('') || '<div class="sub">No runs yet</div>'}
        </div>
      `;
      const moveSel = document.getElementById('moveStatusSel');
      if (moveSel) moveSel.value = t.status;
    }

    function signalCard(label, eventValue, cls) {
      if (!eventValue) {
        return `<div class="signal-card ${cls}">
          <div class="signal-label">${label}</div>
          <div class="signal-value">-</div>
          <div class="signal-sub">No signal yet</div>
        </div>`;
      }
      const when = eventValue.occurred_at || eventValue.recorded_at || '';
      return `<div class="signal-card ${cls}">
        <div class="signal-label">${label}</div>
        <div class="signal-value">${eventValue.event_type || '-'}</div>
        <div class="signal-sub">${eventValue.summary || '-'}${when ? ' &middot; ' + when : ''}</div>
      </div>`;
    }

    function tlStatusClass(e) {
      const to = e.status_to || '';
      if (to === 'done') return 'tl-done';
      if (to === 'blocked') return 'tl-blocked';
      if (to === 'in_progress') return 'tl-in_progress';
      if (to === 'review') return 'tl-review';
      if (to === 'ready') return 'tl-ready';
      if (to === 'todo') return 'tl-todo';
      if (to === 'dropped') return 'tl-dropped';
      return '';
    }

    async function runTask(taskId) {
      const project = currentProject();
      const useOverride = Boolean(document.getElementById('runUseOverrideCk')?.checked);
      const adapter = String(document.getElementById('runAdapterSel')?.value || '').trim();
      const agent = String(document.getElementById('runAgentInput')?.value || '').trim();
      const payload = { project, mode: 'auto' };
      if (useOverride) {
        const override = {};
        if (adapter) override.adapter = adapter;
        if (agent) override.agent = agent;
        payload.mode = 'override';
        payload.override = override;
      }
      try {
        const res = await api(`/api/task/${taskId}/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        await refreshAll();
        await openTask(taskId);
        const route = res.route || {};
        const routeHint = route.adapter && route.agent ? ` (${route.adapter}/${route.agent})` : '';
        alert((res.message || 'run completed') + routeHint);
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
      if (!state.adapters.length) {
        await loadAdapters();
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
      await loadAdapters();
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
