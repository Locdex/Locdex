"""Offline training contract; no sklearn/torch dependency in the Locdex client."""
def training_contract():return {"input":"sanitized RoutingRecord rows","output":"versioned local router artifact","online_training":False}
