from locdex.extensions import CloudAuthorizationRequest,Decision,NullEnterpriseExtension,ToolAuthorizationRequest

def test_null_enterprise_extension_adds_no_private_dependency():
 ext=NullEnterpriseExtension(); assert ext.authorize_tool(ToolAuthorizationRequest("read_file","read",{},".")).decision is Decision.ALLOW; assert ext.authorize_cloud(CloudAuthorizationRequest("anthropic","x","minimal",1000,500)).decision is Decision.ALLOW
