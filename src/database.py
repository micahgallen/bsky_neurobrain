import datetime
import logging

from peewee import (
    SqliteDatabase,
    Model,
    CharField,
    BigIntegerField,
    DateTimeField,
    IntegerField,
    FloatField,
)
from playhouse.migrate import SqliteMigrator, migrate

logger = logging.getLogger(__name__)

db = SqliteDatabase("neurobrain.db", pragmas={"journal_mode": "wal"})


class BaseModel(Model):
    class Meta:
        database = db


class Post(BaseModel):
    uri = CharField(unique=True, index=True)
    cid = CharField()
    indexed_at = DateTimeField(default=datetime.datetime.utcnow, index=True)
    quality_score = IntegerField(default=3)
    like_count = IntegerField(default=0)
    repost_count = IntegerField(default=0)
    reply_count = IntegerField(default=0)
    quote_count = IntegerField(default=0)
    engagement_updated_at = DateTimeField(null=True, default=None)
    feed_score = FloatField(default=3.0, index=True)


class SubscriptionState(BaseModel):
    service = CharField(unique=True)
    cursor = BigIntegerField()


class ClassificationLog(BaseModel):
    uri = CharField()
    text = CharField()
    result = CharField()
    quality_score = IntegerField(default=0)
    classified_at = DateTimeField(default=datetime.datetime.utcnow)


def _migrate_db():
    """Add new columns to existing tables. Safe to run repeatedly."""
    migrator = SqliteMigrator(db)

    # Post table migrations
    cursor = db.execute_sql("PRAGMA table_info(post)")
    existing = {row[1] for row in cursor.fetchall()}

    ops = []
    new_post_cols = {
        "quality_score": IntegerField(default=3),
        "like_count": IntegerField(default=0),
        "repost_count": IntegerField(default=0),
        "reply_count": IntegerField(default=0),
        "quote_count": IntegerField(default=0),
        "engagement_updated_at": DateTimeField(null=True, default=None),
        "feed_score": FloatField(default=3.0),
    }
    for col_name, col_field in new_post_cols.items():
        if col_name not in existing:
            ops.append(migrator.add_column("post", col_name, col_field))

    # ClassificationLog table migrations
    cursor = db.execute_sql("PRAGMA table_info(classificationlog)")
    existing = {row[1] for row in cursor.fetchall()}
    if "quality_score" not in existing:
        ops.append(
            migrator.add_column(
                "classificationlog", "quality_score", IntegerField(default=0)
            )
        )

    if ops:
        migrate(*ops)
        logger.info("Database migration: added %d columns", len(ops))

    # Backfill NULLs on existing rows (ALTER TABLE ADD COLUMN defaults
    # only apply to new inserts, not existing rows)
    db.execute_sql("UPDATE post SET quality_score = 3 WHERE quality_score IS NULL")
    db.execute_sql("UPDATE post SET feed_score = 3.0 WHERE feed_score IS NULL")
    db.execute_sql("UPDATE post SET like_count = 0 WHERE like_count IS NULL")
    db.execute_sql("UPDATE post SET repost_count = 0 WHERE repost_count IS NULL")
    db.execute_sql("UPDATE post SET reply_count = 0 WHERE reply_count IS NULL")
    db.execute_sql("UPDATE post SET quote_count = 0 WHERE quote_count IS NULL")

    db.execute_sql(
        "CREATE INDEX IF NOT EXISTS post_feed_score ON post(feed_score)"
    )


def init_db():
    db.connect(reuse_if_open=True)
    db.create_tables([Post, SubscriptionState, ClassificationLog])
    _migrate_db()
