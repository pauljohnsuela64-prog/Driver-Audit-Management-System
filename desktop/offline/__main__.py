"""Local-only launch; no API, server configuration, login or dotenv loading."""
import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description='BHLI Audit Offline — fictional development testing only')
    parser.parse_args(argv)
    from desktop.offline.identity import database_path, set_app_identity, running_mutex, release_mutex
    path = database_path()
    import customtkinter as ctk
    from desktop.offline.app import OfflineApplication
    ctk.set_appearance_mode('Light')
    set_app_identity()
    handle = running_mutex()
    app = None
    try:
        app = OfflineApplication(db_path=path)
        app.mainloop()
    finally:
        # Even an unexpected mainloop exit must drain admitted local writes.
        if app is not None:
            app.worker.close()
            app.worker.join()
        release_mutex(handle)


if __name__ == '__main__':
    main()
