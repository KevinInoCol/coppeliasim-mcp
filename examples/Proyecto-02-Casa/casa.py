"""
Construye en CoppeliaSim una casa de una planta, sin techo, para robots móviles.

Sin techo a propósito: la vista cenital de CoppeliaSim entra directa a las
habitaciones, se ve al robot en todo momento y no hace falta cortar paredes ni
jugar con la transparencia. Lo que sí hay es planta cerrada con tabiques y
puertas, que es lo que le da sentido a un robot que navega.

Planta (7.2 x 5.6 m interiores, vista cenital, +x este / +y norte):

    +-----------+------------+---------+
    | Dormitor1 | Dormitor2  |  Bano   |   y = +2.8
    +--- o -----+---- o -----+--- o ---+   y = +0.6
    ]        Pasillo                   |   y =  0.0  ] = entrada
    +------ o -----------+---- o ------+   y = -0.6
    |       Sala         |   Cocina    |
    +--------------------+-------------+   y = -2.8
   x=-3.6                              x=+3.6

Decisiones que condicionan al robot que vendrá después:

  - Los vanos de puerta miden 0.90 m y el pasillo 1.20 m de ancho. El carrito
    de `carrito_diferencial.py` mide 0.40 x 0.25 m y gira sobre el eje de las
    ruedas motrices barriendo un radio de 0.32 m: con 0.90 m de vano le sobran
    29 cm por lado para cruzar recto, y en el pasillo puede darse la vuelta.
    El script comprueba esta holgura al final, no la da por supuesta.
  - Las paredes son estáticas, respondables y detectables: un sensor de
    proximidad las ve y el robot no las atraviesa.
  - Los suelos de color de cada habitación son puramente visuales: ni
    respondables ni detectables ni colisionables. Así el robot rueda sobre el
    terreno y no tropieza con el escalón de 1 cm en cada vano.
  - Se sustituye el /Floor por defecto (5 x 5 m) por un terreno de 10 x 10 m,
    porque la casa no cabe en el suelo original.

Uso:
    python Proyecto-02-Casa/casa.py              # construye, verifica y guarda
    python Proyecto-02-Casa/casa.py --foto       # además saca la planta a PNG
    python Proyecto-02-Casa/casa.py --sin-guardar
"""

import math
import os
import struct
import sys
import time
import zlib
from collections import deque

from coppeliasim_zmqremoteapi_client import RemoteAPIClient
from dotenv import find_dotenv, load_dotenv

RUTA_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(find_dotenv())    # opcional: sin .env valen los valores por defecto

COPPELIA_HOST = os.getenv("COPPELIA_HOST", "127.0.0.1")
COPPELIA_PUERTO = int(os.getenv("COPPELIA_PUERTO", "23000"))

RUTA_ESCENA = os.path.join(RUTA_PROYECTO, "Proyecto-02-Casa", "Escena_Casa.ttt")
RUTA_FOTO = os.path.join(RUTA_PROYECTO, "Proyecto-02-Casa", "planta.png")

TERRENO_LADO = 10.0
TERRENO_ESPESOR = 0.2               # su cara superior queda en z = 0

MURO_GROSOR = 0.12
MURO_ALTURA = 0.70                  # a la altura de un sensor de un robot pequeño
PUERTA_ANCHO = 0.90
ENTRADA_ANCHO = 1.00
TRAMO_MINIMO = 0.01                 # tramos más cortos que esto no se crean

# Ejes de las paredes maestras. Todo lo demás se deriva de aquí.
X_OESTE, X_ESTE = -3.6, 3.6
Y_SUR, Y_NORTE = -2.8, 2.8
PASILLO_SUR, PASILLO_NORTE = -0.6, 0.6
TABIQUE_DORM, TABIQUE_BANO = -1.2, 1.4      # divisiones de la franja norte
TABIQUE_COCINA = 0.6                        # división de la franja sur

VUELO = MURO_GROSOR / 2             # los muros norte y sur se alargan medio
                                    # grosor por cada punta para tapar la
                                    # esquina; si no, queda una muesca abierta

