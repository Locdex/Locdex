from dataclasses import dataclass
@dataclass
class RoutingSession:
    current_model:str|None=None; current_route:str|None=None; attempts:int=0; failures:int=0; switch_count:int=0; last_failure_reason:str|None=None
    def record_choice(self,model,route):
        if self.current_model and self.current_model!=model:self.switch_count+=1
        self.current_model=model;self.current_route=route;self.attempts+=1
    def record_failure(self,reason):self.failures+=1;self.last_failure_reason=reason
    def switching_penalty(self,model):return 0.0 if self.current_model in {None,model} else .04
