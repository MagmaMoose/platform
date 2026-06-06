/**
 * Stytch B2B claim extraction — the genuinely-shared core.
 *
 * This logic was duplicated VERBATIM across the mikrotik-minder worker
 * (`worker/src/stytch.ts`) and mikrotik-minder-pro (`src/lib/stytch.ts`); the
 * original comments even read "Mirrors the worker's tested extraction." This is
 * now the single source of truth. Dependency-free (pure object walking), so it
 * is safe to import from both Workers and Pages.
 *
 * Stytch B2B tokens carry `organization_id` under the `.../organization` claim
 * (NOT the session claim), and the email only inside the session's
 * authentication factors. The security guarantee is the signature / issuer /
 * audience / expiry checks performed by the validators; these helpers only
 * choose which org/member/email we resolve, and fail closed when a claim is
 * absent.
 */

export interface SessionClaims {
  memberId: string;
  organizationId: string;
  email: string | null;
}

export type JwtPayload = Record<string, unknown>;

export const STYTCH_SESSION_CLAIM = "https://stytch.com/session";
export const STYTCH_ORG_CLAIM = "https://stytch.com/organization";

export function claimObject(p: JwtPayload, ns: string): Record<string, unknown> | null {
  const c = p[ns];
  return c && typeof c === "object" ? (c as Record<string, unknown>) : null;
}

/** Resolve a string claim: top-level first, then the org and session namespaced claims. */
export function pickString(p: JwtPayload, key: string): string | null {
  const top = p[key];
  if (typeof top === "string") return top;
  for (const ns of [STYTCH_ORG_CLAIM, STYTCH_SESSION_CLAIM]) {
    const v = claimObject(p, ns)?.[key];
    if (typeof v === "string") return v;
  }
  return null;
}

/** Member email: direct `email_address` claim, else inside the session's auth factors. */
export function pickEmail(p: JwtPayload): string | null {
  const direct = pickString(p, "email_address");
  if (direct) return direct;
  const factors = claimObject(p, STYTCH_SESSION_CLAIM)?.["authentication_factors"];
  if (Array.isArray(factors)) {
    for (const f of factors) {
      const ef = f && typeof f === "object" ? (f as Record<string, unknown>)["email_factor"] : null;
      const addr =
        ef && typeof ef === "object" ? (ef as Record<string, unknown>)["email_address"] : null;
      if (typeof addr === "string") return addr;
    }
  }
  return null;
}

/** Map a verified JWT payload → SessionClaims. Fails closed (null) if member/org absent. */
export function claimsFromPayload(p: JwtPayload): SessionClaims | null {
  const memberId = typeof p.sub === "string" ? p.sub : null;
  const organizationId = pickString(p, "organization_id");
  if (!memberId || !organizationId) return null;
  return { memberId, organizationId, email: pickEmail(p) };
}
