#!/usr/bin/env python3
"""
================================================================================
Monitorización de Servicio Apache en Linux
================================================================================
Autor: [Elias Halloumi El amraoui]
Fecha: 2025-12-20
Descripción: 
    Script de monitorización de un servicio web (Apache) y recursos del sistema.
    Permite:
      - Modo manual: menú interactivo usando Textual
      - Modo automático: ejecutable mediante cron, genera logs en JSON
    Funcionalidades:
      - Estado del servicio Apache
      - Puertos escuchando (ej. 80)
      - HTTP status y tiempo de respuesta
      - Recursos del sistema: CPU, RAM, Disco
      - Logs automáticos y manuales en /var/log/monitor-sc
================================================================================
"""

# ==========================
# IMPORTS
# ==========================
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, ListView, ListItem
from textual.containers import Horizontal
from textual.reactive import reactive

import argparse
import subprocess
import os
import pathlib
from datetime import datetime, timedelta
import getpass
import psutil
import requests
import socket
import tempfile
import stat
import json

# ==========================
# CONFIGURACIÓN GENERAL
# ==========================
SERVICES = ["apache2", "httpd"]  # servicios Apache posibles
LOG_PATHS = [                     # posibles rutas de logs Apache
    ("/var/log/apache2/access.log", "/var/log/apache2/error.log"),
    ("/var/log/httpd/access_log", "/var/log/httpd/error_log"),
]

# Carpeta de logs centralizada en /var/log/monitor-sc
LOG_DIR = pathlib.Path("/var/log/monitor-sc")
LOG_DIR.mkdir(parents=True, exist_ok=True)  # crea carpeta si no existe
AUTO_LOG = LOG_DIR / "registro-auto.log"
MANUAL_LOG = LOG_DIR / "registro-manual.log"

# URL a monitorizar
MONITORED_URL = "http://localhost"

HOSTNAME = socket.gethostname()  # nombre de la máquina

# Obtener IP privada de la máquina
def get_private_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

IP_ADDRESS = get_private_ip()

# ==========================
# FUNCIONES ÚTILES
# ==========================
def run_cmd(cmd):
    """Ejecuta un comando de Linux y devuelve la salida como texto."""
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        return e.output

