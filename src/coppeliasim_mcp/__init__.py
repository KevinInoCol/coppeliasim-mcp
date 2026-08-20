"""Servidor MCP para controlar CoppeliaSim 4.10 desde clientes MCP."""

from importlib.metadata import PackageNotFoundError, version

try:
    # La versión la declara pyproject.toml y punto. Repetirla aquí a mano
    # garantiza que un día las dos se contradigan, y el workflow de publicación
    # solo compara la etiqueta contra pyproject.
    __version__ = version("coppeliasim-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0+dev"    # ejecutado desde el repo, sin instalar
