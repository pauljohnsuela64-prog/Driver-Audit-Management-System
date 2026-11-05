"""Windowless offline entry. No server, credentials or technical traceback UI."""


def start():
    from desktop.offline.__main__ import main
    main()


def show_error():
    import ctypes
    ctypes.windll.user32.MessageBoxW(
        None,
        'BHLI Audit Offline could not start (BHLI-OFFLINE-START-01). '
        'If it is already running, use its existing window. Otherwise check your '
        'Windows user profile. Your local database has not been reset or removed.',
        'BHLI Audit Offline — startup error', 0x10,
    )


def run():
    try:
        start()
    except SystemExit as error:
        if error.code in (0, None):
            return 0
        show_error()
        return 2
    except Exception:
        show_error()
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
