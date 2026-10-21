"""FastAPI 应用工厂：通用 agent API + 通用 Feature API，web 端与桌面端共用。

路由一览（{aid} = agent id，{fid} = feature id）：
  GET  /                                   前端单页
  GET  /api/health                         健康检查（桌面壳启动握手用）
  GET  /api/overview                       全 agent 状态聚合（卡片 + 今日进度 + 设置）
  GET  /api/logs?limit=100                 最近日志
  POST /api/agent/{aid}/toggle             启用/停用 {enabled}
  POST /api/agent/{aid}/save               保存快照 {name, force?}
  POST /api/agent/{aid}/switch             切换账号 {name}
  POST /api/agent/{aid}/delete             删除快照 {name}
  POST /api/agent/{aid}/checkin            平台签到 {name?=指定账号} / {} 全部
  POST /api/checkin/all                    全部已启用 agent 签到
  POST /api/settings                       自动签到设置
  GET  /api/agent/{aid}/feature/{fid}/status   Feature 概览（角标/弹窗首屏）
  GET  /api/agent/{aid}/feature/{fid}/job      job 进度流
  POST /api/agent/{aid}/feature/{fid}/run      启动 job / 执行 action {payload}
  POST /api/agent/{aid}/feature/{fid}/import   凭证导入 {data}
"""
from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.agents import all_agents, get
from app.agents.base import valid_name
from app.core import config, logs, orchestrator, paths
from app.core.jobs import jobs


def _find_feature(aid: str, fid: str):
    adapter = get(aid)
    if adapter is None:
        return None, None
    feature = next((f for f in adapter.features() if f.id == fid), None)
    return adapter, feature


# 请求体模型必须定义在模块级：本文件顶部启用了 from __future__ import annotations，
# 路由函数内的注解是字符串，FastAPI 只能从模块全局解析名字——定义在 create_app()
# 局部作用域时解析不到，body 会被降级成 query 参数，所有 POST 一律 422。
class SaveBody(BaseModel):
    name: str
    force: bool = False


class NameBody(BaseModel):
    name: str


class CheckinBody(BaseModel):
    name: str | None = None


class ToggleBody(BaseModel):
    enabled: bool


class SettingsBody(BaseModel):
    auto_enabled: bool | None = None
    auto_resign: bool | None = None
    auto_time: str | None = None
    restore_after_checkin: bool | None = None


class PayloadBody(BaseModel):
    payload: dict = {}


