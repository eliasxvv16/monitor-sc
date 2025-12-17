#!/usr/bin/env python3
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, ListView, ListItem
from textual.containers import Horizontal
from textual.reactive import reactive

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

# ==========================
# CONFIG
# ==========================
SERVICES = ["apache2", "httpd"]
LOG_PATHS = [
    ("/var/log/apache2/access.log", "/var/log/apache2/error.log"),
    ("/var/log/httpd/access_log", "/var/log/httpd/error_log"),
]
BASE_DIR = pathlib.Path(__file__).parent
AUTO_LOG = BASE_DIR / "registro-auto.log"
MANUAL_LOG = BASE_DIR / "registro-manual.log"
MONITORED_URL = "http://localhost"

# Obtener información de la máquina
HOSTNAME = socket.gethostname()

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
# UTILS
# ==========================

def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        return e.output


def detect_apache():
    for service in SERVICES:
        if subprocess.run(
            ["systemctl", "status", service],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0:
            return service
    return None


def detect_logs():
    for access, error in LOG_PATHS:
        if os.path.exists(error):
            return access, error
    return None, None

# ==========================
# SUDO UTILS
# ==========================

def run_sudo(cmd, password):
    fd, path = tempfile.mkstemp()
    with os.fdopen(fd, 'w') as f:
        f.write(f"#!/bin/sh\necho '{password}'\n")
    os.chmod(path, stat.S_IRWXU)

    env = os.environ.copy()
    env["SUDO_ASKPASS"] = path
    env["DISPLAY"] = "dummy"

    try:
        return subprocess.check_output(["sudo", "-A"] + cmd, stderr=subprocess.STDOUT, text=True, env=env)
    finally:
        os.remove(path)

# ==========================
# LOGGING
# ==========================

def write_auto_log():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(AUTO_LOG, "a") as f:
        f.write(f"{now} - {HOSTNAME} ({IP_ADDRESS}) - Script ejecutado en modo AUTO\n")


def write_manual_log(action: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(MANUAL_LOG, "a") as f:
        f.write(f"{now} - {HOSTNAME} ({IP_ADDRESS}) - {action}\n")


def clean_log_file(path: pathlib.Path, max_age: timedelta):
    if not path.exists():
        return
    now = datetime.now()
    valid_lines = []
    with open(path, "r") as f:
        for line in f:
            try:
                date_str = line.split(" - ")[0]
                log_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                if now - log_date <= max_age:
                    valid_lines.append(line)
            except Exception:
                continue
    with open(path, "w") as f:
        f.writelines(valid_lines)


def clean_old_logs():
    clean_log_file(AUTO_LOG, timedelta(days=7))
    clean_log_file(MANUAL_LOG, timedelta(days=1))

# ==========================
# WIDGETS
# ==========================
class OutputPanel(Static):
    pass


def make_item(label):
    widget = Static(label)
    widget.label = label
    return ListItem(widget)

# ==========================
# APP
# ==========================
class ApacheMonitor(App):

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
        if not self.apache_service:
            return "Apache no disponible"

        write_manual_log(option)

        if option == "Estado del servicio":
            return run_cmd(["systemctl", "status", self.apache_service, "--no-pager"])

        if option == "Reload Apache":
            run_sudo(["systemctl", "reload", self.apache_service], self.sudo_password)
            return "✔ Apache recargado correctamente"

        if option == "Restart Apache":
            run_sudo(["systemctl", "restart", self.apache_service], self.sudo_password)
            return "✔ Apache reiniciado correctamente"

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
                result.append(f"HTTP {MONITORED_URL}: {r.status_code} ({r.elapsed.total_seconds():.2f}s)")
            except Exception as e:
                result.append(f"HTTP {MONITORED_URL}: ERROR ({e})")
            cpu_percent = psutil.cpu_percent(interval=1)
            result.append(f"CPU: {cpu_percent}%")
            mem = psutil.virtual_memory()
            result.append(f"RAM: {mem.percent}% de uso")
            disk = psutil.disk_usage('/')
            result.append(f"Disco /: {disk.percent}% de uso")
            status = "OK"
            if cpu_percent > 80 or mem.percent > 80 or disk.percent > 90 or (r.status_code >= 400 if 'r' in locals() else False):
                status = "WARN"
            if cpu_percent > 95 or mem.percent > 95 or disk.percent > 95 or (r.status_code >= 500 if 'r' in locals() else False):
                status = "CRIT"
            result.append(f"Estado final: {status}")
            return "\n".join(result)

        return "Opción no válida"

    def action_refresh(self):
        if self.apache_service:
            self.output.update(run_cmd(["systemctl", "status", self.apache_service, "--no-pager"]))
        else:
            self.output.update("Apache no disponible")

# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    clean_old_logs()
    write_auto_log()
    ApacheMonitor().run()
