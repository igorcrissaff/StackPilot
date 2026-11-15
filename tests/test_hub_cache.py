from unittest.mock import patch

from app.services.hub_cache import HubCache


def test_init_is_idempotent(tmp_path):
    db = tmp_path / "hub.db"
    HubCache(db)
    HubCache(db)  # must not raise


def test_search_cache_hit_and_stale(tmp_path):
    c = HubCache(tmp_path / "hub.db")
    assert c.get_search("jellyfin", 3600) == (None, None, False)
    c.set_search("jellyfin", '["x"]')
    payload, fetched_at, stale = c.get_search("jellyfin", 3600)
    assert (payload, stale) == ('["x"]', False)
    assert isinstance(fetched_at, int)
    assert c.get_search("jellyfin", -1)[2] is True


def test_tags_cache(tmp_path):
    c = HubCache(tmp_path / "hub.db")
    assert c.get_tags("library/nginx", 3600) == (None, None, False)
    c.set_tags("library/nginx", '["latest"]')
    assert c.get_tags("library/nginx", 3600)[0] == '["latest"]'


def test_record_used_image_increments(tmp_path):
    c = HubCache(tmp_path / "hub.db")
    c.record_used_image("jellyfin/jellyfin:latest", "jellyfin")
    c.record_used_image("jellyfin/jellyfin:latest", "jellyfin2")
    imgs = c.list_used_images()
    assert len(imgs) == 1
    assert imgs[0].image == "jellyfin/jellyfin:latest"
    assert imgs[0].use_count == 2
    assert imgs[0].stack_name == "jellyfin2"


def test_list_used_images_most_recent_first(tmp_path):
    c = HubCache(tmp_path / "hub.db")
    with patch("app.services.hub_cache.time.time", side_effect=[100, 200]):
        c.record_used_image("nginx:alpine", "a")
        c.record_used_image("redis:7", "b")
    assert [i.image for i in c.list_used_images()][0] == "redis:7"
