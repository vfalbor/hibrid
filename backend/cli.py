"""hibrid command-line entrypoint. `hibrid serve` runs the router."""
from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "serve"
    if cmd in ("serve", "run", "start"):
        import uvicorn
        from .config import settings
        uvicorn.run("backend.main:app", host=settings.host, port=settings.port)
    elif cmd in ("-h", "--help", "help"):
        print("usage: hibrid serve   # start the router (OpenAI + Anthropic compatible)")
    else:
        print(f"unknown command: {cmd!r}\nusage: hibrid serve")
        sys.exit(2)


if __name__ == "__main__":
    main()
