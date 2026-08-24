---
name: differential-robot-and-sensors
description: Assembling a differential drive robot in CoppeliaSim and getting it to actually move — joint axis and control mode, the friction Bullet obeys, mass and inertia, collision groups — plus proximity sensors, their blind zone, and why a wide cone sees the floor. Use when building a mobile robot, adding wheels or joints, or when the robot will not move, jitters, skids, or the sensor detects nothing.
---

# Differential drive robot and sensors

Every trap on this page costs hours. All of them were measured on a robot that
works.

## Joints: axis and control mode

**A joint acts along its own +Z.** For a wheel driving toward +X, the axis must
lie along Y, which means rotating the whole joint (`-pi/2` about X). It is not a
call parameter: it is the object's orientation.

**A joint with no control mode is deaf.** Send it a velocity and nothing
happens until `dynCtrlMode` is set — a **property**, not an argument of the
creation call. For velocity control the value is 4 (not 2, which is what you
would guess):

```python
sim.setInt32Property(joint, "dynCtrlMode", sim.jointdynctrl_velocity)
sim.setJointTargetVelocity(joint, 3.0)
```

The MCP's `crear_junta` tool does both for you.

## Friction: Bullet reads `frictionOld`

**Bullet 2.7, the default engine, obeys `bullet.frictionOld`, not
`bullet.friction`.** CoppeliaSim exposes both and which one wins depends on the
Bullet version selected in the scene. Setting only `bullet.friction` does
nothing at all.

Measured on a real differential drive: a caster left at old-friction 1 dragged
the robot down to **87% of its straight-line distance** and **51% of its turn
rate**, skid-steering instead of pivoting on its drive axle. Always write both.

Caster: very low friction. Drive wheels: high friction.

## Mass and inertia

`computeMassAndInertia` **only works on convex shapes**. Do not merge the
chassis with the payload and then call it: keep each piece convex on its own and
compute each mass separately.

Without sensible mass, a light robot on thin wheels jitters or gets flung.

## Thin wheels

Wheels 1 cm thick are very little for Bullet: the contact is almost a line and
the robot shakes. Compensate with high friction and enough mass. If the robot
vibrates while standing still, trace the chassis height over time — if it
oscillates, this is why.

## Collision groups

The robot's parts must not collide with each other, but must collide with the
world. The respondable mask does both at once: the low 8 bits say who it hits
within the same tree, the high 8 bits who it hits outside. With `0xFF00` the
robot's parts ignore each other — no more jitter — and still hit the floor and
the obstacles.

## Parenting is not attaching

**Hanging one dynamic shape off another does not rigidly attach them.** It still
falls, and the robot comes apart on Play. Joining two dynamic bodies needs a
joint or a force sensor, which is what the `crear_union_rigida` tool does.

## Proximity sensors

**The object must be `detectable`.** That is the usual reason a sensor "doesn't
work". See the scene-building skill.

**Reading is not detecting.** `sim.readProximitySensor` returns the result of the
simulator's last pass, so **with the simulation stopped it always reports
nothing**. To detect on demand use `sim.checkProximitySensor` (the MCP's
`comprobar_sensor_proximidad`).

**The `offset` is a real blind zone.** A Sharp infrared with a 10–80 cm range
sees nothing closer than 10 cm, and modelling it with the offset reproduces
exactly that. An obstacle against the nose is invisible: that is not a bug.

**A wide cone pointing horizontally sees the floor.** With half-aperture *a* and
the sensor at height *h*, the floor enters the cone at *h / tan(a)*. If that is
below the sensor range, it reports the ground constantly and looks broken. Check
the number before blaming the sensor:

```python
def floor_distance(height, aperture):
    return height / math.tan(aperture)
```

With a 10° aperture and the sensor at 10 cm, the floor shows up at 57 cm. With
45°, at 10 cm: useless.

## Testing the robot

Do not assume it moves. Measure:

- **Sensor**: place an obstacle at three known distances, one inside the blind
  zone, and check all three readings.
- **Straight line**: same velocity to both wheels, trace the position and
  compare distance travelled against theory (`radius * omega * time`). Below 90%
  there is slip: look at the friction.
- **Turning**: opposite velocities, accumulate the angle. If it skids instead of
  pivoting, the caster has too much friction.
- **Stability**: trace the chassis height. If it oscillates, it is mass or thin
  wheels.

## Real time

For teleoperation, switch on real-time mode. Without it the simulation runs as
fast as it can: **49 simulated seconds in 2 seconds of wall clock** was measured,
and no human reflexes work at that rate.
