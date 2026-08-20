# coppeliasim-mcp

An MCP server that lets Claude Code (or any MCP client) drive a running
[CoppeliaSim](https://www.coppeliarobotics.com/) 4.10 simulation: build scenes,
move objects, create joints and proximity sensors, run the simulation and read
sensors back.

**It deliberately does not expose arbitrary Lua execution.** That is the main
difference from other CoppeliaSim MCP servers. See [Security](#security).

Tool names are Spanish by default, with optional English and Portuguese
aliases — see [Tool name languages](#tool-name-languages).

> **Not affiliated with, endorsed by, or maintained by Coppelia Robotics AG.**
> CoppeliaSim is a trademark of Coppelia Robotics AG. This is an independent
> third-party integration; for the simulator itself, go to
> [coppeliarobotics.com](https://www.coppeliarobotics.com/).

---

## Requirements

- CoppeliaSim 4.10 running, with the **ZMQ remote API** add-on active. It ships
  enabled by default and listens on port 23000.
- Python 3.10 or newer.

## Install

```bash
# Recommended: no clone, no virtualenv to manage
uvx coppeliasim-mcp

# Or install it
pip install coppeliasim-mcp
```

Register it with Claude Code:

```bash
claude mcp add coppelia -- uvx coppeliasim-mcp
```

Or, for any MCP client that reads a JSON config:

```json
{
  "mcpServers": {
    "coppelia": {
      "command": "uvx",
      "args": ["coppeliasim-mcp"]
    }
  }
}
```

## Configuration

All settings are optional environment variables. They can also live in a `.env`
file in the working directory — see `.env.example`.

| Variable | Default | What it does |
|---|---|---|
| `COPPELIA_HOST` | `127.0.0.1` | Host of the ZMQ remote API add-on. |
| `COPPELIA_PUERTO` | `23000` | Its port. |
| `COPPELIA_DIRECTORIO_ESCENAS` | current working directory | Only scenes under this folder can be loaded. |
| `COPPELIA_MODO_LECTURA` | `0` | Set to `1` to disable every tool that changes the scene. |
| `COPPELIA_IDIOMAS` | `es` | Tool-name aliases. `es,en,pt` or `todos` to add English and Portuguese. |
| `COPPELIA_TIMEOUT` | `10` | Seconds to wait for a reply before giving up. |

## Tools

**Simulation control** — `iniciar_simulacion`, `detener_simulacion`,
`pausar_simulacion`, `estado_simulacion`, `tiempo_simulacion`

**Scenes** — `cargar_escena`, `cerrar_escena`

**Objects** — `listar_objetos`, `obtener_posicion`, `fijar_posicion`,
`obtener_orientacion`, `fijar_orientacion`, `crear_primitiva`,
`eliminar_objeto`, `emparentar_objeto`, `fijar_detectable`

**Joints** — `obtener_posicion_junta`, `fijar_objetivo_junta`,
`fijar_velocidad_junta`, `obtener_fuerza_junta`

**Proximity sensors** — `crear_sensor_proximidad`, `leer_sensor_proximidad`,
`comprobar_sensor_proximidad`

## Tool name languages

Tools are defined in Spanish (`crear_primitiva`, `leer_sensor_proximidad`, …).
Setting `COPPELIA_IDIOMAS` registers aliases in English and Portuguese that
point at the same functions — no duplicated logic, just more names in the
catalog.

| `COPPELIA_IDIOMAS` | Tools | Catalog size | Cost per request |
|---|---|---|---|
| `es` (default) | 23 | 15.0 KB | — |
| `es,en` | 46 | 27.7 KB | ~3,300 tokens |
| `es,en,pt` / `todos` | 69 | 40.5 KB | ~6,500 tokens |

The catalog is sent to the model on **every** request, so aliases are off by
default. Worth knowing before you turn them on: the model does not need
translated names to understand you in another language. Tool names are
identifiers, not user-facing text — ask for "move the cube forward" or "mova o
cubo para frente" and it will reach for `fijar_posicion` either way. Aliases help
when you want to read the catalog at a glance, or name a tool explicitly in a
prompt.

## Examples

[`examples/carrito_diferencial.py`](examples/carrito_diferencial.py) builds a
complete differential drive robot with obstacle avoidance and measures whether it
actually works. See [examples/README.md](examples/README.md).

## Security

CoppeliaSim's Lua environment has access to `os` and `io`. A tool that runs
arbitrary Lua therefore turns any prompt injection — for example text embedded
in a third-party `.ttt` scene the model is asked to inspect — into command
execution on your machine. This server has no such tool, by design.

The rest of the surface is narrow on purpose:

- `cargar_escena` resolves the path (`Path.resolve(strict=True)`) *before*
  comparing it against `COPPELIA_DIRECTORIO_ESCENAS`, so `../..` and symlinks
  cannot escape it, and it only accepts scene extensions.
- `COPPELIA_MODO_LECTURA=1` disables every mutating tool at once.
- The scene directory defaults to the working directory, not to your home.

## Notes that save debugging time

Things about the CoppeliaSim API that are easy to get wrong, and that the tools
surface directly:

- **`leer_sensor_proximidad` does not detect.** It returns the result of the
  simulator's last sensor pass, so with the simulation stopped it always reports
  nothing. Use `comprobar_sensor_proximidad` to detect on demand.
- **An object must be marked detectable** to be seen by a proximity sensor.
  That is what `fijar_detectable` is for, and it is the usual reason a sensor
  "doesn't work".
- **A wide cone pointing horizontally sees the floor** before it sees your
  obstacle. With half-aperture *a* and the sensor at height *h*, the floor
  enters the cone at *h / tan(a)*. If that is under the sensor range, the sensor
  reports the ground.
- **Re-parenting renumbers sibling paths.** After hanging `/Cylinder[1]` off a
  chassis, `/Cylinder[3]` may become `/Cylinder[1]`. List objects again between
  successive `emparentar_objeto` calls, or resolve handles up front.
- **Parenting does not rigidly attach two dynamic shapes.** Non-static shapes
  fall unless constrained by a joint or a force sensor.

## Releasing

Publishing runs on a tag push, through
[`.github/workflows/publicar.yml`](.github/workflows/publicar.yml):

```bash
# bump version in pyproject.toml first, then
git tag v0.1.0 && git push --tags
```

The workflow refuses to publish when the tag and the version in
`pyproject.toml` disagree, installs the built wheel on Python 3.10 and 3.13, and
runs [`scripts/prueba_humo.py`](scripts/prueba_humo.py) — an MCP handshake plus a
check that a call with no simulator present *answers* instead of hanging — before
it uploads anything. A PyPI version can never be overwritten or reused, so
failing in CI is much cheaper than burning a version number.

It authenticates with PyPI through Trusted Publishing (OIDC), so there is no
token stored in the repository secrets.

## License

MIT — see [LICENSE](LICENSE).

The MIT license covers this server only. CoppeliaSim itself is licensed
separately by Coppelia Robotics AG, and this package neither includes nor
redistributes any part of it — it talks to a simulator you install and license
yourself.

---

# coppeliasim-mcp (español)

Un servidor MCP para manejar una simulación de CoppeliaSim 4.10 desde Claude
Code o cualquier cliente MCP: construir escenas, mover objetos, crear juntas y
sensores de proximidad, correr la simulación y leer los sensores.

**No expone ejecución de Lua arbitrario, a propósito.** Es la diferencia
principal con los otros MCP de CoppeliaSim que circulan. El Lua de CoppeliaSim
tiene acceso a `os` e `io`, así que una tool de ese tipo convierte cualquier
prompt injection —por ejemplo, texto dentro de una escena `.ttt` de terceros—
en ejecución de comandos sobre tu máquina.

> **Sin afiliación, respaldo ni mantenimiento por parte de Coppelia Robotics AG.**
> CoppeliaSim es una marca de Coppelia Robotics AG. Esto es una integración
> independiente de terceros; para el simulador, ve a
> [coppeliarobotics.com](https://www.coppeliarobotics.com/).

## Requisitos

- CoppeliaSim 4.10 abierto, con el add-on **ZMQ remote API** activo. Viene
  habilitado por defecto, escuchando en el puerto 23000.
- Python 3.10 o superior.

## Instalación

```bash
uvx coppeliasim-mcp                              # recomendado
pip install coppeliasim-mcp                      # o instalado
claude mcp add coppelia -- uvx coppeliasim-mcp   # registrar en Claude Code
```

## Configuración

Variables de entorno, todas opcionales. También se pueden poner en un `.env`
en el directorio de trabajo — mira `.env.example`.

| Variable | Por defecto | Para qué |
|---|---|---|
| `COPPELIA_HOST` | `127.0.0.1` | Host del add-on ZMQ remote API. |
| `COPPELIA_PUERTO` | `23000` | Su puerto. |
| `COPPELIA_DIRECTORIO_ESCENAS` | directorio de trabajo | Solo se pueden cargar escenas por debajo de esta carpeta. |
| `COPPELIA_MODO_LECTURA` | `0` | A `1` deshabilita todas las tools que modifican la escena. |
| `COPPELIA_IDIOMAS` | `es` | Alias de nombres de tools. `es,en,pt` o `todos` añade inglés y portugués. |
| `COPPELIA_TIMEOUT` | `10` | Segundos de espera antes de dar una respuesta por perdida. |

## Idiomas de los nombres de tools

Las tools se definen en español. `COPPELIA_IDIOMAS` registra alias en inglés y
portugués sobre las mismas funciones: no duplica lógica, solo añade nombres.

| `COPPELIA_IDIOMAS` | Tools | Catálogo | Coste por petición |
|---|---|---|---|
| `es` (por defecto) | 23 | 15.0 KB | — |
| `es,en` | 46 | 27.7 KB | ~3.300 tokens |
| `es,en,pt` / `todos` | 69 | 40.5 KB | ~6.500 tokens |

El catálogo viaja en **cada** petición al modelo, así que los alias vienen
apagados. Y conviene saber esto antes de encenderlos: el modelo no necesita los
nombres traducidos para entenderte en otro idioma. Los nombres de tools son
identificadores, no texto de cara al usuario — pídele "move the cube forward" o
"mova o cubo para frente" y usará `fijar_posicion` igual. Los alias sirven para
leer el catálogo de un vistazo, o para nombrar una tool explícitamente.

## Ejemplos

[`examples/carrito_diferencial.py`](examples/carrito_diferencial.py) construye un
carrito de tracción diferencial completo con evasión de obstáculos, y mide si de
verdad funciona. Mira [examples/README.md](examples/README.md).

## Cosas que ahorran horas de depuración

- **`leer_sensor_proximidad` no detecta.** Devuelve el resultado del último
  barrido del simulador, así que con la simulación detenida siempre dice que no
  hay nada. Para detectar en el momento, `comprobar_sensor_proximidad`.
- **Un objeto tiene que estar marcado como detectable** para que un sensor de
  proximidad lo vea. Para eso está `fijar_detectable`, y es la causa habitual de
  un sensor que "no funciona".
- **Un cono ancho en horizontal ve el suelo** antes que el obstáculo. Con media
  apertura *a* y el sensor a altura *h*, el suelo entra en el cono a *h / tan(a)*.
  Si eso queda por debajo del alcance, el sensor reporta el piso.
- **Emparentar renumera las rutas de los hermanos.** Al colgar `/Cylinder[1]` de
  un chasis, `/Cylinder[3]` puede pasar a ser `/Cylinder[1]`. Vuelve a listar
  los objetos entre llamadas, o resuelve los handles antes de tocar la jerarquía.
- **Emparentar no une rígidamente dos cuerpos dinámicos.** Las formas no
  estáticas se caen si no las sujeta una junta o un force sensor.

## Licencia

MIT — mira [LICENSE](LICENSE).

La licencia MIT cubre solo este servidor. CoppeliaSim se licencia por separado
con Coppelia Robotics AG, y este paquete no incluye ni redistribuye ninguna parte
de él: habla con un simulador que instalas y licencias tú.
