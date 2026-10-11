from urllib.parse import urlsplit
import httpx


class ClientError(Exception):
    def __init__(self,message,exit_code=5):
        self.exit_code=exit_code
        super().__init__(message)


def server_url(value):
    parsed=urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        raise ClientError('Укажите адрес сервера без credentials, query и fragment.',2)
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in {'127.0.0.1','localhost','::1'}):
        raise ClientError('Нужен HTTPS; HTTP разрешён только для localhost.',2)
    return value.rstrip('/')


class FspClient:
    def __init__(self,server,token,transport=None):
        self.server=server_url(server)
        self.client=httpx.Client(headers={'Authorization':'Bearer '+token,'Accept':'application/json'},
            timeout=15,follow_redirects=False,trust_env=False,transport=transport)

    def close(self):
        self.client.close()

    def request(self,method,path,params=None,data=None,pdf=False):
        try:
            response=self.client.request(method,self.server+'/api/v1/'+path,params=params,json=data)
        except httpx.HTTPError:
            raise ClientError('Не удалось соединиться с сервером. Проверьте адрес и доступность.') from None
        if 300 <= response.status_code < 400:
            raise ClientError('Перенаправление отклонено. Подключитесь к конечному адресу заново.')
        if response.status_code>=400:
            codes={400:2,401:3,403:3,404:4,409:4,410:4,405:2}
            try:
                error=response.json()['error']
                message=str(error.get('message','Ошибка API'))[:200]
                code=str(error.get('code','ERROR'))[:60]
            except (ValueError,KeyError,TypeError):
                message,code='Ошибка сервера','HTTP_'+str(response.status_code)
            raise ClientError(code+': '+message,codes.get(response.status_code,5))
        if pdf:
            if not response.content.startswith(b'%PDF'):
                raise ClientError('Сервер не вернул PDF.')
            return response.content
        try:
            body=response.json()
            if not isinstance(body,dict) or 'data' not in body or 'meta' not in body:
                raise ValueError
            return body
        except (ValueError,TypeError):
            raise ClientError('Ответ сервера не соответствует API v1.') from None

    def get(self,path,**params):
        return self.request('GET',path,params={k:v for k,v in params.items() if v is not None})
