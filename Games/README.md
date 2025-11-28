# CSV Games Directory

Place your game CSV files here.

## Filename Format

```
Opponent_TeamScore-OpponentScore_DD-MM-YYYY_Type.csv
```

### Examples

- `Lakers_105-98_15-03-2024_S.csv` - Season game (Won 105-98)
- `Warriors_88-102_20-03-2024_P.csv` - Playoff game (Lost 88-102)
- `Celtics_95-95_10-01-2024_F.csv` - Friendly game (Tied 95-95)

### Type Codes

- `F` = Friendly
- `S` = Season
- `P` = Playoff

## CSV Format

Must include these columns:

```
Name,MIN,PTS,FGM,FGA,FG%,3PM,3PA,3P%,FTM,FTA,FT%,OREB,DREB,REB,AST,TOV,STL,BLK,PF
John Doe,30:00,25,10,20,50,3,7,42.9,2,2,100,2,6,8,6,2,2,1,2
Jane Smith,28:00,22,9,18,50,2,5,40,2,3,66.7,3,9,12,4,3,1,0,3
```

## Import

Run: `python cli_import.py`
