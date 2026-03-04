from __future__ import annotations

from src.app_runtime import main as application_main


class AppRunner:
    """Thin app entrypoint. Keep app.py minimal."""

    @staticmethod
    def run() -> None:
        application_main()


def main() -> None:
    AppRunner.run()


if __name__ == "__main__":
    main()
