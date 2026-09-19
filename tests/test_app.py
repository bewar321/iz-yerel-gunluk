from pathlib import Path
import json
import re
from journal.app import create_app


def test_served_app_is_self_contained_and_backup_example_valid(tmp_path):
    app = create_app(tmp_path)
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    html = response.text
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    assert 'lang="tr"' in html
    for resource in re.findall(r'(?:src|href)="(/static/[^"]+)"', html):
        assert client.get(resource).status_code == 200
    assert not re.search(r'(?:src|href)="https?://', html)
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
    store = app.extensions['store']
    example = json.loads((Path(__file__).parents[1] / 'examples/kurgu-yedek.json').read_text())
    assert store.restore(example) == 6
    assert len([e for e in store.entries() if e['kind']=='decision']) == 1
