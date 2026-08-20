"""
Servidor MCP para controlar CoppeliaSim 4.10 desde Claude Code vía ZMQ Remote API.

Sin afiliación, respaldo ni mantenimiento por parte de Coppelia Robotics AG.
CoppeliaSim es una marca de Coppelia Robotics AG. Esto es una integración
independiente de terceros, que habla con un simulador instalado y licenciado
aparte; no incluye ni redistribuye ninguna parte de él.

Escrito contra la API real de CoppeliaSim 4.10.0 rev0 (cada llamada sim.* fue
verificada contra Contents/Resources/manual/index/sim.json de la instalación
local) y contra el SDK de MCP v2, donde FastMCP pasó a llamarse MCPServer.

Decisiones de seguridad, a diferencia de los servidores MCP de CoppeliaSim que
circulan por ahí:

  - NO expone ejecución de Lua arbitrario. El Lua de CoppeliaSim tiene acceso a
    `os` e `io`, así que una tool de ese tipo convierte cualquier prompt
    injection (por ejemplo, texto dentro de una escena .ttt de terceros) en
    ejecución de comandos sobre el Mac.
  - `cargar_escena` solo abre archivos por debajo de DIRECTORIO_ESCENAS, con la
    ruta resuelta antes de comparar, para que ../../ y los symlinks no sirvan
    para escapar.
  - MODO_LECTURA=1 deshabilita de golpe todas las tools que mutan la escena.
  - Una sola conexión ZMQ reutilizada, no un socket nuevo por llamada.

Requisitos previos:
    - CoppeliaSim 4.10 abierto, con el add-on "ZMQ remote API" activo (viene
      habilitado por defecto, escuchando en el puerto 23000).

Registrar en Claude Code:
    claude mcp add coppelia -- uvx coppeliasim-mcp

Ejecutar suelto, para comprobar que arranca:
    uvx coppeliasim-mcp
"""

import json
import math
import os
import sys
from pathlib import Path

import zmq
from coppeliasim_zmqremoteapi_client import RemoteAPIClient
from dotenv import load_dotenv
from mcp.server import MCPServer

load_dotenv()

COPPELIA_HOST = os.getenv("COPPELIA_HOST", "127.0.0.1")
COPPELIA_PUERTO = int(os.getenv("COPPELIA_PUERTO", "23000"))
# Por defecto, solo el directorio de trabajo. Apuntar a ~/Documents daría a
# cualquier prompt injection acceso de lectura a todo lo que haya ahí debajo.
DIRECTORIO_ESCENAS = os.getenv("COPPELIA_DIRECTORIO_ESCENAS", os.getcwd())
MODO_LECTURA = os.getenv("COPPELIA_MODO_LECTURA", "0") == "1"
TIMEOUT = float(os.getenv("COPPELIA_TIMEOUT", "10"))

EXTENSIONES_ESCENA = {".ttt", ".ttm", ".simscene.xml", ".xml"}

TIPOS_OBJETO = {
    "todos": "handle_all",
    "shape": "object_shape_type",
    "joint": "object_joint_type",
    "dummy": "object_dummy_type",
    "sensor": "object_proximitysensor_type",
    "camara": "object_camera_type",
    "luz": "object_light_type",
    "path": "object_path_type",
}

PRIMITIVAS = {
    "cubo": "primitiveshape_cuboid",
    "esfera": "primitiveshape_spheroid",
    "cilindro": "primitiveshape_cylinder",
    "cono": "primitiveshape_cone",
    "capsula": "primitiveshape_capsule",
    "disco": "primitiveshape_disc",
    "toroide": "primitiveshape_torus",
}

mcp = MCPServer("CoppeliaSim")

_cliente = None
_sim = None


# ─── Conexión ────────────────────────────────────────────────────────────────

