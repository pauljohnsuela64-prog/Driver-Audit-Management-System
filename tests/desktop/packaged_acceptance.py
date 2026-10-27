"""Drive the real frozen client through native input against fictional loopback API.

No test hooks, credentials or backend are added to the distributed application.
Run with --executable dist/BHLIAudit/BHLIAudit.exe --output artifacts/desktop-phase3e.
"""
import argparse
from contextlib import ExitStack
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import secrets
import subprocess
from tempfile import TemporaryDirectory
import time

from scripts import desktop_demo
from tests.desktop.native_capture import capture

user=ctypes.windll.user32
user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
user.GetForegroundWindow.restype=w.HWND
user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
class Mouse(ctypes.Structure):
    _fields_=[('dx',w.LONG),('dy',w.LONG),('data',w.DWORD),('flags',w.DWORD),('time',w.DWORD),('extra',w.WPARAM)]
class Keyboard(ctypes.Structure):
    _fields_=[('vk',w.WORD),('scan',w.WORD),('flags',w.DWORD),('time',w.DWORD),('extra',w.WPARAM)]
class Union(ctypes.Union):_fields_=[('mouse',Mouse),('key',Keyboard)]
class Input(ctypes.Structure):_fields_=[('type',w.DWORD),('value',Union)]
class GuiInfo(ctypes.Structure):
    _fields_=[('size',w.DWORD),('flags',w.DWORD),('active',w.HWND),('focus',w.HWND),('capture',w.HWND),
              ('menu',w.HWND),('move',w.HWND),('caret',w.HWND),('caret_rect',w.RECT)]
user.SendInput.argtypes=[w.UINT,ctypes.POINTER(Input),ctypes.c_int]
user.GetWindowRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
user.SetForegroundWindow.argtypes=[w.HWND]
user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
_focused=None
_target_pid=0


def key(vk,up=False):
    value=Input(1,Union(key=Keyboard(vk,0,2 if up else 0,0,0)))
    if user.SendInput(1,ctypes.byref(value),ctypes.sizeof(value))!=1:raise RuntimeError('Native keyboard input unavailable')


def press(vk):
    key(vk);key(vk,True)
    time.sleep(.15)


def text(value):
    user.VkKeyScanW.argtypes=[w.WCHAR];user.VkKeyScanW.restype=ctypes.c_short
    for char in value:
        actual=w.DWORD();user.GetWindowThreadProcessId(user.GetForegroundWindow(),ctypes.byref(actual))
        assert actual.value==_target_pid,'Native keyboard target changed'
        mapped=user.VkKeyScanW(char);assert mapped!=-1
        flags=(mapped>>8)&7
        if char.isascii() and char.isalpha():flags=(flags&~1)|int(char.isupper() ^ bool(user.GetKeyState(0x14)&1))
        modifiers=[vk for bit,vk in ((1,0x10),(2,0x11),(4,0x12)) if flags&bit]
        try:
            for vk in modifiers:key(vk)
            key(mapped&255);key(mapped&255,True)
        finally:
            for vk in reversed(modifiers):key(vk,True)
        time.sleep(.004)


def wait(predicate,seconds=12):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=predicate()
        if result:return result
        time.sleep(.04)
    raise AssertionError('Packaged UI did not reach expected state')


def window(pid,title):
    found=[]
    callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    def visit(hwnd,_):
        process=w.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(process))
        if process.value==pid and user.IsWindowVisible(hwnd):
            buf=ctypes.create_unicode_buffer(512);user.GetWindowTextW(hwnd,buf,512)
            if buf.value==title:found.append(hwnd)
        return True
    user.EnumWindows(callback_type(visit),0)
    return found[0] if found else None


def children(hwnd):
    found=[]
    callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    user.EnumChildWindows(hwnd,callback_type(lambda child,_:found.append(child) or True),0)
    return len(found)


def activate(hwnd):
    user.ShowWindow(hwnd,9)
    user.SetWindowPos.argtypes=[w.HWND,w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.UINT]
    user.SetWindowPos(hwnd,w.HWND(-1),0,0,0,0,0x43);user.SetForegroundWindow(hwnd)
    time.sleep(.4)


