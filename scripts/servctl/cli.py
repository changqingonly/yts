from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

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
        command = " ".join(exc.cmd) if isinstance(exc.cmd, list) else str(exc.cmd)
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
