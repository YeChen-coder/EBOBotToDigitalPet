"""Opt-in summary/consolidation test using invented text and disposable memory files."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from session_memory import summarize_turns,save_memory,consolidate_memory,realtime_memory_context


async def main():
    with tempfile.TemporaryDirectory(prefix='ebo-memory-smoke-') as temp:
        sessions=Path(temp)/'sessions.json'
        long_term=Path(temp)/'long_term.json'
        summary=await summarize_turns([{'role':'user','text':'This is fictional software test data. I prefer blue notebooks.'}],tracing_disabled=True)
        assert summary!='NO_MEMORY' and len(summary.split())<=25
        save_memory(sessions,'synthetic-validation',summary)
        await consolidate_memory(sessions,long_term,tracing_disabled=True)
        assert long_term.exists() and realtime_memory_context(sessions,long_term)
        print(json.dumps({'summary_model_verified':True,'consolidation_model_verified':True,
            'files':'temporary','family_memory_used':False}))


if __name__=='__main__':asyncio.run(main())
