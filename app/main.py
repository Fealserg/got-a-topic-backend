import hashlib
import hmac
import os
import json
import logging
import math
import secrets
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, Security
from fastapi.security import APIKeyHeader
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, or_, select, text
from sqlalchemy.exc import IntegrityError

from .schemas import (ErrorResponse, HealthResponse, ConfigResponse, PrivateProfile, OkResponse, RecommendationResponse, InvitationCreated, InvitationResponse, InvitationActionResponse, SlotCreated, StatsResponse)
from .database import SessionLocal
from .models import Booking, Feedback, Invitation, Session, Slot, Topic, User

csrf_header = APIKeyHeader(name='X-Requested-With', description='Для изменяющих запросов введите pereryv.', auto_error=False)
ERROR_RESPONSES = {code: {'model': ErrorResponse, 'description': description} for code, description in {401:'Нет действующей сессии',403:'Действие запрещено',404:'Объект не найден',409:'Конфликт состояния',422:'Ошибка валидации',429:'Лимит запросов; Retry-After в секундах',500:'Внутренняя ошибка без технических подробностей'}.items()}
logger = logging.getLogger('est_tema.requests')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
logger.propagate = False
app = FastAPI(responses=ERROR_RESPONSES, dependencies=[Security(csrf_header)], title='Есть тема · Networking API', version='1.0.0', docs_url='/api/docs', openapi_url='/api/openapi.json', redoc_url=None)
origins = [v.strip() for v in os.getenv('FRONTEND_URL', 'http://127.0.0.1:3000,http://localhost:3000').split(',') if v.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=['GET','POST','PUT','DELETE'], allow_headers=['Content-Type','X-Requested-With'])
COOKIE = 'pereryv_session'
SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
limits = defaultdict(deque)

def fail(status, message, headers=None):
    raise HTTPException(status, message, headers=headers)

@app.exception_handler(StarletteHTTPException)
async def http_error(_, exc):
    return JSONResponse({'error': {'code': exc.status_code, 'message': exc.detail}}, status_code=exc.status_code, headers=exc.headers)

@app.exception_handler(RequestValidationError)
async def validation_error(_, exc):
    return JSONResponse({'error': {'code': 422, 'message': 'Проверьте заполненные поля.', 'fields': [{'field': '.'.join(str(x) for x in e['loc']), 'message': e['msg']} for e in exc.errors()]}}, status_code=422)

@app.middleware('http')
async def security(request, call_next):
    started = time.perf_counter()
    response = None
    try:
        if request.method in ('POST','PUT','DELETE','PATCH'):
            origin = request.headers.get('origin')
            if (origin and origin not in origins) or request.headers.get('x-requested-with') != 'pereryv':
                response = JSONResponse({'error': {'code': 403, 'message': 'Недопустимый источник запроса.'}}, status_code=403)
        if response is None:
            response = await call_next(request)
    except Exception:
        # Do not log exception text, request bodies, credentials or personal data.
        response = JSONResponse({'error': {'code': 500, 'message': 'Внутренняя ошибка сервиса. Попробуйте позже.'}}, status_code=500)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    route = request.scope.get('route')
    endpoint = getattr(route, 'path', 'unmatched')
    size = request.headers.get('content-length', '')
    logger.info(json.dumps({
        'time': int(time.time()), 'method': request.method, 'endpoint': endpoint,
        'status': response.status_code, 'duration_ms': round((time.perf_counter()-started)*1000, 2),
        'input_bytes': int(size) if size.isdecimal() and len(size) < 16 else None,
        'error_code': response.status_code if response.status_code >= 400 else None,
    }, ensure_ascii=False))
    return response

def throttle(request, kind, maximum):
    key = (request.client.host if request.client else 'unknown', kind)
    now = time.time()
    q = limits[key]
    while q and q[0] < now - 60:
        q.popleft()
    if len(q) >= maximum:
        fail(429, 'Слишком много попыток. Подождите минуту.', {'Retry-After': str(max(1, math.ceil(q[0]+60-now)))})
    q.append(now)
    if len(limits) > 10000:
        for k in list(limits):
            if not limits[k] or limits[k][-1] < now-60:
                del limits[k]

