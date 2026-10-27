"""Developer-only fictional API fixture for manually inspecting the frozen client."""
import argparse
from getpass import GetPassWarning, getpass
from pathlib import Path
import subprocess
import warnings

from scripts.desktop_demo import demonstration


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,default=Path('dist/BHLIAudit/BHLIAudit.exe'))
    args=parser.parse_args()
    executable=args.executable.resolve(strict=True)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',GetPassWarning)
            first=getpass('Choose demo_admin password (15-128 characters): ')
            second=getpass('Choose separate demo_admin2 password (15-128 characters): ')
        with demonstration(first,second) as demo:
            first=second=None
            print('Fictional accounts: demo_admin and demo_admin2. Close the client to remove the temporary API/database.')
            subprocess.run([str(executable),'--api-url',demo.origin],check=True)
    except (KeyboardInterrupt,EOFError):
        print('Demo canceled.')
    except Exception:
        raise SystemExit('Demo failed. Use a local hidden-input terminal, separate valid passwords and a built client.') from None


if __name__=='__main__':
    main()
