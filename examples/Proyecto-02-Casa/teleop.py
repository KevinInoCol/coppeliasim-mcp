"""
Teleoperación por teclado del robot de `robot.py`, desde la terminal.

Se conecta a la escena abierta por la API remota y va mandando velocidad a las
dos juntas motrices. No hay que tocar la escena: el robot ya tiene los motores,
esto solo les dice a qué velocidad girar.

Cómo se conduce (teclas sueltas, sin Enter):

         w  adelante                     r         volver al inicio
    a    s    d                          +  / -    más o menos velocidad
         x  atrás                        q / Esc   salir

    a = girar a izquierda, d = girar a derecha, s = PARAR, espacio también para

Las teclas van en rombo alrededor de la 's' a propósito: como son teclas de
estado y no de pulsación mantenida, hace falta una tecla de parar que caiga
bajo el dedo sin buscarla. La terminal no avisa de cuándo se suelta una tecla,
así que el modo "mantener pulsado" saldría a tirones por el retardo de
repetición del teclado; con este reparto se pulsa 'w' para arrancar y 's' para
quedarse quieto, sin pensarlo. Las flechas también valen: arriba adelante,
abajo atrás, izquierda y derecha para girar.

Dos cosas que hace el script y conviene saber:

  - Activa el modo de tiempo real de CoppeliaSim. Sin él la simulación corre
    todo lo rápido que puede (se midieron 49 s simulados en 2 s de reloj) y no
    hay reflejos humanos que valgan.
  - Frena solo si el sensor frontal ve algo a menos de FRENO_DISTANCIA. Se
    puede desactivar con --sin-freno. Marcha atrás y giros siguen permitidos,
    que si no el robot se queda clavado contra la pared.

Uso:
    python Proyecto-02-Casa/teleop.py               # hay que lanzarlo en TU terminal
    python Proyecto-02-Casa/teleop.py --sin-freno
    python Proyecto-02-Casa/teleop.py --demo        # secuencia fija, sin teclado
"""

import math
import os
import select
import sys
import termios
import time
import tty

from coppeliasim_zmqremoteapi_client import RemoteAPIClient
from dotenv import find_dotenv, load_dotenv

RUTA_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(find_dotenv())    # opcional: sin .env valen los valores por defecto

COPPELIA_HOST = os.getenv("COPPELIA_HOST", "127.0.0.1")
COPPELIA_PUERTO = int(os.getenv("COPPELIA_PUERTO", "23000"))

RUEDA_RADIO = 0.05
RUEDA_Y = 0.10

V_CRUCERO = 4.0                     # rad/s de rueda -> 0.2 m/s
V_GIRO = 3.0                        # rad/s de rueda en sentidos opuestos
V_MINIMA, V_MAXIMA = 1.0, 10.0
PASO_VELOCIDAD = 1.0

FRENO_DISTANCIA = 0.20              # m: por debajo de esto no deja avanzar
REFRESCO = 0.05                     # s entre órdenes

PARTIDA = (-3.0, 0.0, 0.0)
CHASIS_Z = 0.08

FLECHAS = {"[A": "w", "[B": "x", "[C": "d", "[D": "a"}


def conectar():
    return RemoteAPIClient(host=COPPELIA_HOST, port=COPPELIA_PUERTO).require("sim")


def buscar_robot(sim):
    try:
        return {
            "chasis": sim.getObject("/Robot"),
            "junta_izq": sim.getObject("/Robot/JuntaIzq"),
            "junta_der": sim.getObject("/Robot/JuntaDer"),
            "sensor": sim.getObject("/Robot/SensorFrontal"),
        }
    except Exception:
        sys.exit("No hay ningún /Robot en la escena. Lanza antes robot.py.")


def preparar_simulacion(sim):
    """Deja la simulación corriendo y en tiempo real, que es como se conduce."""
    sim.setBoolParam(sim.boolparam_realtime_simulation, True)
    if sim.getSimulationState() == sim.simulation_stopped:
        sim.setStepping(False)
        sim.startSimulation()
        time.sleep(0.3)
    return sim.getSimulationState() != sim.simulation_stopped


def leer_teclas():
    """Vacía lo que haya en el teclado sin bloquear. Traduce las flechas."""
    teclas = []
    while select.select([sys.stdin], [], [], 0)[0]:
        caracter = sys.stdin.read(1)
        if caracter == "\x1b":
            resto = ""
            while select.select([sys.stdin], [], [], 0.01)[0] and len(resto) < 2:
                resto += sys.stdin.read(1)
            teclas.append(FLECHAS.get(resto, "\x1b"))
        else:
            teclas.append(caracter.lower())
    return teclas


def aplicar(orden, tecla, velocidad):
    """Traduce una tecla a (avance, giro) en rad/s de rueda."""
    if tecla == "w":
        return velocidad, 0.0
    if tecla == "x":
        return -velocidad, 0.0
    if tecla == "a":
        return 0.0, V_GIRO
    if tecla == "d":
        return 0.0, -V_GIRO
    if tecla in ("s", " "):
        return 0.0, 0.0
    return orden


