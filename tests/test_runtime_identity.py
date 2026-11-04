import pathlib,pytest
from runtime_identity import load_managed_identity
def configure(monkeypatch,tmp_path,keys):
    private=tmp_path/'private.pem';public=tmp_path/'public.pem';private.write_text(keys['private']);public.write_text(keys['public'])
    for key,value in {'DATABASE_ROOT_PASSWORD':'synthetic-test-only','WALLET_TRACKER_SECRET':'synthetic-test-only','WALLET_TRACKER_PRIVATE_KEY_FILE':str(private),'WALLET_TRACKER_PUBLIC_KEY_FILE':str(public)}.items():monkeypatch.setenv(key,value)
    return private,public
def test_managed_pair_preserved(monkeypatch,tmp_path,keys):
    configure(monkeypatch,tmp_path,keys);assert load_managed_identity()==(keys['private'],keys['public'])
def test_missing_managed_file_never_generated(monkeypatch,tmp_path,keys):
    private,_=configure(monkeypatch,tmp_path,keys);private.unlink()
    with pytest.raises(RuntimeError,match='refusing key generation'):load_managed_identity()
    assert not private.exists()
def test_missing_database_input_fails_without_value(monkeypatch,tmp_path,keys):
    configure(monkeypatch,tmp_path,keys);monkeypatch.delenv('DATABASE_ROOT_PASSWORD')
    with pytest.raises(RuntimeError,match='DATABASE_ROOT_PASSWORD'):load_managed_identity()
def test_invalid_pair_does_not_disclose_contents(monkeypatch,tmp_path,keys):
    _,public=configure(monkeypatch,tmp_path,keys);public.write_text('synthetic-invalid-not-a-key')
    with pytest.raises(RuntimeError) as e:load_managed_identity()
    assert 'synthetic-invalid' not in str(e.value)
def test_managed_app_reports_built_revision_without_key_generation(monkeypatch,tmp_path,keys):
    from app import create_app
    from sqlalchemy import URL
    from unittest import mock
    configure(monkeypatch,tmp_path,keys);monkeypatch.setenv('WALLET_TRACKER_REQUIRE_MANAGED_KEYS','true');monkeypatch.setenv('WALLET_TRACKER_STDOUT_LOG','true');monkeypatch.setenv('APP_BUILD_REVISION','a'*40)
    with mock.patch('app.generate_keys_file') as generate:
        app=create_app(database_uri=URL.create('sqlite',database=str(tmp_path/'probe.db')))
        response=app.test_client().get('/api/v1/health');assert response.status_code==200
        assert response.headers['X-WalletTracker-Revision']=='a'*40;generate.assert_not_called()
