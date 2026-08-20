"""
Construye un carrito de tracción diferencial con física real en CoppeliaSim.

A diferencia de `carrito_con_sensor.py`, que movía una maqueta con
setObjectPosition desde Python, esto es un robot: al darle Play, los motores de
las juntas giran las ruedas, las ruedas empujan por fricción, y un child script
en Lua dentro de la escena lee el sensor y decide. No hace falta Python
corriendo: la escena se gobierna sola.

Arquitectura del robot:

    /Carrito                    chasis, dinámico y respondable
      ├── JuntaIzq              revolute, motor en modo velocidad
      │     └── RuedaIzq        cilindro, dinámico y respondable
      ├── JuntaDer
      │     └── RuedaDer
      ├── RuedaLoca             esfera con fricción 0: apoyo delantero libre
      ├── SensorFrontal         sensor de proximidad cónico
      └── Controlador           child script en Lua

Por qué dos ruedas motrices y una esfera, y no las cuatro ruedas del boceto:
con cuatro ruedas fijas el giro exige que las delanteras derrapen de lado
(skid-steer), lo que depende mucho de la fricción y suele quedar brusco o
directamente atascarse. Dos motrices más un apoyo libre es la configuración de
tracción diferencial estándar, y gira limpio sobre su propio eje.

Detalles de la API que se verificaron contra la instalación local, porque
adivinarlos cuesta una tarde:

  - `sim.jointdynctrl_velocity` vale 4, no 2. Se fija en la propiedad
    'dynCtrlMode' de la junta, y sin eso el motor no obedece.
  - El eje de giro de una junta revolute es su +Z. Para que una rueda ruede
    hacia +X, el eje debe quedar a lo largo de Y: rotación de -90° sobre X.
  - `respondableMask`: los 8 bits bajos gobiernan las colisiones dentro del
    mismo árbol, los 8 altos con el resto. Con 0xFF00 las piezas del robot no
    chocan entre sí (nada de temblores) pero sí con el suelo y el obstáculo.
  - `computeMassAndInertia` solo funciona con formas convexas. Cada pieza se
    deja convexa por separado en vez de fusionar el chasis con la carga.

Uso:
    python carrito_diferencial.py            # construye y prueba 12 s de simulación
    python carrito_diferencial.py --solo-construir
"""

import math
import os
import sys

from coppeliasim_zmqremoteapi_client import RemoteAPIClient
from dotenv import load_dotenv

load_dotenv()  # lee un .env del directorio de trabajo, si existe

COPPELIA_HOST = os.getenv("COPPELIA_HOST", "127.0.0.1")
COPPELIA_PUERTO = int(os.getenv("COPPELIA_PUERTO", "23000"))

CHASIS_TAMANO = [0.40, 0.25, 0.06]
CHASIS_Z = 0.09
CHASIS_DENSIDAD = 300.0            # kg/m^3 -> unos 1.8 kg

RUEDA_RADIO = 0.05
RUEDA_ANCHO = 0.04
RUEDA_X = -0.12                     # las motrices, detrás del centro
RUEDA_Y = 0.145
RUEDA_DENSIDAD = 800.0
RUEDA_FRICCION = 1.0                # agarre alto: si derrapa, no avanza

LOCA_RADIO = 0.03                   # apoyo delantero; el chasis queda a 0.06 del suelo
LOCA_X = 0.15
LOCA_DENSIDAD = 500.0
LOCA_FRICCION = 0.0                 # sin fricción: se desliza y no estorba al giro

JUNTA_TORQUE = 2.0                  # N.m que puede dar el motor

SENSOR_POS_LOCAL = [0.21, 0.0, 0.04]
SENSOR_ALCANCE = 0.8
SENSOR_APERTURA = math.radians(25.0)     # ancho, para cubrir el ancho del chasis
SENSOR_INCLINACION = math.radians(4.0)   # unos grados hacia arriba, de margen

OBSTACULO_POS = [1.5, 0.0, 0.1]
OBSTACULO_TAMANO = [0.3, 0.3, 0.2]

# El suelo por defecto mide 5x5 m y no tiene bordes: sin paredes, el carrito
# acaba cayéndose al vacío a los 20 s de Play. Con ellas la demo no se acaba.
RECINTO_LADO = 4.0
RECINTO_ALTURA = 0.3
RECINTO_GROSOR = 0.05