def entry_centers(hwnd,path):
    from PIL import Image
    capture(hwnd,path)
    image=Image.open(path).convert('RGB');width,height=image.size
    raw=image.tobytes();groups=[];samples=[bytes.fromhex(color)*40 for color in ('64748B','0F766E')]
    for y in range(height):
        line=raw[y*width*3:(y+1)*width*3]
        spans=[(line.find(sample),line.rfind(sample)) for sample in samples if line.find(sample)>=0]
        first,last=max(spans,key=lambda pair:pair[1]-pair[0]) if spans else (-1,-1)
        if first>=0 and (last-first)//3+40>width*.25:
            if groups and groups[-1][1]==y-1:groups[-1]=(groups[-1][0],y,first//3,(last-first)//3+40)
            else:groups.append((y,y,first//3,(last-first)//3+40))
    groups=[group for group in groups if group[1]-group[0]<8]
    return [(x+length//2,(top+groups[i+1][1])//2) for i,(top,bottom,x,length) in enumerate(groups[:-1])
            if i%2==0 and 25<groups[i+1][0]-bottom<90
            and abs(groups[i+1][3]-length)<max(12,length*.1)]


def click(hwnd,point):
    global _focused,_target_pid
    activate(hwnd)
    expected=w.DWORD();actual=w.DWORD()
    user.GetWindowThreadProcessId(hwnd,ctypes.byref(expected))
    user.GetWindowThreadProcessId(user.GetForegroundWindow(),ctypes.byref(actual))
    _target_pid=expected.value
    rect=w.RECT();user.GetWindowRect(hwnd,ctypes.byref(rect));x,y=rect.left+point[0],rect.top+point[1]
    candidates=[];callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    def visit(child,_):
        box=w.RECT();user.GetWindowRect(child,ctypes.byref(box))
        if user.IsWindowVisible(child) and box.left<=x<box.right and box.top<=y<box.bottom:
            candidates.append(((box.right-box.left)*(box.bottom-box.top),child,box))
        return True
    user.EnumChildWindows(hwnd,callback_type(visit),0)
    assert candidates,'Native target control not found'
    _,target,box=min(candidates,key=lambda item:item[0]);_focused=target
    user.SetCursorPos(x,y);user.mouse_event(2,0,0,0,0);user.mouse_event(4,0,0,0,0)
    time.sleep(.3)


def logical(hwnd,x,y):
    rect=w.RECT();client=w.RECT();origin=w.POINT(0,0)
    user.GetWindowRect(hwnd,ctypes.byref(rect));user.GetClientRect(hwnd,ctypes.byref(client));user.ClientToScreen(hwnd,ctypes.byref(origin))
    scale=user.GetDpiForWindow(hwnd)/96
    return (round(origin.x-rect.left+x*scale),round(origin.y-rect.top+y*scale))


def client_size(hwnd):
    rect=w.RECT();user.GetClientRect(hwnd,ctypes.byref(rect));scale=user.GetDpiForWindow(hwnd)/96
    return rect.right/scale,rect.bottom/scale


def full_workflow(root,process,demo,password,events,output):
    from desktop.models import AuditQuery
    from zipfile import ZipFile
    import xml.etree.ElementTree as ET
    def seen(method,path):return sum(1 for event in events if event[0:2]==(method,path) and event[2] in (200,201,204))
    click(root,logical(root,340,216))
    fields=wait(lambda:entry_centers(root,output/'04-packaged-create.png'))
    click(root,fields[0]);text('Packaged Acceptance Driver')
    press(9);press(9);press(9);text('Fictional Packaged Station')
    press(9);text('000777');press(9);text('Packaged fictional notes')
    width,height=client_size(root);before=seen('POST','/audits')
    click(root,logical(root,width-120,height-76))
    wait(lambda:seen('POST','/audits')>before)
    probe=desktop_demo.ApiClient(desktop_demo.Config(demo.origin));identity=probe.sign_in('demo_admin',password)
    try:
        record=probe.list_audits(identity.token,AuditQuery(driver_name='Packaged Acceptance Driver')).items[0]
        wait(lambda:seen('GET',f'/audits/{record.id}')>0)
        time.sleep(.4);capture(root,output/'05-packaged-details.png')
        click(root,logical(root,334,height-76))
        fields=wait(lambda:entry_centers(root,output/'06-packaged-edit.png'))
        click(root,fields[0]);key(0x11)
        try:press(0x41)
        finally:key(0x11,True)
        text('Packaged Edited Driver')
        before=seen('PATCH',f'/audits/{record.id}')
        click(root,logical(root,width-120,height-76))
        wait(lambda:seen('PATCH',f'/audits/{record.id}')>before)
        time.sleep(.5)
        updated=probe.get_audit(identity.token,record.id)
        assert updated.driver_name=='Packaged Edited Driver' and updated.audited_by_name==record.audited_by_name
        click(root,logical(root,462,height-76))
        wait(lambda:seen('GET',f'/audits/{record.id}/history')>0)
        time.sleep(.4);capture(root,output/'07-packaged-history.png')
        assert probe.audit_history(identity.token,record.id).total==2
        click(root,logical(root,width-94,124))
        time.sleep(.5)
        click(root,logical(root,width-94,height-76))
        dialog=wait(lambda:window(process.pid,'Delete this audit?'))
        box=w.RECT();user.GetWindowRect(dialog,ctypes.byref(box))
        capture(dialog,output/'08-packaged-delete.png')
        click(dialog,(int((box.right-box.left)*.75),int((box.bottom-box.top)*.9)))
        wait(lambda:seen('DELETE',f'/audits/{record.id}')>0)
        assert [event.action for event in probe.audit_history(identity.token,record.id,include_deleted=True).items]==['CREATE','UPDATE','DELETE']
        time.sleep(.7)
        click(root,logical(root,490,164))
        dialog=wait(lambda:window(process.pid,'Export all matching audits'))
        box=w.RECT();user.GetWindowRect(dialog,ctypes.byref(box))
        click(dialog,(int((box.right-box.left)*.75),int((box.bottom-box.top)*.9)))
        save=wait(lambda:window(process.pid,'Export audits to Excel'))
        callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
        user.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
        def filename_fields():
            controls=[]
            def visit(child,_):
                cls=ctypes.create_unicode_buffer(128);value=ctypes.create_unicode_buffer(2048)
                user.GetClassNameW(child,cls,128)
                if cls.value=='Edit' and user.IsWindowVisible(child):
                    user.SendMessageW(child,0xD,2048,ctypes.cast(value,ctypes.c_void_p).value)
                    if value.value.strip('"').startswith('DAMS-audits-'):controls.append(child)
                return True
            user.EnumChildWindows(save,callback_type(visit),0)
            return controls
        controls=wait(filename_fields)
        assert len(controls)==1,'Native save filename field is ambiguous'
        destination=output/f'packaged-export-{time.time_ns()}.xlsx'
        edit_box=w.RECT();save_box=w.RECT()
        user.GetWindowRect(controls[0],ctypes.byref(edit_box));user.GetWindowRect(save,ctypes.byref(save_box))
        click(save,((edit_box.left+edit_box.right)//2-save_box.left,(edit_box.top+edit_box.bottom)//2-save_box.top))
        key(0x11)
        try:press(0x41)
        finally:key(0x11,True)
        text(str(destination))
        def filename_ready():
            buffer=ctypes.create_unicode_buffer(2048)
            user.SendMessageW(controls[0],0xD,2048,ctypes.cast(buffer,ctypes.c_void_p).value)
            return buffer.value==str(destination)
        wait(filename_ready)
        def save_buttons():
            buttons=[]
            def visit(child,_):
                cls=ctypes.create_unicode_buffer(128);label=ctypes.create_unicode_buffer(128)
                user.GetClassNameW(child,cls,128)
                if cls.value=='Button':
                    user.SendMessageW(child,0xD,128,ctypes.cast(label,ctypes.c_void_p).value)
                    if label.value.replace('&','').lower()=='save':buttons.append(child)
                return True
            user.EnumChildWindows(save,callback_type(visit),0);return buttons
        buttons=wait(save_buttons)
        assert len(buttons)==1
        user.SendMessageW(buttons[0],0xF5,0,0)
        wait(lambda:not window(process.pid,'Export audits to Excel'))
        wait(destination.exists,20)
        with ZipFile(destination) as archive:
            sheet=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            assert len(sheet.findall('s:sheetData/s:row',ns))==61
            assert not sheet.findall('.//s:f',ns)
            assert '000123' in ''.join(sheet.itertext())
        time.sleep(.4);capture(root,output/'09-packaged-export.png')
        click(root,logical(root,width-168,40))
        # Select the real native popup's second row without reactivating its owner.
        menus=[]
        def menu_window(hwnd,_):
            pid=w.DWORD();cls=ctypes.create_unicode_buffer(128)
            user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid));user.GetClassNameW(hwnd,cls,128)
            if pid.value==process.pid and cls.value=='#32768' and user.IsWindowVisible(hwnd):menus.append(hwnd)
            return True
        user.EnumWindows(ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)(menu_window),0)
        assert len(menus)==1,'Theme popup not visible'
        box=w.RECT();user.GetWindowRect(menus[0],ctypes.byref(box))
        user.SetCursorPos((box.left+box.right)//2,int(box.top+(box.bottom-box.top)*.75))
        user.mouse_event(2,0,0,0,0);user.mouse_event(4,0,0,0,0)
        time.sleep(1);capture(root,output/'10-packaged-dark.png')
        user.ShowWindow(root,3)
        time.sleep(.7);capture(root,output/'11-packaged-maximized.png')
        user.ShowWindow(root,9)
        user.MoveWindow.argtypes=[w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.BOOL]
        user.MoveWindow(root,30,30,1200,900,True)
        time.sleep(.7);capture(root,output/'12-packaged-compact.png')
        return {'create':True,'edit':True,'delete':True,'history':True,'attribution_preserved':True,
                'excel_export':str(destination),'exported_records':60}
    finally:probe.logout(identity.token)


def run(executable,output,full=False,smoke=False,https=False):
    output.mkdir(parents=True,exist_ok=True);events=[]
    factory=desktop_demo.create_app
    def observed(*args,**kwargs):
        api=factory(*args,**kwargs)
        @api.middleware('http')
        async def record(request,call_next):
            response=await call_next(request)
            events.append((request.method,request.url.path,response.status_code))
            return response
        return api
    desktop_demo.create_app=observed
    passwords=(secrets.token_urlsafe(24),secrets.token_urlsafe(24))
    process=None
    def stop():
        if process and process.poll() is None:
            save=window(process.pid,'Export audits to Excel')
            if save:user.PostMessageW(save,0x10,0,0);time.sleep(.2)
            (output/'failure-events.json').write_text(json.dumps(events),encoding='utf-8')
            dialog=window(process.pid,'API connection')
            if dialog:capture(dialog,output/'failure-dialog.png')
            hwnd=window(process.pid,'BHLI Audit')
            if hwnd:
                capture(hwnd,output/'failure-state.png')
                user.PostMessageW(hwnd,0x10,0,0)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
    try:
        if https:
            from tests.desktop.tls_demo import tls_demonstration
            demonstration=tls_demonstration
        else:demonstration=desktop_demo.demonstration
        with demonstration(*passwords) as demo, TemporaryDirectory(prefix='dams-packaged-profile-') as profile, ExitStack() as cleanup:
            env=dict(os.environ,LOCALAPPDATA=profile,PATH=os.path.join(os.environ['SystemRoot'],'System32'))
            for name in ('PYTHONPATH','PYTHONHOME','DAMS_DESKTOP_API_URL','DATABASE_URL','DAMS_PROD_RUNTIME_URL'):
                env.pop(name,None)
            events.clear()
            if smoke:env['DAMS_DESKTOP_API_URL']=demo.origin
            process=subprocess.Popen([str(executable)],cwd=profile,env=env)
            cleanup.callback(stop)
            root=wait(lambda:window(process.pid,'BHLI Audit'))
            if smoke:
                wait(lambda:children(root)>20);time.sleep(1)
                capture(root,output/'packaged-ci-login.png')
                user.PostMessageW(root,0x10,0,0);process.wait(timeout=12)
                assert process.returncode==0
                report={'packaged_launch_only':True,'exit_code':0,'external_python_path':False,'api_isolated':True,
                    'authentication_and_workflows':'Verified by separate native full acceptance, not this CI launch smoke'}
                (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report));return
            dialog=wait(lambda:window(process.pid,'API connection'))
            activate(dialog)
            fields=wait(lambda:entry_centers(dialog,output/'01-first-launch-connection.png'))
            login_children=children(root)
            click(dialog,fields[0]);text(demo.origin);time.sleep(.3);capture(dialog,output/'02-connection-entered.png')
            fields=entry_centers(dialog,output/'02-connection-entered.png');click(dialog,fields[1])
            wait(lambda:('GET','/health',200) in events)
            time.sleep(.4);box=w.RECT();user.GetWindowRect(dialog,ctypes.byref(box))
            click(dialog,(int((box.right-box.left)*.75),int((box.bottom-box.top)*.9)))
            wait(lambda:not window(process.pid,'API connection'))
            wait(lambda:children(root)>=login_children)
            time.sleep(.6)
            settings=Path(profile)/'BHLI Audit/settings.json'
            saved_settings=json.loads(settings.read_text())
            assert saved_settings=={'version':1,'api_url':demo.origin},(saved_settings,{'version':1,'api_url':demo.origin})
            activate(root)
            fields=wait(lambda:entry_centers(root,output/'02-packaged-login.png') if children(root)>=login_children else None)
            assert len(fields)>=2
            click(root,fields[0]);text('demo_admin');click(root,fields[1]);text(passwords[0]);press(13)
            wait(lambda:('GET','/auth/me',200) in events)
            wait(lambda:('GET','/audits',200) in events)
            time.sleep(.5);capture(root,output/'03-packaged-dashboard.png')
            workflow=full_workflow(root,process,demo,passwords[0],events,output) if full else {}
            user.PostMessageW(root,0x10,0,0);process.wait(timeout=12)
            assert process.returncode==0
            report={'executable':str(executable),'first_launch_config':True,'normal_admin_login':True,
                'dashboard_rest_read':True,'exit_code':process.returncode,'external_python_path':False,
                'api_isolated':True,'trusted_test_https':https,'events':events,**workflow}
            (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report))
    finally:
        desktop_demo.create_app=factory
        if process and process.poll() is None:
            hwnd=window(process.pid,'BHLI Audit')
            if hwnd:user.PostMessageW(hwnd,0x10,0,0)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--executable',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--full',action='store_true');parser.add_argument('--smoke',action='store_true');parser.add_argument('--https',action='store_true')
    args=parser.parse_args();run(args.executable.resolve(),args.output.resolve(),args.full,args.smoke,args.https)
