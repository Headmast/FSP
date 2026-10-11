"""Reviewed HTTP semantics. Django fields supply shape, not permissions or outcomes."""
import copy
from pathlib import Path
from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.forms import RegistrationForm, AccessibleAuthenticationForm, ConsentForm
from profiles.forms import ProfileForm, FspLinkForm, ExperienceFormSet
from hiring.forms import CompanyForm, NeedForm, RecruiterForm, AssignmentForm
from accounts.integrations import TokenForm
from assistant.forms import NeedPromptForm, ProfileDraftForm

MAX_ID = 2**63 - 1
CSRF = {'type': 'string', 'minLength': 32, 'maxLength': 64, 'writeOnly': True,
        'description': 'CSRF token from this browser session. Cookie csrftoken is also required. X-CSRFToken can replace this field.'}
ID = {'type': 'integer', 'minimum': 1, 'maximum': MAX_ID,
      'description': 'Positive ASCII decimal, at most 19 digits on the wire; leading zeroes accepted. Foreign/malformed ID returns 404.'}
OPTIONAL_ID = {'anyOf': [ID, {'const': ''}], 'description': 'Omitted/empty selects the documented default; explicit ID must be owned/visible.'}
GRADE = {'type': 'string', 'enum': ['Junior', 'Middle']}
SKILLS_NOTE = 'Comma-separated Swift, SwiftUI, UIKit, Combine, CoreData, Git, XCTest, URLSession; case/spacing aliases canonicalized; unknown skill is a form error.'


def ref(name):
    return {'$ref': '#/components/schemas/' + name}


def object_schema(properties, required=(), **extra):
    return {'type': 'object', 'properties': properties, 'required': list(required), **extra}


def form_schema(cls):
    instance = cls(company=None) if cls is AssignmentForm else cls()
    properties, required = {}, []
    for name, field in instance.fields.items():
        if isinstance(field, forms.ModelChoiceField):
            schema = copy.deepcopy(ID if field.required else OPTIONAL_ID)
            schema['description'] = 'Owned dropdown object. Invalid selection is a form error, not necessarily 404; see endpoint.'
        elif isinstance(field, forms.MultipleChoiceField):
            schema = {'type': 'array', 'items': {'type': 'string', 'enum': [v for v, _ in field.choices]}}
        elif isinstance(field, forms.BooleanField):
            schema = {'type': 'boolean'}
            if field.required:
                schema['const'] = True
        elif isinstance(field, forms.IntegerField):
            schema = {'type': 'integer'}
            for key, value in [('minimum', field.min_value), ('maximum', field.max_value)]:
                if value is not None:
                    schema[key] = value
        else:
            schema = {'type': 'string'}
            if getattr(field, 'max_length', None) is not None:
                schema['maxLength'] = field.max_length
            if isinstance(field, forms.EmailField):
                # Empty optional email is valid; RFC format alone would reject it.
                schema['description'] = 'Valid email when non-empty.'
            if isinstance(field, forms.ChoiceField):
                choices = [v for v, _ in field.choices if v != '']
                schema['enum'] = choices if field.required else ['', *choices]
            if field.required:
                schema['minLength'] = 1
        if isinstance(field, forms.IntegerField):
            validators = list(field.validators)
            if getattr(instance, '_meta', None) and name in {f.name for f in instance._meta.model._meta.fields}:
                validators += instance._meta.model._meta.get_field(name).validators
            for validator in validators:
                if isinstance(validator, (MinValueValidator, MaxValueValidator)):
                    value = validator.limit_value
                    if callable(value):
                        value = value()
                    key = 'minimum' if isinstance(validator, MinValueValidator) else 'maximum'
                    combine = max if key == 'minimum' else min
                    schema[key] = combine(value, schema.get(key, value))
        schema['x-django-field'] = type(field).__name__
        properties[name] = schema
        if field.required:
            required.append(name)
    properties['csrfmiddlewaretoken'] = CSRF
    result = object_schema(properties, required, additionalProperties=True, **{'x-form-class': cls.__module__ + '.' + cls.__name__})
    if 'skills' in properties:
        properties['skills']['description'] = SKILLS_NOTE
    return result


