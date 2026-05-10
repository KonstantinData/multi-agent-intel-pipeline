# Multi Role Task Template

Task: <Title>

Target State: <Baseline | Release-ready | Audit-ready>
Scope: <Folders/Files/PR>
Blocking Threshold: <P0 | P0+P1 | All>

Specialist Plan:
1. <role-1> - Goal: <...> - Output: <...>
2. <role-2> - Goal: <...> - Output: <...>
3. <role-3> - Goal: <...> - Output: <...>

Gate Rule:
- Merge is ALLOWED only if all required roles report no blocking findings.
- Conflict resolver: <e.g., security-architect > ai-compliance-owner > release-manager>.

Dynamic Expansion:
- Trigger detected: <yes/no>
- New role: <role>
- Reason: <evidence-based reason>
- Status: <added during execution>

Final Output:
- One consolidated report with one section per role plus a final global decision.
