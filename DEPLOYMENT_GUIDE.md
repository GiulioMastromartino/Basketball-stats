# 🚀 Deployment Guide - Plays-Based PDF Export

**Branch:** `feature/live-game`  
**Date:** January 13, 2026  
**Component:** Plays-based shot tracking and PDF export  
**Status:** Ready for deployment

---

## Pre-Deployment Checklist

### Code Quality
- [ ] All 4 phases implemented (DB, Data Access, PDF Export, UI)
- [ ] All tests passing (`pytest tests/`)
- [ ] Code reviewed and approved
- [ ] No hardcoded paths or credentials
- [ ] No debug print statements
- [ ] Error messages are user-friendly
- [ ] Logging configured properly
- [ ] Security checks passed (SQL injection, XSS)

### Database
- [ ] Migration file created and tested locally
- [ ] Schema matches IMPLEMENTATION_SUMMARY.md
- [ ] Indexes created correctly
- [ ] Foreign keys set up properly
- [ ] Seed script working (`python scripts/seed_plays.py`)
- [ ] Backward compatible (no breaking changes)
- [ ] Rollback strategy documented

### Dependencies
- [ ] `reportlab==4.0.9` added to requirements.txt
- [ ] requirements.txt committed to repo
- [ ] No version conflicts with existing packages
- [ ] Tested in isolated virtual environment
- [ ] Package size acceptable (reportlab ~2MB)

### Documentation
- [ ] README.md updated with new features
- [ ] API documentation updated
- [ ] Database schema documented
- [ ] Sample API calls provided
- [ ] Troubleshooting guide complete
- [ ] IMPLEMENTATION_SUMMARY.md finalized
- [ ] COMMIT_MESSAGE.md in repo

### Testing
- [ ] Unit tests pass (plays_stats, pdf_export)
- [ ] Integration tests pass
- [ ] Manual testing complete:
  - [ ] Create test game with 20+ shots
  - [ ] Tag shots with various plays
  - [ ] Export game PDF - visually verified
  - [ ] Export player PDF - visually verified
  - [ ] Export team PDF - visually verified
  - [ ] Test JSON previews
  - [ ] Edge cases tested (no plays, single play, all misses)
  - [ ] PDFs open correctly in Adobe Reader, Preview, Chrome

### Performance
- [ ] Query times acceptable on staging DB
- [ ] PDF generation times < 500ms
- [ ] No N+1 query issues
- [ ] Memory usage reasonable
- [ ] Load testing completed (if applicable)

---

## Deployment Steps

### Step 1: Pre-Deployment (30 min)

```bash
# 1. Verify you're on feature/live-game branch
git status
# Output: On branch feature/live-game

# 2. Verify all changes committed
git status
# Output: working tree clean

# 3. View commit log
git log --oneline -5
# Verify: docs: add plays-based implementation...
# Verify: docs: add detailed commit message...
# Verify: docs: add detailed deployment guide...

# 4. Verify files exist
ls IMPLEMENTATION_SUMMARY.md
ls COMMIT_MESSAGE.md
ls DEPLOYMENT_GUIDE.md

# 5. Verify code structure
ls core/plays_stats.py
ls web/routes/pdf_export.py
ls migrations/versions/*plays*
ls scripts/seed_plays.py
```

### Step 2: Create Pull Request

```bash
# 1. Push feature/live-game to GitHub
git push origin feature/live-game

# 2. Go to GitHub repo
# https://github.com/GiulioMastromartino/basketball-stats

# 3. Create Pull Request
# - Base branch: main
# - Compare branch: feature/live-game
# - Title: "feat(plays-pdf-stats): add plays-based PDF export with player rankings"
# - Description: [Copy from COMMIT_MESSAGE.md full version]

# 4. Request reviewers
# - Add team members
# - Add relevant stakeholders

# 5. Wait for approval
# - Address review comments
# - Update PR if needed
```

### Step 3: Staging Deployment (1 hour)

