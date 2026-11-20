from app.services.metrics_history import HistoryBucket, MetricsHistoryRepository


def _bucket(start, count, cpu):
    return HistoryBucket(
        bucket_start=start,
        cpu_percent=cpu,
        memory_percent=50.0,
        memory_used=100,
        memory_total=200,
        swap_percent=0.0,
        swap_used=0,
        swap_total=0,
        disk_percent=10.0,
        disk_used=10,
        disk_total=100,
        load_1=0.5,
        load_5=0.4,
        load_15=0.3,
        sample_count=count,
    )


def test_upsert_weighted_merge(tmp_path):
    repo = MetricsHistoryRepository(tmp_path / "m.db")
    repo.upsert_bucket(_bucket(300, 2, 10.0))
    repo.upsert_bucket(_bucket(300, 3, 20.0))
    rows = repo.list_buckets()
    assert len(rows) == 1
    assert rows[0].sample_count == 5
    assert abs(rows[0].cpu_percent - 16.0) < 1e-9


def test_list_ordered_and_filtered(tmp_path):
    repo = MetricsHistoryRepository(tmp_path / "m.db")
    repo.upsert_bucket(_bucket(600, 1, 30.0))
    repo.upsert_bucket(_bucket(300, 1, 10.0))
    assert [r.bucket_start for r in repo.list_buckets()] == [300, 600]
    assert [r.bucket_start for r in repo.list_buckets(start=400)] == [600]
    assert [r.bucket_start for r in repo.list_buckets(start=300, end=600)] == [300]


def test_upsert_preserves_none_loads(tmp_path):
    repo = MetricsHistoryRepository(tmp_path / "m.db")
    b = _bucket(300, 1, 10.0)
    b.load_1 = b.load_5 = b.load_15 = None
    repo.upsert_bucket(b)
    repo.upsert_bucket(b)
    row = repo.list_buckets()[0]
    assert row.load_1 is None and row.load_5 is None and row.load_15 is None
