# AI PCB Primary-Source Traceback v1

This stage is a machine-first, bounded source-traceback run over the five broker reports frozen by the Primary-Source Traceback Gate.

- The broker reports remain source-discovery-only artifacts.
- Only PCB-ER-A02, PCB-ER-B01, and PCB-ER-B02 claims are traced; PCB-ER-A04 and all other ERs are excluded.
- Unresolved citations are valid terminal states and do not trigger requests for human assistance.
- Newly acquired source documents are normalized and linked to report claims, but are not admitted to Evidence Assessment and do not change any ER status.
- The two Novoray reports remain one provisional common-origin chain.
- Network acquisition uses direct HTTP, direct proxy mode, local `trust_env=False`, bounded redirects, bounded response size, and fail-closed SSRF checks.

The deterministic analysis artifact is the traceback fact source. The Markdown report and bundle summary are projections of that artifact.
