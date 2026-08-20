"""
Prueba de humo del paquete instalado: comprueba que habla MCP de verdad.

No necesita CoppeliaSim. Verifica tres cosas, y las tres han fallado alguna vez:

  1. El ejecutable arranca y completa el handshake MCP.
  2. Expone las 23 tools esperadas (un entry point roto o un import perdido se
     manifiesta aquí, no en el `pip install`, que pasaría igual).
  3. Con el simulador ausente, una llamada RESPONDE con un error accionable en
     vez de colgarse. El cliente ZMQ espera diez minutos por defecto, así que
     sin el tope del lado del cliente esto se queda bloqueado.

Uso:
    python scripts/prueba_humo.py [ruta-al-ejecutable]
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

TOOLS_ESPERADAS = 23
TIMEOUT_PRUEBA = 3.0          # segundos que el servidor debe esperar, como máximo
MARGEN = 4.0                  # cuánto de más toleramos antes de llamarlo cuelgue
PUERTO_CERRADO = "59999"      # nadie escucha aquí


class ClienteMCP:
    """Cliente MCP mínimo por stdio, lo justo para una prueba de humo."""

    def __init__(self, ejecutable, entorno):
        self.proceso = subprocess.Popen(
            [ejecutable], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, env=entorno,
        )
        self.respuestas = queue.Queue()
        threading.Thread(target=self._leer, daemon=True).start()

    def _leer(self):
        for linea in self.proceso.stdout:
            linea = linea.strip()
            if linea:
                try:
                    self.respuestas.put(json.loads(linea))
                except json.JSONDecodeError:
                    pass

    def enviar(self, mensaje):
        self.proceso.stdin.write(json.dumps(mensaje) + "\n")
        self.proceso.stdin.flush()

    def pedir(self, id_peticion, metodo, params=None, espera=30):
        self.enviar({"jsonrpc": "2.0", "id": id_peticion, "method": metodo,
                     "params": params or {}})
        limite = time.monotonic() + espera
        while time.monotonic() < limite:
            try:
                mensaje = self.respuestas.get(timeout=limite - time.monotonic())
            except queue.Empty:
                break
            if mensaje.get("id") == id_peticion:
                return mensaje
        raise TimeoutError(f"sin respuesta a {metodo} en {espera:g} s")

    def cerrar(self):
        self.proceso.stdin.close()
        try:
            self.proceso.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proceso.kill()


def main():
    ejecutable = sys.argv[1] if len(sys.argv) > 1 else shutil.which("coppeliasim-mcp")
    if not ejecutable:
        sys.exit("No encuentro el ejecutable 'coppeliasim-mcp' en el PATH.")
    print(f"probando {ejecutable}")

    entorno = dict(os.environ)
    entorno["COPPELIA_PUERTO"] = PUERTO_CERRADO
    entorno["COPPELIA_TIMEOUT"] = str(TIMEOUT_PRUEBA)
    cliente = ClienteMCP(ejecutable, entorno)
    fallos = []

    try:
        respuesta = cliente.pedir(1, "initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "prueba-humo", "version": "1"},
        })
        servidor = respuesta["result"]["serverInfo"]["name"]
        print(f"  ok    handshake MCP -> {servidor}")
        cliente.enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})

        tools = [t["name"] for t in cliente.pedir(2, "tools/list")["result"]["tools"]]
        if len(tools) == TOOLS_ESPERADAS:
            print(f"  ok    {len(tools)} tools expuestas")
        else:
            fallos.append(f"se esperaban {TOOLS_ESPERADAS} tools, hay {len(tools)}")

        inicio = time.monotonic()
        respuesta = cliente.pedir(3, "tools/call",
                                  {"name": "estado_simulacion", "arguments": {}},
                                  espera=TIMEOUT_PRUEBA + MARGEN + 10)
        tardo = time.monotonic() - inicio
        texto = respuesta["result"]["content"][0]["text"]
        if tardo > TIMEOUT_PRUEBA + MARGEN:
            fallos.append(f"la llamada sin simulador tardó {tardo:.1f} s: parece un cuelgue")
        elif "no respondió" not in texto:
            fallos.append(f"error poco claro sin simulador: {texto[:80]}")
        else:
            print(f"  ok    sin simulador responde en {tardo:.1f} s con un error accionable")

        if len(cliente.pedir(4, "tools/list")["result"]["tools"]) != TOOLS_ESPERADAS:
            fallos.append("el servidor no sobrevivió al fallo de conexión")
        else:
            print("  ok    el servidor sigue en pie tras el fallo")
    except TimeoutError as error:
        fallos.append(str(error))
    finally:
        cliente.cerrar()

    if fallos:
        print("\nFALLOS:")
        for fallo in fallos:
            print(f"  - {fallo}")
        sys.exit(1)
    print("\nprueba de humo superada")


if __name__ == "__main__":
    main()
