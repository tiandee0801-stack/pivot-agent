"""Code-free visitor spaces. Each browser gets an isolated dataset and media root."""
from pathlib import Path
from http.cookies import SimpleCookie
import secrets, hashlib, threading, time, sqlite3
from mobile_backend import Pairing, VideoManager
from engine import dispatch, RequestError

class GuestSpaces(Pairing):
    def __init__(self, root, origin=''):
        super().__init__()
        self.origin=origin.rstrip('/')
        self.root=Path(root).expanduser().resolve(); self.root.mkdir(parents=True,exist_ok=True)
        self.managers={}; self.lock=threading.Lock(); self.video_lock=threading.Lock()
        self.guest=True
    @staticmethod
    def token(cookie):
        try:
            c=SimpleCookie(cookie or '');value=c['pivot_space'].value if 'pivot_space' in c else ''
            return value if len(value)==48 and all(x in '0123456789abcdef' for x in value) else ''
        except Exception:return ''
    def authenticated(self,cookie):
        return bool(self.token(cookie))
    def create(self):
        return secrets.token_hex(24)
    def cookie(self,token):
        return 'pivot_space='+token+'; Path=/; HttpOnly; SameSite=Lax; Max-Age='+('604800' if token else '0')+('; Secure' if self.origin else '')
    def workspace(self,token):
        if self.token('pivot_space='+str(token))!=token or not token:
            raise RequestError('体验空间已失效，请刷新页面。','invalid_space',401)
        ident=hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            if ident not in self.managers:
                if len(self.managers)>=40:raise RequestError('当前体验人数较多，请稍后重试。','capacity',503)
                db=self.root/ident/'workspace.sqlite3';db.parent.mkdir(parents=True,exist_ok=True)
                dispatch(str(db),'GET','/api/state',{})
                with sqlite3.connect(db) as connection:
                    import json
                    row=connection.execute('SELECT data FROM workspace WHERE id=1').fetchone()
                    ctx=json.loads(row[0]);ctx['realDeviceOnly']=True
                    connection.execute('UPDATE workspace SET data=? WHERE id=1',(json.dumps(ctx,ensure_ascii=False),))
                    from experience import initialize
                    initialize(connection)
                vm=VideoManager(db);vm.lock=self.video_lock
                self.managers[ident]=(str(db),vm)
            return self.managers[ident]
    def logout(self,cookie):pass
