"""Quick analysis of classification logs for tuning."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import db, ClassificationLog, Post, init_db


def analyze():
    init_db()

    total = ClassificationLog.select().count()
    if total == 0:
        print("No classification logs found.")
        return

    relevant = ClassificationLog.select().where(
        ClassificationLog.result.startswith("RELEVANT")
    ).count()
    not_relevant = ClassificationLog.select().where(
        ClassificationLog.result.startswith("NOT_RELEVANT")
    ).count()
    errors = ClassificationLog.select().where(
        ClassificationLog.result == "ERROR"
    ).count()

    print(f"=== Classification Summary ===")
    print(f"Total:        {total}")
    print(f"RELEVANT:     {relevant} ({100*relevant/total:.1f}%)")
    print(f"NOT_RELEVANT: {not_relevant} ({100*not_relevant/total:.1f}%)")
    print(f"ERROR:        {errors} ({100*errors/total:.1f}%)")
    print(f"Posts in DB:  {Post.select().count()}")
    print()

    # Recent approvals
    print("=== Recent Approvals ===")
    for log in (
        ClassificationLog.select()
        .where(ClassificationLog.result.startswith("RELEVANT"))
        .order_by(ClassificationLog.classified_at.desc())
        .limit(10)
    ):
        print(f"  [{log.uri or 'no-uri'}] {log.text[:100]}")
    print()

    # Recent rejections
    print("=== Recent Rejections (last 5) ===")
    for log in (
        ClassificationLog.select()
        .where(ClassificationLog.result.startswith("NOT_RELEVANT"))
        .order_by(ClassificationLog.classified_at.desc())
        .limit(5)
    ):
        print(f"  {log.text[:100]}")


if __name__ == "__main__":
    analyze()
