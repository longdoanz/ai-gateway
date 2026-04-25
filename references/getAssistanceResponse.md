POST /generateAssistantResponse HTTP/1.1
content-type: application/json
content-length: 4226
x-amzn-codewhisperer-optout: true
x-amzn-kiro-agent-mode: intent-classification
x-amz-user-agent: aws-sdk-js/1.0.34 KiroIDE-0.11.63-89db0a9cea8c87596681f9c44ba98e0b9dc773f913d1e53e48eab0d5bba2befc
user-agent: aws-sdk-js/1.0.34 ua/2.1 os/win32#10.0.26200 lang/js md/nodejs#22.22.0 api/codewhispererstreaming#1.0.34 m/E KiroIDE-0.11.63-89db0a9cea8c87596681f9c44ba98e0b9dc773f913d1e53e48eab0d5bba2befc
host: q.us-east-1.amazonaws.com
amz-sdk-invocation-id: ef8151f1-a326-4324-ad22-f77baf080b74
amz-sdk-request: attempt=1; max=3
Authorization: Bearer token
Connection: close

{"conversationState":{"agentContinuationId":"9841fa64-c868-4d56-a4f0-7119fe56cfe3","agentTaskType":"vibe","chatTriggerType":"MANUAL","conversationId":"2b699faf-b053-4646-90ee-78803ca9206a","currentMessage":{"userInputMessage":{"content":"halo\n\n<EnvironmentContext>\nThis information is provided as context about user environment. Only consider it if it's relevant to the user request ignore it otherwise.\n\n<OPEN-EDITOR-FILES>\n<file name=\"run.sh\" />\n<file name=\"README.md\" />\n<file name=\"/C:/Users/longd/AppData/Roaming/Kiro/User/settings.json\" />\n<file name=\"/C:/Users/longd/.kiro/settings/mcp.json\" />\n<file name=\"export_live.py\" />\n</OPEN-EDITOR-FILES>\n\n<ACTIVE-EDITOR-FILE>\n<file name=\"kiro.kiroAgent.Kiro - MCP Logs\" />\n</ACTIVE-EDITOR-FILE>\n</EnvironmentContext>","modelId":"simple-task","origin":"AI_EDITOR","userInputMessageContext":{}}},"history":[{"userInputMessage":{"content":"\nYou are an intent classifier for a language model.\n\nYour job is to classify the user's intent based on their conversation history into one of two main categories:\n\n1. **Do mode** (default for most requests)\n2. **Spec mode** (only for specific specification/planning requests)\n\nReturn ONLY a JSON object with 3 properties (chat, do, spec) representing your confidence in each category. The values must always sum to 1.\n\n### Category Definitions\n\n#### 1. Do mode (DEFAULT CHOICE)\nInput belongs in do mode if it:\n- Is NOT explicitly about creating or working with specifications\n- Requests modifications to code or the workspace\n- Is an imperative sentence asking for action\n- Starts with a base-form verb (e.g., \"Write,\" \"Create,\" \"Generate\")\n- Has an implied subject (\"you\" is understood)\n- Requests to run commands or make changes to files\n- Asks for information, explanation, or clarification\n- Ends with a question mark (?)\n- Seeks information or explanation\n- Starts with interrogative words like \"who,\" \"what,\" \"where,\" \"when,\" \"why,\" or \"how\"\n- Begins with a helping verb for yes/no questions, like \"Is,\" \"Are,\" \"Can,\" \"Should\"\n- Asks for explanation of code or concepts\n- Examples include:\n  - \"Write a function to reverse a string.\"\n  - \"Create a new file called index.js.\"\n  - \"Fix the syntax errors in this function.\"\n  - \"Refactor this code to be more efficient.\"\n  - \"What is the capital of France?\"\n  - \"How do promises work in JavaScript?\"\n  - \"Can you explain this code?\"\n  - \"Tell me about design patterns\"\n\n#### 2. Spec mode (ONLY for specification requests)\nInput belongs in spec mode ONLY if it EXPLICITLY:\n- Asks to create a specification (or spec) \n- Uses the word \"spec\" or \"specification\" to request creating a formal spec\n- Mentions creating a formal requirements document\n- Involves executing tasks from existing specs\n- Examples include:\n  - \"Create a spec for this feature\"\n  - \"Generate a specification for the login system\"\n  - \"Let's create a formal spec document for this project\"\n  - \"Implement a spec based on this conversation\"\n  - \"Execute task 3.2 from my-feature spec\"\n  - \"Execute task 2 from My Feature\"\n  - \"Start task 1 for the spec\"\n  - \"Start the next task\"\n  - \"What is the next task in the <feature name> spec?\"\n\nIMPORTANT: When in doubt, classify as \"Do\" mode. Only classify as \"Spec\" when the user is explicitly requesting to create or work with a formal specification document.\n\nEnsure you look at the historical conversation between you and the user in addition to the latest user message when making your decision.\nPrevious messages may have context that is important to consider when combined with the user's latest reply.\n\nIMPORTANT: Respond ONLY with a raw JSON object. No explanation, no commentary, no additional text, no markdown formatting, no code fences (```), no backticks.\n\nExample response (exactly this format):\n{\"chat\": 0.0, \"do\": 0.9, \"spec\": 0.1}\n\nHere is the last user message:\nhalo","modelId":"simple-task","origin":"AI_EDITOR"}},{"assistantResponseMessage":{"content":"I will follow these instructions","toolUses":[]}}]},"profileArn":"arn:aws:codewhisperer:us-east-1:557690585382:profile/WAGWGX4DRUPU"}

HTTP/1.1 200 OK
Date: Sat, 25 Apr 2026 00:15:41 GMT
Content-Type: application/json
Transfer-Encoding: chunked
Connection: close
x-amzn-RequestId: 948db5ae-78a9-4f88-8589-d8d4a2f9309d
x-amzn-codewhisperer-conversation-id: 2b699faf-b053-4646-90ee-78803ca9206a
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=47304000; includeSubDomains
X-Frame-Options: DENY
Cache-Control: no-cache
X-Content-Type-Options: nosniff
