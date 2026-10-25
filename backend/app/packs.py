"""Industry packs: everything industry-specific lives in packs/<id>.yaml, the engine never hard-codes it."""
from functools import lru_cache
from pathlib import Path

import yaml

PACK_DIR = Path(__file__).parent / "packs"
REQUIRED = {"id", "name", "vocabulary", "score", "signals", "synthetic"}


@lru_cache
def load_pack(pack_id: str) -> dict:
    path = PACK_DIR / f"{pack_id}.yaml"
    pack = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = REQUIRED - pack.keys()
    if missing:
        raise ValueError(f"pack {pack_id} is missing {sorted(missing)}")
    for key, sig in pack["signals"].items():
        for field in ("label", "weight", "definition", "keywords", "playbook"):
            if field not in sig:
                raise ValueError(f"pack {pack_id}: signal {key} is missing '{field}'")
    return pack


def list_packs() -> list[dict]:
    return [load_pack(p.stem) for p in sorted(PACK_DIR.glob("*.yaml"))]


def public_view(pack: dict) -> dict:
    """What the frontend needs: vocabulary and signal labels, not prompts or synthetic content."""
    return {
        "id": pack["id"], "name": pack["name"], "industry": pack["industry"],
        "vocabulary": pack["vocabulary"],
        "signals": {k: {"label": v["label"], "weight": v["weight"], "definition": v["definition"]}
                    for k, v in pack["signals"].items()},
        "bands": pack["score"]["bands"],
    }
