"""Synthetic full-payload benchmark. Writes only inside a temporary directory."""
import json
import tempfile
import time
import tracemalloc
from pathlib import Path
from agentarium.tail import EventTail


def main():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'events.jsonl'
        with path.open('w') as stream:
            for index in range(10000):
                record=dict(schema_version='0.2',run_id='benchmark',event_id=str(index),sequence=index+1,timestamp='2026-01-01T00:00:00+00:00',type='tool_started' if index%2==0 else 'tool_completed',summary='Synthetic lookup',agent_id='a',task_id='task',tool={'name':'lookup','call_id':str(index//2)},metadata={'tool_input_full' if index%2==0 else 'tool_output_full':'x'*4096})
                stream.write(json.dumps(record)+'\n')
        tail=EventTail(path)
        tracemalloc.start()
        count=0;begin=time.perf_counter()
        while True:
            count+=len(tail.poll())
            if not tail.has_more:break
        elapsed=time.perf_counter()-begin
        _, peak_bytes=tracemalloc.get_traced_memory()
        tracemalloc.stop()
        before=tail.bytes_read
        for _ in range(100):assert tail.poll()==[]
        assert count==10000
        assert tail.bytes_read==before
        assert elapsed<10, f'Tail took {elapsed:.2f}s (target <10s)'
        assert peak_bytes<128*1024*1024, f'Tail peak memory {peak_bytes} bytes (target <128 MiB)'
        print(json.dumps(dict(events=count,file_bytes=path.stat().st_size,read_bytes=tail.bytes_read,seconds=round(elapsed,3),peak_bytes=peak_bytes,target_peak_bytes=128*1024*1024,idle_polls=100,idle_read_bytes=tail.bytes_read-before,target_seconds=10)))

if __name__=='__main__':main()
