/**
 * Stytch B2B session-JWT validation using **jose** — for the Cloudflare **Pages**
 * runtime (SvelteKit hooks). Ported from the dunmir-pro path; claim
 * extraction is shared via ./claims, so it stays in lockstep with the Worker's
 * Web Crypto validator (./webcrypto).
 *
 * Returns null on any failure (caller treats null as unauthenticated).
 */
import { createRemoteJWKSet, jwtVerify } from "jose";
import { type SessionClaims, claimsFromPayload } from "./claims";

export interface StytchJoseConfig {
  STYTCH_JWKS_URL?: string;
  STYTCH_ISSUER?: string;
  STYTCH_PROJECT_ID?: string;
}

let jwks: ReturnType<typeof createRemoteJWKSet> | null = null;
let jwksFor: string | null = null;

export async function validateSession(
  env: StytchJoseConfig,
  jwt: string,
): Promise<SessionClaims | null> {
  if (!env.STYTCH_JWKS_URL || !env.STYTCH_ISSUER || !env.STYTCH_PROJECT_ID) return null;
  try {
    if (!jwks || jwksFor !== env.STYTCH_JWKS_URL) {
      jwks = createRemoteJWKSet(new URL(env.STYTCH_JWKS_URL));
      jwksFor = env.STYTCH_JWKS_URL;
    }
    const { payload } = await jwtVerify(jwt, jwks, {
      issuer: env.STYTCH_ISSUER,
      audience: env.STYTCH_PROJECT_ID,
      algorithms: ["RS256"],
      clockTolerance: 30,
    });
    return claimsFromPayload(payload as Record<string, unknown>);
  } catch {
    return null;
  }
}
