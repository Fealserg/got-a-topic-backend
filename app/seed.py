"""Idempotent reference data; demo profiles only with --demo."""
import argparse
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from .database import SessionLocal
from .models import Topic, Slot, User
from .main import password_hash

TOPICS=['ИИ в аналитике','Системный анализ','Управление требованиями','API и интеграции','BPMN и процессы','Каталоги данных','Карьера и развитие','Архитектура','UX-исследования','Управление командой']
PEOPLE=[('anna','Анна Смирнова','Системный аналитик','Fintech','Помогаю командам договариваться о требованиях. Хочу обменяться опытом внедрения ИИ.',[1,6],[2,3,4],'АС'),('mikhail','Михаил Волков','Lead Analyst','Product studio','Внедряю ИИ-инструменты в работу аналитиков. Ищу новые подходы к архитектуре.',[2,8],[1,6],'МВ'),('elena','Елена Морозова','Бизнес-аналитик','Retail tech','Разбираюсь в сложных процессах и превращаю их в понятные схемы.',[1,3],[5,9],'ЕМ'),('dmitry','Дмитрий Соколов','Архитектор','Cloud team','Проектирую API и интеграции. Буду рад обсудить реальные кейсы и компромиссы.',[3,5],[4,8],'ДС'),('olga','Ольга Кузнецова','Руководитель аналитики','Digital lab','Развиваю аналитиков и выстраиваю команды. Интересуюсь практикой работы с ИИ.',[1,9],[7,10],'ОК'),('pavel','Павел Лебедев','Data Analyst','Data platform','Работаю с качеством и каталогами данных. Ищу коллег с похожими задачами.',[4,8],[1,6],'ПЛ')]

def seed(demo=False):
    with SessionLocal.begin() as db:
        for i,name in enumerate(TOPICS,1):
            if not db.get(Topic,i): db.add(Topic(id=i,name=name))
        if demo and not db.scalar(select(Slot)):
            start=datetime.now(ZoneInfo('Europe/Moscow')).replace(second=0,microsecond=0)+timedelta(minutes=30)
            for i in range(4):
                dt=start+timedelta(minutes=45*i)
                db.add(Slot(starts_at=int(dt.timestamp()),ends_at=int(dt.timestamp())+900,location='Демо · точка нетворкинга у кофе',is_demo=True))
        db.flush()
        slots=list(db.scalars(select(Slot.id).where(Slot.starts_at>time.time())))
        if demo:
            for username,name,role,company,bio,wanted,offered,_ in PEOPLE:
                if not db.scalar(select(User).where(User.username==username)):
                    db.add(User(username=username,password_hash=password_hash('DemoPass2026!'),name=name,role=role,company=company,bio=bio,wanted=wanted,offered=offered,availability=slots,visible=True,is_demo=True))
        admin_password=os.getenv('ADMIN_PASSWORD')
        admin_name=os.getenv('ADMIN_USERNAME','organizer')
        if admin_password:
            if len(admin_password)<12: raise ValueError('ADMIN_PASSWORD must contain at least 12 characters')
            if not db.scalar(select(User).where(User.username==admin_name)):
                db.add(User(username=admin_name,password_hash=password_hash(admin_password),name='Организатор',is_admin=True))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--demo',action='store_true');args=p.parse_args();seed(args.demo)