def schemas():
    result = {name: form_schema(cls) for name, cls in FORM_CLASSES.items()}
    register = result['Registration']
    register['required'].append('email')  # clean_email rejects empty despite model blank=True.
    register['properties']['email']['description'] = 'Unique @demo.invalid address, trimmed/lowercased. No real email is sent.'
    register['properties']['password1']['description'] = 'Minimum configured length 8; common passwords rejected; must equal password2.'
    register['properties']['password1']['minLength'] = 8
    register['properties']['password2']['minLength'] = 8
    register['properties']['password2']['description'] = 'Must equal password1.'
    result['Login']['properties']['next'] = {'type': 'string', 'description': 'Optional safe redirect on same host; unsafe destination replaced by /.'}
    result['Profile']['properties']['name']['description'] = 'Letters, spaces, hyphens; required when published=true.'
    result['Profile']['properties']['city']['description'] = 'Letters, spaces, hyphens; contacts belong in private fields.'
    result['Profile']['properties']['published']['description'] = 'Separate publication consent. Omitted checkbox is false; accepted invitation grants survive unpublishing.'
    result['Profile']['properties']['description']['description'] = 'Private until this company has an accepted invitation. Plain text, not HTML.'
    result['Profile']['properties']['specialization']['description'] = 'Empty/omitted becomes ios_swift.'
    result['Profile']['properties']['experience_months']['description'] = 'Omitted/empty becomes 0; self-reported.'
    result['Profile']['properties'].update({
        'experience-TOTAL_FORMS': {'type': 'integer', 'minimum': 0, 'maximum': 20},
        'experience-INITIAL_FORMS': {'type': 'integer', 'minimum': 0, 'maximum': 20},
        'experience-MIN_NUM_FORMS': {'type': 'integer', 'minimum': 0},
        'experience-MAX_NUM_FORMS': {'type': 'integer', 'minimum': 0}})
    result['Profile']['patternProperties'] = {
        r'^experience-[0-9]+-(organization|role)$': {'type': 'string', 'maxLength': 120},
        r'^experience-[0-9]+-months$': {'type': 'integer', 'minimum': 0, 'maximum': 600},
        r'^experience-[0-9]+-description$': {'type': 'string', 'maxLength': 2000},
        r'^experience-[0-9]+-(id|profile)$': OPTIONAL_ID,
        r'^experience-[0-9]+-DELETE$': {'type': 'boolean'}}
    result['Profile']['description'] = 'Experience formset is validated only when TOTAL_FORMS is present; INITIAL_FORMS then required. At most 20 entries. Empty extra rows are skipped; existing id must be owned; hidden profile must match own Profile if present. Any error prevents the entire profile/formset save.'
    result['Need']['description'] = 'salary_min/max are positive rubles before tax per month; max >= min. Creates a new Need and updates own company name/email. No edit of existing Need.'
    result['Need']['properties']['recruiter']['description'] = 'Optional HR of own Company; empty means unassigned. Invitation stores current HR separately; reassigning Need does not rewrite old invitations.'
    result['FspConnect']['properties']['external_id']['pattern'] = r'^DEMO-(?:(?!000)[0-9]{3}|EMPTY|DOWN)$'
    result['FspConnect']['description'] = 'Explicit fsp-mock-v1 consent; external ID unique in this app, not verified by a real registry.'
    result.update({
        'CsrfOnly': object_schema({'csrfmiddlewaretoken': CSRF}, additionalProperties=True),
        'Confirmation': object_schema({'token': {'type': 'string', 'minLength': 1, 'writeOnly': True}, 'csrfmiddlewaretoken': CSRF}, ['token'], additionalProperties=True),
        'FspAction': {'anyOf': [ref('FspConnect'), object_schema({'action': {'const': 'unlink'}, 'csrfmiddlewaretoken': CSRF}, ['action'], additionalProperties=True)]},
        'StartAttempt': object_schema({'grade': GRADE, 'csrfmiddlewaretoken': CSRF}, ['grade'], additionalProperties=True),
        'Answers': object_schema({'csrfmiddlewaretoken': CSRF}, additionalProperties=True,
            patternProperties={r'^q_.+$': {'type': 'integer', 'minimum': 0, 'maximum': 3}},
            description='q_<task-id> from this attempt, choice 0..3. Missing answers remain stored/unanswered. Non-q_ fields ignored; unknown task/invalid answer gives 302 + message with no partial save.'),
        'Invitation': object_schema({'need': ID, 'candidate': ID, 'accepted_attempts': {'type': 'array', 'maxItems': 20, 'items': ID},
            'discussion': {'type': 'string', 'maxLength': 2000}, 'csrfmiddlewaretoken': CSRF}, ['need', 'candidate'], additionalProperties=True,
            description='Own Need, published candidate of same category. Selected results must be finished, owned by candidate, same grade; employer explicitly accepts them. Contact company email required for a new invitation.'),
        'Assistant': object_schema({'mode': {'type': 'string', 'enum': ['profile','need','result','matching','invitation','conversation']},
            'identifier': OPTIONAL_ID, 'new_need': {'type': 'string', 'enum': ['on', '']}, 'grade': {'type': 'string', 'enum': ['', 'Junior','Middle']},
            'skills': {'type': 'string', 'maxLength': 200, 'description': SKILLS_NOTE}, 'need': OPTIONAL_ID, 'candidate': OPTIONAL_ID, 'invitation': OPTIONAL_ID, 'csrfmiddlewaretoken': CSRF}, additionalProperties=True,
            description='Mode default depends on role. profile/result: candidate; need/matching/invitation: employer; conversation: either role. Matching/invitation require need + candidate; conversation requires invitation. Partial stage selection GET shows form; POST returns 400 before ownership resolution. Complete stage selection resolves ownership/visibility. For result identifier selects own finished attempt, else latest. For need identifier selects own Need, else last unless new_need=on; a new employer may start without Company/Need.'),
        'DraftApply': {'anyOf': [ref('ProfileDraft'), ref('Need')], 'description': 'Actual stored Draft.mode selects the form. Profile applies description only; need creates a new own Need. Body cannot choose mode/owner/grade of Profile.'},
        'TeamAction': {'anyOf': [object_schema({**result['Recruiter']['properties'],'action':{'const':'add'}},['action','name'],additionalProperties=True),
            object_schema({**result['Assignment']['properties'],'action':{'const':'assign'}},['action','need'],additionalProperties=True)]},
        'TokenAction': {'anyOf': [object_schema({**result['Token']['properties'],'action':{'const':'create'}},['action','name','kind'],additionalProperties=True),
            object_schema({'action':{'const':'revoke'},'id':ID,'csrfmiddlewaretoken':CSRF},['action','id'],additionalProperties=True)],
            'description':'Create displays token once in no-store HTML. MCP cannot request contacts. Revoke only own token; repeated revoke is safe. Draft scope may be reserved before V2 paths exist.'},
        'ClientArtifact': object_schema({'filename':{'type':'string'},'bytes':{'type':'integer','minimum':1},'sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'}},['filename','bytes','sha256'],additionalProperties=False),
        'ClientManifest': object_schema({'version':{'type':'string','minLength':1},'commit':{'type':'string','pattern':'^[0-9a-f]{40}$'},'files':{'type':'array','minItems':2,'maxItems':2,'items':ref('ClientArtifact')}},['version','commit','files'],additionalProperties=False,
            description='Actual wheel and source archive of this client version; hashes and byte sizes checked by build_client_release.py and contract verifier.'),
        'HealthOk': object_schema({'status': {'const': 'ok'}}, ['status'], additionalProperties=False),
        'HealthUnavailable': object_schema({'status': {'const': 'unavailable'}}, ['status'], additionalProperties=False),
        'Version': object_schema({'commit': {'type': 'string', 'pattern': '^[0-9a-f]{40}$'}, 'assistant_mode': {'const': 'mock'}}, ['commit','assistant_mode'], additionalProperties=False),
        'FspEvent': object_schema({'event_id': {'type': 'string'}, 'source': {'const': 'mock'}, 'event_name': {'type': 'string'},
            'occurred_on': {'type': 'string', 'format': 'date'}, 'discipline': {'type': 'string'}, 'result': {'type': 'string'}, 'team': {'type': 'boolean'}, 'prize': {'type': 'boolean'}},
            ['event_id','source','event_name','occurred_on','discipline','result','team','prize'], additionalProperties=False),
        'FspHistory': object_schema({'source': {'const': 'mock'}, 'status': {'type': 'string', 'enum': ['not_connected','no_history','demo_history','unavailable']},
            'changes_grade': {'const': False}, 'external_id': {'type': ['string','null']}, 'events': {'type': 'array','items': ref('FspEvent')}},
            ['source','status','changes_grade','external_id','events'], additionalProperties=False)})
    return result


