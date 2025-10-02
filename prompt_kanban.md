Create a fully functional Kanban board in a single HTML file using vanilla JavaScript (no frameworks like react).

Requirements:
- Columns: Backlog, In Progress, Review, Done.
- Cards must be:
  - draggable across columns,
  - editable in place,
  - persisted in localStorage (state survives reloads) - please use your own namespace,
  - deletable with a confirmation prompt.
- Each column provides an “Add card” action.
- Style with Tailwind via CDN.
- Add subtle CSS transitions and trigger a confetti animation when a card moves to “Done”.
- Thoroughly comment the code.
- dont use window.alert or window.prompt to add/edit/delete cards
- if there are no cards yet, create some dummy cards
- modern and vibrant design

As answer return the plain HTML of the working application (script and styles included)
