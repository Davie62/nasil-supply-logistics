# NASIL mobile experience

Implemented 11 November 2026. The existing Django views, permission checks, QuerySets,
CSRF protection, approval policies and orange branding remain authoritative.

## UX decisions

- Retain the familiar staff sidebar and searchable module switcher on desktop,
  with a role-filtered horizontal row for the eight primary workspace sections.
  On phones/tablets, use the existing Bootstrap drawer with larger touch targets,
  keyboard dismissal and focus return. Customer navigation becomes an explicit
  expandable menu with current-section indicators. The public website menu now
  supports keyboard focus, Escape and labelled submenu buttons.
- Turn simple operational tables into labelled record cards below 768px, using the
  same records and links. Desktop tables keep native column headers. Long references,
  names and audit details wrap. Tables with complex spanning headers are not blindly
  transformed. Without JavaScript, native tables remain available in their scroll wrappers.
- Keep create actions in page headers. On mobile lists, show a compact floating
  create action only after its header action scrolls out of view. It respects the
  same server-provided permission-controlled URL and reserves footer space.
- Preserve all three booking-summary values on phones. A keyboard-accessible native
  range input selects the existing discrete 7/30/90-day booking periods; Apply still
  submits the original server-side range value. No invented pricing/distance sliders.
- Keep field validation errors inline. Django messages use reusable severity-aware
  toasts: success/info dismiss after ten seconds, paused on hover/focus; errors and
  warnings remain until manually dismissed. Network failures retain current records.
- Use native dialogs for invoice voiding and quotation/shipment rejection or
  cancellation. Escape and Go back cancel; confirmation submits the original form,
  including the original submitter, through the existing CSRF-protected workflow.

## Component architecture

| Layer | Files | Responsibility |
| --- | --- | --- |
| Shared visual tokens | `static/css/app-ui.css` | Orange/neutral tokens, focus treatment, spacing, touch sizes, cards, responsive forms/tables, dialogs, skeletons, toasts |
| Progressive interactions | `static/js/app-ui.js` | Table labels, chart range control, menus, form help/error associations, notifications, confirmation and same-page GET updates |
| Shared partials | `templates/ui/` | Toast region, confirmation dialog, skeleton structure, empty states, permission-controlled create action |
| Lists and forms | `templates/operations/components/` | Query-preserving pagination, tables, reusable form fields |
| Shell integration | staff, portal, login and public base templates | Load the shared assets once per document; staff/portal opt into result updates |
| Server helper | `operations/templatetags/operations_ui.py` | Bounded/elided page numbers; existing query-string preservation |

The existing dashboard styles and Bootstrap versions remain in place. The shared
layer is additive; public marketing and authenticated application shells keep their
own typography/layout conventions. It does not introduce a React/SPA framework,
duplicate record rendering, an API dependency or a second business-rule layer.

### Notifications

Existing server code continues to use `messages.success`, `messages.error`,
`messages.warning` and `messages.info`. Client interactions can use:

```javascript
document.dispatchEvent(new CustomEvent('nasil:notify', {
  detail: {message: 'Shipment created.', tone: 'success'}
}));
```

Messages are inserted as text, never interpreted as HTML. Confirmation buttons opt
in with `data-confirm-message="..."`; JavaScript never replaces approval validation.

## Loading and navigation

Staff/customer search, report filters, booking-period filters and pagination can
refresh their main content through a same-origin GET. Cards, tables/reports and forms
have distinct skeleton layouts. Skeletons represent actual pending requests, never
an artificial startup delay. No-JavaScript submissions remain normal Django pages.

The client aborts superseded requests, restores content after failures, handles
authentication redirects, updates the URL/title, supports Back/Forward and moves
focus to the updated main region. Export links and write requests stay native;
there is no automatic retry of a financial or stock mutation. Fetched scripts are
not executed. QuerySets, pagination sizes and exports still run on the server.

## Accessibility and performance

- Semantic table/row/cell roles and original headers survive the visual card layout.
  Mobile field labels are hidden from assistive technology to avoid duplicate reading.
- Inputs use a readable 16px size, controls have approximately 44px minimum touch
  targets, radios/checkboxes have clear orange selection, and error/help text is
  associated with its control. Radio groups use fieldsets/legends.
- Native dialogs manage focus; custom menus support Escape and focus return.
  Existing Bootstrap focus management remains responsible for the staff drawer.
- Loading uses `aria-busy` and a live status. Toasts use status/alert severity.
  Reduced-motion preferences disable shimmer, entrance and exit animation.
- A bounded page-number window avoids rendering thousands of pagination links.
  Event delegation supports replaced results without repeatedly registering handlers.
  No chart or table framework was added. Marketing images declare intrinsic
  dimensions to reserve space, and below-fold home images use native lazy loading
  and asynchronous decoding. The existing lightweight SVG booking chart remains in use.

These are implemented accessibility measures, not a WCAG certification. Screen-reader
acceptance on physical iOS/Android devices, field testing with warehouse/dispatch
teams and measured production performance budgets remain release checks. Do not
claim Lighthouse scores or complete WCAG conformance without those measurements.

## Verification

Regression checks: 214 Django tests run, 210 passed and four PostgreSQL-only tests
skipped on SQLite. Shared-component tests cover escaped notifications, active portal
navigation, disabled/compact pagination, large page counts and preserved filters.
Browser fixtures use an isolated SQLite database and synthetic accounts; real customer
records, passwords and external providers are untouched.

Staff layout checks: 26 pages at 320, 375, 390, 430, 768, 1024, 1180, 1440 and 1920px (234 combinations),
including lists, details, forms, reports, audit panels and commercial module screens.
Public/customer checks: 171 combinations over the same widths. The final matrices
reported no page-level horizontal overflow and no JavaScript runtime errors.
The portal's legacy 620px table minimum was removed at mobile widths; the final
portal checks also assert no internal table overflow or clipped tracking links.
All eight interaction checks passed: staff menu/Escape, server-backed period slider,
pagination/loading/Back, request-failure recovery, dialog cancellation, confirmed
native CSRF-protected submission, text-only/manual-dismiss toasts and auto-dismiss.
The focused final suites also passed (44 customer/shared-component tests and 20
navigation/shared-component tests). A 320x640 viewport and 1180x768 landscape tablet
were included. Physical-device and full assistive-technology acceptance remain open.
After the last public-form refinements, the public/core/shared suite ran 47 tests
(45 passed, two PostgreSQL-only skips); JavaScript syntax, patch consistency and the
417-file source security scan passed. The local server was refreshed and returned
HTTP 200 with the new shared assets.
Local screenshot/interaction artifacts are kept in ignored `output/playwright/`.

No deployment is implied by these local changes; a remote demonstration requires a
separate deployment step.