FORM_CLASSES = {'Registration': RegistrationForm, 'Login': AccessibleAuthenticationForm, 'Consent': ConsentForm,
    'Profile': ProfileForm, 'FspConnect': FspLinkForm, 'Company': CompanyForm, 'Need': NeedForm,
    'NeedPrompt': NeedPromptForm, 'ProfileDraft': ProfileDraftForm,'Recruiter':RecruiterForm,'Assignment':AssignmentForm,'Token':TokenForm}


def endpoint(path, methods, role, summary, detail, statuses, *, body=None, query=None, repeat='', effects=''):
    return dict(path=path, methods=methods.split(), role=role, summary=summary, detail=detail, statuses=statuses,
                body=body, query=query or {}, repeat=repeat, effects=effects)


# Statuses are explicit reviewed semantics, never inferred from a green response.
ENDPOINTS = {
    'integrations': endpoint('/accounts/integrations/','GET POST','both','Персональные подключения CLI/MCP',
        'Own tokens only. Processing consent is checked before confirmed/active account here. Create action validates name/kind/contact/draft scopes, stores digest, shows secret once in no-store/no-referrer HTML. MCP contacts rejected. Revoke requires own positive id. No automatic web action from token.',
        {200:'GET list or successful create with one-time secret',400:'Invalid create form/action',302:'Revoke: /accounts/integrations/',404:'Malformed/foreign token id'},body='TokenAction',repeat='Create issues another token; revoke remains revoked on repeat.'),
    'owner-dashboard': endpoint('/company/dashboard/','GET','employer','Дашборд владельца',
        'Owned cohorts by send date; accepted conversion is current outcomes of same cohort. Period=7/30/90/all, hr=own positive ID or unassigned, need=own positive ID. Read does not create Company. No contact data. Seven-day overdue is reporting, not automatic expiry.',
        {200:'Dashboard HTML',404:'Invalid period/foreign or malformed filter'},query={'period':{'type':'string','enum':['7','30','90','all'],'default':'30'},'hr':{'anyOf':[OPTIONAL_ID,{'const':'unassigned'}]},'need':OPTIONAL_ID}),
    'company-team': endpoint('/company/team/','POST','employer','Команда и ответственный HR',
        'action=add creates own Recruiter from name. action=assign updates recruiter on own Need only; empty recruiter clears assignment. Existing invitation recruiter attribution is unchanged. Invalid fields show message and redirect, unknown action is 404.',
        {302:'Success/form error: /company/dashboard/',404:'Unknown action'},body='TeamAction',repeat='Add creates another Recruiter; assign repeats safely.',effects='POST can create own Company if absent.'),
    'download-client': endpoint('/downloads/{filename}','GET HEAD','public','Артефакты CLI',
        'Only manifest.json, current-version fsp_client-<version>-py3-none-any.whl and fsp_client-<version>.tar.gz from owned .runtime/downloads. Missing/unknown artifact 404. No database or authentication; no arbitrary path reads.',
        {200:'Versioned artifact attachment; manifest application/json, wheel octet-stream, tar.gz application/gzip',404:'Missing/unknown artifact'}),
    'home': endpoint('/', 'GET HEAD', 'public', 'Главная / кабинет', 'Anonymous sees welcome. Candidate redirects /profile/; employer sees cabinet. Authenticated without processing-v1 redirects /accounts/consent/.', {200:'Welcome/employer cabinet',302:'Own profile or consent'}, repeat='Same route choice; no business write.'),
    'privacy': endpoint('/accounts/privacy/', 'GET HEAD', 'public', 'Правила обработки', 'Public processing-v1 and publication rules.', {200:'Privacy HTML'}),
    'register': endpoint('/accounts/register/', 'GET POST', 'public', 'Демонстрационная регистрация', 'Only demo.invalid; explicit processing consent. Creates inactive user, candidate Profile if applicable, pending registration in this session and 30-minute one-use demo confirmation.', {200:'GET form or invalid POST, no user created on error',302:'Valid POST: /accounts/confirm/'}, body='Registration', repeat='Duplicate email: 200 form error. Not an idempotent creation endpoint.'),
    'confirm': endpoint('/accounts/confirm/', 'GET POST', 'pending-session', 'Подтверждение demo email', 'GET requires pending session. POST requires same pending user + nonce and unexpired unused token. Successful confirmation activates/login user and clears pending state. Does not prove real mailbox ownership.', {200:'GET demo token/form',302:'Valid POST: /',400:'Wrong/expired token with pending session',404:'No pending session'}, body='Confirmation', repeat='After success pending session is cleared; repeat is 404.'),
    'login': endpoint('/accounts/login/', 'GET POST HEAD OPTIONS', 'public', 'Вход', 'Django authentication, including active-account check. next is limited to allowed same host. GET/HEAD form; POST errors stay 200. OPTIONS empty response with Allow. PUT explicitly rejected.', {200:'Form/error or empty OPTIONS',302:'Valid login to safe next or /'}, body='Login', query={'next': {'type':'string'}}, repeat='Already authenticated GET shows form (redirect_authenticated_user=False); POST rotates session/CSRF.'),
    'logout': endpoint('/accounts/logout/', 'POST OPTIONS', 'public', 'Выход', 'POST with CSRF clears browser session; anonymous valid POST also redirects. OPTIONS returns empty Allow response.', {200:'OPTIONS empty',302:'POST: /'}, body='CsrfOnly', repeat='Valid repeated POST redirects / without restoring session.'),
    'consent': endpoint('/accounts/consent/', 'GET POST', 'authenticated', 'Согласие processing-v1', 'Authenticated user. Email confirmation is not a separate guard here. Explicit checked boolean is required; processing consent event recorded by service.', {200:'GET/form error',302:'POST success: /'}, body='Consent', repeat='Reconfirming current consent does not duplicate identical event.'),
    'profile': endpoint('/profile/', 'GET POST', 'candidate', 'Собственный профиль', 'Confirmed candidate with processing consent. Only own Profile. Skills canonicalized; name/city exclude contact syntax. A publication transition records a separate consent event. Free text/experience/contact are private until the receiving company has an accepted invitation.', {200:'GET or any form/formset validation error',302:'Valid save: /profile/'}, body='Profile', repeat='Replaces current fields; omitted checkbox false. Same publication state does not duplicate consent.'),
    'resume': endpoint('/profile/resume.pdf', 'GET HEAD', 'candidate', 'Собственный PDF', 'Own candidate PDF with private descriptions, experience and contacts. Cyrillic font embedded. HEAD has headers only.', {200:'application/pdf attachment'}),
    'fsp': endpoint('/profile/fsp/', 'GET HEAD', 'candidate', 'Своя demo история ФСП', 'JSON only for owner; changes_grade=false for all states; dates ISO YYYY-MM-DD. Mock identity is not a registry verification.', {200:'FspHistory JSON'}),
    'fsp-link': endpoint('/profile/fsp/link/', 'GET POST', 'candidate', 'Привязка / отзыв demo FSP ID', 'DEMO-001..999 history, DEMO-EMPTY none, DEMO-DOWN unavailable. Explicit consent; unique external ID. action=unlink bypasses connect fields and removes own achievements/bonus, preserving grade.', {200:'GET/form error, invalid or occupied external ID',302:'Connect/unlink success: /profile/fsp/link/'}, body='FspAction', repeat='Connect refreshes without duplicate events; unlink already disconnected is safe.'),
    'company-profile': endpoint('/company/', 'GET POST', 'employer', 'Профиль компании', 'Only own Company. Email may remain empty here, but new invitation requires a valid email. Editing Company never rewrites old invitation snapshots.', {200:'GET/form error',302:'Save: /company/'}, body='Company', repeat='Same POST updates own Company.', effects='GET may lazily create own Company if absent.'),
    'needs': endpoint('/company/needs/', 'GET POST', 'employer', 'Потребности компании', 'Lists own Needs. Valid POST creates one new Need and updates own Company name/email; salary max >= min required.', {200:'GET/form error',302:'Creation: /candidates/'}, body='Need', repeat='Repeated valid POST creates another Need; no idempotency token.', effects='GET may lazily create own Company if absent.'),
    'candidates': endpoint('/candidates/', 'GET HEAD', 'employer', 'Фильтры и рейтинг', 'Owned need defaults to first own Need; grade defaults to selected need grade else Junior. grade must match chosen Need. Invalid grade/skill/fsp/mismatch displays 200 empty result with form error. Current specialisation is iOS/Swift. Declared match and test witness separated.', {200:'Search HTML, including invalid filter form',404:'Malformed/foreign selected need'}, query={'need':OPTIONAL_ID,'grade':{'type':'string','enum':['','Junior','Middle']},'skill':{'type':'string','description':SKILLS_NOTE},'fsp':{'type':'string','enum':['','no_history','demo_history']}}, effects='GET may lazily create own Company if absent.'),
    'candidate': endpoint('/candidates/{pk}/', 'GET HEAD', 'employer', 'Доступная карточка кандидата', 'Visible when published + confirmed category OR this Company has an accepted invitation. Private texts/contacts only under that Company grant. Optional need must be own; absent selects first own matching-grade need. Safe finished witnesses of current grade.', {200:'Candidate HTML with grant-aware fields',404:'Invisible/missing candidate or malformed/foreign need'}, query={'need':OPTIONAL_ID}, effects='May lazily create own Company.'),
    'candidate-resume': endpoint('/candidates/{pk}/resume.pdf', 'GET HEAD', 'employer', 'PDF доступного кандидата', 'Same visibility and contact grant as HTML, including old grant after unpublishing. No contact leak in PDF without acceptance.', {200:'application/pdf attachment',404:'Invisible/missing candidate'}, effects='May lazily create own Company.'),
    'invitations': endpoint('/invitations/', 'GET HEAD', 'both', 'Свои предложения', 'Candidate sees own invitations; employer sees own Company invitations. No cross-candidate data. Immutable conditions snapshot.', {200:'Invitation list'}, effects='Candidate GET/HEAD sets viewed_at for unseen items. Employer read may lazily create own Company.'),
    'invitation-send': endpoint('/invitations/send/', 'POST', 'employer', 'Явная отправка предложения', 'Need must be owned, candidate published and same category. New invitation requires Company email. Proof IDs belong to this candidate and are finished of the same grade (failed proof may be explicitly selected). Snapshot includes conditions/contact company/selected witnesses/discussion. No contacts of candidate opened yet.', {302:'Success/duplicate: /invitations/; missing company email: /company/; invalid proof/discussion: /candidates/{id}/ with message',404:'Malformed/foreign need/candidate/proof ID or >20 proof IDs'}, body='Invitation', repeat='Unique (candidate,need). Duplicate preserves initial snapshot; route still requires candidate published/same current grade, and parses IDs before service duplicate check.'),
    'invitation-accept': endpoint('/invitations/{pk}/accept/', 'POST', 'candidate', 'Принять своё предложение', 'Only own invitation. sent -> accepted opens contact grant for sender Company only. Opposite terminal decision leaves state and displays message.', {302:'All owned decisions: /invitations/',404:'Missing/foreign invitation'}, body='CsrfOnly', repeat='Same terminal decision safe; opposite rejected by message + 302.'),
    'invitation-decline': endpoint('/invitations/{pk}/decline/', 'POST', 'candidate', 'Отклонить своё предложение', 'Only own invitation. sent -> declined keeps contacts closed. Opposite terminal decision leaves state and displays message.', {302:'All owned decisions: /invitations/',404:'Missing/foreign invitation'}, body='CsrfOnly', repeat='Same terminal decision safe; opposite rejected by message + 302.'),
    'assessments': endpoint('/assessments/', 'GET HEAD', 'candidate', 'История и выбор теста', 'Only own attempts and profile category. No answer keys exposed.', {200:'Dashboard HTML'}),
    'assessment-start': endpoint('/assessments/start/', 'POST', 'candidate', 'Начать / продолжить попытку', '8 questions, four areas, 15 minutes. A/B first distribution and later rotation; shuffled options. Invalid grade, 7-day repeat, 30-day category change and downgrade from Middle yield message + redirect. Expired active attempt is finalized before next eligibility check.', {302:'Attempt URL on success/active reuse; /assessments/ on refused start'}, body='StartAttempt', repeat='Active unexpired attempt reused (even if another valid grade requested); otherwise cooldown/rules apply.'),
    'attempt': endpoint('/assessments/{pk}/', 'GET HEAD', 'candidate', 'Своя попытка / результат', 'Owned attempt only. Active HTML shows id/area/prompt/options/selected, never correct keys. Finished HTML shows persisted result.', {200:'Active/result HTML',404:'Missing/foreign attempt'}),
    'assessment-answer': endpoint('/assessments/{pk}/answer/', 'POST', 'candidate', 'Сохранить ответы', 'Valid own snapshot questions q_ID, options 0..3. No scoring/grade accepted from browser. Unknown question/invalid answer rejects entire write. Expired save rejected. Repeated finished attempt returns existing result.', {302:'Own attempt URL with success/error message',404:'Missing/foreign attempt'}, body='Answers', repeat='Replaces submitted answers within active deadline; finished safe no-op.'),
    'assessment-finish': endpoint('/assessments/{pk}/finish/', 'POST', 'candidate', 'Завершить попытку', 'Server scores >=6/8 and >=1 per area. Failed result does not demote. Expired finish ignores late submitted answers and uses already saved answers. Invalid current answers give message and keep active. Snapshot bank/rules immutable.', {302:'Own attempt URL with result/error',404:'Missing/foreign attempt'}, body='Answers', repeat='Finished attempt is idempotent; ignores repeated body, score/category not rewritten.'),
    'assessment-proof': endpoint('/assessments/{pk}/proof/', 'GET HEAD', 'both', 'Безопасное свидетельство', 'Finished own candidate attempt; employer requires visible profile and current grade. Witness fields: attempt_id/specialization/grade/finished_at/bank_version/rules_version/variant/areas/correct_count/total/passed/expired/criteria/limitations. No tasks/answers/keys.', {200:'HTML witness',404:'Foreign/invisible/active/wrong-grade attempt'}, effects='Employer may lazily create own Company.'),
    'assistant': endpoint('/assistant/', 'GET POST', 'both', 'Мок помощника и черновики', 'GET displays mode/selection and last ten own drafts, no provider call. POST profile/need creates private 24-hour Draft only; result/matching/conversation read allowed context. invitation preview has a separate explicit send form. Contacts/free private text/question keys excluded from provider. Usage 10/hour; failed provider calls count; active candidate test blocks POST.', {200:'Mode form/editor/mock result',400:'Invalid prompt or missing result/stage context',404:'Malformed/foreign/invisible explicit ID',409:'Candidate active assessment',429:'10/hour generation limit',503:'Provider failure; manual forms remain available'}, body='Assistant', query={'mode':{'type':'string','enum':['profile','need','result','matching','invitation','conversation']},'need':OPTIONAL_ID,'attempt':OPTIONAL_ID,'candidate':OPTIONAL_ID,'invitation':OPTIONAL_ID}, repeat='POST generation consumes usage and may create another Draft; never sends invitation/changes category.'),
    'assistant-draft': endpoint('/assistant/drafts/{pk}/', 'GET POST', 'both', 'Проверить / применить свой черновик', 'Own Draft + mode matches role. GET editor/status even after expiry. POST checked description or NeedForm, explicit browser action. Source Need deletion allowed; source reassignment/profile description conflict denied. No user-selected mode/owner/source/applied ID. Applying does not consume generation usage.', {200:'GET editor/status',302:'Applied profile: /profile/; need: /company/needs/',400:'Invalid editable fields, no partial write',404:'Foreign/missing Draft',409:'Stale source/description or active candidate test',410:'Expired unapplied Draft'}, body='DraftApply', repeat='Applied Draft POST redirects without second write or validation, even after expiry; candidate active test guard still 409.'),
    'health': endpoint('/health/', 'GET HEAD', 'public', 'Готовность БД', 'Read queries required tables. DatabaseError -> 503 without secrets. Not a full user journey or liveness/reboot proof.', {200:'HealthOk JSON',503:'HealthUnavailable JSON'}),
    'version': endpoint('/version/', 'GET HEAD', 'public', 'Версия выпуска', '40-character Git SHA from deployed REVISION or local Git HEAD; mock mode. No configuration/tokens returned.', {200:'Version JSON'}),
}