MASCARA_ROBOT = 0xFF00              # no chocar entre piezas, sí con el mundo

V_CRUCERO = 4.0                     # rad/s -> 0.2 m/s con ruedas de 5 cm
V_GIRO = 3.0
# El carrito gira sobre el eje de las ruedas motrices (x = RUEDA_X), no sobre su
# centro, así que al girar el morro barre un radio de |RUEDA_X| + medio chasis =
# 0.32 m. La distancia de evasión tiene que superar eso o roza en las esquinas.
D_EVASION = 0.55                    # m
T_GIRO_EXTRA = 1.2                  # s girando de más después de perder de vista

CONTROLADOR_LUA = """
-- Controlador del carrito: avanza, y gira sobre su eje al ver algo cerca.
--
-- El giro es "comprometido": una vez disparado sigue girando un rato aunque el
-- sensor ya no vea nada. Sin eso el carrito roza el obstáculo, porque el haz es
-- más estrecho que el chasis: gira lo justo para que el cono pierda la esquina,
-- se cree libre, y choca con el cuerpo. El compromiso de giro es lo que hace
-- que la maniobra saque de la trayectoria al robot entero, no solo al sensor.
function sysCall_init()
    juntaIzq = sim.getObject('../JuntaIzq')
    juntaDer = sim.getObject('../JuntaDer')
    sensor = sim.getObject('../SensorFrontal')
    vCrucero = %.3f
    vGiro = %.3f
    dEvasion = %.3f
    pasosExtra = math.floor(%.3f / sim.getSimulationTimeStep())
    girosPendientes = 0
end

function sysCall_actuation()
    -- readProximitySensor no detecta: devuelve el barrido que el simulador hizo
    -- en el paso anterior. Un paso de retraso, irrelevante a esta velocidad.
    local detectado, distancia = sim.readProximitySensor(sensor)
    if detectado == 1 and distancia < dEvasion then
        girosPendientes = pasosExtra
    end

    if girosPendientes > 0 then
        girosPendientes = girosPendientes - 1
        sim.setJointTargetVelocity(juntaIzq, -vGiro)   -- giro sobre el sitio,
        sim.setJointTargetVelocity(juntaDer, vGiro)    -- hacia la izquierda
    else
        sim.setJointTargetVelocity(juntaIzq, vCrucero)
        sim.setJointTargetVelocity(juntaDer, vCrucero)
    end
end
""" % (V_CRUCERO, V_GIRO, D_EVASION, T_GIRO_EXTRA)


def conectar():
    return RemoteAPIClient(host=COPPELIA_HOST, port=COPPELIA_PUERTO).require("sim")


def limpiar(sim):
    """Quita todo lo que no sea suelo, cámaras ni luces. Deja la escena en blanco."""
    conservar = set()
    for ruta in ("/Floor",):
        try:
            piso = sim.getObject(ruta)
            conservar.add(piso)
            conservar.update(sim.getObjectsInTree(piso, sim.handle_all, 0))
        except Exception:
            pass

    # Solo lo que construye este script. Nada de dummies: /DefaultLights y
    # /XYZCameraProxy son dummies, y borrarlos desarma la escena por defecto.
    tipos = (sim.object_shape_type, sim.object_joint_type,
             sim.object_proximitysensor_type, sim.object_forcesensor_type)
    borrar = []
    for tipo in tipos:
        for handle in sim.getObjectsInTree(sim.handle_scene, tipo, 0):
            if handle not in conservar:
                borrar.append(handle)
    # los scripts cuelgan de los objetos; se van con ellos, pero por si quedan
    # sueltos de una corrida anterior se recogen aparte
    for handle in sim.getObjectsInTree(sim.handle_scene, sim.sceneobject_script, 0):
        if handle not in conservar:
            borrar.append(handle)

    nombres = []
    for handle in borrar:
        try:
            nombres.append(sim.getObjectAlias(handle, 1))
        except Exception:
            nombres.append(f"handle {handle}")
    if borrar:
        sim.removeObjects(borrar)
    return nombres


AGRUPADORES = {
    "DefaultLights": ([0.0, 0.0, 0.0], ["/LightA", "/LightB", "/LightC", "/LightD"]),
    "XYZCameraProxy": ([0.0, 0.0, 0.75], ["/XViewCamera", "/YViewCamera", "/ZViewCamera",
                                          "/NXViewCamera", "/NYViewCamera", "/NZViewCamera"]),
}


