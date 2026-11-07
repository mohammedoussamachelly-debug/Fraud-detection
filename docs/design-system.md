# SentinelAI design system

Neutral surfaces, fine borders and a restrained blue action color keep investigative evidence primary. Red/amber/green encode semantic status alongside readable text. No color alone communicates a result. Light/dark semantic tokens live in `frontend/src/index.css`.

Typography uses a local system sans-serif stack (Inter when installed), 12px metadata, 14px body/controls, 18px page headings and 24px operational counts. Line height is at least 1.4. IDs use monospace; financial quantities use tabular numerals. No remote font download is required.

Spacing follows a 4px base. Controls use 6px radii, surfaces 8px. The desktop shell has a 224px navigation rail and 48px header; below 1024px navigation becomes a labeled modal drawer. Content uses 16px mobile/24px desktop padding. Tables scroll within their surface, never force page overflow. Page actions and filters wrap on narrow screens.

Shared standards: PageHeader has one h1 and task-specific actions; DataTable provides keyboard activation and loading/error/empty states; FilterBar and DateRangeFilter label every input; ConfirmationDialog summarizes consequential actions; EvidenceViewer displays untrusted content as plain text; status badges always include words. Focus rings are visible and a skip link reaches main content. Dialogs trap focus, support Escape and restore focus through Radix.

Charts use real API data with explicit scope, visible labels and text equivalents. Network edges have arrowheads; node selection is also possible through a keyboard-accessible account list. Truncation and structural-signal disclaimers remain visible. Motion is minimal and respects reduced-motion preferences.