```bash
# 1. SSH to staging server
ssh -i ~/.ssh/basketball-stats.pem ubuntu@staging.basketball-stats.com

# 2. Navigate to app directory
cd /app/basketball-stats

# 3. Pull latest code
git fetch origin
git checkout feature/live-game
git pull origin feature/live-game

# 4. Install dependencies
pip install -r requirements.txt
# Verify: Successfully installed reportlab-4.0.9

# 5. Backup database (CRITICAL)
mysqldump -u root -p basketball_stats > backup_$(date +%Y%m%d_%H%M%S).sql
# Store in: /backups/basketball_stats/

# 6. Run database migration
flask db upgrade
# Output: [SUCCESS] Add plays and shot_events tables

# 7. Seed initial plays
python scripts/seed_plays.py
# Output: [SUCCESS] Inserted 10 plays

# 8. Run tests
pytest tests/test_plays_stats.py -v
pytest tests/test_pdf_export.py -v
# All tests should pass

# 9. Start Flask app
flask run --host=0.0.0.0 --port=5000

# 10. Test API endpoints (in another terminal)
curl "http://staging.basketball-stats.com:5000/api/pdf/game/1/preview" | jq
# Should return: {plays_used: N, plays_coverage: X%}

# 11. Test PDF generation
curl "http://staging.basketball-stats.com:5000/api/pdf/game/1" -o test_game.pdf
file test_game.pdf
# Should output: PDF document, version 1.4

# 12. Verify in browser
# Navigate to: http://staging.basketball-stats.com/game/1
# - Check export buttons visible
# - Click "Export Game Plays" - PDF should download
# - Click "Export Team Plays" - PDF should download

# 13. Monitor logs
tail -f logs/app.log
# Should show no ERROR or WARNING messages
```

### Step 4: Production Deployment (1 hour)

**⚠️ BACKUP BEFORE PROCEEDING**

```bash
# 1. SSH to production server
ssh -i ~/.ssh/basketball-stats-prod.pem ubuntu@api.basketball-stats.com

# 2. Navigate to app directory
cd /app/basketball-stats

# 3. Create pre-deployment backup
date_backup=$(date +%Y%m%d_%H%M%S)
mysqldump -u root -p basketball_stats > /backups/prod_backup_${date_backup}.sql
echo "Backup created: /backups/prod_backup_${date_backup}.sql"

# 4. Verify backup
ls -lh /backups/prod_backup_${date_backup}.sql
# Should show file size > 1MB

# 5. Pull feature/live-game branch
git fetch origin
git checkout feature/live-game
git pull origin feature/live-game

# 6. Verify commit hashes match staging
git log --oneline -1
# Should match: git log --oneline -1 (on staging)

# 7. Install dependencies in production environment
pip install -r requirements.txt --upgrade
# Verify: Successfully installed reportlab-4.0.9

# 8. Run database migration
echo "Running migration..."
flask db upgrade
# Output: [SUCCESS] Add plays and shot_events tables

# 9. Seed initial plays
echo "Seeding plays..."
python scripts/seed_plays.py
# Output: [SUCCESS] Inserted 10 plays

# 10. Run final tests
echo "Running tests..."
pytest tests/test_plays_stats.py tests/test_pdf_export.py -v
# All should pass

# 11. Restart production service (if using systemd/gunicorn)
sudo systemctl restart basketball-stats
# Wait 10 seconds for restart
sleep 10

# 12. Verify service is running
sudo systemctl status basketball-stats
# Should show: active (running)

# 13. Test production endpoints
curl "https://api.basketball-stats.com/api/pdf/game/1/preview"
# Should return valid JSON

# 14. Monitor production logs
tail -f /var/log/basketball-stats/production.log
# Look for errors (none expected)

# 15. Create deployment record
echo "Deployment successful: $(date)" >> /deployments.log
```

### Step 5: Merge to Main

```bash
# 1. Ensure all tests passing in production
# (Complete Step 4 successfully)

# 2. Merge PR on GitHub
# - Click "Merge pull request" button
# - Confirm merge
# - Delete feature/live-game branch (optional)

# 3. Pull main locally
git checkout main
git pull origin main

# 4. Verify merge
git log --oneline -5
# Should show: Merge pull request... from feature/live-game

# 5. Tag release (optional but recommended)
git tag -a v1.1.0-plays-stats -m "Add plays-based statistics and PDF export"
git push origin v1.1.0-plays-stats
```

---

## Rollback Procedure

