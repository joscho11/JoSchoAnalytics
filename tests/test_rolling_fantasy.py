"""Rolling fantasy releases preserve complete, exact started-game snapshots."""
import json
import pandas as pd
import pytest
from publishing.contract import ValidationReport, sha256_file
from publishing.validators import _validate_rolling_fantasy


@pytest.mark.parametrize('change', ['none', 'removed', 'added', 'value', 'hash'])
def test_started_game_snapshot_validation(tmp_path, change):
    old = tmp_path / 'old.csv'
    old.write_text('player_id,game_id,projected_pts\na,g1,10.123456789012345\nb,g2,20\n', encoding='utf-8')
    old_meta = tmp_path / 'old.json'
    old_meta.write_text('{}', encoding='utf-8')
    new = tmp_path / 'new.csv'
    content = old.read_text(encoding='utf-8').replace('b,g2,20', 'b,g2,21')
    if change == 'removed': content = content.replace('a,g1,10.123456789012345\n', '')
    if change == 'added': content += 'c,g1,5\n'
    if change == 'value': content = content.replace('10.123456789012345', '10.123456789012346')
    new.write_text(content, encoding='utf-8')
    manifest = tmp_path / 'data' / 'releases' / 'manifest.json'
    manifest.parent.mkdir(parents=True)
    baseline = {'season':2026, 'week':8, 'model_version':'frozen', 'artifact':'old.csv', 'metadata':'old.json', 'sha256':sha256_file(old)}
    manifest.write_text(json.dumps({'schema_version':1,'products':{'fantasy':{'builds':{'baseline':baseline}}}}),encoding='utf-8')
    metadata = {'season':2026,'week':8,'model_version':'frozen','produced_at':'2026-11-01T13:01:00Z', 'rolling_refresh':{
        'baseline_build_id':'baseline','baseline_artifact_sha256':sha256_file(old), 'baseline_metadata_sha256':sha256_file(old_meta),
        'as_of_utc':'2026-11-01T13:00:00Z','source_requested_utc':'2026-11-01T12:59:00Z','locked_game_ids':['g1']}}
    if change == 'hash': metadata['rolling_refresh']['baseline_artifact_sha256'] = '0'*64
    schedule = pd.DataFrame([{'game_id':'g1','season':2026,'week':8,'gameday':'2026-10-29','gametime':'20:15'}, {'game_id':'g2','season':2026,'week':8,'gameday':'2026-11-01','gametime':'13:00'}])
    report = ValidationReport(product='fantasy')
    _validate_rolling_fantasy(report,new,metadata,schedule,tmp_path)
    assert report.ok == (change == 'none'), report.errors