def restaurar_agrupadores(sim):
    """
    Recrea los dummies que agrupan las luces y las cámaras de vista, si faltan.

    Al borrar un padre, CoppeliaSim no se lleva a los hijos: los reasigna a la
    raíz. O sea que las luces siguen iluminando, pero la jerarquía queda sucia.
    """
    restaurados = []
    for alias, (posicion, hijos) in AGRUPADORES.items():
        try:
            sim.getObject(f"/{alias}")
            continue
        except Exception:
            pass
        sueltos = []
        for ruta in hijos:
            try:
                sueltos.append(sim.getObject(ruta))
            except Exception:
                pass
        if not sueltos:
            continue
        padre = sim.createDummy(0.01)
        sim.setObjectAlias(padre, alias)
        sim.setObjectPosition(padre, posicion, sim.handle_world)
        for handle in sueltos:
            sim.setObjectParent(handle, padre, True)
        restaurados.append(f"{alias} ({len(sueltos)} hijos)")
    return restaurados


def hacer_dinamico(sim, handle, densidad, friccion, respondable=True):
    """Deja una forma lista para el motor de física: masa, inercia y contacto."""
    sim.setBoolProperty(handle, "dynamic", True)
    sim.setBoolProperty(handle, "respondable", respondable)
    sim.setIntProperty(handle, "respondableMask", MASCARA_ROBOT)
    if sim.computeMassAndInertia(handle, densidad) != 1:
        raise RuntimeError(f"{sim.getObjectAlias(handle, 1)} no es convexa: sin masa ni inercia")
    sim.setFloatProperty(handle, "bullet.friction", friccion)


def crear_chasis(sim):
    chasis = sim.createPrimitiveShape(sim.primitiveshape_cuboid, CHASIS_TAMANO, 0)
    sim.setObjectAlias(chasis, "Carrito")
    sim.setObjectPosition(chasis, [0.0, 0.0, CHASIS_Z], sim.handle_world)
    hacer_dinamico(sim, chasis, CHASIS_DENSIDAD, 0.5)
    return chasis


def crear_rueda_motriz(sim, chasis, lado, alias_junta, alias_rueda):
    """Crea junta + rueda de un lado. `lado` es +1 (izquierda) o -1 (derecha)."""
    y = lado * RUEDA_Y
    # Coordenadas LOCALES al chasis: el eje de la rueda va a la altura de su
    # radio sobre el suelo, y el chasis está a CHASIS_Z, así que la z local es
    # negativa. Pasar aquí coordenadas de mundo deja las ruedas en el aire.
    posicion = [RUEDA_X, y, RUEDA_RADIO - CHASIS_Z]

    junta = sim.createJoint(sim.joint_revolute, sim.jointmode_dynamic, 0, [0.06, 0.03])
    sim.setObjectAlias(junta, alias_junta)
    sim.setObjectParent(junta, chasis, True)
    sim.setObjectPosition(junta, posicion, chasis)
    # El eje de la junta es su +Z; -90° sobre X lo deja a lo largo de +Y, que es
    # lo que hace que un giro positivo empuje el carrito hacia +X.
    sim.setObjectOrientation(junta, [-math.pi / 2, 0.0, 0.0], chasis)
    sim.setIntProperty(junta, "dynCtrlMode", sim.jointdynctrl_velocity)
    sim.setFloatProperty(junta, "targetForce", JUNTA_TORQUE)
    sim.setJointTargetVelocity(junta, 0.0)

    rueda = sim.createPrimitiveShape(
        sim.primitiveshape_cylinder,
        [RUEDA_RADIO * 2, RUEDA_RADIO * 2, RUEDA_ANCHO],
        0,
    )
    sim.setObjectAlias(rueda, alias_rueda)
    sim.setObjectParent(rueda, junta, True)
    sim.setObjectPosition(rueda, [0.0, 0.0, 0.0], junta)
    sim.setObjectOrientation(rueda, [0.0, 0.0, 0.0], junta)
    hacer_dinamico(sim, rueda, RUEDA_DENSIDAD, RUEDA_FRICCION)
    return junta, rueda


