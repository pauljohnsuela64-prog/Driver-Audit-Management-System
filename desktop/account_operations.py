"""Windows account policy, separate from the backend's broader ADMIN powers."""
from dataclasses import dataclass
from threading import Lock
from desktop.api import ApiError

_scan_lock=Lock()


def desktop_sign_in(client,username,password):
    result=client.sign_in(username,password)
    if result.user.role=='ADMIN':
        return result
    message='This Windows application requires an HR administrator account.'
    try:
        client.logout(result.token)
    except Exception:
        message+=' Signed out locally; server sign-out could not be confirmed and the session may remain until expiry.'
    raise ApiError(403,message=message)


class ScanCancelled(Exception):
    pass


def list_admins(client,token,cancelled):
    """Filter every backend page, without exposing legacy employee data to views."""
    # A cancelled view may still have an HTTP page in flight. Serialize scans
    # across theme rebuilds, then check cancellation before making another call.
    with _scan_lock:
        return _admin_pages(client,token,cancelled)


def _admin_pages(client,token,cancelled):
    admins={}
    for number in range(1,10001):
        if cancelled.is_set():raise ScanCancelled()
        page=client.list_users(token,number)
        if cancelled.is_set():raise ScanCancelled()
        if page.page!=number or page.page_size!=100:
            raise ApiError(502,message='The administrator list could not be completed. Refresh to try again.')
        for user in page.items:
            if user.role=='ADMIN':admins[user.id]=user
            else:admins.pop(user.id,None)
        if number*100>=page.total:
            return tuple(sorted(admins.values(),key=lambda user:user.id))
    raise ApiError(502,message='The administrator list is incomplete. Contact the service administrator.')


@dataclass(repr=False)
class AccountAction:
    kind: str
    target_id: int | None = None
    pending: bool = True
    message: str = ''
    uncertain: bool = False
    failed: bool = False


def target_admin(client,token,actor_id,target_id):
    if actor_id==target_id:
        raise ApiError(409,message='Use Change My Password for your own account; you cannot disable yourself.')
    target=client.get_user(token,target_id)
    if target.role!='ADMIN':
        raise ApiError(403,message='This account is not an administrator. Refresh the account list.')
    return target


def account_error(error):
    return {'username_exists':'That username is already in use. Refresh before adding another account.',
            'last_admin':'The last active administrator cannot be disabled.',
            'self_access_change':'You cannot disable your own account.',
            'self_reset':'Use Change My Password for your own account.',
            'access_conflict':'Account access changed. Refresh and confirm again.',
            'password_reuse':'Choose a password different from your current password.'}.get(error.code,str(error))
