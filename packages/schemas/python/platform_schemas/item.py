"""Item — Pydantic v2 mirror of the zod schema in ../../src/item.ts.

Single source of truth: the two shapes (zod + Pydantic) must stay in lockstep.
Pydantic v2 only (model_config / field_validator) — never v1.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Item(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime


class ItemCreate(BaseModel):
    name: str
