/**
 * Stytch B2B session-JWT validation using **Web Crypto** — zero dependencies,
 * for the Cloudflare **Workers** runtime (the edge). Ported from the tested
 * dunmir worker path; claim extraction is shared via ./claims.
 *
 * RS256 is hard-pinned (the only algorithm Stytch signs with). Throws on ANY
 * failure — callers must treat a throw as "unauthenticated".
 */
import { type JwtPayload, type SessionClaims, claimsFromPayload } from "./claims";

export interface StytchJwksConfig {
  STYTCH_JWKS_URL?: string;
  STYTCH_ISSUER?: string;
  STYTCH_PROJECT_ID?: string;
}

const CLOCK_SKEW_SECONDS = 30;
const JWKS_TTL_MS = 10 * 60 * 1000;

let jwksCache: { url: string; at: number; keys: Map<string, CryptoKey> } | null = null;

function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

function b64urlToBytes(s: string): Uint8Array {
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/") + pad);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function b64urlToJson<T>(s: string): T {
  return JSON.parse(new TextDecoder().decode(b64urlToBytes(s))) as T;
}

interface Jwk {
  kid?: string;
  kty?: string;
  n?: string;
  e?: string;
}

async function loadJwks(env: StytchJwksConfig): Promise<Map<string, CryptoKey>> {
  if (!env.STYTCH_JWKS_URL) throw new Error("STYTCH_JWKS_URL not configured");
  if (
    jwksCache &&
    jwksCache.url === env.STYTCH_JWKS_URL &&
    Date.now() - jwksCache.at < JWKS_TTL_MS
  ) {
    return jwksCache.keys;
  }
  const res = await fetch(env.STYTCH_JWKS_URL, { headers: { accept: "application/json" } });
  if (!res.ok) throw new Error(`JWKS fetch failed (HTTP ${res.status})`);
  const body = (await res.json()) as { keys?: Jwk[] };
  const keys = new Map<string, CryptoKey>();
  for (const jwk of body.keys ?? []) {
    if (jwk.kty !== "RSA" || !jwk.kid || !jwk.n || !jwk.e) continue;
    keys.set(
      jwk.kid,
      await crypto.subtle.importKey(
        "jwk",
        { kty: "RSA", n: jwk.n, e: jwk.e, alg: "RS256", ext: true },
        { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
        false,
        ["verify"],
      ),
    );
  }
  jwksCache = { url: env.STYTCH_JWKS_URL, at: Date.now(), keys };
  return keys;
}

interface JwtHeader {
  alg?: string;
  kid?: string;
}

/**
 * Validate a Stytch B2B session JWT — RS256 signature against the project JWKS,
 * plus issuer / audience / expiry — with Web Crypto. Throws on ANY failure.
 */
export async function validateStytchSession(
  token: string,
  env: StytchJwksConfig,
): Promise<SessionClaims> {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("malformed JWT");
  const [headerB64, payloadB64, sigB64] = parts as [string, string, string];

  const header = b64urlToJson<JwtHeader>(headerB64);
  if (header.alg !== "RS256" || !header.kid) throw new Error("unexpected JWT header");

  const key = (await loadJwks(env)).get(header.kid);
  if (!key) throw new Error("unknown signing key (kid)");

  const valid = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    b64urlToBytes(sigB64),
    new TextEncoder().encode(`${headerB64}.${payloadB64}`),
  );
  if (!valid) throw new Error("bad signature");

  const payload = b64urlToJson<JwtPayload>(payloadB64);
  const now = nowSeconds();
  if (typeof payload.exp === "number" && now > payload.exp + CLOCK_SKEW_SECONDS) {
    throw new Error("session expired");
  }
  if (typeof payload.nbf === "number" && now < payload.nbf - CLOCK_SKEW_SECONDS) {
    throw new Error("session not yet valid");
  }
  if (env.STYTCH_ISSUER && payload.iss !== env.STYTCH_ISSUER) {
    throw new Error("bad issuer");
  }
  if (env.STYTCH_PROJECT_ID && !audienceMatches(payload.aud, env.STYTCH_PROJECT_ID)) {
    throw new Error("bad audience");
  }

  const claims = claimsFromPayload(payload);
  if (!claims) throw new Error("session missing member (sub) or organization_id");
  return claims;
}

function audienceMatches(aud: unknown, projectId: string): boolean {
  return aud === projectId || (Array.isArray(aud) && aud.includes(projectId));
}
