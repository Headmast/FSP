import json
import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4
import keyring
from .http import ClientError


class Connections:
    def __init__(self):
        self.directory=Path(os.environ.get('FSP_CONFIG_DIR',str(Path.home()/'.config/fsp')))
        self.path=self.directory/'connections.json'

    def read(self):
        try:
            return json.loads(self.path.read_text()) if self.path.exists() else {}
        except (OSError,ValueError):
            raise ClientError('Не удалось прочитать конфигурацию подключений.',2) from None

    def backend(self):
        try:
            backend=keyring.get_keyring()
            candidates=getattr(backend,'backends',[backend])
            for item in candidates:
                module=type(item).__module__
                if module in {'keyring.backends.macOS','keyring.backends.SecretService','keyring.backends.libsecret','keyring.backends.kwallet'} and item.priority>0:
                    return item
        except Exception:
            pass
        raise ClientError('Нет защищённого keyring. Включите macOS Keychain или Linux Secret Service/KWallet.',3)

    def save(self,values):
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,path=tempfile.mkstemp(dir=self.directory,prefix='connections-')
        try:
            with os.fdopen(fd,'w') as stream:
                json.dump(values,stream,ensure_ascii=False,indent=2)
            os.replace(path,self.path)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def login(self,name,server,token,identity):
        values=self.read()
        previous=values.get(name)
        backend=self.backend()
        reference=str(uuid4())
        try:
            backend.set_password('fsp-client',reference,token)
            values[name]={'server':server,'secret_ref':reference,'kind':identity['token_kind'],'role':identity['role']}
            self.save(values)
        except Exception:
            try: backend.delete_password('fsp-client',reference)
            except Exception: pass
            raise ClientError('Не удалось сохранить токен в защищённом хранилище.',3) from None
        if previous:
            try:backend.delete_password('fsp-client',previous['secret_ref'])
            except Exception:pass

    def load(self,name):
        value=self.read().get(name)
        if not value:
            raise ClientError('Подключение не найдено. Выполните fsp auth login.',3)
        try:
            token=self.backend().get_password('fsp-client',value['secret_ref'])
        except ClientError: raise
        except Exception:
            raise ClientError('Не удалось прочитать системное хранилище.',3) from None
        if not token:
            raise ClientError('Токен отсутствует. Подключитесь заново.',3)
        return value,token

    def logout(self,name):
        values=self.read()
        value=values.pop(name,None)
        if value:
            try:self.backend().delete_password('fsp-client',value['secret_ref'])
            except ClientError:raise
            except Exception:raise ClientError('Не удалось удалить секрет.',3) from None
            self.save(values)
