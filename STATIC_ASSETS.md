# Static asset notes

The public site keeps only the assets it actually loads. Legacy duplicates from
the original template bundle (an older jQuery/jQuery Migrate pair, a second
Bootstrap 4 script, an unused Bootstrap CSS folder, unused stylesheets, and the
Flaticon demo/preprocessor files) were removed. No template references them.

Licensing and attribution for retained assets:

- Flaticon icon font — `static/fonts/font/`. License copy retained at
  `static/fonts/license/license.pdf`.
- Bootstrap 5 vendor bundle — `static/vendor/bootstrap5/`. MIT license retained
  at `static/vendor/bootstrap5/LICENSE`.
- Other bundled libraries (Bootstrap 4, jQuery, Owl Carousel, AOS, Magnific
  Popup, Stellar, Datepicker) keep the license headers shipped with their files.

Brand assets derived from `static/images/logo.png`:

- `static/images/logo-header.png` — transparent monochrome header mark.
- `static/images/favicon-32.png` and `static/images/apple-touch-icon.png` —
  square crops used for browser and home-screen icons.
