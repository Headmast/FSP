import argparse
import getpass
import json
import sys
from pathlib import Path
from .config import Connections
from .http import FspClient,ClientError,server_url


def identifier(value):
    if not value.isascii() or not value.isdecimal() or not 0<int(value)<2**63:
        raise argparse.ArgumentTypeError('Нужен положительный ASCII ID.')
    return int(value)


def parser():
    p=argparse.ArgumentParser(prog='fsp',description='FSP CLI · демонстрационные данные')
    p.add_argument('--connection',default='default')
    p.add_argument('--json',action='store_true')
    p.add_argument('--version',action='version',version='fsp-client 0.1.0')
    groups=p.add_subparsers(dest='group',required=True)
    def group(name):return groups.add_parser(name).add_subparsers(dest='action',required=True)
    def command(sub,name,path=None,id=False,list=False,pdf=False):
        cmd=sub.add_parser(name)
        cmd.add_argument('--json',action='store_true',default=argparse.SUPPRESS)
        if path is not None:cmd.set_defaults(path=path)
        if id:cmd.add_argument('id',type=identifier)
        if list:
            cmd.add_argument('--limit',type=int,default=20);cmd.add_argument('--offset',type=int,default=0)
        if pdf:
            cmd.add_argument('--output',required=True);cmd.add_argument('--with-contacts',action='store_true')
        return cmd
    auth=group('auth');login=command(auth,'login');login.add_argument('--server',required=True)
    login.add_argument('--connection',default=argparse.SUPPRESS)
    command(auth,'status');command(auth,'logout')
    pme=groups.add_parser('me');pme.set_defaults(path='me')
    pcat=groups.add_parser('catalog');pcat.set_defaults(path='catalog')
    profile=group('profile');command(profile,'show','me/profile');command(profile,'private','me/profile/private')
    command(profile,'resume','me/profile/resume.pdf',pdf=True)
    assessments=group('assessments');command(assessments,'list','me/assessments',list=True)
    command(assessments,'result','me/assessments/{id}/result',id=True)
    command(group('achievements'),'show','me/achievements')
    invitations=group('invitations');command(invitations,'list','invitations',list=True)
    command(invitations,'show','invitations/{id}',id=True);command(invitations,'contacts','invitations/{id}/contacts',id=True)
    command(group('company'),'show','me/company')
    needs=group('needs');command(needs,'list','needs',list=True);command(needs,'show','needs/{id}',id=True)
    candidates=group('candidates');search=command(candidates,'search','candidates',list=True)
    for name in ['grade','skill','fsp-status']:search.add_argument('--'+name)
    search.add_argument('--need-id',type=identifier)
    show=command(candidates,'show','candidates/{id}',id=True);show.add_argument('--need-id',type=identifier)
    command(candidates,'proofs','candidates/{id}/proofs',id=True,list=True)
    command(candidates,'private','candidates/{id}/private',id=True)
    command(candidates,'resume','candidates/{id}/resume.pdf',id=True,pdf=True)
    command(group('mcp'),'serve')
    return p


def output(value,json_mode):
    if json_mode:
        print(json.dumps(value,ensure_ascii=False,separators=(',',':')))
    else:
        print(json.dumps(value.get('data',value),ensure_ascii=False,indent=2))
        if value.get('meta',{}).get('data_mode')=='demo':
            print('Демонстрационные данные · API v1',file=sys.stderr)


def run(args):
    config=Connections()
    if args.group=='auth' and args.action=='logout':
        config.logout(args.connection)
        output({'data':{'disconnected':True}},args.json)
        return
    if args.group=='auth' and args.action=='login':
        server=server_url(args.server)
        token=getpass.getpass('Токен из веб-кабинета: ')
        api=FspClient(server,token)
        try:
            identity=api.get('me')['data']
            config.login(args.connection,server,token,identity)
            output({'data':identity},args.json)
        finally:api.close()
        return
    connection,token=config.load(args.connection)
    api=FspClient(connection['server'],token)
    try:
        if args.group=='mcp':
            from .mcp import serve
            serve(api)
            return
        if args.group=='auth':
            output(api.get('me'),args.json)
            return
        path=args.path.format(id=getattr(args,'id',None))
        params={name:getattr(args,name,None) for name in ['limit','offset','grade','skill','fsp_status','need_id']}
        if getattr(args,'output',None):
            data=api.request('GET',path,params={'with_contacts':str(args.with_contacts).lower()},pdf=True)
            try:
                with Path(args.output).open('xb') as stream:stream.write(data)
            except OSError:
                raise ClientError('Не удалось записать PDF: проверьте путь; существующий файл не перезаписывается.',2) from None
            output({'data':{'saved':args.output}},args.json)
        else:
            output(api.get(path,**params),args.json)
    finally:api.close()


def main():
    args=parser().parse_args()
    try:run(args)
    except ClientError as exc:
        print(str(exc),file=sys.stderr)
        return exc.exit_code
    except (EOFError,KeyboardInterrupt):
        print('Операция прервана.',file=sys.stderr)
        return 2
    return 0


if __name__=='__main__':sys.exit(main())
