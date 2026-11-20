import time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Booking, Invitation, Slot, User

def invitation(c,recipient,slot=1,topic=1):
    return c.post('/api/invitations',json={'recipient_id':recipient,'slot_id':slot,'topic_id':topic,'message':'Обсудим опыт?'})

def test_health_and_swagger(client):
    assert client.get('/api/health').json()=={'status':'ok'}
    assert client.get('/api/docs').status_code==200
    assert '/api/invitations' in client.get('/api/openapi.json').json()['paths']

def test_unauthorized_and_csrf(client):
    assert client.get('/api/me').status_code==401
    assert client.post('/api/auth/logout',headers={'X-Requested-With':'wrong'}).status_code==403
    assert client.post('/api/auth/logout',headers={'Origin':'https://evil.example'}).status_code==403

def test_registration_login_logout_and_no_password_leak(client):
    payload={'username':'Alice','password':'LongPass123!','name':'Алиса'}
    response=client.post('/api/auth/register',json=payload)
    assert response.status_code==201
    assert 'password' not in response.text
    assert response.json()['visible'] is False
    assert 'HttpOnly' in response.headers['set-cookie']
    assert client.post('/api/auth/register',json=payload).status_code==409
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/me').status_code==401
    assert client.post('/api/auth/login',json={'username':'alice','password':'WrongPass123!'}).status_code==401
    assert client.post('/api/auth/login',json={'username':'alice','password':'LongPass123!'}).status_code==200

def test_profile_does_not_allow_admin_overposting(account):
    c,uid=account('alice')
    r=c.put('/api/me',json={'name':'Алиса','wanted':[1],'offered':[],'availability':[1],'visible':True,'is_admin':True})
    assert r.status_code==200
    assert r.json()['is_admin'] is False
    assert c.get('/api/admin/stats').status_code==403
    assert c.post('/api/admin/slots',json={'starts_at':int(time.time())+10000,'ends_at':int(time.time())+10900,'location':'Кофе'}).status_code==403

def test_visible_profile_needs_topics_and_slot(account):
    c,_=account('alice')
    assert c.put('/api/me',json={'name':'Алиса','wanted':[],'offered':[],'availability':[],'visible':True}).status_code==422
    assert c.put('/api/me',json={'name':'Алиса','wanted':[999],'offered':[],'availability':[1],'visible':True}).status_code==422

def test_matching_explains_direction_filters_hidden_and_time(account):
    a,aid=account('alice',wanted=[1],offered=[2],available=[1])
    b,bid=account('bob',wanted=[2],offered=[1],available=[1])
    _,_=account('hidden',visible=False)
    _,_=account('other',available=[2])
    rows=a.get('/api/recommendations').json()
    assert [r['user']['id'] for r in rows]==[bid]
    assert rows[0]['learn_topics']==[1]
    assert rows[0]['share_topics']==[2]
    assert 'username' not in rows[0]['user'] and 'password_hash' not in rows[0]['user']
    assert a.get('/api/recommendations').json()==rows

def test_full_meeting_accept_and_cancel_frees_slot(account):
    a,aid=account('alice');b,bid=account('bob')
    r=invitation(a,bid);assert r.status_code==201
    iid=r.json()['id']
    assert a.post(f'/api/invitations/{iid}/action',json={'action':'accept'}).status_code==403
    assert b.post(f'/api/invitations/{iid}/action',json={'action':'accept'}).json()['status']=='accepted'
    assert b.post(f'/api/invitations/{iid}/action',json={'action':'accept'}).status_code==200
    with SessionLocal() as db: assert len(list(db.scalars(select(Booking))))==2
    assert a.get('/api/recommendations').json()==[]
    assert a.post(f'/api/invitations/{iid}/action',json={'action':'cancel'}).status_code==200
    with SessionLocal() as db: assert list(db.scalars(select(Booking)))==[]

def test_unrelated_user_cannot_view_or_act_on_invitation(account):
    a,_=account('alice');b,bid=account('bob');c,_=account('carol')
    iid=invitation(a,bid).json()['id']
    assert c.get('/api/invitations').json()==[]
    assert c.post(f'/api/invitations/{iid}/action',json={'action':'cancel'}).status_code==404
    assert c.put(f'/api/invitations/{iid}/feedback',json={'happened':True,'useful':True}).status_code==404

