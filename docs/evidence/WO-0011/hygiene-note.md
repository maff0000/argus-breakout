# WO-0011 — Evidence hygiene note (AMD-0015 §2C)

`auditor-prompt.md` in this directory originally recorded the execution host's network address and an `ssh root@<address>` form. This commit scrubs the **working tree only**,
replacing them with `<delivery-host>`; history is not rewritten. The pre-correction commits (including WO-0011's merge into `main`) still contain the original value in this file's
history, and anyone reading that history should treat the address as non-secret but non-public. Dispatch prompts name `dell-debian` and absolute paths only (AMD-0015 §2C).
No other WO-0011 evidence file contains an address.
