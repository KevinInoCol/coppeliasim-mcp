# Examples

## `carrito_diferencial.py` — differential drive robot with obstacle avoidance

Builds a complete differential drive robot in an empty CoppeliaSim scene and
verifies it works: chassis, two motorized wheels on velocity-controlled revolute
joints, a friction-free caster, a cone-shaped proximity sensor, four walls, and
an embedded Lua child script that reads the sensor and steers. Press Play and it
drives itself.

```bash
pip install coppeliasim-zmqremoteapi-client python-dotenv
python carrito_diferencial.py                 # build, then run a 45 s test
python carrito_diferencial.py --solo-construir  # build only
```

**This script talks to CoppeliaSim directly over the ZMQ remote API, not through
the MCP server.** It is here as the reference implementation of a robot you can
also build by asking the MCP server for it, tool call by tool call — and because
it documents, in code, the API facts that cost the most time to discover:

- `sim.jointdynctrl_velocity` is `4`, and goes in the joint's `dynCtrlMode`
  property. Without it the motor ignores target velocities.
- A revolute joint spins about its own **+Z**. To roll a wheel toward +X, that
  axis must lie along Y: a −90° rotation about X.
- **Parenting two dynamic shapes does not attach them.** They stay separate
  bodies and drift apart. A rigid link needs a joint or a force sensor — and a
  force sensor is the only option when the two bodies need different friction
  coefficients, since grouping forces them to share.
- `respondableMask`: the low 8 bits govern collisions inside the same tree, the
  high 8 bits with everything else. `0xFF00` keeps the robot's own parts from
  colliding with each other while still colliding with the floor.
- `computeMassAndInertia` only works on convex shapes, and returns 0 when it
  fails rather than raising.
- A proximity cone pointing horizontally sees the **floor** before it sees the
  obstacle, and a robot that pitches nose-down under acceleration makes it
  worse. The script prints the floor-intersection distance on every build so the
  geometry is checked instead of assumed.
- The robot pivots about its **driven wheel axle**, not its center, so the nose
  sweeps a wider radius than you would guess. The avoidance distance has to
  clear that or it grazes corners.

The script does not just build the scene — it steps the simulation and measures
whether the robot actually works: forward travel, chassis stability, sensor
detections, and real collision checks against the obstacle and walls. A build
that looks right but hits a wall gets reported as a failure.

---

## `carrito_diferencial.py` (español)

Construye un carrito de tracción diferencial completo en una escena vacía de
CoppeliaSim y comprueba que funciona: chasis, dos ruedas motrices sobre juntas
revolute en control de velocidad, una rueda loca sin fricción, un sensor de
proximidad cónico, cuatro paredes, y un child script en Lua dentro de la escena
que lee el sensor y decide. Le das Play y anda solo.

```bash
pip install coppeliasim-zmqremoteapi-client python-dotenv
python carrito_diferencial.py                   # construye y prueba 45 s
python carrito_diferencial.py --solo-construir  # solo construye
```

**Habla con CoppeliaSim directamente por la ZMQ remote API, no a través del
servidor MCP.** Está aquí como implementación de referencia de un robot que
también puedes construir pidiéndoselo al MCP tool por tool, y porque documenta
en código los detalles de la API que cuestan más tiempo descubrir: los mismos
que lista la sección en inglés de arriba.

El script no solo construye: corre la simulación y mide si el robot de verdad
funciona —avance, estabilidad del chasis, detecciones, y colisiones reales
contra el obstáculo y las paredes—. Un montaje que parece correcto pero roza una
pared se reporta como fallo.
