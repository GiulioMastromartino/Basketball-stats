# BasketballStatsNative

Native iPadOS foundation for porting the existing Flask basketball stats web app into SwiftUI.

This first implementation includes:
- a generator-based Xcode project spec
- a native app shell optimized for iPad navigation
- a local-first JSON persistence layer
- domain models for games, player stats, live-game events, and lineup segments
- dashboard, games, game detail, live-game, and settings screens

## Generate the Xcode project

This repo does not currently have `xcodegen` installed in the active environment. Once it is available:

```bash
cd Native/BasketballStatsNative
xcodegen generate
open BasketballStatsNative.xcodeproj
```

## Current implementation scope

The app is intentionally structured around the migration plan:
- `App/` contains the app shell, environment wiring, and navigation
- `Models/` contains app-owned native entities
- `Services/` contains repository and persistence services
- `Features/` contains the first native screens

## Next implementation steps

- import existing web data from JSON/SQLite exports
- complete offline sync metadata and conflict handling
- port advanced analytics computations from Python to Swift
- replace browser-only play builder with a native editor
- add PDF generation and export flows
