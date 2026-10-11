#!/usr/bin/env python3
"""Create and configure isolated Git worktrees; never copy secrets or remove work."""
import argparse
import json
import re
import shlex
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = '.worktree-local.json'


def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or 'Git command failed')
    return result.stdout.strip()


def inventory():
    # NUL-delimited porcelain also supports checkout paths containing spaces.
    records = git('worktree', 'list', '--porcelain', '-z').split('\0\0')
    result = []
    for record in records:
        fields = {}
        for line in record.split('\0'):
            key, _, value = line.partition(' ')
            fields[key] = value
        if fields.get('worktree'):
            result.append(fields)
    return result


def validate_port(port, checkout, probe=True):
    if not 1024 <= port <= 65535:
        raise ValueError('Port must be between 1024 and 65535')
    for item in inventory():
        other = Path(item['worktree']).resolve()
        if other == checkout.resolve():
            continue
        config = other / CONFIG
        if config.exists():
            data = json.loads(config.read_text())
            if data.get('port') == port:
                raise ValueError(f'Port {port} reserved by {other}')
    if probe:
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
            except OSError as exc:
                raise ValueError(f'Port {port} is already listening or unavailable') from exc


def env_content(path, port):
    settings = {
        'APP_PORT': str(port),
        'DATABASE_PATH': str(path / '.runtime' / 'db.sqlite3'),
        'LOG_DIR': str(path / '.runtime' / 'logs'),
        'PID_DIR': str(path / '.runtime' / 'pids'),
        'VENV_PATH': str(path / '.venv'),
    }
    return '# Local worktree settings; secrets are configured separately.\n' + ''.join(
        f'{key}={shlex.quote(value)}\n' for key, value in settings.items())


def configure(path, port, name):
    for filename in (CONFIG, '.env.worktree'):
        if (path / filename).exists():
            raise ValueError(f'{filename} already exists; refusing to overwrite local settings')
    validate_port(port, path)
    for dirname in ('logs', 'pids'):
        (path / '.runtime' / dirname).mkdir(parents=True, exist_ok=True)
    (path / '.env.worktree').write_text(env_content(path, port))
    (path / CONFIG).write_text(json.dumps({
        'schema_version': 1, 'name': name, 'port': port,
        'root': str(path), 'branch': subprocess.check_output(
            ['git', 'branch', '--show-current'], cwd=path, text=True).strip(),
    }, indent=2) + '\n')


def create(args):
    if not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', args.name):
        raise ValueError('Name must contain lowercase letters, numbers and single hyphens; start with a letter')
    path = ROOT.parent / (ROOT.name + '-worktrees') / args.name
    if path.exists():
        raise ValueError(f'Checkout path already exists: {path}')
    branch = 'mvp/' + args.name
    git('check-ref-format', '--branch', branch)
    ref = subprocess.run(['git', 'show-ref', '--verify', '--quiet', 'refs/heads/' + branch], cwd=ROOT)
    if ref.returncode == 0:
        raise ValueError(f'Branch already exists: {branch}; reuse it explicitly with git worktree add')
    base = git('rev-parse', '--verify', args.base + '^{commit}')
    validate_port(args.port, path)
    git('worktree', 'add', '-b', branch, str(path), base)
    try:
        configure(path, args.port, args.name)
    except Exception as exc:
        raise ValueError(f'Checkout created at {path}, but configuration failed: {exc}. Preserve it and repair manually.') from exc
    print(json.dumps({'path': str(path), 'branch': branch, 'base': base, 'port': args.port}, indent=2))


def check():
    data = json.loads((ROOT / CONFIG).read_text())
    if data.get('schema_version') != 1 or Path(data['root']).resolve() != ROOT:
        raise ValueError('Worktree configuration belongs to another checkout or has invalid schema')
    validate_port(data['port'], ROOT, probe=False)
    if (ROOT / '.env.worktree').read_text() != env_content(ROOT, data['port']):
        raise ValueError('Local environment differs from worktree configuration; repair or regenerate consistently')
    for name in (CONFIG, '.env.worktree', '.runtime/db.sqlite3', '.venv/example'):
        result = subprocess.run(['git', 'check-ignore', '-q', name], cwd=ROOT)
        if result.returncode:
            raise ValueError(f'Runtime path is not ignored by Git: {name}')
    print(f'PASS: isolated worktree {ROOT}, port {data["port"]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    new = commands.add_parser('create')
    new.add_argument('name')
    new.add_argument('--base', default='HEAD', help='Committed starting ref; local uncommitted changes are not copied')
    new.add_argument('--port', type=int, required=True)
    local = commands.add_parser('configure')
    local.add_argument('--port', type=int, required=True)
    commands.add_parser('list')
    commands.add_parser('check')
    args = parser.parse_args()
    try:
        git('rev-parse', '--show-toplevel')
        if args.command == 'create':
            create(args)
        elif args.command == 'configure':
            configure(ROOT, args.port, ROOT.name)
            check()
        elif args.command == 'list':
            for item in inventory():
                path = Path(item['worktree'])
                local = path / CONFIG
                data = json.loads(local.read_text()) if local.exists() else {}
                print(json.dumps({'path': str(path), 'branch': item.get('branch'), 'port': data.get('port')}, ensure_ascii=False))
        else:
            check()
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