def crear_rueda_loca(sim, chasis):
    """
    Esfera de apoyo delantera, sin fricción, unida al chasis por un force sensor.

    El force sensor no está aquí para medir nada: es la forma que documenta
    CoppeliaSim de unir rígidamente dos cuerpos dinámicos. Emparentar no basta
    ("non-static shapes will fall if not otherwise constrained by a joint or
    force sensor"), y agrupar las formas obligaría a compartir el coeficiente de
    fricción, cuando lo que se quiere justamente es chasis con agarre y apoyo
    sin agarre.
    """
    soporte = sim.createForceSensor(0, [0, 1, 1, 0, 0], [0.01, 0.0, 0.0, 0.0, 0.0])
    sim.setObjectAlias(soporte, "SoporteLoca")
    sim.setObjectParent(soporte, chasis, True)
    sim.setObjectPosition(soporte, [LOCA_X, 0.0, LOCA_RADIO - CHASIS_Z], chasis)
    sim.setObjectOrientation(soporte, [0.0, 0.0, 0.0], chasis)

    loca = sim.createPrimitiveShape(
        sim.primitiveshape_spheroid, [LOCA_RADIO * 2] * 3, 0
    )
    sim.setObjectAlias(loca, "RuedaLoca")
    sim.setObjectParent(loca, soporte, True)
    sim.setObjectPosition(loca, [0.0, 0.0, 0.0], soporte)
    sim.setObjectOrientation(loca, [0.0, 0.0, 0.0], soporte)
    hacer_dinamico(sim, loca, LOCA_DENSIDAD, LOCA_FRICCION)
    return loca


def distancia_al_suelo(altura_sensor):
    """
    A qué distancia el borde inferior del cono toca el suelo.

    Si sale menor que el alcance, el sensor reportará el piso como obstáculo.
    Es el compromiso central de montar un sensor de proximidad en horizontal:
    haz ancho para cubrir el ancho del robot, pero no tan ancho que vea el suelo.
    """
    borde = SENSOR_APERTURA / 2 - SENSOR_INCLINACION
    if borde <= 0:
        return float("inf")
    return altura_sensor / math.tan(borde)


def crear_sensor(sim, chasis):
    int_params = [32, 32, 4, 4, 1, 1, 0, 0]
    float_params = [
        0.0, SENSOR_ALCANCE, 0.05, 0.05, 0.05, 0.05, 0.0,
        0.005, SENSOR_ALCANCE * math.tan(SENSOR_APERTURA / 2),
        SENSOR_APERTURA, math.radians(45), 0.0, 0.005, 0.0, 0.0,
    ]
    sensor = sim.createProximitySensor(sim.proximitysensor_cone, 16, 0, int_params, float_params)
    sim.setObjectAlias(sensor, "SensorFrontal")
    sim.setObjectParent(sensor, chasis, False)
    sim.setObjectPosition(sensor, SENSOR_POS_LOCAL, chasis)
    # +90° sobre Y deja el eje de detección al frente; se le resta la
    # inclinación para que el haz suba un poco y perdone que el chasis cabecee
    # al acelerar. Con el haz horizontal, un morro abajo de 10° basta para que
    # el sensor confunda el suelo con un obstáculo.
    sim.setObjectOrientation(sensor, [0.0, math.pi / 2 - SENSOR_INCLINACION, 0.0], chasis)
    return sensor


def crear_controlador(sim, chasis):
    """Mete el child script en la escena, colgado del chasis."""
    script = sim.createScript(sim.scripttype_simulation, CONTROLADOR_LUA, 0, "lua")
    sim.setObjectAlias(script, "Controlador")
    sim.setObjectParent(script, chasis, True)
    return script


def crear_recinto(sim):
    """Cuatro paredes estáticas y detectables, para que el carrito no se caiga."""
    mitad = RECINTO_LADO / 2
    paredes = []
    caras = [
        ("ParedNorte", [0.0, mitad, RECINTO_ALTURA / 2], [RECINTO_LADO, RECINTO_GROSOR, RECINTO_ALTURA]),
        ("ParedSur", [0.0, -mitad, RECINTO_ALTURA / 2], [RECINTO_LADO, RECINTO_GROSOR, RECINTO_ALTURA]),
        ("ParedEste", [mitad, 0.0, RECINTO_ALTURA / 2], [RECINTO_GROSOR, RECINTO_LADO, RECINTO_ALTURA]),
        ("ParedOeste", [-mitad, 0.0, RECINTO_ALTURA / 2], [RECINTO_GROSOR, RECINTO_LADO, RECINTO_ALTURA]),
    ]
    for alias, posicion, tamano in caras:
        pared = sim.createPrimitiveShape(sim.primitiveshape_cuboid, tamano, 0)
        sim.setObjectAlias(pared, alias)
        sim.setObjectPosition(pared, posicion, sim.handle_world)
        sim.setBoolProperty(pared, "dynamic", False)
        sim.setBoolProperty(pared, "respondable", True)
        sim.setObjectSpecialProperty(
            pared,
            sim.objectspecialproperty_detectable_all
            | sim.objectspecialproperty_renderable
            | sim.objectspecialproperty_collidable,
        )
        paredes.append(pared)
    return paredes


