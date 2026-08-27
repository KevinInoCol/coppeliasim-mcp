"""
Construye el robot móvil de los planos y lo mete en la casa de `casa.py`.

Tracción diferencial con las dos ruedas motrices DELANTE y una rueda loca
detrás, tal como sale en los planos: el robot gira alrededor del eje motriz,
que le queda por delante del centro geométrico. Al darle Play los motores
mueven las juntas de verdad; no se empuja nada con setObjectPosition.

Cotas leídas de los planos (todas en metros, origen en el suelo bajo el centro
del chasis, +x al frente, +y a la izquierda, +z arriba):

    chasis            0.20 x 0.15 x 0.10, con 0.03 de luz al suelo
    ruedas motrices   Ø 0.10 x 0.01, en x = +0.07 e y = ±0.10
    rueda loca        en x = -0.075, rellena los 0.03 de luz
    sensor frontal    en (0.10, 0, 0.10), cono de 10°, alcance 0.10 a 0.80 m
    Kinect            encima del chasis, en z = 0.13

Detalles que condicionan el resultado:

  - El sensor es un Sharp de infrarrojos, no un láser: la hoja de datos dice
    10° y 10-80 cm, y esos 10 cm de mínimo son zona ciega de verdad. Se
    modelan con el 'offset' del sensor de proximidad, así que lo que esté más
    cerca de 10 cm NO se detecta. El script lo comprueba a tres distancias.
  - Las ruedas de los planos tienen 1 cm de espesor. Es poquísimo para Bullet:
    el contacto es casi una línea y el robot puede temblar. Se compensa con
    fricción alta y masa suficiente, y la prueba dinámica mide si la altura
    del chasis se mantiene estable.
  - El Kinect es el modelo kinect.ttm de la librería de CoppeliaSim, el mismo
    de las imágenes de referencia. Es estático y no respondable, así que
    colgarlo del chasis no altera la física.

Uso:
    python Proyecto-02-Casa/robot.py                  # construye, prueba y guarda
    python Proyecto-02-Casa/robot.py --solo-construir
    python Proyecto-02-Casa/robot.py --foto
"""

import math
import os
import sys
import time

from coppeliasim_zmqremoteapi_client import RemoteAPIClient
from dotenv import find_dotenv, load_dotenv

RUTA_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(find_dotenv())    # opcional: sin .env valen los valores por defecto

COPPELIA_HOST = os.getenv("COPPELIA_HOST", "127.0.0.1")
COPPELIA_PUERTO = int(os.getenv("COPPELIA_PUERTO", "23000"))

RUTA_ESCENA = os.path.join(RUTA_PROYECTO, "Proyecto-02-Casa", "Escena_Casa.ttt")
RUTA_KINECT = ("/Applications/coppeliaSim.app/Contents/Resources/models/"
               "components/sensors/kinect.ttm")

CHASIS_TAMANO = [0.20, 0.15, 0.10]
LUZ_SUELO = 0.03
CHASIS_Z = LUZ_SUELO + CHASIS_TAMANO[2] / 2      # 0.08: centro del chasis
CHASIS_DENSIDAD = 300.0                          # kg/m^3 -> 0.9 kg

RUEDA_RADIO = 0.05
RUEDA_ESPESOR = 0.01
RUEDA_X = 0.07                                   # delante del centro
RUEDA_Y = 0.10                                   # fuera del chasis, que mide 0.15
RUEDA_DENSIDAD = 1200.0
RUEDA_FRICCION = 1.0                             # si derrapa, no avanza

LOCA_X = -0.075
LOCA_RADIO = LUZ_SUELO / 2                       # justo la luz al suelo
LOCA_DENSIDAD = 500.0
LOCA_FRICCION = 0.0                              # se desliza: no estorba al giro

JUNTA_TORQUE = 1.0                               # N.m de par disponible

SENSOR_POS = [CHASIS_TAMANO[0] / 2, 0.0, 0.10]   # en el morro, a 10 cm del suelo
SENSOR_APERTURA = math.radians(10.0)             # hoja de datos: 10°
SENSOR_MINIMO = 0.10                             # zona ciega
SENSOR_ALCANCE = 0.80

