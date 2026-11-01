from pathlib import Path
from free_hand.executor import build_registry, execute_response

def test_write_requires_approval(tmp_path: Path):
    registry = build_registry(tmp_path, {})
    response = {'version':1,'tool_calls':[{'id':'1','type':'function','function':{'name':'write_file','arguments':{'path':'a.txt','content':'ok'}}}],'final_message':'done'}
    result = execute_response(response, registry, lambda tool,args: True)
    assert result['results'][0]['status'] == 'success'
    assert (tmp_path/'a.txt').read_text() == 'ok'
