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
      const derived = data.derived_summary || {};
      const issueUrl = links.issue_url || '';
      const prUrl = links.pr_url || '';
      const repo = links.repo || '';
      const prCandidates = links.pr_candidates || [];
      const allRuns = (data.recent_runs || data.runs || []).slice(0, 5);
      const timelineRows = (data.timeline || []).slice(0, 20);
      const recommendedActions = Array.isArray(derived.recommended_actions) ? derived.recommended_actions : [];
      const detail = document.getElementById('detail');
      const stage = stageOf(t.status);
      const latestRun = allRuns[0] || null;
      const gatePassed = latestRun ? latestRun.gate_passed : null;
      const gateClass = gatePassed === null || gatePassed === undefined ? '' : (gatePassed ? 'pass' : 'fail');
      const gateText = gatePassed === null || gatePassed === undefined ? '-' : (gatePassed ? 'Passed' : 'Failed');

      // Status summary
      let summaryText = '';
      let needsAttention = false;
      if (stage === 'blocked') { summaryText = 'Task is blocked and needs your attention.'; needsAttention = true; }
      else if (stage === 'review') { summaryText = derived.latest_risk ? 'Agent completed but flagged a risk. Please review.' : 'Agent completed work. Please review.'; }
      else if (stage === 'in_progress') { summaryText = `Agent is working on this task.${t.assigned_agent ? ' (' + t.assigned_agent + ')' : ''}`; }
      else if (stage === 'ready') { summaryText = 'Ready to be picked up by an agent.'; }
      else if (stage === 'todo') { summaryText = 'Queued, waiting to be prioritized.'; }
      else if (stage === 'done') { summaryText = 'Completed.'; }
      else if (stage === 'dropped') { summaryText = 'Dropped.'; }

      // Context-aware action buttons
      let actionButtons = '';
      if (stage === 'review') {
        actionButtons = `
          <button class="btn-approve" onclick="moveTask(${t.id},'done','Approved via console',false)">Approve</button>
          <button class="btn-reject" onclick="moveTask(${t.id},'ready','Changes requested via console',false)">Request Changes</button>
          <button class="btn-block" onclick="moveTask(${t.id},'blocked','Blocked by human',false)">Block</button>
        `;
      } else if (stage === 'blocked') {
        actionButtons = `
          <button onclick="runTask(${t.id})">Retry</button>
          <button class="btn-unblock" onclick="moveTask(${t.id},'ready','Unblocked by human',true)">Unblock</button>
          <button class="btn-reject" onclick="moveTask(${t.id},'dropped','Dropped by human',true)">Drop</button>
        `;
      } else if (stage === 'in_progress') {
        actionButtons = `
          <button class="btn-block" onclick="moveTask(${t.id},'blocked','Manually blocked',false)">Block</button>
        `;
      } else if (stage === 'done') {
        actionButtons = `
          <button class="btn-reject" onclick="moveTask(${t.id},'review','Reopened',true)">Reopen</button>
        `;
      } else if (stage === 'dropped') {
        actionButtons = `
          <button class="btn-unblock" onclick="moveTask(${t.id},'todo','Restored by human',true)">Restore</button>
        `;
      }

      detail.innerHTML = `
        <!-- Header -->
        <div class="detail-header">
          <div class="detail-header-top">
            <div class="detail-title">${t.title}</div>
            <span class="badge-chip ${stageClass(stage)}">${stage.replace('_',' ')}</span>
          </div>
          <div class="detail-summary ${needsAttention ? 'summary-alert' : ''}">${summaryText}</div>
          ${t.description ? `<div class="detail-description">${t.description}</div>` : ''}
          <div class="detail-tag-row">
            <span class="tag-badge tag-priority-${t.priority >= 4 ? 'high' : t.priority >= 3 ? 'med' : 'low'}">${priorityLabel(t.priority)}</span>
            <span class="tag-badge tag-impact-${t.impact >= 4 ? 'high' : t.impact >= 3 ? 'med' : 'low'}">Impact: ${impactLabel(t.impact)}</span>
            <span class="tag-badge tag-effort">Effort: ${effortLabel(t.effort)}</span>
          </div>
          <div class="detail-meta-row">
            <span class="meta-chip"><span class="meta-chip-label">Source</span> ${t.source || '-'}</span>
            ${t.external_id ? `<span class="meta-chip">${t.external_id}</span>` : ''}
            <span class="meta-chip"><span class="meta-chip-label">Agent</span> ${t.assigned_agent || '-'}</span>
          </div>
          ${(repo || issueUrl || prUrl || prCandidates.length) ? `
            <div class="detail-links-row">
              ${repo ? `<a class="link-chip" href="https://github.com/${repo}" target="_blank">Repo</a>` : ''}
              ${issueUrl ? `<a class="link-chip" href="${issueUrl}" target="_blank">Issue</a>` : ''}
              ${prUrl ? `<a class="link-chip" href="${prUrl}" target="_blank">PR</a>` : ''}
              ${prCandidates.length ? prCandidates.map(u => `<a class="link-chip" href="${u}" target="_blank">Related PR</a>`).join('') : ''}
            </div>
          ` : ''}
        </div>

        ${(derived.latest_risk || (latestRun && latestRun.status === 'failed')) ? `
          <div class="detail-alert-banner">
            <span class="alert-icon">!</span>
            <div>
              <div class="alert-title">${derived.latest_risk ? 'Risk Signal Detected' : 'Last Run Failed'}</div>
              <div class="alert-body">${derived.latest_risk ? (derived.latest_risk.summary || '-') : (latestRun.error_detail || latestRun.result_summary || 'Check execution details below')}</div>
            </div>
          </div>
        ` : ''}

        <!-- Actions -->
        ${actionButtons ? `
          <div class="detail-actions-bar">
            ${actionButtons}
            <span class="action-spacer"></span>
            <details class="action-card run-advanced-box">
              <summary class="run-advanced-summary">Advanced</summary>
              <div class="advanced-inner">
                <div class="action-row">
                  <label style="min-width:80px">Adapter</label>
                  <select id="runAdapterSel">
                    ${(state.adapters.length ? state.adapters : ['openclaw']).map(a => `<option value="${a}">${a}</option>`).join('')}
                  </select>
                </div>
                <div class="action-row">
                  <label style="min-width:80px">Agent</label>
                  <input id="runAgentInput" placeholder="optional agent name" />
                </div>
                <div class="action-row">
                  <label><input id="runUseOverrideCk" type="checkbox" />use override</label>
                </div>
                <div class="action-row" style="margin-top:4px">
                  <input id="moveNoteInput" placeholder="add a note..." style="flex:1" />
                  <select id="moveStatusSel" style="max-width:130px">
                    <option value="todo">todo</option>
                    <option value="ready">ready</option>
                    <option value="in_progress">in_progress</option>
                    <option value="review">review</option>
                    <option value="done">done</option>
                    <option value="dropped">dropped</option>
                    <option value="blocked">blocked</option>
                  </select>
                  <label class="force-label"><input id="moveForceCk" type="checkbox" />force</label>
                  <button class="secondary sm" onclick="moveTask(${t.id},null,null,null)">Move</button>
                  <button class="sm btn-cancel-adv" onclick="this.closest('details').removeAttribute('open')">Cancel</button>
                </div>
              </div>
            </details>
          </div>
        ` : `
          <div class="detail-actions-bar">
            <details class="action-card run-advanced-box">
              <summary class="run-advanced-summary">Advanced</summary>
              <div class="advanced-inner">
                <div class="action-row">
                  <input id="moveNoteInput" placeholder="add a note..." style="flex:1" />
                  <select id="moveStatusSel" style="max-width:130px">
                    <option value="todo">todo</option>
                    <option value="ready">ready</option>
                    <option value="in_progress">in_progress</option>
                    <option value="review">review</option>
                    <option value="done">done</option>
                    <option value="dropped">dropped</option>
                    <option value="blocked">blocked</option>
                  </select>
                  <label class="force-label"><input id="moveForceCk" type="checkbox" />force</label>
                  <button class="secondary sm" onclick="moveTask(${t.id},null,null,null)">Move</button>
                  <button class="sm btn-cancel-adv" onclick="this.closest('details').removeAttribute('open')">Cancel</button>
                </div>
              </div>
            </details>
          </div>
        `}

        <!-- Agent's Solution -->
        ${latestRun && latestRun.result_summary ? `
          <div class="detail-section">
            <div class="section-title">Agent's Summary</div>
            <div class="solution-text">${latestRun.result_summary}</div>
            <div class="solution-meta">
              <span>Run #${latestRun.id}</span>
              <span class="${statusClass(latestRun.status)}">${latestRun.status}</span>
              <span>Gate: <span class="${gateClass}">${gateText}</span></span>
              ${latestRun.adapter ? `<span>${latestRun.adapter}</span>` : ''}
              ${latestRun.started_at ? `<span>${shortTime(latestRun.started_at)}</span>` : ''}
            </div>
          </div>
        ` : ''}

        <!-- Execution Process (Run with Steps) -->
        ${latestRun ? `
          <div class="detail-section">
            <div class="section-title">Execution Process</div>
            ${(latestRun.steps && latestRun.steps.length) ? `
              <div class="steps-pipeline">
                ${latestRun.steps.map((s, i) => `
                  <div class="step-node ${s.status === 'passed' || s.status === 'completed' || s.status === 'succeeded' ? 'step-ok' : s.status === 'failed' ? 'step-fail' : 'step-pending'}">
                    <div class="step-connector">${i > 0 ? '<div class="step-line"></div>' : ''}</div>
                    <div class="step-dot"></div>
                    <div class="step-body">
                      <div class="step-head">
                        <span class="step-name">${friendlyStepName(s.step_name)}</span>
                        <span class="step-status ${statusClass(s.status)}">${s.status}</span>
                        ${s.started_at ? `<span class="step-time">${shortTime(s.started_at)}</span>` : ''}
                      </div>
                      ${s.log_excerpt ? `<div class="step-log"><pre>${escapeHtml(s.log_excerpt)}</pre></div>` : ''}
                      ${s.error_code ? `<div class="step-error">${s.error_code}</div>` : ''}
                    </div>
                  </div>
                `).join('')}
              </div>
            ` : '<div class="sub">No step details recorded for this run.</div>'}
          </div>
        ` : ''}

        <!-- Signals -->
        ${(derived.latest_progress || derived.latest_handoff || derived.latest_risk || recommendedActions.length) ? `
          <div class="detail-section">
            <div class="section-title">Signals</div>
            <div class="signal-grid">
              ${signalCard('Progress', derived.latest_progress, 'signal-progress')}
              ${signalCard('Handoff', derived.latest_handoff, 'signal-handoff')}
              ${signalCard('Risk', derived.latest_risk, 'signal-risk')}
            </div>
            ${recommendedActions.length ? `
              <div class="recommended-actions">
                <span class="rec-label">Suggested:</span>
                ${recommendedActions.map(a => `<span class="action-tag">${a.label || a.id || '-'}</span>`).join('')}
              </div>
            ` : ''}
          </div>
        ` : ''}

        <!-- Activity Timeline -->
        <div class="detail-section">
          <div class="section-title">Activity</div>
          <div class="timeline-list">
            ${timelineRows.map(e => {
              const to = e.status_to || '';
              const when = shortTime(e.occurred_at || e.recorded_at);
              return `<div class="tl-item ${tlStatusClass(e)}">
                <span class="tl-event">${friendlyEventType(e.event_type)}</span>
                <span class="tl-time">${when}</span>
                <div class="tl-summary">${e.summary || '-'}${e.status_from && e.status_to ? ` &middot; ${e.status_from} &rarr; <span class="${statusClass(to)}">${to}</span>` : ''}</div>
              </div>`;
            }).join('') || '<div class="sub">No activity yet</div>'}
          </div>
        </div>

        <!-- Previous Runs -->
        ${allRuns.length > 1 ? `
          <div class="detail-section">
            <div class="section-title">Previous Runs (${allRuns.length - 1})</div>
            ${allRuns.slice(1).map(r => `
              <div class="run-card ${r.status === 'completed' || r.status === 'succeeded' ? 'run-ok' : r.status === 'failed' ? 'run-fail' : 'run-other'}">
                <div>
                  <span class="run-id">#${r.id}</span>
                  <span class="run-status ${statusClass(r.status)}">${r.status}</span>
                </div>
                <div style="flex:1;font-size:12px;color:var(--muted)">
                  ${r.result_summary || ((r.steps || []).map(s => `${s.step_name}:${s.status}`).join(' &middot; ') || 'no details')}
                </div>
                <div class="run-meta">
                  ${shortTime(r.started_at)} &middot; gate=${r.gate_passed ? 'pass' : 'fail'}
                </div>
              </div>
            `).join('')}
          </div>
        ` : ''}
      `;
      const moveSel = document.getElementById('moveStatusSel');
      if (moveSel) moveSel.value = t.status;
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    function friendlyStepName(name) {
      if (!name) return 'step';
      const map = { claim: 'Claim Task', edit: 'Write Code', gate: 'Run Checks', execute: 'Execute', plan: 'Plan', review: 'Review' };
      return map[name] || name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }

    function priorityLabel(v) {
      if (v >= 5) return 'P0 Critical';
      if (v >= 4) return 'P1 High';
      if (v >= 3) return 'P2 Medium';
      if (v >= 2) return 'P3 Low';
      return 'P4 Minimal';
    }
    function impactLabel(v) {
      if (v >= 5) return 'Critical';
      if (v >= 4) return 'High';
      if (v >= 3) return 'Medium';
      if (v >= 2) return 'Low';
      return 'Minimal';
    }
    function effortLabel(v) {
      if (v >= 5) return 'XL';
      if (v >= 4) return 'L';
      if (v >= 3) return 'M';
      if (v >= 2) return 'S';
      return 'XS';
    }
    function friendlyEventType(type) {
      if (!type) return 'event';
      return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }
    function shortTime(ts) {
      if (!ts) return '';
      // Try to shorten ISO timestamps to just date+time
      return ts.replace(/^(\d{4}-\d{2}-\d{2})T?(\d{2}:\d{2}).*$/, '$1 $2').replace(/^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})$/, '$2');
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
