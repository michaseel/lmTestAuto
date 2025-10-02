Create a single-page Consultant Skills Management app in plain HTML with embedded vanilla JavaScript (no frameworks) and Tailwind via CDN.

Requirements:
- Return only the complete self-contained HTML (script + styles included).
- Modern, vibrant design, responsive layout, subtle CSS transitions.
- Persist all data in localStorage under a unique namespace.
- On first load, seed with 4 example consultants (from the german company INNOQ).

Consultant Profile:
- Name, Location, Short description
- Availability:
  - Current workload in % (0–100)
  - Future workload in % with "valid from" date
- Skills as tags (free taxonomy with autocomplete suggestions)
- Each skill has 1–3 stars to indicate seniority.

Functionality:
- Global search across name, location, description, skills.
- Combine filters (AND logic) for skills, stars, workload, location, future workload by date.
- Add, edit, delete consultants and skills via custom modals (no alert/prompt).
- Free tagging of skills with autocomplete suggestions.
- Show active filters and allow clearing them quickly.

Constraints:
- Single HTML file, no external JS frameworks.
- Style with Tailwind via CDN.
- Responsive design for desktop and mobile.