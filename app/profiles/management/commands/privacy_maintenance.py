"""Reapply privacy requests, expire minimal history and owned backups, truncate old WAL pages."""
import fcntl
import json
import os
import re
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection,transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from profiles.privacy import reconcile,ledger_records
from profiles.models import PrivacyReceipt
from hiring.models import Invitation
from accounts.models import User


class Command(BaseCommand):
    help=__doc__

    def add_arguments(self,parser):
        parser.add_argument('--reconcile-only',action='store_true')

    def handle(self,*args,**options):
        reconcile()
        if options['reconcile_only']:
            self.stdout.write('PASS: privacy restore fence applied')
            return
        now=timezone.now();cutoff=now-timedelta(days=settings.PRIVACY_ARCHIVE_DAYS)
        path=Path(settings.PRIVACY_LEDGER_PATH)
        # Prune the ledger before receipts, under the same append lock. A crash leaves extra receipts, not replayable old events.
        ledger_records()  # Validate before any expiry or file deletion.
        if path.exists():
            with path.open('r+') as stream:
                fcntl.flock(stream,fcntl.LOCK_EX)
                kept=[row for row in (json.loads(line) for line in stream if line.strip()) if parse_datetime(row['created_at'])>=cutoff]
                stream.seek(0);stream.write(''.join(json.dumps(row,separators=(',',':'))+'\n' for row in kept));stream.truncate()
                stream.flush();os.fsync(stream.fileno())
        with transaction.atomic():
            archived=Invitation.objects.filter(candidate__isnull=True,candidate_erased_at__lt=cutoff).count()
            Invitation.objects.filter(candidate__isnull=True,candidate_erased_at__lt=cutoff).delete()
            PrivacyReceipt.objects.filter(created_at__lt=cutoff).delete()
        for user in User.objects.exclude(assessment_privacy_holds={}):
            values=user.assessment_privacy_holds
            if not isinstance(values,dict):continue
            kept={}
            for key in ['change','Junior','Middle']:
                raw=values.get(key);until=parse_datetime(raw) if isinstance(raw,str) else None
                if until and timezone.is_aware(until) and until>now:kept[key]=raw
            if 'change' in kept and values.get('change_from') in {'Junior','Middle'}:kept['change_from']=values['change_from']
            raw=values.get('variant_until');until=parse_datetime(raw) if isinstance(raw,str) else None
            if until and timezone.is_aware(until) and until>now:
                for key in ['variants','variant_bank','variant_until']:kept[key]=values.get(key)
            if kept!=values:User.objects.filter(pk=user.pk).update(assessment_privacy_holds=kept)
        backup_dir=settings.DATABASE_PATH.parent/'backups';deleted=0
        if backup_dir.exists():
            backup_dir.chmod(0o700)
            for backup in backup_dir.iterdir():
                if backup.is_symlink() or not backup.is_file() or not re.fullmatch(r'[0-9]{18,20}\.sqlite3',backup.name):continue
                backup.chmod(0o600)
                if int(backup.stem)/1e9<(now-timedelta(days=settings.PRIVACY_BACKUP_DAYS)).timestamp():
                    backup.unlink();deleted+=1
        for suffix in ['', '-wal', '-shm']:
            candidate=Path(str(settings.DATABASE_PATH)+suffix)
            if candidate.is_file() and not candidate.is_symlink():candidate.chmod(0o600)
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA wal_checkpoint(TRUNCATE)');checkpoint=cursor.fetchone()
        self.stdout.write(json.dumps({'status':'PASS','archived_invitations_expired':archived,'owned_backups_expired':deleted,
            'wal_checkpoint_busy':bool(checkpoint[0]),'archive_days':settings.PRIVACY_ARCHIVE_DAYS,'backup_days':settings.PRIVACY_BACKUP_DAYS}))
