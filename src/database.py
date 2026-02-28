import datetime
from peewee import (
    SqliteDatabase,
    Model,
    CharField,
    BigIntegerField,
    DateTimeField,
)

db = SqliteDatabase("neurobrain.db")


class BaseModel(Model):
    class Meta:
        database = db


class Post(BaseModel):
    uri = CharField(unique=True, index=True)
    cid = CharField()
    indexed_at = DateTimeField(default=datetime.datetime.utcnow, index=True)


class SubscriptionState(BaseModel):
    service = CharField(unique=True)
    cursor = BigIntegerField()


class ClassificationLog(BaseModel):
    uri = CharField()
    text = CharField()
    result = CharField()
    classified_at = DateTimeField(default=datetime.datetime.utcnow)


def init_db():
    db.connect(reuse_if_open=True)
    db.create_tables([Post, SubscriptionState, ClassificationLog])
