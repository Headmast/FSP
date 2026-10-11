"""Independent learning/V2 HTTP expectations for the full contract verifier."""
import json
from datetime import timedelta
from django.utils import timezone


def learning_scenarios(run, require, profile, other_profile):
    from assessments.models import PracticeSession, LessonProgress, Attempt
    from assessments.learning import start_practice
    profile.refresh_from_db()
    grade_before=(profile.confirmed_grade,profile.test_score,profile.grade_changed_at)
    topics={'ios':'swift','android':'kotlin','flutter':'dart','aurora':'cpp-qt'}
    sessions={}
    for track,topic in topics.items():
        lesson=f'/learning/tracks/{track}/lessons/Junior/{topic}/'
        template='/learning/tracks/{track}/lessons/{grade}/{topic}/'
        run('learning-dashboard-'+track,'candidate','/learning/?track='+track,template='/learning/')
        run('learning-lesson-'+track,'candidate',lesson,template=template)
        run('learning-unchecked-'+track,'candidate',lesson+'complete/','POST',{},302,template=template+'complete/',location=lesson)
        require(not LessonProgress.objects.filter(candidate=profile,track=track).exists(),'Unchecked lesson mutated progress')
        for label in ['complete','repeat']:
            run('learning-'+label+'-'+track,'candidate',lesson+'complete/','POST',{'read':'on'},302,template=template+'complete/',location=lesson,valid_body='LearningRead')
        require(LessonProgress.objects.filter(candidate=profile,track=track).count()==1,'Lesson repeat duplicated progress')
        run('learning-start-'+track,'candidate','/learning/start/','POST',{'track':track,'grade':'Junior'},302,valid_body='LearningStart')
        obj=PracticeSession.objects.get(candidate=profile,track=track,status='active');sessions[track]=obj
        session=f'/learning/sessions/{obj.pk}/';answer=session+'answer/'
        run('learning-start-reuse-'+track,'candidate','/learning/start/','POST',{'track':track,'grade':'Middle'},302,location=session+'?question=0')
        require(PracticeSession.objects.filter(candidate=profile,track=track).count()==1,'Active practice duplicated')
        run('learning-question-'+track,'candidate',session,template='/learning/sessions/{pk}/')
        for index in ['-1','8','bad']:
            run('learning-index-'+track+index,'candidate',session+'?question='+index,expected=404,template='/learning/sessions/{pk}/')
        run('learning-foreign-'+track,'other',session,expected=404,template='/learning/sessions/{pk}/')
        run('learning-no-csrf-'+track,'candidate',answer,'POST',{},403,csrf=False,template='/learning/sessions/{pk}/answer/')
        first=obj.tasks[0];wrong=(first['correct']+1)%4
        run('learning-invalid-atomic-'+track,'candidate',answer,'POST',{'q_'+first['id']:wrong,'q_not_owned':0},302,template='/learning/sessions/{pk}/answer/',location=session)
        obj.refresh_from_db();require(obj.answers=={},'Invalid practice partially saved')
        run('learning-pause-'+track,'candidate',answer,'POST',{'q_'+first['id']:wrong,'action':'pause'},302,template='/learning/sessions/{pk}/answer/',location=f'/learning/?track={track}&grade=Junior',valid_body='LearningAnswers')
        obj.refresh_from_db();require(obj.answers=={first['id']:wrong},'Pause lost answer')
        answers={'q_'+task['id']:(task['correct']+1)%4 for task in obj.tasks}
        run('learning-finish-'+track,'candidate',answer,'POST',{**answers,'action':'finish','confirmed_grade':'Middle','score':100},302,template='/learning/sessions/{pk}/answer/',location=session,valid_body='LearningAnswers')
        obj.refresh_from_db();require(obj.status=='finished' and obj.correct_count==0,'Practice score trusted client')
        before=(obj.answers,obj.correct_count,obj.finished_at)
        run('learning-finish-repeat-'+track,'candidate',answer,'POST',{'action':'finish','q_invalid':'invalid'},302,template='/learning/sessions/{pk}/answer/',location=session)
        obj.refresh_from_db();require((obj.answers,obj.correct_count,obj.finished_at)==before,'Finished practice rewrote result')
        run('learning-review-'+track,'candidate',session+'?question=bad',template='/learning/sessions/{pk}/')
    run('learning-legacy-lesson','candidate','/learning/lessons/Junior/swift/',template='/learning/lessons/{grade}/{topic}/')
    run('learning-legacy-complete','candidate','/learning/lessons/Junior/swift/complete/','POST',{'read':'on'},302,template='/learning/lessons/{grade}/{topic}/complete/',location='/learning/tracks/ios/lessons/Junior/swift/')
    run('learning-track-invalid','candidate','/learning/?track=wrong',expected=404,template='/learning/')
    run('learning-grade-fallback','candidate','/learning/?grade=wrong&track=ios',template='/learning/')
    run('learning-start-invalid','candidate','/learning/start/','POST',{'track':'wrong','grade':'Junior'},302,location='/learning/')
    foreign=start_practice(other_profile,'Junior',track='ios')
    run('learning-source-foreign','candidate','/learning/start/','POST',{'source':foreign.pk},404)
    run('learning-source-malformed','candidate','/learning/start/','POST',{'source':'²'},404)
    run('learning-repeat-errors','candidate','/learning/start/','POST',{'source':sessions['ios'].pk,'track':'wrong','grade':'wrong'},302)
    review=PracticeSession.objects.get(candidate=profile,track='ios',status='active')
    require(review.kind=='review' and review.grade=='Junior' and len(review.tasks)==8,'Source did not select own immutable mistakes')
    path=f'/learning/sessions/{review.pk}/';url=path+'answer/'
    run('learning-repeat-finish','candidate',url,'POST',{'action':'finish',**{'q_'+t['id']:t['correct'] for t in review.tasks}},302,template='/learning/sessions/{pk}/answer/',location=path)
    run('learning-repeat-no-errors','candidate','/learning/start/','POST',{'source':review.pk},302,location='/learning/')
    # The lock must affect reads and writes without finishing/leaking practice.
    exam=Attempt.objects.create(candidate=profile,grade='Junior',tasks=[],bank_version='contract-lock-only',started_at=timezone.now(),expires_at=timezone.now()+timedelta(minutes=15))
    run('learning-exam-dashboard','candidate','/learning/',template='/learning/')
    for route,method,payload,template in [
        ('/learning/lessons/Junior/swift/','GET',None,'/learning/lessons/{grade}/{topic}/'),
        ('/learning/tracks/android/lessons/Junior/kotlin/','GET',None,'/learning/tracks/{track}/lessons/{grade}/{topic}/'),
        ('/learning/lessons/Junior/swift/complete/','POST',{'read':'on'},'/learning/lessons/{grade}/{topic}/complete/'),
        ('/learning/tracks/android/lessons/Junior/kotlin/complete/','POST',{'read':'on'},'/learning/tracks/{track}/lessons/{grade}/{topic}/complete/'),
        ('/learning/start/','POST',{'track':'ios','grade':'Junior'},'/learning/start/'),
        (path,'GET',None,'/learning/sessions/{pk}/'),(url,'POST',{'action':'finish'},'/learning/sessions/{pk}/answer/')]:
        run('learning-exam-lock-'+template,'candidate',route,method,payload,423,template=template)
    exam.delete()  # Lock-only fixture is not a valid completed assessment witness.
    profile.refresh_from_db();require((profile.confirmed_grade,profile.test_score,profile.grade_changed_at)==grade_before,'Learning changed professional category')
    return sessions['ios']