def detect_apache():
    """Detecta qué servicio Apache está activo."""
    for service in SERVICES:
        if subprocess.run(
            ["systemctl", "status", service],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0:
            return service
    return None

def detect_logs():
    """Detecta rutas de logs disponibles según el servicio Apache."""
    for access, error in LOG_PATHS:
        if os.path.exists(error):
            return access, error
    return None, None

# ==========================
# FUNCIONES CON SUDO (SOLO MODO MANUAL)
# ==========================
def run_sudo(cmd, password):
    """Ejecuta un comando con sudo usando la contraseña proporcionada."""
    fd, path = tempfile.mkstemp()
    with os.fdopen(fd, 'w') as f:
        f.write(f"#!/bin/sh\necho '{password}'\n")
    os.chmod(path, stat.S_IRWXU)

    env = os.environ.copy()
    env["SUDO_ASKPASS"] = path
    env["DISPLAY"] = "dummy"

    try:
        return subprocess.check_output(
            ["sudo", "-A"] + cmd,
            stderr=subprocess.STDOUT,
            text=True,
            env=env
        )
    finally:
        os.remove(path)

# ==========================
# LOGS
# ==========================
def clean_log_file(path: pathlib.Path, max_age: timedelta):
    """Limpia registros JSON antiguos según edad máxima."""
    if not path.exists():
        return
    now = datetime.now()
    valid_lines = []
    with open(path, "r") as f:
        for line in f:
            try:
                data = json.loads(line)
                log_date = datetime.fromisoformat(data["timestamp"])
                if now - log_date <= max_age:
                    valid_lines.append(line)
            except Exception:
                continue
    with open(path, "w") as f:
        f.writelines(valid_lines)

def clean_old_logs():
    """Limpia logs antiguos: Auto 7 días, Manual no se limpia."""
    clean_log_file(AUTO_LOG, timedelta(days=7))

def write_manual_log(action: str):
    """Escribe una entrada en el log manual."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(MANUAL_LOG, "a") as f:
        f.write(f"{now} - {HOSTNAME} ({IP_ADDRESS}) - {action}\n")

# ==========================
# MODO AUTOMÁTICO (CRON)
# ==========================
def run_auto_checks():
    """Ejecuta todas las comprobaciones en modo automático y genera log JSON."""
    timestamp = datetime.now().isoformat()
    service = detect_apache()

    results = {
        "timestamp": timestamp,
        "hostname": HOSTNAME,
        "ip": IP_ADDRESS,
        "checks": {},
        "final_status": "OK"
    }

    # Estado del servicio
    if service:
        active = subprocess.run(
            ["systemctl", "is-active", service],
            stdout=subprocess.PIPE,
            text=True
        ).stdout.strip()
        results["checks"]["service"] = active
        if active != "active":
            results["final_status"] = "CRIT"
    else:
        results["checks"]["service"] = "not_found"
        results["final_status"] = "CRIT"

    # Puerto 80
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_open = sock.connect_ex(("127.0.0.1", 80)) == 0
    sock.close()
    results["checks"]["port_80"] = "open" if port_open else "closed"
    if not port_open:
        results["final_status"] = "CRIT"

    # HTTP
    try:
        r = requests.get(MONITORED_URL, timeout=5)
        results["checks"]["http"] = {
            "code": r.status_code,
            "time": round(r.elapsed.total_seconds(), 3)
        }
        if r.status_code >= 500:
            results["final_status"] = "CRIT"
        elif r.status_code >= 400 and results["final_status"] != "CRIT":
            results["final_status"] = "WARN"
    except Exception:
        results["checks"]["http"] = "error"
        results["final_status"] = "CRIT"

    # Recursos del sistema
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent

    results["checks"]["cpu"] = cpu
    results["checks"]["ram"] = mem
    results["checks"]["disk"] = disk

    if cpu > 95 or mem > 95 or disk > 95:
        results["final_status"] = "CRIT"
    elif cpu > 80 or mem > 80 or disk > 90:
        if results["final_status"] != "CRIT":
            results["final_status"] = "WARN"

    # Guardar log JSON
    with open(AUTO_LOG, "a") as f:
        f.write(json.dumps(results) + "\n")

# ==========================
# MODO MANUAL (INTERACTIVO) - TEXTUAL
# ==========================
class OutputPanel(Static):
    """Panel de salida para mostrar resultados en el menú."""
    pass

def make_item(label):
    """Crea un item para el menú interactivo."""
    widget = Static(label)
    widget.label = label
    return ListItem(widget)

class ApacheMonitor(App):
    """Aplicación TUI para monitoreo manual."""
    CSS = """
    Screen { background: black; }
    ListView { width: 28%; border: solid green; background: #0b0b0b; }
    OutputPanel { width: 72%; border: solid cyan; padding: 1; overflow: auto; }
    """

    BINDINGS = [("q", "quit", "Salir"), ("r", "refresh", "Refrescar")]

    apache_service = reactive("")
    access_log = reactive("")
    error_log = reactive("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sudo_password = getpass.getpass("Contraseña sudo: ")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            self.menu = ListView(
                make_item("Estado del servicio"),
                make_item("Reload Apache"),
                make_item("Restart Apache"),
                make_item("Uptime"),
                make_item("Puertos escuchando"),
                make_item("Uso de disco"),
                make_item("Logs (error.log)"),
                make_item("Recursos y HTTP"),
                make_item("Salir"),
            )
            self.output = OutputPanel("Inicializando...")
            yield self.menu
            yield self.output
        yield Footer()

    def on_mount(self):
        self.apache_service = detect_apache()
        self.access_log, self.error_log = detect_logs()
        if not self.apache_service:
            self.output.update("❌ Apache no detectado")
        else:
            self.output.update(f"✅ Servicio detectado: {self.apache_service}")

    def on_list_view_selected(self, event):
        static_widget = event.item.query_one(Static)
        option = static_widget.label
        if option == "Salir":
            self.exit()
            return
        self.output.update(self.handle_option(option))

    def handle_option(self, option):
        """Procesa cada opción del menú manual."""
        if not self.apache_service:
            return "Apache no disponible"

        write_manual_log(option)

        if option == "Estado del servicio":
            return run_cmd(["systemctl", "status", self.apache_service, "--no-pager"])
        if option == "Reload Apache":
            run_sudo(["systemctl", "reload", self.apache_service], self.sudo_password)
            return "✔ Apache recargado"
        if option == "Restart Apache":
            run_sudo(["systemctl", "restart", self.apache_service], self.sudo_password)
            return "✔ Apache reiniciado"
        if option == "Uptime":
            return run_cmd(["systemctl", "show", self.apache_service, "--property=ActiveEnterTimestamp"])
        if option == "Puertos escuchando":
            return run_sudo(["ss", "-lntp"], self.sudo_password)
        if option == "Uso de disco":
            return run_cmd(["df", "-h"])
        if option == "Logs (error.log)":
            if self.error_log:
                return run_cmd(["tail", "-n", "30", self.error_log])
            return "No se encontró error.log"
        if option == "Recursos y HTTP":
            result = []
            try:
                r = requests.get(MONITORED_URL, timeout=5)
                result.append(f"HTTP {r.status_code} ({r.elapsed.total_seconds():.2f}s)")
            except Exception as e:
                result.append(f"HTTP ERROR ({e})")
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent
            result.append(f"CPU: {cpu}%")
            result.append(f"RAM: {mem}%")
            result.append(f"Disco /: {disk}%")
            return "\n".join(result)
        return "Opción no válida"

    def action_refresh(self):
        """Refresca el estado del servicio en el panel."""
        if self.apache_service:
            self.output.update(run_cmd(["systemctl", "status", self.apache_service, "--no-pager"]))
        else:
            self.output.update("Apache no disponible")

# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apache Monitor")
    parser.add_argument("--auto", action="store_true", help="Modo automático (cron)")
    parser.add_argument("--menu", action="store_true", help="Modo manual interactivo")
    args = parser.parse_args()

    clean_old_logs()

    if args.auto:
        # ===== MODO AUTOMÁTICO (CRON) =====
        run_auto_checks()
    else:
        # ===== MODO MANUAL (USUARIO) =====
        ApacheMonitor().run()
