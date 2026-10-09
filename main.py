import argparse
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.ui import MainWindow
from app.paths import create_portfolio_directory, validate_database_path

VERSION = "1.0.0"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run Portfolio Monitor from source.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--database", type=Path,
                           help="Use a SQLite file in a subfolder under data/")
    selection.add_argument("--new-portfolio", action="store_true",
                           help="Create an empty portfolio in data/YYYYMMDD_<12-hex-digits>/")
    args = parser.parse_args(argv)
    try:
        database_path = (create_portfolio_directory() / "portfolio.sqlite3" if args.new_portfolio
                         else validate_database_path(args.database) if args.database is not None else None)
    except ValueError as exc:
        parser.error(str(exc))
    if sys.platform == "win32":
        # Give source launches their own taskbar identity and application icon.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CustomIBMonitor.PortfolioMonitor")
    app = QApplication([sys.argv[0]])
    app.setApplicationVersion(VERSION)
    app.setApplicationName("Portfolio Monitor")
    app.setApplicationDisplayName("Portfolio Monitor")
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "app" / "assets" / "doge.ico")))
    window = MainWindow(database_path=database_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
