# NASIL dashboard design and UX guide

## Reference and branding

The dashboard adapts the layout at https://preview.themewagon.com/dasher/.
The reference's published CSS was inspected for its actual tokens. This implementation
uses original Django templates/CSS and locally vendored Bootstrap 5.3.3 (MIT license
in static/vendor/bootstrap5/LICENSE); it does not embed the remote demo or its data.

Keep NASIL's name and workspace identity. Public company pages retain their existing
branding. Within the staff dashboard, use NASIL's orange and neutral palette, Public
Sans, light cards, subtle shadows, dashed separators and generous spacing. Do not
copy Dasher's logo, user profiles, commercial upsells or demonstration metrics.

| Token | Value / use |
| --- | --- |
| Primary | #f89d13; main actions, chart line, selected navigation |
| Primary dark | #9c4700; readable links and selected navigation text |
| Primary lighter | #fff3e2; soft orange accents; peach/orange welcome gradient |
| Text | #1c252e |
| Secondary text | #637381 |
| Soft background | #f9fafb |
| Separator | #dfe3e8 |
| Completed / info | #d36a08 / #289ac4 |
| Warning / danger | #ffcc70 / #ff5630 |
| Typography | Public Sans, 400-800, system sans-serif fallback |
| Layout | 248px desktop sidebar; 72px topbar; 20-32px content gutters |
| Cards | 16px radius, 22-24px padding, restrained shadow |

Tokens, dark-mode overrides and component rules live in static/css/dashboard-dasher.css.
The previous dashboard stylesheet is retained but is not loaded by the new shell.
Bootstrap 5 is scoped to dashboard templates; the public website keeps its own assets.

## Django-compatible component library

- `dashboard/base_dashboard.html`: shared navigation, responsive drawer, topbar,
  accessible module-search modal, notifications, account menu, flash alerts and footer.
- `dashboard/components/kpi_card.html`: include with label, value, description,
  icon, tone and optional suffix/badge. Values always come from the permitted queryset.
- `dashboard/components/status_badge.html`: include with status and label. Color is
  reinforced with readable text, not used as the sole status indicator.
- `dashboard/workflow_list.html`: consistent table, status cells, record count,
  in-page search, explicit filter state/clear action, empty and no-match states.
- `dashboard/workflow_form.html`: bound Django forms, CSRF, required labels, visible
  field/non-field errors, help text and a real back link. No client-side save simulation.
- `dashboard/presentation.py`: daily booking series and permission-filtered operational
  notifications. `dashboard/context_processors.py` supplies notifications across staff pages.
- `dashboard.js`: Bootstrap offcanvas/modal integration, saved desktop collapse and
  theme preferences, keyboard module search, client-side table filtering and date-range
  submission. No front-end framework or Node build step is required by Django.

## Chart and notification semantics

All-time cards use stored records; delivery completion is delivered divided by all
shipments, including cancelled records. No invented growth percentages are displayed.
The booking chart counts creation dates over 7, 30 or 90 days and fills missing days
with zero. It is a booking trend, not a historical delivery-events chart. Invalid ranges
fall back to 30 days. Current statuses are shown separately in the donut and text legend.
The SVG chart has a title/description, and all chart values are also presented as text.

The notification dropdown shows current unread enquiries, pending quotations and
overdue active shipments. It is a page-load snapshot, not a real-time notification
service or persistent notification history. Counts and links require the corresponding
model-view permission. Completed/cancelled shipments are not classified as overdue.
No enquiry subjects, names or message bodies are exposed in the dropdown.

## Supply-chain UX review

| User goal | Implemented flow | Boundary |
| --- | --- | --- |
| Review new demand | Overview -> pending quotations -> detail -> pricing/approval workflow | Maker/approver separation and amount thresholds are enforced. |
| Prepare dispatch | Workflow step -> pending shipments; New shipment -> creation form | Creation still uses the existing business rules. |
| Follow delivery | In-transit workflow step -> filtered shipment list -> edit for permitted staff | Location/status are recorded manually. |
| Resolve overdue work | Notification -> overdue active shipments, with delivery dates and routes visible | Alerts use estimated dates, not carrier event feeds. |
| Respond to enquiries | Unread notification -> unread message list -> message detail -> explicit mark-as-read POST | View and change permissions remain separate. |
| Find a module | Visible sidebar or Ctrl/Cmd+K search -> a permitted module | This searches module names, not customer/shipment data. |
| Find a record | Server-side list search/filter -> paginated records -> detail | Search applies to the full permitted QuerySet. |
| Manage inventory | Warehouse items -> details -> audited receipt/issue | Negative stock and stale updates are rejected. |
| Manage orders | Clearly labeled Planned entry | Order management remains outside the current implementation. |

Existing staff/model permissions are preserved. Read-only staff see records without
edit/create controls. A staff account without module permissions receives an explicit
access explanation. Account logout remains a CSRF-protected POST. Sample data lives
only in the ignored, isolated visual QA database and never seeds the real database.

## Responsive and accessibility rules

- Desktop: fixed, collapsible sidebar; four KPI cards; two-column analytics and workflow.
- Tablet: KPI cards wrap; charts/tables adapt to the space remaining beside navigation.
- Under 992px: Bootstrap offcanvas navigation with backdrop, focus trap and Escape close.
- Mobile: single-column major panels, two compact KPI columns; tables scroll inside
  their cards instead of widening the document; search/notification controls remain usable.
- Theme and sidebar preferences are optional; blocked local storage must not break UI.
- Interactive controls use buttons/links, focus indicators and accessible names. Charts
  and status labels have text equivalents. Reduced-motion preference disables transitions.

## Verification and remaining scope

Django suite: 46 tests discovered, 45 passed, 1 PostgreSQL-only concurrency test skipped.
System checks passed and no model migration was introduced. Coverage includes chart
ranges/zero filling, invalid ranges, notification permissions and completed-shipment
exclusion, read-only actions, notification refresh and real operational drilldown filters.

Browser checks cover the shell, module search, theme switching, sidebar/drawer,
notification drilldowns, table search, chart ranges, responsive overflow and shared
forms. Screenshots under output/playwright use sample records only.

The verification counts above describe the original dashboard redesign. Core business
rules and internal operations have since added workflow history, server pagination,
inventory, reports, staff screens, private delivery proof and settings. See
BUSINESS_RULES.md and INTERNAL_OPERATIONS.md. Order processing, production PostgreSQL/
deployment validation, broader inventory functions and external notifications remain
roadmap work. See ROADMAP.md and DEPLOYMENT.md.
