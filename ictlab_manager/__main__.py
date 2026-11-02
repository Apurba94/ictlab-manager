"""Start the app: python -m ictlab_manager [data.db] [--port 8028]"""
import sys

from .fieldkit import main_cli
from .web import create_app

sys.exit(main_cli(create_app, "ictlab.db", 8028, sys.argv))
