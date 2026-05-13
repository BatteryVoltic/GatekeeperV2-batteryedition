from __future__ import annotations

import argparse
import atexit
import base64
import hashlib
import importlib.util
import json
import logging
import os
import re
import secrets
import sqlite3
import signal
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename

APP_ROOT = Path(__file__).resolve().parent
DB_PATH = APP_ROOT / "discordBot.db"
WEB_CONFIG_PATH = APP_ROOT / "web_config.json"
TOKENS_PATH = APP_ROOT / "tokens.py"
BANNER_UPLOAD_DIR = APP_ROOT / "resources" / "banners"
ALLOWED_BANNER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_IMAGE_UPLOAD_BYTES = 8 * 1024 * 1024
PERMISSIONS_PATH = APP_ROOT / "bot_perms.json"
PERMISSION_NODES = [
    "whitelist.buttons",
    "staff",
    "bot.*",
    "bot.settings",
    "bot.donator",
    "bot.moderator",
    "bot.permissions",
    "bot.bannergroup.*",
    "bot.bannergroup.rename",
    "bot.bannergroup.remove",
    "bot.bannergroup.add",
    "bot.bannergroup.delete_group",
    "bot.bannergroup.info",
    "bot.bannergroup.create_group",
    "bot.utils.*",
    "bot.utils.message_timeout",
    "bot.utils.roleid",
    "bot.utils.ping",
    "bot.utils.channelid",
    "bot.utils.uuid",
    "bot.utils.userid",
    "bot.utils.status",
    "bot.utils.sync",
    "bot.utils.clear",
    "bot.utils.restart",
    "bot.utils.disconnect",
    "bot.regex_pattern.*",
    "bot.regex_pattern.update",
    "bot.regex_pattern.add",
    "bot.regex_pattern.list",
    "bot.regex_pattern.delete",
    "bot.banner_settings.*",
    "bot.banner_settings.type",
    "bot.banner_settings.auto_update",
    "bot.cog.*",
    "bot.cog.reload",
    "bot.cog.load",
    "bot.cog.unload",
    "server.*",
    "server.broadcast",
    "server.restart",
    "server.update",
    "server.start",
    "server.stop",
    "server.users",
    "server.status",
    "server.backup",
    "server.kill",
    "server.display",
    "server.msg",
    "server.regex.*",
    "server.regex.add",
    "server.regex.list",
    "server.regex.delete",
    "server.banner.*",
    "server.banner.settings",
    "server.banner.background",
    "server.console.*",
    "server.console.filter",
    "server.console.channel",
    "server.console.interact",
    "server.settings.*",
    "server.settings.role",
    "server.settings.host",
    "server.settings.avatar",
    "server.settings.prefix",
    "server.settings.donator",
    "server.settings.info",
    "server.settings.hidden",
    "server.settings.displayname",
    "server.whitelist.*",
    "server.whitelist.add",
    "server.whitelist.true",
    "server.whitelist.false",
    "server.whitelist.remove",
    "server.whitelist.disabled",
    "server.chat.*",
    "server.chat.channel",
    "server.event.*",
    "server.event.channel",
    "bot.whitelist.*",
    "bot.whitelist.auto",
    "bot.whitelist.wait_time",
    "bot.whitelist.request_channel",
    "bot.whitelist.donator_bypass",
    "bot.whitelist_reply.*",
    "bot.whitelist_reply.list",
    "bot.whitelist_reply.add",
    "bot.whitelist_reply.remove",
    "whitelist_request",
    "dbserver.*",
    "dbserver.cleanup",
    "dbserver.change_instance_id",
    "user.*",
    "user.update",
    "user.info",
    "user.add",
    "user.role",
]


def permission_label(node: str) -> str:
    denied = node.startswith("-")
    clean = node[1:] if denied else node
    labels = {
        "whitelist.buttons": "Use whitelist approval buttons",
        "staff": "See staff-only server listings",
        "whitelist_request": "Submit whitelist requests",
        "server.console.interact": "Send commands in Discord console channels",
    }
    if clean in labels:
        label = labels[clean]
    elif clean.endswith(".*"):
        group = clean[:-2].replace("_", " ").replace(".", " → ").title()
        label = f"All {group} actions"
    else:
        parts = clean.replace("_", " ").split(".")
        group = " → ".join(part.title() for part in parts[:-1])
        action = parts[-1].replace("displayname", "display name").replace("uuid", "UUID").title()
        label = f"{group}: {action}" if group else action
    return f"Deny {label}" if denied else label


PERMISSION_CATEGORIES = [
    {
        "key": "bot-core",
        "title": "Bot Core",
        "description": "High-level bot administration: settings, moderators, donators, and permission mode.",
        "matches": lambda node: node in {"bot.*", "bot.settings", "bot.donator", "bot.moderator", "bot.permissions"},
    },
    {
        "key": "bot-display",
        "title": "Bot Display And Posting",
        "description": "Global display controls for banner groups, banner posting type, and automatic updates.",
        "matches": lambda node: node.startswith("bot.bannergroup.") or node.startswith("bot.banner_settings."),
    },
    {
        "key": "bot-tools",
        "title": "Bot Tools And Maintenance",
        "description": "Utility commands, regex-pattern management, cog loading, sync, restart, and diagnostics.",
        "matches": lambda node: node.startswith("bot.utils.") or node.startswith("bot.regex_pattern.") or node.startswith("bot.cog."),
    },
    {
        "key": "server-controls",
        "title": "Server Controls",
        "description": "Direct AMP/server actions such as start, stop, restart, kill, backup, update, status, and users.",
        "matches": lambda node: node in {
            "server.*",
            "server.start",
            "server.stop",
            "server.restart",
            "server.kill",
            "server.backup",
            "server.update",
            "server.status",
            "server.users",
        },
    },
    {
        "key": "server-discord",
        "title": "Server Discord Features",
        "description": "Discord-facing server features: status display, messages, broadcasts, console relay, chat relay, events, and server banners.",
        "matches": lambda node: node in {"server.display", "server.msg", "server.broadcast"} or node.startswith("server.console.") or node.startswith("server.chat.") or node.startswith("server.event.") or node.startswith("server.banner."),
    },
    {
        "key": "server-settings",
        "title": "Server Settings",
        "description": "Per-server settings such as host, role, avatar, prefix, donator-only, hidden, display name, and regex assignment.",
        "matches": lambda node: node.startswith("server.settings.") or node.startswith("server.regex."),
    },
    {
        "key": "whitelist-access",
        "title": "Whitelist And Access",
        "description": "Player whitelist requests, approval buttons, whitelist replies, whitelist timing, donator bypass, and staff-only listing access.",
        "matches": lambda node: node in {"whitelist_request", "whitelist.buttons", "staff"} or node.startswith("server.whitelist.") or node.startswith("bot.whitelist.") or node.startswith("bot.whitelist_reply."),
    },
    {
        "key": "users-database",
        "title": "Users And Database",
        "description": "Stored user records and database server maintenance actions.",
        "matches": lambda node: node.startswith("user.") or node.startswith("dbserver."),
    },
]


