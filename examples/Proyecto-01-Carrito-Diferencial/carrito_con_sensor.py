"""
Monta el escenario "carrito + obstáculo + sensor de proximidad" en CoppeliaSim.

Lo que hace, en orden:

  1. Empareja las piezas del carrito al chasis, para que se mueva como un solo
     cuerpo (el MCP crea primitivas sueltas, sin jerarquía).
  2. Crea un sensor de proximidad cónico en el morro, apuntando al frente del
     carrito (+X local), y lo cuelga del chasis.
  3. Pone un cubo como obstáculo delante, marcado como detectable.
  4. Demuestra que el sensor funciona: avanza el carrito paso a paso y frena
     cuando el sensor reporta el obstáculo por debajo de la distancia de freno.

Tres detalles que cuestan un rato descubrir:

  - `readProximitySensor` NO detecta: solo lee el resultado del último
    `handleProximitySensor`, que el simulador corre durante la simulación. Aquí
    se usa `checkProximitySensor`, que detecta en el momento, con la simulación
    detenida o corriendo.
  - Las piezas se resuelven a handle ANTES de tocar la jerarquía. Emparentar
    renumera las rutas de los hermanos (/Cylinder[3] pasa a /Cylinder[1]), así
    que resolver rutas a mitad del proceso apunta al objeto equivocado.
  - Un cono ancho apuntando en horizontal ve el SUELO antes que el obstáculo.
    Con media apertura a, el suelo entra en el cono a z_sensor/tan(a) metros; el
    haz se mantiene estrecho para que esa distancia quede fuera del alcance.

Uso:
    python carrito_con_sensor.py                # monta el escenario y corre la demo
    python carrito_con_sensor.py --solo-montar  # monta y solo lee en reposo
"""

import math
import os
import sys

from coppeliasim_zmqremoteapi_client import RemoteAPIClient
from dotenv import find_dotenv, load_dotenv

RUTA_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(find_dotenv())    # opcional: sin .env valen los valores por defecto

COPPELIA_HOST = os.getenv("COPPELIA_HOST", "127.0.0.1")
COPPELIA_PUERTO = int(os.getenv("COPPELIA_PUERTO", "23000"))

CHASIS_TAMANO = [0.4, 0.25, 0.06]          # así se reconoce el chasis en la escena
RADIO_CARRITO = 0.35                        # las piezas dentro de este radio son del carrito
PIEZA_TAMANO_MAX = 0.3                      # una pieza del carrito no mide más que esto

SENSOR_ALIAS = "SensorFrontal"
SENSOR_POS_LOCAL = [0.21, 0.0, 0.04]        # relativo al chasis: morro, a la altura del eje
SENSOR_ALCANCE = 0.8                        # metros
SENSOR_APERTURA = math.radians(10.0)        # apertura total del cono

OBSTACULO_ALIAS = "Obstaculo"
OBSTACULO_POS = [1.0, 0.0, 0.1]
OBSTACULO_TAMANO = [0.2, 0.2, 0.2]

PASO_AVANCE = 0.01                          # metros por iteración de la demo
DISTANCIA_FRENO = 0.15                      # metros
MAX_PASOS = 200


def conectar():
    return RemoteAPIClient(host=COPPELIA_HOST, port=COPPELIA_PUERTO).require("sim")


def borrar_si_existe(sim, alias):
    """Hace el script re-ejecutable: quita el objeto de una corrida anterior."""
    try:
        sim.removeObjects([sim.getObject(f"/{alias}")])
        return True
    except Exception:
        return False


def buscar_chasis(sim):
    """Encuentra el chasis por sus dimensiones, no por su ruta (que cambia)."""
    for handle in sim.getObjectsInTree(sim.handle_scene, sim.object_shape_type, 0):
        try:
            medidas = sorted(sim.getShapeBB(handle)[0])
        except Exception:
            continue
        if all(abs(m - e) < 0.01 for m, e in zip(medidas, sorted(CHASIS_TAMANO))):
            return handle
    sys.exit("No encontré el chasis (un cubo de 0.40 x 0.25 x 0.06) en la escena.")


def piezas_del_carrito(sim, chasis):
    """Las shapes suelas cerca del chasis: sus ruedas y su carga."""
    centro = sim.getObjectPosition(chasis, sim.handle_world)
    piezas = []
    for handle in sim.getObjectsInTree(sim.handle_scene, sim.object_shape_type, 0):
        if handle == chasis or sim.getObjectParent(handle) != -1:
            continue
        # El filtro de tamaño no es cosmético: el suelo está centrado en el
        # origen, o sea encima del chasis, así que pasa el filtro de cercanía y
        # termina colgado del carrito si no se lo descarta por sus dimensiones.
        if max(sim.getShapeBB(handle)[0]) > PIEZA_TAMANO_MAX:
            continue
        posicion = sim.getObjectPosition(handle, sim.handle_world)
        plano = math.dist(posicion[:2], centro[:2])
        if plano <= RADIO_CARRITO and posicion[2] < centro[2] + 0.3:
            piezas.append(handle)
    return piezas


def desenganchar_ajenos(sim, chasis):
    """Devuelve a la raíz lo que no debería colgar del chasis (típicamente el suelo)."""
    devueltos = []
    for handle in sim.getObjectsInTree(chasis, sim.object_shape_type, 1):
        # Solo hijos directos: si se recorre el árbol entero se acaba
        # desenganchando también a los hijos de lo desenganchado (/Floor/box).
        if sim.getObjectParent(handle) != chasis:
            continue
        if max(sim.getShapeBB(handle)[0]) > PIEZA_TAMANO_MAX:
            sim.setObjectParent(handle, -1, True)
            devueltos.append(sim.getObjectAlias(handle, 1))
    return devueltos


