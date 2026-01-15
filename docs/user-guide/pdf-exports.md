# PDF Exports

The PDF export system generates professional, publication-ready reports for games, players, and teams, integrating detailed plays analysis.

## Available Reports

### 1. Game Reports
Individual game analysis with plays breakdown.
*   **Access**: Go to any Game Detail page and click "Export PDF".
*   **Content**:
    *   Game Summary (Score, Opponent, Date)
    *   Plays Analysis (Efficiency per play type)
    *   Shot Events Analysis (Timeline)
    *   Overall Shooting Stats

### 2. Player Reports
Career performance with plays-based efficiency.
*   **Access**: Go to any Player Profile and click "Export Report".
*   **Content**:
    *   Career Statistics
    *   Performance by Play (e.g., FG% on "Pick and Roll")
    *   Shot Breakdown (2pt vs 3pt)
    *   Recent Games Log

### 3. Team Reports
Seasonal statistics and plays effectiveness ranking.
*   **Access**: From the main Dashboard or Team Stats page.
*   **Content**:
    *   Season Overview (Win/Loss, PPG)
    *   Team Plays Analysis (Top 10 plays by usage)
    *   Top Performers
    *   Plays Effectiveness Ranking (Ranked by FG%)

## Usage

### Downloading Reports

You can download reports directly from the web interface.

1.  Navigate to the specific game, player, or team page.
2.  Look for the **Export PDF** button (usually top right).
3.  The PDF will generate on-the-fly and download to your device.

### Preview Mode

Most reports offer a "Preview" button alongside the download option. This opens the PDF in a new browser tab for quick viewing without saving the file.

## Technical Details

The reporting engine uses **ReportLab** to generate PDFs programmatically.

*   **In-Memory Generation**: PDFs are built in RAM, ensuring fast response times and no server disk clutter.
*   **Vector Graphics**: Charts and tables use vector graphics for crisp printing at any resolution.
*   **Styles**: Custom stylesheets ensure consistent branding across all reports.

## Troubleshooting

**"PDF file is empty"**
*   Ensure the game/player has data. A game with 0 shots cannot generate a meaningful chart.

**"Generation Failed"**
*   Check the application logs. Common issues include missing font definitions or database connection timeouts.