KINECT_Z = LUZ_SUELO + CHASIS_TAMANO[2]          # apoyado en el techo del chasis

MASCARA_ROBOT = 0xFF00              # las piezas del robot no chocan entre sí

# Dónde arranca el robot dentro de la casa: en el pasillo, junto a la entrada
# oeste y mirando al este.
PARTIDA = (-3.0, 0.0, 0.0)

V_PRUEBA = 4.0                      # rad/s -> 0.2 m/s con ruedas de 5 cm
T_RECTA = 2.5
T_GIRO = 2.0


def conectar():
    return RemoteAPIClient(host=COPPELIA_HOST, port=COPPELIA_PUERTO).require("sim")


def limpiar(sim):
    """Borra un robot de una corrida anterior. La casa no se toca."""
    borrados = []
    for ruta in ("/Robot", "/kinect"):
        try:
            raiz = sim.getObject(ruta)
        except Exception:
            continue
        arbol = set(sim.getObjectsInTree(raiz, sim.handle_all, 0)) | {raiz}
        sim.removeObjects(list(arbol))
        borrados.append(f"{ruta} ({len(arbol)} objetos)")
    return borrados


def fijar_friccion(sim, handle, valor):
    """
    Fija el rozamiento de una forma en las dos propiedades de Bullet.

    Aquí hay una trampa que cuesta una tarde encontrar: CoppeliaSim expone
    'bullet.friction' Y 'bullet.frictionOld', y cuál manda depende de la
    versión de Bullet elegida en la barra de herramientas. Con el Bullet 2.7
    que trae la escena por defecto, la que obedece es la vieja, así que
    escribir solo 'bullet.friction' no hace absolutamente nada.

    Se midió: con la rueda loca a 'bullet.friction' = 0 pero la vieja en 1, el
    robot recorría el 87% de lo que le tocaba en recta y solo el 51% en giro,
    porque la loca frenaba como un patín y el robot giraba en skid-steer
    alrededor de su centro en vez de sobre el eje motriz. Escribiendo las dos
    propiedades: 99% y 99%. Se fija también la de ODE por si se cambia de
    motor.
    """
    for propiedad in ("bullet.friction", "bullet.frictionOld", "ode.friction"):
        try:
            sim.setFloatProperty(handle, propiedad, valor)
        except Exception:
            pass


def hacer_dinamico(sim, handle, densidad, friccion):
    """Deja una forma lista para el motor de física: masa, inercia y contacto."""
    sim.setBoolProperty(handle, "dynamic", True)
    sim.setBoolProperty(handle, "respondable", True)
    sim.setIntProperty(handle, "respondableMask", MASCARA_ROBOT)
    if sim.computeMassAndInertia(handle, densidad) != 1:
        raise RuntimeError(f"{sim.getObjectAlias(handle, 1)} no es convexa: sin masa")
    fijar_friccion(sim, handle, friccion)


def crear_chasis(sim, partida):
    x, y, yaw = partida
    chasis = sim.createPrimitiveShape(sim.primitiveshape_cuboid, CHASIS_TAMANO, 0)
    sim.setObjectAlias(chasis, "Robot")
    sim.setObjectPosition(chasis, [x, y, CHASIS_Z], sim.handle_world)
    sim.setObjectOrientation(chasis, [0.0, 0.0, yaw], sim.handle_world)
    hacer_dinamico(sim, chasis, CHASIS_DENSIDAD, 0.5)
    return chasis


