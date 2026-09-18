import hashlib
import random

TYPES = ("DISCOVERY", "NPC_ENCOUNTER", "RESOURCE", "QUEST", "COMBAT", "LANDMARK", "REST", "RARE")
BIAS = {
    "generic_outdoor": (30, 20, 15, 10, 10, 5, 8, 2),
    "forest_path": (15, 15, 30, 10, 20, 3, 5, 2),
    "waterside": (20, 20, 10, 15, 5, 20, 8, 2),
    "settlement": (15, 35, 10, 20, 3, 7, 8, 2),
    "ancient_landmark": (10, 15, 5, 20, 10, 30, 5, 5),
}


def map_context(scene, confidence):
    if not scene or scene["scene_confidence"] < confidence:
        return {"archetype": "generic_outdoor", "objects": []}
    objects = [o["class"] for o in scene["objects"] if o["confidence"] >= confidence]
    kind = "generic_outdoor"
    if scene["scene"] in ("park", "trail", "forest_like") or "tree" in objects:
        kind = "forest_path"
    if scene["scene"] in ("riverside", "lake_side") or set(objects) & {"pond", "river", "bridge"}:
        kind = "waterside"
    if scene["scene"] in ("campus", "plaza", "urban_outdoor"):
        kind = "settlement"
    if "statue" in objects:
        kind = "ancient_landmark"
    return {"archetype": kind, "objects": objects, "scene": scene["scene"]}


def choose_event(seed, cell, context):
    digest = hashlib.sha256(f"{seed}:{cell}".encode()).hexdigest()
    rng = random.Random(int(digest, 16))
    kind = rng.choices(TYPES, weights=BIAS[context["archetype"]], k=1)[0]
    return "evt_"+digest[:24], kind
