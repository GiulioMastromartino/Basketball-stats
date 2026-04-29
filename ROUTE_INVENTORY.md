# Route Inventory

## Summary

| Blueprint | Prefix | Routes | Primary Return |
|-----------|--------|--------|----------------|
| main_bp | (none) | 23 | HTML + JSON |
| auth_bp | `/auth` | 9 | HTML |
| api_bp | `/api/v1` | 2 | JSON |
| analytics_bp | (none) | 10 | HTML + JSON + redirects |
| plays_bp | (none) | 13 | HTML |
| builder_api_bp | `/api/v1` | 2 | JSON |
| reports_bp | `/reports` | 12 | PDF |
| advanced_api_bp | `/api/advanced` | 28 | JSON |

**Total Routes: 99** (including aliases/redirects)

## Detailed Route Tables

### main_bp (no prefix)

| URL | Methods | Returns | Notes |
|-----|---------|---------|-------|
| `/landing` | GET | HTML | Landing page (unauthenticated) |
| `/` | GET | HTML | Dashboard |
| `/glossary` | GET | HTML | Stats glossary |
| `/live-game` | GET | HTML | Live game tracking |
| `/api/plays` | GET | JSON | Plays list for live game |
| `/live-game/save` | POST | JSON | Save live game data |
| `/upload-game` | GET, POST | HTML/Redirect | Game file upload |
| `/game/<int:game_id>/export-raw` | GET | JSON/File | Export raw game data |
| `/game/<int:game_id>` | GET | HTML | Game detail |
| `/game/<int:game_id>/delete` | POST | Redirect | Delete game |
| `/player/<player_name>` | GET | HTML | Player detail |
| `/team-detail` | GET | HTML | Team stats |
| `/players` | GET | HTML | Players list |
| `/players/cards.pdf` | GET | PDF | Player cards PDF |
| `/players/pages.zip` | GET | ZIP | All player pages ZIP |
| `/games-list` | GET | HTML | Games list |
| `/teams/<opponent_name>` | GET | HTML | Opponent detail |
| `/advanced-analytics` | GET | HTML | Advanced analytics dashboard |
| `/game/<int:game_id>/advanced-report` | GET | HTML | Advanced game report |
| `/lineups` | GET | HTML | Lineups list |
| `/lineup/<int:lineup_id>` | GET | HTML | Lineup card |
| `/game/<int:game_id>/lineup-combinations` | GET | HTML | Game lineup combinations |
| `/lineup-combo/<combo_type>/<path:players_key>` | GET | HTML | Duo/trio combo card |
| `/create-test-game` | POST | Redirect | Create test game (admin) |

### auth_bp (prefix: `/auth`)

| URL | Methods | Returns |
|-----|--------|---------|
| `/login` | GET, POST | HTML/Redirect |
| `/callback` | GET | Redirect |
| `/logout` | GET | Redirect |
| `/verify-otp` | GET, POST | HTML |
| `/users` | GET | HTML (admin) |
| `/settings/update` | POST | Redirect (admin) |
| `/users/create` | GET, POST | HTML/Redirect (admin) |
| `/users/<int:user_id>/delete` | POST | Redirect (admin) |
| `/users/<int:user_id>/role` | POST | Redirect (admin) |

### api_bp (prefix: `/api/v1`) – **CONFLICT: shares prefix with builder_api_bp**

| URL | Methods | Returns |
|-----|--------|---------|
| `/plays` | GET | JSON |
| `/plays/types` | GET | JSON |

### builder_api_bp (prefix: `/api/v1`) – **CONFLICT: shares prefix with api_bp**

| URL | Methods | Returns |
|-----|--------|---------|
| `/plays/api/save-canvas` | POST | JSON |
| `/plays/api/load-canvas/<int:play_id>` | GET | JSON |

### analytics_bp (no prefix)

| URL | Methods | Returns |
|-----|--------|---------|
| `/analytics` | GET | HTML |
| `/api/analytics/team_overview` | GET | JSON |
| `/api/analytics/multi_compare` | GET | JSON |
| `/api/analytics/player_progression` | GET | JSON |
| `/api/analytics/consistency_leaderboard` | GET | JSON |
| `/api/analytics/shooting_breakdown` | GET | JSON |
| `/api/analytics/role_analysis` | GET | JSON |
| `/games/<int:game_id>/summary.pdf` | GET | Redirect |
| `/team/report.pdf` | GET | Redirect |
| `/player/<player_name>/report.pdf` | GET | Redirect |
| `/analytics/reports/download-all` | GET | Redirect |

