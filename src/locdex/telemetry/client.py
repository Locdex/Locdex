import json,requests
from .queue import pop,prepend
from .sanitizer import sanitize_batch
from .schema import SCHEMA_VERSION
from .settings import enabled,endpoint
def flush(*,batch_size=50,timeout=5.0):
    if not enabled():return {"sent":False,"reason":"disabled"}
    url=endpoint()
    if not url:return {"sent":False,"reason":"no_endpoint"}
    events=pop(max(1,min(batch_size,100)))
    if not events:return {"sent":False,"reason":"empty"}
    try:
        events=sanitize_batch(events);payload={"schema_version":SCHEMA_VERSION,"events":events};raw=json.dumps(payload,separators=(",",":"),sort_keys=True).encode()
        if len(raw)>256000:raise ValueError("Telemetry payload exceeds 256 KB client ceiling.")
        response=requests.post(url,json=payload,timeout=timeout,headers={"User-Agent":"locdex-telemetry/1"});response.raise_for_status()
    except Exception as exc:
        prepend(events);return {"sent":False,"reason":"request_failed","error":str(exc)[:300]}
    return {"sent":True,"events":len(events),"status":response.status_code}
