from app.main import app


def test_ops_routes_are_registered():
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/ops/overview" in paths
    assert "/api/logs/recent" in paths
    assert "/api/labels" in paths
    assert "/api/finetune/export" in paths
    assert "/api/finetune/submit" in paths
    assert "/api/finetune/settings" in paths
    assert "/health" in paths