class ImportBody(BaseModel):
    data: str = ""


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(orchestrator.scheduler_loop())
        yield
        task.cancel()

    app = FastAPI(title="AccountTools", lifespan=lifespan)

    # ---------- 静态页 ----------
    @app.get("/")
    def index():
        page = paths.STATIC_DIR / "index.html"
        if page.is_file():
            return FileResponse(page, headers={"Cache-Control": "no-store"})
        return JSONResponse({"ok": False, "error": "index.html not found"}, 404)

    @app.get("/favicon.svg")
    @app.get("/favicon.ico")
    def favicon():
        icon = paths.STATIC_DIR / "favicon.svg"
        if icon.is_file():
            return FileResponse(icon, media_type="image/svg+xml",
                                headers={"Cache-Control": "no-store"})
        return JSONResponse({"ok": False, "error": "favicon not found"}, 404)

    @app.get("/api/health")
    def health():
        return {"ok": True, "app": "accounttools", "frozen": paths.FROZEN}

    # ---------- 聚合状态 ----------
    @app.get("/api/overview")
    def overview():
        agents = all_agents()
        cfg = config.load_config(list(agents))
        today = logs.today_platform_status()
        platforms = []
        total_done = total_accounts = 0
        enabled_count = 0
        for aid, adapter in agents.items():
            pcfg = cfg["platforms"].get(aid, {})
            enabled = pcfg.get("enabled", True)
            ok_os, reason = adapter.available()
            try:
                st = adapter.state()
            except Exception as e:  # noqa: BLE001
                st = {"current": None, "currentLabel": None, "accounts": [], "error": str(e)}
            if not ok_os:
                st = {"current": None, "currentLabel": None, "accounts": [],
                      "scriptFound": False}
            signed = today.get(aid, {"done": 0, "accounts": []})
            n_acc = len(st["accounts"])
            # 日志中记录的是显示名（邮箱/号码/uid），映射回快照名再与账号列表比对
            disp2name = {a.get("display"): a["name"] for a in st["accounts"] if a.get("display")}
            signed_names = sorted({disp2name.get(x, x) for x in signed["accounts"]})
            done = min(len(signed_names), n_acc) if n_acc else 0
            if enabled and ok_os:
                enabled_count += 1
                total_done += done
                total_accounts += n_acc
            platforms.append({
                "id": aid, "label": adapter.label, "badge": adapter.badge,
                "color": adapter.color, "enabled": enabled,
                "available": ok_os, "unavailableReason": reason,
                "needsRestart": adapter.needs_restart,
                "scriptFound": st.get("scriptFound", False),
                "currentLabel": st.get("currentLabel"),
                "accounts": st.get("accounts", []),
                "signedToday": done,
                "signedAccounts": signed_names,
                "allSigned": bool(n_acc) and done >= n_acc,
                "features": [{"id": f.id, "label": f.label, "kind": f.kind,
                              "renderer": f.renderer, "buttonClass": f.button_class,
                              "description": f.description, "confirm": f.confirm,
                              "startLabel": f.start_label or "开始执行",
                              "pollSeconds": f.poll_seconds,
                              "hasStatus": f.status is not None,
                              "available": f.available_ok()[0], "reason": f.available_ok()[1]}
                             for f in adapter.features()],
            })
        return {
            "platforms": platforms,
            "progress": {"done": total_done, "total": total_accounts,
                         "enabledPlatforms": enabled_count},
            "auto": {"enabled": cfg.get("auto_enabled"), "time": cfg.get("auto_time"),
                     "resign": cfg.get("auto_resign"),
                     "restore": cfg.get("restore_after_checkin")},
        }

    @app.get("/api/logs")
    def get_logs(limit: int = 100):
        return {"logs": logs.read_logs(max(1, min(limit, 500)))}

    # ---------- agent 通用动作 ----------
    @app.post("/api/agent/{aid}/toggle")
    def toggle(aid: str, body: ToggleBody):
        adapter = get(aid)
        if adapter is None:
            return JSONResponse({"ok": False, "output": "未知 agent"}, 404)
        cfg = config.load_config(list(all_agents()))
        cfg["platforms"].setdefault(aid, {})["enabled"] = body.enabled
        config.save_config(cfg)
        return {"ok": True,
                "output": f"{'已启用' if body.enabled else '已停用'} {adapter.label}"}

    @app.post("/api/agent/{aid}/save")
    def save(aid: str, body: SaveBody):
        adapter = get(aid)
        if adapter is None:
            return JSONResponse({"ok": False, "output": "未知 agent"}, 404)
        if not valid_name(body.name):
            return {"ok": False,
                    "output": "无效的快照名：仅允许中文/字母/数字/下划线/连字符，1~32 位"}
        return adapter.save(body.name, force=body.force)

    @app.post("/api/agent/{aid}/switch")
    def switch(aid: str, body: NameBody):
        adapter = get(aid)
        if adapter is None:
            return JSONResponse({"ok": False, "output": "未知 agent"}, 404)
        if body.name.startswith("token:"):
            return {"ok": False,
                    "output": "导入的 token 账号为 API 直连签到，无需切换桌面应用"}
        if not valid_name(body.name):
            return {"ok": False, "output": "无效的快照名"}
        r = adapter.switch(body.name)
        logs.append_log(aid, r.get("ok", False),
                        f"[切换] {body.name}: {r.get('output', '')[:200]}",
                        account=body.name, trigger="switch")
        return r

    @app.post("/api/agent/{aid}/delete")
    def delete(aid: str, body: NameBody):
        adapter = get(aid)
        if adapter is None:
            return JSONResponse({"ok": False, "output": "未知 agent"}, 404)
        if not body.name.startswith("token:") and not valid_name(body.name):
            return {"ok": False, "output": "无效的快照名"}
        if body.name.startswith("token:"):
            return adapter.delete(body.name)
        r = adapter.delete(body.name)
        logs.append_log(aid, r.get("ok", False),
                        f"[删除] {r.get('output', '')}", trigger="delete")
        return r

    @app.post("/api/agent/{aid}/checkin")
    def checkin(aid: str, body: CheckinBody):
        adapter = get(aid)
        if adapter is None:
            return JSONResponse({"ok": False, "output": "未知 agent"}, 404)
        ok_os, reason = adapter.available()
        if not ok_os:
            return {"ok": False, "output": reason}
        return orchestrator.agent_checkin(adapter, only_account=body.name or None,
                                          trigger="manual")

    @app.post("/api/checkin/all")
    def checkin_all_api():
        return orchestrator.checkin_all(trigger="manual")

    @app.post("/api/settings")
    def settings(body: SettingsBody):
        cfg = config.load_config(list(all_agents()))
        if body.auto_enabled is not None:
            cfg["auto_enabled"] = body.auto_enabled
        if body.auto_resign is not None:
            cfg["auto_resign"] = body.auto_resign
        if body.restore_after_checkin is not None:
            cfg["restore_after_checkin"] = body.restore_after_checkin
        if body.auto_time is not None:
            if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", body.auto_time):
                return {"ok": False, "output": "时间格式应为 HH:MM（24 小时制）"}
            cfg["auto_time"] = body.auto_time
        config.save_config(cfg)
        return {"ok": True, "output": "设置已保存", "auto": {
            "enabled": cfg["auto_enabled"], "time": cfg["auto_time"],
            "resign": cfg["auto_resign"], "restore": cfg["restore_after_checkin"]}}

    # ---------- Feature 通用端点 ----------
    @app.get("/api/agent/{aid}/feature/{fid}/status")
    def feature_status(aid: str, fid: str, force: int = 0):
        adapter, feature = _find_feature(aid, fid)
        if feature is None:
            return JSONResponse({"ok": False, "error": "未知 feature"}, 404)
        if feature.status is None:
            return {"ok": True}
        try:
            # force=1 绕过服务端缓存(弹窗「刷新」按钮使用,避免点了数据不更新的错觉)
            return feature.status(force=bool(force))
        except TypeError:
            return feature.status()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    @app.get("/api/agent/{aid}/feature/{fid}/job")
    def feature_job(aid: str, fid: str):
        if _find_feature(aid, fid)[1] is None:
            return JSONResponse({"ok": False, "error": "未知 feature"}, 404)
        return jobs.get(f"{aid}:{fid}")

    @app.post("/api/agent/{aid}/feature/{fid}/run")
    def feature_run(aid: str, fid: str, body: PayloadBody):
        adapter, feature = _find_feature(aid, fid)
        if feature is None:
            return JSONResponse({"ok": False, "output": "未知 feature"}, 404)
        ok, reason = feature.available_ok()
        if not ok:
            return {"ok": False, "output": reason}
        if feature.run is None:
            return {"ok": False, "output": "该特性不支持启动动作"}
        try:
            return feature.run(body.payload or {})
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "output": f"执行异常: {e}"}

    @app.post("/api/agent/{aid}/feature/{fid}/import")
    def feature_import(aid: str, fid: str, body: ImportBody):
        adapter, feature = _find_feature(aid, fid)
        if feature is None:
            return JSONResponse({"ok": False, "output": "未知 feature"}, 404)
        if feature.import_data is None:
            return {"ok": False, "output": "该特性不支持导入"}
        try:
            return feature.import_data(body.data)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "output": f"导入异常: {e}"}

    return app
