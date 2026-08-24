---
name: robot-diferencial-y-sensores
description: Montar un robot de tracción diferencial en CoppeliaSim y que se mueva de verdad — el eje y el modo de control de las juntas, la fricción que Bullet obedece, masa e inercia, grupos de colisión — más sensores de proximidad, su zona ciega y por qué un cono ancho ve el suelo. Úsala al construir un robot móvil, al montar ruedas o juntas, o cuando el robot no avanza, tiembla, patina o el sensor no detecta.
---

# Robot diferencial y sensores

Las trampas de esta página cuestan horas cada una. Todas están medidas sobre un
robot que funciona.

## Juntas: el eje y el modo de control

**Una junta actúa a lo largo de su propio +Z.** Para una rueda que impulsa hacia
+X, el eje tiene que quedar sobre Y, lo que significa rotar la junta entera
(`-pi/2` alrededor de X). No es un parámetro de la llamada: es la orientación
del objeto.

**Una junta sin modo de control es sorda.** Aunque le mandes velocidad, no se
mueve hasta que se le pone `dynCtrlMode`, que es una **propiedad**, no un
argumento de la creación. Con el modo de velocidad, el valor es 4 (no 2, que es
lo que uno supondría):

```python
sim.setInt32Property(junta, "dynCtrlMode", sim.jointdynctrl_velocity)
sim.setJointTargetVelocity(junta, 3.0)
```

Si usas la tool `crear_junta` del MCP, hace las dos cosas por ti.

## Fricción: Bullet lee `frictionOld`

**Bullet 2.7, que es el motor por defecto, obedece `bullet.frictionOld`, no
`bullet.friction`.** CoppeliaSim expone las dos y cuál manda depende de la
versión de Bullet elegida en la escena. Poner solo `bullet.friction` no hace
absolutamente nada.

Medido sobre un diferencial real: una rueda loca con la fricción vieja en 1
arrastró al robot al **87% de su distancia** en recta y al **51% de su giro**,
patinando en vez de pivotar sobre el eje motriz. Escribe siempre las dos.

Rueda loca: fricción muy baja. Ruedas motrices: fricción alta.

## Masa e inercia

`computeMassAndInertia` **solo funciona con formas convexas**. No fusiones el
chasis con la carga y luego lo llames: deja cada pieza convexa por separado y
calcula la masa de cada una.

Sin masa razonable, un robot ligero con ruedas finas tiembla o sale despedido.

## Ruedas finas

Las ruedas de 1 cm de espesor son poquísimo para Bullet: el contacto es casi una
línea y el robot tiembla. Se compensa con fricción alta y masa suficiente. Si el
robot vibra parado, mide la altura del chasis a lo largo del tiempo — si oscila,
es esto.

## Grupos de colisión

Las piezas del robot no deben chocar entre sí, pero sí con el mundo. La máscara
de respondable resuelve las dos cosas a la vez: los 8 bits bajos dicen con quién
choca dentro del mismo árbol y los 8 altos con el resto. Con `0xFF00` las piezas
del robot se ignoran entre ellas —se acabaron los temblores— y siguen chocando
con el suelo y los obstáculos.

## Emparentar no es unir

**Colgar una forma dinámica de otra no las une rígidamente.** Se caerá igual, y
el robot se desarma al dar Play. Para unir dos cuerpos dinámicos hace falta una
junta o un sensor de fuerza, que es lo que hace la tool `crear_union_rigida`.

## Sensores de proximidad

**El objeto tiene que ser `detectable`.** Es la razón habitual de que un sensor
"no funcione". Ver la skill de construir escenas.

**Leer no es detectar.** `leer_sensor_proximidad` (y `sim.readProximitySensor`)
devuelve el resultado de la última pasada del simulador, así que **con la
simulación parada siempre dice que no hay nada**. Para detectar bajo demanda usa
`comprobar_sensor_proximidad` / `sim.checkProximitySensor`.

**El `offset` es zona ciega de verdad.** Un Sharp de infrarrojos con rango de
10 a 80 cm no ve nada más cerca de 10 cm, y modelarlo con el offset reproduce
justamente eso. Un obstáculo pegado al morro es invisible: no es un fallo.

**Un cono ancho apuntando en horizontal ve el suelo.** Con semiapertura *a* y el
sensor a altura *h*, el suelo entra en el cono a *h / tan(a)*. Si esa distancia
es menor que el alcance, el sensor reporta el suelo constantemente y parece
averiado. Comprueba el número antes de acusar al sensor:

```python
def distancia_al_suelo(altura, apertura):
    return altura / math.tan(apertura)
```

Con 10° de apertura y el sensor a 10 cm, el suelo aparece a 57 cm. Con 45°, a
10 cm: inservible.

## Probar el robot

No supongas que se mueve. Mide:

- **Sensor**: pon un obstáculo a tres distancias conocidas, una dentro de la
  zona ciega, y comprueba las tres lecturas.
- **Recta**: manda la misma velocidad a las dos ruedas, traza la posición y
  compara la distancia recorrida con la teórica (`radio * omega * tiempo`). Por
  debajo del 90% hay patinaje: mira la fricción.
- **Giro**: velocidades opuestas y acumula el ángulo. Si patina en vez de
  pivotar, la rueda loca tiene demasiada fricción.
- **Estabilidad**: traza la altura del chasis. Si oscila, es masa o ruedas
  finas.

## Tiempo real

Para teleoperar, activa el modo de tiempo real. Sin él la simulación corre todo
lo que puede: se midieron **49 segundos simulados en 2 segundos de reloj**, y no
hay reflejos humanos para eso.
