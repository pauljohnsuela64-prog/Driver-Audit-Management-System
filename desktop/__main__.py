import argparse
import os
from desktop.api import ApiClient
from desktop.config import Config


def main():
    parser=argparse.ArgumentParser(description='BHLI Audit Windows desktop')
    parser.add_argument('--api-url',default=os.getenv('DAMS_DESKTOP_API_URL','http://127.0.0.1:8000'),
                        help='HTTPS API origin, or HTTP on loopback')
    args=parser.parse_args()
    try:
        config=Config(args.api_url)
    except ValueError:
        parser.exit(2,'Invalid service configuration. Use HTTPS, or HTTP on loopback only.\n')
    import customtkinter as ctk
    from desktop.app import Application
    ctk.set_appearance_mode('Light')
    Application(ApiClient(config)).mainloop()


if __name__=='__main__':
    main()
