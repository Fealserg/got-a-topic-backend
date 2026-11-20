"""Initial networking schema."""
from alembic import op
import sqlalchemy as sa
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('users', sa.Column('id',sa.Integer,primary_key=True),sa.Column('username',sa.String(32),unique=True,nullable=False),sa.Column('password_hash',sa.String,nullable=False),sa.Column('name',sa.String(80),nullable=False),sa.Column('role',sa.String(100),nullable=False),sa.Column('company',sa.String(100),nullable=False),sa.Column('bio',sa.String(500),nullable=False),sa.Column('wanted',sa.JSON,nullable=False),sa.Column('offered',sa.JSON,nullable=False),sa.Column('availability',sa.JSON,nullable=False),sa.Column('visible',sa.Boolean,nullable=False),sa.Column('is_admin',sa.Boolean,nullable=False),sa.Column('is_demo',sa.Boolean,nullable=False))
    op.create_table('sessions',sa.Column('token_hash',sa.String(64),primary_key=True),sa.Column('user_id',sa.Integer,sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),sa.Column('expires_at',sa.Integer,nullable=False))
    op.create_table('topics',sa.Column('id',sa.Integer,primary_key=True),sa.Column('name',sa.String(100),unique=True,nullable=False))
    op.create_table('slots',sa.Column('id',sa.Integer,primary_key=True),sa.Column('starts_at',sa.Integer,nullable=False),sa.Column('ends_at',sa.Integer,nullable=False),sa.Column('location',sa.String(150),nullable=False),sa.Column('is_demo',sa.Boolean,nullable=False))
    op.create_table('invitations',sa.Column('id',sa.Integer,primary_key=True),sa.Column('sender_id',sa.Integer,sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),sa.Column('recipient_id',sa.Integer,sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),sa.Column('slot_id',sa.Integer,sa.ForeignKey('slots.id'),nullable=False),sa.Column('topic_id',sa.Integer,sa.ForeignKey('topics.id'),nullable=False),sa.Column('message',sa.String(300),nullable=False),sa.Column('status',sa.String(20),nullable=False),sa.Column('created_at',sa.Integer,nullable=False),sa.Column('accepted_at',sa.Integer,nullable=True))
    op.create_table('bookings',sa.Column('user_id',sa.Integer,sa.ForeignKey('users.id',ondelete='CASCADE'),primary_key=True),sa.Column('slot_id',sa.Integer,sa.ForeignKey('slots.id'),primary_key=True),sa.Column('invitation_id',sa.Integer,sa.ForeignKey('invitations.id',ondelete='CASCADE'),nullable=False))
    op.create_table('feedback',sa.Column('id',sa.Integer,primary_key=True),sa.Column('invitation_id',sa.Integer,sa.ForeignKey('invitations.id',ondelete='CASCADE'),nullable=False),sa.Column('user_id',sa.Integer,sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),sa.Column('happened',sa.Boolean,nullable=False),sa.Column('useful',sa.Boolean,nullable=True),sa.UniqueConstraint('invitation_id','user_id'))

def downgrade():
    for table in ('feedback','bookings','invitations','slots','topics','sessions','users'):
        op.drop_table(table)
