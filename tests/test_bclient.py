"""Pruebas del cliente BlenderMCP contra un servidor falso en un puerto efimero.

Nunca se toca el 9876 (el del addon real del usuario).
"""
import importlib.util
import json
import socket
import threading
import time
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[1] / "_tools" / "bclient.py"


def cargar_bclient(ruta=RUTA):
    spec = importlib.util.spec_from_file_location("bclient_prueba", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def bclient():
    return cargar_bclient()


class ServidorFalso:
    """Acepta una conexion, guarda la peticion y responde en los trozos dados."""

    def __init__(self, trozos: list[bytes], pausa: float = 0.05):
        self.trozos, self.pausa, self.peticion = trozos, pausa, None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.puerto = self.sock.getsockname()[1]
        assert self.puerto != 9876
        self.hilo = threading.Thread(target=self._servir, daemon=True)
        self.hilo.start()

    def _servir(self):
        conn, _ = self.sock.accept()
        with conn:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.peticion = json.loads(conn.recv(65536).decode("utf-8"))
            for t in self.trozos:
                conn.sendall(t)
                time.sleep(self.pausa)  # fuerza recv() separados
        self.sock.close()


def trozos_cortando_la_enie(texto: str) -> list[bytes]:
    datos = json.dumps({"status": "success", "result": texto}, ensure_ascii=False).encode("utf-8")
    corte = datos.index("ñ".encode("utf-8")) + 1  # entre 0xC3 y 0xB1
    return [datos[:corte], datos[corte:]]


def test_enie_partida_entre_dos_recv(bclient):
    srv = ServidorFalso(trozos_cortando_la_enie("Año"))
    resp = bclient.send_command("get_scene_info", {}, timeout=5, port=srv.puerto)
    assert resp == {"status": "success", "result": "Año"}
    assert srv.peticion == {"type": "get_scene_info", "params": {}}


def test_el_cliente_original_fallaba_con_la_enie_partida(tmp_path):
    """Regresion: la version anterior lanzaba UnicodeDecodeError con este mismo servidor."""
    # Reconstruye el bucle de lectura original: decodificar cada vez y capturar solo JSONDecodeError.
    antiguo = '''
import json, socket
def send_command(port, timeout=5):
    with socket.socket() as s:
        s.settimeout(timeout); s.connect(("127.0.0.1", port)); s.sendall(b'{"type":"x","params":{}}')
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk: break
            buf += chunk
            try:
                return json.loads(buf.decode("utf-8"))
            except json.JSONDecodeError:
                continue
'''
    ruta = tmp_path / "bclient_antiguo.py"
    ruta.write_text(antiguo, encoding="utf-8")
    viejo = cargar_bclient(ruta)
    srv = ServidorFalso(trozos_cortando_la_enie("Año"))
    with pytest.raises(UnicodeDecodeError):
        viejo.send_command(srv.puerto)


def test_respuesta_byte_a_byte(bclient):
    datos = json.dumps({"status": "success", "result": {"objetos": ["Cámara", "Luz"], "n": 2}},
                       ensure_ascii=False).encode("utf-8")
    srv = ServidorFalso([datos[i:i + 1] for i in range(len(datos))], pausa=0.001)
    resp = bclient.send_command("x", {"a": 1}, timeout=5, port=srv.puerto)
    assert resp["result"]["objetos"] == ["Cámara", "Luz"]


def test_json_con_llave_de_cierre_intermedia(bclient):
    # El primer trozo termina en '}' pero el JSON aun no esta completo.
    srv = ServidorFalso([b'{"status": "success", "result": {"a": 1}', b', "b": 2}'])
    resp = bclient.send_command("x", {}, timeout=5, port=srv.puerto)
    assert resp == {"status": "success", "result": {"a": 1}, "b": 2}


def test_conexion_cerrada_sin_respuesta(bclient):
    srv = ServidorFalso([b'{"status": "succ'])
    with pytest.raises(RuntimeError, match="sin respuesta completa"):
        bclient.send_command("x", {}, timeout=5, port=srv.puerto)


def test_destino_por_argumento_entorno_y_defecto(bclient):
    assert bclient.destino(entorno={}) == ("127.0.0.1", 9876)
    assert bclient.destino(entorno={"BLENDER_MCP_HOST": "10.0.0.5", "BLENDER_MCP_PORT": "9999"}) == ("10.0.0.5", 9999)
    assert bclient.destino("otro", 1234, entorno={"BLENDER_MCP_PORT": "9999"}) == ("otro", 1234)
    with pytest.raises(ValueError):
        bclient.destino(port=70000, entorno={})
    with pytest.raises(ValueError):
        bclient.destino(entorno={"BLENDER_MCP_PORT": "abc"})


def test_main_con_port_y_code_file(bclient, tmp_path, capsys):
    codigo = tmp_path / "script.py"
    codigo.write_text("print('hola')", encoding="utf-8")
    srv = ServidorFalso(trozos_cortando_la_enie("Año"))
    rc = bclient.main(["execute_code", "--code-file", str(codigo), "--port", str(srv.puerto), "--timeout", "5"])
    assert rc == 0
    assert srv.peticion["params"]["code"] == "print('hola')"
    assert json.loads(capsys.readouterr().out)["result"] == "Año"


def test_main_puerto_cerrado(bclient, capsys):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    libre = s.getsockname()[1]
    s.close()  # nadie escucha: conexion rechazada
    assert libre != 9876
    rc = bclient.main(["get_scene_info", "--port", str(libre), "--timeout", "3"])
    assert rc == 3
    assert f"127.0.0.1:{libre}" in capsys.readouterr().err
