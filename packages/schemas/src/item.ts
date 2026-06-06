import { z } from "zod";

/**
 * Item — the canonical example entity from the golden-stack spec.
 * The matching Pydantic model lives in `python/platform_schemas/item.py`.
 * Keep the two shapes in lockstep: this is the single source of truth.
 */
export const Item = z.object({
  id: z.string().uuid(),
  name: z.string().min(1),
  created_at: z.string().datetime(),
});
export type Item = z.infer<typeof Item>;

export const ItemCreate = Item.pick({ name: true });
export type ItemCreate = z.infer<typeof ItemCreate>;
