"""
GPS Server plugin – Teltonika device monitoring.

REST API for server control, data retrieval, command sending.
WebSocket at /ws/gps for real-time push.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import threading
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.plugins.base import ToolkitPlugin
from app import config

# Import core Teltonika server (kept as-is from original codebase)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from server_app.teltonika_server import (
    TeltonikaServer,
    TeltonikaProtocol,
    annotate_packet,
    io_name,
    IO_ELEMENT_NAMES,
    refresh_io_names,
)


# ── Singleton server instance ───────────────────────────────────────

_server: TeltonikaServer | None = None
_server_lock = threading.Lock()


def _get_server() -> TeltonikaServer:
    global _server
    with _server_lock:
        if _server is None:
            cfg = config.load()
            _server = TeltonikaServer(
                port=cfg.get("server_port", 8000),
                protocol=cfg.get("server_protocol", "TCP"),
            )
        return _server


def _replace_server(port: int, protocol: str) -> TeltonikaServer:
    global _server
    with _server_lock:
        if _server and _server.running:
            _server.stop()
            time.sleep(0.3)
        _server = TeltonikaServer(port=port, protocol=protocol)
        return _server


# ── WebSocket hub ───────────────────────────────────────────────────

_ws_clients: set[WebSocket] = set()


async def _broadcast(data: dict):
    dead = set()
    msg = json.dumps(data, default=str)
    for ws in list(_ws_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


_main_loop: asyncio.AbstractEventLoop | None = None


def _ws_push_loop():
    """Background thread that pushes server changes to WebSocket clients."""
    srv = _get_server()
    last_ver = srv.data_version

    while True:
        time.sleep(0.8)
        srv = _get_server()  # re-fetch in case replaced
        cur = srv.data_version
        if cur == last_ver or not _ws_clients:
            continue
        last_ver = cur

        payload = _build_status(srv)
        loop = _main_loop
        if loop is None or loop.is_closed():
            continue
        try:
            asyncio.run_coroutine_threadsafe(_broadcast(payload), loop)
        except Exception:
            pass


def _build_status(srv: TeltonikaServer) -> dict:
    # get_connected_devices acquires srv.lock internally, so call it first
    dev_list = srv.get_connected_devices()
    devices = {}
    for d in dev_list:
        imei = d.get('IMEI', 'unknown')
        devices[imei] = {
            'ip': d.get('Address', ''),
            'protocol': d.get('Protocol', ''),
            'status': d.get('Status', ''),
            'record_count': 0,
        }
    
    def _enhance(recs):
        out = []
        for r in recs:
            nr = r.copy()
            if 'IO_Data' in r:
                named = {}
                for k, v in r['IO_Data'].items():
                    try:
                        kid = int(k)
                    except (ValueError, TypeError):
                        kid = None
                    named[io_name(kid) if kid is not None else str(k)] = v
                nr['IO_Named'] = named
            out.append(nr)
        return out

    with srv.lock:
        return {
            "type": "status",
            "running": srv.running,
            "protocol": getattr(srv, 'protocol_mode', ''),
            "port": srv.port,
            "records_count": len(srv.parsed_records),
            "raw_count": len(srv.raw_messages),
            "log_count": len(srv.log_messages),
            "cmd_count": len(srv.command_history),
            "devices": devices,
            "last_records": _enhance(srv.parsed_records[:10]),
            "last_logs": srv.log_messages[:10],
            "last_raw": srv.raw_messages[:5],
        }


# ── Request models ──────────────────────────────────────────────────

class CommandReq(BaseModel):
    imei: str
    command: str


class ScheduleReq(BaseModel):
    imei: str
    command: str


class IntervalReq(BaseModel):
    imei: str
    command: str
    interval: float = 20
    interval_sec: float = 20
    duration_sec: float = 3600
    wait_for_record: bool = False


class ServerSettings(BaseModel):
    port: Optional[int] = None
    protocol: Optional[str] = None
    avl_ids_path: Optional[str] = None


# ── Plugin ──────────────────────────────────────────────────────────

class GPSServerPlugin(ToolkitPlugin):
    id = "gps"
    name = "GPS Server"
    icon = "📡"
    order = 10

    def startup(self):
        global _main_loop
        try:
            _main_loop = asyncio.get_running_loop()
        except RuntimeError:
            _main_loop = asyncio.get_event_loop()

        srv = _get_server()
        cfg = config.load()

        # Load AVL IO names
        avl = cfg.get("avl_ids_path", "")
        if avl:
            if os.path.isfile(avl):
                err = refresh_io_names(avl)
                if err:
                    print(f"  [gps] AVL IDs load error: {err}")
                else:
                    print(f"  [gps] Loaded {len(IO_ELEMENT_NAMES)} IO element names")
            else:
                print(f"  [gps] AVL IDs file not found: {avl}")

        # Auto-start server
        print(f"  [gps] Starting {cfg.get('server_protocol', 'TCP')} server on port {cfg.get('server_port', 8000)}")
        err = srv.start()
        if err:
            print(f"  [gps] Server start warning: {err}")
        else:
            print(f"  [gps] Server started successfully")

        # Start WS push thread
        t = threading.Thread(target=_ws_push_loop, daemon=True)
        t.start()
        print(f"  [gps] WebSocket push thread started")

    def shutdown(self):
        srv = _get_server()
        if srv.running:
            srv.stop()

    def register_routes(self, app: FastAPI):

        @app.get("/api/gps/status")
        async def gps_status():
            srv = _get_server()
            return _build_status(srv)

        @app.post("/api/gps/start")
        async def gps_start():
            srv = _get_server()
            if srv.running:
                return {"ok": True, "msg": "Already running"}
            err = srv.start()
            return {"ok": err is None, "msg": err or "Started"}

        @app.post("/api/gps/stop")
        async def gps_stop():
            srv = _get_server()
            srv.stop()
            return {"ok": True}

        @app.post("/api/gps/restart")
        async def gps_restart():
            cfg = config.load()
            srv = _replace_server(cfg["server_port"], cfg["server_protocol"])
            err = srv.start()
            return {"ok": err is None, "msg": err or "Restarted"}

        @app.get("/api/gps/records")
        async def gps_records(limit: int = 500):
            srv = _get_server()
            try:
                with srv.lock:
                    raw_recs = list(srv.parsed_records[:limit])
                out = []
                for r in raw_recs:
                    nr = r.copy()
                    if 'IO_Data' in r:
                        named = {}
                        for k, v in r['IO_Data'].items():
                            try:
                                kid = int(k)
                            except (ValueError, TypeError):
                                kid = None
                            named[io_name(kid) if kid is not None else str(k)] = v
                        nr['IO_Named'] = named
                    out.append(nr)
                return out
            except Exception as e:
                print(f"  [gps] Error in /api/gps/records: {e}")
                import traceback; traceback.print_exc()
                return []

        @app.get("/api/gps/raw")
        async def gps_raw(limit: int = 200, direction: str = "", search: str = "", annotate: bool = False):
            srv = _get_server()
            with srv.lock:
                msgs = list(srv.raw_messages[:limit])
            if direction:
                msgs = [m for m in msgs if m.get("direction", "") == direction.upper()]
            if search:
                sq = search.upper().replace(" ", "")
                msgs = [m for m in msgs if sq in m.get("hex", "")]
            if annotate:
                for m in msgs:
                    try:
                        m["annotations"] = annotate_packet(m.get("hex", ""), m.get("protocol", "TCP"))
                    except Exception:
                        m["annotations"] = []
            return msgs

        @app.get("/api/gps/raw/{index}/annotate")
        async def gps_raw_annotate(index: int):
            srv = _get_server()
            with srv.lock:
                if index < 0 or index >= len(srv.raw_messages):
                    return {"error": "Index out of range"}
                msg = srv.raw_messages[index]
            annotations = annotate_packet(msg["hex"], msg.get("protocol", "TCP"))
            return {"msg": msg, "annotations": annotations}

        @app.get("/api/gps/logs")
        async def gps_logs(limit: int = 200, search: str = ""):
            srv = _get_server()
            with srv.lock:
                logs = list(srv.log_messages[:limit])
            if search:
                q = search.lower()
                logs = [l for l in logs if q in l["message"].lower() or q in l["type"].lower()]
            return logs

        @app.get("/api/gps/history")
        async def gps_history(limit: int = 200):
            srv = _get_server()
            with srv.lock:
                return list(srv.command_history[:limit])

        @app.post("/api/gps/command")
        async def gps_command(req: CommandReq):
            srv = _get_server()
            ok = srv.send_command(req.imei, req.command)
            return {"ok": ok}

        @app.post("/api/gps/schedule")
        async def gps_schedule(req: ScheduleReq):
            srv = _get_server()
            srv.schedule_command(req.imei, req.command)
            return {"ok": True}

        @app.post("/api/gps/interval")
        async def gps_interval(req: IntervalReq):
            srv = _get_server()
            interval = req.interval if req.interval != 20 else req.interval_sec
            result = await asyncio.to_thread(
                srv.send_command_with_interval,
                req.imei, req.command,
                interval, req.duration_sec,
                req.wait_for_record,
            )
            return result

        @app.post("/api/gps/interval/stop")
        async def gps_interval_stop(imei: str = ""):
            srv = _get_server()
            if imei:
                srv.stop_interval_command(imei)
            else:
                # Stop all interval commands
                for dev in srv.get_connected_devices():
                    try:
                        srv.stop_interval_command(dev.get('IMEI', ''))
                    except Exception:
                        pass
            return {"ok": True}

        @app.post("/api/gps/clear")
        async def gps_clear():
            srv = _get_server()
            srv.clear_data()
            return {"ok": True}

        @app.get("/api/gps/settings")
        async def gps_settings_get():
            cfg = config.load()
            return {
                "port": cfg.get("server_port", 7580),
                "protocol": cfg.get("server_protocol", "TCP"),
                "avl_ids_path": cfg.get("avl_ids_path", ""),
            }

        @app.put("/api/gps/settings")
        async def gps_settings(req: ServerSettings):
            updates = {}
            need_restart = False
            if req.port is not None:
                updates["server_port"] = req.port
                need_restart = True
            if req.protocol is not None:
                updates["server_protocol"] = req.protocol
                need_restart = True
            if req.avl_ids_path is not None:
                updates["avl_ids_path"] = req.avl_ids_path
            if updates:
                config.save(updates)
                print(f"  [gps] Settings saved: {updates}")
            if req.avl_ids_path:
                err = refresh_io_names(req.avl_ids_path)
                if err:
                    print(f"  [gps] AVL refresh error: {err}")
                    return {"ok": False, "msg": err}
                else:
                    print(f"  [gps] Loaded {len(IO_ELEMENT_NAMES)} IO names")
            if need_restart:
                cfg = config.load()
                srv = _replace_server(cfg["server_port"], cfg["server_protocol"])
                err = srv.start()
                return {"ok": err is None, "msg": err or "Settings applied & server restarted"}
            return {"ok": True, "msg": "Settings saved"}

        @app.get("/api/gps/io_names")
        async def gps_io_names():
            return {str(k): v for k, v in IO_ELEMENT_NAMES.items()}

        @app.post("/api/gps/avl/refresh")
        async def gps_avl_refresh():
            """Reload IO element names from the configured Excel file."""
            cfg = config.load()
            path = cfg.get("avl_ids_path", "")
            if not path:
                return {"ok": False, "msg": "No AVL IDs path configured in settings"}
            print(f"  [gps] Refreshing IO names from: {path}")
            err = refresh_io_names(path)
            if err:
                print(f"  [gps] AVL refresh error: {err}")
                return {"ok": False, "msg": err}
            count = len(IO_ELEMENT_NAMES)
            print(f"  [gps] Loaded {count} IO element definitions")
            return {"ok": True, "msg": f"Loaded {count} IO definitions", "count": count}

        @app.get("/api/gps/records/export")
        async def gps_records_export():
            """Export all records as JSON file download."""
            srv = _get_server()
            with srv.lock:
                recs = list(srv.parsed_records)
            for r in recs:
                if 'IO_Data' in r:
                    named = {}
                    for k, v in r['IO_Data'].items():
                        try:
                            kid = int(k)
                        except (ValueError, TypeError):
                            kid = None
                        named[io_name(kid) if kid is not None else str(k)] = v
                    r['IO_Named'] = named
            content = json.dumps(recs, indent=2, default=str)
            return Response(
                content=content,
                media_type="application/json",
                headers={"Content-Disposition": "attachment; filename=gps_records.json"},
            )

        @app.post("/api/gps/records/clear")
        async def gps_records_clear():
            """Clear only parsed records (not logs/raw/history)."""
            srv = _get_server()
            with srv.lock:
                count = len(srv.parsed_records)
                srv.parsed_records.clear()
                srv._data_version += 1
            srv.save_state()
            print(f"  [gps] Cleared {count} records")
            return {"ok": True, "msg": f"Cleared {count} records"}

        @app.get("/api/gps/devices")
        async def gps_devices():
            srv = _get_server()
            return srv.get_connected_devices()

        # ── WebSocket for real-time updates ──────────────────────────
        @app.websocket("/ws/gps")
        async def ws_gps(websocket: WebSocket):
            global _main_loop
            _main_loop = asyncio.get_running_loop()
            await websocket.accept()
            _ws_clients.add(websocket)
            # Send initial state
            srv = _get_server()
            try:
                await websocket.send_text(json.dumps(_build_status(srv), default=str))
            except Exception:
                pass
            try:
                while True:
                    # Keep alive; client can also send commands via WS
                    data = await websocket.receive_text()
                    # Parse WS commands if needed
                    try:
                        msg = json.loads(data)
                        if msg.get("action") == "ping":
                            await websocket.send_text('{"type":"pong"}')
                    except Exception:
                        pass
            except WebSocketDisconnect:
                pass
            finally:
                _ws_clients.discard(websocket)


plugin = GPSServerPlugin()
