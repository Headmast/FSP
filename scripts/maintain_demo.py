#!/usr/bin/env python3
"""Cron watchdog for the existing FSP release and its public status page. Standard library only."""
import argparse
import base64
import fcntl
import ftplib
import io
import json
import os
import re
import shlex
import signal
import ssl
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

PORT = 8011
URL_PATTERN = r'https://[a-z0-9.-]+(?:pinggy-free\.link|pinggy\.link|pinggy\.net)'


def valid_url(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == 'https' and not parsed.username and not parsed.password
                and parsed.port is None and parsed.path in ('', '/') and not parsed.query and not parsed.fragment
                and bool(re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:pinggy-free\.link|pinggy\.link|pinggy\.net)', parsed.hostname or '')))
    except (ValueError, TypeError):
        return False



def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else (default or {})


def atomic_write(path, data, mode=0o600):
    temporary = path.with_name(path.name + '.next')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    os.fchmod(fd, mode)
    with os.fdopen(fd, 'w') as handle:
        handle.write(data)
    os.replace(temporary, path)


def get_version(url, local=False):
    headers = {'X-Forwarded-Proto': 'https'} if local else {}
    request = urllib.request.Request(url.rstrip('/') + '/version/', headers=headers)
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.load(response)['commit']


def check_readiness(url, local=False):
    """Read schema health and render the entry form without changing app data."""
    headers = {'X-Forwarded-Proto': 'https'} if local else {}
    try:
        request = urllib.request.Request(url.rstrip('/') + '/health/', headers=headers)
        with urllib.request.urlopen(request, timeout=8) as response:
            if json.load(response).get('status') != 'ok':
                return False
        request = urllib.request.Request(url.rstrip('/') + '/accounts/login/', headers=headers)
        with urllib.request.urlopen(request, timeout=8) as response:
            return (response.headers.get_content_type() == 'text/html'
                    and b'data-testid="login-form"' in response.read(262144))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def version_matches(url, commit, local=False):
    try:
        return get_version(url, local=local) == commit
    except (OSError, ValueError, KeyError):
        return False


def app_ready(url, commit, local=False):
    return version_matches(url, commit, local) and check_readiness(url, local)


def owned_pid(root, name):
    file = root / 'shared/pids' / (name + '.pid')
    if not file.exists():
        return None
    pid = int(file.read_text())
    if pid <= 1:
        raise RuntimeError('Invalid managed PID')
    try:
        cmd = Path(f'/proc/{pid}/cmdline').read_bytes()
        if not cmd:
            return None
        if name == 'mvp-pinggy':
            owned = b'free.pinggy.io' in cmd and b'0:127.0.0.1:8011' in cmd and b'ssh' in cmd
        else:
            cwd = Path(f'/proc/{pid}/cwd').resolve()
            owned = b'gunicorn' in cmd and root / 'releases' in cwd.parents
        if not owned:
            raise RuntimeError('PID does not belong to managed process')
        return pid
    except FileNotFoundError:
        return None


def stop_owned(root, name):
    pid = owned_pid(root, name)
    if pid is None:
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        try:
            if not Path(f'/proc/{pid}/cmdline').read_bytes():
                return
        except FileNotFoundError:
            return
        time.sleep(.1)
    raise RuntimeError('Managed process did not stop')


def launch(root, name, args, **kwargs):
    with (root / 'shared/logs' / (name + '.log')).open('w' if name == 'mvp-pinggy' else 'a') as log:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   start_new_session=True, **kwargs)
    atomic_write(root / 'shared/pids' / (name + '.pid'), str(process.pid))
    return process


def start_tunnel(root):
    stop_owned(root, 'mvp-pinggy')
    process = launch(root, 'mvp-pinggy', ['ssh', '-F', '/dev/null', '-T', '-p', '443',
        '-o', 'StrictHostKeyChecking=accept-new', '-o', 'IdentityFile=none', '-o', 'IdentityAgent=none',
        '-o', 'IdentitiesOnly=yes', '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=2',
        '-o', 'ExitOnForwardFailure=yes', '-R', '0:127.0.0.1:8011', 'free.pinggy.io', 'x:https'])
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError('Tunnel exited')
        urls = re.findall(URL_PATTERN, (root / 'shared/logs/mvp-pinggy.log').read_text())
        if urls and valid_url(urls[-1]):
            return urls[-1]
        time.sleep(.5)
    raise RuntimeError('Tunnel URL timeout')


def configure_origin(root, url):
    if not valid_url(url):
        raise ValueError('Unexpected tunnel URL')
    path = root / 'shared/.env'
    values = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition('=')
        if separator and not key.lstrip().startswith('#'):
            values[key.strip()] = shlex.split(value)[0] if value else ''
    values['ALLOWED_HOSTS'] = urlsplit(url).hostname + ',localhost,127.0.0.1'
    values['CSRF_TRUSTED_ORIGINS'] = url.rstrip('/')
    atomic_write(path, ''.join(key + '=' + shlex.quote(value) + '\n' for key, value in values.items()))


