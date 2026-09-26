# Report Header Standardization - Odoo 18

## Overview
Updated all accounting report headers to follow a consistent, professional format matching the General Ledger report style shown in the reference PDF.

## Header Format
All reports now display:
```
[Company Name]
[Report Title]
As of [Date/Period]
```

- Company name: Bold, 18px, centered
- Report title: Bold, 16px, centered  
- Date line: 13px, centered

## Files Modified

### 1. New Template Created
- **report/report_header_template.xml** - Reusable header template component

### 2. Report Templates Updated
1. **report/general_ledger_report_template.xml** - General Ledger
2. **report/report_trial_balance_template.xml** - Trial Balance
3. **report/report_partner_ledger_template.xml** - Partner Ledger
4. **report/report_financial_template.xml** - Financial Reports (P&L, Balance Sheet, etc.)
5. **report/cash_flow_report_template.xml** - Cash Flow Statement
6. **report/account_bank_book_template.xml** - Bank Book
7. **report/account_cash_book_template.xml** - Cash Book
8. **report/account_day_book_template.xml** - Day Book
9. **report/report_aged_partner_template.xml** - Aged Partner Balance
10. **report/report_tax_template.xml** - Tax Report
11. **report/report_journal_audit_template.xml** - Journal Audit

### 3. Manifest Updated
- **__manifest__.py** - Added report_header_template.xml to data files

## Changes Made

### Before (Old Format)
```xml
<h2><span t-esc="env.company.name"/>: General ledger</h2>
```

### After (New Format)
```xml
<div style="text-align: center; margin-bottom: 30px; margin-top: 20px;">
    <h2 style="margin: 0; font-size: 18px; font-weight: bold;">
        <span t-esc="env.company.name"/>
    </h2>
    <h3 style="margin: 5px 0; font-size: 16px; font-weight: bold;">
        General Ledger
    </h3>
    <p style="margin: 5px 0; font-size: 13px;">
        As of <span t-esc="data['date_to']"/>
    </p>
</div>
```

## Additional Improvements
- Reduced filter section font size to 11px for cleaner appearance
- Added consistent spacing between header and content
- Maintained all existing functionality and data fields
- Filter information remains visible but less prominent

## Testing Recommendations
1. Print/preview each report type
2. Verify date formatting displays correctly
3. Check reports with and without date ranges
4. Ensure company name displays properly for multi-company setups
5. Verify PDF generation maintains formatting

## Compatibility
- Odoo 18 Community Edition
- Compatible with existing report data and wizards
- No database changes required
- Module upgrade required after installation

## Notes
- All reports maintain their existing data structure
- Only visual presentation changed
- Filter options still fully functional
- Report content and calculations unchanged