@contextmanager
def transaction():
    with SessionLocal() as db:
        try:
            db.execute(text('BEGIN IMMEDIATE'))
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest

def verify_password(password, value):
    return hmac.compare_digest(password_hash(password, value.split(':')[0]), value)

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def current_user(request: Request):
    token = request.cookies.get(COOKIE, '')
    with SessionLocal() as db:
        session = db.get(Session, token_hash(token))
        if not session or session.expires_at <= time.time():
            fail(401, 'Войдите в свой профиль.')
        user = db.get(User, session.user_id)
        if not user:
            fail(401, 'Профиль не найден.')
        return user

Auth = Annotated[User, Depends(current_user)]

def public_user(user):
    return {key: getattr(user,key) for key in ('id','name','role','company','bio','wanted','offered','availability','visible','is_demo')}

def private_user(user):
    return {**public_user(user), 'username': user.username, 'is_admin': user.is_admin}

def set_session(db, user, response):
    token = secrets.token_urlsafe(32)
    db.add(Session(token_hash=token_hash(token), user_id=user.id, expires_at=int(time.time())+7*86400))
    response.set_cookie(COOKIE, token, max_age=7*86400, httponly=True, secure=SECURE, samesite='strict', path='/')

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=10, max_length=128)

class Register(Credentials):
    name: str = Field(min_length=1, max_length=80)

class Profile(BaseModel):
    name: str = Field(min_length=1,max_length=80)
    role: str = Field(default='',max_length=100)
    company: str = Field(default='',max_length=100)
    bio: str = Field(default='',max_length=500)
    wanted: list[int] = Field(max_length=5)
    offered: list[int] = Field(max_length=5)
    availability: list[int] = Field(max_length=20)
    visible: bool
    @model_validator(mode='after')
    def complete(self):
        if not self.name.strip():
            raise ValueError('Укажите имя')
        if self.visible and (not self.wanted and not self.offered or not self.availability):
            raise ValueError('Для публикации выберите темы и время')
        return self

class InviteInput(BaseModel):
    recipient_id: int
    slot_id: int
    topic_id: int
    message: str = Field(default='',max_length=300)

class Action(BaseModel):
    action: str = Field(pattern=r'^(accept|decline|cancel)$')

class FeedbackInput(BaseModel):
    happened: bool
    useful: bool | None = None
    @model_validator(mode='after')
    def consistent(self):
        if not self.happened and self.useful is not None:
            raise ValueError('Оценивать можно состоявшуюся встречу')
        return self

class SlotInput(BaseModel):
    starts_at: int
    ends_at: int
    location: str = Field(min_length=1,max_length=150)
    @model_validator(mode='after')
    def duration(self):
        if not self.location.strip():
            raise ValueError('Укажите точку встречи')
        self.location = self.location.strip()
        if self.ends_at-self.starts_at != 900:
            raise ValueError('Слот должен длиться 15 минут')
        if self.starts_at <= time.time():
            raise ValueError('Выберите будущее время')
        return self

@app.get('/api/health', response_model=HealthResponse, tags=['System'])
def health():
    with SessionLocal() as db:
        db.execute(text('SELECT 1'))
    return {'status':'ok'}

@app.get('/api/config', response_model=ConfigResponse, tags=['System'])
def config():
    with SessionLocal() as db:
        return {'topics':[{'id':t.id,'name':t.name} for t in db.scalars(select(Topic).order_by(Topic.id))],
                'slots':[{'id':s.id,'starts_at':s.starts_at,'ends_at':s.ends_at,'location':s.location,'is_demo':s.is_demo} for s in db.scalars(select(Slot).order_by(Slot.starts_at))],
                'demo_enabled':os.getenv('DEMO_MODE','false').lower()=='true'}