def start_server(root):
    stop_owned(root, 'mvp-server')
    release = (root / 'current').resolve()
    if root / 'releases' not in release.parents:
        raise RuntimeError('Release is outside managed directory')
    env = os.environ.copy()
    for key in ('DEBUG', 'DJANGO_SECRET_KEY', 'ALLOWED_HOSTS', 'CSRF_TRUSTED_ORIGINS', 'APP_PORT', 'DATABASE_PATH', 'ASSISTANT_MODE'):
        env.pop(key, None)
    env['FSP_ENV_FILE'] = str(root / 'shared/.env')
    launch(root, 'mvp-server', [str(release / '.venv/bin/python'), 'scripts/run_app.py'], cwd=release, env=env)
    for _ in range(30):
        try:
            if get_version('http://127.0.0.1:8011', local=True) == (release / 'REVISION').read_text().strip():
                return
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(.2)
    raise RuntimeError('Application startup timeout')


class SessionFTP_TLS(ftplib.FTP_TLS):
    def ntransfercmd(self, cmd, rest=None):
        connection, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            connection = self.context.wrap_socket(connection, server_hostname=self.host, session=self.sock.session)
        return connection, size


def publish(config, filename, data):
    if filename not in {'fsp-demo.html', 'fsp-demo-status.json'}:
        raise ValueError('Unexpected publication filename')
    certificate = base64.b64decode(config['certificate_der'])
    context = ssl.create_default_context()
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(certificate))
    if hasattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN'):
        context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    ftp = SessionFTP_TLS(context=context, timeout=15)
    try:
        ftp.connect(config['host'], config.get('port', 21))
        ftp.auth()
        if ftp.sock.getpeercert(binary_form=True) != certificate:
            raise RuntimeError('Hosting certificate differs from trusted certificate')
        ftp.login(config['user'], config['password'])
        ftp.prot_p()
        ftp.cwd(config['remote_directory'])
        temporary = '.' + filename + '.watchdog-upload'
        ftp.storbinary('STOR ' + temporary, io.BytesIO(data))
        received = io.BytesIO()
        ftp.retrbinary('RETR ' + temporary, received.write)
        if received.getvalue() != data:
            raise RuntimeError('Hosting upload differs from source')
        ftp.rename(temporary, filename)
        ftp.quit()
    finally:
        ftp.close()


def maintain(root):
    shared = root / 'shared'
    state_path = shared / 'watchdog-state.json'
    state = read_json(state_path)
    release = read_json(shared / 'release.json')
    commit = (root / 'current/REVISION').read_text().strip()
    url = release.get('url', '')
    available = False
    action = 'checked'
    try:
        renewed = owned_pid(root, 'mvp-pinggy') is None or not valid_url(url)
        local_url = 'http://127.0.0.1:8011'
        local_ready = public_ready = False
        if not renewed:
            if not version_matches(local_url, commit, local=True):
                start_server(root)
                action = 'application-restarted'
            local_ready = app_ready(local_url, commit, local=True)
            if local_ready:
                public_ready = app_ready(url, commit)
                state['failures'] = 0 if public_ready else state.get('failures', 0) + 1
                renewed = state['failures'] >= 3
            else:
                # A reachable application with a broken DB/template is not a
                # broken tunnel. Expose the outage instead of restarting it.
                state['failures'] = 0
        if renewed:
            url = start_tunnel(root)
            configure_origin(root, url)
            release.update(url=url, commit=commit, assistant='mock', tunnel='pinggy-free')
            atomic_write(shared / 'release.json', json.dumps(release, indent=2) + '\n')
            start_server(root)
            state['failures'] = 0
            action = 'renewed'
            local_ready = app_ready(local_url, commit, local=True)
            public_ready = local_ready and app_ready(url, commit)
        available = local_ready and public_ready
        message = ('Демо доступно' if available else
                   'Приложение недоступно; повтор через минуту' if not local_ready else
                   'Проверяем соединение; повтор через минуту')
    except Exception as error:
        available = False
        message = 'Восстановление не завершено; повтор через минуту'
        state['last_error'] = type(error).__name__
    status = {'schema_version': 1, 'available': available, 'url': url if valid_url(url) else '',
              'prototype_url': url.rstrip('/') + '/static/prototype/index.html' if valid_url(url) else '',
              'commit': commit, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'message': message, 'assistant': 'mock'}
    atomic_write(shared / 'watchdog-state.json', json.dumps(state) + '\n')
    atomic_write(shared / 'public-status.json', json.dumps(status, ensure_ascii=False, indent=2) + '\n')
    try:
        publish(read_json(shared / 'portal-publisher.json'), 'fsp-demo-status.json',
                (json.dumps(status, ensure_ascii=False, indent=2) + '\n').encode())
        publication = 'published'
    except Exception as error:
        publication = 'publish-failed:' + type(error).__name__
    print(json.dumps({'checked_at': status['checked_at'], 'available': available, 'action': action,
                      'publication': publication}, ensure_ascii=False), flush=True)
    return available and publication == 'published'


def cron_content(text, command):
    begin, end = '# BEGIN FSP DEMO WATCHDOG', '# END FSP DEMO WATCHDOG'
    if text.count(begin) != text.count(end) or text.count(begin) > 1:
        raise ValueError('Malformed managed crontab block')
    if begin in text:
        start = text.index(begin)
        finish = text.index(end, start) + len(end)
        text = text[:start] + text[finish:]
    return text.rstrip() + '\n' + begin + '\n' + command + '\n' + end + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.home() / 'fsp-mvp')
    args = parser.parse_args()
    with (args.root / 'shared/maintenance.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Maintenance already running; skipped', flush=True)
            return 0
        return 0 if maintain(args.root.resolve()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