def test_duplicate_invitation_and_self_invite(account):
    a,aid=account('alice');b,bid=account('bob')
    assert invitation(a,aid).status_code==422
    assert invitation(a,bid).status_code==201
    assert invitation(a,bid).status_code==409
    assert invitation(b,aid).status_code==409

def test_non_shared_topic_is_rejected(account):
    a,_=account('alice',wanted=[1],offered=[]);_,bid=account('bob',wanted=[1],offered=[])
    assert invitation(a,bid,topic=2).status_code==422

def test_concurrent_acceptance_produces_one_meeting(account):
    a,aid=account('alice');b,bid=account('bob');c,cid=account('carol')
    first=invitation(a,bid).json()['id'];second=invitation(a,cid).json()['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda pair:pair[0].post(f'/api/invitations/{pair[1]}/action',json={'action':'accept'}),[(b,first),(c,second)]))
    assert sorted(r.status_code for r in responses)==[200,409]
    with SessionLocal() as db:
        assert len(list(db.scalars(select(Booking))))==2
        assert len(list(db.scalars(select(Booking).where(Booking.user_id==aid))))==1
        assert sorted(db.scalars(select(Invitation.status)))==['accepted','conflict']

def test_decline_cooldown_and_changed_availability(account):
    a,_=account('alice');b,bid=account('bob')
    iid=invitation(a,bid).json()['id']
    assert b.post(f'/api/invitations/{iid}/action',json={'action':'decline'}).status_code==200
    assert invitation(a,bid,slot=2).status_code==429

def test_accept_rechecks_visibility(account):
    a,_=account('alice');b,bid=account('bob')
    iid=invitation(a,bid).json()['id']
    data=a.get('/api/me').json();data['visible']=False
    assert a.put('/api/me',json=data).status_code==200
    assert b.post(f'/api/invitations/{iid}/action',json={'action':'accept'}).status_code==409

def test_feedback_requires_finished_meeting_and_both_confirmations(account):
    a,aid=account('alice');b,bid=account('bob');admin,adminid=account('organizer')
    with SessionLocal.begin() as db: db.get(User,adminid).is_admin=True
    iid=invitation(a,bid).json()['id']
    assert b.post(f'/api/invitations/{iid}/action',json={'action':'accept'}).status_code==200
    assert a.put(f'/api/invitations/{iid}/feedback',json={'happened':True,'useful':True}).status_code==409
    with SessionLocal.begin() as db:
        slot=db.get(Slot,1);slot.starts_at=int(time.time())-1000;slot.ends_at=int(time.time())-100
    assert a.put(f'/api/invitations/{iid}/feedback',json={'happened':False,'useful':True}).status_code==422
    assert a.put(f'/api/invitations/{iid}/feedback',json={'happened':True,'useful':True}).status_code==200
    assert admin.get('/api/admin/stats').json()['confirmed_meetings']==0
    assert b.put(f'/api/invitations/{iid}/feedback',json={'happened':True,'useful':False}).status_code==200
    stats=admin.get('/api/admin/stats').json()
    assert stats['confirmed_meetings']==1 and stats['ratings']==2 and stats['positive_ratings']==1

def test_admin_slots_must_not_overlap(account):
    c,uid=account('admin')
    with SessionLocal.begin() as db: db.get(User,uid).is_admin=True
    with SessionLocal() as db:start=db.get(Slot,1).starts_at
    assert c.post('/api/admin/slots',json={'starts_at':start+30,'ends_at':start+930,'location':'Кофе'}).status_code==409
    assert c.post('/api/admin/slots',json={'starts_at':start+900,'ends_at':start+1800,'location':'Кофе'}).status_code==201

def test_deletion_cascades_other_participants_meeting(account):
    a,_=account('alice');b,bid=account('bob')
    iid=invitation(a,bid).json()['id']
    assert b.post(f'/api/invitations/{iid}/action',json={'action':'accept'}).status_code==200
    assert a.delete('/api/me').status_code==200
    assert a.get('/api/me').status_code==401
    assert b.get('/api/invitations').json()==[]
    with SessionLocal() as db:assert list(db.scalars(select(Booking)))==[]

def test_login_rate_limit(client):
    for _ in range(10):client.post('/api/auth/login',json={'username':'unknown','password':'WrongPass123!'})
    assert client.post('/api/auth/login',json={'username':'unknown','password':'WrongPass123!'}).status_code==429

def test_data_and_session_survive_new_connections(account):
    from app.database import engine
    a,aid=account('alice');b,bid=account('bob')
    iid=invitation(a,bid).json()['id']
    b.post(f'/api/invitations/{iid}/action',json={'action':'accept'})
    engine.dispose()
    assert a.get('/api/me').json()['id']==aid
    assert b.get('/api/invitations').json()[0]['status']=='accepted'

def test_demo_accounts_excluded_from_metrics(account):
    admin,uid=account('admin');a,aid=account('alice');b,bid=account('bob')
    with SessionLocal.begin() as db:
        db.get(User,uid).is_admin=True
        db.get(User,bid).is_demo=True
    iid=invitation(a,bid).json()['id']
    assert b.post(f'/api/invitations/{iid}/action',json={'action':'accept'}).status_code==200
    result=admin.get('/api/admin/stats').json()
    assert result['profiles']==2 and result['invitations']==0
    assert result['participants_with_meeting']==0

def test_expired_invitation_cannot_be_accepted(account):
    a,_=account('alice');b,bid=account('bob')
    iid=invitation(a,bid).json()['id']
    with SessionLocal.begin() as db:
        slot=db.get(Slot,1);slot.starts_at=int(time.time())-100;slot.ends_at=int(time.time())+800
    assert b.get('/api/invitations').json()[0]['status']=='expired'
    assert b.post(f'/api/invitations/{iid}/action',json={'action':'accept'}).status_code==409

def test_openapi_success_and_error_contracts_are_explicit(client):
    schema=client.get('/api/openapi.json').json()
    for path,methods in schema['paths'].items():
        for method,operation in methods.items():
            if method not in ('get','post','put','delete'): continue
            for code,response in operation['responses'].items():
                if code in ('200','201'):
                    assert response['content']['application/json']['schema'],(path,method)
            assert operation['responses']['500']['content']['application/json']['schema']['$ref'].endswith('/ErrorResponse')
    assert 'password_hash' not in str(schema['components']['schemas']['PrivateProfile'])

def test_unexpected_error_is_safe_json_and_structured_log(client,caplog,monkeypatch):
    import app.main as main
    records=[]
    monkeypatch.setattr(main.logger,'info',records.append)
    def broken():raise RuntimeError('sensitive-debug-detail')
    monkeypatch.setattr(main,'SessionLocal',broken)
    response=client.get('/api/health?token=secret-query')
    assert response.status_code==500
    assert response.headers['content-type'].startswith('application/json')
    assert response.json()['error']['code']==500
    assert 'sensitive-debug-detail' not in response.text
    import json
    record=json.loads(records[-1])
    assert record['status']==500 and record['duration_ms']>=0
    assert record['endpoint']=='/api/health'
    assert 'secret-query' not in records[-1]

def test_framework_404_also_uses_error_envelope(client):
    response=client.get('/api/no-such-endpoint')
    assert response.status_code==404
    assert response.json()['error']['code']==404

def test_rate_limit_has_retry_after(client):
    for _ in range(10):client.post('/api/auth/login',json={'username':'unknown','password':'WrongPass123!'})
    response=client.post('/api/auth/login',json={'username':'unknown','password':'WrongPass123!'})
    assert response.status_code==429
    assert 1<=int(response.headers['retry-after'])<=60

def test_cooldown_has_retry_after(account):
    a,_=account('alice');b,bid=account('bob')
    iid=invitation(a,bid).json()['id']
    b.post(f'/api/invitations/{iid}/action',json={'action':'decline'})
    response=invitation(a,bid,slot=2)
    assert response.status_code==429
    assert 1<=int(response.headers['retry-after'])<=3600
