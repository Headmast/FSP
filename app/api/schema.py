"""OpenAPI 3.1 contract for the token API, independent of historical HTML routes."""
S={'type':'string'}
I={'type':'integer'}
B={'type':'boolean'}
F={'type':'number'}
N={'type':['string','null']}

def array(items):return {'type':'array','items':items}
def obj(properties,required=None):
    return {'type':'object','properties':properties,'required':list(properties) if required is None else required,'additionalProperties':False}
def ref(name):return {'$ref':'#/components/schemas/'+name}

schemas={
 'Meta':obj({'api_version':{'const':'1'},'data_mode':{'const':'demo'},'request_id':S}),
 'Pagination':obj({'limit':I,'offset':I,'total':I}),
 'Identity':obj({'id':I,'role':{'enum':['candidate','employer']},'token_kind':{'enum':['cli','mcp']},'scopes':array(S),'expires_at':S}),
 'Profile':obj({'id':I,'name':S,'city':S,'skills':array(S),'specialization':{'const':'ios_swift'},'experience_months':I,
    'roles':array(S),'soft_skills':array(S),'published':B,'desired_grade':S,'confirmed_grade':S,'test_score':F,
    'fsp_status':S,'self_declared':array(S)}),
 'Experience':obj({'id':I,'organization':S,'role':S,'months':I,'description':S}),
 'PrivateProfile':obj({'id':I,'contact_email':S,'contact_phone':S,'description':S,'experiences':array(ref('Experience'))}),
 'Proof':obj({'attempt_id':{'type':['integer','null']},'specialization':S,'grade':S,'finished_at':N,
    'bank_version':S,'rules_version':S,'variant':N,'areas':{'type':'object','additionalProperties':I},
    'correct_count':I,'total':I,'passed':B,'expired':B,'criteria':{'type':'object','additionalProperties':I},'limitations':S}),
 'Assessment':obj({'id':I,'grade':S,'status':S,'started_at':S,'expires_at':S,'result':{'anyOf':[ref('Proof'),{'type':'null'}]}}),
 'Company':obj({'id':I,'name':S,'industry':S,'description':S},['id','name']),
 'CompanyState':obj({'state':{'enum':['ready','company_not_created']},'company':{'anyOf':[ref('Company'),{'type':'null'}]}}),
 'Need':obj({'id':I,'company_id':I,'title':S,'grade':S,'skills':array(S),'salary_min':I,'salary_max':I,
    'currency':{'const':'RUB'},'salary_period':{'const':'month'},'salary_tax':{'const':'gross'},'work_format':S,'tasks':S,'next_step':S},
    ['id','company_id','title','grade','skills','salary_min','salary_max','currency','salary_period','salary_tax','work_format']),
 'Explanation':obj({'declared_matches':array(S),'declared_gaps':array(S),'confirmation':{'anyOf':[ref('Proof'),{'type':'null'}]},'unknown':array(S)}),
 'Match':obj({'profile':ref('Profile'),'score':F,'parts':obj({'test':F,'skills':F,'fsp':F}),'explanation':ref('Explanation')}),
 'Candidate':obj({'profile':ref('Profile'),'contacts_allowed':B,'explanation':ref('Explanation')}),
 'Invitation':obj({'id':I,'candidate_id':I,'need_id':I,'company_id':I,'company':N,'title':N,'grade':S,
    'salary_min':{'type':['integer','null']},'salary_max':{'type':['integer','null']},'currency':S,'salary_period':S,'salary_tax':S,
    'work_format':N,'status':S,'created_at':S,'responded_at':N,'accepted_results':array(ref('Proof')),
    'company_description':S,'company_industry':S,'tasks':S,'next_step':S,'discussion':S},
    ['id','candidate_id','need_id','company_id','company','title','grade','salary_min','salary_max','currency','salary_period','salary_tax','work_format','status','created_at','responded_at','accepted_results']),
 'CompanyContact':obj({'company_id':I,'contact_email':S}),
 'Achievement':obj({'id':I,'source':{'const':'mock'},'event_name':S,'occurred_on':S,'team':B,'prize':B,'event_id':S,'discipline':S,'result':S},
    ['id','source','event_name','occurred_on','team','prize']),
 'Achievements':obj({'source':{'const':'mock'},'status':S,'changes_grade':{'const':False},'events':array(ref('Achievement')),'external_id':N},
    ['source','status','changes_grade','events']),
 'Catalog':obj({'specializations':array(S),'grades':array(S),'skills':array(S),'roles':{'type':'object','additionalProperties':S},
    'soft_skills':{'type':'object','additionalProperties':S},'features':array(S),'fsp_source':{'const':'mock'}}),
 'Error':obj({'error':obj({'code':S,'message':S,'details':{'type':'object'}},['code','message']),'meta':ref('Meta')})
}