def limitar_espera(cliente):
    """
    Pone un tope a lo que el cliente espera una respuesta.

    Hace falta porque el `timeout` del cliente ZMQ no protege de esto: ese valor
    viaja DENTRO de la petición, o sea que es el tiempo que espera CoppeliaSim,
    no el que espera el cliente. Si no hay nadie escuchando en el puerto, el
    socket se queda bloqueado en recv esperando una respuesta que nunca llega, y
    con el valor por defecto del cliente eso son diez minutos.

    Es el fallo más probable de un primer arranque —CoppeliaSim cerrado, o el
    add-on desactivado— y sin este tope se manifiesta como un cuelgue en vez de
    como un mensaje que diga qué revisar.

    LINGER a 0 para que descartar la conexión no bloquee al cerrar el socket.
    """
    cliente.socket.setsockopt(zmq.RCVTIMEO, int(TIMEOUT * 1000))
    cliente.socket.setsockopt(zmq.LINGER, 0)


def obtener_sim():
    """Devuelve el handle `sim`, reutilizando la conexión ZMQ entre llamadas."""
    global _cliente, _sim
    if _sim is None:
        cliente = RemoteAPIClient(host=COPPELIA_HOST, port=COPPELIA_PUERTO)
        limitar_espera(cliente)
        # `require` es el primer viaje de ida y vuelta: si CoppeliaSim no está,
        # falla aquí, ya con el tope puesto. Solo se cachea si tuvo éxito, para
        # no dejar guardado un cliente a medio construir.
        _sim = cliente.require("sim")
        _cliente = cliente
    return _sim


def reiniciar_conexion():
    """Descarta la conexión cacheada; la siguiente llamada reconecta."""
    global _cliente, _sim
    if _cliente is not None:
        try:
            _cliente.socket.close()
            _cliente.context.term()
        except Exception:
            pass    # ya estaba roto; lo que importa es no reusarlo
    _cliente = None
    _sim = None


def ejecutar(funcion):
    """
    Corre una operación contra el simulador traduciendo los fallos a texto.

    Distingue dos clases de fallo, porque se arreglan de forma distinta y
    confundirlas cuesta caro:

      - El simulador respondió, pero rechazó la operación (objeto inexistente,
        argumento inválido). La conexión está sana: se informa el error y se
        mantiene el socket. Tirarla aquí obligaría a reconectar por cada typo.
      - No hubo respuesta (CoppeliaSim cerrado, add-on apagado, socket muerto).
        Ahí sí se descarta la conexión para que la siguiente llamada reconecte.
        Un socket REQ de ZMQ queda inservible tras un timeout, así que reusarlo
        no es una opción: hay que tirarlo.
    """
    try:
        return funcion(obtener_sim())
    except zmq.Again:
        reiniciar_conexion()
        return (
            f"CoppeliaSim no respondió en {TIMEOUT:g} s ({COPPELIA_HOST}:{COPPELIA_PUERTO}).\n"
            "Revisa que CoppeliaSim esté abierto y que el add-on 'ZMQ remote API' esté "
            "activo. Si el simulador está ocupado con una operación larga, súbelo "
            "con COPPELIA_TIMEOUT."
        )
    except Exception as error:
        mensaje = str(error)
        if "in sim." in mensaje or "in simxxx." in mensaje:
            detalle = mensaje.split(": ", 1)[-1].strip()
            return f"CoppeliaSim rechazó la operación: {detalle}"
        reiniciar_conexion()
        return (
            f"Sin respuesta de CoppeliaSim en {COPPELIA_HOST}:{COPPELIA_PUERTO}: {mensaje}\n"
            "Revisa que CoppeliaSim esté abierto y que el add-on 'ZMQ remote API' esté activo."
        )


def ruta_de(nombre: str) -> str:
    """
    Normaliza un nombre de objeto a la ruta que espera sim.getObject.

    En CoppeliaSim 4.x, sim.getObject busca por *ruta* ('/Cuboid'), no por
    nombre suelto ('Cuboid'). Pasarle el nombre pelado es el error que rompe
    la mayoría de los ejemplos que circulan.
    """
    return nombre if nombre.startswith("/") else f"/{nombre}"


def escritura_permitida():
    """Devuelve el mensaje de bloqueo si el servidor está en modo lectura."""
    if MODO_LECTURA:
        return (
            "Bloqueado: el servidor corre con COPPELIA_MODO_LECTURA=1. "
            "Quita esa variable del .env para permitir modificar la escena."
        )
    return None


# ─── Control de simulación ───────────────────────────────────────────────────