@app.post('/api/auth/register', response_model=PrivateProfile, status_code=201, tags=['Auth'])
def register(body: Register, request: Request, response: Response):
    throttle(request,'register',30)
    if not body.name.strip():
        fail(422,'Укажите имя.')
    try:
        with transaction() as db:
            user = User(username=body.username.lower(), password_hash=password_hash(body.password), name=body.name.strip())
            db.add(user)
            db.flush()
            set_session(db,user,response)
            return private_user(user)
    except IntegrityError:
        fail(409,'Этот логин уже занят.')

@app.post('/api/auth/login', response_model=PrivateProfile, tags=['Auth'])
def login(body: Credentials, request: Request, response: Response):
    throttle(request,'login:'+token_hash(body.username.lower())[:16],10)
    with transaction() as db:
        user = db.scalar(select(User).where(User.username==body.username.lower()))
        if not user or not verify_password(body.password,user.password_hash):
            fail(401,'Неверный логин или пароль.')
        db.execute(delete(Session).where(Session.expires_at < int(time.time())))
        set_session(db,user,response)
        return private_user(user)

@app.post('/api/auth/logout', response_model=OkResponse, tags=['Auth'])
def logout(request: Request, response: Response):
    with transaction() as db:
        db.execute(delete(Session).where(Session.token_hash==token_hash(request.cookies.get(COOKIE,''))))
    response.delete_cookie(COOKIE,path='/')
    return {'ok':True}

@app.get('/api/me', response_model=PrivateProfile, tags=['Profile'])
def me(user: Auth):
    return private_user(user)

@app.put('/api/me', response_model=PrivateProfile, tags=['Profile'])
def update_profile(body: Profile, user: Auth):
    with transaction() as db:
        topics = set(db.scalars(select(Topic.id)))
        slots = set(db.scalars(select(Slot.id).where(Slot.starts_at>time.time())))
        if not set(body.wanted+body.offered)<=topics or not set(body.availability)<=slots:
            fail(422,'Тема или доступное время больше недействительны. Обновите страницу.')
        current = db.get(User,user.id)
        for key,value in body.model_dump().items():
            setattr(current,key,list(dict.fromkeys(value)) if isinstance(value,list) else value.strip() if isinstance(value,str) else value)
        # Existing accepted meetings remain; visibility only controls discovery.
        return private_user(current)

@app.delete('/api/me', response_model=OkResponse, tags=['Profile'])
def delete_profile(user: Auth, response: Response):
    with transaction() as db:
        db.execute(delete(User).where(User.id==user.id))
    response.delete_cookie(COOKIE,path='/')
    return {'ok':True}

def busy_slots(db, uid):
    return set(db.scalars(select(Booking.slot_id).where(Booking.user_id==uid)))

def compatible_topics(a,b):
    direct = set(a.wanted)&set(b.offered)
    reverse = set(a.offered)&set(b.wanted)
    common = (set(a.wanted+a.offered)&set(b.wanted+b.offered)) - direct - reverse
    return direct,reverse,common

@app.get('/api/recommendations', response_model=list[RecommendationResponse], tags=['Matching'])
def recommendations(user: Auth):
    if not user.visible:
        return []
    with SessionLocal() as db:
        future_slots = list(db.scalars(select(Slot).where(Slot.starts_at>time.time())))
        future = {s.id for s in future_slots}
        starts = {s.id: s.starts_at for s in future_slots}
        free = set(user.availability)&future-busy_slots(db,user.id)
        met = set()
        for inv in db.scalars(select(Invitation).where(Invitation.status=='accepted',or_(Invitation.sender_id==user.id,Invitation.recipient_id==user.id))):
            met.add(inv.recipient_id if inv.sender_id==user.id else inv.sender_id)
        result=[]
        for other in db.scalars(select(User).where(User.visible==True,User.id!=user.id)):
            if other.id in met:
                continue
            slots = sorted(free&set(other.availability)-busy_slots(db,other.id), key=lambda sid: starts[sid])
            direct,reverse,common = compatible_topics(user,other)
            score=3*len(direct)+2*len(reverse)+len(common)
            if score and slots:
                result.append({'user':public_user(other),'score':score,'learn_topics':sorted(direct),'share_topics':sorted(reverse),'common_topics':sorted(common),'slot_ids':slots})
        return sorted(result,key=lambda r:(-r['score'],r['user']['id']))[:30]

