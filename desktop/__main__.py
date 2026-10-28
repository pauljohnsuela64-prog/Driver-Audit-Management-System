import argparse
import os
import sys
from desktop.api import ApiClient
from desktop.config import Config


def main(argv=None):
    parser=argparse.ArgumentParser(description='BHLI Audit Windows desktop')
    parser.add_argument('--api-url',default=None,
                        help='HTTPS API origin, or HTTP on loopback')
    args=parser.parse_args(argv)
    from desktop.settings import settings_path,resolve_settings,SettingsError
    from desktop.resources import set_app_identity,running_mutex,release_mutex
    try:path=settings_path()
    except SettingsError:path=None
    endpoint=resolve_settings(args.api_url,os.environ,path,getattr(sys,'frozen',False))
    import customtkinter as ctk
    from desktop.app import Application
    ctk.set_appearance_mode('Light')
    set_app_identity()
    handle=running_mutex()
    try:
        app=Application(ApiClient(endpoint.config or Config()),endpoint,path)
        if endpoint.config is None:app.after(100,app.open_connection)
        app.mainloop()
    finally:release_mutex(handle)


if __name__=='__main__':
    main()
