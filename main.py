import sys

from PySide6.QtWidgets import QApplication

from app.ui import MainWindow


def main():
    if 2 <= len(sys.argv) <= 3 and sys.argv[1] in ("--sync-trades", "--sync-analytics", "--sync-cash"):
        from scripts.sync_trades import main as sync_trades
        from scripts.sync_analytics import main as sync_analytics
        from scripts.sync_cash import main as sync_cash
        return {
            "--sync-trades": sync_trades,
            "--sync-analytics": sync_analytics,
            "--sync-cash": sync_cash,
        }[sys.argv[1]](sys.argv[2] if len(sys.argv) == 3 else None)
    app = QApplication(sys.argv)
    app.setApplicationName("Portfolio Monitor")
    app.setApplicationDisplayName("Portfolio Monitor")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