EXAMPLES = {
    'Recruiter':{'name':'Рекрутер'},'Assignment':{'need':1},'Token':{'name':'Локальный CLI','kind':'cli','contacts':False,'drafts':False},
    'TeamAction':{'action':'add','name':'Рекрутер'},'TokenAction':{'action':'create','name':'Локальный CLI','kind':'cli','contacts':False,'drafts':False},
    'Registration': {'email':'contract@demo.invalid','role':'candidate','password1':'Demo-Contract-934!','password2':'Demo-Contract-934!','processing_consent':True},
    'Login': {'username':'contract@demo.invalid','password':'Demo-Contract-934!'},
    'Consent': {'processing_consent':True},
    'Profile': {'name':'Анна','city':'Москва','skills':'Swift, Core Data','specialization':'ios_swift','experience_months':12,'roles':['developer','reviewer'],'soft_skills':['teamwork'],'description':'Приватное описание','contact_email':'contact@demo.invalid','contact_phone':'+70000000000','desired_grade':'Junior','published':True},
    'Company': {'name':'Демо компания','industry':'Мобильная разработка','description':'Тестовый продукт','contact_email':'company@demo.invalid'},
    'Need': {'title':'iOS разработчик','grade':'Junior','skills':'Swift','tasks':'Разработка экрана приложения','salary_min':90000,'salary_max':120000,'work_format':'remote','next_step':'Знакомство с командой','company_name':'Демо компания','company_email':'company@demo.invalid'},
    'NeedPrompt': {'grade':'Junior','skills':'Swift'}, 'ProfileDraft': {'description':'Проверенное приватное описание'},
    'CsrfOnly': {}, 'Confirmation': {'token':'DEMO_TOKEN_FROM_YOUR_PENDING_SESSION'}, 'FspAction': {'external_id':'DEMO-001','consent':True},
    'StartAttempt': {'grade':'Junior'}, 'Answers': {}, 'Invitation': {'need':1,'candidate':1,'accepted_attempts':[],'discussion':'Обсудим задачи'},
    'Assistant': {'mode':'need','new_need':'on','grade':'Junior','skills':'Swift'}, 'DraftApply': {'description':'Проверенное приватное описание'},
}


