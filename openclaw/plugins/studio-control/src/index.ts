import { Type } from "@sinclair/typebox";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

import { createControlApiClient } from "./controlApi.js";

function mapToolToAction(toolName: string): string | null {
  const normalized = toolName.trim().toLowerCase();
  if (!normalized) return null;

  const exactMatches: Record<string, string> = {
    "git.push": "git_push",
    "pull_request": "pull_request",
    "pr.create": "pull_request",
    "file.write": "file_write",
    "file.edit": "file_write",
    "secret.read": "secret_access",
    "shell.rm": "destructive_shell",
    "shell.delete": "destructive_shell",
    "test.run": "test_run",
  };
  if (exactMatches[normalized]) return exactMatches[normalized];

  if (normalized.startsWith("http.") || normalized.startsWith("web.")) return "network_request";
  return null;
}

function extractTargetHost(args: Record<string, unknown> | undefined): string | undefined {
  const directHost = args?.targetHost;
  if (typeof directHost === "string" && directHost.trim()) return directHost.trim();

  const urlValue = args?.url;
  if (typeof urlValue !== "string" || !urlValue.trim()) return undefined;
  try {
    return new URL(urlValue).host;
  } catch {
    return undefined;
  }
}

function asText(payload: unknown): string {
  return JSON.stringify(payload, null, 2);
}