# (alias, eje del muro, coordenada del eje perpendicular, inicio, fin, puertas)
# eje "x": el muro corre a lo largo de x, a la altura y = coordenada.
# Cada puerta es (centro, ancho) medido sobre el eje por el que corre el muro.
MUROS_EXTERIORES = [
    ("MuroNorte", "x", Y_NORTE, X_OESTE - VUELO, X_ESTE + VUELO, []),
    ("MuroSur", "x", Y_SUR, X_OESTE - VUELO, X_ESTE + VUELO, []),
    ("MuroEste", "y", X_ESTE, Y_SUR, Y_NORTE, []),
    ("MuroOeste", "y", X_OESTE, Y_SUR, Y_NORTE, [(0.0, ENTRADA_ANCHO)]),
]

MUROS_INTERIORES = [
    ("TabiqueNorte", "x", PASILLO_NORTE, X_OESTE, X_ESTE,
     [(-2.4, PUERTA_ANCHO), (0.1, PUERTA_ANCHO), (2.5, PUERTA_ANCHO)]),
    ("TabiqueSur", "x", PASILLO_SUR, X_OESTE, X_ESTE,
     [(-1.5, PUERTA_ANCHO), (2.0, PUERTA_ANCHO)]),
    ("TabiqueDormitorios", "y", TABIQUE_DORM, PASILLO_NORTE, Y_NORTE, []),
    ("TabiqueBano", "y", TABIQUE_BANO, PASILLO_NORTE, Y_NORTE, []),
    ("TabiqueCocina", "y", TABIQUE_COCINA, Y_SUR, PASILLO_SUR,
     [(-1.8, PUERTA_ANCHO)]),
]

# (alias, inicial para el plano ASCII, rectángulo x0 x1 y0 y1, color)
HABITACIONES = [
    ("Sala", "S", (X_OESTE, TABIQUE_COCINA, Y_SUR, PASILLO_SUR), [0.78, 0.60, 0.42]),
    ("Cocina", "C", (TABIQUE_COCINA, X_ESTE, Y_SUR, PASILLO_SUR), [0.86, 0.86, 0.88]),
    ("Pasillo", "P", (X_OESTE, X_ESTE, PASILLO_SUR, PASILLO_NORTE), [0.70, 0.70, 0.68]),
    ("Dormitorio1", "1", (X_OESTE, TABIQUE_DORM, PASILLO_NORTE, Y_NORTE), [0.60, 0.70, 0.86]),
    ("Dormitorio2", "2", (TABIQUE_DORM, TABIQUE_BANO, PASILLO_NORTE, Y_NORTE), [0.70, 0.82, 0.62]),
    ("Bano", "B", (TABIQUE_BANO, X_ESTE, PASILLO_NORTE, Y_NORTE), [0.58, 0.80, 0.86]),
]

SUELO_ESPESOR = 0.01

COLOR_TERRENO = [0.42, 0.50, 0.38]
COLOR_EXTERIOR = [0.86, 0.82, 0.74]
COLOR_INTERIOR = [0.74, 0.77, 0.80]

# Con qué robot se comprueba que la planta es transitable. Radio de holgura,
# no medio ancho: incluye el margen que hace falta para no ir rozando.
ROBOT_RADIO = 0.25
CELDA = 0.05                        # resolución del mapa de ocupación

CAMARA_POS = [0.0, -9.5, 8.5]

FOTO_RESOLUCION = 1024
FOTO_ALTURA = 12.0                  # el sensor ortográfico va encima de todo
FOTO_ANCHO = 9.0                    # metros que abarca el encuadre


def conectar():
    return RemoteAPIClient(host=COPPELIA_HOST, port=COPPELIA_PUERTO).require("sim")


def limpiar(sim):
    """Borra la casa de una corrida anterior y el suelo por defecto."""
    borrados = []
    for ruta in ("/Casa", "/Floor", "/CamaraPlano"):
        try:
            raiz = sim.getObject(ruta)
        except Exception:
            continue
        arbol = set(sim.getObjectsInTree(raiz, sim.handle_all, 0)) | {raiz}
        borrados.append(f"{ruta} ({len(arbol)} objetos)")
        sim.removeObjects(list(arbol))
    return borrados