def crear_obstaculo(sim):
    obstaculo = sim.createPrimitiveShape(sim.primitiveshape_cuboid, OBSTACULO_TAMANO, 0)
    sim.setObjectAlias(obstaculo, "Obstaculo")
    sim.setObjectPosition(obstaculo, OBSTACULO_POS, sim.handle_world)
    # Estático pero respondable: el carrito no puede atravesarlo ni empujarlo.
    sim.setBoolProperty(obstaculo, "dynamic", False)
    sim.setBoolProperty(obstaculo, "respondable", True)
    sim.setObjectSpecialProperty(
        obstaculo,
        sim.objectspecialproperty_detectable_all
        | sim.objectspecialproperty_renderable
        | sim.objectspecialproperty_collidable,
    )
    return obstaculo


def construir(sim):
    borrados = limpiar(sim)
    print(f"0. Escena limpiada ({len(borrados)} objetos): {', '.join(borrados) or 'nada'}")
    if restaurados := restaurar_agrupadores(sim):
        print(f"   agrupadores por defecto restaurados: {', '.join(restaurados)}")

    chasis = crear_chasis(sim)
    print(f"1. Chasis '{sim.getObjectAlias(chasis, 1)}', "
          f"masa {sim.getFloatProperty(chasis, 'mass'):.3f} kg")

    junta_izq, rueda_izq = crear_rueda_motriz(sim, chasis, +1, "JuntaIzq", "RuedaIzq")
    junta_der, rueda_der = crear_rueda_motriz(sim, chasis, -1, "JuntaDer", "RuedaDer")
    print(f"2. Ruedas motrices: masa {sim.getFloatProperty(rueda_izq, 'mass'):.3f} kg cada una, "
          f"fricción {RUEDA_FRICCION}, motor a {JUNTA_TORQUE} N.m")
    print(f"   modo de control de las juntas: dynCtrlMode="
          f"{sim.getIntProperty(junta_izq, 'dynCtrlMode')} (velocidad)")

    loca = crear_rueda_loca(sim, chasis)
    print(f"3. Rueda loca delantera, fricción {LOCA_FRICCION}")

    sensor = crear_sensor(sim, chasis)
    altura = CHASIS_Z + SENSOR_POS_LOCAL[2]
    suelo = distancia_al_suelo(altura)
    print(f"4. Sensor cónico de {math.degrees(SENSOR_APERTURA):.0f}° inclinado "
          f"{math.degrees(SENSOR_INCLINACION):.0f}° arriba, alcance {SENSOR_ALCANCE} m")
    print(f"   a {altura:.3f} m del suelo, el haz lo toca a {suelo:.2f} m -> "
          f"{'ok, fuera del alcance' if suelo > SENSOR_ALCANCE else 'PROBLEMA: verá el piso'}")
    print(f"   ancho del haz a la distancia de evasión: "
          f"{2 * D_EVASION * math.tan(SENSOR_APERTURA / 2):.3f} m "
          f"(chasis: {CHASIS_TAMANO[1]:.3f} m)")

    script = crear_controlador(sim, chasis)
    print(f"5. Child script '{sim.getObjectAlias(script, 1)}' colgado del chasis")

    obstaculo = crear_obstaculo(sim)
    print(f"6. Obstáculo estático en {OBSTACULO_POS}")

    paredes = crear_recinto(sim)
    print(f"7. Recinto de {RECINTO_LADO} x {RECINTO_LADO} m ({len(paredes)} paredes)")

    return {
        "chasis": chasis, "junta_izq": junta_izq, "junta_der": junta_der,
        "rueda_izq": rueda_izq, "rueda_der": rueda_der,
        "loca": loca, "sensor": sensor, "obstaculo": obstaculo,
        "paredes": paredes,
    }


