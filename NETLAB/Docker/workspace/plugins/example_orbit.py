"""Keep relays on a gentle orbit around the station."""
NAME = "Orbit Keeper"
VERSION = "1.0.0"
AUTHOR = "NETLAB"
DESCRIPTION = "Distributes relays evenly on a circle and holds station."
import math
def plan_positions(context):
    relays = context.get("relays", []); n = max(1, len(relays))
    r = context.get("coverage_m", 90); sx, sy, sz = context.get("station", [0,0,0])
    return {rid: [sx + r*math.cos(2*math.pi*i/n), sy + r*math.sin(2*math.pi*i/n), 40.0] for i, rid in enumerate(relays)}
def on_failure(context, failed_index):
    return None
