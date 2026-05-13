'''
   Copyright (C) 2021-2022 Katelynn Cadwallader.

   This file is part of Gatekeeper, the AMP Minecraft Discord Bot.

   Gatekeeper is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation; either version 3, or (at your option)
   any later version.

   Gatekeeper is distributed in the hope that it will be useful, but WITHOUT
   ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
   or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
   License for more details.

   You should have received a copy of the GNU General Public License
   along with Gatekeeper; see the file COPYING.  If not, write to the Free
   Software Foundation, 51 Franklin Street - Fifth Floor, Boston, MA
   02110-1301, USA. 

'''
import sys
import subprocess
import argparse
import pip
import threading
from threading import current_thread
import time
import pathlib
import os
import re
import json
import secrets


class Setup:
    def __init__(self):
        # Use action="store_true", then check the arg via "args.name" eg. "args.dev"
        parser = argparse.ArgumentParser(description='AMP Discord Bot')
        parser.add_argument('-token', help='Bypasse tokens validation check.', required=False, action="store_true")
        parser.add_argument('-super', help='This leaves AMP Super Admin role intact, use at your own risk.', required=False, action="store_true")

        # All the args below are used for development purpose.
        parser.add_argument('-dev', help='Enable development print statments.', required=False, action="store_true")
        parser.add_argument('-command', help='Enable command usage print statements.', required=False, action="store_true")
        parser.add_argument('-discord', help='Disables Discord Intigration (used for testing)', required=False, action="store_false")
        parser.add_argument('-debug', help='Enables DEBUGGING level for logging', required=False, action="store_true")
        parser.add_argument('--web-port', help='Port for the Gatekeeper Web UI. Defaults to AMP ApplicationPort1 when present, otherwise 40004 outside AMP.', required=False)
        parser.add_argument('--reset-web-login', help='Reset Web UI login setup and exit. The next web page load will ask for a new login.', required=False, action="store_true")
        self.args, self.unknown_args = parser.parse_known_args()
        if self.args.reset_web_login:
            self.reset_web_login()
            sys.exit(0)
        self.web_ui_port, self.web_ui_port_source = self.resolve_web_ui_port()

        self.pip_install()

        # Custom Logger functionality.
        import logging
        import logger
        logger.init(self.args)
        self.logger = logging.getLogger()
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        self.logger.info(f'Gatekeeper Web UI port resolved to {self.web_ui_port} ({self.web_ui_port_source})')

        # Renaming Main Thread to "Gatekeeper"
        Gatekeeper = current_thread()
        Gatekeeper.name = 'Gatekeeper'

        self.logger.dev(f'Current Startup Args:{self.args}')

        self.logger.dev("**ATTENTION** YOU ARE IN DEVELOPMENT MODE** All features are not present and stability is not guaranteed!")

        if not self.args.discord:
            self.logger.critical("***ATTENTION*** Discord Intergration has been DISABLED!")

        # This sets up our SQLite Database!
        import DB
        self.DBHandler = DB.getDBHandler()
        self.DB = self.DBHandler.DB
        self.DB_Config = self.DB.DBConfig
        self.logger.info(f'SQL Database Version: {self.DB.DBHandler.DB_Version} // SQL Database: {self.DB.DBHandler.SuccessfulDatabase}')

        import web_ui
        web_ui.register_shutdown_logging()
        self.Web_UI_Thread = threading.Thread(
            target=web_ui.run,
            name='Gatekeeper Web UI',
            kwargs={'host': '0.0.0.0', 'port': self.web_ui_port},
            daemon=True,
        )
        self.Web_UI_Thread.start()
        self.logger.info(f'Gatekeeper Web UI running at http://0.0.0.0:{self.web_ui_port}')

        # This connects and creates all our AMP related parts
        import AMP_Handler
        self.AMP_Thread = threading.Thread(target=AMP_Handler.AMP_init, name='AMP Handler', args=[self.args, ])
        self.AMP_Thread.start()

        if self.args.discord:
            while (AMP_Handler.AMP_setup == False):
                time.sleep(.5)

            # if self.args.dev and pathlib.Path('tokens_dev.py').exists():
            #     import tokens_dev as tokens

            import tokens

            import discordBot
            discordBot.client_run(tokens)

    def resolve_web_ui_port(self) -> tuple[int, str]:
        explicit_port = self.parse_port(self.args.web_port)
        if explicit_port:
            return explicit_port, "--web-port"

        cli_port = self.port_from_args(self.unknown_args)
        if not cli_port:
            cli_port = self.port_from_args(sys.argv[1:])
        if cli_port:
            return cli_port, "AMP command line arguments"

        env_port = self.port_from_environment()
        if env_port:
            return env_port, "environment"

        config_port = self.port_from_amp_config()
        if config_port:
            return config_port, "AMP config file"

        if self.is_amp_environment():
            print(
                "Gatekeeper Web UI could not find AMP's ApplicationPort1. "
                "Set App Command Line Arguments to include: --web-port {{$ApplicationPort1}}"
            )
        return 40004, "local fallback"

    def reset_web_login(self) -> None:
        config_path = pathlib.Path(__file__).resolve().parent / "web_config.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                config = {}
        else:
            config = {}
        config["secret_key"] = config.get("secret_key") or secrets.token_hex(32)
        config.pop("username", None)
        config.pop("password_hash", None)
        config["setup_complete"] = False
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print("Gatekeeper Web UI login has been reset.")
        print("Start Gatekeeper and open the Web UI to create a new login.")

    def port_from_args(self, args: list[str]):
        candidates = []
        for index, raw_arg in enumerate(args):
            arg = self.clean_arg(raw_arg)
            key, value = self.split_key_value(arg)
            if key:
                priority = self.port_key_priority(key)
                port = self.parse_port(value)
                if priority is not None and port:
                    candidates.append((priority, port))
            priority = self.port_key_priority(arg)
            if priority is not None and index + 1 < len(args):
                port = self.parse_port(args[index + 1])
                if port:
                    candidates.append((priority, port))
            if "serverport" in self.normalize_port_key(arg):
                port = self.parse_port_from_text(arg)
                if port:
                    candidates.append((50, port))
        if candidates:
            candidates.sort(key=lambda item: item[0])
            return candidates[0][1]
        return None

    def port_from_environment(self):
        preferred_names = [
            "GATEKEEPER_WEB_PORT",
            "WEB_PORT",
            "PORT",
            "GenericModule.App.Ports.$ApplicationPort1",
            "GenericModule_App_Ports_ApplicationPort1",
            "GenericModule__App__Ports__ApplicationPort1",
            "GenericModule.App.ApplicationPort1",
            "AMP_APPLICATION_PORT1",
            "APPLICATION_PORT1",
            "AMP_SERVER_PORT",
            "SERVER_PORT",
            "GenericModule.App.Ports.$ServerPort",
            "GenericModule_App_Ports_ServerPort",
            "GenericModule__App__Ports__ServerPort",
        ]
        for name in preferred_names:
            port = self.parse_port(os.environ.get(name))
            if port:
                return port
        candidates = []
        for name, value in os.environ.items():
            normalized_name = self.normalize_port_key(name)
            priority = self.port_key_priority(name)
            if priority is not None or "applicationport1" in normalized_name or "serverport" in normalized_name or "webport" in normalized_name:
                port = self.parse_port(value)
                if port:
                    candidates.append((priority if priority is not None else 100, port))
        if candidates:
            candidates.sort(key=lambda item: item[0])
            return candidates[0][1]
        return None

    def port_from_amp_config(self):
        config_roots = [pathlib.Path.cwd(), pathlib.Path(__file__).resolve().parent]
        config_roots.extend(config_roots[0].parents[:3])
        if pathlib.Path("/AMP").exists():
            config_roots.append(pathlib.Path("/AMP"))

        seen = set()
        for root in config_roots:
            if not root.exists() or root in seen:
                continue
            seen.add(root)
            for path in self.find_amp_config_files(root):
                port = self.port_from_config_file(path)
                if port:
                    return port
        return None

    def find_amp_config_files(self, root: pathlib.Path):
        names = {
            "GenericModule.kvp",
            "GenericModule.json",
            "configmanifest.json",
            "metaconfig.json",
            "AppSettings.json",
            "AMPConfig.conf",
        }
        ignored_dirs = {".git", "__pycache__", "venv", ".venv", "node_modules", "logs"}
        try:
            pending = [(root, 0)]
            while pending:
                current, depth = pending.pop()
                if depth > 4:
                    continue
                for path in current.iterdir():
                    if path.is_dir():
                        if path.name not in ignored_dirs:
                            pending.append((path, depth + 1))
                    elif path.is_file() and (path.name in names or path.suffix.lower() in {".kvp", ".json", ".conf"}):
                        yield path
        except (OSError, PermissionError):
            return

    def port_from_config_file(self, path: pathlib.Path):
        try:
            if path.stat().st_size > 1024 * 1024:
                return None
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, PermissionError):
            return None

        primary_endpoint_port = self.port_from_primary_endpoint(text)
        if primary_endpoint_port:
            return primary_endpoint_port

        monitor_port = self.port_from_monitor_ports(text)
        if monitor_port:
            return monitor_port

        preferred_patterns = [
            r"GenericModule\.App\.Ports\.\$?ApplicationPort1\s*[=:]\s*\"?(\d{2,5})\"?",
            r"GenericModule\.App\.ApplicationPort1\s*[=:]\s*\"?(\d{2,5})\"?",
            r"App\.Ports\.\$?ApplicationPort1\s*[=:]\s*\"?(\d{2,5})\"?",
            r"ApplicationPort1\s*[=:]\s*\"?(\d{2,5})\"?",
            r'"ApplicationPort1"\s*:\s*"?(\d{2,5})"?',
        ]
        fallback_patterns = [
            r"GenericModule\.App\.Ports\.\$?ServerPort\s*[=:]\s*\"?(\d{2,5})\"?",
            r"App\.Ports\.\$?ServerPort\s*[=:]\s*\"?(\d{2,5})\"?",
            r"ServerPort\s*[=:]\s*\"?(\d{2,5})\"?",
            r'"ServerPort"\s*:\s*"?(\d{2,5})"?',
        ]
        for pattern in [*preferred_patterns, *fallback_patterns]:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                port = self.parse_port(match.group(1))
                if port:
                    return port
        return None

    @classmethod
    def port_from_primary_endpoint(cls, text: str):
        match = re.search(r"AMP\.PrimaryEndpoint\s*=\s*.+?:(\d{2,5})\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return cls.parse_port(match.group(1))
        return None

    @classmethod
    def port_from_monitor_ports(cls, text: str):
        match = re.search(r"Monitoring\.MonitorPorts\s*=\s*(\[.*?\])\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            return None
        try:
            ports = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        if not isinstance(ports, list):
            return None
        candidates = []
        for item in ports:
            if not isinstance(item, dict):
                continue
            name = str(item.get("Name", "")).lower()
            port = cls.parse_port(item.get("Port"))
            if not port:
                continue
            if "main" in name:
                return port
            candidates.append(port)
        return candidates[0] if candidates else None

    def is_amp_environment(self) -> bool:
        cwd = str(pathlib.Path.cwd()).lower().replace("\\", "/")
        app_root = str(pathlib.Path(__file__).resolve().parent).lower().replace("\\", "/")
        if "/amp/" in cwd or "/amp/" in app_root or cwd.startswith("/amp") or app_root.startswith("/amp"):
            return True
        return any(name.upper().startswith("AMP") or "GENERICMODULE" in name.upper() for name in os.environ)

    @staticmethod
    def clean_arg(value):
        return str(value or "").strip().strip('"').strip("'")

    @classmethod
    def split_key_value(cls, arg):
        for separator in ("=", ":"):
            if separator in arg:
                key, value = arg.split(separator, 1)
                return cls.clean_arg(key), cls.clean_arg(value)
        return None, None

    @staticmethod
    def normalize_port_key(value):
        key = str(value or "").strip().strip('"').strip("'")
        key = key.lstrip("+-/")
        key = key.replace("$", "")
        key = key.replace("_", ".").replace("-", "")
        key = key.lower()
        return key

    @classmethod
    def port_key_priority(cls, value):
        key = cls.normalize_port_key(value)
        preferred_keys = {
            "webport",
            "gatekeeperwebport",
            "gatekeeper.web.port",
            "genericmodule.app.ports.applicationport1",
            "genericmodule.app.applicationport1",
            "app.ports.applicationport1",
            "applicationport1",
        }
        fallback_keys = {
            "genericmodule.app.ports.serverport",
            "app.ports.serverport",
            "serverport",
        }
        if key in preferred_keys:
            return 10
        if key in fallback_keys:
            return 50
        return None

    @classmethod
    def parse_port_from_text(cls, value):
        matches = re.findall(r"(?<!\d)(\d{2,5})(?!\d)", str(value or ""))
        for match in reversed(matches):
            port = cls.parse_port(match)
            if port:
                return port
        return None

    @staticmethod
    def parse_port(value):
        try:
            port = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        if 1 <= port <= 65535:
            return port
        return None

    def python_ver_check(self):
        if not sys.version_info.major >= 3 and not sys.version_info.minor >= 10:
            self.logger.critical(f'Unable to Start Gatekeeper, Python Version is {sys.version_info.major + "." + sys.version_info.minor} we require Python Version >= 3.10')
            sys.exit(1)

    def pip_install(self):
        pip_version = pip.__version__.split('.')
        pip_v_major = int(pip_version[0])
        pip_v_minor = int(pip_version[1])

        if pip_v_major > 22 or (pip_v_major == 22 and pip_v_minor >= 1):
            _current_path = pathlib.Path(__file__).parent.absolute()
            _requirements_path = _current_path.joinpath('requirements.txt')
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', f'{_requirements_path}'])
        else:
            print(f'Unable to Start Gatekeeper, PIP Version is {pip.__version__}, we require PIP Version >= 22.1')


Start = Setup()
