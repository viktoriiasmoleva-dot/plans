# -*- coding: utf-8 -*-
"""Мостик «Планы» ⇄ Mi Fitness.

Отдаёт приложение «Планы» (папка уровнем выше) и добавляет /api-эндпоинты,
которые читают данные Mi Fitness из облака Xiaomi через библиотеку mifit
(https://github.com/Jenwein/mifit). Запускать из venv инструмента mifit:

    %APPDATA%\\uv\\tools\\mifit\\Scripts\\python.exe bridge.py

Адреса после старта:
    ПК:      http://127.0.0.1:8788/
    Телефон: http://<IP-компьютера>:8788/  (та же Wi-Fi сеть)

Токен берётся из config.json рядом со скриптом (создаётся при первом запуске).
Ответы кэшируются на 5 минут, чтобы не дёргать облако Xiaomi лишний раз.
Сессия Xiaomi лежит в ~/.mifit/session.json (её обновляет opencode/mifit login).
"""
from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
from pathlib import Path
import socket

import mifit
from mifit.errors import AuthError, MiFitError

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
import uvicorn

HERE = Path(__file__).resolve().parent
APP_DIR = HERE.parent  # папка «планы-приложение»
CONFIG_PATH = HERE / "config.json"

CACHE_TTL_S = 300.0  # 5 минут, как и MCP-сервер mifit


# ---------------------------------------------------------------- config ----

def load_config() -> dict:
    cfg = {"token": secrets.token_hex(12), "port": 8788, "host": "0.0.0.0"}
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig")))
        except Exception:
            pass
    else:
        CONFIG_PATH.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return cfg


CFG = load_config()
TOKEN = str(CFG["token"])
PORT = int(CFG["port"])
HOST = str(CFG["host"])


# ---------------------------------------------------------------- session ---

_client: mifit.MiFit | None = None
_client_failed = False


def client() -> mifit.MiFit | None:
    """Клиент из сохранённой сессии; None, если сессии нет."""
    global _client, _client_failed
    if _client is not None and not _client_failed:
        return _client
    try:
        _client = mifit.MiFit()  # читает ~/.mifit/session.json, автообновление вкл.
        _client_failed = False
        return _client
    except (AuthError, MiFitError, OSError):
        _client = None
        return None


def drop_client() -> None:
    """Забыть клиента: следующий запрос перечитает сессию с диска."""
    global _client_failed
    _client_failed = True


# ------------------------------------------------------------------ cache ---

_cache: dict[tuple, tuple[float, dict]] = {}


def cached(key: tuple, fn):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    value = fn()
    _cache[key] = (now + CACHE_TTL_S, value)
    return value


def with_retry(fn, attempts: int = 2, pause_s: float = 3.0):
    """Одна повторная попытка на сетевой сбой (Xiaomi/WARP иногда рвут TLS).

    Ошибки mifit (AuthError, ApiError) повторами не лечатся — проскакивают сразу.
    """
    for i in range(attempts):
        try:
            return fn()
        except (AuthError, MiFitError):
            raise
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(pause_s)


# ---------------------------------------------------------------- helpers ---

def iso(d: date) -> str:
    return d.isoformat()


def clamp_days(raw, default: int, hi: int) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(hi, n))


def fmt_local(epoch_s, offset_s) -> str | None:
    """Время записи в «местном» времени устройства (смещение у записи своё)."""
    if not epoch_s:
        return None
    off = offset_s or 0
    return time.strftime("%Y-%m-%dT%H:%M", time.gmtime(epoch_s + off))


def records_list(result) -> list[dict]:
    out = []
    for r in (result.records or []):
        if is_dataclass(r):
            out.append(asdict(r))
    return out


def plain(value):
    """asdict-словарь без «сырых» полей, приложению не нужных."""
    drop = ("epoch_s", "stages", "start_epoch_s", "end_epoch_s", "source_sport_code")
    return {k: v for k, v in value.items() if k not in drop}


# -------------------------------------------------------------------- api ---

CORS = {"Access-Control-Allow-Origin": "*"}


def ok_json(payload: dict) -> JSONResponse:
    return JSONResponse(dict(ok=True, **payload), headers=CORS)


def err_json(kind: str, message: str = "", status: int = 200) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": kind, "message": message}, status_code=status, headers=CORS
    )


def authorized(request) -> bool:
    return request.query_params.get("token", "") == TOKEN