def estatico(sim, handle, color, detectable=True):
    """Deja una forma como parte fija del decorado: sin masa, pero sólida."""
    sim.setBoolProperty(handle, "dynamic", False)
    sim.setBoolProperty(handle, "respondable", detectable)
    propiedades = sim.objectspecialproperty_renderable
    if detectable:
        propiedades |= (sim.objectspecialproperty_detectable_all
                        | sim.objectspecialproperty_collidable
                        | sim.objectspecialproperty_measurable)
    sim.setObjectSpecialProperty(handle, propiedades)
    sim.setShapeColor(handle, None, sim.colorcomponent_ambient_diffuse, color)


def crear_caja(sim, alias, padre, tamano, centro, color, detectable=True):
    caja = sim.createPrimitiveShape(sim.primitiveshape_cuboid, tamano, 0)
    sim.setObjectAlias(caja, alias)
    sim.setObjectPosition(caja, centro, sim.handle_world)
    sim.setObjectParent(caja, padre, True)
    estatico(sim, caja, color, detectable)
    return caja


def crear_terreno(sim, padre):
    return crear_caja(
        sim, "Terreno", padre,
        [TERRENO_LADO, TERRENO_LADO, TERRENO_ESPESOR],
        [0.0, 0.0, -TERRENO_ESPESOR / 2],
        COLOR_TERRENO,
    )


def tramos_de_muro(inicio, fin, puertas):
    """Trocea un muro en los pedazos macizos que quedan entre sus vanos."""
    tramos = []
    cursor = inicio
    for centro, ancho in sorted(puertas):
        arranque, remate = centro - ancho / 2, centro + ancho / 2
        if arranque - cursor > TRAMO_MINIMO:
            tramos.append((cursor, arranque))
        cursor = max(cursor, remate)
    if fin - cursor > TRAMO_MINIMO:
        tramos.append((cursor, fin))
    return tramos


def rectangulo_de_tramo(eje, coordenada, desde, hasta):
    """Huella en planta (x0, x1, y0, y1) de un tramo de muro."""
    if eje == "x":
        return (desde, hasta, coordenada - MURO_GROSOR / 2, coordenada + MURO_GROSOR / 2)
    return (coordenada - MURO_GROSOR / 2, coordenada + MURO_GROSOR / 2, desde, hasta)


def crear_muros(sim, padre, definiciones, color):
    """Levanta una tanda de muros y devuelve sus huellas en planta."""
    huellas = []
    for alias, eje, coordenada, inicio, fin, puertas in definiciones:
        tramos = tramos_de_muro(inicio, fin, puertas)
        for indice, (desde, hasta) in enumerate(tramos, start=1):
            x0, x1, y0, y1 = rectangulo_de_tramo(eje, coordenada, desde, hasta)
            nombre = alias if len(tramos) == 1 else f"{alias}_{indice}"
            crear_caja(
                sim, nombre, padre,
                [x1 - x0, y1 - y0, MURO_ALTURA],
                [(x0 + x1) / 2, (y0 + y1) / 2, MURO_ALTURA / 2],
                color,
            )
            huellas.append((x0, x1, y0, y1))
    return huellas


def crear_suelos(sim, padre):
    """
    Una losa de color por habitación, solo para verlas desde arriba.

    Van retranqueadas medio grosor de muro para no meterse dentro de la pared,
    y son puro adorno: el robot rueda sobre el terreno, no sobre ellas.
    """
    losas = []
    for alias, _inicial, (x0, x1, y0, y1), color in HABITACIONES:
        margen = MURO_GROSOR / 2
        losas.append(crear_caja(
            sim, f"Suelo{alias}", padre,
            [x1 - x0 - 2 * margen, y1 - y0 - 2 * margen, SUELO_ESPESOR],
            [(x0 + x1) / 2, (y0 + y1) / 2, SUELO_ESPESOR / 2],
            color, detectable=False,
        ))
    return losas


def normalizar(vector):
    modulo = math.sqrt(sum(c * c for c in vector))
    return [c / modulo for c in vector]