def crear_rueda(sim, chasis, lado, alias_junta, alias_rueda):
    """Junta motriz + rueda de un lado. `lado` es +1 (izquierda) o -1 (derecha)."""
    # Coordenadas locales al chasis, cuyo origen está en su centro, a CHASIS_Z
    # del suelo: por eso la z de la rueda sale negativa.
    posicion = [RUEDA_X, lado * RUEDA_Y, RUEDA_RADIO - CHASIS_Z]

    junta = sim.createJoint(sim.joint_revolute, sim.jointmode_dynamic, 0, [0.04, 0.02])
    sim.setObjectAlias(junta, alias_junta)
    sim.setObjectParent(junta, chasis, True)
    sim.setObjectPosition(junta, posicion, chasis)
    # El eje de una junta revolute es su +Z; -90° sobre X lo pone a lo largo de
    # +Y, que es lo que hace que girar en positivo empuje el robot hacia +X.
    sim.setObjectOrientation(junta, [-math.pi / 2, 0.0, 0.0], chasis)
    sim.setIntProperty(junta, "dynCtrlMode", sim.jointdynctrl_velocity)
    sim.setFloatProperty(junta, "targetForce", JUNTA_TORQUE)
    sim.setJointTargetVelocity(junta, 0.0)

    rueda = sim.createPrimitiveShape(
        sim.primitiveshape_cylinder,
        [RUEDA_RADIO * 2, RUEDA_RADIO * 2, RUEDA_ESPESOR],
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
    Esfera trasera sin fricción, unida al chasis por un sensor de fuerza.

    El sensor de fuerza no mide nada aquí: es la forma que documenta
    CoppeliaSim de unir rígidamente dos cuerpos dinámicos. Emparentar no basta,
    y fusionar las formas obligaría a compartir fricción, cuando lo que se
    quiere es chasis con agarre y apoyo trasero que resbale.
    """
    soporte = sim.createForceSensor(0, [0, 1, 1, 0, 0], [0.005, 0.0, 0.0, 0.0, 0.0])
    sim.setObjectAlias(soporte, "SoporteLoca")
    sim.setObjectParent(soporte, chasis, True)
    sim.setObjectPosition(soporte, [LOCA_X, 0.0, LOCA_RADIO - CHASIS_Z], chasis)
    sim.setObjectOrientation(soporte, [0.0, 0.0, 0.0], chasis)

    loca = sim.createPrimitiveShape(sim.primitiveshape_spheroid, [LOCA_RADIO * 2] * 3, 0)
    sim.setObjectAlias(loca, "RuedaLoca")
    sim.setObjectParent(loca, soporte, True)
    sim.setObjectPosition(loca, [0.0, 0.0, 0.0], soporte)
    sim.setObjectOrientation(loca, [0.0, 0.0, 0.0], soporte)
    hacer_dinamico(sim, loca, LOCA_DENSIDAD, LOCA_FRICCION)
    return loca


def crear_sensor(sim, chasis):
    """Sensor de proximidad cónico con la zona ciega de la hoja de datos."""
    radio_lejano = SENSOR_ALCANCE * math.tan(SENSOR_APERTURA / 2)
    int_params = [32, 32, 4, 4, 1, 1, 0, 0]
    float_params = [
        SENSOR_MINIMO,          # offset: por debajo de esto no ve nada
        SENSOR_ALCANCE,
        0.02, 0.02, 0.02, 0.02, 0.0,
        0.002,                  # radio en la boca del cono
        radio_lejano,
        SENSOR_APERTURA,
        math.radians(45.0),
        0.0, 0.002, 0.0, 0.0,
    ]
    sensor = sim.createProximitySensor(sim.proximitysensor_cone, 16, 0,
                                       int_params, float_params)
    sim.setObjectAlias(sensor, "SensorFrontal")
    sim.setObjectParent(sensor, chasis, False)
    sim.setObjectPosition(sensor, [SENSOR_POS[0], SENSOR_POS[1],
                                   SENSOR_POS[2] - CHASIS_Z], chasis)
    # El sensor detecta por su +Z; +90° sobre Y lo deja mirando al frente.
    sim.setObjectOrientation(sensor, [0.0, math.pi / 2, 0.0], chasis)
    return sensor


def montar_kinect(sim, chasis):
    """
    Carga el kinect.ttm de la librería y lo apoya mirando al frente.

    Ojo con el giro de -90°: las cámaras rgb y depth del modelo apuntan por el
    +Y del kinect, no por su +Z ni por su +X. Sin corregirlo el robot avanza
    mirando a su izquierda, con la barra del sensor puesta a lo largo en vez de
    atravesada. Con el giro, la barra queda como en los planos y las dos
    cámaras miran adonde mira el sensor de proximidad.
    """
    if not os.path.exists(RUTA_KINECT):
        return None
    kinect = sim.loadModel(RUTA_KINECT)
    sim.setObjectParent(kinect, chasis, True)
    sim.setObjectPosition(kinect, [0.0, 0.0, KINECT_Z - CHASIS_Z], chasis)
    sim.setObjectOrientation(kinect, [0.0, 0.0, -math.pi / 2], chasis)
    return kinect


def verificar_kinect(sim, robot):
    """Comprueba que las cámaras miran al frente, comparándolas con el sensor."""
    if robot["kinect"] is None:
        return
    chasis = robot["chasis"]
    frente = sim.getObjectMatrix(robot["sensor"], chasis)
    eje_sensor = [frente[2], frente[6], frente[10]]
    for nombre in ("rgb", "depth"):
        camara = sim.getObject(f"/Robot/kinect/{nombre}")
        m = sim.getObjectMatrix(camara, chasis)
        eje = [m[2], m[6], m[10]]
        coincide = sum(a * b for a, b in zip(eje, eje_sensor))
        print(f"   cámara {nombre:<6} mira a [{eje[0]:+.2f}, {eje[1]:+.2f}, {eje[2]:+.2f}] "
              f"-> {'al frente, como el sensor' if coincide > 0.99 else 'DESALINEADA'}")


def distancia_al_suelo(altura, apertura):
    """A qué distancia el borde inferior del cono tocaría el suelo."""
    return altura / math.tan(apertura / 2)


def construir(sim):
    borrados = limpiar(sim)
    print(f"0. Limpieza: {', '.join(borrados) or 'no había robot previo'}")

    chasis = crear_chasis(sim, PARTIDA)
    print(f"1. Chasis {CHASIS_TAMANO[0]} x {CHASIS_TAMANO[1]} x {CHASIS_TAMANO[2]} m, "
          f"masa {sim.getFloatProperty(chasis, 'mass'):.3f} kg, "
          f"luz al suelo {LUZ_SUELO} m")

    junta_izq, rueda_izq = crear_rueda(sim, chasis, +1, "JuntaIzq", "RuedaIzq")
    junta_der, rueda_der = crear_rueda(sim, chasis, -1, "JuntaDer", "RuedaDer")
    print(f"2. Ruedas Ø{RUEDA_RADIO * 2} x {RUEDA_ESPESOR} m en x={RUEDA_X}, "
          f"y=±{RUEDA_Y}: {sim.getFloatProperty(rueda_izq, 'mass'):.3f} kg cada una, "
          f"motor a {JUNTA_TORQUE} N.m en modo "
          f"{sim.getIntProperty(junta_izq, 'dynCtrlMode')} (velocidad)")

    loca = crear_rueda_loca(sim, chasis)
    print(f"3. Rueda loca en x={LOCA_X}, radio {LOCA_RADIO} m, fricción {LOCA_FRICCION}")

    sensor = crear_sensor(sim, chasis)
    suelo = distancia_al_suelo(SENSOR_POS[2], SENSOR_APERTURA)
    print(f"4. Sensor cónico de {math.degrees(SENSOR_APERTURA):.0f}°, "
          f"de {SENSOR_MINIMO} a {SENSOR_ALCANCE} m, a {SENSOR_POS[2]} m del suelo")
    print(f"   el borde del haz tocaría el suelo a {suelo:.2f} m -> "
          f"{'ok, más lejos que el alcance' if suelo > SENSOR_ALCANCE else 'PROBLEMA: verá el piso'}")

    kinect = montar_kinect(sim, chasis)
    print(f"5. Kinect: {'kinect.ttm montado en z=' + str(KINECT_Z) if kinect else 'NO ENCONTRADO, se omite'}")

    robot = {"chasis": chasis, "junta_izq": junta_izq, "junta_der": junta_der,
             "rueda_izq": rueda_izq, "rueda_der": rueda_der,
             "loca": loca, "sensor": sensor, "kinect": kinect}
    verificar_kinect(sim, robot)
    return robot


def probar_sensor(sim, robot):
    """
    Comprueba la zona ciega y el alcance sin arrancar la simulación.

    `checkProximitySensor` hace el barrido en el momento, con la escena parada,
    así que se puede ir colocando el robot a distancias conocidas de una pared
    y contrastar lo que mide contra lo que debería medir.
    """
    try:
        sim.getObject("/Casa")
    except Exception:
        print("\n--- sensor: no hay casa en la escena, se omite la prueba ---")
        return

    chasis, sensor = robot["chasis"], robot["sensor"]
    pose = sim.getObjectPosition(chasis, sim.handle_world)
    cara_muro = 3.6 - 0.06          # cara interior del MuroEste
    morro = SENSOR_POS[0]

    grosor_muro = 0.12

    print("\n--- sensor contra el muro este (cara interior en x = "
          f"{cara_muro:.2f}) ---")
    print(f"   {'distancia':>10} {'detecta':>8} {'mide':>8}  qué pasa")
    for distancia in (1.20, 0.60, 0.30, 0.15, 0.05):
        x = cara_muro - distancia - morro
        sim.setObjectPosition(chasis, [x, 0.0, CHASIS_Z], sim.handle_world)
        detectado, medida, *_ = sim.checkProximitySensor(sensor, sim.handle_all)
        marca = f"{medida:.3f}" if detectado == 1 else "   —"

        if distancia > SENSOR_ALCANCE:
            explica = ("fuera de alcance" if detectado == 0
                       else "INESPERADO: debería estar fuera de alcance")
        elif distancia >= SENSOR_MINIMO:
            explica = (f"mide bien (error {abs(medida - distancia) * 1000:.0f} mm)"
                       if detectado == 1 and abs(medida - distancia) < 0.01
                       else "INESPERADO: aquí tendría que medir la pared")
        else:
            # Dentro de la zona ciega la cara del muro no existe para el sensor,
            # pero el cono sigue hasta 0.8 m y alcanza la cara TRASERA del muro.
            # Un infrarrojo real hace justo esto: por debajo del mínimo devuelve
            # lecturas que no significan lo que parecen.
            trasera = distancia + grosor_muro
            explica = (f"zona ciega: no ve la cara frontal, ve la trasera a "
                       f"{trasera:.2f} m" if detectado == 1
                       and abs(medida - trasera) < 0.01 else "zona ciega")
        print(f"   {distancia:10.2f} {'sí' if detectado == 1 else 'no':>8} "
              f"{marca:>8}  {explica}")

    sim.setObjectPosition(chasis, [pose[0], pose[1], CHASIS_Z], sim.handle_world)


def rodar(sim, robot, velocidad_izq, velocidad_der, segundos):
    """Manda velocidad a las dos juntas y devuelve la traza del recorrido."""
    sim.setJointTargetVelocity(robot["junta_izq"], velocidad_izq)
    sim.setJointTargetVelocity(robot["junta_der"], velocidad_der)
    traza = []
    for _ in range(int(segundos / sim.getSimulationTimeStep())):
        sim.step()
        x, y, z = sim.getObjectPosition(robot["chasis"], sim.handle_world)
        rumbo = math.degrees(sim.getObjectOrientation(robot["chasis"], sim.handle_world)[2])
        traza.append({"t": sim.getSimulationTime(), "x": x, "y": y, "z": z, "rumbo": rumbo})
    return traza


def probar(sim, robot):
    """Play de verdad: recta primero, giro sobre el sitio después."""
    sim.setObjectPosition(robot["chasis"], [PARTIDA[0], PARTIDA[1], CHASIS_Z],
                          sim.handle_world)
    sim.setObjectOrientation(robot["chasis"], [0.0, 0.0, PARTIDA[2]], sim.handle_world)

    sim.setStepping(True)
    sim.startSimulation()
    recta = rodar(sim, robot, V_PRUEBA, V_PRUEBA, T_RECTA)
    giro = rodar(sim, robot, -V_PRUEBA, V_PRUEBA, T_GIRO)
    rodar(sim, robot, 0.0, 0.0, 0.2)
    sim.stopSimulation()
    esperar_parada(sim)
    sim.setStepping(False)

    print(f"\n--- recta: {T_RECTA} s con las dos ruedas a {V_PRUEBA} rad/s ---")
    inicio, fin = recta[0], recta[-1]
    avance = math.hypot(fin["x"] - inicio["x"], fin["y"] - inicio["y"])
    teorico = V_PRUEBA * RUEDA_RADIO * T_RECTA
    print(f"   avanzó {avance:.3f} m (teórico sin deslizamiento {teorico:.3f} m, "
          f"rendimiento {100 * avance / teorico:.0f}%)")
    print(f"   desvío lateral {fin['y'] - inicio['y']:+.4f} m, "
          f"rumbo final {fin['rumbo']:+.1f}°")
    alturas = [p["z"] for p in recta]
    print(f"   altura del chasis entre {min(alturas):.4f} y {max(alturas):.4f} m "
          f"(nominal {CHASIS_Z:.3f}) -> "
          f"{'estable' if max(alturas) - min(alturas) < 0.005 else 'INESTABLE, tiembla'}")

    print(f"\n--- giro: {T_GIRO} s con las ruedas en sentidos opuestos ---")
    vuelta = giro_acumulado(giro)
    deriva = math.hypot(giro[-1]["x"] - giro[0]["x"], giro[-1]["y"] - giro[0]["y"])
    teorico_giro = math.degrees(V_PRUEBA * RUEDA_RADIO * T_GIRO / RUEDA_Y)
    print(f"   giró {vuelta:+.1f}° (teórico {teorico_giro:+.1f}°, "
          f"rendimiento {100 * abs(vuelta / teorico_giro):.0f}%)")

    # Si pivota sobre el eje motriz, el centro del chasis recorre la cuerda de
    # un arco de radio RUEDA_X. Comparar las dos cifras distingue un giro
    # limpio de un patinazo tipo skid-steer, que dejaría el centro casi quieto.
    cuerda = 2 * RUEDA_X * abs(math.sin(math.radians(vuelta) / 2))
    print(f"   el centro del chasis se desplazó {deriva:.3f} m; pivotando sobre "
          f"el eje motriz ({RUEDA_X} m por delante) tocaría {cuerda:.3f} m -> "
          f"{'gira sobre el eje, sin derrapar' if abs(deriva - cuerda) < 0.02 else 'DERRAPA'}")
    return recta + giro


def giro_acumulado(traza):
    """
    Suma los incrementos de rumbo en vez de restar los extremos.

    Restar el rumbo final del inicial parece lo natural y está mal en cuanto el
    robot pasa de media vuelta: el ángulo vive en [-180, 180], así que un giro
    real de +221° se lee como -139°. Acumulando paso a paso el giro sale entero.
    """
    total = 0.0
    for antes, despues in zip(traza, traza[1:]):
        total += (despues["rumbo"] - antes["rumbo"] + 180) % 360 - 180
    return total


def esperar_parada(sim, limite=10.0):
    plazo = time.time() + limite
    while sim.getSimulationState() != sim.simulation_stopped and time.time() < plazo:
        time.sleep(0.05)
    return sim.getSimulationState() == sim.simulation_stopped


def main():
    sim = conectar()
    robot = construir(sim)
    probar_sensor(sim, robot)

    if "--solo-construir" not in sys.argv:
        probar(sim, robot)
        sim.setObjectPosition(robot["chasis"], [PARTIDA[0], PARTIDA[1], CHASIS_Z],
                              sim.handle_world)
        sim.setObjectOrientation(robot["chasis"], [0.0, 0.0, PARTIDA[2]],
                                 sim.handle_world)

    if "--foto" in sys.argv:
        import casa
        ancho, alto = casa.fotografiar(sim, os.path.join(
            RUTA_PROYECTO, "Proyecto-02-Casa", "planta_con_robot.png"))
        print(f"\nPlano cenital de {ancho}x{alto} px con el robot dentro")

    if "--sin-guardar" not in sys.argv:
        sim.saveScene(RUTA_ESCENA)
        print(f"\nEscena guardada en {RUTA_ESCENA}")


if __name__ == "__main__":
    main()