@mcp.tool()
def iniciar_simulacion() -> str:
    """Inicia la simulación en CoppeliaSim."""
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        sim.startSimulation()
        return "Simulación iniciada."

    return ejecutar(accion)


@mcp.tool()
def detener_simulacion() -> str:
    """Detiene la simulación en CoppeliaSim."""
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        sim.stopSimulation()
        return "Simulación detenida."

    return ejecutar(accion)


@mcp.tool()
def pausar_simulacion() -> str:
    """Pausa la simulación en CoppeliaSim."""
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        sim.pauseSimulation()
        return "Simulación pausada."

    return ejecutar(accion)


@mcp.tool()
def estado_simulacion() -> str:
    """Consulta si la simulación está detenida, corriendo o pausada."""

    def accion(sim):
        estado = sim.getSimulationState()
        etiquetas = {
            sim.simulation_stopped: "detenida",
            sim.simulation_paused: "pausada",
            sim.simulation_advancing_firstafterstop: "corriendo (primer paso)",
            sim.simulation_advancing_running: "corriendo",
            sim.simulation_advancing_lastbeforepause: "corriendo (por pausar)",
            sim.simulation_advancing_firstafterpause: "corriendo (reanudada)",
            sim.simulation_advancing_lastbeforestop: "corriendo (por detenerse)",
        }
        return f"Estado: {etiquetas.get(estado, f'desconocido (código {estado})')}"

    return ejecutar(accion)


@mcp.tool()
def tiempo_simulacion() -> str:
    """Devuelve el tiempo de simulación transcurrido, en segundos."""
    return ejecutar(lambda sim: f"Tiempo de simulación: {sim.getSimulationTime():.4f} s")


# ─── Escena ──────────────────────────────────────────────────────────────────

@mcp.tool()
def cargar_escena(ruta: str) -> str:
    """
    Carga una escena .ttt o .xml desde disco.

    Solo se permiten rutas por debajo del directorio configurado en
    COPPELIA_DIRECTORIO_ESCENAS.
    """
    if bloqueo := escritura_permitida():
        return bloqueo

    base = Path(DIRECTORIO_ESCENAS).expanduser().resolve()
    try:
        destino = Path(ruta).expanduser().resolve(strict=True)
    except FileNotFoundError:
        return f"No existe el archivo: {ruta}"

    if not destino.is_relative_to(base):
        return (
            f"Bloqueado: '{destino}' está fuera de {base}. "
            "Mueve la escena ahí o cambia COPPELIA_DIRECTORIO_ESCENAS."
        )
    if not any(destino.name.endswith(ext) for ext in EXTENSIONES_ESCENA):
        return f"Bloqueado: '{destino.name}' no es una escena ({', '.join(sorted(EXTENSIONES_ESCENA))})."

    def accion(sim):
        sim.loadScene(str(destino))
        return f"Escena cargada: {destino}"

    return ejecutar(accion)


@mcp.tool()
def cerrar_escena() -> str:
    """Cierra la escena actual."""
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        sim.closeScene()
        return "Escena cerrada."

    return ejecutar(accion)


@mcp.tool()
def listar_objetos(tipo: str = "todos") -> str:
    """
    Lista los objetos de la escena actual con su ruta y su handle.

    tipo: 'todos', 'shape', 'joint', 'dummy', 'sensor', 'camara', 'luz', 'path'.
    """

    def accion(sim):
        if tipo not in TIPOS_OBJETO:
            return f"Tipo desconocido '{tipo}'. Válidos: {', '.join(TIPOS_OBJETO)}"
        constante = getattr(sim, TIPOS_OBJETO[tipo])
        handles = sim.getObjectsInTree(sim.handle_scene, constante, 0)
        objetos = [
            {"ruta": sim.getObjectAlias(handle, 1), "handle": handle}
            for handle in handles
        ]
        return json.dumps({"total": len(objetos), "objetos": objetos}, ensure_ascii=False)

    return ejecutar(accion)


# ─── Objetos ─────────────────────────────────────────────────────────────────