def probar(sim, robot, segundos=45.0):
    """Corre la simulación paso a paso y mide qué hace el carrito de verdad."""
    chasis = robot["chasis"]
    sim.setStepping(True)
    sim.startSimulation()

    dt = sim.getSimulationTimeStep()
    pasos = int(segundos / dt)
    print(f"\n   dt={dt:.3f} s, {pasos} pasos ({segundos:.0f} s de simulación)")
    print(f"   {'t':>5} {'x':>7} {'y':>7} {'z':>6} {'rumbo':>7} {'sensor':>8}  estado")

    # Piezas contra las que comprobar choques de verdad. La distancia del sensor
    # solo mide a lo largo del haz, así que un roce con la esquina del chasis no
    # aparece ahí: hace falta detección de colisión.
    piezas = [robot["chasis"], robot["rueda_izq"], robot["rueda_der"], robot["loca"]]

    traza = []
    for paso in range(pasos):
        sim.step()
        t = sim.getSimulationTime()
        x, y, z = sim.getObjectPosition(chasis, sim.handle_world)
        rumbo = math.degrees(sim.getObjectOrientation(chasis, sim.handle_world)[2])
        detectado, distancia, _p, _o, _n = sim.readProximitySensor(robot["sensor"])
        estorbos = [robot["obstaculo"]] + robot["paredes"]
        choque = any(sim.checkCollision(pieza, estorbo)[0] == 1
                     for pieza in piezas for estorbo in estorbos)
        traza.append({"t": t, "x": x, "y": y, "z": z, "rumbo": rumbo,
                      "detectado": detectado == 1, "distancia": distancia,
                      "choque": choque})
        if paso % 20 == 0:
            medida = f"{distancia:.3f}" if detectado == 1 else "  —  "
            estado = "EVADE" if (detectado == 1 and distancia < D_EVASION) else "avanza"
            print(f"   {t:5.2f} {x:7.3f} {y:7.3f} {z:6.3f} {rumbo:7.1f} {medida:>8}  {estado}")

    sim.stopSimulation()
    while sim.getSimulationState() != sim.simulation_stopped:
        pass
    sim.setStepping(False)
    return traza


def informar(traza):
    """Comprueba que el robot hizo lo que debía, con números en vez de impresiones."""
    print("\n--- veredicto ---")
    inicio, fin = traza[0], traza[-1]

    avance = fin["x"] - inicio["x"]
    print(f"avanzó {avance:+.3f} m en x, {fin['y']:+.3f} m en y")

    alturas = [p["z"] for p in traza]
    print(f"altura del chasis entre {min(alturas):.3f} y {max(alturas):.3f} m "
          f"(nominal {CHASIS_Z:.3f}) -> {'estable' if max(alturas) - min(alturas) < 0.02 else 'INESTABLE'}")

    detecciones = [p for p in traza if p["detectado"]]
    if detecciones:
        print(f"detectó el obstáculo desde t={detecciones[0]['t']:.2f} s, "
              f"a {detecciones[0]['distancia']:.3f} m")
    else:
        print("NUNCA detectó el obstáculo")

    evasiones = [p for p in traza if p["detectado"] and p["distancia"] < D_EVASION]
    if evasiones:
        rumbos = [p["rumbo"] for p in evasiones]
        print(f"maniobra de evasión: {len(evasiones)} pasos, "
              f"rumbo de {rumbos[0]:.1f}° a {rumbos[-1]:.1f}°")
    else:
        print("NUNCA entró en maniobra de evasión")

    minima = min((p["distancia"] for p in traza if p["detectado"]), default=None)
    if minima is not None:
        print(f"distancia mínima medida por el haz: {minima:.3f} m")

    choques = [p for p in traza if p["choque"]]
    if choques:
        print(f"CHOCÓ: {len(choques)} pasos en contacto con obstáculo o pared, "
              f"desde t={choques[0]['t']:.2f} s")
    else:
        print("nunca tocó el obstáculo ni las paredes -> evasión limpia")

    disparos = sum(1 for a, b in zip(traza, traza[1:])
                   if not a["detectado"] and b["detectado"])
    print(f"maniobras disparadas en total: {disparos}")


def main():
    sim = conectar()
    robot = construir(sim)
    if "--solo-construir" not in sys.argv:
        traza = probar(sim, robot)
        informar(traza)


if __name__ == "__main__":
    main()