def emparentar(sim, chasis, piezas):
    for handle in piezas:
        sim.setObjectParent(handle, chasis, True)


def crear_sensor(sim, chasis):
    """Crea el sensor cónico en el morro del carrito y lo cuelga del chasis."""
    # El sensor detecta a lo largo de su eje +Z, así que rotarlo +90° sobre Y
    # deja ese eje mirando al frente del carrito (+X local).
    int_params = [32, 32, 4, 4, 1, 1, 0, 0]
    float_params = [
        0.0,               # offset del volumen
        SENSOR_ALCANCE,    # alcance
        0.05, 0.05,        # x/y size (solo tipo pirámide)
        0.05, 0.05,        # x/y size far
        0.0,               # inside gap
        0.005,             # radio cerca
        SENSOR_ALCANCE * math.tan(SENSOR_APERTURA / 2),   # radio lejos, coherente con la apertura
        SENSOR_APERTURA,   # apertura del cono
        math.radians(45),  # ángulo umbral
        0.0,               # distancia mínima de detección
        0.005,             # tamaño del punto de detección
        0.0, 0.0,          # reservados
    ]
    sensor = sim.createProximitySensor(sim.proximitysensor_cone, 16, 0, int_params, float_params)
    sim.setObjectAlias(sensor, SENSOR_ALIAS)
    sim.setObjectParent(sensor, chasis, False)
    sim.setObjectPosition(sensor, SENSOR_POS_LOCAL, chasis)
    sim.setObjectOrientation(sensor, [0.0, math.pi / 2, 0.0], chasis)
    return sensor


def crear_obstaculo(sim):
    """Crea el cubo obstáculo delante del carrito y lo marca como detectable."""
    obstaculo = sim.createPrimitiveShape(sim.primitiveshape_cuboid, OBSTACULO_TAMANO, 0)
    sim.setObjectAlias(obstaculo, OBSTACULO_ALIAS)
    sim.setObjectPosition(obstaculo, OBSTACULO_POS, sim.handle_world)
    sim.setObjectSpecialProperty(
        obstaculo,
        sim.objectspecialproperty_detectable_all | sim.objectspecialproperty_renderable,
    )
    return obstaculo


def leer(sim, sensor):
    """Detección inmediata contra todo lo detectable: (detectado, distancia, objeto)."""
    estado, distancia, _punto, objeto, _normal = sim.checkProximitySensor(sensor, sim.handle_all)
    if estado != 1:
        return False, None, None
    return True, distancia, objeto


def demo_avance(sim, chasis, sensor):
    """Avanza el carrito hasta que el sensor vea algo por debajo de la distancia de freno."""
    for paso in range(MAX_PASOS):
        detectado, distancia, objeto = leer(sim, sensor)
        if detectado and distancia <= DISTANCIA_FRENO:
            alias = sim.getObjectAlias(objeto, 1)
            x = sim.getObjectPosition(chasis, sim.handle_world)[0]
            print(f"   paso {paso:3d}: FRENO — {alias} a {distancia:.3f} m (chasis en x={x:.2f})")
            return True
        if paso % 10 == 0:
            estado = f"obstáculo a {distancia:.3f} m" if detectado else "vía libre"
            print(f"   paso {paso:3d}: {estado}")
        x, y, z = sim.getObjectPosition(chasis, sim.handle_world)
        sim.setObjectPosition(chasis, [x + PASO_AVANCE, y, z], sim.handle_world)
    print("   la demo agotó los pasos sin alcanzar la distancia de freno")
    return False


def main():
    solo_montar = "--solo-montar" in sys.argv
    sim = conectar()

    for alias in (SENSOR_ALIAS, OBSTACULO_ALIAS):
        if borrar_si_existe(sim, alias):
            print(f"0. Quitado '{alias}' de una corrida anterior")

    chasis = buscar_chasis(sim)
    print(f"1. Chasis: '{sim.getObjectAlias(chasis, 1)}' (handle {chasis})")

    if devueltos := desenganchar_ajenos(sim, chasis):
        print(f"   desenganchados del chasis (no son piezas): {', '.join(devueltos)}")

    piezas = piezas_del_carrito(sim, chasis)
    emparentar(sim, chasis, piezas)
    hijos = sim.getObjectsInTree(chasis, sim.object_shape_type, 1)
    print(f"   emparentadas {len(piezas)} piezas nuevas; el chasis tiene {len(hijos)} hijos")

    sensor = crear_sensor(sim, chasis)
    padre = sim.getObjectAlias(sim.getObjectParent(sensor), 1)
    apertura = math.degrees(SENSOR_APERTURA)
    ciego = SENSOR_POS_LOCAL[2] + 0.05  # altura del sensor sobre el suelo
    print(f"2. Sensor '{sim.getObjectAlias(sensor, 1)}' colgado de '{padre}'")
    print(f"   cono de {apertura:.0f}°, alcance {SENSOR_ALCANCE} m")
    print(f"   el suelo entra en el cono a {ciego / math.tan(SENSOR_APERTURA / 2):.2f} m "
          f"(fuera del alcance, así que no lo ve)")

    obstaculo = crear_obstaculo(sim)
    print(f"3. Obstáculo '{sim.getObjectAlias(obstaculo, 1)}' en {OBSTACULO_POS}")

    detectado, distancia, objeto = leer(sim, sensor)
    alias = sim.getObjectAlias(objeto, 1) if detectado else None
    medida = f"{distancia:.3f} m" if detectado else "—"
    print(f"4. Lectura en reposo: detectado={detectado}, objeto={alias}, distancia={medida}")

    if not solo_montar:
        print("5. Demo: avanzar y frenar ante el obstáculo")
        demo_avance(sim, chasis, sensor)


if __name__ == "__main__":
    main()
