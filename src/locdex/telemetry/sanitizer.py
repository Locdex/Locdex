from dataclasses import fields
from .schema import RoutingTelemetryEvent
ALLOWED_FIELDS={f.name for f in fields(RoutingTelemetryEvent)}
def sanitize_event(event):
    unknown=set(event)-ALLOWED_FIELDS
    if unknown:raise ValueError(f"Telemetry event contains unsupported fields: {sorted(unknown)}")
    for k,v in event.items():
        if isinstance(v,str) and len(v)>160:raise ValueError(f"Telemetry string too long: {k}")
    return dict(event)
def sanitize_batch(events,*,max_events=100):
    if not isinstance(events,list) or not events:raise ValueError("Telemetry batch must contain at least one event.")
    if len(events)>max_events:raise ValueError(f"Telemetry batch exceeds {max_events} events.")
    return [sanitize_event(e) for e in events]