def mandar(sim, robot, avance, giro, frenar):
    """
    Reparte (avance, giro) entre las dos ruedas y frena si toca.

    Girar a la izquierda es rueda izquierda hacia atrás y derecha hacia
    delante: se midió que esa combinación da rumbo creciente, o sea giro
    antihorario visto desde arriba.
    """
    if frenar and avance > 0:
        avance = 0.0
    sim.setJointTargetVelocity(robot["junta_izq"], avance - giro)
    sim.setJointTargetVelocity(robot["junta_der"], avance + giro)
    return avance


def leer_sensor(sim, robot):
    detectado, distancia, *_ = sim.readProximitySensor(robot["sensor"])
    return distancia if detectado == 1 else None


def volver_al_inicio(sim, robot):
    sim.setObjectPosition(robot["chasis"], [PARTIDA[0], PARTIDA[1], CHASIS_Z],
                          sim.handle_world)
    sim.setObjectOrientation(robot["chasis"], [0.0, 0.0, PARTIDA[2]], sim.handle_world)


def estado(sim, robot, avance, giro, velocidad, distancia, frenado):
    x, y, _z = sim.getObjectPosition(robot["chasis"], sim.handle_world)
    rumbo = math.degrees(sim.getObjectOrientation(robot["chasis"], sim.handle_world)[2])
    lineal = avance * RUEDA_RADIO
    angular = math.degrees(giro * RUEDA_RADIO / RUEDA_Y)
    medida = f"{distancia:.2f} m" if distancia is not None else "  —   "
    aviso = " FRENO" if frenado else "      "
    return (f"\rx={x:+.2f} y={y:+.2f} rumbo={rumbo:+6.1f}°  "
            f"v={lineal:+.2f} m/s w={angular:+5.0f}°/s  "
            f"tope={velocidad:.0f} rad/s  sensor={medida}{aviso}   ")


def conducir(sim, robot, con_freno):
    velocidad = V_CRUCERO
    orden = (0.0, 0.0)
    print("w adelante · x atrás · a/d giro · s parar · r reiniciar · "
          "+/- velocidad · q salir\n")
    while True:
        for tecla in leer_teclas():
            if tecla in ("q", "\x1b", "\x03"):
                return
            if tecla == "r":
                volver_al_inicio(sim, robot)
                orden = (0.0, 0.0)
            elif tecla in ("+", "="):
                velocidad = min(V_MAXIMA, velocidad + PASO_VELOCIDAD)
            elif tecla == "-":
                velocidad = max(V_MINIMA, velocidad - PASO_VELOCIDAD)
            else:
                orden = aplicar(orden, tecla, velocidad)

        if sim.getSimulationState() == sim.simulation_stopped:
            print("\nLa simulación se paró desde la GUI. Fin.")
            return

        distancia = leer_sensor(sim, robot)
        frenar = con_freno and distancia is not None and distancia < FRENO_DISTANCIA
        avance = mandar(sim, robot, orden[0], orden[1], frenar)
        print(estado(sim, robot, avance, orden[1], velocidad, distancia,
                     frenar and orden[0] > 0), end="", flush=True)
        time.sleep(REFRESCO)


def demostracion(sim, robot, con_freno):
    """Secuencia fija para comprobar que el mando llega, sin teclado."""
    guion = [("adelante", 4.0, 0.0, 1.5), ("girar izquierda", 0.0, 3.0, 1.0),
             ("adelante", 4.0, 0.0, 1.5), ("girar derecha", 0.0, -3.0, 1.0),
             ("parar", 0.0, 0.0, 0.5)]
    for nombre, avance, giro, segundos in guion:
        fin = time.time() + segundos
        while time.time() < fin:
            distancia = leer_sensor(sim, robot)
            frenar = con_freno and distancia is not None and distancia < FRENO_DISTANCIA
            mandar(sim, robot, avance, giro, frenar)
            time.sleep(REFRESCO)
        x, y, _z = sim.getObjectPosition(robot["chasis"], sim.handle_world)
        rumbo = math.degrees(sim.getObjectOrientation(robot["chasis"], sim.handle_world)[2])
        print(f"   {nombre:<16} -> x={x:+.3f} y={y:+.3f} rumbo={rumbo:+7.1f}°")
    mandar(sim, robot, 0.0, 0.0, False)


def main():
    sim = conectar()
    robot = buscar_robot(sim)
    con_freno = "--sin-freno" not in sys.argv

    if not preparar_simulacion(sim):
        sys.exit("No se pudo arrancar la simulación.")
    print(f"Robot listo. Tiempo real activado. Freno de emergencia: "
          f"{'a ' + str(FRENO_DISTANCIA) + ' m' if con_freno else 'desactivado'}")

    try:
        if "--demo" in sys.argv:
            demostracion(sim, robot, con_freno)
        elif not sys.stdin.isatty():
            sys.exit("Esto necesita una terminal de verdad: lánzalo tú, o usa --demo.")
        else:
            descriptor = sys.stdin.fileno()
            antiguo = termios.tcgetattr(descriptor)
            try:
                tty.setcbreak(descriptor)
                conducir(sim, robot, con_freno)
            finally:
                termios.tcsetattr(descriptor, termios.TCSADRAIN, antiguo)
                print()
    finally:
        mandar(sim, robot, 0.0, 0.0, False)
        print("Ruedas paradas. La simulación sigue corriendo.")


if __name__ == "__main__":
    main()
