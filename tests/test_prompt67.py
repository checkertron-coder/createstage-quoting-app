"""
P67: Quote Number Collision Fix — Tests

1. Sequential quotes get unique numbers
2. Collision is avoided when a gap exists
3. generate_quote_number never returns a duplicate
"""

from datetime import datetime

from backend import models
from backend.routers.quotes import generate_quote_number


# === 1. Sequential quotes get incrementing numbers ===

def test_sequential_quote_numbers(db):
    """Each call returns a higher sequence number."""
    n1 = generate_quote_number(db)
    # Insert a quote with that number
    db.add(models.Quote(quote_number=n1, job_type="test"))
    db.commit()

    n2 = generate_quote_number(db)
    assert n1 != n2

    # Both should have the current year
    year = str(datetime.utcnow().year)
    assert year in n1
    assert year in n2

    # n2's sequence should be higher than n1's
    seq1 = int(n1.split("-")[-1])
    seq2 = int(n2.split("-")[-1])
    assert seq2 > seq1


# === 2. Collision avoided when number already taken ===

def test_collision_avoidance(db):
    """If the expected next number exists, skip to the next free one."""
    year = datetime.utcnow().year

    # Pre-populate quotes with specific numbers to create a collision scenario
    for i in range(1, 6):
        db.add(models.Quote(
            quote_number="CS-%d-%s" % (year, str(i).zfill(4)),
            job_type="test",
        ))
    db.commit()

    # generate_quote_number should return CS-YYYY-0006 (next after 5 existing)
    result = generate_quote_number(db)
    assert result == "CS-%d-0006" % year

    # Now also insert 0006 to force a gap
    db.add(models.Quote(quote_number="CS-%d-0006" % year, job_type="test"))
    db.commit()

    result2 = generate_quote_number(db)
    assert result2 == "CS-%d-0007" % year


# === 3. No duplicate ever returned ===

def test_no_duplicates_under_bulk(db):
    """Generate 20 quote numbers in sequence — all unique."""
    generated = []
    for _ in range(20):
        qn = generate_quote_number(db)
        assert qn not in generated, "Duplicate quote number: %s" % qn
        generated.append(qn)
        db.add(models.Quote(quote_number=qn, job_type="test"))
        db.commit()

    assert len(set(generated)) == 20
