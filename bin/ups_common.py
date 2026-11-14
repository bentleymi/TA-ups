"""Shared collection logic for TA-ups scripted inputs (NUT upsc / apcupsd)."""
import json
import os
import re
import subprocess
import sys

NUT_PATHS = ("/usr/sbin/upsc", "/usr/bin/upsc")
APC_PATHS = ("/usr/sbin/apcaccess", "/usr/bin/apcaccess")

FIELD_MAP = (
    (("ups.status",), "status"),
    (("ups.model",), "model"),
    (("ups.name",), "name"),
    (("ups.battery.charge", "battery.charge"), "battery_charge"),
    (("ups.load", "load"), "load"),
    (("battery.voltage",), "battery_voltage"),
    (("input.voltage",), "input_voltage"),
    (("ups.delay.shutdown",), "delay_shutdown"),
)

NUMERIC_FIELDS = ("battery_charge", "load", "battery_voltage", "input_voltage")

METRIC_FIELDS = ("battery_charge", "load", "input_voltage")


def _find(paths):
    for p in paths:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def run_cmd(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    return p.stdout


def parse_kv(text):
    out = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        out[key.strip()] = val.strip()
    return out


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _sanitize(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "device"


def _build(raw):
    rec = {}
    for keys, field in FIELD_MAP:
        for k in keys:
            v = raw.get(k)
            if v is None or v == "":
                continue
            rec[field] = _num(v) if field in NUMERIC_FIELDS and _num(v) is not None else v
            break
    st = rec.get("status") or ""
    rec["on_battery"] = 1 if "OB" in st or "LB" in st else 0
    return rec


def _nut_devices(upsc, devices):
    listing = run_cmd([upsc, "-l"])
    for line in (listing or "").splitlines():
        name = line.strip()
        if not name:
            continue
        raw = parse_kv(run_cmd([upsc, name]))
        if not raw:
            continue
        rec = _build(raw)
        if rec:
            devices[_sanitize(name)] = rec


def _apc_device(apc, devices):
    raw = parse_kv(run_cmd([apc]))
    if not raw:
        return
    rec = _build(raw)
    if rec:
        devices[_sanitize("apcupsd")] = rec


def discover():
    data = {"status": "absent", "backend": None, "device_count": 0, "ups": {}}
    devices = {}
    upsc = _find(NUT_PATHS)
    if upsc:
        data["backend"] = "nut"
        _nut_devices(upsc, devices)
    else:
        apc = _find(APC_PATHS)
        if apc:
            data["backend"] = "apcupsd"
            _apc_device(apc, devices)
    data["ups"] = devices
    data["device_count"] = len(devices)
    if devices:
        data["status"] = "alarm" if any(d.get("on_battery") for d in devices.values()) else "ok"
    return data


def metrics_payload(data):
    devices = (data or {}).get("ups") or {}
    payload = {"device_count": len(devices)}
    for name, d in sorted(devices.items()):
        payload["%s_on_battery" % name] = 1 if d.get("on_battery") else 0
        for key in METRIC_FIELDS:
            v = d.get(key)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            payload["%s_%s" % (name, key)] = int(v) if float(v).is_integer() else float(v)
    return payload


def emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    sys.stdout.flush()


def fail(message):
    sys.stderr.write("TA-ups collection error: %s\n" % message)
    return 1