@mcp.tool()
def obtener_posicion(nombre: str, relativo_a: str = "mundo") -> str:
    """
    Devuelve la posición [x, y, z] de un objeto, en metros.

    relativo_a: 'mundo' o la ruta de otro objeto (por ejemplo '/Cuboid').
    """

    def accion(sim):
        handle = sim.getObject(ruta_de(nombre))
        referencia = sim.handle_world if relativo_a == "mundo" else sim.getObject(ruta_de(relativo_a))
        posicion = sim.getObjectPosition(handle, referencia)
        return json.dumps({"objeto": nombre, "posicion": posicion}, ensure_ascii=False)

    return ejecutar(accion)


@mcp.tool()
def fijar_posicion(nombre: str, x: float, y: float, z: float, relativo_a: str = "mundo") -> str:
    """Mueve un objeto a la posición (x, y, z), en metros."""
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        handle = sim.getObject(ruta_de(nombre))
        referencia = sim.handle_world if relativo_a == "mundo" else sim.getObject(ruta_de(relativo_a))
        sim.setObjectPosition(handle, [x, y, z], referencia)
        return f"'{nombre}' movido a ({x}, {y}, {z})."

    return ejecutar(accion)


@mcp.tool()
def obtener_orientacion(nombre: str, relativo_a: str = "mundo") -> str:
    """Devuelve la orientación de un objeto como ángulos de Euler en radianes."""

    def accion(sim):
        handle = sim.getObject(ruta_de(nombre))
        referencia = sim.handle_world if relativo_a == "mundo" else sim.getObject(ruta_de(relativo_a))
        angulos = sim.getObjectOrientation(handle, referencia)
        return json.dumps(
            {"objeto": nombre, "orientacion_rad": angulos}, ensure_ascii=False
        )

    return ejecutar(accion)


@mcp.tool()
def fijar_orientacion(
    nombre: str, alfa: float, beta: float, gamma: float, relativo_a: str = "mundo"
) -> str:
    """Fija la orientación de un objeto con ángulos de Euler en radianes."""
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        handle = sim.getObject(ruta_de(nombre))
        referencia = sim.handle_world if relativo_a == "mundo" else sim.getObject(ruta_de(relativo_a))
        sim.setObjectOrientation(handle, [alfa, beta, gamma], referencia)
        return f"Orientación de '{nombre}' fijada a ({alfa}, {beta}, {gamma}) rad."

    return ejecutar(accion)


@mcp.tool()
def eliminar_objeto(nombre: str) -> str:
    """Elimina un objeto de la escena por su ruta."""
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        handle = sim.getObject(ruta_de(nombre))
        sim.removeObject(handle)
        return f"Objeto '{nombre}' eliminado."

    return ejecutar(accion)


@mcp.tool()
def crear_primitiva(
    forma: str,
    tamano_x: float = 0.1,
    tamano_y: float = 0.1,
    tamano_z: float = 0.1,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
) -> str:
    """
    Crea una forma primitiva en la escena y devuelve su ruta.

    forma: 'cubo', 'esfera', 'cilindro', 'cono', 'capsula', 'disco', 'toroide'.
    Tamaños y posición en metros.
    """
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        if forma not in PRIMITIVAS:
            return f"Forma desconocida '{forma}'. Válidas: {', '.join(PRIMITIVAS)}"
        constante = getattr(sim, PRIMITIVAS[forma])
        handle = sim.createPrimitiveShape(constante, [tamano_x, tamano_y, tamano_z], 0)
        sim.setObjectPosition(handle, [x, y, z], sim.handle_world)
        return f"Creado {forma} '{sim.getObjectAlias(handle, 1)}' en ({x}, {y}, {z})."

    return ejecutar(accion)


