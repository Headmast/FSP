from django.apps import AppConfig


class ProfilesConfig(AppConfig):
    name='profiles'

    def ready(self):
        from django.db.models.signals import pre_delete
        from .models import Profile
        from .privacy import archive_profile_links
        def scrub(sender,instance,**kwargs):
            archive_profile_links(instance)
            from accounts.models import ApiToken,User
            from django.db.models import F
            ApiToken.objects.filter(user_id=instance.user_id).delete()
            User.objects.filter(pk=instance.user_id).update(session_generation=F('session_generation')+1)
        pre_delete.connect(scrub,sender=Profile,weak=False,dispatch_uid='fsp-privacy-profile-delete')