@app.post('/api/invitations', response_model=InvitationCreated, status_code=201, tags=['Meetings'])
def invite(body: InviteInput,user: Auth,request: Request):
    throttle(request,'invite:'+str(user.id),10)
    with transaction() as db:
        sender=db.get(User,user.id)
        other=db.get(User,body.recipient_id)
        slot=db.get(Slot,body.slot_id)
        if other is None or other.id==user.id or not sender.visible or not other.visible:
            fail(422,'Приглашение этому участнику недоступно.')
        if not slot or slot.starts_at<=time.time() or slot.id not in sender.availability or slot.id not in other.availability:
            fail(409,'Это время больше недоступно.')
        if body.topic_id not in set(sender.wanted+sender.offered)&set(other.wanted+other.offered):
            fail(422,'Выберите общую тему.')
        if slot.id in busy_slots(db,sender.id)|busy_slots(db,other.id):
            fail(409,'Время уже занято.')
        existing=db.scalar(select(Invitation).where(or_((Invitation.sender_id==user.id)&(Invitation.recipient_id==other.id),(Invitation.sender_id==other.id)&(Invitation.recipient_id==user.id)),Invitation.slot_id==slot.id,Invitation.status.in_(['pending','accepted'])))
        if existing:
            fail(409,'Приглашение на это время уже существует.')
        recent=db.scalar(select(Invitation).where(Invitation.sender_id==user.id,Invitation.recipient_id==other.id,Invitation.created_at>time.time()-3600))
        if recent:
            fail(429,'Вы уже приглашали этого участника. Повторите через час.', {'Retry-After': str(max(1, math.ceil(recent.created_at+3600-time.time())))})
        inv=Invitation(sender_id=user.id,recipient_id=other.id,slot_id=slot.id,topic_id=body.topic_id,message=body.message.strip(),created_at=int(time.time()))
        db.add(inv);db.flush()
        return {'id':inv.id,'status':inv.status}

@app.get('/api/invitations', response_model=list[InvitationResponse], tags=['Meetings'])
def invitations(user: Auth):
    with SessionLocal() as db:
        result=[]
        for inv in db.scalars(select(Invitation).where(or_(Invitation.sender_id==user.id,Invitation.recipient_id==user.id)).order_by(Invitation.created_at.desc(),Invitation.id.desc())):
            other=db.get(User,inv.recipient_id if inv.sender_id==user.id else inv.sender_id)
            feedback=db.scalar(select(Feedback).where(Feedback.invitation_id==inv.id,Feedback.user_id==user.id))
            status='expired' if inv.status=='pending' and db.get(Slot,inv.slot_id).starts_at<=time.time() else inv.status
            result.append({'id':inv.id,'incoming':inv.recipient_id==user.id,'other':public_user(other),'slot_id':inv.slot_id,'topic_id':inv.topic_id,'message':inv.message,'status':status,'feedback':{'happened':feedback.happened,'useful':feedback.useful} if feedback else None})
        return result

@app.post('/api/invitations/{invitation_id}/action', response_model=InvitationActionResponse, tags=['Meetings'])
def invitation_action(invitation_id: int,body: Action,user: Auth):
    with transaction() as db:
        inv=db.get(Invitation,invitation_id)
        if not inv or user.id not in (inv.sender_id,inv.recipient_id):
            fail(404,'Приглашение не найдено.')
        if body.action in ('accept','decline') and user.id!=inv.recipient_id:
            fail(403,'Ответить может только получатель.')
        desired={'accept':'accepted','decline':'declined','cancel':'cancelled'}[body.action]
        if inv.status==desired:
            return {'status':desired}
        if body.action=='cancel':
            if inv.status not in ('pending','accepted') or db.get(Slot,inv.slot_id).starts_at<=time.time():
                fail(409,'Отменить эту встречу уже нельзя.')
            db.execute(delete(Booking).where(Booking.invitation_id==inv.id))
        elif inv.status!='pending' or db.get(Slot,inv.slot_id).starts_at<=time.time():
            fail(409,'Приглашение больше недействительно.')
        elif body.action=='accept':
            a,b=db.get(User,inv.sender_id),db.get(User,inv.recipient_id)
            if not a.visible or not b.visible or inv.slot_id not in a.availability or inv.slot_id not in b.availability:
                fail(409,'Участник изменил доступность.')
            if inv.slot_id in busy_slots(db,a.id)|busy_slots(db,b.id):
                fail(409,'У одного из участников уже назначена встреча.')
            db.add_all([Booking(user_id=uid,slot_id=inv.slot_id,invitation_id=inv.id) for uid in (a.id,b.id)])
            inv.accepted_at=int(time.time())
            for conflict in db.scalars(select(Invitation).where(Invitation.id!=inv.id,Invitation.slot_id==inv.slot_id,Invitation.status=='pending',or_(Invitation.sender_id.in_([a.id,b.id]),Invitation.recipient_id.in_([a.id,b.id])))):
                conflict.status='conflict'
        inv.status=desired
        return {'status':desired}

