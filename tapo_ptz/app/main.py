"""Tapo PTZ – einfache Schwenk-/Neigesteuerung und Zeitpläne für Tapo-Kameras (z. B. TC70)."""
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime

import requests
from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from pytapo import Tapo
from waitress import serve

OPTIONS_FILE = "/data/options.json"
STATE_FILE = "/data/state.json"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tapo_ptz")
logging.getLogger("waitress").setLevel(logging.WARNING)

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "static"))


# ---------------------------------------------------------------- Kameras
class Camera:
    def __init__(self, cfg):
        self.name = cfg["name"]
        self.host = cfg["host"]
        self.username = cfg.get("username") or "admin"
        self.password = cfg["password"]
        self.cloud_password = cfg.get("cloud_password") or ""
        self.entity_id = cfg.get("entity_id") or ""
        self.lock = threading.Lock()
        self._tapo = None

    def _connect(self):
        log.info("Verbinde mit %s (%s) ...", self.name, self.host)
        self._tapo = Tapo(
            self.host,
            self.username,
            self.password,
            self.cloud_password,
            printWarnInformation=False,
        )

    def call(self, fn_name, *args):
        """Ruft eine pytapo-Funktion auf; bei Fehler einmal neu verbinden."""
        with self.lock:
            for attempt in (1, 2):
                try:
                    if self._tapo is None:
                        self._connect()
                    return getattr(self._tapo, fn_name)(*args)
                except Exception as err:  # noqa: BLE001
                    log.warning("%s: %s fehlgeschlagen (Versuch %s): %s", self.name, fn_name, attempt, err)
                    self._tapo = None
                    if attempt == 2:
                        raise


def load_cameras():
    with open(OPTIONS_FILE, encoding="utf-8") as f:
        opts = json.load(f)
    cams = {}
    for c in opts.get("cameras", []):
        cams[c["name"]] = Camera(c)
    return cams


CAMERAS = load_cameras()


def cam_or_404(name):
    cam = CAMERAS.get(name)
    if cam is None:
        raise KeyError(f"Kamera '{name}' nicht gefunden")
    return cam


# ---------------------------------------------------------------- Zustand (Zeitpläne)
STATE_LOCK = threading.Lock()


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"schedules": []}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


STATE = load_state()


# ---------------------------------------------------------------- Fehlerbehandlung
@app.errorhandler(Exception)
def handle_error(err):
    if isinstance(err, HTTPException):
        return err
    code = 404 if isinstance(err, KeyError) else 500
    msg = str(err).strip("'\"")
    log.error("API-Fehler: %s", msg)
    return jsonify({"ok": False, "error": msg}), code


# ---------------------------------------------------------------- Weboberfläche
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/cameras")
def api_cameras():
    return jsonify([
        {"name": c.name, "host": c.host, "has_snapshot": bool(c.entity_id)}
        for c in CAMERAS.values()
    ])


@app.route("/api/<cam>/move", methods=["POST"])
def api_move(cam):
    body = request.get_json(force=True)
    x = int(body.get("x", 0))
    y = int(body.get("y", 0))
    cam_or_404(cam).call("moveMotor", x, y)
    return jsonify({"ok": True})


@app.route("/api/<cam>/calibrate", methods=["POST"])
def api_calibrate(cam):
    cam_or_404(cam).call("calibrateMotor")
    return jsonify({"ok": True})


@app.route("/api/<cam>/presets")
def api_presets(cam):
    presets = cam_or_404(cam).call("getPresets") or {}
    return jsonify([{"id": str(k), "name": v} for k, v in presets.items()])


