import time

from app.models import create_engine, create_tables, get_session
from app.services import RegisterService

if __name__ == "__main__":
    # Create tables if they don't exist
    create_tables()

    # Initialize sergices to register events for user "axel" doing "work"
    service = RegisterService(username="axel", activity_label="train")

    # start services
    service.start()

    # 10 minutes de sleep
    time.sleep(600)

    # stop services
    service.stop()