def permission_groups(nodes: list[str]) -> list[dict[str, Any]]:
    grouped = []
    assigned: set[str] = set()
    for category in PERMISSION_CATEGORIES:
        category_nodes = [node for node in nodes if node not in assigned and category["matches"](node)]
        assigned.update(category_nodes)
        grouped.append({
            "key": category["key"],
            "title": category["title"],
            "description": category["description"],
            "nodes": category_nodes,
        })
    remaining = [node for node in nodes if node not in assigned]
    if remaining:
        grouped.append({
            "key": "advanced",
            "title": "Advanced Or Unmatched",
            "description": "Permission nodes that do not fit a known category. Use these only when you know the exact command behavior.",
            "nodes": remaining,
        })
    return grouped

CONFIG_DEFAULTS = {
    "DB_Version": 3.0,
    "Guild_ID": None,
    "Moderator_role_id": None,
    "Permissions": 0,
    "Whitelist_Request_Channel": None,
    "Whitelist_Wait_Time": 5,
    "Auto_Whitelist": 0,
    "Banner_Auto_Update": 1,
    "Banner_Type": 0,
    "Banner_Update_Interval": 60,
    "Banner_Timezone": "UTC",
    "Banner_Use_12Hour": 1,
    "Banner_Timestamp_Format": "f",
    "Bot_Version": None,
    "Message_Timeout": 60,
    "Donator_Bypass": 0,
    "Donator_role_id": None,
    "Auto_BG_Remove": 0,
}

SERVER_FIELDS = [
    "DisplayName",
    "Host",
    "Whitelist",
    "Whitelist_disabled",
    "Donator",
    "Console_Flag",
    "Console_Filtered",
    "Console_Filtered_Type",
    "Discord_Console_Channel",
    "Discord_Chat_Channel",
    "Discord_Chat_Prefix",
    "Discord_Event_Channel",
    "Discord_Role",
    "Avatar_url",
    "Embed_Image_url",
    "Embed_Color",
    "Embed_Color_Mode",
    "Embed_Color_Online",
    "Embed_Color_Offline",
    "Embed_Color_Starting",
    "Embed_Color_Role",
    "Embed_Donator_Hidden",
    "Embed_Whitelist_Hidden",
    "Embed_Footer_Timezone",
    "Embed_Footer_Format",
    "Hidden",
]

BANNER_FIELDS = [
    "background_path",
    "blur_background_amount",
    "color_header",
    "color_body",
    "color_host",
    "color_whitelist_open",
    "color_whitelist_closed",
    "color_donator",
    "color_status_online",
    "color_status_offline",
    "color_player_limit_min",
    "color_player_limit_max",
    "color_player_online",
]

BOOLEAN_SERVER_FIELDS = {
    "Whitelist",
    "Whitelist_disabled",
    "Donator",
    "Console_Flag",
    "Console_Filtered",
    "Embed_Donator_Hidden",
    "Embed_Whitelist_Hidden",
    "Hidden",
}

BANNER_INTEGER_FIELDS = {"blur_background_amount"}

BANNER_DEFAULTS = {
    "background_path": None,
    "blur_background_amount": 0,
    "color_header": "#85c1e9",
    "color_body": "#f2f3f4",
    "color_host": "#5dade2",
    "color_whitelist_open": "#f7dc6f",
    "color_whitelist_closed": "#cb4335",
    "color_donator": "#212f3c",
    "color_status_online": "#28b463",
    "color_status_offline": "#e74c3c",
    "color_player_limit_min": "#ba4a00",
    "color_player_limit_max": "#5dade2",
    "color_player_online": "#f7dc6f",
}

app = Flask(__name__)
shutdown_registered = False
discord_client = None


