---
name: project-structure
description: How to lay out a CoppeliaSim robotics project so it stays reproducible — one script per artifact, the connect/clean/create/build/verify order, and what belongs in the Python API versus what belongs in the MCP tools. Use when starting a CoppeliaSim project, adding a script to an existing one, or when someone asks where to begin.
---

# Structure of a CoppeliaSim project

A CoppeliaSim project you can hand in, re-run and grade has a specific shape.
This skill describes it. None of it is style: every piece solves a problem that
shows up every time.

## Before any code: what goes where

**Anything that must be reproducible is written in Python** against
`coppeliasim_zmqremoteapi_client`. That covers building the scene, assembling
the robot, and every control loop.

**MCP tools are for looking and checking**, not for building: list objects, read
a position, fire a sensor, see whether the simulation is running. A control loop
cannot fit through them, and forty walls is forty calls that leave no file
behind.

Rule of thumb: if the result must survive closing CoppeliaSim, it goes in a
script. If it is a question ("where did that wall end up?"), it goes in a tool.

## One script per artifact

Do not put the scene, the robot and the controller in one file. They change at
different rates: the scene is built once, the robot is tweaked twenty times, and
the controller runs constantly.

    scene.py       the world: floor, walls, obstacles
    robot.py       the robot inside it: chassis, joints, sensors
    control.py     what the robot does: teleop, navigation, the task

Each runs on its own and leaves the scene in a known state.

## The order of the functions

Scripts always follow the same sequence. Keeping it means anyone — including you
a month from now — knows where to look.

```python
def connect():
    return RemoteAPIClient(host=COPPELIA_HOST, port=COPPELIA_PORT).require("sim")

def clean(sim):
    """Delete whatever the previous run left behind."""

def create_piece(sim, ...):
    """One function per kind of piece. Returns the handle."""

def build(sim):
    """Calls the create_* functions in order and returns what was built."""

def verify(...):
    """MEASURES the result. Does not assume it worked."""

def main():
    sim = connect()
    thing = build(sim)
    ok = verify(thing)
    if "--no-save" not in sys.argv:
        sim.saveScene(SCENE_PATH)
    print("\nVerdict:", "ready" if ok else "needs work")

if __name__ == "__main__":
    main()
```

### `clean()` is what makes the script re-runnable

Without it, the second run leaves two overlapping houses. Delete the whole tree
of what you created, not individual objects:

```python
root = sim.getObject("/House")
tree = set(sim.getObjectsInTree(root, sim.handle_all, 0)) | {root}
sim.removeObjects(list(tree))
```

Wrap it in `try/except`: on the first run nothing exists, and that is not an
error.

Careful when deleting by type instead of by root: `/DefaultLights` and
`/XYZCameraProxy` are *dummies*, and removing them dismantles the default scene.
Filter to the types you create (`object_shape_type`, `object_joint_type`,
`object_proximitysensor_type`, `object_forcesensor_type`) and keep `/Floor`.

### `verify()` is what separates a project from a script

It is the most skipped function and the most valuable. Do not ask whether it
looks right: **measure it and let the script deliver a verdict**.

- Does the robot fit through the door? Rasterise the footprints and check the
  clearance.
- Is every room reachable? A BFS over the grid answers it.
- Does the sensor detect? Put an obstacle at three known distances and look.
- Does the robot drive straight? Trace the position and compare against theory.

A verdict printed at the end turns "I think it works" into a number.

## Configuration and flags

Host and port come from a `.env` at the project root, with defaults that already
work, so the script runs with no configuration at all:

```python
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
COPPELIA_HOST = os.getenv("COPPELIA_HOST", "127.0.0.1")
COPPELIA_PORT = int(os.getenv("COPPELIA_PUERTO", "23000"))
```

Anchor the path to `__file__`, never to the working directory, or the script
will only work when launched from one specific folder and fail silently from any
other.

Useful flags, read straight from `sys.argv` without needing `argparse`:

    --build-only   build and skip the tests
    --no-save      do not overwrite the .ttt
    --photo        render an image of the result

## The module header

The docstring at the top should not restate the obvious: **record the decisions
and the dimensions** that drive everything else, with units. That is where you
explain why the doorway is 0.90 m and not 0.80, or why the wheels carry so much
friction. Without it, the next person to touch a number breaks something and has
no idea why.

## Recurring mistakes

- Using `setObjectPosition` where a motor should do the work. If the robot has
  joints, send them a velocity; shoving it by hand is not simulation.
- Saving the scene before verifying, and thereby saving a broken one.
- Putting the control loop in the script that builds: every geometry tweak then
  forces a full re-run of the test.
- Letting paths depend on the working directory.