@app.route("/api/<cam>/presets", methods=["POST"])
def api_preset_save(cam):
    name = (request.get_json(force=True).get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Name fehlt"}), 400
    cam_or_404(cam).call("savePreset", name)
    return jsonify({"ok": True})


@app.route("/api/<cam>/presets/<pid>/goto", methods=["POST"])
def api_preset_goto(cam, pid):
    cam_or_404(cam).call("setPreset", pid)
    return jsonify({"ok": True})


@app.route("/api/<cam>/presets/<pid>", methods=["DELETE"])
def api_preset_delete(cam, pid):
    cam_or_404(cam).call("deletePreset", pid)
    with STATE_LOCK:
        STATE["schedules"] = [
            s for s in STATE["schedules"]
            if not (s["camera"] == cam and str(s["preset_id"]) == str(pid))
        ]
        save_state(STATE)
    return jsonify({"ok": True})


@app.route("/api/<cam>/snapshot")
def api_snapshot(cam):
    c = cam_or_404(cam)
    if not c.entity_id:
        return Response(status=204)
    r = requests.get(
        f"http://supervisor/core/api/camera_proxy/{c.entity_id}",
        headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
        timeout=10,
    )
    if r.status_code != 200:
        return jsonify({"ok": False, "error": f"Snapshot: HTTP {r.status_code}"}), 502
    return Response(r.content, mimetype=r.headers.get("Content-Type", "image/jpeg"),
                    headers={"Cache-Control": "no-store"})


@app.route("/api/schedules")
def api_schedules():
    with STATE_LOCK:
        return jsonify(STATE["schedules"])


@app.route("/api/schedules", methods=["POST"])
def api_schedule_add():
    b = request.get_json(force=True)
    cam_or_404(b["camera"])
    hh, mm = b["time"].split(":")
    entry = {
        "id": uuid.uuid4().hex[:8],
        "camera": b["camera"],
        "preset_id": str(b["preset_id"]),
        "preset_name": b.get("preset_name", ""),
        "time": f"{int(hh):02d}:{int(mm):02d}",
        "days": sorted({int(d) for d in b.get("days", list(range(7)))}),
        "enabled": True,
    }
    with STATE_LOCK:
        STATE["schedules"].append(entry)
        STATE["schedules"].sort(key=lambda s: (s["time"], s["camera"]))
        save_state(STATE)
    return jsonify({"ok": True, "schedule": entry})


@app.route("/api/schedules/<sid>", methods=["PATCH"])
def api_schedule_toggle(sid):
    b = request.get_json(force=True)
    with STATE_LOCK:
        for s in STATE["schedules"]:
            if s["id"] == sid:
                s["enabled"] = bool(b.get("enabled", not s["enabled"]))
        save_state(STATE)
    return jsonify({"ok": True})


@app.route("/api/schedules/<sid>", methods=["DELETE"])
def api_schedule_delete(sid):
    with STATE_LOCK:
        STATE["schedules"] = [s for s in STATE["schedules"] if s["id"] != sid]
        save_state(STATE)
    return jsonify({"ok": True})


# ---------------------------------------------------------------- Zeitplaner
def scheduler_loop():
    fired = set()  # "id@YYYY-MM-DD HH:MM" – verhindert Doppelausführung
    log.info("Zeitplaner gestartet (Zeitzone: %s)", os.environ.get("TZ", "unbekannt"))
    while True:
        now = datetime.now()
        hhmm = now.strftime("%H:%M")
        stamp = now.strftime("%Y-%m-%d ") + hhmm
        with STATE_LOCK:
            due = [
                s for s in STATE["schedules"]
                if s.get("enabled") and s["time"] == hhmm and now.weekday() in s["days"]
                and f"{s['id']}@{stamp}" not in fired
            ]
        for s in due:
            fired.add(f"{s['id']}@{stamp}")
            try:
                log.info("Zeitplan: %s → Position '%s' (%s)", s["camera"], s["preset_name"], s["time"])
                cam_or_404(s["camera"]).call("setPreset", s["preset_id"])
            except Exception as err:  # noqa: BLE001
                log.error("Zeitplan %s fehlgeschlagen: %s", s["id"], err)
        if len(fired) > 500:
            fired = {f for f in fired if f.endswith(stamp)}
        time.sleep(15)


if __name__ == "__main__":
    log.info("Kameras: %s", ", ".join(CAMERAS) or "keine konfiguriert")
    threading.Thread(target=scheduler_loop, daemon=True).start()
    serve(app, host="0.0.0.0", port=8099, threads=8)
