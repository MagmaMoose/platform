import { DEFAULT_TENANT_ID, type Env } from "./env";
import { newId, nowSeconds } from "./ids";
import { meetsSeverity, type AlertKind, type RouteKind, type Severity } from "./schema";

export interface AlertInput {
  severity: Severity;
  kind: AlertKind;
  title: string;
  payload: Record<string, unknown>;
  agent_id?: string;
  device_id?: string;
  job_id?: string;
  // The tenant this alert belongs to. If omitted, it's resolved from agent_id
  // (else the default tenant). Determines which alert routes receive it.
  tenant_id?: string;
}

export interface StoredAlert extends AlertInput {
  id: string;
  created_at: number;
}

interface RouteRow {
  id: string;
  name: string;
  kind: RouteKind;
  url: string;
  events: string | null;
  min_severity: Severity;
  enabled: number;
}

const SEVERITY_COLOR_SLACK: Record<Severity, string> = {
  info: "#3aa3e3",
  warning: "#f2c744",
  critical: "#d72631",
};

const SEVERITY_COLOR_DISCORD: Record<Severity, number> = {
  info: 0x3aa3e3,
  warning: 0xf2c744,
  critical: 0xd72631,
};

// Which Slack channel an alert lands in, chosen by kind (not severity):
//   success → SLACK_SUCCESS_CHANNEL  (#mikrotik-minder)   — good news / wins
//   info    → SLACK_INFO_CHANNEL     (#engineering-info)  — config changes
//   failure → SLACK_FAILURE_CHANNEL  (#engineering-alerts) — needs attention
const SLACK_CHANNEL_CLASS: Record<AlertKind, "success" | "info" | "failure"> = {
  heartbeat_recovered: "success",
  backup_succeeded: "success",
  update_applied: "success",
  manual: "success",
  drift_detected: "info",
  heartbeat_missed: "failure",
  job_failed: "failure",
  update_available: "failure",
  update_failed: "failure",
  restore_due: "failure",
};

export async function fireAlert(
  env: Env,
  input: AlertInput,
  ctx?: { waitUntil(p: Promise<unknown>): void },
): Promise<string> {
  const id = newId("alert");
  const created = nowSeconds();
  const tenantId = input.tenant_id ?? (await resolveAlertTenant(env, input.agent_id));
  await env.DB.prepare(
    `INSERT INTO alerts (id, severity, kind, agent_id, device_id, job_id, title, payload, created_at, tenant_id)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)`,
  )
    .bind(
      id,
      input.severity,
      input.kind,
      input.agent_id ?? null,
      input.device_id ?? null,
      input.job_id ?? null,
      input.title,
      JSON.stringify(input.payload),
      created,
      tenantId,
    )
    .run();

  const stored: StoredAlert = { ...input, id, created_at: created, tenant_id: tenantId };
  const dispatch = deliverAlert(env, stored);
  if (ctx) ctx.waitUntil(dispatch);
  else await dispatch;
  return id;
}

export async function deliverAlert(env: Env, alert: StoredAlert): Promise<void> {
  const routes = await pickRoutes(env, alert);
  const work: Promise<unknown>[] = routes.map((r) => deliverToRoute(env, alert, r));
  // The env-configured Slack bot integration fires for every alert, alongside
  // any DB-configured webhook/discord routes.
  if (env.SLACK_BOT_TOKEN) {
    work.push(deliverToSlackBot(env, alert));
  }
  if (work.length === 0) return;
  await Promise.all(work);
}

/**
 * Post an alert to Slack via chat.postMessage using a bot token.
 *
 * The channel is chosen by alert kind (see SLACK_CHANNEL_CLASS): wins →
 * SUCCESS, config changes → INFO, everything else → FAILURE. INFO falls back
 * to FAILURE when SLACK_INFO_CHANNEL is unset; an unset target channel is
 * simply skipped.
 */
