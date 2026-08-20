# coppeliasim-mcp

An MCP server that lets Claude Code (or any MCP client) drive a running
[CoppeliaSim](https://www.coppeliarobotics.com/) 4.10 simulation: build scenes,
move objects, create joints and proximity sensors, run the simulation and read
sensors back.

**It deliberately does not expose arbitrary Lua execution.** That is the main
difference from other CoppeliaSim MCP servers. See [Security](#security).

> Tool names and descriptions are in Spanish (`crear_primitiva`,
> `leer_sensor_proximidad`, …). The tools work the same regardless of the
> language you talk to the model in — the model maps your request to them.

---

## Requirements

- CoppeliaSim 4.10 running, with the **ZMQ remote API** add-on active. It ships
  enabled by default and listens on port 23000.
- Python 3.9 or newer.

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

## License

MIT — see [LICENSE](LICENSE).

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

## Requisitos

- CoppeliaSim 4.10 abierto, con el add-on **ZMQ remote API** activo. Viene
  habilitado por defecto, escuchando en el puerto 23000.
- Python 3.9 o superior.

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
