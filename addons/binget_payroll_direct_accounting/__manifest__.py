{
    "name": "Binget Payroll - Direct Accounting Sides",
    "version": "18.0.1.0.0",
    "summary": "Makes salary rule Debit/Credit Account fields post exactly as their name says, with no automatic sign-based flipping.",
    "description": """
Standard OCA payroll_account decides whether a rule posts as a debit or a
credit based on the *sign* of the rule's computed result, regardless of
which field (Debit Account / Credit Account) the account was placed in.
That is confusing for anyone configuring or auditing salary rules, because
a "Debit Account" can end up posting as a credit line, and vice versa.

This module removes that auto-flip behaviour:

- Debit Account  -> always posts the line's absolute amount as a DEBIT.
- Credit Account -> always posts the line's absolute amount as a CREDIT.

What you set on the rule is exactly what you get on the Journal Entry.
""",
    "category": "Human Resources/Payroll",
    "author": "Binget Holding",
    "license": "AGPL-3",
    "depends": ["payroll_account"],
    "installable": True,
    "application": False,
}
