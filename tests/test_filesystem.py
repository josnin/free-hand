from pathlib import Path
import pytest
from free_hand.tools.filesystem import safe_path, read_file, write_file

def test_traversal(tmp_path: Path):
    with pytest.raises(ValueError): safe_path(tmp_path, '../outside')
def test_secret_blocked(tmp_path: Path):
    (tmp_path/'.env').write_text('secret')
    with pytest.raises(ValueError): read_file(tmp_path, '.env')
def test_no_overwrite(tmp_path: Path):
    (tmp_path/'a').write_text('old')
    with pytest.raises(FileExistsError): write_file(tmp_path, 'a', 'new')
def test_write_new(tmp_path: Path):
    write_file(tmp_path, 'sub/a.txt', 'hello')
    assert (tmp_path/'sub/a.txt').read_text() == 'hello'