### plays_bp (no prefix)

| URL | Methods | Returns |
|-----|--------|---------|
| `/plays` | GET | HTML |
| `/plays/view/<int:play_id>` | GET | HTML |
| `/plays/add` | POST | Redirect |
| `/plays/edit/<int:play_id>` | POST | Redirect |
| `/plays/delete/<int:play_id>` | POST | Redirect |
| `/plays/` | GET | HTML |
| `/plays/create` | GET | HTML |
| `/plays/<int:play_id>` | GET | HTML |
| `/plays/<int:play_id>/edit-builder` | GET | HTML |
| `/plays/<int:play_id>/delete` | POST | Redirect |
| `/plays/clear-all` | POST | Redirect |
| `/plays/types/add` | POST | Redirect |
| `/plays/types/<int:type_id>/delete` | POST | Redirect |

### reports_bp (prefix: `/reports`)

| URL | Methods | Returns |
|-----|--------|---------|
| `/games/<int:game_id>/summary.pdf` | GET | PDF |
| `/games/<int:game_id>/advanced_summary.pdf` | GET | PDF |
| `/team/report.pdf` | GET | PDF |
| `/player/<player_name>/report.pdf` | GET | PDF |
| `/download-all` | GET | ZIP |
| `/games/<int:game_id>/visual.pdf` | GET | PDF |
| `/lineup/report.pdf` | GET | PDF |
| `/player/<player_name>/scouting.pdf` | GET | PDF |
| `/season/trends.pdf` | GET | PDF |
| `/clutch/report.pdf` | GET | PDF |
| `/live/halftime-pdf` | POST | PDF |
| `/games/<int:game_id>/evolution.pdf` | GET | PDF |

### advanced_api_bp (prefix: `/api/advanced`)

| URL | Methods | Returns |
|-----|--------|---------|
| `/player/<player_name>/advanced` | GET | JSON |
| `/player/<player_name>/usage` | GET | JSON |
| `/player/<player_name>/pps` | GET | JSON |
| `/clutch/<int:game_id>` | GET | JSON |
| `/clutch/season` | GET | JSON |
| `/lineup/on-off/<player_name>` | GET | JSON |
| `/lineup/duos` | GET | JSON |
| `/lineup/trios` | GET | JSON |
| `/lineup/rankings` | GET | JSON |
| `/lineups/combinations` | GET | JSON |
| `/lineups/combinations/detail` | GET | JSON |
| `/rotation/<int:game_id>` | GET | JSON |
| `/lineup/game/<int:game_id>/rankings` | GET | JSON |
| `/shots/chart` | GET | JSON |
| `/shots/heatmap` | GET | JSON |
| `/shots/hexbin` | GET | JSON |
| `/shots/by-play/<int:play_id>` | GET | JSON |
| `/plays/rankings` | GET | JSON |
| `/four-factors` | GET | JSON |
| `/possessions/reconstruct/<int:game_id>` | POST | JSON |
| `/possessions/<int:game_id>` | GET | JSON |
| `/zones` | GET | JSON |
| `/zones/classify` | POST | JSON |
| `/game/<int:game_id>/report` | GET | JSON |
| `/lineups` | GET | JSON |
| `/lineup/<int:lineup_id>` | GET | JSON |
| `/lineup/<int:lineup_id>` | PUT | JSON |

## Known Issues & Conflicts

1. **Duplicate `/api/v1` prefix**: Both `api_bp` and `builder_api_bp` are registered under `/api/v1`, leading to potential overlapping routes. Recommend merging into a single `api_v1_bp`.
2. **Duplicate formula definitions**: `calculate_ts_percent` appears in both `core/utils.py` and `core/advanced_analytics.py`.
3. **Inline calculations**: eFG% computed inline in `web/routes/reports.py` instead of using `calculate_efg_percent`.
4. **Inline possession formula** in multiple places.
5. **Inline game score** in `core/services/analytics_service.py` instead of using `calculate_game_score`.

## Action Items

- PR 1: Extensions consolidation (completed)
- PR 2: This inventory (completed)
- PR 3: Merge API blueprints
- PR 4: Consolidate all formula definitions and replace inlines
- PR 5: Extract `game_detail` route into service
- PR 6: Extract `player_detail` and related context
- PR 7: Extract report services

