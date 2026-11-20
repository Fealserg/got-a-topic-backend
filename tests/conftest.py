import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

temp=tempfile.TemporaryDirectory(prefix='pereryv-tests-')
os.environ['DATABASE_URL']='sqlite:///'+str(Path(temp.name)/'test.db')
os.environ['FRONTEND_URL']='http://testserver'
from app.database import Base,engine,SessionLocal
from app.models import Topic,Slot
from app.main import app,limits
import time

@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    limits.clear()
    with SessionLocal.begin() as db:
        db.add_all([Topic(id=1,name='ИИ'),Topic(id=2,name='API')])
        start=int(time.time())+3600
        db.add_all([Slot(id=1,starts_at=start,ends_at=start+900,location='Кофе'),Slot(id=2,starts_at=start+1800,ends_at=start+2700,location='Кофе')])
    yield

@pytest.fixture
def client():
    with TestClient(app,headers={'X-Requested-With':'pereryv'}) as c: yield c

@pytest.fixture
def account():
    clients=[]
    def create(name,wanted=None,offered=None,available=None,visible=True):
        c=TestClient(app,headers={'X-Requested-With':'pereryv'});clients.append(c)
        r=c.post('/api/auth/register',json={'username':name,'password':'TestingPass123!','name':name})
        assert r.status_code==201,r.text
        uid=r.json()['id']
        r=c.put('/api/me',json={'name':name,'role':'Аналитик','company':'','bio':'','wanted':[1] if wanted is None else wanted,'offered':[2] if offered is None else offered,'availability':[1,2] if available is None else available,'visible':visible})
        assert r.status_code==200,r.text
        return c,uid
    yield create
    for c in clients:c.close()