def set_discord_client(client: Any) -> None:
    global discord_client
    discord_client = client


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def ensure_web_config() -> dict[str, Any]:
    if WEB_CONFIG_PATH.exists():
        config = json.loads(WEB_CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        config = {}

    changed = False
    if "secret_key" not in config:
        config["secret_key"] = secrets.token_hex(32)
        changed = True
    if "setup_complete" not in config:
        config["setup_complete"] = bool(config.get("username") and config.get("password_hash"))
        changed = True

    if changed:
        WEB_CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def save_web_config(config: dict[str, Any]) -> None:
    WEB_CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def load_tokens_config() -> dict[str, str]:
    values = {"token": "", "AMPAuth": "", "AMPUser": "", "AMPPassword": "", "AMPurl": ""}
    if not TOKENS_PATH.exists():
        return values
    spec = importlib.util.spec_from_file_location("gatekeeper_web_tokens", TOKENS_PATH)
    if spec is None or spec.loader is None:
        return values
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return values
    for key in values:
        values[key] = str(getattr(module, key, "") or "")
    return values


def python_string(value: str) -> str:
    return repr(value or "")


def save_tokens_config(values: dict[str, str]) -> None:
    content = "\n".join([
        "# Discord Server Connection Bot Token (Under Bot request token)",
        f"token = {python_string(values.get('token', ''))}",
        "",
        "# 2Factor AUTH Code for AMP Console Login. Leave blank if you are not using 2FA.",
        f"AMPAuth = {python_string(values.get('AMPAuth', ''))}",
        "",
        "# AMP login credentials. Do not share this file.",
        f"AMPUser = {python_string(values.get('AMPUser', ''))}",
        f"AMPPassword = {python_string(values.get('AMPPassword', ''))}",
        f"AMPurl = {python_string(values.get('AMPurl', ''))}",
        "",
    ])
    TOKENS_PATH.write_text(content, encoding="utf-8")


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db_if_needed() -> None:
    import os
    import DB

    cwd = Path.cwd()
    try:
        os.chdir(APP_ROOT)
        DB.getDBHandler()
    finally:
        os.chdir(cwd)


def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect_db() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def fetch_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with connect_db() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    with connect_db() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def log_change(kind: str, **details: Any) -> None:
    execute("insert into Log(Log) values(?)", (json.dumps({"Type": kind, **details}),))


def setting_dict() -> dict[str, Any]:
    rows = fetch_all("select Name, Value from Config order by Name")
    settings = {row["Name"]: row["Value"] for row in rows}
    for key, value in CONFIG_DEFAULTS.items():
        settings.setdefault(key, config_value(settings, key, value))
    return settings


def config_name_variants(name: str) -> list[str]:
    """Returns common config spellings used by DBConfig and older web UI forms."""
    compact = name.capitalize().replace(" ", "_").replace("-", "_")
    variants = [name, compact]
    if name == "Whitelist_Wait_Time":
        variants.extend(["WhiteList_Wait_Time", "Whitelist_wait_time"])
    if name == "Whitelist_Request_Channel":
        variants.append("Whitelist_request_channel")
    if name == "Moderator_role_id":
        variants.append("Moderator_Role_ID")
    if name == "Donator_role_id":
        variants.extend(["Donator_Role_ID", "Donator_role_id"])
    return list(dict.fromkeys(variants))


def config_value(settings: dict[str, Any], name: str, default: Any = None) -> Any:
    for variant in config_name_variants(name):
        if variant in settings:
            return settings[variant]
    return default


def set_setting(name: str, value: Any) -> None:
    existing = None
    existing_name = name
    for variant in config_name_variants(name):
        existing = fetch_one("select ID, Name from Config where Name=?", (variant,))
        if existing:
            existing_name = existing["Name"]
            break
    if existing:
        execute("update Config set Value=? where Name=?", (value, existing_name))
    else:
        execute("insert into Config(Name, Value) values(?, ?)", (name, value))
    log_change("UpdateConfig", Name=name, Value=value)


def load_permissions() -> dict[str, Any]:
    if not PERMISSIONS_PATH.exists():
        return {"Roles": []}
    return json.loads(PERMISSIONS_PATH.read_text(encoding="utf-8"))


def save_permissions(data: dict[str, Any]) -> None:
    roles = data.get("Roles", [])
    seen = set()
    for role in roles:
        name = str(role.get("name", "")).strip()
        if not name:
            raise ValueError("Every permission role needs a name.")
        if name.lower() in seen:
            raise ValueError(f"Duplicate permission role: {name}")
        seen.add(name.lower())
        discord_role_id = str(role.get("discord_role_id") or "None").strip()
        if discord_role_id != "None" and not discord_role_id.isnumeric():
            raise ValueError(f"Discord role ID for {name} must be numeric or None.")
        role["discord_role_id"] = discord_role_id
        role["prefix"] = str(role.get("prefix") or "None").strip() or "None"
        role["permissions"] = sorted(set(str(item).strip() for item in role.get("permissions", []) if str(item).strip()))
    PERMISSIONS_PATH.write_text(json.dumps({"Roles": roles}, indent=2), encoding="utf-8")
    try:
        import utils

        utils.bPerms = None
    except Exception:
        pass


def ensure_banner(server_id: int) -> dict[str, Any]:
    banner = fetch_one("select * from ServerBanners where ServerID=?", (server_id,))
    if banner:
        return banner
    fields = ["ServerID", *BANNER_FIELDS]
    values = [server_id, *[BANNER_DEFAULTS[field] for field in BANNER_FIELDS]]
    placeholders = ", ".join("?" for _ in fields)
    execute(f"insert into ServerBanners({', '.join(fields)}) values({placeholders})", tuple(values))
    return fetch_one("select * from ServerBanners where ServerID=?", (server_id,))


def banner_files() -> list[dict[str, str]]:
    banner_dir = BANNER_UPLOAD_DIR
    if not banner_dir.exists():
        return []
    return [
        {
            "name": path.name,
            "path": path.as_posix(),
            "url": url_for("banner_asset", filename=path.name),
            "public_url": url_for("public_banner_asset", filename=path.name, _external=True),
        }
        for path in sorted(banner_dir.iterdir())
        if path.is_file() and path.suffix.lower() in ALLOWED_BANNER_EXTENSIONS
    ]


def discord_options() -> dict[str, list[dict[str, Any]]]:
    if not discord_client or not getattr(discord_client, "is_ready", lambda: False)():
        return {"guilds": [], "channels": [], "roles": []}

    guilds = []
    channels = []
    roles = []
    for guild in getattr(discord_client, "guilds", []):
        guilds.append({"id": str(guild.id), "name": guild.name})
        for channel in getattr(guild, "text_channels", []):
            channels.append({"id": str(channel.id), "guild_id": str(guild.id), "name": f"{guild.name} / #{channel.name}"})
        for role in getattr(guild, "roles", []):
            if getattr(role, "is_default", lambda: False)():
                continue
            roles.append({"id": str(role.id), "guild_id": str(guild.id), "name": f"{guild.name} / {role.name}"})
    return {"guilds": guilds, "channels": channels, "roles": roles}


def timezone_options() -> list[dict[str, Any]]:
    common = [
        "UTC",
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Phoenix",
        "America/Los_Angeles",
        "America/Anchorage",
        "Pacific/Honolulu",
        "Europe/London",
        "Europe/Berlin",
        "Australia/Sydney",
    ]
    try:
        from zoneinfo import available_timezones

        zones = list(dict.fromkeys([*common, *sorted(available_timezones())]))
    except Exception:
        zones = common

    return sorted(
        [timezone_option(zone) for zone in zones],
        key=lambda item: (item["offset_minutes"], item["value"]),
    )


def timezone_option(tz_name: str) -> dict[str, Any]:
    offset_minutes = timezone_offset_minutes(tz_name)
    sign = "+" if offset_minutes >= 0 else "-"
    abs_minutes = abs(offset_minutes)
    label = f"UTC{sign}{abs_minutes // 60:02d}:{abs_minutes % 60:02d} - {tz_name}"
    return {"value": tz_name, "label": label, "offset_minutes": offset_minutes}


def timezone_offset_minutes(tz_name: str) -> int:
    try:
        from zoneinfo import ZoneInfo

        offset = datetime.now(ZoneInfo(tz_name)).utcoffset()
        if offset is not None:
            return int(offset.total_seconds() // 60)
    except Exception:
        pass
    fallback_tz = fallback_timezone(tz_name)
    offset = datetime.now(fallback_tz).utcoffset()
    return int(offset.total_seconds() // 60) if offset is not None else 0


def embed_preview(server: dict[str, Any], live: Any | None) -> dict[str, Any]:
    server_title = server_name(server)
    target_name = getattr(live, "TargetName", None) if live else None
    description = getattr(live, "Description", None) if live else None
    instance_running = bool(live and getattr(live, "Running", False))
    dedicated_running = bool(live and getattr(live, "ADS_Running", False))
    instance_status = status_text(instance_running)
    dedicated_status = status_text(dedicated_running, starting=server_starting(live))
    users = None
    user_list = None

    if live and getattr(live, "ADS_Running", False):
        try:
            users = live.getUsersOnline()
            user_list = ", ".join(live.getUserList()) or None
        except Exception:
            users = None

    return {
        "title": f"{server_title} - [{target_name}]" if target_name else server_title,
        "description": description or "Server description will appear here when AMP provides one.",
        "thumbnail": server.get("Avatar_url"),
        "image": server.get("Embed_Image_url"),
        "color": server.get("Embed_Color") or "#71368a",
        "color_mode": server.get("Embed_Color_Mode") or "static",
        "footer": server_embed_footer(server),
        "info_fields": [
            ("Host", server.get("Host") or "Not set", False),
            *([] if server.get("Embed_Donator_Hidden") else [("Donator Only", on_off(server.get("Donator")), True)]),
            *([] if server.get("Embed_Whitelist_Hidden") else [("Whitelist Requests", on_off(server.get("Whitelist")), True)]),
            ("Role", server.get("Discord_Role") or "Not set", False),
            ("Hidden", str(bool(server.get("Hidden"))), True),
            ("Whitelist Hidden", str(bool(server.get("Whitelist_disabled"))), True),
            ("Filtered Console", str(bool(server.get("Console_Filtered"))), False),
            ("Console Filter Type", "Whitelist" if server.get("Console_Filtered_Type") else "Blacklist", True),
            ("Console Channel", server.get("Discord_Console_Channel") or "Not set", False),
            ("Discord Chat Prefix", server.get("Discord_Chat_Prefix") or "Not set", False),
            ("Chat Channel", server.get("Discord_Chat_Channel") or "Not set", True),
            ("Event Channel", server.get("Discord_Event_Channel") or "Not set", True),
        ],
        "display_fields": [
            ("Instance Status", instance_status, False),
            ("Dedicated Server Status", dedicated_status, False),
            ("Host", server.get("Host") or "Not set", True),
            *([] if server.get("Embed_Donator_Hidden") else [("Donator Only", on_off(server.get("Donator")), True)]),
            *([] if server.get("Embed_Whitelist_Hidden") else [("Whitelist Requests", on_off(server.get("Whitelist")), True)]),
            ("Players" if users else "Player Limit", f"{users[0]}/{users[1]}" if users else "None", True),
            ("Players Online", user_list or "None", False),
        ],
    }


def status_text(is_online: bool, starting: bool = False) -> str:
    if starting:
        return "🟡 Starting"
    if is_online:
        return "✅ Online"
    return "❌ Offline"


def server_starting(server: Any | None) -> bool:
    if not server:
        return False
    if bool(getattr(server, "ADS_Starting", False)):
        return True
    for attr in ("ADS_State", "AppState", "State", "Status", "ApplicationState", "ApplicationStateName"):
        raw = getattr(server, attr, "") or ""
        if isinstance(raw, dict):
            for key in ("State", "state", "Value", "value", "Name", "name"):
                if key in raw:
                    raw = raw[key]
                    break
        value = str(raw).lower()
        try:
            if int(float(value)) in {5, 7, 10, 30, 100, 110}:
                return True
        except ValueError:
            pass
        if any(word in value for word in ["starting", "restarting", "loading", "initializing"]):
            return True
    return False


def on_off(value: Any) -> str:
    return "✅ On" if bool(value) else "❌ Off"


def server_embed_footer(server: dict[str, Any]) -> str:
    tz_name = server.get("Embed_Footer_Timezone") or "UTC"
    fmt = server.get("Embed_Footer_Format") or "%Y-%m-%d %I:%M %p %Z"
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name)).strftime(fmt)
    except Exception:
        try:
            import pytz

            return datetime.now(pytz.timezone(tz_name)).strftime(fmt)
        except Exception:
            fallback_tz = fallback_timezone(tz_name)
            return datetime.now(fallback_tz).strftime(fmt)


def fallback_timezone(tz_name: str):
    now = datetime.utcnow()
    dst = is_us_dst(now)
    zones = {
        "UTC": (0, "UTC"),
        "America/New_York": (-4 if dst else -5, "EDT" if dst else "EST"),
        "America/Chicago": (-5 if dst else -6, "CDT" if dst else "CST"),
        "America/Denver": (-6 if dst else -7, "MDT" if dst else "MST"),
        "America/Los_Angeles": (-7 if dst else -8, "PDT" if dst else "PST"),
        "America/Phoenix": (-7, "MST"),
    }
    offset, name = zones.get(tz_name, zones["UTC"])
    return timezone(timedelta(hours=offset), name)


def is_us_dst(now_utc: datetime) -> bool:
    year = now_utc.year
    march_first = datetime(year, 3, 1)
    november_first = datetime(year, 11, 1)
    second_sunday_march = 14 - march_first.weekday() if march_first.weekday() != 6 else 8
    first_sunday_november = 7 - november_first.weekday() if november_first.weekday() != 6 else 1
    start = datetime(year, 3, second_sunday_march, 7)
    end = datetime(year, 11, first_sunday_november, 6)
    return start <= now_utc < end


def all_banner_groups() -> list[dict[str, Any]]:
    return fetch_all("select * from BannerGroup order by name")


def banner_groups_for_server(server_id: int) -> list[dict[str, Any]]:
    return fetch_all(
        """select BG.ID, BG.name
           from BannerGroup BG
           join BannerGroupServers BGS on BGS.BannerGroupID = BG.ID
           where BGS.ServerID=?
           order by BG.name""",
        (server_id,),
    )


def banner_channels_for_groups(group_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not group_ids:
        return {}
    placeholders = ", ".join("?" for _ in group_ids)
    rows = fetch_all(
        f"""select ID, Discord_Channel_ID, Discord_Guild_ID, BannerGroupID
            from BannerGroupChannels
            where BannerGroupID in ({placeholders})
            order by Discord_Channel_ID""",
        tuple(group_ids),
    )
    channels: dict[int, list[dict[str, Any]]] = {group_id: [] for group_id in group_ids}
    for row in rows:
        channels.setdefault(row["BannerGroupID"], []).append(row)
    return channels


def get_live_handler():
    try:
        import AMP_Handler

        if AMP_Handler.Handler is None:
            args = argparse.Namespace(token=False, super=True, dev=False, command=False, discord=False, debug=False)
            handler = AMP_Handler.getAMPHandler(args=args)
            handler.setup_AMPInstances()
        return AMP_Handler.getAMPHandler()
    except Exception as exc:
        app.logger.warning("AMP connection is unavailable: %s", exc)
        return None


def live_server(instance_id: str):
    handler = get_live_handler()
    if not handler:
        return None
    return handler.AMP_Instances.get(instance_id)


def server_status_map(live_handler: Any | None) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    if not live_handler:
        return statuses
    amp_instances = getattr(live_handler, "AMP_Instances", {})
    instances = []
    for _ in range(3):
        try:
            instances = list(amp_instances.items())
            break
        except RuntimeError:
            continue
    for instance_id, amp_server in instances:
        container_online = bool(getattr(amp_server, "Running", False))
        dedicated_online = bool(getattr(amp_server, "ADS_Running", False))
        dedicated_starting = server_starting(amp_server)
        if container_online:
            try:
                dedicated_online = bool(amp_server._ADScheck() and getattr(amp_server, "ADS_Running", False))
                dedicated_starting = server_starting(amp_server)
            except Exception:
                dedicated_online = bool(getattr(amp_server, "ADS_Running", False))
                dedicated_starting = server_starting(amp_server)
        if dedicated_starting:
            dedicated_online = False
        statuses[instance_id] = {
            "amp_connected": True,
            "container_online": container_online,
            "dedicated_online": dedicated_online,
            "dedicated_starting": dedicated_starting,
        }
    return statuses


def normalize_server_value(field: str, raw: Any) -> Any:
    if field in BOOLEAN_SERVER_FIELDS:
        return 1 if str(raw).lower() in {"1", "true", "on", "yes"} else 0
    if raw is None:
        return None
    value = str(raw).strip()
    return value if value else None


def normalize_banner_value(field: str, raw: Any) -> Any:
    if field in BANNER_INTEGER_FIELDS:
        try:
            return max(0, int(raw or 0))
        except (TypeError, ValueError):
            return 0
    if raw is None:
        return None
    value = str(raw).strip()
    return value if value else None


def server_name(server: dict[str, Any]) -> str:
    return server.get("DisplayName") or server.get("FriendlyName") or server.get("InstanceName") or server.get("InstanceID")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_globals():
    return {
        "settings": setting_dict(),
        "server_name": server_name,
        "discord_options": discord_options(),
        "timezone_options": timezone_options(),
        "permission_label": permission_label,
        "web_config": ensure_web_config(),
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    config = ensure_web_config()
    if not config.get("setup_complete"):
        return redirect(url_for("setup_account"))
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == config.get("username") and hash_password(password) == config.get("password_hash"):
            session["logged_in"] = True
            flash("Welcome back.", "success")
            return redirect(url_for("dashboard"))
        flash("That login did not match.", "error")
    return render_template("login.html")


@app.route("/setup", methods=["GET", "POST"])
def setup_account():
    config = ensure_web_config()
    if config.get("setup_complete"):
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not username:
            flash("Create a username before continuing.", "error")
        elif len(password) < 6:
            flash("Use a password with at least 6 characters.", "error")
        elif password != confirm:
            flash("The passwords did not match.", "error")
        else:
            config["username"] = username
            config["password_hash"] = hash_password(password)
            config["setup_complete"] = True
            save_web_config(config)
            session["logged_in"] = True
            flash("Web login created.", "success")
            return redirect(url_for("dashboard"))
    return render_template("setup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    servers = fetch_all("select * from Servers order by Hidden, FriendlyName, InstanceName")
    users = fetch_one("select count(*) as Count from Users")
    regex = fetch_one("select count(*) as Count from RegexPatterns")
    logs = fetch_all("select ID, Log, LogDate from Log order by ID desc limit 8")
    live = get_live_handler()
    live_statuses = server_status_map(live)
    live_ids = set(live_statuses.keys())
    return render_template(
        "dashboard.html",
        servers=servers,
        user_count=users["Count"],
        regex_count=regex["Count"],
        logs=logs,
        live_ids=live_ids,
        live_statuses=live_statuses,
        live_ok=bool(live),
    )


@app.route("/api/recent-changes")
@login_required
def recent_changes_api():
    logs = fetch_all("select ID, Log, LogDate from Log order by ID desc limit 8")
    return jsonify([
        {"id": log["ID"], "log": log["Log"], "date": log["LogDate"]}
        for log in logs
    ])


@app.route("/api/server-statuses")
@login_required
def server_statuses_api():
    live = get_live_handler()
    statuses = server_status_map(live)
    return jsonify(statuses)


@app.route("/api/servers/<instance_id>/settings", methods=["POST"])
@login_required
def api_server_setting(instance_id: str):
    server = fetch_one("select * from Servers where InstanceID=?", (instance_id,))
    if not server:
        return jsonify({"ok": False, "error": "Server not found."}), 404
    data = request.get_json(silent=True) or request.form
    field = str(data.get("field") or "")
    if field not in SERVER_FIELDS:
        return jsonify({"ok": False, "error": "Unknown server setting."}), 400
    value = normalize_server_value(field, data.get("value"))
    execute(f"update Servers set {field}=? where InstanceID=?", (value, instance_id))
    log_change("ServerAutosave", InstanceID=instance_id, Field=field, Value=value)
    amp = live_server(instance_id)
    if amp and hasattr(amp, "_setDBattr"):
        amp._setDBattr()
    return jsonify({"ok": True, "field": field, "value": value})


@app.route("/api/servers/<instance_id>/banner", methods=["POST"])
@login_required
def api_server_banner_setting(instance_id: str):
    server = fetch_one("select * from Servers where InstanceID=?", (instance_id,))
    if not server:
        return jsonify({"ok": False, "error": "Server not found."}), 404
    data = request.get_json(silent=True) or request.form
    field = str(data.get("field") or "")
    if field not in BANNER_FIELDS:
        return jsonify({"ok": False, "error": "Unknown banner setting."}), 400
    ensure_banner(server["ID"])
    value = normalize_banner_value(field, data.get("value"))
    execute(f"update ServerBanners set {field}=? where ServerID=?", (value, server["ID"]))
    log_change("BannerAutosave", InstanceID=instance_id, Field=field, Value=value)
    return jsonify({"ok": True, "field": field, "value": value})


@app.route("/servers")
@login_required
def servers():
    rows = fetch_all("select * from Servers order by Hidden, FriendlyName, InstanceName")
    live = get_live_handler()
    live_statuses = server_status_map(live)
    live_ids = set(live_statuses.keys())
    return render_template("servers.html", servers=rows, live_ids=live_ids, live_statuses=live_statuses, live_ok=bool(live))


@app.route("/servers/<instance_id>", methods=["GET", "POST"])
@login_required
def server_detail(instance_id: str):
    server = fetch_one("select * from Servers where InstanceID=?", (instance_id,))
    if not server:
        flash("Server not found.", "error")
        return redirect(url_for("servers"))

    if request.method == "POST":
        scope = request.form.get("form_scope", "all")
        scope_fields = {
            "overview": [
                "DisplayName",
                "Host",
                "Discord_Role",
                "Discord_Chat_Prefix",
                "Whitelist",
                "Whitelist_disabled",
                "Donator",
                "Hidden",
                "Discord_Console_Channel",
                "Discord_Chat_Channel",
                "Discord_Event_Channel",
                "Console_Filtered_Type",
                "Console_Flag",
                "Console_Filtered",
            ],
            "embeds": [
                "Avatar_url",
                "Embed_Image_url",
                "Embed_Color",
                "Embed_Color_Mode",
                "Embed_Color_Online",
                "Embed_Color_Offline",
                "Embed_Color_Starting",
                "Embed_Color_Role",
                "Embed_Donator_Hidden",
                "Embed_Whitelist_Hidden",
                "Embed_Footer_Timezone",
                "Embed_Footer_Format",
            ],
        }
        active_fields = scope_fields.get(scope, SERVER_FIELDS)
        values = {}
        for field in active_fields:
            values[field] = normalize_server_value(field, request.form.get(field))

        assignments = ", ".join(f"{field}=?" for field in active_fields)
        execute(f"update Servers set {assignments} where InstanceID=?", (*[values[field] for field in active_fields], instance_id))
        log_change("ServerUpdate", InstanceID=instance_id, Fields=values)
        amp = live_server(instance_id)
        if amp and hasattr(amp, "_setDBattr"):
            amp._setDBattr()
        flash("Server settings saved.", "success")
        return redirect(url_for("server_detail", instance_id=instance_id))

    banner = ensure_banner(server["ID"])
    groups = all_banner_groups()
    server_groups = banner_groups_for_server(server["ID"])
    group_channels = banner_channels_for_groups([group["ID"] for group in server_groups])
    regex = fetch_all(
        """select RP.ID, RP.Name, RP.Type, RP.Pattern
           from ServerRegexPatterns SRP
           join RegexPatterns RP on RP.ID = SRP.RegexPatternID
           join Servers S on S.ID = SRP.ServerID
           where S.InstanceID=?
           order by RP.Name""",
        (instance_id,),
    )
    live = live_server(instance_id)
    return render_template(
        "server_detail.html",
        server=server,
        regex=regex,
        live=live,
        banner=banner,
        banner_files=banner_files(),
        banner_groups=groups,
        server_groups=server_groups,
        group_channels=group_channels,
        preview=embed_preview(server, live),
        discord_options=discord_options(),
    )


@app.route("/banner-assets/<path:filename>")
@login_required
def banner_asset(filename: str):
    return send_from_directory(BANNER_UPLOAD_DIR, filename)


@app.route("/public-banner-assets/<path:filename>")
def public_banner_asset(filename: str):
    return send_from_directory(BANNER_UPLOAD_DIR, filename)


@app.route("/servers/<instance_id>/banner-upload", methods=["POST"])
@login_required
def upload_banner(instance_id: str):
    server = fetch_one("select * from Servers where InstanceID=?", (instance_id,))
    if not server:
        flash("Server not found.", "error")
        return redirect(url_for("servers"))

    upload = request.files.get("banner_image")
    if not upload or not upload.filename:
        flash("Choose an image to upload.", "error")
        return redirect(url_for("server_detail", instance_id=instance_id))

    filename = secure_filename(upload.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_BANNER_EXTENSIONS:
        flash("Use a PNG, JPG, JPEG, WEBP, or GIF image.", "error")
        return redirect(url_for("server_detail", instance_id=instance_id))
    upload.seek(0, 2)
    if upload.tell() > MAX_IMAGE_UPLOAD_BYTES:
        flash("Image is too large. Keep Discord embed and thumbnail uploads under 8 MB.", "error")
        return redirect(url_for("server_detail", instance_id=instance_id))
    upload.seek(0)

    BANNER_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = BANNER_UPLOAD_DIR / filename
    stem = destination.stem
    counter = 1
    while destination.exists():
        destination = BANNER_UPLOAD_DIR / f"{stem}-{counter}{suffix}"
        counter += 1

    upload.save(destination)
    use_for = request.form.get("use_for", "banner")
    public_url = url_for("public_banner_asset", filename=destination.name, _external=True)
    ensure_banner(server["ID"])
    if use_for in {"banner", "both"}:
        execute("update ServerBanners set background_path=? where ServerID=?", (destination.as_posix(), server["ID"]))
    if use_for in {"embed_image", "both"}:
        execute("update Servers set Embed_Image_url=? where ID=?", (public_url, server["ID"]))
    if use_for == "embed_thumbnail":
        execute("update Servers set Avatar_url=? where ID=?", (public_url, server["ID"]))
    log_change("BannerImageUpload", InstanceID=instance_id, Path=destination.as_posix())
    flash("Image uploaded and selected.", "success")
    return redirect(url_for("server_detail", instance_id=instance_id))


@app.route("/servers/<instance_id>/thumbnail-editor-upload", methods=["POST"])
@login_required
def upload_edited_thumbnail(instance_id: str):
    server = fetch_one("select * from Servers where InstanceID=?", (instance_id,))
    if not server:
        flash("Server not found.", "error")
        return redirect(url_for("servers"))

    image_data = request.form.get("edited_thumbnail", "")
    match = re.match(r"^data:image/png;base64,(.+)$", image_data)
    if not match:
        flash("Use the thumbnail editor to create a thumbnail before uploading.", "error")
        return redirect(url_for("server_detail", instance_id=instance_id))

    try:
        raw = base64.b64decode(match.group(1), validate=True)
    except Exception:
        flash("Edited thumbnail data was invalid. Try choosing the image again.", "error")
        return redirect(url_for("server_detail", instance_id=instance_id))
    if len(raw) > MAX_IMAGE_UPLOAD_BYTES:
        flash("Edited thumbnail is too large. Keep it under 8 MB.", "error")
        return redirect(url_for("server_detail", instance_id=instance_id))

    BANNER_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(f"{server_name(server)}-thumbnail.png") or "thumbnail.png"
    destination = BANNER_UPLOAD_DIR / filename
    stem = destination.stem
    counter = 1
    while destination.exists():
        destination = BANNER_UPLOAD_DIR / f"{stem}-{counter}.png"
        counter += 1
    destination.write_bytes(raw)

    public_url = url_for("public_banner_asset", filename=destination.name, _external=True)
    execute("update Servers set Avatar_url=? where ID=?", (public_url, server["ID"]))
    log_change("ThumbnailEditorUpload", InstanceID=instance_id, Path=destination.as_posix())
    flash("Edited thumbnail uploaded and selected.", "success")
    return redirect(url_for("server_detail", instance_id=instance_id))


@app.route("/servers/<instance_id>/banner", methods=["POST"])
@login_required
def server_banner(instance_id: str):
    server = fetch_one("select * from Servers where InstanceID=?", (instance_id,))
    if not server:
        flash("Server not found.", "error")
        return redirect(url_for("servers"))
    ensure_banner(server["ID"])
    values = {}
    for field in BANNER_FIELDS:
        values[field] = normalize_banner_value(field, request.form.get(field))
    assignments = ", ".join(f"{field}=?" for field in BANNER_FIELDS)
    execute(f"update ServerBanners set {assignments} where ServerID=?", (*[values[field] for field in BANNER_FIELDS], server["ID"]))
    log_change("BannerUpdate", InstanceID=instance_id, Fields=values)
    flash("Banner settings saved.", "success")
    return redirect(url_for("server_detail", instance_id=instance_id))


@app.route("/servers/<instance_id>/banner-groups", methods=["POST"])
@login_required
def server_banner_groups(instance_id: str):
    server = fetch_one("select * from Servers where InstanceID=?", (instance_id,))
    if not server:
        flash("Server not found.", "error")
        return redirect(url_for("servers"))
    action = request.form.get("action")
    group_id = request.form.get("group_id")
    group_name = request.form.get("group_name", "").strip()
    channel_ref = request.form.get("channel_ref", "").strip()
    channel_id = request.form.get("channel_id", "").strip()
    guild_id = request.form.get("guild_id", "").strip()
    if channel_ref and ":" in channel_ref:
        guild_id, channel_id = channel_ref.split(":", 1)

    if action == "create" and group_name:
        try:
            group_id = execute("insert into BannerGroup(name) values(?)", (group_name,))
            flash("Banner group created.", "success")
        except sqlite3.IntegrityError:
            flash("That banner group already exists.", "error")
            return redirect(url_for("server_detail", instance_id=instance_id))

    if action in {"assign", "create"} and group_id:
        try:
            execute("insert into BannerGroupServers(ServerID, BannerGroupID) values(?, ?)", (server["ID"], group_id))
            flash("Server assigned to banner group.", "success")
        except sqlite3.IntegrityError:
            flash("Server is already in that banner group.", "error")
    elif action == "remove" and group_id:
        execute("delete from BannerGroupServers where ServerID=? and BannerGroupID=?", (server["ID"], group_id))
        flash("Server removed from banner group.", "success")
    elif action == "add_channel" and group_id and channel_id and guild_id:
        try:
            execute(
                "insert into BannerGroupChannels(Discord_Channel_ID, Discord_Guild_ID, BannerGroupID) values(?, ?, ?)",
                (channel_id, guild_id, group_id),
            )
            flash("Banner channel added.", "success")
        except sqlite3.IntegrityError:
            flash("That banner channel is already assigned.", "error")
    elif action == "remove_channel":
        channel_row_id = request.form.get("channel_row_id")
        if channel_row_id:
            execute("delete from BannerGroupMessages where BannerGroupChannelsID=?", (channel_row_id,))
            execute("delete from BannerGroupChannels where ID=?", (channel_row_id,))
            flash("Banner channel removed.", "success")

    log_change("BannerGroupUpdate", InstanceID=instance_id, Action=action, GroupID=group_id)
    return redirect(url_for("server_detail", instance_id=instance_id))


@app.route("/servers/<instance_id>/action", methods=["POST"])
@login_required
def server_action(instance_id: str):
    action = request.form.get("action", "")
    message = request.form.get("message", "")
    amp = live_server(instance_id)
    if not amp:
        flash("AMP is not connected. Check tokens.py and AMP availability.", "error")
        return redirect(url_for("server_detail", instance_id=instance_id))

    actions = {
        "start": amp.StartInstance,
        "stop": amp.StopInstance,
        "restart": amp.RestartInstance,
        "kill": amp.KillInstance,
    }
    try:
        if action in actions:
            actions[action]()
        elif action == "message":
            if not message.strip():
                flash("Enter a console message first.", "error")
                return redirect(url_for("server_detail", instance_id=instance_id))
            amp.ConsoleMessage(message.strip())
        elif action == "backup":
            now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            amp.takeBackup("Backup from Gatekeeper Web UI", f"Created from Gatekeeper Web UI at {now}")
        else:
            flash("Unknown action.", "error")
            return redirect(url_for("server_detail", instance_id=instance_id))
        flash(f"{action.title()} sent to {amp.InstanceName}.", "success")
    except Exception as exc:
        flash(f"AMP action failed: {exc}", "error")
    return redirect(url_for("server_detail", instance_id=instance_id))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    sections = [
        {
            "title": "Bot Core",
            "description": "Global bot configuration changed by /bot commands.",
            "fields": ["Guild_ID", "Moderator_role_id", "Permissions", "Message_Timeout"],
        },
        {
            "title": "Whitelist Cog",
            "description": "Controls /bot whitelist, public whitelist request buttons, staff approval routing, and auto-whitelist timing.",
            "fields": ["Whitelist_Request_Channel", "Whitelist_Wait_Time", "Auto_Whitelist", "Donator_Bypass"],
        },
        {
            "title": "Donator Access",
            "description": "Role used by donator-only server checks and whitelist bypass logic.",
            "fields": ["Donator_role_id"],
        },
    ]
    editable = [field for section in sections for field in section["fields"]]
    if request.method == "POST":
        for name in editable:
            if name in {"Auto_Whitelist", "Donator_Bypass", "Banner_Auto_Update", "Auto_BG_Remove", "Banner_Use_12Hour"}:
                if request.form.get(f"{name}_present"):
                    set_setting(name, 1 if request.form.get(name) else 0)
            else:
                if name in request.form:
                    value = request.form.get(name)
                    set_setting(name, value.strip() if value and value.strip() else None)
        flash("Bot settings saved.", "success")
        return redirect(url_for("settings_page"))
    return render_template("settings.html", current=setting_dict(), sections=sections, editable=editable)


@app.route("/display", methods=["GET", "POST"])
@login_required
def display_settings():
    if request.method == "POST":
        for name in ["Banner_Type", "Banner_Update_Interval", "Banner_Timestamp_Format", "Banner_Timezone"]:
            value = request.form.get(name)
            set_setting(name, value.strip() if value and value.strip() else None)
        for name in ["Banner_Auto_Update", "Auto_BG_Remove", "Banner_Use_12Hour"]:
            set_setting(name, 1 if request.form.get(name) else 0)
        flash("Display settings saved.", "success")
        return redirect(url_for("display_settings"))
    current = setting_dict()
    try:
        base_interval = max(15, int(current.get("Banner_Update_Interval") or 60))
    except (TypeError, ValueError):
        base_interval = 60
    return render_template(
        "display_settings.html",
        current=current,
        effective_interval=base_interval,
    )


@app.route("/permissions", methods=["GET", "POST"])
@login_required
def permissions_page():
    data = load_permissions()
    roles = data.get("Roles", [])
    if request.method == "POST":
        action = request.form.get("action")
        role_index = request.form.get("role_index")
        try:
            if action == "add_role":
                name = request.form.get("name", "").strip()
                if not name:
                    raise ValueError("Role name is required.")
                roles.append({"name": name, "discord_role_id": "None", "prefix": "None", "permissions": []})
            elif action == "delete_role" and role_index is not None:
                roles.pop(int(role_index))
            elif action == "save_role" and role_index is not None:
                role = roles[int(role_index)]
                role["name"] = request.form.get("name", "").strip()
                role["discord_role_id"] = request.form.get("discord_role_id", "None").strip() or "None"
                role["prefix"] = request.form.get("prefix", "None").strip() or "None"
                selected = request.form.getlist("permissions")
                custom_nodes = [
                    item.strip()
                    for item in request.form.get("custom_permissions", "").replace("\r", "\n").split("\n")
                    if item.strip()
                ]
                role["permissions"] = selected + custom_nodes
            save_permissions({"Roles": roles})
            log_change("PermissionsUpdate", Action=action)
            flash("Permissions saved.", "success")
        except (ValueError, IndexError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("permissions_page"))

    return render_template(
        "permissions.html",
        roles=roles,
        permission_nodes=PERMISSION_NODES,
        permission_groups=permission_groups(PERMISSION_NODES),
        current=setting_dict(),
    )


@app.route("/users", methods=["GET", "POST"])
@login_required
def users():
    role_names = [role["name"] for role in load_permissions().get("Roles", [])]
    if request.method == "POST":
        action = request.form.get("action", "add_user")
        if action == "update_role":
            user_id = request.form.get("user_id")
            role_name = request.form.get("role_name")
            execute("update Users set Role=? where ID=?", (role_name or None, user_id))
            log_change("PermissionUserRoleUpdate", UserID=user_id, Role=role_name)
            flash("User permission role updated.", "success")
            return redirect(url_for("users", q=request.args.get("q", "")))

        fields = {
            "DiscordID": request.form.get("DiscordID"),
            "DiscordName": request.form.get("DiscordName"),
            "MC_IngameName": request.form.get("MC_IngameName"),
            "MC_UUID": request.form.get("MC_UUID"),
            "SteamID": request.form.get("SteamID"),
            "Role": request.form.get("Role"),
        }
        fields = {key: (value.strip() if value and value.strip() else None) for key, value in fields.items()}
        if fields["DiscordID"]:
            execute(
                "insert into Users(DiscordID, DiscordName, MC_IngameName, MC_UUID, SteamID, Role) values(?, ?, ?, ?, ?, ?)",
                tuple(fields.values()),
            )
            log_change("AddUser", DiscordID=fields["DiscordID"])
            flash("User added.", "success")
        else:
            flash("Discord ID is required.", "error")
        return redirect(url_for("users"))

    query = request.args.get("q", "").strip()
    if query:
        like = f"%{query}%"
        rows = fetch_all(
            """select * from Users
               where DiscordID like ? or DiscordName like ? or MC_IngameName like ? or MC_UUID like ? or SteamID like ?
               order by DiscordName, MC_IngameName""",
            (like, like, like, like, like),
        )
    else:
        rows = fetch_all("select * from Users order by DiscordName, MC_IngameName")
    return render_template("users.html", users=rows, query=query, role_names=role_names)


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id: int):
    execute("delete from Users where ID=?", (user_id,))
    log_change("DeleteUser", UserID=user_id)
    flash("User deleted.", "success")
    return redirect(url_for("users"))


@app.route("/regex", methods=["GET", "POST"])
@login_required
def regex():
    if request.method == "POST":
        name = request.form.get("Name", "").strip()
        pattern = request.form.get("Pattern", "").strip()
        kind = int(request.form.get("Type", 0))
        if not name or not pattern:
            flash("Name and pattern are required.", "error")
        else:
            execute("insert into RegexPatterns(Name, Type, Pattern) values(?, ?, ?)", (name, kind, pattern))
            log_change("RegexAdd", Name=name, Type=kind, Pattern=pattern)
            flash("Regex pattern added.", "success")
        return redirect(url_for("regex"))
    rows = fetch_all("select * from RegexPatterns order by Name")
    server_rows = fetch_all("select ID, InstanceID, InstanceName, FriendlyName, DisplayName from Servers order by FriendlyName")
    return render_template("regex.html", patterns=rows, servers=server_rows)


@app.route("/regex/<int:regex_id>/delete", methods=["POST"])
@login_required
def delete_regex(regex_id: int):
    execute("delete from ServerRegexPatterns where RegexPatternID=?", (regex_id,))
    execute("delete from RegexPatterns where ID=?", (regex_id,))
    log_change("RegexDelete", RegexID=regex_id)
    flash("Regex pattern deleted.", "success")
    return redirect(url_for("regex"))


@app.route("/server-regex", methods=["POST"])
@login_required
def server_regex():
    server_id = request.form.get("server_id")
    regex_id = request.form.get("regex_id")
    mode = request.form.get("mode")
    if mode == "add":
        try:
            execute("insert into ServerRegexPatterns(ServerID, RegexPatternID) values(?, ?)", (server_id, regex_id))
            flash("Pattern assigned to server.", "success")
        except sqlite3.IntegrityError:
            flash("That pattern is already assigned.", "error")
    elif mode == "remove":
        execute("delete from ServerRegexPatterns where ServerID=? and RegexPatternID=?", (server_id, regex_id))
        flash("Pattern removed from server.", "success")
    return redirect(url_for("regex"))


@app.route("/whitelist-replies", methods=["GET", "POST"])
@login_required
def whitelist_replies():
    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if message:
            execute("insert into WhitelistReply(Message) values(?)", (message,))
            log_change("WhitelistReplyAdd", Message=message)
            flash("Reply added.", "success")
        return redirect(url_for("whitelist_replies"))
    rows = fetch_all("select * from WhitelistReply order by ID")
    return render_template("whitelist_replies.html", replies=rows)


@app.route("/whitelist-replies/<int:reply_id>/delete", methods=["POST"])
@login_required
def delete_whitelist_reply(reply_id: int):
    execute("delete from WhitelistReply where ID=?", (reply_id,))
    log_change("WhitelistReplyDelete", ReplyID=reply_id)
    flash("Reply deleted.", "success")
    return redirect(url_for("whitelist_replies"))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    config = ensure_web_config()
    if request.method == "POST":
        username = request.form.get("username", "").strip() or config["username"]
        password = request.form.get("password", "")
        config["username"] = username
        if password:
            config["password_hash"] = hash_password(password)
        config["setup_complete"] = True
        save_web_config(config)
        flash("Login credentials updated.", "success")
        return redirect(url_for("account"))
    return render_template("account.html", username=config["username"])


@app.route("/amp-login", methods=["GET", "POST"])
@login_required
def amp_login():
    tokens = load_tokens_config()
    if request.method == "POST":
        discord_token = request.form.get("token", "")
        if discord_token:
            tokens["token"] = discord_token.strip()
        tokens["AMPurl"] = request.form.get("AMPurl", "").strip().rstrip("/")
        amp_user = request.form.get("AMPUser", "").strip()
        if amp_user:
            tokens["AMPUser"] = amp_user
        password = request.form.get("AMPPassword", "")
        if password:
            tokens["AMPPassword"] = password
        amp_auth = request.form.get("AMPAuth", "").strip()
        if request.form.get("clear_AMPAuth"):
            tokens["AMPAuth"] = ""
        elif amp_auth:
            tokens["AMPAuth"] = amp_auth
        missing = []
        if not tokens.get("token"):
            missing.append("Discord bot token")
        if not tokens.get("AMPurl"):
            missing.append("AMP URL")
        if not tokens.get("AMPUser"):
            missing.append("AMP username")
        if not tokens.get("AMPPassword"):
            missing.append("AMP password")
        if missing:
            flash("Missing required credential fields: " + ", ".join(missing), "error")
            return redirect(url_for("amp_login"))
        save_tokens_config(tokens)
        log_change("AmpLoginUpdate", AMPurl=tokens["AMPurl"], AMPUser=tokens["AMPUser"])
        flash("Credential settings saved. Reboot the bot for Discord and AMP changes to take effect.", "success")
        return redirect(url_for("amp_login"))
    return render_template(
        "amp_login.html",
        tokens=tokens,
        has_discord_token=bool(tokens.get("token")),
        has_amp_user=bool(tokens.get("AMPUser")),
        has_password=bool(tokens.get("AMPPassword")),
        has_amp_auth=bool(tokens.get("AMPAuth")),
        tokens_exists=TOKENS_PATH.exists(),
    )


@app.route("/reboot", methods=["POST"])
@login_required
def reboot_bot():
    app.logger.warning("Gatekeeper reboot requested from Web UI.")
    log_change("WebUIReboot")
    def exit_process():
        time.sleep(1)
        os._exit(0)

    threading.Thread(target=exit_process, name="Gatekeeper Web UI Reboot", daemon=True).start()
    flash("Reboot requested. AMP should restart Gatekeeper if the instance is configured to restart.", "success")
    return redirect(url_for("dashboard"))


def run(host: str = "0.0.0.0", port: int = 40004) -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    init_db_if_needed()
    config = ensure_web_config()
    app.secret_key = config["secret_key"]
    logging.getLogger(__name__).info("Gatekeeper Web UI listening on http://%s:%s", host, port)
    app.run(host=host, port=port, debug=False, use_reloader=False)


def register_shutdown_logging() -> None:
    global shutdown_registered
    if shutdown_registered:
        return
    shutdown_registered = True

    def log_shutdown(reason: str) -> None:
        logging.getLogger(__name__).info("Gatekeeper shutdown requested: %s", reason)

    def signal_handler(signum, frame):
        signame = signal.Signals(signum).name
        log_shutdown(signame)
        sys.exit(0)

    atexit.register(lambda: logging.getLogger(__name__).info("Gatekeeper process stopped."))
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, signal_handler)
        except (ValueError, OSError):
            continue


def main() -> None:
    run()


if __name__ == "__main__":
    main()
