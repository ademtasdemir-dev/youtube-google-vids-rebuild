"""Entry point for the standalone EXE and local development.

Starts the FastAPI app with uvicorn and opens the browser automatically.
"""
import socket
import threading
import webbrowser

import uvicorn

from analyzer import app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    port = find_free_port()
    url = f"http://127.0.0.1:{port}"

    # Open the browser shortly after the server starts
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    print(f"YouTube Rebuild Tool läuft auf {url} ...")
    print("Beenden mit Strg+C")

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
