"""Cliente directo para el addon BlenderMCP (socket TCP localhost:9876).

Uso:
  python bclient.py get_scene_info
  python bclient.py execute_code --code-file chunk.py
  python bclient.py get_viewport_screenshot --params "{\"max_size\": 900, \"filepath\": \"C:/x.png\", \"format\": \"png\"}"
"""
import argparse
import json
import socket
import sys

HOST, PORT = "127.0.0.1", 9876


def send_command(cmd_type: str, params: dict, timeout: float = 110.0) -> dict:
    payload = json.dumps({"type": cmd_type, "params": params}).encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect((HOST, PORT))
        s.sendall(payload)
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            try:
                return json.loads(buf.decode("utf-8"))
            except json.JSONDecodeError:
                continue
    raise RuntimeError("Conexion cerrada sin respuesta completa. Buffer: %r" % buf[:500])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("type")
    ap.add_argument("--code-file", help="Archivo .py cuyo contenido se envia como params.code")
    ap.add_argument("--params", help="JSON con params adicionales")
    ap.add_argument("--timeout", type=float, default=110.0)
    args = ap.parse_args()

    params = json.loads(args.params) if args.params else {}
    if args.code_file:
        with open(args.code_file, "r", encoding="utf-8") as f:
            params["code"] = f.read()

    try:
        resp = send_command(args.type, params, timeout=args.timeout)
    except socket.timeout:
        print("ERROR: timeout esperando respuesta de Blender", file=sys.stderr)
        return 2
    except ConnectionRefusedError:
        print("ERROR: conexion rechazada — ¿addon BlenderMCP activo en puerto 9876?", file=sys.stderr)
        return 3

    print(json.dumps(resp, ensure_ascii=False, indent=2)[:6000])
    return 0 if resp.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
