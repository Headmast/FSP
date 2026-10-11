"""Exercise real Git worktrees in disposable repos; never touch the project checkout."""
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]


class WorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fsp worktree checks ')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repo with spaces'
        (self.repo / 'scripts').mkdir(parents=True)
        shutil.copy(SOURCE / 'worktree.py', self.repo / 'scripts/worktree.py')
        shutil.copy(SOURCE.parent / '.gitignore', self.repo / '.gitignore')
        self.git('init', '-b', 'main')
        self.git('add', '.')
        self.git('-c', 'user.name=Worktree checks', '-c', 'user.email=checks@demo.invalid', 'commit', '-m', 'Fixture')
        self.ports = []

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, text=True, capture_output=True, check=True).stdout

    def port(self):
        while True:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                value = sock.getsockname()[1]
            if value not in self.ports:
                self.ports.append(value)
                return value

    def run_tool(self, *args, repo=None, success=True):
        result = subprocess.run([sys.executable, str((repo or self.repo) / 'scripts/worktree.py'), *map(str, args)], text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def create(self, name, port=None):
        result = self.run_tool('create', name, '--base', 'main', '--port', port or self.port())
        return Path(json.loads(result.stdout)['path'])

    def test_two_checkout_paths_and_runtime_are_isolated(self):
        first, second = self.create('assessment'), self.create('hiring')
        a, b = [json.loads((path / '.worktree-local.json').read_text()) for path in (first, second)]
        self.assertNotEqual(a['port'], b['port'])
        self.assertNotEqual(a['root'], b['root'])
        self.assertEqual(a['branch'], 'mvp/assessment')
        self.assertTrue((first / '.git').is_file())
        self.run_tool('check', repo=first)
        self.run_tool('check', repo=second)
        for path in (first, second):
            state = subprocess.run(['git', 'status', '--porcelain'], cwd=path, text=True, capture_output=True, check=True)
            self.assertEqual(state.stdout, '')
        listed = [json.loads(line) for line in self.run_tool('list').stdout.splitlines()]
        self.assertEqual(len(listed), 3)

    def test_duplicate_port_rejected_before_branch_creation(self):
        port = self.port()
        self.create('assessment', port)
        result = self.run_tool('create', 'hiring', '--port', port, success=False)
        self.assertIn('reserved', result.stderr)
        self.assertNotIn('mvp/hiring', self.git('branch', '--list'))

    def test_invalid_names_and_ports_rejected(self):
        for name in ('../escape', 'Bad', 'bad--name'):
            self.run_tool('create', name, '--port', self.port(), success=False)
        self.run_tool('create', 'bad-port', '--port', 80, success=False)
        self.assertEqual(self.git('branch', '--list').strip(), '* main')

    def test_runtime_tampering_detected(self):
        checkout = self.create('assessment')
        env = checkout / '.env.worktree'
        env.write_text(env.read_text().replace('APP_PORT=', 'WRONG_PORT='))
        self.assertIn('differs', self.run_tool('check', repo=checkout, success=False).stderr)

    def test_uncommitted_changes_not_copied(self):
        (self.repo / 'local-only.txt').write_text('not committed')
        checkout = self.create('assessment')
        self.assertFalse((checkout / 'local-only.txt').exists())

    def test_reconfigure_does_not_overwrite_settings(self):
        self.run_tool('configure', '--port', self.port())
        original = (self.repo / '.env.worktree').read_text()
        self.run_tool('configure', '--port', self.port(), success=False)
        self.assertEqual((self.repo / '.env.worktree').read_text(), original)

    def test_listening_port_rejected(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            sock.listen()
            self.run_tool('create', 'busy', '--port', sock.getsockname()[1], success=False)
        self.assertNotIn('mvp/busy', self.git('branch', '--list'))


if __name__ == '__main__':
    unittest.main()
