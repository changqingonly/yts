from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .component_commands import ComponentResult
from .config import (
    DEFAULT_FRONTEND_HOST,
    DEFAULT_FRONTEND_PORT,
    DEFAULT_HOST,
    PROFILE_DEFAULT_PORTS,
    _resolve_backend_port,
)
from .errors import ServctlError


def main(argv: Sequence[str] | None = None, *, api: Any | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    api = api or _servctl_api()
    root = api.Path(api.__file__).resolve().parents[2]

    try:
        if args.command == "components":
            names = args.names or None
            if args.component_command == "install":
                results = api.install_components(root, names)
            elif args.component_command == "verify":
                results = api.verify_components(root, names)
            elif args.component_command == "status":
                results = api.status_components(root, args.profile, names)
            else:
                parser.error(f"unsupported component command: {args.component_command}")
            _print_component_results(results)
            return 0 if _component_results_succeeded(results) else 1
        if args.command == "deploy":
            api.deploy(root, args.profile)
        elif args.command == "install":
            api.install(root)
        elif args.command == "start":
            port = _resolve_backend_port(args.profile, args.port)
            progress = api._console_progress
            print(f"servctl: starting profile={args.profile}", flush=True)
            api.start(
                root,
                args.profile,
                host=args.host,
                port=port,
                reload=args.reload,
                frontend_host=args.frontend_host,
                frontend_port=args.frontend_port,
                progress=progress,
            )
            print(
                "servctl: started "
                f"profile={args.profile} "
                f"backend=http://{args.host}:{port} "
                f"frontend=http://{args.frontend_host}:{args.frontend_port}",
                flush=True,
            )
        elif args.command == "stop":
            port = _resolve_backend_port(args.profile, args.port)
            progress = api._console_progress
            print(f"servctl: stopping profile={args.profile}", flush=True)
            api.stop(
                root,
                args.profile,
                host=args.host,
                port=port,
                frontend_host=args.frontend_host,
                frontend_port=args.frontend_port,
                progress=progress,
            )
            print(f"servctl: stopped profile={args.profile}", flush=True)
        elif args.command == "restart":
            port = _resolve_backend_port(args.profile, args.port)
            api.restart(
                root,
                args.profile,
                host=args.host,
                port=port,
                reload=args.reload,
                frontend_host=args.frontend_host,
                frontend_port=args.frontend_port,
            )
        elif args.command == "status":
            port = _resolve_backend_port(args.profile, args.port)
            print(
                api.status(
                    root,
                    args.profile,
                    host=args.host,
                    port=port,
                    frontend_host=args.frontend_host,
                    frontend_port=args.frontend_port,
                )
            )
        else:
            parser.error(f"unsupported command: {args.command}")
    except ServctlError as exc:
        print(f"servctl: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        command = _format_failed_command(exc.cmd)
        print(
            f"servctl: command failed with exit code {exc.returncode}: {command}", file=sys.stderr
        )
        return exc.returncode or 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="servctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "install", help="bootstrap local uv, Python venv, Node, and frontend deps"
    )

    components_parser = subparsers.add_parser(
        "components", help="install, verify, and inspect desktop component assets"
    )
    component_subparsers = components_parser.add_subparsers(dest="component_command", required=True)
    component_install = component_subparsers.add_parser(
        "install", help="build and download selected component assets"
    )
    component_install.add_argument("names", nargs="*", metavar="NAME")
    component_verify = component_subparsers.add_parser(
        "verify", help="verify selected component assets without changing them"
    )
    component_verify.add_argument("names", nargs="*", metavar="NAME")
    component_status = component_subparsers.add_parser(
        "status", help="show selected component asset and process states"
    )
    component_status.add_argument("names", nargs="*", metavar="NAME")
    component_status.add_argument("--profile", default="local", choices=["cloud", "local"])

    deploy_parser = subparsers.add_parser("deploy", help="check config and build frontend assets")
    deploy_parser.add_argument("--profile", default="cloud", choices=["cloud", "local"])

    start_parser = subparsers.add_parser("start", help="start the FastAPI server and web frontend")
    _add_server_args(start_parser)
    _add_frontend_args(start_parser)
    start_parser.add_argument(
        "--reload", action="store_true", help="start uvicorn with reload enabled"
    )

    stop_parser = subparsers.add_parser("stop", help="stop the FastAPI server and web frontend")
    _add_server_args(stop_parser)
    _add_frontend_args(stop_parser)

    restart_parser = subparsers.add_parser(
        "restart", help="deploy, stop, then start the FastAPI server and web frontend"
    )
    _add_server_args(restart_parser)
    _add_frontend_args(restart_parser)
    restart_parser.add_argument(
        "--reload", action="store_true", help="start uvicorn with reload enabled"
    )

    status_parser = subparsers.add_parser("status", help="show FastAPI and web frontend status")
    _add_server_args(status_parser)
    _add_frontend_args(status_parser)
    return parser


def _add_server_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", default="cloud", choices=["cloud", "local"])
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=_backend_port_help(),
    )


def _add_frontend_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--frontend-host", default=DEFAULT_FRONTEND_HOST)
    parser.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)


def _backend_port_help() -> str:
    return (
        "backend port; defaults to "
        f"{PROFILE_DEFAULT_PORTS['cloud']} for cloud and {PROFILE_DEFAULT_PORTS['local']} for local"
    )


def _servctl_api() -> Any:
    return importlib.import_module(__package__)


def _print_component_results(results: Sequence[ComponentResult]) -> None:
    for result in results:
        print(f"{result.name}: {result.state} - {result.detail}")


def _component_results_succeeded(results: Sequence[ComponentResult]) -> bool:
    return all(
        (result.enabled and result.state == "ready")
        or (not result.enabled and result.state == "disabled")
        for result in results
    )


def _format_failed_command(command: str | Sequence[str]) -> str:
    if isinstance(command, str):
        return _redact_command_argument(command)
    return " ".join(_redact_command_argument(argument) for argument in command)


def _redact_command_argument(argument: str) -> str:
    try:
        parsed = urlsplit(argument)
    except ValueError:
        return (
            "<invalid URL redacted>" if argument.startswith(("http://", "https://")) else argument
        )
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return argument

    hostname = parsed.hostname
    if ":" in hostname:
        hostname = f"[{hostname}]"
    try:
        port = f":{parsed.port}" if parsed.port is not None else ""
    except ValueError:
        return f"{parsed.scheme}://<invalid authority redacted>"
    query = "<redacted>" if parsed.query else ""
    fragment = "<redacted>" if parsed.fragment else ""
    return urlunsplit((parsed.scheme, f"{hostname}{port}", parsed.path, query, fragment))
