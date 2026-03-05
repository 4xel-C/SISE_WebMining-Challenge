import time

from app.models import create_engine, create_tables, get_session
from app.services import RegisterService

if __name__ == "__main__":
    # Create tables if they don't exist
    create_tables()

    # Initialize services to register events for user "axel" doing "train"
    service = RegisterService(username="axel", activity_label="train")

    # start services
    service.start()
    print("[main] Enregistrement en cours — Ctrl+C pour arrêter.")

    try:
        # 10 minutes de sleep
        time.sleep(600)
    except KeyboardInterrupt:
        print("\n[main] Interruption reçue.")
    finally:
        service.stop()
        print("[main] Session terminée et sauvegardée.")