@mcp.tool()
def emparentar_objeto(objeto: str, padre: str, mantener_pose: bool = True) -> str:
    """
    Cuelga un objeto de otro, para que se muevan como un solo cuerpo.

    padre: ruta del nuevo padre, o 'mundo' para devolver el objeto a la raíz.
    mantener_pose: True deja el objeto donde está; False lo lleva al origen del padre.

    Ojo: emparentar renumera las rutas de los hermanos ('/Cylinder[3]' puede
    pasar a ser '/Cylinder[1]'). Si vas a emparentar varias piezas seguidas,
    vuelve a listar los objetos entre una llamada y la siguiente.
    """
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        handle = sim.getObject(ruta_de(objeto))
        destino = -1 if padre == "mundo" else sim.getObject(ruta_de(padre))
        sim.setObjectParent(handle, destino, mantener_pose)
        actual = sim.getObjectParent(handle)
        nombre_padre = sim.getObjectAlias(actual, 1) if actual >= 0 else "mundo"
        return f"'{sim.getObjectAlias(handle, 1)}' ahora cuelga de '{nombre_padre}'."

    return ejecutar(accion)


@mcp.tool()
def fijar_detectable(nombre: str, detectable: bool = True) -> str:
    """
    Marca o desmarca un objeto como detectable por los sensores de proximidad.

    Un objeto no detectable es invisible para `leer_sensor_proximidad`, aunque
    esté justo delante del sensor. Es la causa habitual de un sensor que 'no
    funciona'.
    """
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        handle = sim.getObject(ruta_de(nombre))
        propiedades = sim.getObjectSpecialProperty(handle)
        if detectable:
            propiedades |= sim.objectspecialproperty_detectable_all
        else:
            propiedades &= ~sim.objectspecialproperty_detectable_all
        sim.setObjectSpecialProperty(handle, propiedades)
        estado = "detectable" if detectable else "no detectable"
        return f"'{sim.getObjectAlias(handle, 1)}' quedó {estado}."

    return ejecutar(accion)

# ─── Articulaciones ──────────────────────────────────────────────────────────

@mcp.tool()
def obtener_posicion_junta(junta: str) -> str:
    """Lee la posición de una articulación: radianes si es rotativa, metros si es prismática."""

    def accion(sim):
        handle = sim.getObject(ruta_de(junta))
        return json.dumps(
            {"junta": junta, "posicion": sim.getJointPosition(handle)}, ensure_ascii=False
        )

    return ejecutar(accion)


@mcp.tool()
def fijar_objetivo_junta(junta: str, posicion: float) -> str:
    """Fija la posición objetivo de una articulación (radianes o metros)."""
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        handle = sim.getObject(ruta_de(junta))
        sim.setJointTargetPosition(handle, posicion)
        return f"Objetivo de '{junta}' fijado en {posicion}."

    return ejecutar(accion)


@mcp.tool()
def fijar_velocidad_junta(junta: str, velocidad: float) -> str:
    """Fija la velocidad objetivo de una articulación."""
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        handle = sim.getObject(ruta_de(junta))
        sim.setJointTargetVelocity(handle, velocidad)
        return f"Velocidad de '{junta}' fijada en {velocidad}."

    return ejecutar(accion)


@mcp.tool()
def obtener_fuerza_junta(junta: str) -> str:
    """Lee la fuerza o par medido en una articulación."""

    def accion(sim):
        handle = sim.getObject(ruta_de(junta))
        return json.dumps(
            {"junta": junta, "fuerza": sim.getJointForce(handle)}, ensure_ascii=False
        )

    return ejecutar(accion)


# ─── Sensores ────────────────────────────────────────────────────────────────

@mcp.tool()
def leer_sensor_proximidad(sensor: str) -> str:
    """Lee un sensor de proximidad: si detecta algo, a qué distancia y en qué punto."""

    def accion(sim):
        handle = sim.getObject(ruta_de(sensor))
        detectado, distancia, punto, objeto, normal = sim.readProximitySensor(handle)
        return json.dumps(
            {
                "sensor": sensor,
                "detectado": bool(detectado),
                "distancia": distancia,
                "punto": punto,
                "objeto_detectado": sim.getObjectAlias(objeto, 1) if objeto > 0 else None,
            },
            ensure_ascii=False,
        )

    return ejecutar(accion)


