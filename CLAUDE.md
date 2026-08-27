# coppeliasim-mcp

MCP server that drives a running CoppeliaSim 4.10 over the ZMQ remote API.
Single source file: `src/coppeliasim_mcp/server.py`.

If you are *using* this server rather than developing it, you do not need this
file: the server sends its own usage guidance to the client at handshake (the
`INSTRUCCIONES` constant), and the user-facing detail is in `README.md`.

## Development loop

The server is meant to be installed editable, so edits are live with no publish
step in between:

```bash
pip install -e .
```

Point your MCP client at the `coppeliasim-mcp` executable that this puts in the
environment's `bin/`. Restart the client (or `/reload-plugins`) to pick up a
change; nothing else is needed.

Check your work without CoppeliaSim running:

```bash
python scripts/prueba_humo.py "$(which coppeliasim-mcp)"
```

That covers the MCP handshake, the expected tool count, and the one failure
mode that keeps coming back: a call with no simulator present must *answer*
with an actionable error instead of hanging. `TOOLS_ESPERADAS` in that script
is a hard count — adding a tool means updating it, which is deliberate.

## Releasing

Publishing is irreversible. A PyPI version can never be overwritten or reused.

```bash
# 1. bump `version` in pyproject.toml   <- the step people forget
# 2. commit and push
git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z
```

The tag is what publishes; a plain push never does. CI refuses to publish when
the tag and `pyproject.toml` disagree, and it re-runs the smoke test against
the built wheel on Python 3.10 and 3.13 before uploading. Authentication is
Trusted Publishing over OIDC, so there is no token in the repository secrets.

Semver as applied here: new tools bump the minor, fixes bump the patch.

## Invariants — do not break these

- **No arbitrary Lua execution, ever.** This is the reason this server exists
  rather than one of the others. CoppeliaSim's Lua reaches `os` and `io`, so a
  Lua tool turns text inside any third-party `.ttt` into command execution on
  the user's machine. Requests to "just add an `eval` tool" are the threat, not
  a shortcut.
- **Paths stay confined.** `cargar_escena` and `guardar_escena` resolve the path
  before comparing it against `DIRECTORIO_ESCENAS`, so `../../` and symlinks
  cannot escape. `cargar_modelo` is limited to the local CoppeliaSim library
  because a `.ttm` can carry Lua child scripts that run on Play.
- **`COPPELIA_MODO_LECTURA=1` must disable every mutating tool.** A new
  write tool has to honour it.
- **One reused ZMQ connection**, not a socket per call.
- **`pyproject.toml` is the version's source of truth.** `__version__` and the
  MCP handshake both read it from package metadata, so never hardcode it there.
  The one unavoidable duplicate is `.claude-plugin/plugin.json`, which cannot
  read Python metadata; CI fails the release if the two disagree, because a
  stale `plugin.json` silently stops users from receiving the new version.

## Skills and the plugin

The repository is also a Claude Code plugin: `.claude-plugin/plugin.json` plus
`.claude-plugin/marketplace.json` at the root, `skills/` beside them, and a
`.mcp.json` that points at `uvx coppeliasim-mcp` so installing the plugin brings
the server from PyPI rather than from this checkout.

`skills/` holds three topics, each written three times — Spanish, English and
Portuguese, mirroring `COPPELIA_IDIOMAS`:

| Topic | es | en | pt |
|---|---|---|---|
| Project layout | `estructura-de-proyecto` | `project-structure` | `estrutura-de-projeto` |
| Scenes | `construir-escena` | `build-a-scene` | `construir-cena` |
| Robot and sensors | `robot-diferencial-y-sensores` | `differential-robot-and-sensors` | `robo-diferencial-e-sensores` |

Only the `description` of each skill is always in context (~830 tokens for all
nine); the bodies load on demand. A skill's `name` must match its folder.

**Editing one language means editing all three.** They are translations of the
same procedure, not independent documents, and nothing enforces it — the cost of
the trilingual choice lands here. Test with
`claude --plugin-dir .` and validate with `claude plugin validate . --strict`.

The content is distilled from real working projects, not written from theory.
Every measurement quoted in a skill (87% of straight-line distance, 49 simulated
seconds in 2 of wall clock, the floor entering a 10-degree cone at 57 cm) came
from a robot that runs. Do not add a claim you have not measured.

## Facts, and where they were checked

Every `sim.*` call was verified against
`Contents/Resources/manual/index/sim.json` of a real CoppeliaSim 4.10.0 rev0
install. When adding a tool, check the same file rather than trusting a
plausible-looking API name — several do not exist, and several take different
arguments than you would guess.

The API behaviours that cost real debugging time are written up under "Notes
that save debugging time" in `README.md`, with the measurements that produced
them. Two that bite hardest: Bullet 2.7 obeys `bullet.frictionOld`, not
`bullet.friction`; and a joint stays deaf to speed orders until `dynCtrlMode`
is set, which is a property rather than an argument of the creation call.

## Examples

`examples/` holds two complete projects — `Proyecto-01-Carrito-Diferencial/` and
`Proyecto-02-Casa/` — that were built against a real simulator. They are the
source of every measurement quoted in the README and in the skills, so treat
them as evidence rather than decoration: changing a number in the docs means
re-running the script that produced it.

They are plain Python against `coppeliasim_zmqremoteapi_client`, never tool
calls, which is the same point the server's `INSTRUCCIONES` makes to the model.

`examples/` does not ship in the wheel (`packages = ["src/coppeliasim_mcp"]`),
so the scene `.ttt` files cost repository size but nothing to PyPI users. They
are regenerable output of the scripts — avoid re-committing them for cosmetic
scene edits, since git stores binaries whole and every save adds a full copy to
the history.

Each script finds its `.env` with `find_dotenv()`, searching upward, and falls
back to working defaults when there is none — so a fresh clone runs with no
configuration.

## Tool names

Spanish by default. `COPPELIA_IDIOMAS` registers English and Portuguese aliases
for the same functions. Each extra language re-registers all 31 tools and adds
roughly 4,000 tokens to the catalog sent on every request, so the default stays
Spanish-only. The server's `INSTRUCCIONES` costs ~440 tokens on top of that;
keep it as judgment the model cannot infer from tool names, not as a manual.
