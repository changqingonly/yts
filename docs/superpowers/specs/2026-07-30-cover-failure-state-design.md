# Cover Failure State Design

## Goal

Keep the default record as the primary music-player visual when cover generation fails, and reduce the failure UI to a quiet status line with an explicit retry action.

## Behavior

- `failed`: show one muted status line reading `封面生成失败` and a text `重试` action.
- `unavailable`: show one muted status line reading `本地图片模型未安装` with no error panel.
- Remove the failure-details icon, expandable error dialog, and raw backend error text from the player surface.
- Keep the existing retry request and status polling behavior unchanged.
- Keep generated-cover delete/regenerate controls unchanged when a cover exists.

## Visual Constraints

- The default record remains visible and unchanged.
- Failure and unavailable text use the existing muted status treatment, not danger colors or bordered alert containers.
- The retry action remains keyboard accessible as a text button.

## Verification

- Update the frontend source-level test to assert the quiet status and retry action while rejecting the removed detail dialog.
- Run the focused and full music lifecycle tests.
- Build the frontend and visually inspect the local music page at desktop width.
