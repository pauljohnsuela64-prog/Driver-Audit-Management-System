"""Non-secret desktop endpoint configuration; never reads server dotenv files."""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import tempfile

from desktop.config import Config


class SettingsError(ValueError):pass


@dataclass(frozen=True)
class Endpoint:
    config: Config | None
    source: str
    error: str=''
    locked: bool=False


def settings_path(environ=None):
    env=os.environ if environ is None else environ
    root=env.get('LOCALAPPDATA')
    if not root:raise SettingsError('Windows user settings location is unavailable.')
    return Path(root)/'BHLI Audit'/'settings.json'


def validated(origin):
    if not isinstance(origin,str) or len(origin)>2048:raise SettingsError('Enter a valid HTTPS API origin, or HTTP on loopback only.')
    try:return Config(origin)
    except (ValueError,TypeError):raise SettingsError('Enter a valid HTTPS API origin, or HTTP on loopback only.') from None


def load_settings(path):
    try:
        with Path(path).open('rb') as stream:raw=stream.read(8193)
        if len(raw)>8192:raise ValueError()
        data=json.loads(raw)
        if (not isinstance(data,dict) or set(data)!={'version','api_url'} or
            type(data['version']) is not int or data['version']!=1):raise ValueError()
        return validated(data['api_url'])
    except (OSError,ValueError,TypeError,RecursionError):
        raise SettingsError('Saved connection settings are invalid or unreadable. Configure the service again.') from None


def save_settings(path,origin):
    config=validated(origin);path=Path(path);temporary=None
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.settings-',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name)
            json.dump({'version':1,'api_url':config.base_url},stream)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    except OSError:raise SettingsError('Connection settings could not be saved. Check your Windows profile permissions.') from None
    finally:
        if temporary and temporary.exists():
            try:temporary.unlink()
            except OSError:raise SettingsError('Temporary connection settings could not be removed. Contact your administrator.') from None
    return config


def resolve_settings(cli,environ,path,frozen):
    source='Command line' if cli is not None else 'Environment' if environ.get('DAMS_DESKTOP_API_URL') is not None else 'Saved settings'
    locked=source!='Saved settings'
    try:
        if source=='Command line':config=validated(cli)
        elif source=='Environment':config=validated(environ['DAMS_DESKTOP_API_URL'])
        elif path is not None and Path(path).exists():config=load_settings(path)
        else:return Endpoint(None,'Not configured') if frozen else Endpoint(Config(),'Developer default')
        return Endpoint(config,source,locked=locked)
    except (SettingsError,OSError):return Endpoint(None,source,'Service configuration is invalid or unavailable. Check the operator setting or configure the connection.',locked)