def producto_cruz(a, b):
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def matriz_mirando(desde, hacia):
    """
    Matriz de pose para que un ojo puesto en `desde` enfoque `hacia`.

    Las cámaras y los sensores de visión de CoppeliaSim miran por su +Z, con
    +Y como vertical de la imagen. Es justo al revés que en OpenGL, y usar el
    -Z por costumbre deja la vista enfocando el cielo detrás de la escena: se
    ve el degradado del fondo y ni rastro de los objetos. Se arma la matriz a
    mano en vez de buscar los ángulos de Euler, que aquí no son evidentes.
    """
    frente = normalizar([h - d for h, d in zip(hacia, desde)])
    vertical_mundo = [0.0, 0.0, 1.0]
    proyeccion = sum(v * f for v, f in zip(vertical_mundo, frente))
    arriba = normalizar([v - proyeccion * f for v, f in zip(vertical_mundo, frente)])
    derecha = producto_cruz(arriba, frente)
    return [derecha[0], arriba[0], frente[0], desde[0],
            derecha[1], arriba[1], frente[1], desde[1],
            derecha[2], arriba[2], frente[2], desde[2]]


def colocar_camara(sim):
    """Deja la vista de la GUI mirando la casa desde el sur y desde arriba."""
    try:
        camara = sim.getObject("/DefaultCamera")
    except Exception:
        return False
    sim.setObjectMatrix(camara, matriz_mirando(CAMARA_POS, [0.0, 0.0, 0.0]),
                        sim.handle_world)
    return True


def construir(sim):
    borrados = limpiar(sim)
    print(f"0. Escena limpiada: {', '.join(borrados) or 'no había nada que borrar'}")

    casa = sim.createDummy(0.02)
    sim.setObjectAlias(casa, "Casa")
    sim.setObjectPosition(casa, [0.0, 0.0, 0.0], sim.handle_world)

    for alias in ("Muros", "Suelos"):
        grupo = sim.createDummy(0.01)
        sim.setObjectAlias(grupo, alias)
        sim.setObjectParent(grupo, casa, True)

    muros = sim.getObject("/Casa/Muros")
    suelos = sim.getObject("/Casa/Suelos")

    crear_terreno(sim, casa)
    print(f"1. Terreno de {TERRENO_LADO} x {TERRENO_LADO} m, cara superior en z = 0")

    huellas = crear_muros(sim, muros, MUROS_EXTERIORES, COLOR_EXTERIOR)
    exteriores = len(huellas)
    huellas += crear_muros(sim, muros, MUROS_INTERIORES, COLOR_INTERIOR)
    print(f"2. Muros: {exteriores} tramos de fachada y {len(huellas) - exteriores} "
          f"de tabique, {MURO_GROSOR * 100:.0f} cm de grosor y {MURO_ALTURA} m de alto")

    losas = crear_suelos(sim, suelos)
    print(f"3. {len(losas)} habitaciones con suelo de color (solo visual)")

    if colocar_camara(sim):
        print(f"4. Cámara principal en {CAMARA_POS}, enfocando la casa")

    return {"casa": casa, "huellas": huellas}


def dentro(rectangulo, x, y, margen=0.0):
    x0, x1, y0, y1 = rectangulo
    return x0 - margen <= x <= x1 + margen and y0 - margen <= y <= y1 + margen


def rasterizar(huellas, margen=0.0):
    """
    Mapa de ocupación de la planta. Con margen > 0 los muros se engordan, que
    es la forma barata de preguntar si cabe un robot de ese radio.

    Devuelve (rejilla, columnas, filas): rejilla[fila][columna] es True si esa
    celda está ocupada. La fila 0 es la del norte, para que al imprimirla salga
    con la misma orientación que la vista cenital.
    """
    x_ini, x_fin = X_OESTE - MURO_GROSOR, X_ESTE + MURO_GROSOR
    y_ini, y_fin = Y_SUR - MURO_GROSOR, Y_NORTE + MURO_GROSOR
    columnas = int(round((x_fin - x_ini) / CELDA))
    filas = int(round((y_fin - y_ini) / CELDA))

    rejilla = []
    for fila in range(filas):
        y = y_fin - (fila + 0.5) * CELDA
        linea = []
        for columna in range(columnas):
            x = x_ini + (columna + 0.5) * CELDA
            linea.append(any(dentro(h, x, y, margen) for h in huellas))
        rejilla.append(linea)
    return rejilla, (x_ini, y_fin)


