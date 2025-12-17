#!/usr/bin/env python3
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, ListView, ListItem
from textual.containers import Horizontal
from textual.reactive import reactive
import subprocess
import os
import pathlib
from datetime import datetime, timedelta

# ==========================
# CONFIG
# ==========================
SERVICES = ["apache2", "httpd"]
LOG_PATHS = [
    ("/var/log/apache2/access.log", "/var/log/apache2/error.log"),
    ("/var/log/httpd/access_log", "/var/log/httpd/error_log"),
]

BASE_DIR = pathlib.Path(__file__).parent
AUTO_LOG = BASE_DIR / "registro-auto.txt"
MANUAL_LOG = BASE_DIR / "registro-manual.txt"

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
# LOGGING
# ==========================
def write_auto_log():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(AUTO_LOG, "a") as f:
        f.write(f"{now} - Script ejecutado en modo AUTO\n")

def write_manual_log(action: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(MANUAL_LOG, "a") as f:
        f.write(f"{now} - {action}\n")

def clean_old_logs():
    now = datetime.now()

    # Limpiar registro auto (7 días)
    if AUTO_LOG.exists():
        lines = []
        with open(AUTO_LOG, "r") as f:
            for line in f:
                date_str = line.split(" - ")[0]
                log_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                if now - log_date <= timedelta(days=7):
                    lines.append(line)
        with open(AUTO_LOG, "w") as f:
            f.writelines(lines)

    # Limpiar registro manual (1 día)
    if MANUAL_LOG.exists():
        lines = []
        with open(MANUAL_LOG, "r") as f:
            for line in f:
                date_str = line.split(" - ")[0]
                log_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                if now - log_date <= timedelta(days=1):
                    lines.append(line)
        with open(MANUAL_LOG, "w") as f:
            f.writelines(lines)

# ==========================
# WIDGETS
# ==========================
class OutputPanel(Static):
    pass

def make_item(label):
    widget = Static(label)
    widget.label = label  # Guardamos el texto en un atributo
    return ListItem(widget)

# ==========================
# APP
# ==========================
class ApacheMonitor(App):

    CSS = """
    Screen {
        background: black;
    }

    ListView {
        width: 28%;
        border: solid green;
        background: #0b0b0b;
    }

    OutputPanel {
        width: 72%;
        border: solid cyan;
        padding: 1;
        overflow: auto;
    }
    """

    BINDINGS = [
        ("q", "quit", "Salir"),
        ("r", "refresh", "Refrescar"),
    ]

    apache_service = reactive("")
    access_log = reactive("")
    error_log = reactive("")

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
        option = static_widget.label  # <-- Usamos atributo guardado

        if option == "Salir":
            self.exit()
            return

        self.output.update(self.handle_option(option))

    def handle_option(self, option):
        if not self.apache_service:
            return "Apache no disponible"

        # Registrar acción manual
        if option != "Salir":
            write_manual_log(option)

        if option == "Estado del servicio":
            return run_cmd(["systemctl", "status", self.apache_service, "--no-pager"])

        if option == "Reload Apache":
            run_cmd(["sudo", "systemctl", "reload", self.apache_service])
            return "✔ Apache recargado correctamente"

        if option == "Restart Apache":
            run_cmd(["sudo", "systemctl", "restart", self.apache_service])
            return "✔ Apache reiniciado correctamente"

        if option == "Uptime":
            return run_cmd([
                "systemctl", "show", self.apache_service,
                "--property=ActiveEnterTimestamp"
            ])

        if option == "Puertos escuchando":
            return run_cmd(["ss", "-lntp"])

        if option == "Uso de disco":
            return run_cmd(["df", "-h"])

        if option == "Logs (error.log)":
            if self.error_log:
                return run_cmd(["tail", "-n", "30", self.error_log])
            return "No se encontró error.log"

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
