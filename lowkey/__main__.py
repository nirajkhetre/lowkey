"""lowkey: bills your hours, lowkey. Everything stays on this machine.

python -m lowkey               track this computer + island + dashboard on http://127.0.0.1:7777
python -m lowkey --demo        the bundled demo week (no tracking, no island)
python -m lowkey --no-island   track + dashboard, without the island
"""
import sys
import threading

from .config import CONFIG, DEMO, LIVE, MODEL, PORT
from .labeler import mark_personal, model_ok, refresh
from .server import make_server
from .tracker import track


def main():
    ready = "ready" if model_ok() else "not found, using keyword rules"
    print(f"lowkey {'(demo) ' if DEMO else ''}-> http://127.0.0.1:{PORT}   model: {MODEL} ({ready})")
    server = make_server()
    if not DEMO:
        threading.Thread(target=track, daemon=True).start()
        threading.Thread(target=refresh, daemon=True).start()
    island = None
    if not DEMO and "--no-island" not in sys.argv:
        try:
            from .island import Island
            island = Island(LIVE, {"personal": mark_personal}, CONFIG["me"]["currency"],
                            CONFIG["me"].get("daily_goal_h", 6))
        except ImportError:
            print("island off: pip install PySide6-Essentials to get it")
    if island:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        island.run()  # Qt needs the main thread (required on macOS)
    else:
        server.serve_forever()


if __name__ == "__main__":
    main()