def habitacion_en(x, y):
    for alias, inicial, rectangulo, _color in HABITACIONES:
        if dentro(rectangulo, x, y):
            return alias, inicial
    return None, " "


def imprimir_plano(rejilla, origen):
    """Vuelca la planta rasterizada como dibujo ASCII, para verla sin la GUI."""
    x_ini, y_fin = origen
    paso = max(1, int(round(0.10 / CELDA)))     # una celda de 10 cm por carácter
    print("\n--- planta rasterizada (# muro, letra = habitación) ---")
    for fila in range(0, len(rejilla), paso):
        y = y_fin - (fila + 0.5) * CELDA
        linea = []
        for columna in range(0, len(rejilla[fila]), paso):
            x = x_ini + (columna + 0.5) * CELDA
            linea.append("#" if rejilla[fila][columna] else habitacion_en(x, y)[1])
        print("   " + "".join(linea))
    letras = ", ".join(f"{inicial}={alias}" for alias, inicial, _r, _c in HABITACIONES)
    print(f"   leyenda: {letras}")


def alcanzables(rejilla, origen, partida):
    """Inunda la planta desde un punto y devuelve el conjunto de celdas libres."""
    x_ini, y_fin = origen
    filas, columnas = len(rejilla), len(rejilla[0])
    columna = int((partida[0] - x_ini) / CELDA)
    fila = int((y_fin - partida[1]) / CELDA)
    if rejilla[fila][columna]:
        return set()

    vistas = {(fila, columna)}
    cola = deque(vistas)
    while cola:
        f, c = cola.popleft()
        for df, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            vecino = (f + df, c + dc)
            if not (0 <= vecino[0] < filas and 0 <= vecino[1] < columnas):
                continue
            if vecino in vistas or rejilla[vecino[0]][vecino[1]]:
                continue
            vistas.add(vecino)
            cola.append(vecino)
    return vistas


def verificar(huellas):
    """
    Comprueba con números lo que se le va a pedir a la casa: que las
    habitaciones tengan el tamaño previsto y que un robot de ROBOT_RADIO pueda
    llegar a todas desde la entrada sin rozar.
    """
    rejilla, origen = rasterizar(huellas)
    imprimir_plano(rejilla, origen)

    print("\n--- habitaciones ---")
    total = 0.0
    for alias, _inicial, (x0, x1, y0, y1), _color in HABITACIONES:
        ancho, fondo = x1 - x0 - MURO_GROSOR, y1 - y0 - MURO_GROSOR
        total += ancho * fondo
        print(f"   {alias:<12} {ancho:4.2f} x {fondo:4.2f} m = {ancho * fondo:5.2f} m2")
    print(f"   {'TOTAL':<12} {total:20.2f} m2 útiles")

    print(f"\n--- transitabilidad para un robot de radio {ROBOT_RADIO} m ---")
    holgura = PUERTA_ANCHO - 2 * ROBOT_RADIO
    print(f"   vano de {PUERTA_ANCHO} m -> {holgura:.2f} m de holgura al cruzarlo "
          f"({'pasa' if holgura > 0 else 'NO PASA'})")
    ancho_pasillo = PASILLO_NORTE - PASILLO_SUR - MURO_GROSOR
    print(f"   pasillo de {ancho_pasillo:.2f} m -> "
          f"{'cabe girando' if ancho_pasillo > 2 * ROBOT_RADIO else 'DEMASIADO ESTRECHO'}")

    inflada, origen = rasterizar(huellas, margen=ROBOT_RADIO)
    libres = alcanzables(inflada, origen, (0.0, 0.0))
    x_ini, y_fin = origen
    visitadas = {habitacion_en(x_ini + (c + 0.5) * CELDA, y_fin - (f + 0.5) * CELDA)[0]
                 for f, c in libres}
    for alias, _inicial, _rectangulo, _color in HABITACIONES:
        estado = "alcanzable" if alias in visitadas else "AISLADA"
        print(f"   {alias:<12} {estado}")

    fuera = any(x_ini + (c + 0.5) * CELDA < X_OESTE for _f, c in libres)
    print(f"   la entrada oeste deja salir al exterior: {'sí' if fuera else 'no'}")
    return all(alias in visitadas for alias, _i, _r, _c in HABITACIONES)


