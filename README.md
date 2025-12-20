# Monitorización de Apache y Sistema en Linux

**Autor:** [Elias Halloumi El Amraoui]  
**Fecha:** 2025-12-20  
**Proyecto:** Script de monitorización automática y manual en Linux  
**Lenguaje:** Python 3  
**Entorno:** Virtualenv (opcional)  

---

## 1. Descripción del proyecto

Este proyecto consiste en un script en Python que permite **monitorizar un servicio web Apache y los recursos del sistema Linux**.  
El script tiene **modo manual** (interactivo con menú) y **modo automático** (para ejecución vía cron).  
Genera registros en archivos de log, separados por modo:

- `registro-auto.log` → registros automáticos en formato JSON  
- `registro-manual.log` → registros de acciones manuales en texto plano  

El diseño permite **futuras ampliaciones**, como alertas por correo o monitorización de múltiples servicios.

---

## 2. Dependencias

El script requiere las siguientes librerías de Python:

- `textual` → interfaz de terminal interactiva  
- `psutil` → monitorización de CPU, RAM y disco  
- `requests` → comprobación HTTP  
- Librerías estándar: `os`, `subprocess`, `socket`, `pathlib`, `json`, `getpass`, `tempfile`, `stat`, `datetime`, `argparse`

### Instalación de librerías (en virtualenv recomendado)

```bash
python3 -m venv venv
source venv/bin/activate
pip install textual psutil requests
```

> Nota: la carpeta de logs `/var/log/monitor-sc` requiere permisos de escritura del usuario que ejecuta el script (Chown y chmod).

---

## 3. Estructura de archivos y logs

- **Script:** `monitor-sc.py`  
- **Logs:** `/var/log/monitor-sc/`
  - `registro-auto.log` → entradas JSON de ejecución automática  
  - `registro-manual.log` → registro de acciones manuales  
  - `cron.log` → salida de cron y errores  

El script crea automáticamente la carpeta `/var/log/monitor-sc` si no existe.

---

## 4. Funcionamiento del script

### 4.1 Modo manual (`--menu`)

- Abre un **menú interactivo en terminal** con las opciones:
  1. Estado del servicio Apache
  2. Reload Apache
  3. Restart Apache
  4. Uptime
  5. Puertos escuchando
  6. Uso de disco
  7. Logs
  8. Recursos y HTTP
  9. Salir

- Algunas acciones requieren **sudo** (`Reload`, `Restart`, `Puertos escuchando`)  
- Cada acción se registra en `registro-manual.log`  

**Ejecutar modo manual:**

```bash
python monitor.py --menu
```

---

### 4.2 Modo automático (`--auto`)

- Realiza las siguientes comprobaciones **una sola vez**:
  - Estado del servicio Apache (`active`, `inactive`, `not_found`)  
  - Puerto 80 abierto o cerrado  
  - Respuesta HTTP (código y tiempo de respuesta)  
  - Uso de CPU, RAM y disco  
  - Estado final: `OK`, `WARN` o `CRIT` según reglas definidas  

- Guarda los resultados en `registro-auto.log` en **formato JSON**, con timestamp, hostname, IP y detalles de cada check.

**Ejecutar modo automático:**

```bash
python monitor.py --auto
```

> Este modo **no reinicia ni recarga Apache**, solo monitoriza.

---

### 4.3 Limpieza de logs

- `registro-auto.log` → se limpia automáticamente de entradas mayores a 7 días  
- `registro-manual.log` → no se limpia automáticamente (puede ampliarse en el futuro)  

Función principal para limpieza de logs automáticos:

```python
def clean_old_logs():
    clean_log_file(AUTO_LOG, timedelta(days=7))
```

---

## 5. Automatización con Cron

Para ejecutar el script automáticamente cada 6 horas:

1. Edita el crontab:

```bash
crontab -e
```

2. Añade la línea:

```bash
0 */6 * * * /home/ubuntu/monitor-sc/venv/bin/python /home/ubuntu/monitor-sc/monitor.py --auto >> /var/log/monitor-sc/cron.log 2>&1
```

- `0 */6 * * *` → cada 6 horas  
- `2>&1` → redirige errores al mismo log (`cron.log`)  
- Asegúrate de que `/var/log/monitor-sc` sea escribible por el usuario:

```bash
sudo chown -R ubuntu:ubuntu /var/log/monitor-sc
sudo chmod 755 /var/log/monitor-sc
```

---

### 5.1 Para pruebas rápidas (cada minuto)

```bash
* * * * * /home/ubuntu/monitor-sc/venv/bin/python /home/ubuntu/monitor-sc/monitor.py --auto >> /var/log/monitor-sc/cron.log 2>&1
```

---

## 6. Resumen de rutas y archivos

| Modo         | Comando                           | Log generado                       |
|--------------|----------------------------------|-----------------------------------|
| Manual       | `--menu`                          | `registro-manual.log` (texto)     |
| Automático   | `--auto`                          | `registro-auto.log` (JSON)        |
| Cron         | `--auto` + cron                   | `registro-auto.log` + `cron.log`  |

---

## 7. Consideraciones

- La carpeta de logs debe existir y ser escribible por el usuario  
- El script detecta automáticamente **qué archivo de log de Apache existe** según la distribución:  
  - Debian/Ubuntu: `/var/log/apache2/error.log`  
  - CentOS/RedHat: `/var/log/httpd/error_log`  
- El script es modular y permite futuras ampliaciones: alertas por email, múltiples servicios, etc.

---

## 8. Ejemplo de entrada JSON en `registro-auto.log`

```json
{
  "timestamp": "2025-12-20T12:00:00",
  "hostname": "ip-10-0-1-55",
  "ip": "10.0.1.55",
  "checks": {
    "service": "active",
    "port_80": "open",
    "http": { "code": 200, "time": 0.123 },
    "cpu": 12.5,
    "ram": 35.2,
    "disk": 50
  },
  "final_status": "OK"
}
```

---

Este documento resume **todo lo necesario para entender y usar el script**, desde la instalación de dependencias, ejecución manual y automática, hasta la automatización con cron y gestión de logs.