def read_summary(days: int) -> dict:
    today = date.today()
    start = today - timedelta(days=days - 1)
    c = client()
    if c is None:
        return {"logged_in": False, "days": []}

    steps = {r["date"]: r for r in records_list(c.steps(iso(start), iso(today)))}
    sleep = {r["date"]: r for r in records_list(c.sleep(iso(start), iso(today)))}
    hr = {r["date"]: r for r in records_list(c.heart_rate_daily(iso(start), iso(today)))}

    out_days = []
    for i in range((today - start).days + 1):
        d = iso(start + timedelta(days=i))
        day: dict = {"date": d}
        s = steps.get(d)
        if s:
            day["steps"] = plain(s)
        sl = sleep.get(d)
        if sl:
            sessions = []
            for sess in sl.get("sessions", []):
                sess = dict(sess)
                s_start = fmt_local(sess.get("start_epoch_s"), sess.get("utc_offset_s"))
                s_end = fmt_local(sess.get("end_epoch_s"), sess.get("utc_offset_s"))
                sess = plain(sess)
                sess["start"] = s_start
                sess["end"] = s_end
                sessions.append(sess)
            rec = plain(sl)
            rec["sessions"] = sessions
            day["sleep"] = rec
        h = hr.get(d)
        if h:
            day["hr"] = plain(h)
        out_days.append(day)
    return {"logged_in": True, "today": iso(today), "days": out_days}


def read_workouts(days: int) -> dict:
    today = date.today()
    start = today - timedelta(days=days - 1)
    c = client()
    if c is None:
        return {"logged_in": False, "workouts": []}

    rows = []
    for w in records_list(c.workouts(iso(start), iso(today))):
        rec = plain(w)
        rec["start"] = fmt_local(w.get("start_epoch_s"), w.get("utc_offset_s"))
        rec["end"] = fmt_local(w.get("end_epoch_s"), w.get("utc_offset_s"))
        rows.append(rec)
    rows.sort(key=lambda r: r.get("start_epoch_s") or 0, reverse=True)
    return {"logged_in": True, "workouts": rows}


def api_status(request):
    if not authorized(request):
        return err_json("token", "неверный token", 401)
    c = client()
    info = {
        "logged_in": c is not None,
        "today": iso(date.today()),
        "cache_ttl_s": CACHE_TTL_S,
    }
    if c is not None:
        info["region"] = getattr(getattr(c, "session", None), "region", None)
    return ok_json(info)


def api_summary(request):
    if not authorized(request):
        return err_json("token", "неверный token", 401)
    days = clamp_days(request.query_params.get("days"), 7, 31)
    try:
        data = cached(("summary", days), lambda: with_retry(lambda: read_summary(days)))
    except AuthError:
        drop_client()
        return err_json("auth", "сессия Xiaomi истекла — войдите заново (mifit login)")
    except MiFitError as exc:
        return err_json("api", str(exc))
    except Exception as exc:  # сеть и прочее
        return err_json("network", str(exc))
    return ok_json(data)


def api_workouts(request):
    if not authorized(request):
        return err_json("token", "неверный token", 401)
    days = clamp_days(request.query_params.get("days"), 30, 92)
    try:
        data = cached(("workouts", days), lambda: with_retry(lambda: read_workouts(days)))
    except AuthError:
        drop_client()
        return err_json("auth", "сессия Xiaomi истекла — войдите заново (mifit login)")
    except MiFitError as exc:
        return err_json("api", str(exc))
    except Exception as exc:
        return err_json("network", str(exc))
    return ok_json(data)


app = Starlette(
    routes=[
        Route("/api/status", api_status, methods=["GET"]),
        Route("/api/summary", api_summary, methods=["GET"]),
        Route("/api/workouts", api_workouts, methods=["GET"]),
        Mount("/", app=StaticFiles(directory=APP_DIR, html=True), name="app"),
    ]
)


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    print("«Планы» + Mi Fitness — мостик запущен")
    print(f"  ПК:       http://127.0.0.1:{PORT}/")
    print(f"  Телефон:  http://{lan_ip()}:{PORT}/   (та же Wi-Fi сеть)")
    print(f"  Токен:    {TOKEN}")
    print("  Остановить: закрыть это окно (или Ctrl+C).")
    try:
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
    except KeyboardInterrupt:
        pass