@mcp.tool()
def comprobar_sensor_proximidad(sensor: str) -> str:
    """
    Detecta ahora mismo con un sensor de proximidad, sin necesidad de simulación.

    Diferencia con `leer_sensor_proximidad`: esa tool NO detecta, solo devuelve
    el resultado del último barrido que hizo el simulador, así que con la
    simulación detenida siempre dice que no hay nada. Esta hace la detección en
    el momento, y sirve para verificar una escena en reposo.
    """

    def accion(sim):
        handle = sim.getObject(ruta_de(sensor))
        estado, distancia, punto, objeto, normal = sim.checkProximitySensor(handle, sim.handle_all)
        detectado = estado == 1
        return json.dumps(
            {
                "sensor": sensor,
                "detectado": detectado,
                "distancia": distancia if detectado else None,
                "punto": punto if detectado else None,
                "objeto_detectado": sim.getObjectAlias(objeto, 1) if detectado else None,
            },
            ensure_ascii=False,
        )

    return ejecutar(accion)


@mcp.tool()
def crear_sensor_proximidad(
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    alcance: float = 0.8,
    apertura_grados: float = 10.0,
    padre: str = "mundo",
    alias: str = "SensorProximidad",
) -> str:
    """
    Crea un sensor de proximidad cónico y lo orienta hacia el frente (+X).

    x, y, z: posición en metros, relativa al padre (o al mundo si padre='mundo').
    alcance: hasta dónde ve, en metros.
    apertura_grados: apertura total del cono. Cuanto más ancho, más 've' de lado.
    padre: ruta del objeto del que debe colgar, por ejemplo el chasis de un robot.

    Dos trampas de geometría, por si el sensor 'no detecta lo que debería':
      - El sensor mira a lo largo de su eje +Z. Esta tool lo rota 90° sobre Y
        para que mire al frente (+X), que es la convención de avance habitual.
      - Un cono ancho en horizontal ve el SUELO antes que el obstáculo: con
        media apertura a y el sensor a altura h, el suelo entra en el cono a
        h/tan(a) metros. Si eso queda por debajo del alcance, el sensor
        reportará el piso. Estrecha la apertura o sube el sensor.
    """
    if bloqueo := escritura_permitida():
        return bloqueo

    def accion(sim):
        if not 0 < apertura_grados < 180:
            return f"apertura_grados fuera de rango: {apertura_grados} (debe estar entre 0 y 180)."
        if alcance <= 0:
            return f"El alcance debe ser positivo: {alcance}."

        apertura = math.radians(apertura_grados)
        int_params = [32, 32, 4, 4, 1, 1, 0, 0]
        float_params = [
            0.0,                                   # offset del volumen
            alcance,                               # alcance
            0.05, 0.05,                            # x/y size (solo tipo pirámide)
            0.05, 0.05,                            # x/y size far
            0.0,                                   # inside gap
            0.005,                                 # radio cerca
            alcance * math.tan(apertura / 2),      # radio lejos, coherente con la apertura
            apertura,                              # apertura del cono
            math.radians(45),                      # ángulo umbral
            0.0,                                   # distancia mínima de detección
            0.005,                                 # tamaño del punto de detección
            0.0, 0.0,                              # reservados
        ]
        handle = sim.createProximitySensor(sim.proximitysensor_cone, 16, 0, int_params, float_params)
        sim.setObjectAlias(handle, alias)

        referencia = sim.handle_world
        if padre != "mundo":
            referencia = sim.getObject(ruta_de(padre))
            sim.setObjectParent(handle, referencia, False)
        sim.setObjectPosition(handle, [x, y, z], referencia)
        sim.setObjectOrientation(handle, [0.0, math.pi / 2, 0.0], referencia)

        ruta = sim.getObjectAlias(handle, 1)
        return (
            f"Creado sensor de proximidad '{ruta}' en ({x}, {y}, {z}) respecto a {padre}, "
            f"cono de {apertura_grados}° y alcance {alcance} m, mirando a +X."
        )

    return ejecutar(accion)

# ─── Alias multilingües ──────────────────────────────────────────────────────

