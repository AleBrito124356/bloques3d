"""Cliente directo para el addon BlenderMCP (socket TCP; por defecto 127.0.0.1:9876).

Es la herramienta con la que se hizo la sesion original (ver historial/). No
hace falta para el generador: ``python -m bloques3d`` usa Blender sin interfaz.

Uso:
  python _tools/bclient.py get_scene_info
  python _tools/bclient.py execute_code --code-file script.py
  python _tools/bclient.py get_viewport_screenshot --params "{\"max_size\": 900, \"filepath\": \"C:/x.png\", \"format\": \"png\"}"
  python _tools/bclient.py --host 127.0.0.1 --port 9877 get_scene_info

El destino tambien se puede fijar con BLENDER_MCP_HOST y BLENDER_MCP_PORT.
"""
import argparse
import json
import os
import socket
import sys

HOST, PORT = "127.0.0.1", 9876   # valores por defecto (se conservan por compatibilidad)


def destino(host=None, port=None, entorno=None):
    """(host, puerto) a partir de los argumentos, el entorno o los valores por defecto."""
    entorno = os.environ if entorno is None else entorno
    host = host or entorno.get("BLENDER_MCP_HOST") or HOST
    bruto = port if port is not None else entorno.get("BLENDER_MCP_PORT") or PORT
    try:
        puerto = int(bruto)
    except (TypeError, ValueError):
        raise ValueError(f"puerto no valido: {bruto!r}") from None
    if not 0 < puerto < 65536:
        raise ValueError(f"puerto fuera de rango: {puerto}")
    return host, puerto


def _respuesta_completa(buf: bytes):
    """Devuelve el JSON si ``buf`` ya es una respuesta completa, si no ``None``.

    TCP puede cortar un caracter UTF-8 de varios bytes (la 'ñ' de "Año", por
    ejemplo) entre dos ``recv``. Antes se decodificaba cada trozo y el
    ``UnicodeDecodeError`` tumbaba el cliente; ahora un corte asi solo
    significa "faltan bytes".
    """
    if not buf.rstrip().endswith(b"}"):
        return None
    try:
        return json.loads(buf.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def send_command(cmd_type: str, params: dict, timeout: float = 110.0, host=None, port=None) -> dict:
    host, port = destino(host, port)
    payload = json.dumps({"type": cmd_type, "params": params}).encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect((host, port))
        s.sendall(payload)
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            resp = _respuesta_completa(buf)
            if resp is not None:
                return resp
    raise RuntimeError("Conexion cerrada sin respuesta completa. Buffer: %r" % buf[:500])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cliente TCP para el addon BlenderMCP")
    ap.add_argument("type")
    ap.add_argument("--code-file", help="Archivo .py cuyo contenido se envia como params.code")
    ap.add_argument("--params", help="JSON con params adicionales")
    ap.add_argument("--timeout", type=float, default=110.0)
    ap.add_argument("--host", help="por defecto BLENDER_MCP_HOST o 127.0.0.1")
    ap.add_argument("--port", type=int, help="por defecto BLENDER_MCP_PORT o 9876")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # una respuesta con emojis no debe romper la consola cp1252
        sys.stdout.reconfigure(errors="replace")

    params = json.loads(args.params) if args.params else {}
    if args.code_file:
        with open(args.code_file, "r", encoding="utf-8") as f:
            params["code"] = f.read()

    host, port = args.host, args.port
    try:
        host, port = destino(host, port)
        resp = send_command(args.type, params, timeout=args.timeout, host=host, port=port)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 4
    except socket.timeout:
        print("ERROR: timeout esperando respuesta de Blender", file=sys.stderr)
        return 2
    except ConnectionRefusedError:
        print(f"ERROR: conexion rechazada en {host}:{port} - ¿addon BlenderMCP activo?", file=sys.stderr)
        return 3
    except (OSError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 5

    print(json.dumps(resp, ensure_ascii=False, indent=2)[:6000])
    return 0 if resp.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
