import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { definePluginEntry } from "openclaw/plugin-sdk/core";

const execFileAsync = promisify(execFile);

type PluginConfig = {
  dbPath: string;
  defaultProject?: string;
  defaultAdapter?: string;
  defaultAgentName?: string;
};

type CapabilityDoc = {
  plugin: {
    id: string;
    name: string;
    version: string;
    summary: string;
  };
  defaults: {
    dbPath: string;
    project: string;
    adapter: string;
    agent: string;
  };
  commandHints: Array<{ id: string; when: string; example: string }>;
  tools: Array<{ id: string; when: string; inputSchema: Record<string, unknown> }>;
  httpRoutes: Array<{ method: string; path: string; when: string }>;
  workflow: string[];
};

type LegacyToolDef = {
  id: string;
  description: string;
  inputSchema: Record<string, unknown>;
  run: (input: any) => Promise<any>;
};

async function runAgentflow(args: string[]): Promise<{ stdout: string; stderr: string }> {
  const { stdout, stderr } = await execFileAsync("python3", ["-m", "agentflow.cli", ...args], {
    env: { ...process.env, PYTHONPATH: "src" },
    cwd: process.cwd()
  });
  return { stdout: String(stdout ?? ""), stderr: String(stderr ?? "") };
}

function parseStructuredOutput(stdout: string): unknown | null {
  const text = String(stdout || "").trim();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function runWithTempJson(
  prefix: string,
  payload: unknown,
  argsBuilder: (tmpPath: string) => string[]
): Promise<{ stdout: string; stderr: string }> {
  const fs = await import("node:fs/promises");
  const os = await import("node:os");
  const path = await import("node:path");
  const tmp = path.join(os.tmpdir(), `${prefix}-${Date.now()}.json`);
  try {
    await fs.writeFile(tmp, JSON.stringify(payload), "utf-8");
    return await runAgentflow(argsBuilder(tmp));
  } finally {
    await fs.rm(tmp, { force: true });
  }
}

function buildCapabilitiesDoc(config: {
  dbPath: string;
  project: string;
  adapter: string;
  agent: string;
}): CapabilityDoc {
  return {
    plugin: {
      id: "agentflow",
      name: "AgentFlow",
      version: "0.2.0",
      summary: "Stage-first task orchestration plugin with webhook and audit support."
    },
    defaults: {
      dbPath: config.dbPath,
      project: config.project,
      adapter: config.adapter,
      agent: config.agent
    },
    commandHints: [
      {
        id: "agentflow.run",
        when: "Execute one claimable task from queue",
        example: "agentflow.run({ project: 'kthena', adapter: 'openclaw', agent: 'openclaw-agent' })"
      },
      {
        id: "agentflow.create",
        when: "Create one task in AgentFlow",
        example: "agentflow.create({ project: 'kthena', title: 'fix flaky gate' })"
      },
      {
        id: "agentflow.move",
        when: "Move one task to a target status",
        example: "agentflow.move({ task_id: 12, to_status: 'approved', note: 'triaged' })"
      },
      {
        id: "agentflow.detail",
        when: "Inspect one task with runs + history",
        example: "agentflow.detail({ task_id: 12 })"
      },
      {
        id: "agentflow.audit",
        when: "Read recent status transition events",
        example: "agentflow.audit({ project: 'kthena', limit: 20 })"
      },
      {
        id: "agentflow.help",
        when: "Read plugin usage guidance and capability map",
        example: "agentflow.help({ mode: 'quickstart' })"
      }
    ],
    tools: [
      {
        id: "agentflow_status",
        when: "Read board queue summary text for a project",
        inputSchema: { type: "object", properties: { project: { type: "string" } } }
      },
      {
        id: "agentflow_capabilities",
        when: "Discover plugin capabilities, routes, and recommended workflow",
        inputSchema: { type: "object", properties: { mode: { type: "string", enum: ["quickstart", "full"] } } }
      },
      {
        id: "agentflow_create_task",
        when: "Create a task via AgentFlow CLI",
        inputSchema: {
          type: "object",
          required: ["project", "title"],
          properties: {
            project: { type: "string" },
            title: { type: "string" },
            description: { type: "string" },
            priority: { type: "number" },
            impact: { type: "number" },
            effort: { type: "number" },
            source: { type: "string" },
            external_id: { type: "string" }
          }
        }
      },
      {
        id: "agentflow_move_task",
        when: "Move a task status via AgentFlow CLI",
        inputSchema: {
          type: "object",
          required: ["task_id", "to_status"],
          properties: {
            task_id: { type: "number" },
            to_status: { type: "string" },
            note: { type: "string" }
          }
        }
      },
      {
        id: "agentflow_task_detail",
        when: "Read one task detail with runs/history",
        inputSchema: { type: "object", required: ["task_id"], properties: { task_id: { type: "number" } } }
      },
      {
        id: "agentflow_recent_runs",
        when: "Read recent runs in a project",
        inputSchema: {
          type: "object",
          properties: {
            project: { type: "string" },
            limit: { type: "number" }
          }
        }
      },
      {
        id: "agentflow_audit",
        when: "Read audit/status transition events",
        inputSchema: {
          type: "object",
          properties: {
            project: { type: "string" },
            limit: { type: "number" }
          }
        }
      }
    ],
    httpRoutes: [
      { method: "GET", path: "/agentflow/capabilities", when: "Capability discovery for agents" },
      { method: "POST", path: "/agentflow/webhook/comment", when: "Issue comment trigger ingress" },
      { method: "POST", path: "/agentflow/webhook/issues", when: "Scheduled discovery ingress" },
      { method: "POST", path: "/agentflow/webhook/github", when: "Generic GitHub event ingress" }
    ],
    workflow: [
      "discover: webhook/issues payload -> AgentFlow task ingestion",
      "triage: inspect board/status with agentflow_status",
      "execute: run one task with agentflow.run",
      "observe: inspect run/audit from AgentFlow web console"
    ]
  };
}

function formatHelpText(doc: CapabilityDoc, mode: string): string {
  if (mode === "quickstart") {
    return [
      "AgentFlow OpenClaw Plugin Quickstart",
      `defaults: project=${doc.defaults.project}, adapter=${doc.defaults.adapter}, agent=${doc.defaults.agent}`,
      "1) use tool agentflow_capabilities(mode=full) when agent is unsure",
      "2) run queue task with command agentflow.run",
      "3) inspect board text with tool agentflow_status(project=...)",
      "4) send comment webhook to /agentflow/webhook/comment for event-driven run"
    ].join("\n");
  }
  return JSON.stringify(doc, null, 2);
}

function toolTextPayload(raw: any): string {
  if (raw && typeof raw === "object") {
    if (typeof raw.content === "string") return raw.content;
    if (Array.isArray(raw.content)) {
      const textParts = raw.content
        .filter((x) => x && typeof x === "object" && x.type === "text")
        .map((x) => String(x.text || ""));
      if (textParts.length) return textParts.join("\n");
    }
  }
  if (typeof raw === "string") return raw;
  return JSON.stringify(raw ?? {});
}

function toolDataPayload(raw: any): unknown {
  if (raw && typeof raw === "object" && "data" in raw) return raw.data;
  return undefined;
}

function registerToolCompat(api: any, spec: LegacyToolDef): void {
  const canonical = {
    name: spec.id,
    description: spec.description,
    parameters: spec.inputSchema,
    async execute(_id: string, params: any) {
      const raw = await spec.run(params ?? {});
      const text = toolTextPayload(raw);
      const data = toolDataPayload(raw);
      return data !== undefined
        ? { content: [{ type: "text", text }], data }
        : { content: [{ type: "text", text }] };
    },
  };
  try {
    api.registerTool?.(canonical);
  } catch {
    api.registerTool?.(spec);
  }
}

export default definePluginEntry({
  id: "agentflow",
  name: "AgentFlow",
  register(api: any) {
    const cfg: PluginConfig = (api?.config ?? {}) as PluginConfig;
    const dbPath = cfg.dbPath || "./data/agentflow.db";
    const defaultProject = cfg.defaultProject || "default";
    const defaultAdapter = cfg.defaultAdapter || "openclaw";
    const defaultAgentName = cfg.defaultAgentName || "openclaw-agent";
    const capabilitiesDoc = buildCapabilitiesDoc({
      dbPath,
      project: defaultProject,
      adapter: defaultAdapter,
      agent: defaultAgentName
    });

    api.registerCommand?.({
      id: "agentflow.run",
      description: "Run one AgentFlow task through adapter",
      async handler(input: { project?: string; adapter?: string; agent?: string }) {
        const project = input?.project || defaultProject;
        const adapter = input?.adapter || defaultAdapter;
        const agent = input?.agent || defaultAgentName;
        const result = await runAgentflow([
          "--db",
          dbPath,
          "run-once",
          "--project",
          project,
          "--adapter",
          adapter,
          "--agent",
          agent
        ]);
        return { ok: true, output: result.stdout || result.stderr };
      }
    });

    api.registerCommand?.({
      id: "agentflow.create",
      description: "Create one AgentFlow task",
      async handler(input: {
        project?: string;
        title?: string;
        description?: string;
        priority?: number;
        impact?: number;
        effort?: number;
        source?: string;
        external_id?: string;
      }) {
        if (!input?.title) {
          return { ok: false, output: "title is required" };
        }
        const project = input?.project || defaultProject;
        const args = ["--db", dbPath, "add-task", "--project", project, "--title", String(input.title)];
        if (input.description) args.push("--description", String(input.description));
        if (input.priority !== undefined) args.push("--priority", String(input.priority));
        if (input.impact !== undefined) args.push("--impact", String(input.impact));
        if (input.effort !== undefined) args.push("--effort", String(input.effort));
        if (input.source) args.push("--source", String(input.source));
        if (input.external_id) args.push("--external-id", String(input.external_id));
        const result = await runAgentflow(args);
        return { ok: true, output: result.stdout || result.stderr };
      }
    });

    api.registerCommand?.({
      id: "agentflow.move",
      description: "Move one AgentFlow task to a target status",
      async handler(input: { task_id?: number; to_status?: string; note?: string }) {
        if (!Number.isFinite(Number(input?.task_id)) || !input?.to_status) {
          return { ok: false, output: "task_id and to_status are required" };
        }
        const args = ["--db", dbPath, "move", String(Number(input.task_id)), String(input.to_status)];
        if (input.note) args.push("--note", String(input.note));
        const result = await runAgentflow(args);
        return { ok: true, output: result.stdout || result.stderr };
      }
    });

    api.registerCommand?.({
      id: "agentflow.detail",
      description: "Get task detail with runs and history",
      async handler(input: { task_id?: number }) {
        if (!Number.isFinite(Number(input?.task_id))) {
          return { ok: false, output: "task_id is required" };
        }
        const result = await runAgentflow([
          "--db",
          dbPath,
          "task-detail",
          "--task-id",
          String(Number(input.task_id)),
          "--json"
        ]);
        const data = parseStructuredOutput(result.stdout);
        return data !== null ? { ok: true, output: JSON.stringify(data), data } : { ok: true, output: result.stdout || result.stderr };
      }
    });

    api.registerCommand?.({
      id: "agentflow.audit",
      description: "List recent status transition audit events",
      async handler(input: { project?: string; limit?: number }) {
        const project = input?.project || defaultProject;
        const limit = Number.isFinite(Number(input?.limit)) ? Number(input?.limit) : 30;
        const result = await runAgentflow([
          "--db",
          dbPath,
          "audit",
          "--project",
          project,
          "--limit",
          String(Math.max(1, Math.min(200, limit))),
          "--json"
        ]);
        const data = parseStructuredOutput(result.stdout);
        return data !== null ? { ok: true, output: JSON.stringify(data), data } : { ok: true, output: result.stdout || result.stderr };
      }
    });

    api.registerCommand?.({
      id: "agentflow.help",
      description: "Show AgentFlow capability guidance for agents",
      async handler(input: { mode?: string }) {
        const mode = input?.mode || "quickstart";
        return { ok: true, output: formatHelpText(capabilitiesDoc, mode) };
      }
    });

    registerToolCompat(api, {
      id: "agentflow_status",
      description: "Read AgentFlow queue status",
      inputSchema: {
        type: "object",
        properties: {
          project: { type: "string" }
        }
      },
      async run(input: { project?: string }) {
        const project = input?.project || defaultProject;
        const result = await runAgentflow(["--db", dbPath, "board", "--project", project, "--json"]);
        const data = parseStructuredOutput(result.stdout);
        return data !== null ? { content: JSON.stringify(data), data } : { content: result.stdout || result.stderr };
      }
    });

    registerToolCompat(api, {
      id: "agentflow_capabilities",
      description: "Describe AgentFlow plugin capabilities, routes, and usage",
      inputSchema: {
        type: "object",
        properties: {
          mode: { type: "string", enum: ["quickstart", "full"] }
        }
      },
      async run(input: { mode?: string }) {
        const mode = input?.mode || "full";
        if (mode === "quickstart") {
          return { content: formatHelpText(capabilitiesDoc, "quickstart") };
        }
        return { content: JSON.stringify(capabilitiesDoc, null, 2) };
      }
    });

    registerToolCompat(api, {
      id: "agentflow_create_task",
      description: "Create a task in AgentFlow",
      inputSchema: {
        type: "object",
        required: ["project", "title"],
        properties: {
          project: { type: "string" },
          title: { type: "string" },
          description: { type: "string" },
          priority: { type: "number" },
          impact: { type: "number" },
          effort: { type: "number" },
          source: { type: "string" },
          external_id: { type: "string" }
        }
      },
      async run(input: {
        project: string;
        title: string;
        description?: string;
        priority?: number;
        impact?: number;
        effort?: number;
        source?: string;
        external_id?: string;
      }) {
        const args = ["--db", dbPath, "add-task", "--project", input.project, "--title", input.title];
        if (input.description) args.push("--description", String(input.description));
        if (input.priority !== undefined) args.push("--priority", String(input.priority));
        if (input.impact !== undefined) args.push("--impact", String(input.impact));
        if (input.effort !== undefined) args.push("--effort", String(input.effort));
        if (input.source) args.push("--source", String(input.source));
        if (input.external_id) args.push("--external-id", String(input.external_id));
        const result = await runAgentflow(args);
        return { content: result.stdout || result.stderr };
      }
    });

    registerToolCompat(api, {
      id: "agentflow_move_task",
      description: "Move task to another status",
      inputSchema: {
        type: "object",
        required: ["task_id", "to_status"],
        properties: {
          task_id: { type: "number" },
          to_status: { type: "string" },
          note: { type: "string" }
        }
      },
      async run(input: { task_id: number; to_status: string; note?: string }) {
        const args = ["--db", dbPath, "move", String(input.task_id), String(input.to_status)];
        if (input.note) args.push("--note", String(input.note));
        const result = await runAgentflow(args);
        return { content: result.stdout || result.stderr };
      }
    });

    registerToolCompat(api, {
      id: "agentflow_task_detail",
      description: "Read one task detail",
      inputSchema: {
        type: "object",
        required: ["task_id"],
        properties: { task_id: { type: "number" } }
      },
      async run(input: { task_id: number }) {
        const result = await runAgentflow(["--db", dbPath, "task-detail", "--task-id", String(input.task_id), "--json"]);
        const data = parseStructuredOutput(result.stdout);
        return data !== null ? { content: JSON.stringify(data), data } : { content: result.stdout || result.stderr };
      }
    });

    registerToolCompat(api, {
      id: "agentflow_recent_runs",
      description: "Read recent runs for a project",
      inputSchema: {
        type: "object",
        properties: {
          project: { type: "string" },
          limit: { type: "number" }
        }
      },
      async run(input: { project?: string; limit?: number }) {
        const project = input?.project || defaultProject;
        const limit = Number.isFinite(Number(input?.limit)) ? Number(input?.limit) : 20;
        const result = await runAgentflow([
          "--db",
          dbPath,
          "recent-runs",
          "--project",
          project,
          "--limit",
          String(Math.max(1, Math.min(200, limit))),
          "--json"
        ]);
        const data = parseStructuredOutput(result.stdout);
        return data !== null ? { content: JSON.stringify(data), data } : { content: result.stdout || result.stderr };
      }
    });

    registerToolCompat(api, {
      id: "agentflow_audit",
      description: "Read recent status transition events",
      inputSchema: {
        type: "object",
        properties: {
          project: { type: "string" },
          limit: { type: "number" }
        }
      },
      async run(input: { project?: string; limit?: number }) {
        const project = input?.project || defaultProject;
        const limit = Number.isFinite(Number(input?.limit)) ? Number(input?.limit) : 30;
        const result = await runAgentflow([
          "--db",
          dbPath,
          "audit",
          "--project",
          project,
          "--limit",
          String(Math.max(1, Math.min(200, limit))),
          "--json"
        ]);
        const data = parseStructuredOutput(result.stdout);
        return data !== null ? { content: JSON.stringify(data), data } : { content: result.stdout || result.stderr };
      }
    });

    api.registerHttpRoute?.({
      method: "GET",
      path: "/agentflow/capabilities",
      async handler(req: any) {
        const mode = req?.query?.mode === "quickstart" ? "quickstart" : "full";
        if (mode === "quickstart") {
          return { status: 200, body: { ok: true, text: formatHelpText(capabilitiesDoc, "quickstart") } };
        }
        return { status: 200, body: { ok: true, capabilities: capabilitiesDoc } };
      }
    });

    api.registerHttpRoute?.({
      method: "POST",
      path: "/agentflow/webhook/comment",
      async handler(req: any) {
        const payload = req?.body ?? {};
        const project = payload?.project || defaultProject;
        const adapter = payload?.adapter || defaultAdapter;
        const agent = payload?.agent || defaultAgentName;

        const result = await runWithTempJson("agentflow-comment", payload, (tmp) => [
          "--db",
          dbPath,
          "handle-comment",
          "--project",
          project,
          "--payload-file",
          tmp,
          "--adapter",
          adapter,
          "--agent",
          agent
        ]);
        return { status: 200, body: { ok: true, output: result.stdout || result.stderr } };
      }
    });

    api.registerHttpRoute?.({
      method: "POST",
      path: "/agentflow/webhook/issues",
      async handler(req: any) {
        const payload = req?.body ?? {};
        const project = payload?.project || defaultProject;
        const normalized = Array.isArray(payload?.issues)
          ? payload.issues
          : Array.isArray(payload)
            ? payload
            : payload?.number
              ? [payload]
              : [];
        const result = await runWithTempJson("agentflow-issues", normalized, (tmp) => [
          "--db",
          dbPath,
          "discover-issues",
          "--project",
          project,
          "--from-file",
          tmp
        ]);
        return { status: 200, body: { ok: true, output: result.stdout || result.stderr } };
      }
    });

    api.registerHttpRoute?.({
      method: "POST",
      path: "/agentflow/webhook/github",
      async handler(req: any) {
        const payload = req?.body ?? {};
        const project = payload?.project || defaultProject;
        const adapter = payload?.adapter || defaultAdapter;
        const agent = payload?.agent || defaultAgentName;
        const event =
          String(req?.headers?.["x-github-event"] || req?.headers?.["X-GitHub-Event"] || "").toLowerCase();

        if (event === "issues") {
          const issue = payload?.issue && typeof payload.issue === "object" ? payload.issue : null;
          const action = String(payload?.action || "");
          const issues = issue && (action === "opened" || action === "reopened") ? [issue] : [];
          const result = await runWithTempJson("agentflow-gh-issues", issues, (tmp) => [
            "--db",
            dbPath,
            "discover-issues",
            "--project",
            project,
            "--from-file",
            tmp
          ]);
          return { status: 200, body: { ok: true, event, output: result.stdout || result.stderr } };
        }

        const result = await runWithTempJson("agentflow-gh-comment", payload, (tmp) => [
          "--db",
          dbPath,
          "handle-comment",
          "--project",
          project,
          "--payload-file",
          tmp,
          "--adapter",
          adapter,
          "--agent",
          agent
        ]);
        return { status: 200, body: { ok: true, event: event || "unknown", output: result.stdout || result.stderr } };
      }
    });
  }
});