def build_spec():
    spec = {'openapi':'3.1.1','info':{'title':'FSP demo: browser HTTP contracts','version':'0.1.0',
        'description':'Django browser forms + session/CSRF; JSON read routes and PDF. Not a REST backend. Only demo identities and mock FSP/AI. Live URL comes from LLM Love status; the portal is not the backend.'},
        'servers':[{'url':'http://127.0.0.1:{port}','variables':{'port':{'default':'8041','description':'Your isolated worktree port; production URL from the portal status.'}}}],
        'components':{'securitySchemes':{'Session':{'type':'apiKey','in':'cookie','name':'sessionid'},'CsrfCookie':{'type':'apiKey','in':'cookie','name':'csrftoken'}},'schemas':schemas()},'paths':{}}
    for name, entry in ENDPOINTS.items():
        operations = {}
        for method in entry['methods']:
            protected = entry['role'] in {'candidate','employer','both','authenticated'}
            op = {'operationId':name.replace('-','_')+'_'+method.lower(),'summary':entry['summary']+' · '+method,
                'description':entry['detail']+'\nRepeat: '+entry['repeat']+'\nRead effects: '+(entry['effects'] or 'No business write on GET/HEAD.'),
                'x-django-url-name':name if name!='download-client' else None,'x-role':entry['role'],'x-repeat':entry['repeat'],'x-read-effects':entry['effects'],
                'security':[{'Session':[]}] if protected or entry['role']=='pending-session' else [],'responses':{},'parameters':[]}
            if '{pk}' in entry['path']:
                op['parameters'].append({'name':'pk','in':'path','required':True,'schema':ID})
            if '{filename}' in entry['path']:
                op['parameters'].append({'name':'filename','in':'path','required':True,'schema':{'type':'string','description':'One allowed current-version artifact filename; slashes forbidden by route converter.'}})
            if method in {'GET','HEAD'}:
                op['parameters'] += [{'name':key,'in':'query','required':False,'schema':schema} for key,schema in entry['query'].items()]
            statuses = dict(entry['statuses'])
            if protected:
                statuses.setdefault(302,'Unauthenticated: /accounts/login/?next=<path>; missing processing-v1: /accounts/consent/. Role/email checked before consent.')
                if entry['role'] != 'authenticated':
                    statuses[403]='Wrong role/unconfirmed email; POST additionally invalid CSRF.'
            statuses[405]='Unsupported method for an authorized caller; Allow lists supported methods. Middleware CSRF or outer authentication may reject first.'
            if method == 'POST':
                statuses.setdefault(403,'Missing/mismatched csrf cookie + header/form token.')
                op['security'] = [{'Session':[],'CsrfCookie':[]}] if protected or entry['role']=='pending-session' else [{'CsrfCookie':[]}]
                op['parameters'].append({'name':'X-CSRFToken','in':'header','required':False,'schema':CSRF,'description':'Alternative to csrfmiddlewaretoken form field; csrf cookie still required.'})
                op['x-csrf']='Cookie plus same-session header OR form token; session/CSRF rotate at login. application/json is not parsed into request.POST; 415 is not promised.'
                if entry['body']:
                    media={'schema':ref(entry['body']),'examples':{'valid_shape':{'value':EXAMPLES[entry['body']]}}}
                    body_schema=spec['components']['schemas'][entry['body']]
                    arrays={key:{'style':'form','explode':True} for key,value in body_schema.get('properties',{}).items() if value.get('type')=='array'}
                    if arrays:media['encoding']=arrays
                    op['requestBody']={'required':True,'content':{'application/x-www-form-urlencoded':copy.deepcopy(media),'multipart/form-data':copy.deepcopy(media)}}
            for status, description in statuses.items():
                # Some statuses apply only to one method; authentication is retained for every protected method.
                if method in {'GET','HEAD'} and status in {400,409,410,429}:continue
                if method in {'GET','HEAD'} and status==302 and name in {'register','confirm','login'}:continue
                if name=='assistant' and method=='GET' and status==503:continue
                if name=='assistant-draft' and method=='GET' and status==302:description='Authentication or consent redirect only; editor never applies on GET.'
                if method=='POST' and name in {'register','confirm','consent','profile','company-profile','needs','fsp-link','assistant-draft'} and status==200:
                    if name in {'confirm','assistant-draft'}:continue
                if name=='logout' and method=='POST' and status==200:continue
                if method=='OPTIONS' and status not in {200,405}:continue
                response={'description':description}
                if method=='HEAD' and status not in {302,405}:
                    media_type='application/json' if name in {'health','version','fsp'} and status in {200,503} else 'application/pdf' if name in {'resume','candidate-resume'} and status==200 else 'text/html; charset=utf-8'
                    response['headers']={'Content-Type':{'required':True,'schema':{'const':media_type}}}
                    if media_type=='application/pdf':response['headers']['Content-Disposition']={'required':True,'schema':{'type':'string'}}
                    if name=='download-client':response['headers']={'Content-Disposition':{'required':True,'schema':{'type':'string'}}} if status==200 else {}
                if status in {302,405}:
                    header='Location' if status==302 else 'Allow'
                    response['headers']={header:{'required':True,'schema':{'type':'string'}}}
                if method not in {'HEAD','OPTIONS'} and status not in {302,405}:
                    schema_name = {'health':'HealthOk' if status==200 else 'HealthUnavailable','version':'Version','fsp':'FspHistory'}.get(name) if status in {200,503} else None
                    if schema_name:
                        response['content']={'application/json':{'schema':ref(schema_name)}}
                    elif status==200 and name in {'resume','candidate-resume'}:
                        response['content']={'application/pdf':{}}
                        response['headers']={'Content-Disposition':{'required':True,'schema':{'type':'string'}}}
                    elif status==200 and name=='download-client':
                        response['content']={'application/octet-stream':{},'application/gzip':{},'application/json':{'schema':ref('ClientManifest')}}
                        response['headers']={'Content-Disposition':{'required':True,'schema':{'type':'string'}},'Cache-Control':{'required':True,'schema':{'const':'no-cache'}}}
                    else:response['content']={'text/html':{'schema':{'type':'string'}}}
                if name=='integrations' and status in {200,400}:
                    response['headers']={'Cache-Control':{'required':True,'schema':{'const':'no-store'}},'Referrer-Policy':{'required':True,'schema':{'const':'no-referrer'}}}
                if method=='OPTIONS' and status==200:response['headers']={'Allow':{'required':True,'schema':{'type':'string'}}}
                op['responses'][str(status)]=response
            operations[method.lower()]=op
        spec['paths'][entry['path']]=operations
    add_token_api(spec)
    return spec


