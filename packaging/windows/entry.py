"""Frozen launch entry: no console, no backend imports, visible safe failures."""
def show_error():
    import ctypes
    ctypes.windll.user32.MessageBoxW(None,
        'BHLI Audit could not start (BHLI-START-01). Contact your administrator or reinstall the application.',
        'BHLI Audit — startup error',0x10)


def run():
    try:
        from desktop.__main__ import main
        main()
    except SystemExit as error:
        if error.code in (0,None):return 0
        show_error();return 2
    except Exception:
        show_error();return 1
    return 0


if __name__=='__main__':raise SystemExit(run())
