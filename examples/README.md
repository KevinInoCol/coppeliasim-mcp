# Examples

Two complete projects, built against a real CoppeliaSim 4.10 and measured rather
than assumed. Every figure quoted in the main README and in the plugin's skills
was produced here.

They are ordinary Python scripts that talk to CoppeliaSim through
`coppeliasim_zmqremoteapi_client` — the same API the MCP server uses. That is
deliberate, and it is the point: **the tools are for inspecting and verifying a
scene; a project is written as a script.** These examples show what that looks
like.

## Requirements

```bash
pip install coppeliasim-zmqremoteapi-client python-dotenv
```

CoppeliaSim 4.10 must be running, with the ZMQ remote API add-on active (on by
default, port 23000). Host and port come from a `.env` found anywhere above the
script; without one, the defaults already work.

## [`Proyecto-01-Carrito-Diferencial/`](Proyecto-01-Carrito-Diferencial/)

A differential drive robot that spots an obstacle with a proximity sensor and
brakes. Two stages: an exploratory script that adopts a cart assembled by hand
through the MCP tools, and the finished one that builds everything in code —
chassis, motorised joints, caster, sensor, enclosure and obstacle — then drives
it for 45 seconds and reports distance travelled against theory.

This project is where **`bullet.frictionOld`** was found: with the caster's
friction written only to `bullet.friction`, which Bullet 2.7 silently ignores,
the robot covered 87% of its straight-line distance and 51% of its turn rate.
Writing both properties: 99% and 99%.

## [`Proyecto-02-Casa/`](Proyecto-02-Casa/)

A single-storey house with no roof — so the top-down view looks straight into the
rooms — plus a mobile robot that drives through it and a keyboard teleop script.

`casa.py` does not just build the floor plan: it rasterises the wall footprints,
runs a BFS from the entrance and refuses to call the house finished if any room
turns out to be walled off. `robot.py` builds the robot from dimensioned plans
and then measures whether it drives straight, turns on its drive axle and holds
its chassis height steady. `teleop.py` drives it from the terminal.

Between them they are the worked answer to "how do I lay out a CoppeliaSim
project so it stays reproducible", which is what the plugin's
`project-structure` skill describes in the abstract.

## Running them

```bash
python examples/Proyecto-02-Casa/casa.py            # build, verify, save
python examples/Proyecto-02-Casa/casa.py --foto     # also render the floor plan
python examples/Proyecto-02-Casa/robot.py           # needs the house first
python examples/Proyecto-02-Casa/teleop.py          # run this in your own terminal
```

Each script cleans up after its previous run, so they are safe to re-run.
