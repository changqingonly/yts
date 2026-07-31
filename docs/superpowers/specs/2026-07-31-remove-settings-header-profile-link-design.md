# Remove Settings Header Profile Link Design

## Goal

Remove the duplicate profile entry from the settings page header.

## Behavior

- Remove the top-right `个人资料` link from the settings header.
- Keep `设置 -> 账户 -> 个人资料` as the only profile entry within settings.
- Keep the `/profile/setup` route and account-section behavior unchanged.
- Remove CSS used only by the deleted header link, including mobile overrides and focus selectors.

## Verification

- Assert the header link class is absent while the account link remains.
- Run the focused layout test, full layout test file, and frontend build.
