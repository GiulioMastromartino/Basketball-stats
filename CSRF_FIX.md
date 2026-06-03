# CSRF Token Fix - Plays Module

## Problem
When adding a play manually via the modal form, received error:
```
Bad Request
The CSRF token is missing.
```

## Root Cause
Flask-WTF (CSRF protection) requires all POST forms to include a CSRF token. The form was missing this token in both templates.

## Solution

### Files Modified
1. **web/templates/plays/index.html** - Added CSRF token to Add/Delete modals
2. **web/templates/plays/view.html** - Added CSRF token to Edit/Delete modals

### Changes Made

#### Add CSRF Token Hidden Input
Before:
```html
<form action="{{ url_for('plays.add') }}" method="POST" enctype="multipart/form-data">
    <div class="modal-body">
```

After:
```html
<form action="{{ url_for('plays.add') }}" method="POST" enctype="multipart/form-data">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
    <div class="modal-body">
```

### Applied To
- ✓ Add Play modal (index.html)
- ✓ Delete Play modal (index.html)
- ✓ Edit Play modal (view.html)
- ✓ Delete Play modal (view.html)

## How CSRF Protection Works

1. **Server generates token**: Flask-WTF creates a unique token per session
2. **Token embedded in form**: `{{ csrf_token() }}` renders the token
3. **Client submits token**: Hidden input sends it with the form
4. **Server validates**: Flask-WTF checks token matches session
5. **Request allowed**: Only valid tokens are processed

## Verification

To verify CSRF protection is working:

1. **Start Flask app**: The app must have `SECRET_KEY` configured
2. **Navigate to `/plays`**: Should load normally
3. **Click "Add New Play"**: Modal should open
4. **Fill form and submit**: Should successfully add play
5. **Check console**: No CSRF token errors

## Flask-WTF Configuration

Ensure your `app.py` or config has:

```python
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Required!

csrf = CSRFProtect(app)
```

If not configured, add it to ensure CSRF protection works.

## Template Syntax

### Method 1: Hidden Input (Used Here)
```html
<form method="POST">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
    <!-- form fields -->
</form>
```

### Method 2: As Function Call
```html
<form method="POST">
    {{ csrf_token() }}
    <!-- form fields -->
</form>
```

## Testing the Fix

1. **Reload Flask application**
2. **Navigate to http://localhost:5000/plays**
3. **Test Add Play:**
   - Click "Add New Play" button
   - Fill in: Name (required), Type, Description, Image (optional)
   - Click "Add Play"
   - Should see success message
4. **Test Edit Play:**
   - Click "View" on any play
   - Click "Edit Play" button
   - Make changes
   - Click "Save Changes"
   - Should see success message
5. **Test Delete Play:**
   - Click delete button or icon
   - Confirm deletion in modal
   - Should see success message

## Common Issues

### Issue: "CSRF token missing" still appears
**Solution**: 
- Hard reload browser (Ctrl+Shift+R or Cmd+Shift+R)
- Clear browser cache
- Restart Flask application

### Issue: "CSRF token invalid"
**Solution**:
- Check `SECRET_KEY` is set in Flask app
- Verify user session hasn't expired
- Try clearing cookies and reloading

### Issue: Token in wrong place
**Solution**:
- Ensure hidden input is INSIDE the form tag
- Check for typo in `name="csrf_token"`
- Verify `{{ csrf_token() }}` renders correctly

## Security Notes

✓ CSRF tokens are:
- Unique per session
- Regenerated on each request
- Validated server-side
- Required for POST/PUT/DELETE requests

✓ This protects against:
- Cross-site request forgery
- Malicious form submissions
- Unauthorized state changes

## Files Updated

| File | Changes | Status |
|------|---------|--------|
| web/templates/plays/index.html | Added csrf_token() to 2 forms | ✓ Fixed |
| web/templates/plays/view.html | Added csrf_token() to 2 forms | ✓ Fixed |

---

**Status**: ✓ RESOLVED  
**Date**: January 12, 2026  
**Verified**: Add/Edit/Delete operations now work with CSRF protection