def action_scenarios(run, require, anonymous, users, profile, company, need, token_pairs):
    from accounts.models import ApiToken
    from api.core import issue_token
    from api.models import ActionDraft
    from profiles.models import Experience
    from hiring.models import Need, Invitation
    from assessments.models import Attempt
    from uuid import uuid4
    template='/drafts/{pk}/'
    def reset(key):ApiToken.objects.filter(pk=token_pairs[key][0].pk).update(request_count=0)
    def prepare(label,key,kind,payload=None,target=None,expected=201,secret=None):
        reset(key);data={'kind':kind,'payload':payload or {}}
        if target is not None:data['target_id']=target
        response,_=run(label,anonymous,'/api/v1/drafts','POST',data,expected,csrf=False,raw_json=True,bearer=secret or token_pairs[key][1],valid_body='ActionPrepare' if expected==201 else None)
        return ActionDraft.objects.get(pk=response.json()['data']['id']) if expected==201 else None
    def approve(label,key,obj,expected=302,action='apply',extra=None):
        path=f'/drafts/{obj.pk}/'
        run(label,key,path,'POST',{'action':action,'acknowledge':True,**(extra or {})},expected,template=template,location=path if expected==302 else None,valid_body='ActionApproval' if expected==302 else None)
        obj.refresh_from_db();return obj
    before=profile.city
    draft=prepare('v2-prepare-profile','candidate','profile.update',{'city':'Казань'})
    profile.refresh_from_db();require(profile.city==before,'Prepare mutated profile')
    url=f'/api/v1/drafts/{draft.pk}'
    run('v2-own-read',anonymous,url,bearer=token_pairs['candidate'][1],template='/api/v1/drafts/{pk}')
    run('v2-foreign-api',anonymous,url,expected=404,bearer=token_pairs['employer'][1],template='/api/v1/drafts/{pk}')
    run('v2-foreign-web','other',f'/drafts/{draft.pk}/',expected=404,template=template)
    run('v2-apply-bearer-no-session',anonymous,f'/drafts/{draft.pk}/','POST',{'action':'apply','acknowledge':True},302,template=template,bearer=token_pairs['candidate'][1])
    run('v2-apply-no-csrf','candidate',f'/drafts/{draft.pk}/','POST',{'action':'apply','acknowledge':True},403,csrf=False,template=template)
    run('v2-apply-unacknowledged','candidate',f'/drafts/{draft.pk}/','POST',{'action':'apply'},400,template=template)
    run('v2-no-api-apply',anonymous,url+'/apply','POST',{},404,template='/api/v1/{unknown}',raw_json=True,bearer=token_pairs['candidate'][1])
    approve('v2-profile-apply','candidate',draft)
    profile.refresh_from_db();require(profile.city=='Казань','Approved patch not applied')
    original_time=draft.applied_at
    ActionDraft.objects.filter(pk=draft.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
    approve('v2-applied-repeat-expired','candidate',draft)
    require(draft.applied_at==original_time,'Replay rewrote applied timestamp')
    approve('v2-cancel-applied','candidate',draft,409,action='cancel')
    for label,state,expected in [('stale','stale',409),('expired','expired',410),('cancelled','cancelled',409)]:
        obj=prepare('v2-'+label+'-prepare','candidate','profile.update',{'city':'Тула'})
        if state=='stale':
            profile.city='Омск';profile.save(update_fields=['city'])
        elif state=='expired':ActionDraft.objects.filter(pk=obj.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        else:approve('v2-cancel-web','candidate',obj,action='cancel')
        approve('v2-'+label+'-apply','candidate',obj,expected)
    obj=prepare('v2-cancel-prepare','candidate','profile.update',{'city':'Тула'})
    for label in ['cancel','cancel-repeat']:
        run('v2-'+label,anonymous,f'/api/v1/drafts/{obj.pk}/cancel','POST',{},200,template='/api/v1/drafts/{pk}/cancel',raw_json=True,bearer=token_pairs['candidate'][1])
    obj.refresh_from_db();require(obj.status=='cancelled','API cancel not saved')
    run('v2-cancel-body-invalid',anonymous,f'/api/v1/drafts/{obj.pk}/cancel','POST',{'extra':1},400,template='/api/v1/drafts/{pk}/cancel',raw_json=True,bearer=token_pairs['candidate'][1])
    run('v2-json-media-invalid',anonymous,'/api/v1/drafts','POST',{'kind':'profile.publish'},400,bearer=token_pairs['candidate'][1])
    run('v2-json-array-invalid',anonymous,'/api/v1/drafts','POST',[1],400,raw_json=True,bearer=token_pairs['candidate'][1])
    prepare('v2-body-fields-invalid','candidate','profile.update',{'confirmed_grade':'Middle'},expected=400)
    prepare('v2-role-invalid','candidate','company.update',{'name':'Компания'},expected=403)
    _,read_secret=issue_token(users['candidate'],'no-draft','cli')
    prepare('v2-scope-invalid','candidate','profile.update',{'city':'Тула'},expected=403,secret=read_secret)
    _,mcp_secret=issue_token(users['candidate'],'mcp-draft','mcp',drafts=True)
    prepare('v2-mcp-contact-rejected','candidate','profile.update',{'contact_email':'private@demo.invalid'},expected=400,secret=mcp_secret)
    mcp=prepare('v2-mcp-safe','candidate','profile.update',{'city':'Тула','description':'secret-description-contract'},secret=mcp_secret)
    _,body=run('v2-mcp-projection',anonymous,f'/api/v1/drafts/{mcp.pk}',bearer=mcp_secret,template='/api/v1/drafts/{pk}')
    require(b'secret-description-contract' not in body and 'payload' not in json.loads(body)['data'],'MCP leaked private draft text')
    obj=prepare('v2-experience','candidate','profile.update',{'experiences':[{'organization':'Компания','role':'Разработчик','months':12,'description':'Частный опыт'}]})
    approve('v2-experience-apply','candidate',obj);require(Experience.objects.filter(profile=profile,months=12).count()==1,'Experience payload not applied')
    for kind in ['profile.unpublish','profile.publish']:
        obj=prepare('v2-'+kind,'candidate',kind)
        if kind=='profile.publish':approve('v2-publication-consent-missing','candidate',obj,400)
        approve('v2-'+kind+'-apply','candidate',obj,extra={'publication_consent':True})
        profile.refresh_from_db();require(profile.published==(kind=='profile.publish'),'Publication transition failed')
    obj=prepare('v2-company','employer','company.update',{'industry':'Мобильная разработка'})
    approve('v2-company-apply','employer',obj);company.refresh_from_db();require(company.industry=='Мобильная разработка','Company patch not applied')
    payload={'title':'Мобильный разработчик','grade':'Junior','tasks':'Разработка экрана','salary_min':100000,'salary_max':150000,'work_format':'remote','next_step':'Встреча','skills':'Swift'}
    from hiring.models import Recruiter
    owned_hr=Recruiter.objects.filter(company=company).first()
    payload['recruiter']=owned_hr.pk
    count=Need.objects.filter(company=company).count()
    obj=prepare('v2-need-create','employer','need.create',payload)
    require(Need.objects.filter(company=company).count()==count,'Prepare created need')
    approve('v2-need-create-apply','employer',obj)
    created=Need.objects.get(pk=obj.applied_target_id);require(created.recruiter_id==owned_hr.pk,'Recruiter assignment not applied');require(Need.objects.filter(company=company).count()==count+1,'Approved need not created')
    obj=prepare('v2-need-update','employer','need.update',{'salary_max':160000},created.pk)
    approve('v2-need-update-apply','employer',obj);created.refresh_from_db();require(created.salary_max==160000,'Need update failed')
    foreign_hr=Recruiter.objects.create(company=Need.objects.exclude(company=company).first().company,name='Чужой HR')
    prepare('v2-foreign-hr-rejected','employer','need.update',{'recruiter':foreign_hr.pk},created.pk,400)
    obj=prepare('v2-hr-unassign','employer','need.update',{'recruiter':None},created.pk)
    run('v2-hr-edit-browser','employer',f'/drafts/{obj.pk}/',template='/drafts/{pk}/')
    approve('v2-hr-unassign-apply','employer',obj);created.refresh_from_db();require(created.recruiter_id is None,'Unassign HR failed')
    prepare('v2-need-invalid-salary','employer','need.update',{'salary_max':1},created.pk,400)
    count=Invitation.objects.count()
    obj=prepare('v2-invitation-send','employer','invitation.send',{'candidate_id':profile.pk,'accepted_attempts':[],'discussion':'Обсудим задачу'},created.pk)
    require(Invitation.objects.count()==count,'Prepare sent invitation')
    approve('v2-invitation-send-apply','employer',obj)
    invite=Invitation.objects.get(pk=obj.applied_target_id);require(invite.status=='sent','Approved invitation not sent')
    prepare('v2-invitation-duplicate','employer','invitation.send',{'candidate_id':profile.pk},created.pk,409)
    obj=prepare('v2-invitation-accept','candidate','invitation.accept',target=invite.pk)
    approve('v2-invitation-accept-apply','candidate',obj);invite.refresh_from_db();require(invite.status=='accepted','Accepted draft not decided')
    new_need=Need.objects.create(company=company,title='Вторая роль',grade='Junior',tasks='Задача',salary_min=1,salary_max=2,work_format='remote')
    obj=prepare('v2-send-for-decline','employer','invitation.send',{'candidate_id':profile.pk},new_need.pk)
    approve('v2-send-for-decline-apply','employer',obj)
    obj=prepare('v2-decline','candidate','invitation.decline',target=obj.applied_target_id)
    approve('v2-decline-apply','candidate',obj);require(Invitation.objects.get(pk=obj.applied_target_id).status=='declined','Decline draft not decided')
    # API parser rejects malformed/non-owned identifiers; browser only accepts canonical UUID.
    for value in ['bad',str(uuid4())]:
        run('v2-invalid-'+value,anonymous,'/api/v1/drafts/'+value,expected=404,template='/api/v1/drafts/{pk}',bearer=token_pairs['candidate'][1])
    run('v2-draft-pagination',anonymous,'/api/v1/drafts?limit=0',expected=400,template='/api/v1/drafts',bearer=token_pairs['candidate'][1])
    return draft