@app.put('/api/invitations/{invitation_id}/feedback', response_model=OkResponse, tags=['Meetings'])
def feedback(invitation_id: int,body: FeedbackInput,user: Auth):
    with transaction() as db:
        inv=db.get(Invitation,invitation_id)
        if not inv or user.id not in (inv.sender_id,inv.recipient_id):
            fail(404,'Встреча не найдена.')
        if inv.status!='accepted' or db.get(Slot,inv.slot_id).ends_at>time.time():
            fail(409,'Обратная связь доступна после завершения встречи.')
        row=db.scalar(select(Feedback).where(Feedback.invitation_id==inv.id,Feedback.user_id==user.id))
        if not row:
            row=Feedback(invitation_id=inv.id,user_id=user.id,**body.model_dump());db.add(row)
        else:
            row.happened, row.useful=body.happened,body.useful
        return {'ok':True}

@app.post('/api/admin/slots', response_model=SlotCreated, status_code=201, tags=['Admin'])
def create_slot(body: SlotInput,user: Auth):
    if not user.is_admin:
        fail(403,'Доступно организатору.')
    with transaction() as db:
        if db.scalar(select(Slot).where(Slot.starts_at<body.ends_at,Slot.ends_at>body.starts_at)):
            fail(409,'Интервал пересекается с существующим.')
        slot=Slot(**body.model_dump());db.add(slot);db.flush()
        return {'id':slot.id}

@app.get('/api/admin/stats', response_model=StatsResponse, tags=['Admin'])
def stats(user: Auth):
    if not user.is_admin:
        fail(403,'Доступно организатору.')
    with SessionLocal() as db:
        users=list(db.scalars(select(User).where(User.is_demo==False)))
        ids={u.id for u in users}
        invs=[i for i in db.scalars(select(Invitation)) if i.sender_id in ids and i.recipient_id in ids]
        feedbacks=list(db.scalars(select(Feedback)))
        inv_ids={i.id for i in invs}
        f=[v for v in feedbacks if v.invitation_id in inv_ids]
        active={u.id for u in users if u.visible and (u.wanted or u.offered) and u.availability}
        matched={uid for i in invs if i.status=='accepted' for uid in (i.sender_id,i.recipient_id)} & active
        happened=sum(1 for i in invs if sum(v.happened for v in f if v.invitation_id==i.id)==2)
        rated=[v for v in f if v.useful is not None]
        topics=[{'name':t.name,'participants':sum(t.id in set(u.wanted+u.offered) for u in users if u.visible)} for t in db.scalars(select(Topic))]
        return {'profiles':len(users),'active_profiles':len(active),'participants_with_meeting':len(matched),'invitations':len(invs),'ever_accepted':sum(i.accepted_at is not None for i in invs),'cancelled_after_accept':sum(i.status=='cancelled' and i.accepted_at is not None for i in invs),'confirmed_meetings':happened,'positive_ratings':sum(v.useful is True for v in rated),'ratings':len(rated),'feedback_responses':len(f),'demo_excluded':True,'topics':sorted(topics,key=lambda t:-t['participants'])}
