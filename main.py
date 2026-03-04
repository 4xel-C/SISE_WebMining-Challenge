from app.collector import KeyboardListener, MouseListener
from app.models import create_engine, create_tables, get_session

if __name__ == "__main__":
    # Create tables if they don't exist
    create_tables()

    # Start keyboard and mouse listener
