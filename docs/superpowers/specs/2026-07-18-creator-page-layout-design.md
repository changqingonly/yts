# Creator Page Layout Redesign

## Goal

Redesign the creation page for ordinary song creators. The primary flow is:

1. Describe a song idea in one or two sentences.
2. Start creation.
3. Follow simplified progress and handle required decisions.
4. Review the final song and save it to assets.

Workflow editing, node configuration, trace inspection, raw JSON, and graph visualization remain available in an explicit advanced mode. They must not compete with the primary flow.

## Information Architecture

The page uses two persistent columns and one conditional drawer:

- A narrow conversation sidebar lists recent creation sessions and starts a new creation.
- The main column is a chronological creation feed. It contains the submitted idea, simplified progress, required human decisions, errors, and the final result.
- A compact composer stays at the bottom of the main column before and between runs.
- The result detail drawer opens only when the user selects a completed result. It is not an empty persistent third column.

The application shell's global navigation remains unchanged.

## Layout

### Conversation Sidebar

The sidebar is approximately 232 pixels wide on desktop. It contains:

- A single `New creation` command.
- A compact recent-session list using the existing workflow history data.
- Each row shows title or prompt summary, relative update time, and a restrained status marker.
- Selecting a row loads its trace through the existing history control flow.

The sidebar does not contain node lists, model controls, credits, filters, or workflow settings.

### Creation Feed

The feed is the dominant surface. Content appears in chronological order:

- The submitted song idea.
- A five-stage progress block.
- A human decision block when the workflow waits for input.
- A direct error block when execution fails.
- A final result summary after completion.

The feed scrolls independently. New run events remain visible without moving the composer. Technical node IDs, span IDs, duration chips, edge counts, LLM payloads, and raw JSON are excluded from ordinary mode.

### Bottom Composer

The composer follows the supplied reference image's structure: one rounded container with text input above and a compact toolbar below.

- Default input height fits two to three lines because most users enter one or two sentences.
- The input grows with content up to approximately six visible lines, then scrolls internally.
- The toolbar contains a single `Lyrics creation` mode label and the primary send button.
- Inspiration suggestions sit outside the composer and insert example directions into the input.
- The send button is disabled for an empty or whitespace-only prompt and while a workflow action is active.
- During an active run, the submitted prompt is immutable. A new prompt starts a new creation rather than mutating the running request.

### Result Drawer

Selecting the completed result opens a right-side drawer containing:

- Song title.
- Style Prompt.
- Full lyrics.
- `Save to assets` and `Create again` commands.

The drawer uses the existing final-delivery data and existing save action. Closing it returns focus to the selected result in the feed.

### Advanced Mode

An understated `Advanced mode` entry opens the existing technical workspace. It contains:

- Workflow node navigation.
- Node configuration and input/output inspection.
- Trace and raw result inspection.
- Workflow graph editing.

Ordinary and advanced modes share the same workflow state. Switching modes must not restart, clear, or synthesize a run.

## Simplified Progress

Existing workflow nodes map to five creator-facing stages:

| Creator stage | Existing groups |
| --- | --- |
| Understand | Input validation |
| Compose | Song brief, style and hook, structure design |
| Write | Lyric generation |
| Polish | Quality review, repair, formatting, title refinement |
| Complete | Delivery review and output |

The current stage is derived from real node statuses. Completed stages require their mapped nodes to have completed. Waiting and failed states remain attached to the stage containing the actual node. The UI must not infer completion when trace data does not support it.

## State And Control Flow

The redesign preserves the existing request sequence:

- Template loading still verifies the selected API target first.
- Starting a run still clears prior live run state and opens the existing stream.
- Trace and node-status messages update the current run incrementally.
- Waiting actions still resume the exact waiting node with the selected action.
- History selection still fetches the selected thread trace before updating the active view.
- Saving a result still calls the existing song asset service.

The UI may derive presentation state from this data, but it must not add fallback results, synthetic progress, swallowed exceptions, or silent recovery. Invalid workflow messages, malformed JSON, unavailable targets, interrupted streams, and failed requests remain explicit failures with actionable error text.

## Visual Direction

The visual direction is `Lyrics manuscript`, adapted to a dense working application:

- Deep-sea background and existing brand cyan/green remain consistent with the application shell.
- A restrained Chinese serif is used only for song ideas, result titles, and lyric content.
- Utility labels, controls, timestamps, and progress use the existing sans-serif system.
- The compact composer is the signature element: a soft manuscript surface with a quiet ruled texture and a bottom tool strip.
- Coral is reserved for required attention or an active waiting decision. Cyan-green indicates active creation and completion.
- Cards are not nested. Feed items use dividers and subtle surface changes rather than independent floating panels.

## Responsive Behavior

- Desktop: conversation sidebar plus main feed; result opens as a right drawer.
- Narrow desktop and tablet: sidebar collapses behind a history button; feed remains full width.
- Mobile: single-column feed with a sticky bottom composer; the result drawer becomes a full-width sheet.
- The composer, progress steps, and action rows use stable dimensions so status changes do not shift surrounding layout.

## Accessibility

- All icon-only controls have accessible names and tooltips.
- Composer, history rows, progress, waiting actions, and drawer support keyboard navigation.
- Focus remains visible on dark surfaces.
- Errors use `role="alert"`; non-error run updates use non-interrupting status semantics.
- Motion is limited to the active progress marker and disabled under reduced-motion preferences.

## Testing

Focused frontend source tests will cover:

- Ordinary mode contains the conversation sidebar, creation feed, compact composer, five-stage progress, and conditional result drawer.
- Technical node and trace controls are absent from ordinary mode and remain present in advanced mode.
- Empty prompts cannot start a run.
- Active workflow actions disable conflicting composer actions.
- Waiting actions remain available in the feed and call the existing resume flow.
- Errors render explicitly and are not replaced with a fallback state.
- History selection and final-result asset saving preserve their current service calls.
- Responsive CSS collapses the sidebar and drawer as specified.

The existing workflow route and orchestration tests remain the behavioral regression suite. Frontend build verification is required after the layout change.

## Out Of Scope

- Changing workflow APIs or orchestration behavior.
- Adding model selection, duration controls, credits, or generation parameters to ordinary mode.
- Editing generated lyrics inline.
- Replacing the application shell navigation.
- Adding new persistence or draft semantics.