def escribir_png(ruta, pixeles, ancho, alto):
    """
    Guarda RGB crudo como PNG sin depender de Pillow, que no está instalado.

    El sensor entrega la imagen de abajo arriba y mirando hacia -Z, así que el
    resultado sale girado 180°: hay que invertir filas y columnas para que el
    plano quede con el norte arriba y el este a la derecha.
    """
    filas = []
    for f in range(alto):
        fila = pixeles[f * ancho * 3:(f + 1) * ancho * 3]
        volteada = b"".join(fila[p * 3:(p + 1) * 3] for p in range(ancho - 1, -1, -1))
        filas.append(b"\x00" + volteada)
    cuerpo = zlib.compress(b"".join(filas), 9)

    def trozo(tipo, datos):
        return (struct.pack(">I", len(datos)) + tipo + datos
                + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF))

    with open(ruta, "wb") as png:
        png.write(b"\x89PNG\r\n\x1a\n")
        png.write(trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)))
        png.write(trozo(b"IDAT", cuerpo))
        png.write(trozo(b"IEND", b""))


def esperar_parada(sim, limite=10.0):
    """Espera a que la simulación pare de verdad, sin quedarse colgado si no."""
    plazo = time.time() + limite
    while sim.getSimulationState() != sim.simulation_stopped and time.time() < plazo:
        time.sleep(0.05)
    return sim.getSimulationState() == sim.simulation_stopped


def fotografiar(sim, ruta):
    """
    Saca un plano cenital con un sensor de visión ortográfico de usar y tirar.

    Es la única forma de ver el resultado sin la GUI delante, y de paso deja
    una imagen del proyecto. El sensor se borra al terminar para no ensuciar la
    escena que se va a guardar.
    """
    try:
        sim.removeObjects([sim.getObject("/CamaraPlano")])
    except Exception:
        pass

    # options=1: manejo explícito y proyección ortográfica (sin el bit de
    # perspectiva). En float_params el tercer valor es, en ortográfica, el
    # ancho en metros del encuadre, no el ángulo de visión.
    camara = sim.createVisionSensor(
        1,
        [FOTO_RESOLUCION, FOTO_RESOLUCION, 0, 0],
        [0.05, FOTO_ALTURA * 2, FOTO_ANCHO, 0.05, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    sim.setObjectAlias(camara, "CamaraPlano")
    sim.setObjectPosition(camara, [0.0, 0.0, FOTO_ALTURA], sim.handle_world)
    # El sensor mira por su +Z; 180° sobre X lo dejan mirando al suelo.
    sim.setObjectOrientation(camara, [math.pi, 0.0, 0.0], sim.handle_world)
    # (aquí sí valen los Euler: mirar recto hacia abajo es un giro simple)

    sim.startSimulation()
    time.sleep(0.5)                 # un respiro para que renderice el primer cuadro
    sim.handleVisionSensor(camara)
    imagen, (ancho, alto) = sim.getVisionSensorImg(camara)
    sim.stopSimulation()
    esperar_parada(sim)
    sim.removeObjects([camara])

    escribir_png(ruta, imagen, ancho, alto)
    return ancho, alto


def main():
    sim = conectar()
    casa = construir(sim)
    completa = verificar(casa["huellas"])

    if "--foto" in sys.argv:
        ancho, alto = fotografiar(sim, RUTA_FOTO)
        print(f"\nPlano cenital de {ancho}x{alto} px en {RUTA_FOTO}")

    if "--sin-guardar" not in sys.argv:
        sim.saveScene(RUTA_ESCENA)
        print(f"\nEscena guardada en {RUTA_ESCENA}")

    print("\nVeredicto:", "casa lista para meter un robot" if completa
          else "hay habitaciones sin acceso, revisar los vanos")


if __name__ == "__main__":
    main()
