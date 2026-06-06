// @platform/cf-auth — shared Stytch B2B session auth for Cloudflare runtimes.
//
// Import the dependency-free claim core from the root, and pick a validator by
// runtime via the subpath exports:
//   import { claimsFromPayload, type SessionClaims } from "@platform/cf-auth";
//   import { validateStytchSession } from "@platform/cf-auth/webcrypto"; // Workers
//   import { validateSession }       from "@platform/cf-auth/jose";      // Pages
export * from "./claims";