function buildQuery(params: Record<string, unknown>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    query.set(key, String(value));
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

export default definePluginEntry({
  id: "studio-control",
  name: "Studio Control",
  description: "Bridges OpenClaw to the AI Venture Studio control API.",
  register(api: any) {
    const apiAny = api as any;
    const getClient = () => createControlApiClient(apiAny.pluginConfig);

    apiAny.registerTool({
      name: "studio_attention",
      description: "Returns current founder attention items from the control plane.",
      parameters: Type.Object({
        limit: Type.Optional(Type.Number({ minimum: 1, maximum: 100 })),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const limit = Number(params?.limit ?? 20);
        const payload = await client.get(`/v1/attention?limit=${limit}`);
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_tasks",
      description: "Lists tracked tasks so the chief can see queued, blocked, or active work.",
      parameters: Type.Object({
        limit: Type.Optional(Type.Number({ minimum: 1, maximum: 100 })),
        status: Type.Optional(Type.String()),
        venture: Type.Optional(Type.String()),
        requestedBy: Type.Optional(Type.String()),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const payload = await client.get(
          `/v1/tasks${buildQuery({
            limit: Number(params?.limit ?? 20),
            status: params?.status,
            venture: params?.venture,
            requested_by: params?.requestedBy,
          })}`
        );
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_task_state",
      description: "Returns the latest control-plane state for one task.",
      parameters: Type.Object({
        taskId: Type.Number(),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const taskId = Number(params?.taskId);
        const payload = await client.get(`/v1/tasks/${taskId}/state`);
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_create_task",
      description: "Creates a new tracked task in the control plane.",
      parameters: Type.Object({
        title: Type.String({ minLength: 1 }),
        description: Type.String({ minLength: 1 }),
        category: Type.String({ minLength: 1 }),
        ideaId: Type.Optional(Type.Number()),
        targetRepo: Type.Optional(Type.String()),
        venture: Type.Optional(Type.String()),
        requestedBy: Type.Optional(Type.String()),
        slackChannelId: Type.Optional(Type.String()),
        slackThreadTs: Type.Optional(Type.String()),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const payload = await client.post("/v1/tasks", {
          idea_id: params?.ideaId,
          title: params?.title,
          description: params?.description,
          category: params?.category,
          target_repo: params?.targetRepo,
          venture: params?.venture,
          requested_by: params?.requestedBy,
          slack_channel_id: params?.slackChannelId,
          slack_thread_ts: params?.slackThreadTs,
        });
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_pending_approvals",
      description: "Returns unresolved approval requests.",
      parameters: Type.Object({
        limit: Type.Optional(Type.Number({ minimum: 1, maximum: 100 })),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const limit = Number(params?.limit ?? 20);
        const payload = await client.get(`/v1/approvals/pending?limit=${limit}`);
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_resolve_approval",
      description: "Approves or denies an approval request on behalf of a trusted Slack user.",
      parameters: Type.Object({
        approvalId: Type.Number(),
        slackUserId: Type.String({ minLength: 1 }),
        resolution: Type.Union([Type.Literal("approved"), Type.Literal("denied")]),
        note: Type.Optional(Type.String()),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const approvalId = Number(params?.approvalId);
        const payload = await client.post(`/v1/approvals/${approvalId}/resolve`, {
          slack_user_id: params?.slackUserId,
          resolution: params?.resolution,
          note: params?.note,
        });
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_create_signal",
      description: "Creates a routed control-plane signal and attention item when needed.",
      parameters: Type.Object({
        source: Type.String(),
        kind: Type.String(),
        severity: Type.String(),
        summary: Type.String(),
        task_id: Type.Optional(Type.Number()),
        venture: Type.Optional(Type.String()),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const payload = await client.post("/v1/signals", {
          source: params?.source,
          kind: params?.kind,
          severity: params?.severity,
          summary: params?.summary,
          task_id: params?.task_id,
          venture: params?.venture,
        });
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_complete_manual_verification",
      description: "Marks a task or story as manually checked so the queue can move again.",
      parameters: Type.Object({
        taskId: Type.Number(),
        storyId: Type.Optional(Type.String()),
        note: Type.Optional(Type.String()),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const taskId = Number(params?.taskId);
        const payload = await client.post(`/v1/tasks/${taskId}/manual-verification/complete`, {
          story_id: params?.storyId,
          note: params?.note ?? "Manual verification completed from OpenClaw.",
        });
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_requeue_task",
      description: "Puts a blocked or failed task back into the queue so a worker can retry it.",
      parameters: Type.Object({
        taskId: Type.Number(),
        note: Type.Optional(Type.String()),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const taskId = Number(params?.taskId);
        const payload = await client.post(`/v1/tasks/${taskId}/requeue`, {
          note: params?.note ?? "Requeued from OpenClaw.",
        });
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_agent_runs",
      description: "Lists recent worker runs so the chief can explain what happened and what is stuck.",
      parameters: Type.Object({
        limit: Type.Optional(Type.Number({ minimum: 1, maximum: 100 })),
        taskId: Type.Optional(Type.Number()),
        runKind: Type.Optional(Type.String()),
        status: Type.Optional(Type.String()),
        triggerSource: Type.Optional(Type.String()),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const payload = await client.get(
          `/v1/agent-runs${buildQuery({
            limit: Number(params?.limit ?? 20),
            task_id: params?.taskId,
            run_kind: params?.runKind,
            status: params?.status,
            trigger_source: params?.triggerSource,
          })}`
        );
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_recent_briefings",
      description: "Lists recent briefings so the chief can avoid repeating the same summary.",
      parameters: Type.Object({
        limit: Type.Optional(Type.Number({ minimum: 1, maximum: 100 })),
        scope: Type.Optional(Type.String()),
        deliveredTo: Type.Optional(Type.String()),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const payload = await client.get(
          `/v1/briefings${buildQuery({
            limit: Number(params?.limit ?? 10),
            scope: params?.scope,
            delivered_to: params?.deliveredTo,
          })}`
        );
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_generate_briefing",
      description: "Generates a fresh founder briefing from current attention items and stores it.",
      parameters: Type.Object({
        scope: Type.Optional(Type.String()),
        deliveredTo: Type.Optional(Type.String()),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const payload = await client.post("/v1/briefings/generate", {
          scope: params?.scope ?? "daily",
          delivered_to: params?.deliveredTo,
        });
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_run_worker_once",
      description: "Ask the control plane to advance one queued task by one worker pass.",
      parameters: Type.Object({
        workerId: Type.Optional(Type.String()),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const payload = await client.post("/v1/worker/run-once", {
          worker_id: params?.workerId,
        });
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerHook(
      "before_tool_call",
      async (event: any) => {
        const client = getClient();
        const toolName = event.tool?.name ?? event.toolName ?? "";
        const actionType = mapToolToAction(toolName);
        if (!actionType) return {};
        const taskId = Number(event.metadata?.taskId ?? 0);
        if (!Number.isFinite(taskId) || taskId <= 0) {
          return {
            block: true,
            reason: "Risky tool calls must be attached to a tracked task.",
          };
        }

        const evaluation = await client.post("/v1/policy/evaluate", {
          task_id: taskId,
          agent_run_id: event.metadata?.agentRunId,
          story_id: event.metadata?.storyId,
          agent_role: event.metadata?.agentRole ?? "implementer",
          tool_name: toolName,
          action_type: actionType,
          target_host: extractTargetHost(event.args),
          target_repo: event.metadata?.targetRepo,
          metadata: event.metadata ?? {},
        });

        if (evaluation.decision === "block") {
          return {
            block: true,
            reason: String(evaluation.reason),
          };
        }

        if (evaluation.decision === "require_approval") {
          return {
            requireApproval: true,
            reason: String(evaluation.reason),
          };
        }

        return {};
      },
      { priority: 50 }
    );
  },
});
