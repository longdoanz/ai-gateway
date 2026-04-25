GET /getUsageLimits?origin=AI_EDITOR&profileArn=arn%3Aaws%3Acodewhisperer%3Aus-east-1%3A557690585382%3Aprofile%2FWAGWGX4DRUPU&resourceType=AGENTIC_REQUEST HTTP/1.1
x-amz-user-agent: aws-sdk-js/1.0.0 KiroIDE-0.11.63-89db0a9cea8c87596681f9c44ba98e0b9dc773f913d1e53e48eab0d5bba2befc
user-agent: aws-sdk-js/1.0.0 ua/2.1 os/win32#10.0.26200 lang/js md/nodejs#22.22.0 api/codewhispererruntime#1.0.0 m/N,E KiroIDE-0.11.63-89db0a9cea8c87596681f9c44ba98e0b9dc773f913d1e53e48eab0d5bba2befc
host: q.us-east-1.amazonaws.com
amz-sdk-invocation-id: 70b2c2ca-5aa3-433b-b2ef-b3ad2099c7f2
amz-sdk-request: attempt=1; max=1
Authorization: Bearer token
Connection: close

curl -H 'x-amz-user-agent: aws-sdk-js/1.0.0 KiroIDE-0.11.63-89db0a9cea8c87596681f9c44ba98e0b9dc773f913d1e53e48eab0d5bba2befc' -H 'user-agent: aws-sdk-js/1.0.0 ua/2.1 os/win32#10.0.26200 lang/js md/nodejs#22.22.0 api/codewhispererruntime#1.0.0 m/N,E KiroIDE-0.11.63-89db0a9cea8c87596681f9c44ba98e0b9dc773f913d1e53e48eab0d5bba2befc' -H 'amz-sdk-invocation-id: 70b2c2ca-5aa3-433b-b2ef-b3ad2099c7f2' -H 'amz-sdk-request: attempt=1; max=1' -H 'Authorization: Bearer Token' -H 'Connection: close' 'https://q.us-east-1.amazonaws.com/getUsageLimits?origin=AI_EDITOR&profileArn=arn%3Aaws%3Acodewhisperer%3Aus-east-1%3A557690585382%3Aprofile%2FWAGWGX4DRUPU&resourceType=AGENTIC_REQUEST'




HTTP/1.1 200 OK
Date: Sat, 25 Apr 2026 00:15:11 GMT
Content-Type: application/json
Content-Length: 927
Connection: close
x-amzn-RequestId: e855c6af-9f1f-4efe-b8de-94ccff9e6b50
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=47304000; includeSubDomains
X-Frame-Options: DENY
Cache-Control: no-cache
X-Content-Type-Options: nosniff

{"daysUntilReset":0,"limits":[],"nextDateReset":1.7775936E9,"overageConfiguration":{"overageLimit":null,"overageStatus":"ENABLED"},"subscriptionInfo":{"overageCapability":"OVERAGE_CAPABLE","subscriptionManagementTarget":"MANAGE","subscriptionTitle":"KIRO PRO+","type":"Q_DEVELOPER_STANDALONE_PRO_PLUS","upgradeCapability":"UPGRADE_INCAPABLE"},"totalUsage":null,"usageBreakdown":null,"usageBreakdownList":[{"bonuses":[],"currency":"USD","currentOverages":0,"currentOveragesWithPrecision":0.0,"currentUsage":1154,"currentUsageWithPrecision":1154.26,"displayName":"Credit","displayNamePlural":"Credits","freeTrialInfo":null,"nextDateReset":1.7775936E9,"overageCap":10000,"overageCapWithPrecision":10000.0,"overageCharges":0.0,"overageRate":0.04,"resourceType":"CREDIT","unit":"INVOCATIONS","usageLimit":2000,"usageLimitWithPrecision":2000.0}],"userInfo":{"email":null,"userId":"d-9667b5ad50.996aa52c-0071-7089-7be0-954f2df5134c"}}