const ALPHABET = "0123456789abcdefghijkmnpqrstvwxyz";

export function newId(prefix: string): string {
  const random = new Uint8Array(10);
  crypto.getRandomValues(random);
  let suffix = "";
  for (const byte of random) {
    suffix += ALPHABET[byte % ALPHABET.length];
  }
  return `${prefix}_${suffix}`;
}

export function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}
