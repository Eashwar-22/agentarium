import json
import os
import tempfile
import unittest
from pathlib import Path

from agentarium.events import create_demo_events
from agentarium.tail import EventTail


class EventTailTests(unittest.TestCase):
    def test_partial_utf8_lines_are_emitted_only_when_complete(self):
        data = create_demo_events()[0].to_dict()
        data['summary'] = 'A full UTF-8 record: café'
        raw=(json.dumps(data,ensure_ascii=False)+'\n').encode()
        cut=raw.index('é'.encode())+1
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl'
            path.write_bytes(raw[:cut])
            tail=EventTail(path,chunk_bytes=64)
            result=[]
            while True:
                result.extend(tail.poll())
                if not tail.has_more:break
            self.assertEqual(result,[])
            with path.open('ab') as stream:stream.write(raw[cut:])
            while True:
                result.extend(tail.poll())
                if not tail.has_more:break
            self.assertEqual(result[0].summary,data['summary'])
            before=tail.bytes_read
            self.assertEqual(tail.poll(),[])
            self.assertEqual(tail.bytes_read,before)

    def test_replacement_and_same_inode_rewrite_restart_the_cursor(self):
        events=create_demo_events()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl'
            path.write_text(events[0].to_json()+'\n')
            tail=EventTail(path)
            self.assertEqual(tail.poll()[0].event_id,events[0].event_id)
            # Rewrite to a larger recording with a different initial event ID.
            raw=events[0].to_dict();raw['event_id']='replacement'
            path.write_text(json.dumps(raw)+'\n'+events[1].to_json()+'\n')
            self.assertEqual(tail.poll()[0].event_id,'replacement')
            replacement=Path(tmp)/'new.jsonl'
            replacement.write_text(events[0].to_json()+'\n')
            os.replace(replacement,path)
            self.assertEqual(tail.poll()[0].event_id,events[0].event_id)

    def test_malformed_lines_do_not_hide_following_valid_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl'
            path.write_text('broken\n'+create_demo_events()[0].to_json()+'\n')
            tail=EventTail(path)
            self.assertEqual(len(tail.poll()),1)
            self.assertEqual(tail.invalid_lines,1)