# path, DTO, role, paginated, private
READ_ROUTES=[
 ('/me','Identity',None,False,False),('/catalog','Catalog',None,False,False),
 ('/me/profile','Profile','candidate',False,False),('/me/profile/private','PrivateProfile','candidate',False,True),
 ('/me/assessments','Assessment','candidate',True,False),('/me/assessments/{id}/result','Proof','candidate',False,False),
 ('/me/achievements','Achievements','candidate',False,False),('/me/company','CompanyState','employer',False,False),
 ('/needs','Need','employer',True,False),('/needs/{id}','Need','employer',False,False),
 ('/candidates','Match','employer',True,False),('/candidates/{id}','Candidate','employer',False,False),
 ('/candidates/{id}/proofs','Proof','employer',True,False),('/candidates/{id}/private','PrivateProfile','employer',False,True),
 ('/invitations','Invitation',None,True,False),('/invitations/{id}','Invitation',None,False,False),
 ('/invitations/{id}/contacts','ContactUnion',None,False,True)]
schemas['ContactUnion']={'oneOf':[ref('PrivateProfile'),ref('CompanyContact')]}


def document():
    paths={}
    for path,dto,role,paginated,private in READ_ROUTES:
        properties={'data':array(ref(dto)) if paginated else ref(dto),'meta':ref('Meta')}
        if paginated:properties['pagination']=ref('Pagination')
        params=[]
        if '{id}' in path:params.append({'name':'id','in':'path','required':True,'schema':{'type':'integer','minimum':1,'maximum':2**63-1}})
        if paginated:
            params.extend([{'name':'limit','in':'query','schema':{'type':'integer','default':20,'minimum':1,'maximum':100}},
                {'name':'offset','in':'query','schema':{'type':'integer','default':0,'minimum':0,'maximum':2**31-1}}])
        if path in {'/candidates','/candidates/{id}'}:
            params.append({'name':'need_id','in':'query','schema':{'type':'integer','minimum':1}})
        if path=='/candidates':
            params.extend([{'name':name,'in':'query','schema':schema} for name,schema in [('grade',{'enum':['Junior','Middle']}),('skill',S),('fsp_status',{'enum':['no_history','demo_history']})]])
        scope=([role+'.read'] if role else ['candidate.read OR employer.read'])+(['contacts.read; kind=cli'] if private else [])
        responses={'200':{'description':'Success; MCP omits free text and contact fields','content':{'application/json':{'schema':obj(properties)}}}}
        for status in [400,401,403,404,405,409,429,503]:responses[str(status)]={'description':'API error','content':{'application/json':{'schema':ref('Error')}}}
        paths[path]={'get':{'operationId':path.strip('/').replace('/','_').replace('{id}','by_id'),
            'parameters':params,'x-required-scopes':scope,'responses':responses}}
    for path,role in [('/me/profile/resume.pdf','candidate'),('/candidates/{id}/resume.pdf','employer')]:
        paths[path]={'get':{'x-required-scopes':[role+'.read; kind=cli','contacts.read when with_contacts=true'],
            'parameters':([{'name':'id','in':'path','required':True,'schema':I}] if '{id}' in path else [])+
                [{'name':'with_contacts','in':'query','schema':{'type':'boolean','default':False}}],
            'responses':{'200':{'description':'PDF, contacts opt-in subject to accepted grant',
                'content':{'application/pdf':{'schema':{'type':'string','format':'binary'}}}}}}}
    return {'openapi':'3.1.0','info':{'title':'FSP token API','version':'1.0.0','description':'Demo. Separate from HTML/session forms. MCP has no private/PDF/contact access.'},
        'servers':[{'url':'/api/v1'}],'security':[{'BearerToken':[]}],'paths':paths,
        'components':{'securitySchemes':{'BearerToken':{'type':'http','scheme':'bearer'}},'schemas':schemas}}
