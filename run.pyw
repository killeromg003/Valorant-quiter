"""Launch without a console window. Run with pythonw.exe (double-click works)."""

import sys
import traceback


def _report(detail: str) -> None:
    try:
        from quiter.config import APP_DIR

        APP_DIR.mkdir(parents=True, exist_ok=True)
        (APP_DIR / "crash.log").write_text(detail, encoding="utf-8")
    except Exception:
        pass
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            detail[-1500:],
            "VALORANT Quiter failed to start",
            0x10,  # MB_ICONERROR
        )
    except Exception:
        pass


try:
    from quiter.main import main

    raise SystemExit(main())
except SystemExit:
    raise
except BaseException:
    detail = traceback.format_exc()
    _report(detail)
    raise
