# Complete Report Header Update Guide - Matching PDF Format

## ✅ Already Completed
1. **General Ledger** - ✓ DONE
2. **Trial Balance** - ✓ DONE

## 📋 Standard Header Template (To Apply to All Reports)

### Replace This Pattern:
```xml
<t t-call="web.internal_layout">
    <t t-set="data_report_margin_top" t-value="12"/>
    <t t-set="data_report_header_spacing" t-value="9"/>
    <div class="page">
        <h2>Report Title</h2>
```

### With This Pattern:
```xml
<t t-set="data_report_margin_top" t-value="15"/>
<t t-set="data_report_header_spacing" t-value="0"/>
<t t-set="data_report_dpi" t-value="110"/>

<!-- Custom clean layout - no default Odoo header -->
<div class="page" style="padding-top: 5px;">

    <!-- FULL HEADER -->
    <div style="text-align: center; margin-bottom: 18px;">
        <div style="font-size: 24px; font-weight: 700; letter-spacing: 0.5px; color: #111; margin-bottom: 4px;">
            <span t-esc="env.company.name"/>
        </div>
        <div style="font-size: 18px; font-weight: 600; color: #222; margin-bottom: 3px;">
            [REPORT TITLE HERE]
        </div>
        <div style="font-size: 14px; font-weight: 500; color: #444;">
            [DATE LINE HERE]
        </div>
    </div>

    <!-- Page number footer -->
    <div class="footer" style="width: 100%; text-align: right; font-size: 10px; color: #555;">
        <span class="page"/> / <span class="topage"/>
    </div>
```

## 🔧 Key Changes for Each Report

### 3. Partner Ledger (`report_partner_ledger_template.xml`)
**Title:** `Partner Ledger`
**Date Line:**
```xml
<t t-if="data['form'].get('date_to')">
    As of <span t-esc="data['form']['date_to']"/>
</t>
```

### 4. Financial Reports (`report_financial_template.xml`)
**Title:** `<span t-esc="data['form']['account_report_id'][1]"/>` (Dynamic)
**Date Line:**
```xml
<t t-if="data['form'].get('date_to')">
    As of <span t-esc="data['form']['date_to']"/>
</t>
```

### 5. Cash Flow (`cash_flow_report_template.xml`)
**Title:** `<span t-esc="data['account_report_id'][1]"/>` (Dynamic)
**Date Line:**
```xml
As of <span t-esc="data['date_to']"/>
```

### 6. Bank Book (`account_bank_book_template.xml`)
**Title:** `Bank Book`
**Date Line:**
```xml
<t t-if="data.get('date_to')">
    As of <span t-esc="data['date_to']"/>
</t>
```

### 7. Cash Book (`account_cash_book_template.xml`)
**Title:** `Cash Book`
**Date Line:**
```xml
<t t-if="data.get('date_to')">
    As of <span t-esc="data['date_to']"/>
</t>
```

### 8. Day Book (`account_day_book_template.xml`)
**Title:** `Day Book`
**Date Line:**
```xml
<t t-if="data.get('date_to')">
    As of <span t-esc="data['date_to']"/>
</t>
```

### 9. Aged Partner Balance (`report_aged_partner_template.xml`)
**Title:** `Aged Partner Balance`
**Date Line:**
```xml
<t t-if="data.get('date_from')">
    As of <span t-esc="data['date_from']"/>
</t>
```

### 10. Tax Report (`report_tax_template.xml`)
**Title:** `Tax Report`
**Date Line:**
```xml
<t t-if="data.get('date_to')">
    As of <span t-esc="data['date_to']"/>
</t>
```

### 11. Journal Audit (`report_journal_audit_template.xml`)
**Title:** `<span t-esc="o.name"/> Journal Audit` (Dynamic)
**Date Line:**
```xml
<span t-esc="context_timestamp(datetime.datetime.now()).strftime('%B %Y')"/>
```

## 💰 Currency Format Changes

### Replace ALL instances of:
```xml
<span t-esc="value"
      t-options="{'widget': 'monetary', 'display_currency': env.company.currency_id}"/>
```

### With:
```xml
<span t-esc="'{:,.2f}'.format(value)"/>
<span t-esc="env.company.currency_id.symbol"/>
```

## 📊 Table Styling Updates

### Update table tag:
```xml
<table class="table table-sm" style="border-collapse:collapse; width:100%; font-size:11.5px;">
```

### Header row style:
```xml
<tr style="background:#d9d9d9; border:1px solid #999; font-weight:bold;">
```

### Header cells with amounts:
```xml
<th style="padding:7px; border:1px solid #999; border-left:2px solid #666; text-align:right;">
```

### Data rows:
```xml
<td style="padding:6px; border:1px solid #ddd;">
```

### Amount cells in data rows:
```xml
<td class="text-end" style="padding:6px; border:1px solid #ddd; border-left:2px solid #999;">
```

## ⚠️ Important: Remove web.internal_layout

**CRITICAL:** Remove the `<t t-call="web.internal_layout">` wrapper completely!

### Before:
```xml
<t t-call="web.html_container">
    <t t-call="web.internal_layout">
        <div class="page">
```

### After:
```xml
<t t-call="web.html_container">
    <t t-set="data_report_margin_top" t-value="15"/>
    <t t-set="data_report_header_spacing" t-value="0"/>
    <div class="page" style="padding-top: 5px;">
```

## 🎨 Complete Example (General Ledger - Reference)

See `report/general_ledger_report_template.xml` for the complete, correct implementation.

Key features:
- No web.internal_layout
- Clean centered header (24px/18px/14px)
- Page numbers in footer
- Consistent table styling
- Manual currency formatting with {:,.2f}
- 11.5px font size for tables
- Proper borders (#999, #666, #ddd, #bbb)

## 🚀 Implementation Steps

For each report file:
1. Open the XML file
2. Remove `<t t-call="web.internal_layout">` wrapper
3. Update margin/spacing/dpi settings
4. Replace header section with standard template
5. Update report title and date line
6. Add page footer
7. Update table styling (font-size: 11.5px)
8. Replace all monetary t-options with manual formatting
9. Test PDF generation

## ✅ Verification Checklist

After updating each report:
- [ ] Header is centered with correct font sizes
- [ ] Date line shows "As of [Date]"
- [ ] Page numbers appear in footer
- [ ] Currency values show with 2 decimals + symbol
- [ ] Tables have consistent borders
- [ ] No Odoo default header/footer appears
- [ ] PDF prints correctly
- [ ] All data displays properly

##Note
All filter information sections can be removed or hidden as they're not part of the standard header format shown in your PDF.
