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
- **The version number lives in `pyproject.toml` and nowhere else.** Both
  `__version__` and the MCP handshake read it from package metadata. Do not add
  a third copy.

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

## Tool names

Spanish by default. `COPPELIA_IDIOMAS` registers English and Portuguese aliases
for the same functions. Each extra language re-registers all 31 tools and adds
roughly 4,000 tokens to the catalog sent on every request, so the default stays
Spanish-only. The server's `INSTRUCCIONES` costs ~440 tokens on top of that;
keep it as judgment the model cannot infer from tool names, not as a manual.