def add_token_api(spec):
    """Preserve the API module's reviewed DTOs, namespaced away from browser forms."""
    from api.schema import document
    api=copy.deepcopy(document())
    def rename(obj):
        if isinstance(obj,list):return [rename(v) for v in obj]
        if isinstance(obj,dict):return {k:v.replace('#/components/schemas/','#/components/schemas/Api') if k=='$ref' else rename(v) for k,v in obj.items()}
        return obj
    spec['components']['schemas'].update({'Api'+name:rename(value) for name,value in api['components']['schemas'].items()})
    spec['components']['securitySchemes'].update(api['components']['securitySchemes'])
    error={'description':'Token API error boundary, no HTML redirect or session/CSRF. See error.code; not every status applies to every route.',
        'content':{'application/json':{'schema':ref('ApiError')}}}
    for path,operations in api['paths'].items():
        full='/api/v1'+path.replace('{id}','{pk}')
        for method,op in operations.items():
            op=rename(op);op['operationId']='token_'+op.get('operationId',full.strip('/').replace('/','_').replace('{pk}','id'))
            op['security']=[{'BearerToken':[]}];op['x-contract-group']='token-api';op['x-django-url-name']=None
            op['description']='Bearer token with role/scope checks; 60/minute, 30-day expiry. MCP omits private/free text, contacts and PDF. No business write on GET; token usage/last_used updated. No cookie authentication or CSRF. IDs use same bounded positive parser; malformed/foreign IDs 404. '+'; '.join(op.get('x-required-scopes',[]))
            for parameter in op.get('parameters',[]):
                if parameter['in']=='path':parameter['name']='pk'
            for status in [400,401,403,404,405,429,503,500]:op['responses'].setdefault(str(status),copy.deepcopy(error))
            for status,response in op['responses'].items():
                response.setdefault('headers',{}).update({'Cache-Control':{'required':True,'schema':{'const':'no-store'}},'X-Request-ID':{'required':True,'schema':{'type':'string','format':'uuid'}}})
                if status=='401':response['headers']['WWW-Authenticate']={'required':True,'schema':{'const':'Bearer'}}
                if status=='405':response['headers']['Allow']={'required':True,'schema':{'const':', '.join(m.upper() for m in operations)}}
                if status=='429':response['headers']['Retry-After']={'required':True,'schema':{'const':'60'}}
                if 'application/pdf' in response.get('content',{}):response['content']['application/pdf']={}
            spec['paths'].setdefault(full,{})[method]=op
    # Schema endpoint and explicit JSON 404 fallbacks are also part of the URL tree.
    common={str(status):copy.deepcopy(error) for status in [401,403,404,405,429,503,500]}
    for path in ['/api/v1/openapi.json','/api/v1/','/api/v1/{unknown}']:
        op={'operationId':'token_'+('openapi' if path.endswith('json') else 'fallback_root' if path.endswith('/') else 'fallback_path'),
            'security':[{'BearerToken':[]}],'x-contract-group':'token-api','x-django-url-name':None,
            'summary':'Token schema' if path.endswith('json') else 'Unknown token route',
            'description':'Same token authentication, rate limit and JSON error boundary as /api/v1/me. Unknown route GET returns 404 after valid auth; unsupported method 405.',
            'parameters':[],'responses':copy.deepcopy(common)}
        if path.endswith('json'):op['responses']['200']={'description':'OpenAPI of token API module','content':{'application/json':{'schema':{'type':'object','required':['openapi','info','paths','components']}}}}
        if '{unknown}' in path:op['parameters']=[{'name':'unknown','in':'path','required':True,'schema':{'type':'string','minLength':1,'description':'May contain slash; explicit known routes take precedence.'}}]
        for status,response in op['responses'].items():
            response['headers']={'Cache-Control':{'required':True,'schema':{'const':'no-store'}},'X-Request-ID':{'required':True,'schema':{'type':'string','format':'uuid'}}}
            if status=='405':response['headers']['Allow']={'required':True,'schema':{'const':'GET'}}
            if status=='401':response['headers']['WWW-Authenticate']={'required':True,'schema':{'const':'Bearer'}}
            if status=='429':response['headers']['Retry-After']={'required':True,'schema':{'const':'60'}}
        spec['paths'][path]={'get':op}