# Las tools se definen en español, y aquí se registran alias en inglés y
# portugués sobre las MISMAS funciones: un alias no duplica lógica, solo añade
# un nombre más al catálogo.
#
# Por qué están apagados por defecto: el catálogo de tools viaja en el contexto
# de cada petición al modelo, así que pasar de 23 a 69 tools triplica ese gasto
# en todas las peticiones, no solo en las que usan CoppeliaSim. Y un catálogo
# más grande también le da al modelo más ocasiones de elegir mal.
#
# Vale la pena saber que el modelo NO necesita el alias para entenderte en otro
# idioma: los nombres de tools son identificadores, no texto de cara al usuario.
# Puedes pedirle "move the cube forward" y usará `fijar_posicion` sin problema.
# Los alias sirven para leer el catálogo de un vistazo, o para escribir prompts
# que nombren la tool explícitamente.
#
# Se activan con COPPELIA_IDIOMAS, por ejemplo: es,en,pt

IDIOMAS_DISPONIBLES = ("es", "en", "pt")

ALIAS = {
    "iniciar_simulacion": {
        "en": ("start_simulation", "Start the simulation in CoppeliaSim."),
        "pt": ("iniciar_simulacao", "Inicia a simulação no CoppeliaSim."),
    },
    "detener_simulacion": {
        "en": ("stop_simulation", "Stop the simulation in CoppeliaSim."),
        "pt": ("parar_simulacao", "Para a simulação no CoppeliaSim."),
    },
    "pausar_simulacion": {
        "en": ("pause_simulation", "Pause the simulation in CoppeliaSim."),
        "pt": ("pausar_simulacao", "Pausa a simulação no CoppeliaSim."),
    },
    "estado_simulacion": {
        "en": ("simulation_state", "Report whether the simulation is stopped, running or paused."),
        "pt": ("estado_simulacao", "Informa se a simulação está parada, rodando ou pausada."),
    },
    "tiempo_simulacion": {
        "en": ("simulation_time", "Return the current simulation time, in seconds."),
        "pt": ("tempo_simulacao", "Retorna o tempo atual de simulação, em segundos."),
    },
    "cargar_escena": {
        "en": ("load_scene", "Load a .ttt or .xml scene from disk, restricted to the configured folder."),
        "pt": ("carregar_cena", "Carrega uma cena .ttt ou .xml do disco, restrita à pasta configurada."),
    },
    "cerrar_escena": {
        "en": ("close_scene", "Close the current scene."),
        "pt": ("fechar_cena", "Fecha a cena atual."),
    },
    "listar_objetos": {
        "en": ("list_objects", "List the objects in the current scene with their path and handle."),
        "pt": ("listar_objetos_cena", "Lista os objetos da cena atual com seu caminho e handle."),
    },
    "obtener_posicion": {
        "en": ("get_position", "Return an object's [x, y, z] position, in meters."),
        "pt": ("obter_posicao", "Retorna a posição [x, y, z] de um objeto, em metros."),
    },
    "fijar_posicion": {
        "en": ("set_position", "Move an object to position (x, y, z), in meters."),
        "pt": ("definir_posicao", "Move um objeto para a posição (x, y, z), em metros."),
    },
    "obtener_orientacion": {
        "en": ("get_orientation", "Return an object's Euler angles, in radians."),
        "pt": ("obter_orientacao", "Retorna os ângulos de Euler de um objeto, em radianos."),
    },
    "fijar_orientacion": {
        "en": ("set_orientation", "Set an object's orientation from Euler angles, in radians."),
        "pt": ("definir_orientacao", "Define a orientação de um objeto por ângulos de Euler, em radianos."),
    },
    "eliminar_objeto": {
        "en": ("delete_object", "Remove an object from the scene by its path."),
        "pt": ("remover_objeto", "Remove um objeto da cena pelo seu caminho."),
    },
    "crear_primitiva": {
        "en": ("create_primitive", "Create a primitive shape (cuboid, sphere, cylinder, cone, capsule, disc, torus)."),
        "pt": ("criar_primitiva", "Cria uma forma primitiva (cubo, esfera, cilindro, cone, cápsula, disco, toro)."),
    },
    "emparentar_objeto": {
        "en": ("set_parent", "Attach an object to another in the hierarchy, so they move together."),
        "pt": ("vincular_objeto", "Vincula um objeto a outro na hierarquia, para que se movam juntos."),
    },
    "fijar_detectable": {
        "en": ("set_detectable", "Mark or unmark an object as detectable by proximity sensors."),
        "pt": ("definir_detectavel", "Marca ou desmarca um objeto como detectável por sensores de proximidade."),
    },
    "obtener_posicion_junta": {
        "en": ("get_joint_position", "Return a joint's position, in radians or meters."),
        "pt": ("obter_posicao_junta", "Retorna a posição de uma junta, em radianos ou metros."),
    },
    "fijar_objetivo_junta": {
        "en": ("set_joint_target", "Set a joint's target position."),
        "pt": ("definir_alvo_junta", "Define a posição alvo de uma junta."),
    },
    "fijar_velocidad_junta": {
        "en": ("set_joint_velocity", "Set a joint's target velocity."),
        "pt": ("definir_velocidade_junta", "Define a velocidade alvo de uma junta."),
    },
    "obtener_fuerza_junta": {
        "en": ("get_joint_force", "Return the force or torque measured at a joint."),
        "pt": ("obter_forca_junta", "Retorna a força ou torque medido em uma junta."),
    },
    "leer_sensor_proximidad": {
        "en": ("read_proximity_sensor", "Read the simulator's last proximity sensor pass. Does not detect on its own."),
        "pt": ("ler_sensor_proximidade", "Lê a última varredura do sensor feita pelo simulador. Não detecta por si só."),
    },
    "comprobar_sensor_proximidad": {
        "en": ("check_proximity_sensor", "Detect right now with a proximity sensor, no simulation needed."),
        "pt": ("verificar_sensor_proximidade", "Detecta agora com um sensor de proximidade, sem precisar de simulação."),
    },
    "crear_sensor_proximidad": {
        "en": ("create_proximity_sensor", "Create a cone-shaped proximity sensor aimed forward (+X)."),
        "pt": ("criar_sensor_proximidade", "Cria um sensor de proximidade cônico apontado para frente (+X)."),
    },
}