async function deliverToSlackBot(env: Env, alert: StoredAlert): Promise<void> {
  const cls = SLACK_CHANNEL_CLASS[alert.kind];
  const channel =
    cls === "success"
      ? env.SLACK_SUCCESS_CHANNEL
      : cls === "info"
        ? env.SLACK_INFO_CHANNEL || env.SLACK_FAILURE_CHANNEL
        : env.SLACK_FAILURE_CHANNEL;
  if (!channel) return; // no channel configured for this class

  try {
    const res = await fetch("https://slack.com/api/chat.postMessage", {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.SLACK_BOT_TOKEN}`,
        "content-type": "application/json; charset=utf-8",
      },
      body: JSON.stringify(slackBotMessage(alert, channel, env.PRO_UI_URL)),
    });
    // Slack returns HTTP 200 even for logical failures; the body carries `ok`.
    const data = (await res.json().catch(() => ({}))) as { ok?: boolean; error?: string };
    if (!res.ok || !data.ok) {
      console.error("slack chat.postMessage failed", res.status, data.error ?? "(no body)");
    }
  } catch (err) {
    console.error("slack chat.postMessage threw", err instanceof Error ? err.message : err);
  }
}

// An alert belongs to its agent's tenant (or the default tenant when there's no
// agent, e.g. a manual test). Routing is then confined to that tenant's routes.
async function resolveAlertTenant(env: Env, agentId?: string): Promise<string> {
  if (agentId) {
    const row = await env.DB.prepare("SELECT tenant_id FROM agents WHERE id = ?1")
      .bind(agentId)
      .first<{ tenant_id: string | null }>();
    if (row?.tenant_id) return row.tenant_id;
  }
  return DEFAULT_TENANT_ID;
}

async function pickRoutes(env: Env, alert: StoredAlert): Promise<RouteRow[]> {
  const { results } = await env.DB.prepare(
    "SELECT id, name, kind, url, events, min_severity, enabled FROM alert_routes WHERE enabled = 1 AND tenant_id = ?1",
  )
    .bind(alert.tenant_id ?? DEFAULT_TENANT_ID)
    .all<RouteRow>();
  return results.filter((r) => {
    if (!meetsSeverity(alert.severity, r.min_severity)) return false;
    if (r.events) {
      try {
        const list = JSON.parse(r.events) as string[];
        if (!list.includes(alert.kind)) return false;
      } catch {
        return false;
      }
    }
    return true;
  });
}

async function deliverToRoute(env: Env, alert: StoredAlert, route: RouteRow): Promise<void> {
  const body = formatBody(alert, route.kind);
  let status: "ok" | "failed" = "failed";
  let httpStatus: number | null = null;
  let error: string | null = null;
  try {
    const res = await fetch(route.url, {
      method: "POST",
      headers: { "content-type": "application/json", "user-agent": "mikrotik-minder/0.1" },
      body: JSON.stringify(body),
    });
    httpStatus = res.status;
    status = res.ok ? "ok" : "failed";
    if (!res.ok) error = `HTTP ${res.status}`;
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }

  await env.DB.prepare(
    `INSERT INTO alert_deliveries (id, alert_id, route_id, status, http_status, error, delivered_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)`,
  )
    .bind(newId("dlv"), alert.id, route.id, status, httpStatus, error, nowSeconds())
    .run();
}

function formatBody(alert: StoredAlert, kind: RouteKind): unknown {
  if (kind === "slack") return slackBody(alert);
  if (kind === "discord") return discordBody(alert);
  return genericBody(alert);
}

function slackBody(alert: StoredAlert) {
  return {
    text: `Mikrotik Minder: ${alert.kind}`,
    attachments: [
      {
        color: SEVERITY_COLOR_SLACK[alert.severity],
        title: alert.title,
        fields: [
          { title: "Severity", value: alert.severity, short: true },
          { title: "Kind", value: alert.kind, short: true },
          ...renderFields(alert),
        ],
        footer: "mikrotik-minder",
        ts: alert.created_at,
      },
    ],
  };
}

function discordBody(alert: StoredAlert) {
  return {
    username: "Mikrotik Minder",
    embeds: [
      {
        title: alert.title,
        color: SEVERITY_COLOR_DISCORD[alert.severity],
        fields: [
          { name: "Severity", value: alert.severity, inline: true },
          { name: "Kind", value: alert.kind, inline: true },
          ...renderFields(alert).map((f) => ({
            name: f.title,
            value: f.value,
            inline: f.short ?? false,
          })),
        ],
        timestamp: new Date(alert.created_at * 1000).toISOString(),
      },
    ],
  };
}

function genericBody(alert: StoredAlert) {
  return {
    id: alert.id,
    severity: alert.severity,
    kind: alert.kind,
    title: alert.title,
    agent_id: alert.agent_id ?? null,
    device_id: alert.device_id ?? null,
    job_id: alert.job_id ?? null,
    payload: alert.payload,
    created_at: alert.created_at,
  };
}

const SEVERITY_EMOJI: Record<Severity, string> = {
  info: ":white_check_mark:",
  warning: ":warning:",
  critical: ":rotating_light:",
};

/** Block Kit message for the Slack Web API `chat.postMessage`. */
function slackBotMessage(alert: StoredAlert, channel: string, proUiUrl?: string) {
  const detailLines = renderFields(alert)
    .map((f) => `*${f.title}:* ${f.value}`)
    .join("\n");
  // Build a deep link to the Pro UI device page when we can. The device page
  // hosts the "Backups" section + the timeline, so for kinds that have a
  // download or follow-up action this is where the operator actually wants
  // to land. We append it as a Block Kit action button so it renders well
  // both inline and as the notification preview.
  const linkButton = proUiUrl && alert.device_id
    ? {
        type: "actions",
        elements: [
          {
            type: "button",
            text: { type: "plain_text", text: actionLabelFor(alert.kind), emoji: true },
            url: `${proUiUrl.replace(/\/$/, "")}/devices/${encodeURIComponent(alert.device_id)}`,
            style: alert.severity === "critical" ? "danger" : undefined,
          },
        ],
      }
    : null;
  return {
    channel,
    // `text` is the notification fallback (lockscreen / a11y).
    text: `${alert.severity.toUpperCase()} · ${alert.title}`,
    blocks: [
      {
        type: "header",
        text: {
          type: "plain_text",
          text: `${SEVERITY_EMOJI[alert.severity]} ${alert.title}`.slice(0, 150),
          emoji: true,
        },
      },
      {
        type: "section",
        fields: [
          { type: "mrkdwn", text: `*Severity:*\n${alert.severity}` },
          { type: "mrkdwn", text: `*Kind:*\n${alert.kind}` },
        ],
      },
      ...(detailLines
        ? [{ type: "section", text: { type: "mrkdwn", text: detailLines.slice(0, 2900) } }]
        : []),
      ...(linkButton ? [linkButton] : []),
      {
        type: "context",
        elements: [
          {
            type: "mrkdwn",
            text: `mikrotik-minder · alert \`${alert.id}\` · <!date^${alert.created_at}^{date_short_pretty} {time}|just now>`,
          },
        ],
      },
    ],
  };
}

// What the "View in Pro" CTA button says depends on the alert kind. The
// generic label is "Open device"; backup_succeeded gets a more specific
// "Download backup" hint so operators know they can fetch the body from
// there.
function actionLabelFor(kind: string): string {
  if (kind === "backup_succeeded") return "Download backup";
  if (kind === "update_applied") return "View update";
  return "Open device";
}

function renderFields(alert: StoredAlert): { title: string; value: string; short?: boolean }[] {
  const out: { title: string; value: string; short?: boolean }[] = [];
  for (const [k, v] of Object.entries(alert.payload)) {
    if (v == null) continue;
    const str = typeof v === "string" ? v : JSON.stringify(v);
    if (str.length > 200) continue;
    out.push({ title: k, value: str, short: str.length < 40 });
  }
  return out;
}
