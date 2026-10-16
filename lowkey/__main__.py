"""lowkey: bills your hours, lowkey. Everything stays on this machine.

python -m lowkey               track this computer + island + dashboard on http://127.0.0.1:7777
python -m lowkey --demo        the bundled demo week (no tracking, no island)
python -m lowkey --no-island   track + dashboard, without the island
"""
import sys
import threading
import webbrowser

from .config import CONFIG, DEMO, LIVE, MODEL, PORT
from .labeler import mark_personal, model_ok, refresh
from .server import make_server
from .tracker import track


def main():
    ready = "ready" if model_ok() else "not found, using keyword rules"
    try:
        server = make_server()  # binding first doubles as a lock: a second lowkey stops here instead of tracking twice
    except OSError:
        sys.exit(f"lowkey: port {PORT} is already in use. Is lowkey already running? "
                 f"(run another copy on a different port with LOWKEY_PORT=7788)")
    print(f"lowkey {'(demo) ' if DEMO else ''}-> http://127.0.0.1:{PORT}   model: {MODEL} ({ready})", flush=True)
    if not DEMO:
        threading.Thread(target=track, daemon=True).start()
        threading.Thread(target=refresh, daemon=True).start()
    island = None
    if not DEMO and "--no-island" not in sys.argv:
        try:
            from .island import Island
            open_page = lambda h="": webbrowser.open(f"http://127.0.0.1:{PORT}/{h}")
            island = Island(LIVE, {"personal": mark_personal, "open": open_page}, CONFIG["me"]["currency"],
                            CONFIG["me"].get("daily_goal_h", 6))
        except ImportError:
            print("island off: pip install PySide6-Essentials to get it")
    if island:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        island.run()  # Qt needs the main thread (required on macOS)
    else:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("lowkey: bye")


if __name__ == "__main__":
    main()
