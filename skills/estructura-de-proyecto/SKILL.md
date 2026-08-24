---
name: estructura-de-proyecto
description: Cómo organizar un proyecto de robótica en CoppeliaSim para que sea reproducible — un script por artefacto, el orden conectar/limpiar/crear/construir/verificar, y qué va en la API de Python frente a qué va en las tools del MCP. Úsala al empezar un proyecto de CoppeliaSim, al añadir un script a uno existente, o cuando alguien pregunte por dónde empezar.
---

# Estructura de un proyecto de CoppeliaSim

Un proyecto de CoppeliaSim que se pueda entregar, repetir y corregir tiene una
forma concreta. Esta skill la describe. No es estilo: cada pieza resuelve un
problema que aparece siempre.

## Antes de escribir código: qué va dónde

**Todo lo que deba ser reproducible se escribe en Python** contra
`coppeliasim_zmqremoteapi_client`. Eso incluye construir la escena, montar el
robot y cualquier bucle de control.

**Las tools del MCP son para mirar y comprobar**, no para construir: listar
objetos, leer una posición, disparar un sensor, ver si la simulación corre. Un
bucle de control no cabe en ellas, y cuarenta paredes son cuarenta llamadas que
no dejan ningún archivo detrás.

Regla práctica: si el resultado tiene que sobrevivir a cerrar CoppeliaSim, va en
un script. Si es una pregunta ("¿dónde quedó la pared?"), va en una tool.

## Un script por artefacto

No metas la escena, el robot y el control en el mismo archivo. Se separan
porque tienen ritmos distintos: la escena se construye una vez, el robot se
retoca veinte veces, y el control se ejecuta constantemente.

    escena.py     el mundo: suelo, paredes, obstáculos
    robot.py      el robot dentro de esa escena: chasis, juntas, sensores
    control.py    lo que hace el robot: teleoperación, navegación, la tarea

Cada uno se ejecuta solo y deja la escena en un estado conocido.

## El orden de las funciones

Los scripts siguen siempre la misma secuencia. Respetarla hace que cualquiera
—incluido tú dentro de un mes— sepa dónde mirar.

```python
def conectar():
    return RemoteAPIClient(host=COPPELIA_HOST, port=COPPELIA_PUERTO).require("sim")

def limpiar(sim):
    """Borra lo que dejó la corrida anterior."""

def crear_pieza(sim, ...):
    """Una función por tipo de pieza. Devuelve el handle."""

def construir(sim):
    """Llama a las crear_* en orden y devuelve lo construido."""

def verificar(...):
    """MIDE el resultado. No supone que salió bien."""

def main():
    sim = conectar()
    cosa = construir(sim)
    ok = verificar(cosa)
    if "--sin-guardar" not in sys.argv:
        sim.saveScene(RUTA_ESCENA)
    print("\nVeredicto:", "listo" if ok else "revisar")

if __name__ == "__main__":
    main()
```

### `limpiar()` es lo que hace el script re-ejecutable

Sin ella, la segunda ejecución deja dos casas superpuestas. Borra el árbol
completo de lo que creaste, no los objetos sueltos:

```python
raiz = sim.getObject("/Casa")
arbol = set(sim.getObjectsInTree(raiz, sim.handle_all, 0)) | {raiz}
sim.removeObjects(list(arbol))
```

Envuélvelo en `try/except`: en la primera ejecución no existe nada y eso no es
un error.

Cuidado al borrar por tipo en vez de por raíz: `/DefaultLights` y
`/XYZCameraProxy` son *dummies*, y borrarlos desarma la escena por defecto.
Filtra por los tipos que tú creas (`object_shape_type`, `object_joint_type`,
`object_proximitysensor_type`, `object_forcesensor_type`) y conserva `/Floor`.

### `verificar()` es lo que separa un proyecto de un script

Es la función que más se omite y la que más vale. No preguntes si parece
correcto: **mídelo y que el script se pronuncie**.

- ¿El robot cabe por la puerta? Rasteriza las huellas y comprueba la holgura.
- ¿Se llega a todas las habitaciones? Un BFS sobre la rejilla lo responde.
- ¿El sensor detecta? Pon un obstáculo a tres distancias conocidas y mira.
- ¿El robot avanza recto? Traza la posición y compara con la teórica.

Un veredicto impreso al final convierte "creo que funciona" en un dato.

## Configuración y flags

El host y el puerto salen de un `.env` en la raíz del proyecto, con valores por
defecto que ya sirven, para que el script funcione sin configurar nada:

```python
load_dotenv(os.path.join(RUTA_PROYECTO, ".env"))
COPPELIA_HOST = os.getenv("COPPELIA_HOST", "127.0.0.1")
COPPELIA_PUERTO = int(os.getenv("COPPELIA_PUERTO", "23000"))
```

Ancla la ruta a `__file__`, nunca al directorio de trabajo, o el script solo
funcionará lanzado desde una carpeta concreta y fallará en silencio desde otra.

Flags útiles, leídos de `sys.argv` sin necesidad de `argparse`:

    --solo-construir   construye y no ejecuta las pruebas
    --sin-guardar      no sobrescribe el .ttt
    --foto             saca una imagen del resultado

## La cabecera del módulo

El docstring de arriba no describe lo obvio: **anota las decisiones y las cotas**
que condicionan todo lo demás, con sus unidades. Es donde se explica por qué el
vano mide 0.90 m y no 0.80, o por qué las ruedas llevan tanta fricción. Sin eso,
el número siguiente que alguien toque romperá algo sin saber por qué.

## Errores que se repiten

- Construir con `setObjectPosition` lo que debería mover un motor. Si el robot
  tiene juntas, se le manda velocidad; empujarlo a mano no es simular.
- Guardar la escena antes de verificar, y guardar así una escena rota.
- Poner el bucle de control en el mismo script que construye: cada retoque de
  geometría obliga a repetir la prueba entera.
- Depender del directorio de trabajo para las rutas.
