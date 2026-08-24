---
name: build-a-scene
description: Building CoppeliaSim scenes from code — walls with doorways, floors, obstacles, and the three independent properties (dynamic, respondable, detectable) that decide whether an object falls, collides or is visible to a sensor. Includes how to verify in code that a robot fits and that every area is reachable. Use when creating or changing a scene's geometry.
---

# Building a scene from code

## The three properties, and why they get confused

A CoppeliaSim object has three **independent** switches. Almost every scene
problem comes from mixing them up:

| Property | What it decides | When it is wrong |
|---|---|---|
| `dynamic` | whether physics moves it (falls, gets pushed) | the scenery collapses on Play |
| `respondable` | whether other bodies collide with it | the robot drives through walls |
| `detectable` | whether a proximity sensor sees it | the sensor "doesn't work" |

A scenery wall is **not dynamic, respondable and detectable**:

```python
sim.setBoolProperty(handle, "dynamic", False)
sim.setBoolProperty(handle, "respondable", True)
sim.setObjectInt32Param(handle, sim.shapeintparam_respondable_mask, 0xFFFF)
sim.setBoolProperty(handle, "detectable", True)
```

**`detectable` is the number one cause of "my sensor detects nothing".** It is
neither inherited nor set automatically: a freshly created object is invisible to
every proximity sensor until you set it.

## Decorative floors must not be solid

If you colour each room's floor with a thin box, that box must **not** be
respondable or collidable. A 1 cm floor is a 1 cm step in every doorway, and the
robot trips over it or gets stuck.

Leave them as pure decoration: not dynamic, not respondable, not detectable. The
robot rolls on the real ground, not on the colour layer.

## The default floor is 5 x 5 m

`/Floor` ships with the scene and is small for almost any floor plan. If your
scene is bigger, delete it and create ground of the size you need, or the robot
will drive off the edge halfway through.

## Walls with doorways

A wall with a door is not one object: it is two segments with a gap between
them. Generate the segments from the full line plus the list of openings rather
than placing each piece by hand — that way the numbers come from one place and
moving a door forces no recalculation:

```python
def wall_segments(start, end, doors):
    """Returns the wall pieces between start and end, skipping the openings."""
```

Dimensions that work in practice: 0.90 m doorways and 1.20 m corridors let a
robot of roughly 0.40 x 0.25 m pass and turn around. Check the clearance rather
than assuming it.

## Names and hierarchy

Hang everything off an aliased root (`/House`, `/Robot`). That makes `clean()` a
one-liner and the scene readable at a glance.

**Re-parenting renumbers siblings.** After hanging `/Cylinder[1]` off a chassis,
`/Cylinder[3]` may become `/Cylinder[1]`. If you re-parent several times in a
row, list again between calls, or resolve every handle up front. A script that
assumes stable names breaks in ways that are very hard to read.

## Verifying that the scene is usable

Building is not finishing. Two checks that earn their keep:

**1. Rasterise and measure clearance.** Project the wall footprints onto a grid
and check that each doorway leaves room for the robot's turning radius.

**2. Reachability by BFS.** From the entrance, walk the grid with a queue and
confirm every area is reached. It is about fifteen lines and instantly catches
the room that got walled off by a 10 cm mistake:

```python
from collections import deque

def reachable(grid, origin, start):
    seen, queue = {start}, deque([start])
    while queue:
        x, y = queue.popleft()
        for n in ((x+1,y), (x-1,y), (x,y+1), (x,y-1)):
            if free(grid, n) and n not in seen:
                seen.add(n); queue.append(n)
    return seen
```

Printing the grid as ASCII in the terminal is the fastest way to see what
happened. A top-down view in characters reveals a walled-off doorway faster than
looking at the 3D scene.

## At the end, and only at the end

Save the scene **after** verifying. Saving first leaves a broken `.ttt` that
looks fine.
