import importlib.util
import json
import os
import tempfile
import unittest
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('maintain_demo',Path(__file__).resolve().parents[1]/'maintain_demo.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SHA='a'*40
OLD='https://old.run.pinggy-free.link'
NEW='https://new.run.pinggy-free.link'

class ReadinessHTTPTests(unittest.TestCase):
    def setUp(self):
        self.health_status=200;self.marker=True;self.requests=[]
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                owner.requests.append((self.path,self.headers.get('X-Forwarded-Proto')))
                status=200;content_type='application/json'
                if self.path=='/version/':body=json.dumps({'commit':SHA}).encode()
                elif self.path=='/health/':
                    status=owner.health_status;body=json.dumps({'status':'ok' if status==200 else 'unavailable'}).encode()
                else:
                    content_type='text/html'
                    body=b'<form data-testid="login-form"></form>' if owner.marker else b'Upstream error'
                self.send_response(status);self.send_header('Content-Type',content_type);self.end_headers();self.wfile.write(body)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
    def test_healthy_version_database_and_html_are_required(self):
        self.assertTrue(m.app_ready(self.url,SHA,local=True))
        self.assertEqual([x[0] for x in self.requests],['/version/','/health/','/accounts/login/'])
        self.assertTrue(all(x[1]=='https' for x in self.requests))
    def test_healthy_version_with_failed_health_is_not_available(self):
        self.health_status=503
        self.assertFalse(m.app_ready(self.url,SHA))
        self.assertEqual([x[0] for x in self.requests],['/version/','/health/'])
    def test_broken_render_is_unavailable_even_with_healthy_database(self):
        self.marker=False
        self.assertFalse(m.app_ready(self.url,SHA))

class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        (self.root/'shared/pids').mkdir(parents=True)
        (self.root/'releases'/SHA).mkdir(parents=True)
        (self.root/'releases'/SHA/'REVISION').write_text(SHA)
        (self.root/'current').symlink_to(self.root/'releases'/SHA)
        (self.root/'shared/release.json').write_text(json.dumps({'commit':SHA,'url':OLD}))
        (self.root/'shared/.env').write_text("DJANGO_SECRET_KEY=synthetic-secret\nDATABASE_PATH=/unchanged/db.sqlite3\nALLOWED_HOSTS=old.run.pinggy-free.link\n")
        readiness=patch.object(m,'check_readiness',return_value=True)
        readiness.start();self.addCleanup(readiness.stop)
    def tearDown(self):self.tmp.cleanup()
    def status(self):return json.loads((self.root/'shared/public-status.json').read_text())
    def test_urls_reject_credentials_ports_and_foreign_destinations(self):
        self.assertTrue(m.valid_url(NEW))
        for url in ['http://new.run.pinggy-free.link','https://user:secret@new.run.pinggy-free.link','https://new.run.pinggy-free.link:443','https://new.run.pinggy-free.link:bad','https://new.run.pinggy-free.link.attacker.org','https://evil.org','https://new.run.pinggy-free.link/?x=1']:
            self.assertFalse(m.valid_url(url),url)
    def test_healthy_run_does_not_restart_or_expose_secrets(self):
        with patch.object(m,'owned_pid',return_value=123),patch.object(m,'get_version',return_value=SHA),patch.object(m,'publish') as publish,patch.object(m,'start_server') as server,patch.object(m,'start_tunnel') as tunnel:
            self.assertTrue(m.maintain(self.root));server.assert_not_called();tunnel.assert_not_called()
        data=publish.call_args.args[2].decode();self.assertNotIn('synthetic-secret',data);self.assertTrue(self.status()['available'])
    def test_expired_tunnel_updates_origin_preserves_secret_and_release(self):
        with patch.object(m,'owned_pid',return_value=None),patch.object(m,'start_tunnel',return_value=NEW),patch.object(m,'start_server') as server,patch.object(m,'get_version',return_value=SHA),patch.object(m,'publish'):
            self.assertTrue(m.maintain(self.root));server.assert_called_once()
        env=(self.root/'shared/.env').read_text();self.assertIn('DJANGO_SECRET_KEY=synthetic-secret',env);self.assertIn('DATABASE_PATH=/unchanged/db.sqlite3',env);self.assertIn('CSRF_TRUSTED_ORIGINS='+NEW,env)
        self.assertEqual(os.stat(self.root/'shared/.env').st_mode & 0o777,0o600)
        self.assertEqual(self.status()['url'],NEW)
    def test_three_failed_checks_before_renewing_live_tunnel(self):
        def version(url,**kwargs):
            if url==OLD:raise OSError('temporary connection error')
            return SHA
        with patch.object(m,'owned_pid',return_value=123),patch.object(m,'get_version',side_effect=version),patch.object(m,'start_tunnel',return_value=NEW) as tunnel,patch.object(m,'start_server'),patch.object(m,'publish'):
            self.assertFalse(m.maintain(self.root));self.assertFalse(m.maintain(self.root));tunnel.assert_not_called()
            self.assertTrue(m.maintain(self.root));tunnel.assert_called_once()
    def test_failed_app_restart_marks_public_status_unavailable(self):
        def version(url,**kwargs):
            if kwargs.get('local'):raise OSError('app down')
            return SHA
        with patch.object(m,'owned_pid',return_value=123),patch.object(m,'get_version',side_effect=version),patch.object(m,'start_server',side_effect=RuntimeError('wrong PID')),patch.object(m,'publish'):
            self.assertFalse(m.maintain(self.root))
        self.assertFalse(self.status()['available'])
    def test_publisher_failure_retries_without_restarting_healthy_services(self):
        with patch.object(m,'owned_pid',return_value=123),patch.object(m,'get_version',return_value=SHA),patch.object(m,'publish',side_effect=OSError('hosting down')),patch.object(m,'start_tunnel') as tunnel:
            self.assertFalse(m.maintain(self.root));tunnel.assert_not_called()

    def test_database_failure_is_unavailable_without_restart_or_tunnel_rotation(self):
        with patch.object(m,'owned_pid',return_value=123),patch.object(m,'get_version',return_value=SHA),patch.object(m,'check_readiness',return_value=False),patch.object(m,'publish'),patch.object(m,'start_server') as server,patch.object(m,'start_tunnel') as tunnel:
            for _ in range(4):self.assertFalse(m.maintain(self.root))
            server.assert_not_called();tunnel.assert_not_called()
        self.assertFalse(self.status()['available'])
        self.assertEqual(json.loads((self.root/'shared/watchdog-state.json').read_text())['failures'],0)

    def test_readiness_recovers_after_database_returns(self):
        with patch.object(m,'owned_pid',return_value=123),patch.object(m,'get_version',return_value=SHA),patch.object(m,'check_readiness',return_value=False),patch.object(m,'publish'):
            self.assertFalse(m.maintain(self.root))
        with patch.object(m,'owned_pid',return_value=123),patch.object(m,'get_version',return_value=SHA),patch.object(m,'publish'),patch.object(m,'start_server') as server:
            self.assertTrue(m.maintain(self.root));server.assert_not_called()

    def test_public_health_failure_requires_three_ticks_when_local_is_healthy(self):
        with patch.object(m,'owned_pid',return_value=123),patch.object(m,'get_version',return_value=SHA),patch.object(m,'check_readiness',side_effect=lambda url,local=False:local or url==NEW),patch.object(m,'publish'),patch.object(m,'start_tunnel',return_value=NEW) as tunnel,patch.object(m,'start_server'):
            self.assertFalse(m.maintain(self.root));self.assertFalse(m.maintain(self.root))
            tunnel.assert_not_called()
            self.assertTrue(m.maintain(self.root));tunnel.assert_called_once()
    def test_global_cron_environment_does_not_override_shared_config(self):
        with patch.dict(m.os.environ,{'DEBUG':'1','APP_PORT':'9999'}),patch.object(m,'stop_owned'),patch.object(m,'launch') as launch,patch.object(m,'get_version',return_value=SHA):
            m.start_server(self.root)
        env=launch.call_args.kwargs['env']
        self.assertNotIn('DEBUG',env);self.assertNotIn('APP_PORT',env)
        self.assertEqual(env['FSP_ENV_FILE'],str(self.root/'shared/.env'))
    def test_foreign_pid_is_not_killed(self):
        (self.root/'shared/pids/mvp-pinggy.pid').write_text('12345')
        with patch.object(Path,'read_bytes',return_value=b'ssh\0free.pinggy.io\0-R\00:127.0.0.1:9999'),patch.object(m.os,'kill') as kill:
            with self.assertRaises(RuntimeError):m.stop_owned(self.root,'mvp-pinggy')
            kill.assert_not_called()
    def test_deployment_lock_skips_tick_without_running_recovery(self):
        with (self.root/'shared/maintenance.lock').open('a') as lock:
            m.fcntl.flock(lock,m.fcntl.LOCK_EX|m.fcntl.LOCK_NB)
            with patch('sys.argv',['maintain_demo.py','--root',str(self.root)]),patch.object(m,'maintain') as maintain:
                self.assertEqual(m.main(),0);maintain.assert_not_called()
    def test_cron_install_is_idempotent_and_preserves_other_jobs(self):
        existing='MAILTO=owner@example.invalid\n0 4 * * * /usr/bin/backup\n'
        first=m.cron_content(existing,'* * * * * /usr/bin/watchdog')
        second=m.cron_content(first,'* * * * * /usr/bin/watchdog')
        self.assertEqual(first,second);self.assertIn(existing.strip(),second);self.assertEqual(second.count('BEGIN FSP DEMO WATCHDOG'),1)
        with self.assertRaises(ValueError):m.cron_content('# BEGIN FSP DEMO WATCHDOG','job')