**If something goes wrong:**

```bash
# 1. Stop the app
sudo systemctl stop basketball-stats

# 2. Restore database from backup
mysql -u root -p basketball_stats < /backups/prod_backup_${date_backup}.sql

# 3. Revert code to previous version
git checkout main
git pull origin main

# 4. Restart app
sudo systemctl start basketball-stats

# 5. Verify
sudo systemctl status basketball-stats
curl "https://api.basketball-stats.com/health"

# 6. Create incident report
echo "Rollback executed at $(date). Reason: [explanation]" >> /deployments.log
```

---

## Monitoring Post-Deployment

### First 24 Hours
- [ ] Monitor error logs every 1 hour
- [ ] Check PDF generation performance
- [ ] Monitor database query times
- [ ] Check disk space
- [ ] Monitor memory usage
- [ ] Track user feedback

### First Week
- [ ] Daily log review
- [ ] Performance trending
- [ ] User adoption metrics
- [ ] Bug reports
- [ ] Database size growth

### Ongoing
- [ ] Weekly performance reports
- [ ] Monthly cost analysis (if cloud)
- [ ] Quarterly optimization review
- [ ] Plan enhancements based on usage

---

## Key Endpoints to Test

### Game Report
```bash
curl -v "https://api.basketball-stats.com/api/pdf/game/1" \
  -H "Accept: application/pdf" \
  -o game_report.pdf
# Expected: 200 OK, PDF file
```

### Player Report
```bash
curl -v "https://api.basketball-stats.com/api/pdf/player/John%20Smith?game_id=1" \
  -o player_report.pdf
# Expected: 200 OK, PDF file
```

### Team Report
```bash
curl -v "https://api.basketball-stats.com/api/pdf/team/1" \
  -o team_report.pdf
# Expected: 200 OK, PDF file (landscape)
```

### JSON Previews
```bash
curl "https://api.basketball-stats.com/api/pdf/game/1/preview" | jq
# Expected: {plays_used: N, plays_coverage: X%, ...}

curl "https://api.basketball-stats.com/api/pdf/team/1/preview" | jq
# Expected: {plays: [...with player_rankings...]}
```

---

## Troubleshooting

### PDF Generation Fails
```bash
# 1. Check ReportLab installed
pip list | grep reportlab
# Should show: reportlab 4.0.9

# 2. Check permissions
ls -l /tmp/
# Should be writable

# 3. Check disk space
df -h /
# Should have > 1GB free

# 4. Check logs
tail -50 logs/app.log | grep ERROR
```

### Database Migration Fails
```bash
# 1. Check current migration version
flask db current

# 2. Check migration history
flask db history

# 3. If stuck, upgrade step by step
flask db upgrade +1

# 4. Check database directly
mysql -u root -p basketball_stats
> SHOW TABLES;
> DESCRIBE plays;
> DESCRIBE shot_events;
```

### Seed Script Fails
```bash
# 1. Check plays table exists
mysql -u root -p basketball_stats \
  "SELECT COUNT(*) FROM plays;"

# 2. Run seed script with verbose output
python scripts/seed_plays.py -v

# 3. Check for duplicate keys
mysql -u root -p basketball_stats \
  "SHOW CREATE TABLE plays;"
```

---

## Support Contacts

- **Deployment Issues:** [Your DevOps Contact]
- **Database Issues:** [Your DBA]
- **Code Issues:** [Your Tech Lead]
- **Escalation:** [Your Manager]

---

## Related Documentation

- [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md) - Technical overview
- [COMMIT_MESSAGE.md](./COMMIT_MESSAGE.md) - Detailed commit info
- [README.md](./README.md) - Project overview
- [API_DOCUMENTATION.md](./docs/API_DOCUMENTATION.md) - API reference

---

## Deployment Status

| Environment | Status | Date | Notes |
|-------------|--------|------|-------|
| Local Dev | 💻 In Progress | - | - |
| Staging | 📤 Pending | - | Ready when Phase 1-4 complete |
| Production | 📤 Pending | - | After staging approval |

---

**Last Updated:** January 13, 2026  
**Branch:** `feature/live-game`  
**Status:** 📋 Ready for deployment  

Good luck with the deployment! 🌟