def idiomas_pedidos():
    """
    Lee COPPELIA_IDIOMAS y devuelve los idiomas de alias a registrar.

    'es' es el canónico y nunca genera alias. Acepta 'todos'/'all' como atajo.
    Un idioma desconocido se ignora en silencio: no vale tumbar el servidor,
    y encima antes de que el usuario pueda leer el error, por un typo en el .env.
    """
    crudo = os.getenv("COPPELIA_IDIOMAS", "es").strip().lower()
    if crudo in ("todos", "all"):
        pedidos = list(IDIOMAS_DISPONIBLES)
    else:
        pedidos = [parte.strip() for parte in crudo.split(",") if parte.strip()]
    return [i for i in pedidos if i in IDIOMAS_DISPONIBLES and i != "es"]


def registrar_alias():
    """Registra los alias sobre las mismas funciones ya decoradas. Idempotente."""
    idiomas = idiomas_pedidos()
    if not idiomas:
        return []

    ocupados = set(ALIAS) | {
        nombre for traducciones in ALIAS.values() for nombre, _ in traducciones.values()
    } - {
        nombre
        for traducciones in ALIAS.values()
        for idioma, (nombre, _) in traducciones.items()
        if idioma in idiomas
    }

    registrados = []
    for canonico, traducciones in ALIAS.items():
        funcion = globals()[canonico]
        for idioma in idiomas:
            nombre, descripcion = traducciones[idioma]
            if nombre in ocupados:      # colisión con un nombre ya expuesto
                continue
            mcp.tool(name=nombre, description=descripcion)(funcion)
            ocupados.add(nombre)
            registrados.append(nombre)
    return registrados


ALIAS_REGISTRADOS = registrar_alias()


# ─── Arranque ────────────────────────────────────────────────────────────────

def verificar_configuracion():
    """Falla temprano si la configuración no tiene sentido, antes de abrir sockets."""
    if not Path(DIRECTORIO_ESCENAS).expanduser().is_dir():
        sys.exit(f"COPPELIA_DIRECTORIO_ESCENAS no es un directorio: {DIRECTORIO_ESCENAS}")
    if not 1 <= COPPELIA_PUERTO <= 65535:
        sys.exit(f"COPPELIA_PUERTO fuera de rango: {COPPELIA_PUERTO}")


def main():
    """Punto de entrada del ejecutable `coppeliasim-mcp`."""
    verificar_configuracion()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
